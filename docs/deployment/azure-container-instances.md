# Azure Container Instances deployment

The `deploy` branch deploys automatically through
[deploy-aci.yml](../../.github/workflows/deploy-aci.yml). The workflow also supports
manual dispatch once GitHub has registered it. Deployments are serialized, tests
must pass, and every image is tagged with its exact Git commit.

## Resources and authentication

The `market-analyst-july-batch-deploy` resource group in Central India contains:

- A Basic Azure Container Registry, `marketanalystjulydeploy` (admin login disabled).
- A Standard LRS storage account, `marketanalystjulyfiles`, with separate 20 GiB
  shares for documents, analysis artifacts, and Caddy certificate state.
- A user-assigned identity, `market-analyst-runtime`, with registry `AcrPull` and
  secret `get` access to the existing `marketanalystjulybatchkv` Key Vault.
- An ACI group, `market-analyst-july`, running the API/frontend (1 CPU, 2 GiB),
  document ingestion worker (1 CPU, 2 GiB), and Caddy HTTPS proxy (0.25 CPU, 0.5 GiB).

The expected endpoint is https://market-analyst-july.centralindia.azurecontainer.io.
Only ports 80 and 443 are public. Caddy obtains and renews certificates, redirects
HTTP to HTTPS, and forwards to the internal API on port 8000. The worker waits for
API startup and migrations before polling PostgreSQL.

GitHub uses an Entra application with a federated credential limited to
`repo:rushikesh-cloud/market-analyst-july-batch:ref:refs/heads/deploy`. Its Contributor
role is limited to the deployment resource group. There is no Azure client secret.
The separate runtime managed identity retrieves database and provider credentials
from Key Vault. Existing PostgreSQL, OpenAI, and Document Intelligence resources
remain in `market-analyst-july-batch`.

PostgreSQL's `AllowAzureServicesForACI` firewall rule permits Azure-originating
connections (including other tenants); PostgreSQL password authentication and TLS
remain mandatory. For stricter network isolation, move to private networking with
controlled outbound access. The existing developer IP rule is retained.

## GitHub configuration

| Actions secret | Purpose |
| --- | --- |
| `AZURE_CLIENT_ID` | GitHub's federated Entra application ID |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_STORAGE_KEY` | Mount the Azure Files shares |
| `APP_ENV_JSON` | Backend configuration, Key Vault secret names, runtime managed identity client ID, and Clerk settings |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk frontend key embedded during the image build |

Database passwords and OpenAI/Document Intelligence API keys remain in Key Vault.
The backend does not require a Clerk secret key. All backend environment values
are submitted as ACI secure values; the temporary specification is private to the
runner and deleted after deployment.

Actions variables hold `AZURE_RESOURCE_GROUP`, `AZURE_LOCATION`, `AZURE_ACR_NAME`,
`AZURE_ACR_SERVER`, `AZURE_CONTAINER_NAME`, `AZURE_DNS_LABEL`,
`AZURE_STORAGE_ACCOUNT`, and `AZURE_RUNTIME_IDENTITY_ID`.

Provision/reconcile resources and transfer configuration with authenticated `az`
and `gh` CLIs (the command prints no secrets):

```bash
python scripts/deploy/bootstrap_azure.py \
  --env-file /path/to/backend.env \
  --frontend-env-file /path/to/frontend.env
```

The first round uses the existing Clerk development instance. A production Clerk
instance, its publishable key, and matching issuer should be configured before a
production launch. The renderer sets authorized origins to the deployed HTTPS
origin. Authentication remains required for all workspace APIs.

## Delivery and verification

Merge the desired changes into `deploy` and push:

```bash
git switch deploy
git merge main
git push origin deploy
```

Use a separate worktree if the main checkout has unfinished changes. GitHub runs
backend unit tests, frontend request tests, deployment specification tests, the
Docker frontend build/typecheck, image publication, ACI deployment, and live smoke
checks. Live checks require every container to be running, a trusted HTTPS
certificate, a healthy API, downloadable JavaScript assets, and rejection of an
anonymous request to `/api/auth/me`.

```bash
gh run list --branch deploy
gh run view RUN_ID --log-failed
python scripts/deploy/verify_deployment.py \
  --resource-group market-analyst-july-batch-deploy --name market-analyst-july
az container logs -g market-analyst-july-batch-deploy -n market-analyst-july --container-name web
az container logs -g market-analyst-july-batch-deploy -n market-analyst-july --container-name document-worker
```

ACI updates can briefly interrupt service. Revert the problematic commit on
`deploy` and push to deploy the prior code through the same checks. Database
migrations run on API startup and are not automatically reversed; inspect schema
compatibility before rollback. Azure Files survive container replacement. A
rollback does not restore database or file contents. Rotate the storage account
key in GitHub if it is regenerated in Azure.

Azure Files mounting in ACI requires root, so the workflow explicitly builds with
`RUNTIME_USER=root`. Ordinary local Docker builds retain `appuser`. This deployment
uses the latest committed application baseline; the unfinished analysis worker
is not included, so queued agentic analysis is not yet processed by this release.
Existing local PDFs/artifacts are not copied to Azure Files by provisioning.

The shared KB workflow index currently has no deployment-specific route; project
configuration and the deployment-patterns skill were used for implementation.
