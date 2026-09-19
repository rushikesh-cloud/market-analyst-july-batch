"""Regression checks for public exposure, identity, and durable storage."""
import json
import unittest

from render_aci import render


class DeploymentSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            'AZURE_DNS_LABEL': 'example', 'AZURE_LOCATION': 'centralindia',
            'APP_ENV_JSON': json.dumps({'AZURE_CLIENT_ID': 'runtime-client',
                                        'CLERK_AUTHORIZED_PARTIES': 'http://localhost:5173'}),
            'DEPLOY_IMAGE': 'example.azurecr.io/app:commit',
            'AZURE_STORAGE_ACCOUNT': 'storage', 'AZURE_STORAGE_KEY': 'test-storage-key',
            'AZURE_CONTAINER_NAME': 'app', 'AZURE_RUNTIME_IDENTITY_ID': '/identity/runtime',
            'AZURE_ACR_SERVER': 'example.azurecr.io', 'GITHUB_SHA': 'commit',
        }
        self.spec = render(self.env)
        self.props = self.spec['properties']

    def test_only_https_proxy_is_public(self):
        self.assertEqual({item['port'] for item in self.props['ipAddress']['ports']}, {80, 443})
        proxy = self.props['containers'][2]['properties']
        self.assertIn('example.centralindia.azurecontainer.io', proxy['command'])
        for container in self.props['containers'][:2]:
            env = container['properties']['environmentVariables']
            self.assertTrue(all('secureValue' in item and 'value' not in item for item in env))
            origins = next(item['secureValue'] for item in env if item['name'] == 'CLERK_AUTHORIZED_PARTIES')
            self.assertEqual(origins, 'https://example.centralindia.azurecontainer.io')

    def test_registry_uses_runtime_identity_without_password(self):
        self.assertEqual(self.props['imageRegistryCredentials'], [{
            'server': 'example.azurecr.io', 'identity': '/identity/runtime'}])
        self.assertIn('/identity/runtime', self.spec['identity']['userAssignedIdentities'])

    def test_api_worker_share_durable_files_and_exact_image(self):
        web, worker = [item['properties'] for item in self.props['containers'][:2]]
        self.assertEqual(web['volumeMounts'], worker['volumeMounts'])
        self.assertEqual(web['image'], self.env['DEPLOY_IMAGE'])
        self.assertEqual(worker['image'], web['image'])
        self.assertIn('exec /app/.venv/bin/python -m app.worker', worker['command'][-1])
        self.assertEqual({item['name'] for item in self.props['volumes']},
                         {'documents', 'analysis-artifacts', 'caddy'})


if __name__ == '__main__':
    unittest.main()
