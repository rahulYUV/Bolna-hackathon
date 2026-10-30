import httpx
import ipaddress
from pathlib import Path
import re
import secrets
import time
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app import db
from app.config import BOLNA_API_KEY, BOLNA_AGENT_ID, DEMO_AUTH_BYPASS, SHOPKEEPER_PHONE, SUPABASE_ANON_KEY, SUPABASE_URL

app = FastAPI(title="Hisaab")
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
DEMO_SESSIONS: dict[str, dict[str, object]] = {}


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")

class CallTriggerRequest(BaseModel):
    customer_id: int


class ShopkeeperPhoneCheckRequest(BaseModel):
    phone: str


class DemoLoginRequest(BaseModel):
    phone: str
    otp: str


def normalize_phone(phone: str) -> str:
    return re.sub(r"\D", "", phone)


async def require_shopkeeper(authorization: str | None = Header(default=None)) -> dict:
    """Validate the Supabase session and restrict this demo to its shop owner."""
    if not SHOPKEEPER_PHONE:
        raise HTTPException(status_code=503, detail="Shopkeeper authentication is not configured.")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Please log in to continue.")

    bearer_token = authorization.split(" ", 1)[1].strip()
    if DEMO_AUTH_BYPASS:
        demo_session = DEMO_SESSIONS.get(bearer_token)
        if demo_session:
            if float(demo_session["expires_at"]) > time.time() and normalize_phone(str(demo_session["phone"])) == normalize_phone(SHOPKEEPER_PHONE):
                return {"phone": demo_session["phone"], "demo": True}
            DEMO_SESSIONS.pop(bearer_token, None)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        raise HTTPException(status_code=503, detail="Shopkeeper authentication is not configured.")

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.get(
                f"{SUPABASE_URL.rstrip('/')}/auth/v1/user",
                headers={"apikey": SUPABASE_ANON_KEY, "Authorization": authorization},
            )
    except httpx.RequestError:
        raise HTTPException(status_code=503, detail="Could not verify the Supabase session.")

    if response.status_code == 401:
        raise HTTPException(status_code=401, detail="Your session has expired. Please log in again.")
    if response.status_code >= 400:
        raise HTTPException(status_code=503, detail="Could not verify the Supabase session.")

    user = response.json()
    if normalize_phone(user.get("phone") or "") != normalize_phone(SHOPKEEPER_PHONE):
        raise HTTPException(status_code=403, detail="This demo account is limited to the shop owner.")
    return user


@app.get("/health")
def health():
    """Checks that the API is up and can reach Postgres."""
    try:
        with db.get_cursor() as cur:
            cur.execute("SELECT 1 AS ok")
            cur.fetchone()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
    return {"status": "ok", "database": "connected"}


@app.get("/auth/session")
async def auth_session(_shopkeeper: dict = Depends(require_shopkeeper)):
    """Confirms that the current Supabase user is the configured shop owner."""
    return {"role": "shopkeeper"}


@app.post("/auth/check-shopkeeper-phone")
def check_shopkeeper_phone(payload: ShopkeeperPhoneCheckRequest):
    """Only allow the configured owner's number to request an OTP or create an Auth user."""
    if not SHOPKEEPER_PHONE:
        raise HTTPException(status_code=503, detail="Shopkeeper authentication is not configured.")
    if normalize_phone(payload.phone) != normalize_phone(SHOPKEEPER_PHONE):
        raise HTTPException(status_code=403, detail="This demo only allows the configured shopkeeper phone number.")
    return {"allowed": True}


@app.get("/auth/demo-mode")
def auth_demo_mode():
    return {"enabled": DEMO_AUTH_BYPASS}


