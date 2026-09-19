# Clerk authentication

React uses `@clerk/react` for sign-up, sign-in, sessions, and account management.
FastAPI verifies Clerk session JWTs using PyJWT and the instance's public JWKS.
The linked Clerk application is `app_3JX4rhmpow8eJkiC94QCMnwlJGf` (Market Analyst).
The application has two server-assigned roles:

- **Admin:** Companies, Documents (including upload and search), and Agentic Analysis.
- **General:** Agentic Analysis only, including company selection, run submission,
  history, results, and evidence/artifact downloads.

New signed-in accounts are general users by default. Admin IDs are configured in
`CLERK_ADMIN_USER_IDS`; matching an email address or sending a role in client
metadata never grants admin access. The existing account is configured as admin in
the local ignored `.env`. Analysis remains shared across workspace users; this
change does not add per-user or organization data isolation.

## Local setup

1. Run `npm run install:all`.
2. From `frontend`, run `clerk auth login`, then
   `clerk init --app app_3JX4rhmpow8eJkiC94QCMnwlJGf`. React lives in this directory;
   the repository root is only a development-process launcher.
3. Clerk writes the development publishable key to `frontend/.env.local`.
   Alternatively, use `frontend/.env.example` and supply your application's key.
4. Add `CLERK_ISSUER_URL=https://frank-crab-5856.clerk.accounts.dev` to the root
   `.env`. See `backend/.env.example` for the other server settings.
5. Start or restart `npm run dev`. Changes to backend environment variables require
   a full backend restart; Uvicorn source reload does not reload uv's environment file.
6. Visit http://localhost:5173 and select **Sign up**. Clerk controls the configured
   identifiers, social providers, and verification requirements.
7. New users land on **Agentic Analysis**. To grant administration, add the verified
   Clerk `user_...` ID to `CLERK_ADMIN_USER_IDS` in the root `.env` and restart the
   backend. Refresh the browser to load the new role. The header profile button
   provides account management and **Sign out**.
8. Run `clerk doctor` from `frontend` to check the linked development instance.

`CLERK_ACCESS_MODE=all_signed_in` is the default and is configured locally. All
signed-in users can access analysis, while only `CLERK_ADMIN_USER_IDS` can access
management routes. Admin promotion and revocation require configuration and a full
backend restart. Every API request enforces the current server role; refreshing
the browser updates the navigation.

For an invitation-only workspace, set `CLERK_ACCESS_MODE=approved_users` and list
general users in `CLERK_ALLOWED_USER_IDS`. Configured admins retain access in that
mode without needing a second allowlist entry. Unknown modes fail closed.

The backend uses public signing keys and does not require `CLERK_SECRET_KEY`.
The CLI may write that key locally; keep it in ignored environment files and never
prefix it with `VITE_`. Only the publishable key belongs in a client build.

## API behavior

Every workspace API requires a Clerk session bearer token. Company management,
document, upload, ingestion-status, retry, content, chunk, and document-search
routes additionally require admin access. `GET /api/analysis/companies` is the
read-only company selector available to both roles. The analysis routes, including
`/api/companies/{company_id}/analysis-runs`, are available to both roles. The React request hook obtains a
current token with `useAuth().getToken()` for each request, including uploads and
polling. It never stores tokens in local storage. API requests cannot follow
redirects with credentials.

FastAPI verifies RS256 signatures against the configured issuer's cached JWKS,
issuer, expiry, not-before, issued-at, authorized origin (`azp`), user ID, and session
ID. Pending organization sessions are rejected. The default allowed origins are
`http://localhost:5173` and `http://localhost:8000`; configure
`CLERK_AUTHORIZED_PARTIES` as a comma-separated list for other origins. This list
also configures CORS. Cookie-only requests are not accepted by the backend.

- `GET /api/auth/me` returns the user's verified `user_id` and `role` (`admin` or `general`).
- Missing or invalid sessions return `401` with a Bearer challenge.
- General users requesting management routes return `403`. Accounts awaiting
  approval in invitation-only mode also return `403`.
- Missing configuration or unavailable signing keys return `503`.
- `GET /api/health` and CORS preflight remain public.

Workspace pages mount after the access check and unmount on sign-out or session
changes. The API independently enforces access on every request. Tokens use Clerk's
short lifetime; local verification does not contact Clerk to check revocation on
every request, so an already issued token may remain valid until its expiry.

## Production configuration

Create/configure a production instance of the same Clerk application and use its
publishable key and issuer. Set the exact deployed frontend origin in
`CLERK_AUTHORIZED_PARTIES` and configure `CLERK_ADMIN_USER_IDS`. The development CLI
link and ignored keys are local machine state, not deployment configuration.

Vite embeds `VITE_CLERK_PUBLISHABLE_KEY` at build time. Supply it when running
`npm run build`. For the existing container recipe, pass
`--build-arg VITE_CLERK_PUBLISHABLE_KEY=pk_live_...` and provide the backend's
`CLERK_*` variables at runtime. No Docker build is needed for local development.

## Validation

```bash
npm run build
npm --prefix frontend test
uv --directory backend run python -m unittest discover -s tests -v
```

Frontend request tests require Node 22.18+ (native TypeScript stripping). API auth
tests use real local RSA signatures and exercise every protected route without a
Clerk network connection. Existing business-route tests explicitly override access;
they do not introduce an authentication bypass into application code. PostgreSQL
search integration tests remain opt-in as documented in the project README.

Browser validation also completed sign-up (email and phone test codes), password
sign-in, sign-out, mobile profile controls, and real Clerk JWT verification against
an isolated local API/database. It used Clerk's official testing-token behavior;
the temporary development account was deleted afterward. Google sign-in was not
exercised. No production instance was deployed.

Sources: [React quickstart](https://clerk.com/docs/react/getting-started/quickstart?manual=1),
[JWT verification](https://clerk.com/docs/guides/sessions/manual-jwt-verification),
[session claims](https://clerk.com/docs/guides/sessions/session-tokens).
