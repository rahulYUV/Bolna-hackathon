<h1 align="center">🧾 Hisaab</h1>

<p align="center"><strong>💚 A clearer khata. 📞 A kinder follow-up.</strong></p>

<p align="center">
  <a href="https://www.python.org/"><img alt="Python 3.11+" src="https://img.shields.io/badge/Python-3.11%2B-3776AB?style=for-the-badge&logo=python&logoColor=white"></a>
  <a href="https://fastapi.tiangolo.com/"><img alt="FastAPI" src="https://img.shields.io/badge/API-FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white"></a>
  <a href="https://react.dev/"><img alt="React" src="https://img.shields.io/badge/UI-React-149ECA?style=for-the-badge&logo=react&logoColor=white"></a>
  <a href="https://www.typescriptlang.org/"><img alt="TypeScript" src="https://img.shields.io/badge/TypeScript-5.8-3178C6?style=for-the-badge&logo=typescript&logoColor=white"></a>
  <a href="https://www.postgresql.org/"><img alt="PostgreSQL" src="https://img.shields.io/badge/Database-PostgreSQL-4169E1?style=for-the-badge&logo=postgresql&logoColor=white"></a>
  <a href="https://www.bolna.ai/"><img alt="Bolna Voice AI" src="https://img.shields.io/badge/Voice%20AI-Bolna-315C42?style=for-the-badge"></a>
</p>

<p align="center">
  🌿 Hisaab helps neighborhood kirana shopkeepers organize customer credit and make thoughtful voice follow-ups when they choose.
</p>

<p align="center">
  <a href="#product-preview">🖼️ Product preview</a> ·
  <a href="#the-product">✨ How it works</a> ·
  <a href="#run-locally">🚀 Run locally</a> ·
  <a href="#api-overview">🔌 API</a>
</p>

---

## The problem

For a neighborhood shop, collecting udhaar is personal. Customers are often regulars and neighbors, so asking for payment can feel awkward. Hisaab brings the ledger and follow-up history into one dashboard and gives the shopkeeper a deliberate way to start a conversation with care.

> **Product stage:** Hisaab is an early MVP built around one shopkeeper workflow. Calls are initiated manually by the shopkeeper. Promise dates are saved for reference and do not automatically trigger calls.

## The product

Hisaab combines a digital customer ledger with a voice follow-up workflow:

1. **Keep the khata organized.** Add and edit customers, review balances, and see payment status and promises.
2. **Choose whether to follow up.** Open a customer profile and start a call when you decide it is appropriate. Hisaab does not automatically place future calls.
3. **Let the voice agent handle the reminder.** A configured Bolna voice agent places the outbound call. The intended experience is a brief, respectful Hindi or Hinglish conversation.
4. **Review what happened.** When Bolna provides the information, Hisaab saves the call status, summary, transcript, duration, and recording reference. A captured promise date can be shown alongside the customer account.
5. **Stay in control.** Record payments, mark balances paid or unpaid, and set a customer to “do not call.”

The goal is not to replace the shopkeeper's relationship with a customer. Hisaab is designed to make the shopkeeper's records clearer and make a chosen follow-up easier to manage.

## What is implemented

- Shopkeeper dashboard with customer accounts, balances, payment state, follow-up list, and recent call activity.
- Customer creation and editing, Indian phone number normalization, payment recording, and paid/unpaid controls.
- Shopkeeper-only dashboard access through Supabase phone OTP, or a loopback-only local demo login.
- Manual outbound call trigger through a configured Bolna agent.
- Call protections for configured calling hours, attempt limits, customer opt-out, cooldown, and duplicate trigger requests.
- Authenticated Bolna call-ended webhook with duplicate-event handling.
- Call history with outcome, summary, transcript, duration, timestamps, and phone details when supplied by Bolna.
- On-demand execution refresh and authenticated recording playback when the provider makes the relevant call data available.
- Promise dates stored and shown in the customer workflow. These dates do not schedule a call.
- Retention cleanup for app-stored call artifacts and temporary redacted payload snapshots.

## Product preview

### Landing page

The product introduction and the idea behind a more thoughtful voice follow-up.

![Hisaab landing page](images/1st.png)

### Shopkeeper dashboard

An at-a-glance view of outstanding balances, promises, and call activity.

