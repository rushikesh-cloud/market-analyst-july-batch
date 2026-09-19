"""Company registry with PostgreSQL support and a local SQLite default."""

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from app.nse_tickers import normalize_nse_ticker


class Base(DeclarativeBase):
    pass


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    ticker: Mapped[str] = mapped_column(String(40), unique=True)


def make_engine():
    url = os.environ.get("DATABASE_URL")
    if not url and os.environ.get("USE_AZURE_DATABASE", "").lower() == "true":
        from app.resources import get_resource_clients

        return get_resource_clients().database_engine()
    if not url:
        data_directory = Path(__file__).resolve().parent.parent / "data"
        data_directory.mkdir(exist_ok=True)
        url = f"sqlite:///{data_directory / 'market-analyst.db'}"
    if url.startswith(("postgres://", "postgresql://")):
        url = "postgresql+psycopg://" + url.split("://", 1)[1]
    return create_engine(url, pool_pre_ping=True)


engine = make_engine()
router = APIRouter(prefix="/api/companies", tags=["companies"])


class CompanyInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    ticker: str

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("ticker", mode="before")
    @classmethod
    def normalize_ticker(cls, value):
        return normalize_nse_ticker(value)


class CompanyOutput(BaseModel):
    """Legacy symbols remain readable until the user explicitly corrects them."""
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    ticker: str


def check_ticker_collision(session: Session, ticker: str, company_id: str):
    # Include canonicalizable historical bare symbols; never rewrite records.
    for existing in session.scalars(select(Company).where(Company.id != company_id)):
        try:
            canonical = normalize_nse_ticker(existing.ticker)
        except ValueError:
            continue
        if canonical == ticker:
            raise HTTPException(409, "This ticker is already configured.")


@router.get("", response_model=list[CompanyOutput])
def list_companies():
    with Session(engine) as session:
        return session.scalars(select(Company).order_by(Company.name, Company.id)).all()


def save(session: Session, company: Company):
    try:
        session.commit()
    except IntegrityError as error:
        session.rollback()
        raise HTTPException(409, "This ticker is already configured.") from error
    session.refresh(company)
    return company


@router.post("", response_model=CompanyOutput, status_code=201)
def create_company(payload: CompanyInput):
    with Session(engine) as session:
        company = Company(id=str(uuid4()), **payload.model_dump())
        check_ticker_collision(session, company.ticker, company.id)
        session.add(company)
        return save(session, company)


@router.put("/{company_id}", response_model=CompanyOutput)
def update_company(company_id: str, payload: CompanyInput):
    with Session(engine) as session:
        company = session.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Company not found.")
        check_ticker_collision(session, payload.ticker, company_id)
        company.name, company.ticker = payload.name, payload.ticker
        return save(session, company)


@router.delete("/{company_id}", status_code=204)
def delete_company(company_id: str):
    with Session(engine) as session:
        company = session.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Company not found.")
        from app.documents import Document

        if session.scalar(select(Document.id).where(Document.company_id == company_id)):
            raise HTTPException(
                409, "Delete this company's documents before deleting the company."
            )
        if engine.dialect.name == "postgresql":
            from app.analysis.models import AnalysisRun

            if session.scalar(select(AnalysisRun.id).where(
                AnalysisRun.company_id == company_id
            ).limit(1)):
                raise HTTPException(409, "Analysis history must be retained. This company cannot be deleted.")
        session.delete(company)
        try:
            session.commit()
        except IntegrityError as error:
            session.rollback()
            raise HTTPException(409, "This company has retained records and cannot be deleted.") from error
        return Response(status_code=204)
