"""Regression checks for public exposure, identity, and durable storage."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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

    def test_cli_writes_private_secret_file_and_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'aci.json'
            env = {**os.environ, **self.env, 'ACI_SPEC_PATH': str(path)}
            command = [sys.executable, str(Path(__file__).with_name('render_aci.py'))]
            subprocess.run(command, env=env, check=True, capture_output=True)
            self.assertEqual(json.loads(path.read_text()), self.spec)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            second = subprocess.run(command, env=env, capture_output=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(json.loads(path.read_text()), self.spec)

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
