CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
  id varchar(36) PRIMARY KEY,
  company_id varchar(36) NOT NULL REFERENCES companies(id),
  fiscal_year integer NOT NULL CHECK (fiscal_year >= 1900),
  filename varchar(255) NOT NULL,
  storage_path varchar(500) NOT NULL,
  status varchar(30) NOT NULL DEFAULT 'queued',
  markdown text,
  embedding_deployment varchar(200),
  embedding_dimensions integer,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  deleted_at timestamptz,
  UNIQUE (company_id, fiscal_year)
);
CREATE INDEX IF NOT EXISTS ix_documents_company_id ON documents(company_id);
CREATE INDEX IF NOT EXISTS ix_documents_status ON documents(status);

CREATE TABLE IF NOT EXISTS ingestion_runs (
  id varchar(36) PRIMARY KEY,
  document_id varchar(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  attempt integer NOT NULL,
  status varchar(30) NOT NULL DEFAULT 'queued',
  error text,
  lease_owner varchar(100),
  lease_expires_at timestamptz,
  created_at timestamptz NOT NULL,
  started_at timestamptz,
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_document_id ON ingestion_runs(document_id);
CREATE INDEX IF NOT EXISTS ix_ingestion_runs_status ON ingestion_runs(status);

CREATE TABLE IF NOT EXISTS ingestion_stages (
  id varchar(36) PRIMARY KEY,
  run_id varchar(36) NOT NULL REFERENCES ingestion_runs(id) ON DELETE CASCADE,
  name varchar(30) NOT NULL,
  position integer NOT NULL,
  status varchar(30) NOT NULL DEFAULT 'pending',
  completed_items integer,
  total_items integer,
  started_at timestamptz,
  finished_at timestamptz,
  error text,
  UNIQUE (run_id, name)
);
CREATE INDEX IF NOT EXISTS ix_ingestion_stages_run_id ON ingestion_stages(run_id);

CREATE TABLE IF NOT EXISTS document_chunks (
  id varchar(36) PRIMARY KEY,
  document_id varchar(36) NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  sequence integer NOT NULL,
  chunk_type varchar(20) NOT NULL,
  heading_path jsonb NOT NULL,
  content text NOT NULL,
  overlap_text text NOT NULL DEFAULT '',
  token_count integer NOT NULL,
  embedding vector(1536),
  UNIQUE (document_id, sequence)
);
CREATE INDEX IF NOT EXISTS ix_document_chunks_document_id ON document_chunks(document_id);
