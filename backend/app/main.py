from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.companies import Base, engine, router
from app.documents import router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    if engine.dialect.name == "postgresql":
        from app.migrate import migrate

        migrate()
    else:
        Base.metadata.create_all(engine)
    yield
    engine.dispose()


app = FastAPI(title="Market Analyst API", version="0.1.0", lifespan=lifespan)
app.include_router(router)
app.include_router(documents_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", tags=["health"])
async def health_check() -> dict[str, str]:
    """Return the service liveness state."""
    return {"status": "healthy"}


static_directory = Path(__file__).parent.parent / "static"
if static_directory.is_dir():
    app.mount("/", StaticFiles(directory=static_directory, html=True), name="frontend")
