# Hisaab end-to-end audit

Audit date: 2026-10-31. No real provider requests were made. Bolna and LLM behavior must be mocked in automated tests.

## Documented claims

`agent.mmd` is absent from the repository, so it contains no inspectable claims or flow arrows. The flow below is taken from the written README and `docs/reliability.md`; no diagram arrows can be attributed to the missing file.

| Claim | Status | Evidence |
|---|---|---|
| README: Postgres persistence | Partial | `schema.sql` defines customers, calls, payments, webhook events, audit state; fresh database could not be started here. |
| README: Python FastAPI backend | Working | `app/main.py` defines the service and routes. |
| README: Python 3.10+ requirement | Contradicted | `app/reliability.py` imports `StrEnum`, available in Python 3.11+; README corrected to require 3.11. |
| README: Bolna Hindi/Hinglish voice agent | Partial | `app/main.py` posts customer and ledger amount. `rulesforcallagent.md` documents Hindi/Hinglish and a `[Shop Name]` opening, but code does not verify that this file is loaded by the configured Bolna agent; it has no good-time question or recording notice. |
| README: Claude extraction | Contradicted | The README originally claimed Claude; `app/sarvam.py` implements Sarvam, while `app/main.py` only parses webhook `extracted_data`. |
| README: APScheduler | Missing | No scheduler dependency or worker; `app/db.py` stores `next_followup_date` only. |
| README: Streamlit dashboard | Contradicted | `frontend/src/` is React/TypeScript and Vite; FastAPI serves `app/static`. |
| README: Telegram daily summary | Missing | No Telegram client or bot found. `/dashboard/summary` is an API, not Telegram delivery. |
| README: Render/Railway hosting and ngrok | Missing | No deployment configuration found. |
| README: listed customer/call/webhook/profile/dashboard endpoints | Partial | Present routes are in `app/main.py`; `GET /summary/today` is absent (actual route is `GET /dashboard/summary`). Listed `POST /customers/{id}/payment(s)` both exist; `/dashboard/followups` exists. |
| README: data tables | Partial | `schema.sql` includes customers, calls, payments, webhook events, and call state audit; listed fields are expanded/renamed (e.g. `notes`, `promise_date`, timestamps). |
| README: React/Vite dashboard and FastAPI static build | Working | `frontend/package.json`, `frontend/vite.config.ts`, `app/main.py`; `npm run build` passed. |
| README: owner-only protected routes | Partial | `require_shopkeeper` guards customer/call/dashboard routes (`app/main.py`); runtime auth test could not run. |
| README: demo login is loopback only | Working in code | `/auth/demo-login` validates `request.client.host` with `ipaddress.is_loopback` (`app/main.py`). Runtime test could not run. |
| `agent.mmd` claims / tech-stack rows / arrows | Missing | `agent.mmd` does not exist. |
| Reliability doc: webhook secret or IP allowlist | Working in code | `authenticate_bolna_webhook` enforces `BOLNA_WEBHOOK_SECRET` when configured, otherwise configured IPs (`app/main.py`). |
| Reliability doc: duplicate webhook suppression | Working in code | `webhook_events.provider_event_id` unique and `register_webhook_event` (`schema.sql`, `app/db.py`). |
| Reliability doc: extraction limited to four fields | Working in code | `Extraction` forbids extras (`app/reliability.py`). |
| Reliability doc: promise backend validation and ledger protection | Working in code | `validate_promise` bounds dates and amount; webhook saves promise fields and never updates `amount_due` (`app/main.py`, `app/db.py`). |
| README: do-not-call blocks manual trigger | Working in code | `/calls/trigger` checks `customer.do_not_call` (`app/main.py`). |
| README: calls within configured window | Partial | Trigger checks `SHOP_CALLING_HOURS` in Asia/Kolkata (`app/main.py`); default spans 10 AM–1 AM, an unusually broad window. No scheduler exists to validate. |
| README: follow-up scheduling | Partial | Webhook stores `next_followup_date`; no scheduler makes a follow-up call (`app/db.py`). |
| README: recording URL shown when available | Partial | UI supports audio; webhook only reads `recording_url`, field mapping from a real Bolna payload is unverified (`app/main.py`, `frontend/src/App.tsx`). |

## Requested flow trace

