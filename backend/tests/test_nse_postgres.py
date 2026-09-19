"""C04 canonical collisions use real independent PostgreSQL transactions."""

import os
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app import companies, documents
from tests.analysis_postgres_support import isolated_postgres


@unittest.skipUnless(os.environ.get('ANALYSIS_TEST_POSTGRES') == '1', 'Requires isolated PostgreSQL')
class NsePostgresTests(unittest.TestCase):
    def test_c04_03_concurrent_canonical_and_legacy_conflicts_preserve_documents(self):
        with isolated_postgres() as engine, patch.object(companies, 'engine', engine):
            with Session(engine) as session:
                session.add(companies.Company(id='legacy', name='Original', ticker='RELIANCE'))
                session.flush()
                session.add(documents.Document(id='report', company_id='legacy', fiscal_year=2025,
                    filename='report.pdf', storage_path='not-read.pdf', status='complete'))
                session.commit()
            with self.assertRaises(HTTPException) as error:
                companies.create_company(companies.CompanyInput(name='Duplicate', ticker='reliance.ns'))
            self.assertEqual(error.exception.status_code, 409)
            def create(ticker):
                try:
                    return companies.create_company(companies.CompanyInput(name='Concurrent', ticker=ticker)).ticker
                except HTTPException as exc:
                    return exc.status_code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results=list(pool.map(create,[' m&m ', 'M&M.NS']))
            self.assertCountEqual(results,['M&M.NS',409])
            with Session(engine) as session:
                legacy=session.get(companies.Company,'legacy')
                self.assertEqual((legacy.name,legacy.ticker),('Original','RELIANCE'))
                self.assertEqual(session.get(documents.Document,'report').company_id,'legacy')
                self.assertEqual(len(list(session.scalars(select(companies.Company)))),2)
