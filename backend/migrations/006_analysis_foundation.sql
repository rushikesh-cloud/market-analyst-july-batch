CREATE TABLE IF NOT EXISTS analysis_runs (
    id varchar(36) PRIMARY KEY,
    company_id varchar(36) NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
    company_snapshot jsonb NOT NULL,
    agent_type varchar(20) NOT NULL CHECK (agent_type IN ('fundamental','technical','news')),
    status varchar(30) NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','completed','insufficient_data','failed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz, finished_at timestamptz, as_of timestamptz, deadline_at timestamptz,
    attempt integer NOT NULL DEFAULT 0 CHECK (attempt >= 0),
    lease_owner varchar(200),
    lease_generation integer NOT NULL DEFAULT 0 CHECK (lease_generation >= 0),
    lease_expires_at timestamptz,
    progress jsonb NOT NULL DEFAULT '{}', error jsonb, result jsonb,
    schema_version varchar(50) NOT NULL DEFAULT '1.0',
    prompt_version varchar(200) NOT NULL, scoring_version varchar(200) NOT NULL,
    model_version varchar(200), model_configuration jsonb NOT NULL,
    usage jsonb NOT NULL DEFAULT '{}',
    model_calls integer NOT NULL DEFAULT 0 CHECK (model_calls >= 0),
    tool_calls integer NOT NULL DEFAULT 0 CHECK (tool_calls >= 0)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_analysis_active_company_agent
    ON analysis_runs(company_id, agent_type) WHERE status IN ('queued','running');
CREATE INDEX IF NOT EXISTS ix_analysis_history ON analysis_runs(company_id, created_at, id);
CREATE INDEX IF NOT EXISTS ix_analysis_runs_status ON analysis_runs(status);

-- Snapshot payloads contain source IDs as data, never cascading source FKs.
CREATE TABLE IF NOT EXISTS analysis_evidence (
    run_id varchar(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE RESTRICT,
    id varchar(200) NOT NULL,
    fingerprint varchar(64) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(run_id, id), UNIQUE(run_id, fingerprint)
);
CREATE TABLE IF NOT EXISTS analysis_artifacts (
    id varchar(36) PRIMARY KEY,
    run_id varchar(36) NOT NULL REFERENCES analysis_runs(id) ON DELETE RESTRICT,
    relative_path varchar(1000) NOT NULL,
    mime_type varchar(200) NOT NULL,
    byte_size integer NOT NULL CHECK (byte_size >= 0),
    sha256 varchar(64) NOT NULL,
    purpose varchar(200) NOT NULL,
    lease_generation integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(run_id, relative_path)
);
CREATE INDEX IF NOT EXISTS ix_analysis_artifacts_run_id ON analysis_artifacts(run_id);