<p align="center">
  <img src="images/2nd.png" width="49%" alt="Hisaab shopkeeper dashboard">
  <img src="images/3rd.png" width="49%" alt="Hisaab customer khata with balances and payment status">
</p>

<p align="center"><sub>Overview dashboard and customer khata</sub></p>

## How the system fits together

```text
React + TypeScript dashboard
          | Supabase phone OTP / authenticated requests
          v
FastAPI application -------- PostgreSQL (including Supabase Postgres)
          |                                      ^
          | outbound call request                | authenticated call-ended webhook
          v                                      |
     Bolna voice agent --------------------------+
```

The frontend is built with Vite. In production-build mode, FastAPI serves the generated frontend from `app/static/`. PostgreSQL stores shop, customer, payment, call, webhook-event, and call-state audit data.

## Repository map

| Path | Description |
| --- | --- |
| `app/main.py` | FastAPI routes, authentication, call and webhook flow, recording proxy, retention task |
| `app/db.py` | PostgreSQL queries and schema compatibility helpers |
| `app/reliability.py` | Extraction schema, promise validation, and call-state transitions |
| `app/config.py` | Environment-based application configuration |
| `frontend/src/` | React and TypeScript dashboard source |
| `app/static/` | Built frontend served by FastAPI |
| `schema.sql` | Initial schema for a fresh PostgreSQL database |
| `tests/` | Backend unit and route tests; provider/database calls are mocked where applicable |
| `docs/reliability.md` | Call flow, webhook safety, validation, and retention details |
| `docs/dashboard-metrics.md` | Definitions for dashboard metrics |
| `docs/audit.md` | Claim-by-claim implementation audit and known verification gaps |

## Run locally

### Requirements

- Python 3.11 or newer
- Node.js and npm (for frontend development or builds)
- PostgreSQL, or a Supabase Postgres connection string
- Bolna API key and agent ID to place real calls
- Supabase Auth configuration for real phone OTP; local demo auth is available for development

### 1. Create and configure the database

Create a PostgreSQL database and apply [`schema.sql`](./schema.sql). The application has compatibility helpers for selected columns, but a new database should start from the checked-in schema.

### 2. Configure environment variables

Copy `.env.example` to `.env` and set the values for your environment. At minimum, the backend needs:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
BOLNA_API_KEY=your_bolna_api_key
BOLNA_AGENT_ID=your_bolna_agent_id
SHOPKEEPER_PHONE=+91XXXXXXXXXX
```

For actual phone OTP sign-in, configure `SUPABASE_URL` and `SUPABASE_ANON_KEY`, enable phone sign-in in Supabase Auth, and configure its SMS provider. The app restricts access to the configured shopkeeper phone.

For a local-only demonstration, set `DEMO_AUTH_BYPASS=true`. This option only works for requests from the same machine, uses the configured shopkeeper phone, and creates an in-memory session that disappears when the API restarts. **Do not enable demo bypass on a public deployment.**

Other settings in `.env.example` cover shop profile, calling hours, attempt limits, webhook validation, call cooldown, and data retention. Keep `.env` private. Never expose provider credentials or a Supabase service-role key in frontend variables. Only the public Supabase anon/publishable key belongs in `VITE_` variables.

### 3. Start the backend

From the project root, in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API is available at `http://127.0.0.1:8000`. `GET /health` checks API/database availability, and the interactive API reference is at `http://127.0.0.1:8000/docs`.

### 4. Start or build the dashboard

For Supabase OTP, set the same public project URL and anon/publishable key for the frontend:

```dotenv
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLIC_ANON_KEY
```

For frontend development, use a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Vite runs at `http://127.0.0.1:5173`; keep FastAPI running at port 8000. To build the frontend for FastAPI to serve:

```powershell
cd frontend
npm run build
```

Then open `http://127.0.0.1:8000/`. Restart FastAPI after backend environment changes, and restart Vite or rebuild after frontend environment changes.

### Local demo sign-in

With `DEMO_AUTH_BYPASS=true`, open the app locally and use the six-digit demo code for the configured shopkeeper phone. The session is stored in memory by the API and is cleared when the process restarts. Use Supabase OTP for a deployed environment.

## API overview

Protected routes require an authenticated shopkeeper session. `/docs` is the source of truth for request and response schemas.

