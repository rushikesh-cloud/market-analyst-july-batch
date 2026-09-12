"""Annual report storage, ingestion state, and Markdown chunking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import os
from pathlib import Path
import re
import shutil
from typing import Literal
from uuid import uuid4

import tiktoken
from fastapi import APIRouter, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    delete,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, defer, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from app.companies import Base, Company, engine


MAX_PDF_BYTES = 50 * 1024 * 1024
EMBEDDING_DIMENSIONS = int(os.environ.get("RAG_VECTOR_DIMENSIONS", "1536"))
PIPELINE_STAGES = ("queued", "parse", "chunk", "embed", "index", "complete")
CHUNKING_VERSION = "page-header-v2"
TERMINAL_STATUSES = {"complete", "failed"}
workspace_root = Path(
    os.environ.get("MARKET_ANALYST_WORKSPACE_ROOT", Path(__file__).resolve().parents[2])
).resolve()


def utcnow() -> datetime:
    return datetime.now(UTC)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("company_id", "fiscal_year"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(ForeignKey("companies.id"), index=True)
    fiscal_year: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    markdown: Mapped[str | None] = mapped_column(Text)
    embedding_deployment: Mapped[str | None] = mapped_column(String(200))
    embedding_dimensions: Mapped[int | None] = mapped_column(Integer)
    chunking_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    company: Mapped[Company] = relationship()


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class IngestionStage(Base):
    __tablename__ = "ingestion_stages"
    __table_args__ = (UniqueConstraint("run_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("ingestion_runs.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(30))
    position: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    completed_items: Mapped[int | None] = mapped_column(Integer)
    total_items: Mapped[int | None] = mapped_column(Integer)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (UniqueConstraint("document_id", "sequence"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    page_number: Mapped[int] = mapped_column(Integer, default=1, index=True)
    chunk_type: Mapped[str] = mapped_column(String(20))
    heading_path: Mapped[list[str]] = mapped_column(JSON)
    content: Mapped[str] = mapped_column(Text)
    overlap_text: Mapped[str] = mapped_column(Text, default="")
    token_count: Mapped[int] = mapped_column(Integer)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))


class CompanySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    ticker: str


class DocumentOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    company_id: str
    company: CompanySummary
    fiscal_year: int
    filename: str
    storage_path: str
    status: str
    created_at: datetime
    updated_at: datetime


class StageOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str
    status: str
    completed_items: int | None
    total_items: int | None
    started_at: datetime | None
    finished_at: datetime | None
    error: str | None


class StatusOutput(BaseModel):
    document_id: str
    status: str
    attempt: int
    error: str | None
    stages: list[StageOutput]


class ChunkOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    sequence: int
    page_number: int
    chunk_type: str
    heading_path: list[str]
    content: str
    overlap_text: str
    token_count: int


class ChunkPage(BaseModel):
    items: list[ChunkOutput]
    total: int
    offset: int
    limit: int


class ContentOutput(BaseModel):
    markdown: str
    page: int
    page_count: int


router = APIRouter(prefix="/api/documents", tags=["documents"])


def require_postgres() -> None:
    if engine.dialect.name != "postgresql":
        raise HTTPException(503, "Document ingestion requires PostgreSQL with pgvector.")


def resolve_document_path(relative_path: str) -> Path:
    candidate = (workspace_root / relative_path).resolve()
    documents_root = (workspace_root / "documents").resolve()
    if candidate != documents_root and documents_root not in candidate.parents:
        raise ValueError("Document path must remain inside the documents directory.")
    return candidate


def _document(session: Session, document_id: str) -> Document:
    item = session.get(Document, document_id)
    if item is None or item.deleted_at is not None:
        raise HTTPException(404, "Document not found.")
    return item


def _new_run(session: Session, document: Document, attempt: int) -> IngestionRun:
    run = IngestionRun(id=str(uuid4()), document_id=document.id, attempt=attempt)
    session.add(run)
    session.flush()
    for position, name in enumerate(PIPELINE_STAGES):
        session.add(
            IngestionStage(
                id=str(uuid4()), run_id=run.id, name=name, position=position,
                status="complete" if name == "queued" else "pending",
                started_at=utcnow() if name == "queued" else None,
                finished_at=utcnow() if name == "queued" else None,
            )
        )
    return run


def enqueue_stale_documents() -> int:
    """Requeue parsed documents when chunk metadata requires an upgrade."""
    queued = 0
    with Session(engine) as session:
        items = session.scalars(
            select(Document).where(
                Document.markdown.is_not(None),
                or_(
                    Document.chunking_version.is_(None),
                    Document.chunking_version != CHUNKING_VERSION,
                ),
                Document.status.not_in(("queued", "parse", "chunk", "embed", "index")),
            )
        ).all()
        for item in items:
            latest = session.scalar(
                select(IngestionRun.attempt)
                .where(IngestionRun.document_id == item.id)
                .order_by(IngestionRun.attempt.desc())
            ) or 0
            item.status = "queued"
            item.updated_at = utcnow()
            _new_run(session, item, latest + 1)
            queued += 1
        session.commit()
    return queued


@router.post("", response_model=DocumentOutput, status_code=202)
async def upload_document(
    company_id: str = Form(...), fiscal_year: int = Form(...), file: UploadFile = File(...)
):
    require_postgres()
    maximum_year = utcnow().year + 1
    if not 1900 <= fiscal_year <= maximum_year:
        raise HTTPException(422, f"Fiscal year must be between 1900 and {maximum_year}.")
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".pdf") or file.content_type != "application/pdf":
        raise HTTPException(422, "Upload a PDF file.")

    document_id = str(uuid4())
    relative_path = f"documents/{document_id}/source.pdf"
    destination = resolve_document_path(relative_path)
    destination.parent.mkdir(parents=True, exist_ok=False)
    size = 0
    header = b""
    try:
        with destination.open("wb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_PDF_BYTES:
                    raise HTTPException(413, "PDF exceeds the 50 MB upload limit.")
                if len(header) < 5:
                    header += chunk[: 5 - len(header)]
                output.write(chunk)
        if header != b"%PDF-":
            raise HTTPException(422, "The uploaded file is not a valid PDF.")
        with Session(engine) as session:
            if session.get(Company, company_id) is None:
                raise HTTPException(422, "Select an existing company.")
            document = Document(
                id=document_id, company_id=company_id, fiscal_year=fiscal_year,
                filename=filename, storage_path=relative_path,
            )
            session.add(document)
            try:
                session.flush()
                _new_run(session, document, 1)
                session.commit()
            except IntegrityError as error:
                session.rollback()
                raise HTTPException(
                    409, "A report already exists for this company and fiscal year."
                ) from error
            session.refresh(document)
            _ = document.company
            return document
    except BaseException:
        shutil.rmtree(destination.parent, ignore_errors=True)
        raise
    finally:
        await file.close()


@router.get("", response_model=list[DocumentOutput])
def list_documents(company_id: str | None = None, fiscal_year: int | None = None):
    with Session(engine) as session:
        statement = select(Document).where(Document.deleted_at.is_(None))
        if company_id:
            statement = statement.where(Document.company_id == company_id)
        if fiscal_year is not None:
            statement = statement.where(Document.fiscal_year == fiscal_year)
        documents = session.scalars(statement.order_by(Document.created_at.desc())).all()
        for item in documents:
            _ = item.company
        return documents


@router.get("/{document_id}", response_model=DocumentOutput)
def get_document(document_id: str):
    with Session(engine) as session:
        item = _document(session, document_id)
        _ = item.company
        return item


@router.get("/{document_id}/status", response_model=StatusOutput)
def get_status(document_id: str):
    with Session(engine) as session:
        item = _document(session, document_id)
        run = session.scalars(
            select(IngestionRun).where(IngestionRun.document_id == item.id)
            .order_by(IngestionRun.attempt.desc())
        ).first()
        if run is None:
            raise HTTPException(404, "Ingestion run not found.")
        stages = session.scalars(
            select(IngestionStage).where(IngestionStage.run_id == run.id)
            .order_by(IngestionStage.position)
        ).all()
        return StatusOutput(
            document_id=item.id, status=item.status, attempt=run.attempt,
            error=run.error, stages=[StageOutput.model_validate(stage) for stage in stages],
        )


def split_markdown_pages(markdown: str) -> list[str]:
    return [
        page.strip()
        for page in re.split(r"\s*<!--\s*PageBreak\s*-->\s*", markdown)
    ]


@router.get("/{document_id}/content", response_model=ContentOutput)
def get_content(document_id: str, page: int = Query(1, ge=1)):
    with Session(engine) as session:
        item = _document(session, document_id)
        if item.markdown is None:
            raise HTTPException(409, "Document content is not available yet.")
        pages = split_markdown_pages(item.markdown)
        if page > len(pages):
            raise HTTPException(404, "Document page not found.")
        return ContentOutput(markdown=pages[page - 1], page=page, page_count=len(pages))


@router.get("/{document_id}/chunks", response_model=ChunkPage)
def get_chunks(
    document_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    page: int | None = Query(None, ge=1),
):
    with Session(engine) as session:
        item = _document(session, document_id)
        statement = select(DocumentChunk).where(DocumentChunk.document_id == item.id)
        if page is not None:
            statement = statement.where(DocumentChunk.page_number == page)
        all_items = session.scalars(
            statement
            .options(defer(DocumentChunk.embedding))
            .order_by(DocumentChunk.sequence)
        ).all()
        return ChunkPage(
            items=[ChunkOutput.model_validate(value) for value in all_items[offset:offset + limit]],
            total=len(all_items), offset=offset, limit=limit,
        )


@router.post("/{document_id}/retry", response_model=DocumentOutput, status_code=202)
def retry_document(document_id: str):
    require_postgres()
    with Session(engine) as session:
        item = _document(session, document_id)
        if item.status != "failed":
            raise HTTPException(409, "Only failed ingestion can be retried.")
        latest = session.scalar(
            select(IngestionRun.attempt).where(IngestionRun.document_id == item.id)
            .order_by(IngestionRun.attempt.desc())
        ) or 0
        item.status = "queued"
        item.updated_at = utcnow()
        _new_run(session, item, latest + 1)
        session.commit()
        session.refresh(item)
        _ = item.company
        return item


@router.delete("/{document_id}", status_code=204)
def delete_document(document_id: str):
    with Session(engine) as session:
        item = _document(session, document_id)
        item.deleted_at = utcnow()  # Fences workers before physical cleanup.
        item.status = "deleted"
        session.commit()
        path = resolve_document_path(item.storage_path)
        shutil.rmtree(path.parent, ignore_errors=True)
        run_ids = select(IngestionRun.id).where(IngestionRun.document_id == item.id)
        session.execute(delete(IngestionStage).where(IngestionStage.run_id.in_(run_ids)))
        session.execute(delete(IngestionRun).where(IngestionRun.document_id == item.id))
        session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == item.id))
        session.delete(item)
        session.commit()
        return Response(status_code=204)


@dataclass(frozen=True)
class ChunkDraft:
    sequence: int
    page_number: int
    chunk_type: Literal["para", "table"]
    heading_path: list[str]
    content: str
    overlap_text: str
    token_count: int


_encoding = tiktoken.get_encoding("cl100k_base")


def _tokens(value: str) -> list[int]:
    return _encoding.encode(value)


def _decode(tokens: list[int]) -> str:
    return _encoding.decode(tokens)


def _split_to_limit(content: str, heading_prefix: str, available: int) -> list[str]:
    tokens = _tokens(content)
    if len(tokens) <= available:
        return [content.strip()]
    return [_decode(tokens[index:index + available]).strip() for index in range(0, len(tokens), available)]


def _split_table_to_limit(content: str, available: int) -> list[str]:
    if len(_tokens(content)) <= available:
        return [content.strip()]
    if content.lstrip().lower().startswith("<table"):
        opening = re.search(r"<table[^>]*>", content, re.IGNORECASE)
        rows = re.findall(r"<tr[^>]*>.*?</tr>", content, re.IGNORECASE | re.DOTALL)
        if opening and rows:
            header = rows[0] if "<th" in rows[0].lower() else ""
            parts: list[str] = []
            current = [opening.group(0), header] if header else [opening.group(0)]
            for row in rows[1:] if header else rows:
                candidate = "\n".join(current + [row, "</table>"])
                if len(_tokens(candidate)) > available and len(current) > (2 if header else 1):
                    parts.append("\n".join(current + ["</table>"]))
                    current = [opening.group(0), header, row] if header else [opening.group(0), row]
                else:
                    current.append(row)
            if len(current) > 1:
                parts.append("\n".join(current + ["</table>"]))
            if parts and all(len(_tokens(part)) <= available for part in parts):
                return parts
    else:
        lines = content.splitlines()
        if len(lines) >= 3:
            header = lines[:2]
            parts, current = [], header.copy()
            for row in lines[2:]:
                candidate = "\n".join(current + [row])
                if len(_tokens(candidate)) > available and len(current) > 2:
                    parts.append("\n".join(current))
                    current = header + [row]
                else:
                    current.append(row)
            if len(current) > 2:
                parts.append("\n".join(current))
            if parts and all(len(_tokens(part)) <= available for part in parts):
                return parts
    return _split_to_limit(content, "", available)


def chunk_markdown(markdown: str, max_tokens: int = 2000, overlap_tokens: int = 50) -> list[ChunkDraft]:
    if max_tokens <= overlap_tokens:
        raise ValueError("max_tokens must be greater than overlap_tokens")
    headings: list[str] = []
    blocks: list[tuple[str, list[str], str, int]] = []
    paragraph: list[str] = []
    table: list[str] = []
    html_table = False
    page_number = 1

    def flush_paragraph():
        if paragraph:
            blocks.append(("para", headings.copy(), "\n".join(paragraph).strip(), page_number))
            paragraph.clear()

    def flush_table():
        if table:
            blocks.append(("table", headings.copy(), "\n".join(table).strip(), page_number))
            table.clear()

    for line in markdown.splitlines():
        heading = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        stripped = line.strip()
        starts_html_table = bool(re.match(r"<table(?:\s|>)", stripped, re.IGNORECASE))
        is_pipe_table = line.lstrip().startswith("|") and line.rstrip().endswith("|")
        if re.fullmatch(r"<!--\s*PageBreak\s*-->", stripped, re.IGNORECASE):
            flush_paragraph(); flush_table()
            html_table = False
            page_number += 1
        elif html_table or starts_html_table:
            if not html_table:
                flush_paragraph()
                html_table = True
            table.append(line)
            if re.search(r"</table>\s*$", stripped, re.IGNORECASE):
                html_table = False
                flush_table()
        elif heading:
            flush_paragraph(); flush_table()
            level = len(heading.group(1))
            headings[:] = headings[: level - 1]
            headings.append(heading.group(2).strip())
        elif is_pipe_table:
            flush_paragraph(); table.append(line)
        elif not stripped:
            flush_table()
            if paragraph and paragraph[-1] != "":
                paragraph.append("")
        else:
            flush_table(); paragraph.append(line)
    flush_paragraph(); flush_table()

    drafts: list[ChunkDraft] = []
    previous_original = ""
    for chunk_type, path, block, block_page in blocks:
        overlap = _decode(_tokens(previous_original)[-overlap_tokens:]) if previous_original else ""
        prefix = " > ".join(path)
        # Reserve the full overlap budget for every continuation; later pieces
        # overlap their immediate predecessor rather than the prior block.
        reserved = len(_tokens(prefix)) + overlap_tokens + 2
        available = max(1, max_tokens - reserved)
        parts = _split_table_to_limit(block, available) if chunk_type == "table" else _split_to_limit(block, prefix, available)
        for part in parts:
            part_overlap = _decode(_tokens(previous_original)[-overlap_tokens:]) if previous_original else ""
            combined = "\n".join(value for value in (prefix, part_overlap, part) if value)
            drafts.append(ChunkDraft(
                sequence=len(drafts), page_number=block_page,
                chunk_type=chunk_type, heading_path=path.copy(),
                content=part, overlap_text=part_overlap, token_count=len(_tokens(combined)),
            ))
            previous_original = part
    return drafts
