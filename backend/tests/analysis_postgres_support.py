"""Opt-in PostgreSQL tests with independent transactions in a disposable schema.

Run with ANALYSIS_TEST_POSTGRES=1 and the normal application database settings.
Only the randomly generated schema is created or removed. Existing public data
is never loaded into tests; public remains on the path for the vector type.
"""

from contextlib import contextmanager
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, text


@contextmanager
def isolated_postgres(*, migrate: bool = True):
    if os.environ.get("ANALYSIS_TEST_POSTGRES") != "1":
        raise unittest.SkipTest("Set ANALYSIS_TEST_POSTGRES=1 for isolated PostgreSQL tests.")

    from app.companies import engine as configured_engine

    if configured_engine.dialect.name != "postgresql":
        raise RuntimeError("ANALYSIS_TEST_POSTGRES requires a configured PostgreSQL database.")

    schema = f"analysis_test_{uuid4().hex}"
    with configured_engine.begin() as connection:
        if not connection.execute(text("SELECT 1 FROM pg_extension WHERE extname='vector'")).scalar():
            raise RuntimeError("Isolated PostgreSQL tests require the existing vector extension.")
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        # Qualify the ledger before the migrator can resolve a public ledger.
        connection.execute(text(
            f'CREATE TABLE "{schema}".schema_migrations '
            '(version varchar(255) PRIMARY KEY, '
            'applied_at timestamptz NOT NULL DEFAULT now())'
        ))
    test_engine = create_engine(
        configured_engine.url,
        pool_pre_ping=True,
        connect_args={"options": f"-csearch_path={schema},public -clock_timeout=5000"},
    )
    try:
        if migrate:
            from app import migrate as migration_module
            from unittest.mock import patch

            with patch.object(migration_module, "engine", test_engine):
                migration_module.migrate()
            with test_engine.connect() as connection:
                for table in ("schema_migrations", "companies", "documents", "document_chunks"):
                    namespace = connection.execute(text(
                        "SELECT n.nspname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                        "WHERE c.oid=to_regclass(:name)"
                    ), {"name": table}).scalar_one()
                    if namespace != schema:
                        raise RuntimeError("Test database relation escaped its isolated schema.")
        yield test_engine
    finally:
        test_engine.dispose()
        with configured_engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
