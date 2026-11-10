# QA Insights API

FastAPI backend for the QA Pulse micro-frontends. The React shell signs users
in with Keycloak using Authorization Code flow and PKCE. This API verifies
Keycloak bearer access tokens, enforces realm-role permissions, and serves
randomized QA reporting data; it does not issue sessions, collect passwords,
or provision users.

## Requirements and setup

- Python 3.12+
- PostgreSQL

Create and activate a virtual environment, then install the dependencies:

```sh
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Copy `.env.sample` to `.env` and configure:

- `PSQL_STR` or `DATABASE_URL`: PostgreSQL connection URL.
- `SESSION_SECRET`: a random value of at least 32 characters.
- `APP_ENV` and `APP_ORIGIN`: set the allowed public origin in production.
- `KEYCLOAK_URL`, `KEYCLOAK_REALM`, and `KEYCLOAK_API_AUDIENCE`: expected token
  issuer and audience. The defaults match the local `qa-pulse` realm.
- `KEYCLOAK_ISSUER`: optional exact `iss` claim expected in access tokens. Set
  this separately when the API must reach the JWKS endpoint through an internal
  network address that differs from the browser-visible Keycloak URL.
- `KEYCLOAK_JWKS_URL`: optional signing-key endpoint override. Docker Compose
  uses the internal Keycloak service URL here while validating the public
  browser-visible issuer.
- `OPENROUTER_API_KEY`: only needed for the legacy chat endpoints.

Import [`../qa-mfe-shell/keycloak/qa-pulse-realm.json`](../qa-mfe-shell/keycloak/qa-pulse-realm.json)
into the local Keycloak instance. It defines the public `qa-mfe-shell` client,
PKCE S256, the `qa-insights-api-admin` audience mapper, and the supported realm
roles, including `QA_ENGINEER`. Do not enable password or
direct-grant login in the SPA client.

Create users and assign realm roles in Keycloak's Admin Console. The public
`qa-mfe-shell` client handles sign-in; do not enable password or direct-grant
login in the SPA client or add a client secret to the browser application.

Run the API on port 8000:

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs`.

## QA endpoints

All QA business-data endpoints require a valid Keycloak access token in the
`Authorization: Bearer` header. Tokens must be signed with Keycloak's RS256
realm key, have the configured issuer and API audience, and be unexpired.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `GET /api/qa/auth/session` | Signed in | Return the current Keycloak profile and supported roles |
| `GET /api/qa/dashboard` | Signed in | Random KPIs, readiness, trend, and execution summaries |
| `GET /api/qa/test-cases` | QA roles | Random in-memory cases; supports `status` and `query` |
| `GET /api/qa/test-cases/{case_id}` | QA roles | Case details, logs, failure context, and placeholders |

The supported realm roles are `ADMIN`, `QA_MANAGER`, `QA_ENGINEER`,
`DEVELOPER`, and `VIEWER`. Test-case APIs allow `ADMIN`, `QA_MANAGER`,
`QA_ENGINEER`, and `DEVELOPER`. Role checks happen in FastAPI after JWT
signature and claim validation; client route guards are not an authorization
boundary. The API retains the signed-in profile endpoint for the shell but has
no registration, pending-user, approval, or user-administration endpoints.

The test-case catalog is generated in memory once per process. None of these
QA results are persisted or represent actual test outcomes.

## Database and legacy endpoints

The existing PostgreSQL URL and DAZZ database are reused by the legacy DAZZ
API. The historical `0002_qa_auth.sql` migration is no longer needed for QA
sign-in; already-created `qa_data` records are not consulted. Existing DAZZ
API routes remain available for compatibility.

Run the backend tests with:

```sh
pytest -q
```