| Method and path | Purpose |
| --- | --- |
| `GET /health` | API and database health check |
| `GET /auth/demo-mode` | Check whether local demo authentication is enabled |
| `POST /auth/check-shopkeeper-phone` | Verify the configured owner phone before requesting OTP |
| `POST /auth/demo-login` | Local loopback-only demo sign-in |
| `GET /auth/session` | Read the current shopkeeper session |
| `GET /customers`, `POST /customers` | List and create customer accounts |
| `GET /customers/{id}`, `PATCH /customers/{id}` | Read and update a customer |
| `POST /customers/{id}/mark-paid`, `POST /customers/{id}/mark-unpaid` | Change a customer's paid state |
| `POST /customers/{id}/payment`, `POST /customers/{id}/payments` | Record a payment |
| `POST /customers/{id}/do-not-call`, `POST /customers/{id}/allow-calls` | Set or remove call opt-out |
| `GET /dashboard/summary`, `GET /dashboard/followups` | Read dashboard metrics and prioritized follow-ups |
| `GET /shop-profile` | Read the configured shop profile |
| `GET /calls`, `POST /calls/trigger` | Read call history or manually trigger a call |
| `POST /calls/{id}/sync`, `GET /calls/{id}/recording` | Refresh call details or stream an available recording |
| `POST /webhook/call-ended` | Receive a Bolna call event |

Example call-trigger request:

```json
{"customer_id": 1}
```

The API returns a Bolna execution ID when Bolna accepts the request. Only call people who have agreed to receive calls, and use test numbers for demonstrations.

## Calls, outcomes, and follow-up data

The app reads call details such as summary, transcript, conversation duration, timestamps, agent phone, recording URL, and structured outcome data when Bolna supplies them. The dashboard displays speaker labels in transcripts. Recording playback is streamed through an authenticated backend endpoint; the provider URL is not sent to the dashboard.

Bolna needs a publicly reachable webhook URL to send events to a local development machine. If a webhook cannot reach the app, **Refresh details** can request the execution from Bolna using its stored ID. This requires a configured `BOLNA_API_KEY` and an execution still available from Bolna.

Promise information is validated before it is stored. A promise amount cannot exceed the current ledger balance, and accepted promise dates are limited to today through 60 days out. Extracted call data does not directly change a customer's balance; payments are recorded separately by the shopkeeper.

## Dashboard metrics

Dashboard date boundaries use India time (`Asia/Kolkata`); database timestamps are stored in UTC. “Recovered after a Hisaab call” is a time-based association, not proof that the call caused the payment. See [`docs/dashboard-metrics.md`](./docs/dashboard-metrics.md) for metric definitions.

## Safety and data handling

- Call triggers respect configured calling hours, attempt limits, cooldowns, and customer opt-out.
- Bolna webhook requests are authenticated using the configured source IP allowlist or, for local development, `BOLNA_WEBHOOK_SECRET`.
- Duplicate webhook events are deduplicated. Call state changes are recorded and invalid backwards transitions are rejected.
- Only a strict set of outcome fields is accepted. Transcript text is not treated as instructions.
- Timestamps are stored in UTC; promise dates use India calendar dates.
- `CUSTOMER_DATA_RETENTION_DAYS` defaults to 30. The app removes expired call-related records and local redacted payload snapshots. Recording retention at Bolna is governed by Bolna.
- Keep phone numbers, transcripts, API keys, and webhook secrets private. Temporary payload snapshots are redacted before writing and ignored by Git.

See [`docs/reliability.md`](./docs/reliability.md) for implementation details and [`docs/audit.md`](./docs/audit.md) for known gaps and verification status.

## Development checks

From `frontend/`:

```powershell
npm run typecheck
npm run build
```

From the project root, with Python dependencies installed:

```powershell
python -m unittest discover -s tests -v
```

Automated backend tests use mocks for applicable database and provider behavior. They do not establish that a live Supabase database, Bolna API, or real phone call works end to end.

## Roadmap and validation

The current MVP focuses on a single shopkeeper workflow. The next product questions are whether customers find voice reminders respectful, which languages and times work best, and whether a saved promise leads to payment. Those questions require more shopkeeper and customer conversations; this repository does not claim those outcomes have been established.

Potential next steps include validating the call experience with customers, improving visibility into call outcomes, and evaluating whether an automatic follow-up scheduler is appropriate. A scheduler is not part of the current implementation.

## a preview

Recent call outcomes and follow-up activity appear together in the dashboard.

![Hisaab recent call activity and dashboard footer](images/footer.png)
