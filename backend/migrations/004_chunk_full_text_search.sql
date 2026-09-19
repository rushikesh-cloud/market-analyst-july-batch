-- Expression index covers existing chunks and stays current during ingestion.
CREATE INDEX IF NOT EXISTS ix_document_chunks_full_text
ON document_chunks USING gin (
    to_tsvector('english', content || ' ' || heading_path::text)
);
