# QA Insights API

FastAPI backend for the QA Pulse micro-frontends. It provides email/password
authentication, role checks, and randomized QA reporting data. User accounts
are stored in PostgreSQL; QA dashboard and test-case samples exist only in
memory.

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
- `OPENROUTER_API_KEY`: only needed for the legacy chat endpoints.

Apply the QA authentication migration to the existing database:

```sh
psql "$PSQL_STR" -f migrations/0002_qa_auth.sql
```

It creates `qa_data.users` without changing the existing `public` schema.
PostgreSQL unquoted identifiers cannot contain hyphens, so the schema name is
`qa_data`, not `qa-data`.

Run the API on port 8000:

```sh
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Interactive API docs are available at `http://localhost:8000/docs`.

## QA endpoints

All QA business-data endpoints require a valid QA session cookie.

| Endpoint | Access | Purpose |
| --- | --- | --- |
| `POST /api/qa/auth/signup` | Public | Create an account with username, email, and password |
| `POST /api/qa/auth/login` | Public | Sign in with email and password |
| `GET /api/qa/auth/session` | Signed in | Return the current account |
| `POST /api/qa/auth/logout` | Signed in | Clear the session cookie |
| `GET /api/qa/dashboard` | Signed in | Random KPIs, readiness, trend, and execution summaries |
| `GET /api/qa/test-cases` | QA roles | Random in-memory cases; supports `status` and `query` |
| `GET /api/qa/test-cases/{case_id}` | QA roles | Case details, logs, failure context, and placeholders |
| `GET /api/qa/admin/overview` | `ADMIN` | Randomized administrative overview |

Signup passwords must contain 12–128 characters and are scrypt-hashed. Signup
assigns `QA_MANAGER`; clients cannot choose a role. Promote an administrator
out of band in the database. This development authentication is not a
production identity provider. A trusted backend or identity provider must
enforce production authentication and authorization; frontend route guards
are not a security boundary.

Dashboard and admin metrics are randomized per request. The test-case catalog
is generated in memory once per process. None of these QA results are persisted
or represent actual test outcomes.

## Database and legacy endpoints

The existing PostgreSQL URL and DAZZ database are reused; QA user accounts are
isolated in the `qa_data` schema. Existing DAZZ API routes and their migration
remain available for compatibility, but the DAZZ frontend and its Node/Vite
build configuration are not part of this API repository.

Run the backend tests with:

```sh
pytest -q
```
