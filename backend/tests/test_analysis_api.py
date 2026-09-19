"""C07 HTTP contracts against PostgreSQL with adapters injected only in tests."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import tempfile
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import companies, main
from app.auth import AuthenticatedUser, require_workspace_access
from app.analysis import api
from app.analysis.artifact_store import ArtifactStore
from app.analysis.contracts import AgentType, CompanySnapshot, ModelConfiguration, AnalysisError, ErrorCode
from app.analysis.fixtures import result_fixture
from app.analysis.models import AnalysisRun, utcnow
from app.analysis.registry import AgentRegistry
from app.analysis.repository import enqueue_run
from tests.analysis_postgres_support import isolated_postgres

MODEL = ModelConfiguration(deployment='synthetic', api_version='synthetic')


class AnalysisApiUnitTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(main.app)
        self.addCleanup(self.client.close)
        override = patch.dict(main.app.dependency_overrides, {
            require_workspace_access: lambda: AuthenticatedUser('test','test'),
        })
        override.start(); self.addCleanup(override.stop)

    def test_C07_03_invalid_payload_pagination_and_sqlite(self):
        engine = create_engine('sqlite://')
        self.addCleanup(engine.dispose)
        with patch.object(api, 'engine', engine):
            for payload in ({}, {'agent_type':'other'}, {'agent_type':'technical','company_id':'injected'}):
                self.assertEqual(self.client.post('/api/companies/x/analysis-runs',json=payload).status_code,422)
            for query in ('limit=0','limit=101','offset=-1','agent_type=other','limit=abc'):
                self.assertEqual(self.client.get('/api/companies/x/analysis-runs?'+query).status_code,422)
            for path in ('/api/companies/x/analysis-runs','/api/analysis-runs/x','/api/analysis-runs/x/artifacts/x'):
                response=self.client.get(path)
                self.assertEqual(response.status_code,503,response.text)
                self.assertEqual(response.json()['detail']['code'],'postgresql_required')
            self.assertEqual(self.client.post('/api/companies/x/analysis-runs',json={'agent_type':'news'}).status_code,503)
            self.assertFalse(any(x['available'] for x in self.client.get('/api/analysis-agents').json()['items']))

    def test_safe_database_and_configuration_failures(self):
        with patch.object(api,'get_run',side_effect=SQLAlchemyError('SENTINEL_SECRET_URL')):
            response=self.client.get('/api/analysis-runs/x')
            self.assertEqual(response.status_code,503)
            self.assertNotIn('SENTINEL',response.text)
        with patch('app.resources.get_resource_clients',side_effect=RuntimeError('SENTINEL')):
            with self.assertRaises(AnalysisError) as error:
                api.resolve_configuration(AgentType.TECHNICAL)
            self.assertEqual(error.exception.code,ErrorCode.CONFIGURATION_ERROR)
        clients=Mock()
        clients.analysis_model_configuration.return_value=MODEL
        with patch('app.resources.get_resource_clients',return_value=clients):
            self.assertEqual(api.resolve_configuration(AgentType.NEWS),MODEL)
            clients.settings.analysis.require_tavily_secret.assert_called_once()
        clients.settings.analysis.require_tavily_secret.side_effect=AnalysisError(ErrorCode.CONFIGURATION_ERROR)
        with patch('app.resources.get_resource_clients',return_value=clients),self.assertRaises(AnalysisError):
            api.resolve_configuration(AgentType.NEWS)

    def test_production_registry_is_unavailable_without_provider_calls(self):
        from app.analysis.registry import registry
        self.assertEqual(registry.available(),())
        with patch.object(api,'require_postgres'),patch.object(api,'resolve_configuration') as config:
            result=self.client.get('/api/analysis-agents').json()
        self.assertEqual([x['error']['code'] for x in result['items']],['agent_unavailable']*3)
        config.assert_not_called()


class AnalysisApiPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context=isolated_postgres()
        cls.engine=cls.context.__enter__()
        cls.addClassCleanup(cls.context.__exit__,None,None,None)

    def setUp(self):
        self.client=TestClient(main.app); self.addCleanup(self.client.close)
        self.registry=AgentRegistry(); self.adapter=Mock()
        for agent in AgentType: self.registry.register(agent,self.adapter)
        self.company=CompanySnapshot(id=str(uuid4()),name='Synthetic company',ticker='S'+uuid4().hex[:10].upper()+'.NS')
        with Session(self.engine) as session:
            session.add(companies.Company(**self.company.model_dump()));session.commit()
        for item in (
            patch.object(api,'engine',self.engine),patch.object(companies,'engine',self.engine),
            patch.object(api,'registry',self.registry),patch.object(api,'resolve_configuration',return_value=MODEL),
            patch.dict(main.app.dependency_overrides,{require_workspace_access:lambda:AuthenticatedUser('test','test','admin')}),
        ):
            item.start();self.addCleanup(item.stop)
        self.path=f'/api/companies/{self.company.id}/analysis-runs'

    def start(self,agent='technical'):
        response=self.client.post(self.path,json={'agent_type':agent})
        self.assertEqual(response.status_code,202,response.text)
        return response.json()

    def test_C07_01_02_durable_submission_race_and_rerun(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            runs=list(pool.map(lambda _:self.start(),range(2)))
        self.assertEqual(runs[0]['id'],runs[1]['id'])
        self.assertEqual(runs[0]['status'],'queued')
        self.adapter.run.assert_not_called()
        with patch.object(api, 'registry', AgentRegistry()), patch.object(api, 'resolve_configuration') as configuration:
            self.assertEqual(self.start()['id'], runs[0]['id'])
            configuration.assert_not_called()
        with Session(self.engine) as session:
            row=session.get(AnalysisRun,runs[0]['id']);row.status='failed';row.finished_at=utcnow();session.commit()
        self.assertNotEqual(self.start()['id'],runs[0]['id'])
        # Both the history guard and FK protect retained runs.
        self.assertEqual(self.client.delete('/api/companies/'+self.company.id).status_code,409)

    def test_C07_03_missing_ids_legacy_uninstalled_and_unconfigured(self):
        for path in ('/api/companies/missing/analysis-runs','/api/analysis-runs/missing'):
            self.assertEqual(self.client.get(path).status_code,404)
        self.assertEqual(self.client.post('/api/companies/missing/analysis-runs',json={'agent_type':'news'}).status_code,404)
        with Session(self.engine) as session:
            session.get(companies.Company,self.company.id).ticker='LEGACY';session.commit()
        response=self.client.post(self.path,json={'agent_type':'technical'})
        self.assertEqual(response.status_code,409)
        self.assertEqual(response.json()['detail']['code'],'ticker_correction_required')
        with Session(self.engine) as session:
            session.get(companies.Company,self.company.id).ticker=self.company.ticker;session.commit()
        with patch.object(api,'registry',AgentRegistry()):
            self.assertEqual(self.client.post(self.path,json={'agent_type':'technical'}).status_code,503)
        with patch.object(api,'resolve_configuration',side_effect=AnalysisError(ErrorCode.CONFIGURATION_ERROR)):
            self.assertEqual(self.client.post(self.path,json={'agent_type':'technical'}).status_code,503)
        capabilities=self.client.get('/api/analysis-agents').json()['items']
        self.assertTrue(all(x['available'] for x in capabilities))

    def test_C07_04_history_stable_order_filter_and_company_scope(self):
        tied=utcnow();ids=[]
        for agent in ['technical','news','technical','fundamental','technical']:
            run=self.start(agent);ids.append(run['id'])
            with Session(self.engine) as session:
                row=session.get(AnalysisRun,run['id']);row.status='failed';row.created_at=tied;session.commit()
        first=self.client.get(self.path+'?limit=2').json()
        second=self.client.get(self.path+'?limit=3&offset=2').json()
        self.assertEqual([x['id'] for x in first['items']+second['items']],sorted(ids,reverse=True))
        technical=self.client.get(self.path+'?agent_type=technical').json()['items']
        self.assertEqual(len(technical),3)
        self.assertTrue(all(x['company_id']==self.company.id for x in technical))

    def test_C07_05_all_lifecycle_results_and_safe_progress(self):
        for status in ['queued','running','completed','insufficient_data','failed']:
            run=self.start('fundamental');now=utcnow()
            with Session(self.engine) as session:
                row=session.get(AnalysisRun,run['id']);row.status=status
                row.progress={'stage': ['SENTINEL_SECRET_URL'], 'raw_prompt':'SENTINEL_SECRET_URL'}
                if status in ['completed','insufficient_data']:
                    row.as_of=now;row.result=result_fixture('fundamental',status,run_id=row.id,company=self.company,as_of=now).model_dump(mode='json')
                if status=='failed':row.error=AnalysisError(ErrorCode.PROVIDER_UNAVAILABLE).as_safe_error().model_dump(mode='json')
                session.commit()
            response=self.client.get('/api/analysis-runs/'+run['id'])
            self.assertEqual(response.status_code,200,response.text)
            self.assertEqual(response.json()['status'],status)
            self.assertNotIn('SENTINEL',response.text)
            if status=='insufficient_data':self.assertIsNone(response.json()['result']['final_score'])
            if status in ['queued','running']:
                with Session(self.engine) as session:
                    session.get(AnalysisRun,run['id']).status='failed';session.commit()

    def test_C07_06_registered_artifact_bytes_and_safe_404(self):
        run=self.start();now=utcnow()
        with Session(self.engine) as session:
            row=session.get(AnalysisRun,run['id']);row.status='running';row.as_of=now
            row.lease_owner='owner';row.lease_generation=1;row.lease_expires_at=now+timedelta(seconds=60)
            row.deadline_at=now+timedelta(minutes=5);session.commit()
        with tempfile.TemporaryDirectory() as root,patch.dict('os.environ',{'ANALYSIS_ARTIFACT_DIR':root}):
            metadata=ArtifactStore(self.engine,run['id'],'owner',1).write(b'PNG fixture',mime_type='image/png',purpose='test')
            path=f"/api/analysis-runs/{run['id']}/artifacts/{metadata.id}"
            response=self.client.get(path)
            self.assertEqual(response.content,b'PNG fixture');self.assertEqual(response.headers['content-type'],'image/png')
            self.assertEqual(response.headers['x-content-type-options'],'nosniff')
            self.assertNotIn(root,response.text)
            for missing in (str(uuid4()),'%2e%2e%2f', 'unknown'):
                missing_response = self.client.get(f"/api/analysis-runs/{run['id']}/artifacts/{missing}")
                self.assertEqual(missing_response.status_code,404, f"{missing}: {missing_response.text[:100]}")
            other=self.start('news')
            self.assertEqual(self.client.get(f"/api/analysis-runs/{other['id']}/artifacts/{metadata.id}").status_code,404)