| Hop | Exists in code? | Covered by test? | Evidence / result |
|---|---|---|---|
| Shopkeeper triggers call | Yes | No end-to-end test | `POST /calls/trigger`; requires auth, open calling window, balance, attempt allowance, and Bolna credentials. |
| Backend calls Bolna | Yes | No | `httpx.AsyncClient.post` to Bolna; no call was made during this audit. |
| Bolna webhook arrives/authenticates | Yes | Partly | `POST /webhook/call-ended`; existing `tests/test_reliability.py` covers wrong secret. |
| Webhook duplicate ignored | Yes | Yes, mocked | Existing test mocks event registration and asserts duplicate response. |
| Transcript saved | Yes | No | Completed event saves transcript (`app/db.py`); existing tests do not cover persistence path. |
| Extraction runs | Sarvam: no; webhook extraction: yes | Schema unit coverage only | `app/sarvam.py` is not imported by `app/main.py`; webhook parses Bolna `extracted_data`. |
| Promise validated and saved | Yes | Partial | Pure validation boundary tested; no route/database integration test. |
| Follow-up scheduled for promise date | Date stored only | No | `next_followup_date` saved, no scheduler/queue exists. |
| Follow-up call made on promise date in IST/window | No | No | No scheduler. Manual trigger checks IST window only. |
| Mark paid | Yes | Partial | Route and mocked DB response covered by `tests/test_customer_routes.py`; no Postgres integration. |

## Commands and verification

| Command/action | Result |
|---|---|
| `npm.cmd run build` in `frontend/` | PASS; TypeScript and Vite production build completed. |
| Dependency installation | NOT RUN; frontend `node_modules` was already present; no usable Python installation was available for `pip install -r requirements.txt`. |
| Python unit suite using `.venv` | BLOCKED; virtual environment references missing `C:\Users\rs620\AppData\Local\Programs\Python\Python311\python.exe`. No Python installation is registered with `py -0p`. |
| `psql`/`postgres`/`docker` discovery | BLOCKED; no command available to provision a throwaway PostgreSQL instance. |
| Fresh schema application and API server startup | NOT RUN; PostgreSQL and a usable Python runtime are unavailable. `schema.sql` exists and is the schema source. |
| Endpoint requests / route auth requests | NOT RUN; API could not be started. Existing tests are unit/mock tests, not the requested full endpoint suite. |
| Provider calls | NOT RUN; no real Bolna or LLM calls were made. |
| Secret inspection | NOT performed; `.env` was not read or printed. |

## Ranked gaps

### Blocks the demo

1. No usable Python installation or local PostgreSQL runtime in the audit environment; therefore the API, DB-backed endpoints, fresh schema, and auth behavior could not be demonstrated here. Estimate: 30–60 minutes once Python/Postgres are available.
2. The agent manual has no good-time question or recording notice, and the repo cannot prove that the manual is loaded into the configured Bolna agent. Estimate: 1–2 hours to update, configure, and verify without dialing a customer.

### Weakens the pitch

1. Automatic promise-date follow-up is absent; today dates are stored/displayed only. Estimate: 1–2 days for a persistent, timezone-aware scheduler, locking, retries, and safe-window checks.
2. Sarvam extraction is not wired to webhook processing; extraction currently depends on Bolna `extracted_data`. Estimate: 0.5–1 day to connect it with timeouts, fallbacks, and mocked tests.
3. README claims were stale (Claude, APScheduler, Streamlit, Telegram, hosting, and route mismatch); tech-stack table and endpoint summary corrected in README.
4. No automated endpoint-level tests cover health, list calls/customers, webhook persistence, call trigger safety, or non-loopback demo login. Estimate: 0.5–1 day after a runnable test environment exists.

### Nice to have

1. Add deployment configuration and operator setup verification. Estimate: 0.5–1 day.
2. Add Telegram summary and retention worker. Estimate: 1–2 days.
3. Confirm real provider recording URL field mapping and revise calling-hours default to a narrower shop-safe period. Estimate: 1–2 hours plus provider payload sample.

## Demo script that matches current code

1. Start a local PostgreSQL database, apply `schema.sql`, configure local-only demo auth, set a shopkeeper phone, and start FastAPI. Keep Bolna credentials absent unless using a mocked transport.
2. Open the dashboard at `http://127.0.0.1:8000/`, use the six-digit local demo login, add a customer with a test phone and a non-zero balance.
3. Show the customer list, dashboard summary/follow-ups, and profile; mark the test customer paid and show the balance/status update.
4. For a call-flow walkthrough without placing a real call, use mocked `httpx.AsyncClient` and mocked database functions in tests to return a synthetic Bolna execution ID. POST a synthetic completed webhook with transcript and strict `extracted_data`, then show the recorded call and promise date.
5. Explain that automatic calling on the promise date is not implemented. Do not use a real customer number or real provider credentials in the demo.

The API/database portion of this script was not executable in this environment, so it is a code-based script pending a usable Python/Postgres setup.
