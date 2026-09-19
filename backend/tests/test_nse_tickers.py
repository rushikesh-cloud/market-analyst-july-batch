"""C04 canonical input and legacy records through real company API validation."""

import unittest
from sqlalchemy.orm import Session
from app import companies
from app.nse_tickers import is_canonical_nse_ticker, normalize_nse_ticker
from tests import test_companies


class NseTickerTests(unittest.TestCase):
    def test_c04_01_canonical_and_idempotent(self):
        for value, expected in [(' reliance ', 'RELIANCE.NS'), ('reliance.ns', 'RELIANCE.NS'),
                                ('M&M', 'M&M.NS'), ('BAJAJ-AUTO.NS', 'BAJAJ-AUTO.NS')]:
            self.assertEqual(normalize_nse_ticker(value), expected)
            self.assertEqual(normalize_nse_ticker(expected), expected)
            self.assertTrue(is_canonical_nse_ticker(expected))
        self.assertFalse(is_canonical_nse_ticker('RELIANCE'))
        self.assertFalse(is_canonical_nse_ticker('RELIANCE.BO'))

    def test_c04_02_invalid_symbols_and_canonical_length(self):
        for value in ['RELIANCE.BO', '7203.T', '^NSEI', 'EURUSD=X', '.NS', 'ABC.NS.NS',
                      'ABC DEF', 'A' * 38, 'ABC-', '&ABC', '', None, 123, 'ＡＢＣ']:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_nse_ticker(value)
        self.assertEqual(len(normalize_nse_ticker('A' * 37)), 40)


class NseCompanyApiTests(unittest.TestCase):
    setUp = test_companies.CompanyTests.setUp
    tearDown = test_companies.CompanyTests.tearDown
    add = test_companies.CompanyTests.add

    def seed(self, identifier, ticker):
        with Session(self.engine) as session:
            session.add(companies.Company(id=identifier, name=identifier, ticker=ticker))
            session.commit()

    def test_c04_01_api_normalizes_create_and_update(self):
        record = self.add('Example', ' m&m ').json()
        self.assertEqual(record['ticker'], 'M&M.NS')
        saved = self.client.put('/api/companies/'+record['id'], json={
            'name': 'Example', 'ticker': ' bajaj-auto.ns ',
        })
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['ticker'], 'BAJAJ-AUTO.NS')

    def test_c04_02_api_rejects_invalid_without_changes(self):
        record = self.add().json()
        for ticker in ['RELIANCE.BO', '7203.T', '^NSEI', 'EURUSD=X', '.NS', 'ABC.NS.NS',
                       'ABC DEF', 'A' * 38]:
            self.assertEqual(self.add(ticker=ticker).status_code, 422)
            self.assertEqual(self.client.put('/api/companies/'+record['id'], json={
                'name': 'Changed', 'ticker': ticker,
            }).status_code, 422)
        self.assertEqual(self.client.get('/api/companies').json(), [record])

    def test_c04_03_legacy_collision_preserves_records(self):
        self.seed('legacy', 'RELIANCE')
        other = self.add('Other', 'OTHER').json()
        original = self.client.get('/api/companies').json()
        self.assertEqual(self.add('Duplicate', ' reliance.ns ').status_code, 409)
        self.assertEqual(self.client.put('/api/companies/'+other['id'], json={
            'name': 'Duplicate', 'ticker': 'reliance',
        }).status_code, 409)
        self.assertEqual(self.client.get('/api/companies').json(), original)

    def test_c04_04_legacy_readable_and_explicit_save(self):
        for identifier, ticker in [('bare', 'RELIANCE'), ('global', '7203.T'), ('index', '^NSEI')]:
            self.seed(identifier, ticker)
        original = self.client.get('/api/companies').json()
        self.assertEqual({x['ticker'] for x in original}, {'RELIANCE', '7203.T', '^NSEI'})
        saved = self.client.put('/api/companies/bare', json={'name': 'bare', 'ticker': 'RELIANCE'})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()['ticker'], 'RELIANCE.NS')
        self.assertEqual(self.client.put('/api/companies/global', json={
            'name': 'corrected', 'ticker': 'CORRECTED',
        }).status_code, 200)

    def test_c04_05_two_legacy_spellings_remain_distinct(self):
        self.seed('first', 'RELIANCE')
        self.seed('second', 'reliance')
        self.seed('incompatible', '^NSEI')
        before = self.client.get('/api/companies').json()
        response = self.client.put('/api/companies/first', json={
            'name': 'changed', 'ticker': 'RELIANCE.NS',
        })
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get('/api/companies').json(), before)
