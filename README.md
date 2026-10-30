# Hisaab: 
 
Built for the Bolna Buildathon (Bolna is YC F25)
 
 Hisaab is a voice agent that politely calls kirana customers in Hindi/Hinglish to collect udhaar, logs their promises, and follows up until the shopkeeper marks it paid.

## How to run

### 1. Set up Python

Python 3.10 or newer is recommended. From the project root, create and activate a virtual environment:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

On macOS or Linux, activate it with `source .venv/bin/activate` instead.

Install the project dependencies:

```bash
pip install -r requirements.txt
```

### 2. Configure environment variables

Create a `.env` file in the project root (keep it private) and set:

```dotenv
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DATABASE
BOLNA_API_KEY=your_bolna_api_key
BOLNA_AGENT_ID=your_bolna_agent_id
SARVAM_API_KEY=your_sarvam_api_key
```

`DATABASE_URL` is required when the application starts. Bolna credentials are required to trigger calls. The current call-ended webhook stores the transcript and outcome sent by Bolna; Sarvam extraction is available as a separate module and is not yet wired into that webhook.

The database must be reachable and have the tables expected by the app, including `customers` and `calls`. This repository does not currently include a schema or migration script.

### 3. Start the API

From the project root, run:

```bash
uvicorn app.main:app --reload
```

The API will be available at <http://127.0.0.1:8000>. Check `GET /health` for API and database connectivity, and open <http://127.0.0.1:8000/docs> to inspect and try the endpoints.

To trigger a demo call, use `POST /calls/trigger` with a customer ID that exists in the database:

```json
{"customer_id": 1}
```

Only trigger calls to yourself or teammates during a demo.
 
## The problem
 
The real problem isn't record-keeping. It's getting paid without damaging the relationship.
 
- **Money is stuck.** Thin margins, little working capital. Every unpaid Rs 500 is cash the shop can't use to restock.
- **Customers are neighbors.** Asking "paisa kab doge?" feels rude, so many shopkeepers avoid asking and the amount grows.
- **Udhaar is how they compete.** They can't stop giving credit, so they need a way to collect without confrontation.
- **Follow-up is inconsistent.** Reminders happen randomly, when the shopkeeper remembers.
## Why voice (vs SMS/WhatsApp from Khatabook, OkCredit)
 
SMS can't handle replies. A call can: "Friday ko dunga", "abhi paise nahi hain", "amount galat hai". The reply becomes structured data and the agent follows up on the promised date.
 

 
## Agent rules
 
- Never invent amounts. Use only the confirmed ledger value passed in as a variable.
- Polite, non-threatening tone. No pressure, no late-night calls.
- Keep replies to one or two sentences to reduce latency.
- Escalate disputes instead of arguing.
- Demo calls go only to my own or teammates' phones.
## Tech stack
 
| Part || Choice ||
|---|---|
| Database | Postgres (Supabase or plain Postgres) |
| Backend | Python FastAPI |
| Voice agent | Bolna (Hindi/Hinglish) |
| Outcome extraction | LLM (Claude API) |
| Scheduler | APScheduler (recalls, daily summary) |
| Dashboard | Streamlit |
| Daily summary | Telegram bot |
| Hosting | Render/Railway, ngrok in development |
 
**Tables:** `customers` (id, name, phone, amount_due, status, promise_date), `calls` (id, customer_id, called_at, transcript, outcome, promise_date, notes)
 
**Endpoints:** `POST /calls/trigger`, `POST /webhook/call-ended`, `POST /customers/{id}/mark-paid`, `GET /summary/today`
 
Check Bolna's docs for the exact call-trigger request and webhook payload before writing the client.

## Shopkeeper dashboard

Start the FastAPI app as above and open <http://127.0.0.1:8000/>. The dashboard is served by the API and reads the complete customer list from `GET /customers`, recorded calls from `GET /calls`, and connection state from `GET /health`. Use the customer table to search and filter balances; **Call gently** asks for confirmation before sending `POST /calls/trigger` with that customer's ID. A call appears in recent activity after Bolna sends the call-ended webhook.

`GET /calls` returns recorded call fields (`id`, `customer_id`, `customer_name`, `phone`, `called_at`, `outcome`, `promise_date`, `notes`, and `transcript`) newest first. It uses the `calls` and `customers` tables described above.

The React + TypeScript source is in `frontend/`. Run `npm install` and `npm run dev` there to develop with Vite at <http://127.0.0.1:5173/> (keep FastAPI running at port 8000). Run `npm run build` to compile the frontend into `app/static`, which FastAPI serves at <http://127.0.0.1:8000/>.

### Shopkeeper-only Supabase login

The demo home page allows one shopkeeper to sign in. Public signup and customer login are disabled for this demo. With `DEMO_AUTH_BYPASS=true`, the local demo accepts any six-digit entry for the configured owner phone and issues an in-memory 8-hour session. The bypass endpoint only accepts requests from the same computer (`localhost`/loopback); protected customer and call routes still require that issued session and the configured `SHOPKEEPER_PHONE`.

To use real Supabase OTP instead, set `DEMO_AUTH_BYPASS=false`. The frontend requests and verifies OTPs with Supabase Auth; FastAPI validates the Supabase session and restricts protected routes to the configured owner phone.

1. Copy `.env.example` to `.env` and fill in `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SHOPKEEPER_PHONE`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_ANON_KEY`. Use the Supabase **public anon/publishable key** in the frontend; never use a service-role key there. Use the same project URL and public key for the backend and frontend.
2. In Supabase Authentication, enable Phone sign-in, allow phone signups, and configure an SMS provider. With real OTP enabled, the first OTP request creates the owner Auth user only after FastAPI confirms the number matches `SHOPKEEPER_PHONE`; any other number is rejected before Supabase is called. The number must match in international format (for example, `+91...`).
3. For a no-SMS demo, configure a Supabase test phone number and fixed OTP for that owner. Supabase still requires an SMS provider to be configured, but does not send a message for a test phone. Treat the fixed code as demo-only.
4. Restart FastAPI and Vite after editing `.env`; Vite embeds its `VITE_` settings at build time. Then run `npm run build` for the FastAPI-served version.

`GET /health`, `GET /auth/demo-mode`, and `POST /auth/check-shopkeeper-phone` are public; the phone-check endpoint only accepts the configured owner number. `POST /auth/demo-login` is available only with `DEMO_AUTH_BYPASS=true` and from localhost. `GET /auth/session`, `GET /customers`, `GET /customers/{id}`, `GET /calls`, and `POST /calls/trigger` require a valid owner session.
 
