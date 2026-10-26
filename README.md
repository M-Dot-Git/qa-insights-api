# QA Insights API

FastAPI backend for the QA Pulse micro-frontends. It verifies Keycloak bearer
access tokens, enforces realm-role permissions, and serves randomized QA
reporting data. Keycloak owns QA identities; QA passwords are not stored by
this API.

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
- `KEYCLOAK_ADMIN_CLIENT_ID` and `KEYCLOAK_ADMIN_CLIENT_SECRET`: a confidential
  service-account client for disabled registration creation and admin review.
- `OPENROUTER_API_KEY`: only needed for the legacy chat endpoints.

Import [`../qa-mfe-shell/keycloak/qa-pulse-realm.json`](../qa-mfe-shell/keycloak/qa-pulse-realm.json)
into the local Keycloak instance. It defines the public `qa-mfe-shell` client,
PKCE S256, the `qa-insights-api` audience mapper, and the supported realm
roles, including `QA_ENGINEER`. Do not enable password or
direct-grant login in the SPA client.

For approval-backed registration, create a separate confidential Keycloak
client named `qa-insights-api-admin`, enable its service account, and grant
that service account only the `query-users`, `view-users`, and `manage-users`
client roles from `realm-management`. Store its generated client secret in the
API's `KEYCLOAK_ADMIN_CLIENT_SECRET` environment variable; never place it in a
browser app or commit it. Keep API issuer/audience settings and the admin
client credentials in the API environment.

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
| `POST /api/qa/auth/register` | Public | Create a disabled Keycloak user awaiting approval |
| `GET /api/qa/auth/session` | Signed in | Return the current Keycloak profile and supported roles |
| `GET /api/qa/admin/users/pending` | `ADMIN` | List pending registrations |
| `POST /api/qa/admin/users/{id}/approve` | `ADMIN` | Assign a role and enable a pending account |
| `POST /api/qa/admin/users/{id}/reject` | `ADMIN` | Keep the pending account disabled and mark it rejected |
| `GET /api/qa/dashboard` | Signed in | Random KPIs, readiness, trend, and execution summaries |
| `GET /api/qa/test-cases` | QA roles | Random in-memory cases; supports `status` and `query` |
| `GET /api/qa/test-cases/{case_id}` | QA roles | Case details, logs, failure context, and placeholders |
| `GET /api/qa/admin/overview` | `ADMIN` | Randomized administrative overview |

The supported realm roles are `ADMIN`, `QA_MANAGER`, `QA_ENGINEER`,
`DEVELOPER`, and `VIEWER`. Test-case APIs allow `ADMIN`, `QA_MANAGER`,
`QA_ENGINEER`, and `DEVELOPER`; the admin API requires `ADMIN`. Role checks
happen in FastAPI after JWT signature and claim validation; client route guards
are not an authorization boundary.

Self-service signup does not grant a role or enable the user. The API creates
the account disabled in Keycloak, and an administrator approves it with the
intended role from the Admin MFE. Rejected records remain disabled in Keycloak
with a `registrationStatus=rejected` attribute. Registration passwords are
sent directly from the browser to the API over HTTPS in production and passed
to Keycloak; the API does not store them.

Dashboard and admin metrics are randomized per request. The test-case catalog
is generated in memory once per process. None of these QA results are persisted
or represent actual test outcomes.

## Database and legacy endpoints

The existing PostgreSQL URL and DAZZ database are reused by the legacy DAZZ
API. The historical `0002_qa_auth.sql` migration is no longer needed for QA
sign-in; already-created `qa_data` records are not consulted. Existing DAZZ
API routes remain available for compatibility.

Run the backend tests with:

```sh
pytest -q
```
