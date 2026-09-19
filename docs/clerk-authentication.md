# Clerk authentication

React uses `@clerk/react` for sign-up, sign-in, sessions, and account management.
FastAPI verifies Clerk session JWTs using PyJWT and the instance's public JWKS.
The linked Clerk application is `app_3JX4rhmpow8eJkiC94QCMnwlJGf` (Market Analyst).
The application remains a shared research workspace: approved users have the same
read and write access to existing companies and documents. There is no per-user or
organization data isolation in this integration.

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
7. With the default access policy, a new account sees an access-pending message.
   Copy its `user_...` ID from the Clerk Dashboard into the root `.env`:
   `CLERK_ALLOWED_USER_IDS=user_first,user_second`. Restart the backend, then select
   **Retry**. The header profile button provides account management and **Sign out**.
8. Run `clerk doctor` from `frontend` to check the linked development instance.

`CLERK_ACCESS_MODE=approved_users` is the default. Setting it to `all_signed_in`
explicitly gives **every account that signs up** access to all workspace records and
mutations. Unknown modes fail closed. Approval is based on verified Clerk user IDs,
not client-supplied email addresses or profile metadata. User approval and revocation
currently require server configuration and restart.

The backend uses public signing keys and does not require `CLERK_SECRET_KEY`.
The CLI may write that key locally; keep it in ignored environment files and never
prefix it with `VITE_`. Only the publishable key belongs in a client build.

## API behavior

All company, document, upload, ingestion-status, retry, content, chunk, and search
routes require a Clerk session bearer token. The React request hook obtains a
current token with `useAuth().getToken()` for each request, including uploads and
polling. It never stores tokens in local storage. API requests cannot follow
redirects with credentials.

FastAPI verifies RS256 signatures against the configured issuer's cached JWKS,
issuer, expiry, not-before, issued-at, authorized origin (`azp`), user ID, and session
ID. Pending organization sessions are rejected. The default allowed origins are
`http://localhost:5173` and `http://localhost:8000`; configure
`CLERK_AUTHORIZED_PARTIES` as a comma-separated list for other origins. This list
also configures CORS. Cookie-only requests are not accepted by the backend.

- `GET /api/auth/me` returns the approved user's verified `user_id`.
- Missing or invalid sessions return `401` with a Bearer challenge.
- Accounts awaiting approval return `403`.
- Missing configuration or unavailable signing keys return `503`.
- `GET /api/health` and CORS preflight remain public.

Workspace pages mount after the access check and unmount on sign-out or session
changes. The API independently enforces access on every request. Tokens use Clerk's
short lifetime; local verification does not contact Clerk to check revocation on
every request, so an already issued token may remain valid until its expiry.

## Production configuration

Create/configure a production instance of the same Clerk application and use its
publishable key and issuer. Set the exact deployed frontend origin in
`CLERK_AUTHORIZED_PARTIES` and configure the approved users. The development CLI
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
