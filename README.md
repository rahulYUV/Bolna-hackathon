# Hisaab

Hisaab helps a kirana shopkeeper track customer credit and follow up politely by voice. The dashboard manages customers, balances, payments, call outcomes, and follow-ups. Outbound calls are placed through a configured Bolna voice agent; the app stores the resulting call details and presents them to the shopkeeper.

## What works in this repository

- FastAPI backend with PostgreSQL persistence.
- React, TypeScript, and Vite dashboard, served as static assets by FastAPI after a production build.
- Shopkeeper-only dashboard access using Supabase phone OTP or a local-only demo login.
- Customer creation and editing, Indian phone normalization, payment recording, paid/unpaid state, and do-not-call controls.
- Outbound Bolna call triggering with calling-hour, attempt, cooldown, and duplicate-request safeguards.
- Authenticated and deduplicated Bolna call-ended webhook handling.
- Call history with summary, transcript, duration, timestamps, status, phone details, and authenticated recording playback when Bolna supplies those fields.
- On-demand execution lookup from Bolna when call details need refreshing.
- Daily retention cleanup for app-stored call artifacts and the temporary redacted payload snapshots.

Automatic follow-up calling, a retry scheduler, and deployment configuration are not implemented. Promise dates are recorded and shown in the dashboard; they do not trigger a future call automatically.

## Architecture

```text
frontend/ (React + TypeScript + Vite)
          | Supabase OTP, authenticated API requests
          v
FastAPI (app/main.py) ---- PostgreSQL/Supabase DB (app/db.py, schema.sql)
          |                         ^
          | Bolna call trigger      | Bolna call-ended webhook
          v                         |
      Bolna Voice Agent ------------+
```

`app/sarvam.py` contains a Sarvam client and transcript outcome-extraction helper, with a standalone example in `sarvam_test.py`. The active call and webhook routes currently use the configured Bolna agent and accept structured `extracted_data` from Bolna; they do not invoke the Sarvam helper. Configure Sarvam in the Bolna agent itself if that agent uses Sarvam for speech processing.

## Repository map

| Path | Purpose |
|---|---|
| `app/main.py` | FastAPI routes, authentication, call/webhook flow, recording proxy, retention task |
| `app/db.py` | PostgreSQL queries and schema compatibility helpers |
| `app/reliability.py` | Strict extraction schema, promise validation, status transitions |
| `app/sarvam.py` | Optional Sarvam transcript helper; not part of active webhook processing |
| `frontend/src/` | Dashboard source code |
| `app/static/` | Production frontend output served by FastAPI |
| `schema.sql` | Initial database schema for a fresh database |
| `tests/` | Backend unit and route tests; database/provider calls are mocked where applicable |
| `fetch_execution.py` | Fetches a Bolna execution and writes a redacted local JSON snapshot |
| `docs/` | Reliability, API/dashboard behavior, and implementation audit notes |

## Requirements

- Python 3.11 or newer.
- Node.js and npm (for frontend development/build).
- PostgreSQL. Supabase Postgres is supported using its connection string.
- Bolna credentials to place real calls.
- Supabase Auth credentials for real phone OTP login, unless using local demo mode.

## Local setup

### 1. Create the database

Create a PostgreSQL database, then run [`schema.sql`](./schema.sql) against it. The application also has compatibility helpers for selected columns, but a fresh database should be initialized from the checked-in schema.

### 2. Configure the backend

Copy `.env.example` to `.env` and fill the values required for your environment. Keep `.env` private and never put provider secrets in `VITE_` variables.

