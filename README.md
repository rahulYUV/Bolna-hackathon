# Hisaab: 
 
Built for the Bolna Buildathon (Bolna is YC F25)
 
 Hisaab is a voice agent that politely calls kirana customers in Hindi/Hinglish to collect udhaar, logs their promises, and follows up until the shopkeeper marks it paid.
 
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
 
| Part | Choice |
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
 
