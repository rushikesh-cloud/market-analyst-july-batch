ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS page_number integer NOT NULL DEFAULT 1;
CREATE INDEX IF NOT EXISTS ix_document_chunks_page_number ON document_chunks(page_number);
