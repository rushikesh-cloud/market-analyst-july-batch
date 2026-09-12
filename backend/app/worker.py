"""Durable PostgreSQL worker for annual-report ingestion."""

from __future__ import annotations

import argparse
from datetime import timedelta
import os
import socket
import time
from uuid import uuid4

from azure.ai.documentintelligence.models import AnalyzeDocumentRequest, DocumentContentFormat
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, defer

from app.companies import engine
from app.documents import (
    Document,
    DocumentChunk,
    CHUNKING_VERSION,
    EMBEDDING_DIMENSIONS,
    IngestionRun,
    IngestionStage,
    chunk_markdown,
    resolve_document_path,
    utcnow,
)
from app.resources import get_resource_clients


LEASE_MINUTES = 10


def _create_embeddings(client, deployment: str, inputs: list[str]):
    """Retry transient Azure routing failures without losing batch progress."""
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            return client.embeddings.create(model=deployment, input=inputs)
        except Exception as error:
            last_error = error
            status = getattr(error, "status_code", None)
            code = getattr(error, "code", None)
            if status not in {404, 408, 429, 500, 502, 503, 504} and code != "DeploymentNotFound":
                raise
            if attempt < 4:
                time.sleep(min(2 ** attempt, 8))
    raise last_error or RuntimeError("Embedding request failed.")


def claim_run(owner: str) -> str | None:
    """Atomically claim the oldest queued or expired run."""
    now = utcnow()
    with Session(engine, expire_on_commit=False) as session, session.begin():
        statement = (
            select(IngestionRun)
            .join(Document, Document.id == IngestionRun.document_id)
            .where(
                Document.deleted_at.is_(None),
                IngestionRun.status.in_(("queued", "processing")),
                (IngestionRun.lease_expires_at.is_(None))
                | (IngestionRun.lease_expires_at < now),
            )
            .order_by(IngestionRun.created_at)
            .with_for_update(skip_locked=True)
        )
        run = session.scalars(statement).first()
        if run is None:
            return None
        run.status = "processing"
        run.started_at = run.started_at or now
        run.lease_owner = owner
        run.lease_expires_at = now + timedelta(minutes=LEASE_MINUTES)
        document = session.get(Document, run.document_id)
        if document:
            document.status = "parse"
            document.updated_at = now
        return run.id


def _stage(session: Session, run_id: str, name: str) -> IngestionStage:
    return session.scalar(
        select(IngestionStage).where(
            IngestionStage.run_id == run_id, IngestionStage.name == name
        )
    )


def _start_stage(session: Session, run: IngestionRun, document: Document, name: str) -> None:
    now = utcnow()
    stage = _stage(session, run.id, name)
    stage.status = "processing"
    stage.started_at = stage.started_at or now
    document.status = name
    document.updated_at = now
    run.lease_expires_at = now + timedelta(minutes=LEASE_MINUTES)
    session.commit()


def _complete_stage(session: Session, run: IngestionRun, name: str, count: int | None = None) -> None:
    stage = _stage(session, run.id, name)
    stage.status = "complete"
    stage.completed_items = count
    stage.total_items = count
    stage.finished_at = utcnow()
    session.commit()


def _ensure_active(session: Session, document_id: str, owner: str) -> tuple[IngestionRun, Document]:
    run = session.scalar(
        select(IngestionRun).where(
            IngestionRun.document_id == document_id,
            IngestionRun.lease_owner == owner,
            IngestionRun.status == "processing",
        ).order_by(IngestionRun.attempt.desc())
    )
    document = session.get(Document, document_id)
    if run is None or document is None or document.deleted_at is not None:
        raise RuntimeError("Ingestion was cancelled.")
    return run, document


