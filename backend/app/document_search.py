"""Document-scoped hybrid retrieval with reciprocal rank fusion."""
from __future__ import annotations

import json
import math

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.companies import engine
from app.documents import ChunkOutput, EMBEDDING_DIMENSIONS, _document, require_postgres
from app.resources import get_resource_clients

router = APIRouter(prefix='/api/documents', tags=['documents'])


class SearchInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    query: str = Field(min_length=1, max_length=2000)
    k: int = Field(default=10, ge=1, le=100, strict=True)
    max_tokens: int = Field(default=10000, ge=1, le=100000, strict=True)


class SearchChunk(ChunkOutput):
    score: float
    semantic_rank: int | None
    text_rank: int | None


class SearchOutput(BaseModel):
    query: str
    k: int
    max_tokens: int
    items: list[SearchChunk]
    total_tokens: int
    budget_limited: bool


# Exact vector ranking within one document avoids global ANN filtering losses.
# Both candidate lists use the same document scope and stable sequence tie-breaker.
HYBRID_QUERY = text("""
WITH semantic AS (
    SELECT id, row_number() OVER (
        ORDER BY embedding <=> CAST(:embedding AS vector), sequence
    ) AS semantic_rank
    FROM document_chunks
    WHERE document_id = :document_id AND embedding IS NOT NULL
    ORDER BY embedding <=> CAST(:embedding AS vector), sequence
    LIMIT :candidate_limit
), lexical AS (
    SELECT id, row_number() OVER (
        ORDER BY ts_rank_cd(
            to_tsvector('english', content || ' ' || heading_path::text),
            websearch_to_tsquery('english', :query)
        ) DESC, sequence
    ) AS text_rank
    FROM document_chunks
    WHERE document_id = :document_id
      AND to_tsvector('english', content || ' ' || heading_path::text)
          @@ websearch_to_tsquery('english', :query)
    ORDER BY text_rank
    LIMIT :candidate_limit
), fused AS (
    SELECT coalesce(s.id, l.id) AS id, s.semantic_rank, l.text_rank,
           coalesce(1.0 / (60 + s.semantic_rank), 0.0)
           + coalesce(1.0 / (60 + l.text_rank), 0.0) AS score
    FROM semantic s FULL OUTER JOIN lexical l ON s.id = l.id
)
SELECT c.id, c.sequence, c.page_number, c.chunk_type, c.heading_path,
       c.content, c.overlap_text, c.token_count,
       f.score, f.semantic_rank, f.text_rank
FROM fused f JOIN document_chunks c ON c.id = f.id
JOIN documents d ON d.id = c.document_id
WHERE d.id = :document_id AND d.deleted_at IS NULL
ORDER BY f.score DESC, c.sequence
""")


def query_embedding(query: str, deployment: str) -> list[float]:
    try:
        client = get_resource_clients().openai().with_options(timeout=20.0, max_retries=1)
        response = client.embeddings.create(model=deployment, input=[query])
        vector = response.data[0].embedding
        if (len(vector) != EMBEDDING_DIMENSIONS
                or not all(math.isfinite(value) for value in vector)
                or not any(vector)):
            raise ValueError('Invalid query embedding.')
        return vector
    except Exception as error:
        # Provider errors may include endpoints or credentials; never expose them.
        raise HTTPException(503, 'Search embeddings are unavailable. Please retry.') from error


@router.post('/{document_id}/search', response_model=SearchOutput)
def search_document(document_id: str, payload: SearchInput):
    require_postgres()
    try:
        with Session(engine) as session:
            document = _document(session, document_id)
            if (document.status != 'complete' or not document.embedding_deployment
                    or document.embedding_dimensions != EMBEDDING_DIMENSIONS):
                raise HTTPException(409, 'Search is available after document ingestion completes.')
            vector = query_embedding(payload.query, document.embedding_deployment)
            rows = session.execute(HYBRID_QUERY, {
                'document_id': document_id,
                'query': payload.query,
                'embedding': json.dumps(vector),
                'candidate_limit': max(50, payload.k * 5),
            }).mappings()
            items = []
            total_tokens = 0
            budget_limited = False
            for row in rows:
                if total_tokens + row['token_count'] > payload.max_tokens:
                    budget_limited = True
                    continue
                items.append(SearchChunk.model_validate(row))
                total_tokens += row['token_count']
                if len(items) == payload.k:
                    break
            return SearchOutput(
                query=payload.query, k=payload.k, max_tokens=payload.max_tokens,
                items=items, total_tokens=total_tokens, budget_limited=budget_limited,
            )
    except SQLAlchemyError as error:
        raise HTTPException(503, 'Document search is unavailable. Please retry.') from error
