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

The API uses SQLAlchemy through the shared Azure resource utilities. The configured
`.env` enables `USE_AZURE_DATABASE=true`: Companies uses
`get_resource_clients().database_engine()` to connect to PostgreSQL with the password
from Key Vault. Both `npm run dev` and `npm run dev:backend` load this configuration.
An explicit `DATABASE_URL` overrides Azure resource settings, for example:

```bash
export DATABASE_URL='postgresql+psycopg://user:password@localhost:5432/market_analyst'
npm run dev
```

The initial companies table is created at startup. Future schema changes require
versioned migrations. If neither `DATABASE_URL` nor Azure database mode is configured,
the local fallback is `backend/data/market-analyst.db` (SQLite, ignored by Git).
Azure connection failures never fall back to SQLite. For Docker, supply the Azure
resource environment configuration and managed identity, or `DATABASE_URL`.
The starter has no authentication; production access control is still pending.

## Azure resource utilities

The server uses `app.resources.get_resource_clients()` as the single access layer for
Azure OpenAI, Document Intelligence, and PostgreSQL. It resolves API keys and the
database password from Key Vault with `DefaultAzureCredential`; no application source
or environment file stores those values.

For local development, sign in with `az login` and run `npm run dev`. The command loads
the ignored `.env`, then `DefaultAzureCredential` uses the Azure CLI identity to read
the Key Vault secrets. A deployed workload must use a managed identity with Key Vault
secret `get` permission.

```python
from app.resources import get_resource_clients

resources = get_resource_clients()
luna = resources.openai()
document_intelligence = resources.document_intelligence()
database_engine = resources.database_engine()
```

Validation:

```bash
npm run build
uv --directory backend run python -m unittest discover -s tests -v
```
