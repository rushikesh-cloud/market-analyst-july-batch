from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.companies import Base, engine, router
from app.documents import router as documents_router
from app.document_search import router as document_search_router
from app.auth import AuthenticatedUser, authorized_parties, require_admin, require_workspace_access
from app.analysis.api import router as analysis_router


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
protected = APIRouter(dependencies=[Depends(require_workspace_access)])
protected.include_router(router, dependencies=[Depends(require_admin)])
protected.include_router(documents_router, dependencies=[Depends(require_admin)])
protected.include_router(document_search_router, dependencies=[Depends(require_admin)])
protected.include_router(analysis_router)


@protected.get('/api/auth/me', tags=['auth'])
def current_user(user: AuthenticatedUser = Depends(require_workspace_access)) -> dict[str, str]:
    return {'user_id': user.user_id, 'role': user.role}


app.include_router(protected)

app.add_middleware(
    CORSMiddleware,
    allow_origins=authorized_parties(),
    allow_credentials=False,
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
