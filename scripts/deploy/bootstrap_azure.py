"""Provision deployment resources and configure GitHub without printing secrets.

Run from the deploy checkout with an authenticated Azure CLI and GitHub CLI.
The existing root .env supplies resource names, never raw provider credentials.
"""
import argparse
import json
import subprocess
from pathlib import Path


def run(*args, value=None):
    result = subprocess.run(args, input=value, text=True, capture_output=True)
    if result.returncode:
        # Azure errors can contain submitted settings: keep them out of logs.
        raise RuntimeError(f"Command failed: {' '.join(args[:3])} (exit {result.returncode})")
    return result.stdout.strip()


def az(*args):
    output = run('az', *args, '--only-show-errors', '-o', 'json')
    return json.loads(output) if output else None


def read_env(path):
    return dict(line.split('=', 1) for line in Path(path).read_text().splitlines()
                if '=' in line and not line.lstrip().startswith('#'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env-file', required=True)
    parser.add_argument('--frontend-env-file', required=True)
    parser.add_argument('--repo', default='rushikesh-cloud/market-analyst-july-batch')
    args = parser.parse_args()
    settings = read_env(args.env_file)
    account = az('account', 'show')
    group = 'market-analyst-july-batch-deploy'
    location = 'centralindia'
    registry = 'marketanalystjulydeploy'
    storage = 'marketanalystjulyfiles'
    identity_name = 'market-analyst-runtime'
    group_id = az('group', 'create', '-n', group, '-l', location)['id']
    print('Deployment resource group ready.', flush=True)
    acr = az('acr', 'create', '-g', group, '-n', registry, '--sku', 'Basic', '--admin-enabled', 'false')
    az('storage', 'account', 'create', '-g', group, '-n', storage, '-l', location,
       '--sku', 'Standard_LRS', '--kind', 'StorageV2', '--min-tls-version', 'TLS1_2',
       '--allow-blob-public-access', 'false')
    for share in ('documents', 'analysis-artifacts', 'caddy'):
        az('storage', 'share-rm', 'create', '-g', group, '--storage-account', storage,
           '-n', share, '--quota', '20')
    identity = az('identity', 'create', '-g', group, '-n', identity_name)
    az('role', 'assignment', 'create', '--assignee-object-id', identity['principalId'],
       '--assignee-principal-type', 'ServicePrincipal', '--role', 'AcrPull', '--scope', acr['id'])
    vault = settings['AZURE_KEY_VAULT_URI'].split('//')[1].split('.')[0]
    az('keyvault', 'set-policy', '-n', vault, '--object-id', identity['principalId'], '--secret-permissions', 'get')
    server = settings['POSTGRES_HOST'].split('.')[0]
    az('postgres', 'flexible-server', 'firewall-rule', 'create', '-g', settings['AZURE_RESOURCE_GROUP'],
       '-n', server, '--rule-name', 'AllowAzureServicesForACI', '--start-ip-address', '0.0.0.0', '--end-ip-address', '0.0.0.0')
    print('Registry, storage, runtime identity, and database access ready.', flush=True)
    apps = az('ad', 'app', 'list', '--display-name', 'market-analyst-july-github-deploy')
    app = apps[0] if apps else az('ad', 'app', 'create', '--display-name', 'market-analyst-july-github-deploy')
    principals = az('ad', 'sp', 'list', '--filter', f"appId eq '{app['appId']}'")
    principal = principals[0] if principals else az('ad', 'sp', 'create', '--id', app['appId'])
    credentials = az('ad', 'app', 'federated-credential', 'list', '--id', app['id'])
    if not any(item['name'] == 'github-deploy-branch' for item in credentials):
        az('ad', 'app', 'federated-credential', 'create', '--id', app['id'], '--parameters', json.dumps({
            'name': 'github-deploy-branch', 'issuer': 'https://token.actions.githubusercontent.com',
            'subject': f'repo:{args.repo}:ref:refs/heads/deploy', 'audiences': ['api://AzureADTokenExchange']}))
    az('role', 'assignment', 'create', '--assignee-object-id', principal['id'],
       '--assignee-principal-type', 'ServicePrincipal', '--role', 'Contributor', '--scope', group_id)
    variables = {
        'AZURE_RESOURCE_GROUP': group, 'AZURE_LOCATION': location, 'AZURE_ACR_NAME': registry,
        'AZURE_ACR_SERVER': acr['loginServer'], 'AZURE_CONTAINER_NAME': 'market-analyst-july',
        'AZURE_DNS_LABEL': 'market-analyst-july', 'AZURE_STORAGE_ACCOUNT': storage,
        'AZURE_RUNTIME_IDENTITY_ID': identity['id'],
    }
    settings.update(AZURE_CLIENT_ID=identity['clientId'], MARKET_ANALYST_WORKSPACE_ROOT='/app',
                    ANALYSIS_ARTIFACT_DIR='/app/analysis-artifacts')
    # The actual DNS name is resolved by the deployment script (ACI can add a hash).
    secrets = {
        'AZURE_CLIENT_ID': app['appId'], 'AZURE_TENANT_ID': account['tenantId'],
        'AZURE_SUBSCRIPTION_ID': account['id'], 'APP_ENV_JSON': json.dumps(settings),
        'VITE_CLERK_PUBLISHABLE_KEY': read_env(args.frontend_env_file)['VITE_CLERK_PUBLISHABLE_KEY'],
        'AZURE_STORAGE_KEY': az('storage', 'account', 'keys', 'list', '-g', group, '-n', storage)[0]['value'],
    }
    for key, value in variables.items():
        run('gh', 'variable', 'set', key, '--repo', args.repo, '--body', value)
    for key, value in secrets.items():
        run('gh', 'secret', 'set', key, '--repo', args.repo, value=value)
    print('GitHub Actions variables and secrets configured. No secret values printed.', flush=True)


if __name__ == '__main__':
    main()
