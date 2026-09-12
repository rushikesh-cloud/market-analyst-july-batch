"""Company registry with PostgreSQL support and a local SQLite default."""

import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import String, create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column


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
    name: str = Field(min_length=1, max_length=200)
    ticker: str = Field(min_length=1, max_length=40, pattern=r"^[A-Z0-9^][A-Z0-9.\-^=]*$")

    @field_validator("name", "ticker", mode="before")
    @classmethod
    def normalize(cls, value, info):
        if isinstance(value, str):
            value = value.strip()
            return value.upper() if info.field_name == "ticker" else value
        return value


class CompanyOutput(CompanyInput):
    model_config = ConfigDict(from_attributes=True)
    id: str


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
        session.add(company)
        return save(session, company)


@router.put("/{company_id}", response_model=CompanyOutput)
def update_company(company_id: str, payload: CompanyInput):
    with Session(engine) as session:
        company = session.get(Company, company_id)
        if company is None:
            raise HTTPException(404, "Company not found.")
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
        session.delete(company)
        session.commit()
        return Response(status_code=204)
