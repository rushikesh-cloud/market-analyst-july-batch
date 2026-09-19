"""Render an ACI ARM request; output contains secrets and must stay temporary."""
import json
import os
from pathlib import Path


def render(env):
    fqdn = f"{env['AZURE_DNS_LABEL']}.{env['AZURE_LOCATION']}.azurecontainer.io"
    app_env = json.loads(env['APP_ENV_JSON'])
    app_env['CLERK_AUTHORIZED_PARTIES'] = f'https://{fqdn}'
    app_env['MARKET_ANALYST_WORKSPACE_ROOT'] = '/app'
    app_env['ANALYSIS_ARTIFACT_DIR'] = '/app/analysis-artifacts'
    environment = [{'name': name, 'secureValue': str(value)} for name, value in sorted(app_env.items())]
    mounts = [{'name': 'documents', 'mountPath': '/app/documents'},
              {'name': 'analysis-artifacts', 'mountPath': '/app/analysis-artifacts'}]
    probe = {'httpGet': {'path': '/api/health', 'port': 8000, 'scheme': 'http'},
             'initialDelaySeconds': 60, 'periodSeconds': 15, 'timeoutSeconds': 5, 'failureThreshold': 6}
    wait_command = (
        'until /app/.venv/bin/python -c "import urllib.request; '
        "urllib.request.urlopen('http://localhost:8000/api/health', timeout=5)"
        '"; do sleep 5; done; exec /app/.venv/bin/python -m app.worker'
    )
    containers = [
        {'name': 'web', 'properties': {
            'image': env['DEPLOY_IMAGE'], 'ports': [{'port': 8000, 'protocol': 'TCP'}],
            'environmentVariables': environment, 'volumeMounts': mounts,
            'resources': {'requests': {'cpu': 1, 'memoryInGB': 2}},
            'livenessProbe': probe, 'readinessProbe': probe}},
        {'name': 'document-worker', 'properties': {
            'image': env['DEPLOY_IMAGE'], 'command': ['/bin/sh', '-c', wait_command],
            'environmentVariables': environment, 'volumeMounts': mounts,
            'resources': {'requests': {'cpu': 1, 'memoryInGB': 2}}}},
        {'name': 'https', 'properties': {
            'image': 'caddy:2.10.2-alpine',
            'command': ['caddy', 'reverse-proxy', '--from', fqdn, '--to', 'localhost:8000'],
            'ports': [{'port': 80, 'protocol': 'TCP'}, {'port': 443, 'protocol': 'TCP'}],
            'volumeMounts': [{'name': 'caddy', 'mountPath': '/data'}],
            'resources': {'requests': {'cpu': 0.25, 'memoryInGB': 0.5}}}},
    ]
    volumes = [{'name': name, 'azureFile': {
        'shareName': name, 'storageAccountName': env['AZURE_STORAGE_ACCOUNT'],
        'storageAccountKey': env['AZURE_STORAGE_KEY'], 'readOnly': False,
    }} for name in ('documents', 'analysis-artifacts', 'caddy')]
    return {
        'apiVersion': '2023-05-01', 'type': 'Microsoft.ContainerInstance/containerGroups',
        'name': env['AZURE_CONTAINER_NAME'], 'location': env['AZURE_LOCATION'],
        'identity': {'type': 'UserAssigned', 'userAssignedIdentities': {env['AZURE_RUNTIME_IDENTITY_ID']: {}}},
        'properties': {
            'osType': 'Linux', 'restartPolicy': 'Always',
            'imageRegistryCredentials': [{'server': env['AZURE_ACR_SERVER'], 'identity': env['AZURE_RUNTIME_IDENTITY_ID']}],
            'ipAddress': {'type': 'Public', 'dnsNameLabel': env['AZURE_DNS_LABEL'],
                          'ports': [{'port': 80, 'protocol': 'TCP'}, {'port': 443, 'protocol': 'TCP'}]},
            'containers': containers, 'volumes': volumes,
        },
        'tags': {'application': 'market-analyst-july-batch', 'commit': env['GITHUB_SHA'], 'managed-by': 'github-actions'},
    }


if __name__ == '__main__':
    path = Path(os.environ['ACI_SPEC_PATH'])
    # O_EXCL prevents an existing file or symlink from being overwritten.
    with path.open('x', opener=lambda p, flags: os.open(p, flags, 0o600)) as output:
        json.dump(render(os.environ), output)