Minimum backend settings:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
BOLNA_API_KEY=your_bolna_api_key
BOLNA_AGENT_ID=your_bolna_agent_id
SHOPKEEPER_PHONE=+91XXXXXXXXXX
```

For real Supabase authentication, also set `SUPABASE_URL` and `SUPABASE_ANON_KEY`. For local-only demo authentication, set `DEMO_AUTH_BYPASS=true`; the bypass accepts requests only from the same machine and requires the configured shopkeeper phone. Do not enable this mode on a public deployment.

Other settings and defaults are listed with comments in [`.env.example`](./.env.example), including calling hours, attempt limits, webhook validation, cooldown, and 30-day retention.

Install dependencies and run the API from the project root:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is at <http://127.0.0.1:8000>. `GET /health` checks API/database availability, and <http://127.0.0.1:8000/docs> shows the OpenAPI interface.

### 3. Configure and run the dashboard

For real Supabase OTP, set the same public project URL and anon/publishable key for both backend and frontend:

```dotenv
SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLIC_ANON_KEY
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLIC_ANON_KEY
```

Enable phone sign-in and configure an SMS provider in Supabase Auth. The app only allows the configured `SHOPKEEPER_PHONE`. Never put a Supabase service-role key in the frontend.

To run the frontend with Vite during development, open a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite runs at <http://127.0.0.1:5173>; keep FastAPI running at port 8000. To serve the dashboard from FastAPI, build it after setting `VITE_` values:

```powershell
cd frontend
npm run build
```

Then open <http://127.0.0.1:8000/>. Restart FastAPI after backend `.env` changes; restart Vite or rebuild after frontend environment changes.

### Local demo login

With `DEMO_AUTH_BYPASS=true`, the local demo accepts a six-digit code for the configured owner phone and creates an in-memory session. It only works from loopback. Sessions disappear when the API process restarts. Use real Supabase OTP for deployment.

## Main API routes

The interactive API reference at `/docs` is the source of truth for request/response schemas. Protected routes require the shopkeeper session.

| Method and path | Purpose |
|---|---|
| `GET /health` | API/database health |
| `GET /auth/demo-mode` | Reports whether local demo authentication is enabled |
| `POST /auth/check-shopkeeper-phone` | Validates the configured owner phone before OTP request |
| `POST /auth/demo-login` | Local loopback-only demo login |
| `GET /auth/session` | Current shopkeeper session |
| `GET /customers`, `POST /customers` | List and create customers |
| `GET /customers/{id}`, `PATCH /customers/{id}` | Read and update a customer |
| `POST /customers/{id}/mark-paid`, `POST /customers/{id}/mark-unpaid` | Change paid state |
| `POST /customers/{id}/payment`, `POST /customers/{id}/payments` | Record a payment |
| `POST /customers/{id}/do-not-call`, `POST /customers/{id}/allow-calls` | Manage call opt-out |
| `GET /dashboard/summary`, `GET /dashboard/followups` | Dashboard KPIs and prioritized follow-ups |
| `GET /shop-profile` | Configured single-shop profile |
| `GET /calls`, `POST /calls/trigger` | Call history and outbound call trigger |
| `POST /calls/{id}/sync`, `GET /calls/{id}/recording` | Refresh call data and stream recording |
| `POST /webhook/call-ended` | Bolna execution event callback |

Example call trigger:

```json
{"customer_id": 1}
```

The response includes the Bolna execution ID when the provider accepts the call. Place demo calls only to numbers whose owners have agreed to receive them.

## Call details and provider behavior

The webhook and on-demand sync read the Bolna execution fields `summary`, `transcript`, `conversation_duration`, `created_at`/`initiated_at`, `agent_number`, and `telephony_data.recording_url`, plus Bolna `extracted_data` for the validated outcome. The transcript is displayed with Bolna's speaker labels. Recording playback goes through the authenticated backend proxy; the provider URL is not returned to the dashboard.

Bolna delivery to a local machine requires a publicly reachable webhook URL. If that is unavailable, the dashboard's **Refresh details** action uses the stored Bolna execution ID to retrieve the completed execution. This requires `BOLNA_API_KEY` and an execution still available from Bolna.

## Tests and checks

From `frontend/`:

```powershell
npm run typecheck
npm run build
```

From the project root, with the Python dependencies installed:

```powershell
python -m unittest discover -s tests -v
```

The checked-in backend tests cover validation, auth boundaries, and selected route behavior with mocks. They do not verify a live Supabase database, Bolna API, Sarvam API, or real phone call. Use a dedicated test database and provider test setup before performing manual integration testing.

## Data handling and safety

- Use `BOLNA_WEBHOOK_SECRET` for local webhook testing, or the configured Bolna source IP allowlist for production webhook access. See [docs/reliability.md](./docs/reliability.md).
- Call attempts are limited by calling hours, `MAX_CALL_ATTEMPTS`, customer opt-out, and `CALL_TRIGGER_COOLDOWN_MINUTES`.
- Store timestamps in UTC; promise dates are interpreted as India calendar dates.
- `CUSTOMER_DATA_RETENTION_DAYS` defaults to 30. The app removes expired call rows and related call audit/webhook records, and expires local redacted payload snapshots. The cleanup loop runs while the API process is running; Bolna-hosted recordings follow Bolna's retention policy.
- Keep phone numbers, transcripts, API keys, and webhook secrets private. Temporary local payload snapshots are redacted before writing and ignored by Git.

## Current limits

- No automatic future call scheduler or retry queue; follow-up dates are stored for the shopkeeper.
- Runtime webhook processing uses Bolna's structured `extracted_data`; the separate Sarvam extraction utility is not called by the route.
- No payment gateway/UPI integration, Telegram alerts, or deployment manifests are included.
- The configured Bolna agent prompt and its internal speech-provider configuration are managed in Bolna, outside this repository.

For reliability details and a claim-by-claim implementation audit, see [docs/reliability.md](./docs/reliability.md) and [docs/audit.md](./docs/audit.md). Dashboard metric definitions are in [docs/dashboard-metrics.md](./docs/dashboard-metrics.md).
