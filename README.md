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