def process_run(run_id: str, owner: str) -> None:
    resources = get_resource_clients()
    try:
        with Session(engine, expire_on_commit=False) as session:
            run = session.get(IngestionRun, run_id)
            if run is None or run.lease_owner != owner:
                return
            document = session.get(Document, run.document_id)
            if document is None or document.deleted_at is not None:
                return

            _start_stage(session, run, document, "parse")
            if document.markdown is None:
                pdf = resolve_document_path(document.storage_path).read_bytes()
                poller = resources.document_intelligence().begin_analyze_document(
                    "prebuilt-layout",
                    AnalyzeDocumentRequest(bytes_source=pdf),
                    output_content_format=DocumentContentFormat.MARKDOWN,
                )
                markdown = poller.result().content or ""
                run, document = _ensure_active(session, document.id, owner)
                document.markdown = markdown
            else:
                markdown = document.markdown
            _complete_stage(session, run, "parse")

            _start_stage(session, run, document, "chunk")
            chunks = list(session.scalars(
                select(DocumentChunk).where(DocumentChunk.document_id == document.id)
                .options(defer(DocumentChunk.embedding))
                .order_by(DocumentChunk.sequence)
            ))
            if document.chunking_version != CHUNKING_VERSION:
                session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
                chunks = []
            if not chunks:
                drafts = chunk_markdown(markdown)
                chunks = [
                    DocumentChunk(
                        id=str(uuid4()), document_id=document.id, sequence=draft.sequence,
                        chunk_type=draft.chunk_type, heading_path=draft.heading_path,
                        content=draft.content, overlap_text=draft.overlap_text,
                        token_count=draft.token_count,
                    ) for draft in drafts
                ]
                session.add_all(chunks)
                document.chunking_version = CHUNKING_VERSION
                session.commit()
            _complete_stage(session, run, "chunk", len(chunks))

            _start_stage(session, run, document, "embed")
            deployment = resources.settings.openai.embedding_deployment
            pending_ids = set(session.scalars(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.embedding.is_(None),
                )
            ))
            pending = [chunk for chunk in chunks if chunk.id in pending_ids]
            for offset in range(0, len(pending), 16):
                run, document = _ensure_active(session, document.id, owner)
                batch = pending[offset:offset + 16]
                inputs = [
                    "\n".join(
                        value for value in (
                            " > ".join(chunk.heading_path), chunk.overlap_text, chunk.content
                        ) if value
                    ) for chunk in batch
                ]
                response = _create_embeddings(resources.openai(), deployment, inputs)
                vectors = [item.embedding for item in response.data]
                if any(len(vector) != EMBEDDING_DIMENSIONS for vector in vectors):
                    raise RuntimeError(
                        f"Embedding deployment returned an unexpected dimension; expected {EMBEDDING_DIMENSIONS}."
                    )
                for chunk, vector in zip(batch, vectors, strict=True):
                    chunk.embedding = vector
                stage = _stage(session, run.id, "embed")
                stage.total_items = len(chunks)
                stage.completed_items = len(chunks) - len(pending) + offset + len(batch)
                run.lease_expires_at = utcnow() + timedelta(minutes=LEASE_MINUTES)
                session.commit()
            document.embedding_deployment = deployment
            document.embedding_dimensions = EMBEDDING_DIMENSIONS
            _complete_stage(session, run, "embed", len(chunks))

            _start_stage(session, run, document, "index")
            missing = session.scalar(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document.id,
                    DocumentChunk.embedding.is_(None),
                ).limit(1)
            )
            if missing:
                raise RuntimeError("One or more chunks have no embedding.")
            _complete_stage(session, run, "index", len(chunks))

            _start_stage(session, run, document, "complete")
            now = utcnow()
            stage = _stage(session, run.id, "complete")
            stage.status = "complete"
            stage.started_at = stage.started_at or now
            stage.finished_at = now
            run.status = "complete"
            run.finished_at = now
            run.lease_owner = None
            run.lease_expires_at = None
            document.status = "complete"
            document.updated_at = now
            session.commit()
    except Exception as error:
        with Session(engine, expire_on_commit=False) as session:
            run = session.get(IngestionRun, run_id)
            if run is None:
                return
            document = session.get(Document, run.document_id)
            if document is None or document.deleted_at is not None:
                return
            now = utcnow()
            run.status = "failed"
            run.error = str(error)[:2000]
            run.finished_at = now
            run.lease_owner = None
            run.lease_expires_at = None
            document.status = "failed"
            document.updated_at = now
            active = session.scalar(
                select(IngestionStage).where(
                    IngestionStage.run_id == run.id,
                    IngestionStage.status == "processing",
                )
            )
            if active:
                active.status = "failed"
                active.error = "This stage failed. Retry the ingestion to continue."
                active.finished_at = now
            session.commit()


def run_worker(once: bool = False) -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("The ingestion worker requires PostgreSQL with pgvector.")
    owner = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        run_id = claim_run(owner)
        if run_id:
            process_run(run_id, owner)
        elif once:
            return
        else:
            time.sleep(2)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    run_worker(parser.parse_args().once)
