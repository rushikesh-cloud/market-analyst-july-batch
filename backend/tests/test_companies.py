import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app import companies
from app.main import app


class CompanyTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = create_engine(f"sqlite:///{Path(self.directory.name) / 'test.db'}")
        companies.Base.metadata.create_all(self.engine)
        self.override = patch.object(companies, "engine", self.engine)
        self.override.start()
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.override.stop()
        self.engine.dispose()
        self.directory.cleanup()

    def add(self, name='Microsoft', ticker='MSFT'):
        return self.client.post('/api/companies', json={'name': name, 'ticker': ticker})

    def test_crud_and_persistence(self):
        response = self.add(' Microsoft ', ' msft ')
        self.assertEqual(response.status_code, 201)
        company = response.json()
        self.assertEqual(company['name'], 'Microsoft')
        self.assertEqual(company['ticker'], 'MSFT')
        self.engine.dispose()  # Force new database connections, preserving records.
        self.assertEqual(self.client.get('/api/companies').json(), [company])
        path = f"/api/companies/{company['id']}"
        response = self.client.put(path, json={'name': 'Reliance', 'ticker': 'reliance.ns'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['ticker'], 'RELIANCE.NS')
        self.assertEqual(self.client.delete(path).status_code, 204)
        self.assertEqual(self.client.get('/api/companies').json(), [])
        self.assertEqual(self.client.delete(path).status_code, 404)
        self.assertEqual(self.client.put(path, json={'name': 'Missing', 'ticker': 'MISS'}).status_code, 404)

    def test_duplicate_create_and_update_are_atomic(self):
        self.add()
        self.assertEqual(self.add(ticker=' msft ').status_code, 409)
        second = self.add('Apple', 'AAPL').json()
        self.assertEqual(self.client.put(f"/api/companies/{second['id']}", json={'name': 'Changed', 'ticker': 'MSFT'}).status_code, 409)
        self.assertIn(second, self.client.get('/api/companies').json())

    def test_validation(self):
        for name, ticker in [(' ', 'MSFT'), ('A' * 201, 'A'), ('Name', ''), ('Name', 'bad ticker'), ('Name', '<script>'), ('Name', 'A' * 41)]:
            with self.subTest(name=name, ticker=ticker):
                self.assertEqual(self.add(name, ticker).status_code, 422)
        for ticker in ['BRK-B', '^GSPC', 'EURUSD=X', '7203.T']:
            with self.subTest(ticker=ticker):
                self.assertEqual(self.add(ticker, ticker).status_code, 201)