@app.post("/auth/demo-login")
def auth_demo_login(payload: DemoLoginRequest, request: Request):
    """Issue a short-lived local demo session for the configured shopkeeper."""
    if not DEMO_AUTH_BYPASS:
        raise HTTPException(status_code=404, detail="Demo login is disabled.")
    client_host = request.client.host if request.client else ""
    try:
        if not ipaddress.ip_address(client_host).is_loopback:
            raise HTTPException(status_code=403, detail="Demo login is only available from this computer.")
    except ValueError:
        raise HTTPException(status_code=403, detail="Demo login is only available from this computer.")
    if not SHOPKEEPER_PHONE or normalize_phone(payload.phone) != normalize_phone(SHOPKEEPER_PHONE):
        raise HTTPException(status_code=403, detail="This demo only allows the configured shopkeeper phone number.")
    if not re.fullmatch(r"\d{6}", payload.otp):
        raise HTTPException(status_code=400, detail="Enter any six digits to continue in demo mode.")

    now = time.time()
    expired_tokens = [token for token, session in DEMO_SESSIONS.items() if float(session["expires_at"]) <= now]
    for token in expired_tokens:
        DEMO_SESSIONS.pop(token, None)

    token = secrets.token_urlsafe(32)
    expires_at = now + 8 * 60 * 60
    DEMO_SESSIONS[token] = {"phone": SHOPKEEPER_PHONE, "expires_at": expires_at}
    return {"access_token": token, "token_type": "bearer", "expires_in": 8 * 60 * 60}


@app.get("/customers")
def customers(_shopkeeper: dict = Depends(require_shopkeeper)):
    return db.list_customers()


@app.get("/calls")
def calls(_shopkeeper: dict = Depends(require_shopkeeper)):
    return db.list_calls()


@app.get("/customers/{customer_id}")
def customer(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    row = db.get_customer(customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@app.post("/calls/trigger")
async def trigger_call(payload: CallTriggerRequest, _shopkeeper: dict = Depends(require_shopkeeper)):
    """Triggers an outbound Bolna voice call to a customer for udhaar collection."""
    customer = db.get_customer(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    if not BOLNA_API_KEY or not BOLNA_AGENT_ID:
        raise HTTPException(status_code=500, detail="Bolna API key or Agent ID is not configured in environment variables.")

    bolna_url = "https://api.bolna.ai/call"
    headers = {
        "Authorization": f"Bearer {BOLNA_API_KEY}",
        "Content-Type": "application/json"
    }
    
    bolna_payload = {
        "agent_id": BOLNA_AGENT_ID,
        "recipient_phone_number": customer["phone"],
        "user_data": {
            "customer_name": customer["name"],
            "amount_due": str(customer["amount_due"])
        }
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(bolna_url, json=bolna_payload, headers=headers, timeout=30.0)
            if response.status_code >= 400:
                raise HTTPException(status_code=response.status_code, detail=f"Bolna API error: {response.text}")
            
            bolna_data = response.json()
        except httpx.RequestError as exc:
            raise HTTPException(status_code=500, detail=f"Failed to connect to Bolna API: {exc}")

    return {
        "status": "success",
        "message": f"Call triggered successfully for {customer['name']}",
        "bolna_response": bolna_data
    }


@app.post("/webhook/call-ended")
async def call_ended_webhook(payload: dict):
    """Receives call summary, transcript, and outcome from Bolna when a call finishes."""
    try:
        call_data = payload.get("data", payload)
        transcript = call_data.get("transcript", "No transcript available")
        outcome = call_data.get("outcome", "completed")
        customer_phone = call_data.get("recipient_phone_number")
        
        customer_id = None
        if customer_phone:
            with db.get_cursor() as cur:
                cur.execute("SELECT id FROM customers WHERE phone = %s", (customer_phone,))
                row = cur.fetchone()
                if row:
                    customer_id = row["id"]

        if customer_id:
            with db.get_cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO calls (customer_id, transcript, outcome)
                    VALUES (%s, %s, %s)
                    """,
                    (customer_id, str(transcript), str(outcome))
                )
        
        return {"status": "success", "message": "Call log saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook error: {str(e)}")
