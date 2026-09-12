# Market Analyst

## Local development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and Node.js, then install both projects' dependencies once:

```bash
npm run install:all
```

Then start the React client and FastAPI server together:

```bash
npm run dev
```

The client is available at http://localhost:5173 and the API docs at http://localhost:8000/docs. The FastAPI dependencies are managed in `backend/pyproject.toml` and locked in `backend/uv.lock`.

## Docker

Build and run the production image:

```bash
docker build -t market-analyst .
docker run --rm -p 8000:8000 market-analyst
```

The image serves the React build and API from http://localhost:8000.

## Azure Container Instances

ACI deployment is intentionally deferred. After this project has a deployable container image,
create and deploy its Azure Container Instance as a separate activity.

## Companies and design

The Companies page supports adding, searching, editing, and deleting companies.
Company names and Yahoo Finance tickers are required; symbols are normalized to
uppercase and must be unique. Ticker format is checked locally, without calling
Yahoo Finance to verify that a symbol exists. Documents and Agentic Analysis are
planned destinations within the shared navigation.

Follow [design.md](design.md) for all UI work.

The API uses SQLAlchemy. Local development defaults to a persistent SQLite file at
`backend/data/market-analyst.db` (ignored by Git). Set `DATABASE_URL` in the server's
process environment to use PostgreSQL, for example:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/market_analyst'
npm run dev
```

The initial companies table is created at startup. Future schema changes require
versioned migrations. For Docker, supply `DATABASE_URL` for PostgreSQL or mount a
writable volume at `/app/data` to persist SQLite across container replacement.
The starter has no authentication; production access control is still pending.

Validation:

```bash
npm run build
uv --directory backend run python -m unittest discover -s tests -v
```
