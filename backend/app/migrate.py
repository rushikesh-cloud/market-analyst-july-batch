"""Apply ordered SQL migrations to the configured PostgreSQL database."""

import os
from pathlib import Path

from sqlalchemy import text

from app.companies import engine


def migrate() -> None:
    if engine.dialect.name != "postgresql":
        raise RuntimeError("Migrations require PostgreSQL.")
    directory = Path(__file__).resolve().parents[1] / "migrations"
    with engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(version varchar(255) PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        ))
        applied = set(connection.execute(text("SELECT version FROM schema_migrations")).scalars())
        for path in sorted(directory.glob("*.sql")):
            if path.name in applied:
                continue
            raw = connection.connection.driver_connection
            dimensions = int(os.environ.get("RAG_VECTOR_DIMENSIONS", "1536"))
            sql = path.read_text().replace("vector(1536)", f"vector({dimensions})")
            raw.execute(sql)
            connection.execute(
                text("INSERT INTO schema_migrations(version) VALUES (:version)"),
                {"version": path.name},
            )


if __name__ == "__main__":
    migrate()
