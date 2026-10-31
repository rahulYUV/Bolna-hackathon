import asyncio
import httpx
import ipaddress
import logging
import math
import json
from contextlib import asynccontextmanager
from pathlib import Path
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urljoin, urlsplit
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, ValidationError
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask
from app import db
from app.config import (
    BOLNA_API_KEY,
    BOLNA_AGENT_ID,
    BOLNA_WEBHOOK_ALLOWED_IPS,
    BOLNA_WEBHOOK_SECRET,
    CALL_TRIGGER_COOLDOWN_MINUTES,
    MAX_CALL_ATTEMPTS,
    CUSTOMER_DATA_RETENTION_DAYS,
    DEMO_AUTH_BYPASS,
    SHOPKEEPER_PHONE,
    SHOP_NAME,
    SHOP_TYPE,
    SHOP_LOCATION,
    SHOP_LANGUAGE,
    SHOP_CALLING_HOURS,
    SUPABASE_ANON_KEY,
    SUPABASE_URL,
)
from app.reliability import (
    bolna_status_to_state,
    constant_time_equal,
    parse_extraction,
    validate_promise,
)

logger = logging.getLogger(__name__)
INDIA_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="IST")
STATIC_DIR = Path(__file__).parent / "static"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
WEBHOOK_PAYLOAD_PATH = PROJECT_ROOT / "last_webhook_payload.json"
EXECUTION_PAYLOAD_PATH = PROJECT_ROOT / "last_execution_payload.json"
PHONE_NUMBER_PATTERN = re.compile(r"(?<!\w)(?:\+?91[\s().-]*)?[6-9](?:[\s().-]*\d){9}(?!\w)")
SENSITIVE_FIELD_PATTERN = re.compile(
    r"(?:api[-_]?key|secret|auth|token|password|credential)", re.IGNORECASE
)


async def retention_cleanup_loop():
    while True:
        try:
            await asyncio.to_thread(db.purge_expired_call_data, CUSTOMER_DATA_RETENTION_DAYS)
            expires_before = time.time() - max(1, CUSTOMER_DATA_RETENTION_DAYS) * 24 * 60 * 60
            for payload_path in (WEBHOOK_PAYLOAD_PATH, EXECUTION_PAYLOAD_PATH):
                if payload_path.exists() and payload_path.stat().st_mtime < expires_before:
                    payload_path.unlink()
        except Exception:
            logger.exception("Call data retention cleanup failed")
            await asyncio.sleep(5 * 60)
            continue
        await asyncio.sleep(24 * 60 * 60)


@asynccontextmanager
async def lifespan(_app):
    cleanup_task = asyncio.create_task(retention_cleanup_loop())
    try:
        yield
    finally:
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass


app = FastAPI(title="Hisaab", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
DEMO_SESSIONS: dict[str, dict[str, object]] = {}


def redact_webhook_payload(value, *, field_name: str = "", inside_secret: bool = False):
    """Redact sensitive webhook values while preserving the payload structure."""
    if isinstance(value, dict):
        return {
            key: redact_webhook_payload(
                child,
                field_name=str(key),
                inside_secret=inside_secret or bool(SENSITIVE_FIELD_PATTERN.search(str(key))),
            )
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [
            redact_webhook_payload(child, field_name=field_name, inside_secret=inside_secret)
            for child in value
        ]
    if inside_secret:
        return "REDACTED"
    normalized_field = re.sub(r"[^a-z]", "", field_name.lower())
    is_phone_field = any(part in normalized_field for part in ("phone", "mobile", "telephone")) or normalized_field in {
        "fromnumber", "tonumber", "usernumber", "agentnumber", "callernumber", "recipientnumber"
    }
    if is_phone_field:
        return "+91XXXXXXXXXX" if value is not None and str(value).strip() else value
    if not isinstance(value, str):
        return value

    if "recording" in normalized_field and "url" in normalized_field:
        value = value.split("?", 1)[0]
    return PHONE_NUMBER_PATTERN.sub("+91XXXXXXXXXX", value)


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


class CustomerCreateRequest(BaseModel):
    name: str
    phone: str
    amount_due: float


class CustomerUpdateRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    amount_due: float | None = None


class PaymentRequest(BaseModel):
    amount: float
    method: str | None = None


def normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", phone)
    if digits.startswith("0091"):
        digits = digits[2:]
    if digits.startswith("91") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) != 10 or digits[0] not in "6789":
        raise ValueError("Enter a valid Indian mobile number.")
    return f"+91{digits}"


def validate_customer_payload(name: str, phone: str, amount_due: float) -> tuple[str, str, float]:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise HTTPException(status_code=422, detail="Customer name is required.")
    if not math.isfinite(amount_due) or amount_due < 0:
        raise HTTPException(status_code=422, detail="Amount due must be a non-negative number.")
    try:
        normalized_phone = normalize_phone(phone)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return cleaned_name, normalized_phone, amount_due


def calling_hours_open() -> bool:
    """Keep outbound calls inside the configured local shop hours."""
    try:
        start_text, end_text = SHOP_CALLING_HOURS.split("-", 1)
        start = datetime.strptime(start_text.strip(), "%I:%M %p").time()
        end = datetime.strptime(end_text.strip(), "%I:%M %p").time()
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="SHOP_CALLING_HOURS must use '10:00 AM - 7:00 PM' format.") from exc
    # India does not observe daylight saving time, so a fixed UTC+05:30 offset
    # avoids relying on an external timezone database (missing on some Windows installs).
    now = datetime.now(INDIA_TIMEZONE).time()
    if start <= end:
        return start <= now <= end
    # An end time earlier than the start time means the window crosses midnight.
    return now >= start or now <= end


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
        raise HTTPException(status_code=401, detail="Your demo session has expired. Please log in again.")

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


@app.post("/customers", status_code=201)
def create_customer(payload: CustomerCreateRequest, _shopkeeper: dict = Depends(require_shopkeeper)):
    name, phone, amount_due = validate_customer_payload(payload.name, payload.phone, payload.amount_due)
    try:
        return db.create_customer(name, phone, amount_due)
    except db.DuplicatePhoneError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.patch("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    payload: CustomerUpdateRequest,
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    current = db.get_customer(customer_id)
    if not current:
        raise HTTPException(status_code=404, detail="Customer not found")
    name = payload.name if payload.name is not None else str(current["name"])
    phone = payload.phone if payload.phone is not None else str(current["phone"])
    amount_due = payload.amount_due if payload.amount_due is not None else float(current["amount_due"])
    name, phone, amount_due = validate_customer_payload(name, phone, amount_due)
    try:
        return db.update_customer(customer_id, name, phone, amount_due)
    except db.DuplicatePhoneError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/customers/{customer_id}/mark-paid")
def mark_customer_paid(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    try:
        customer = db.set_customer_paid(customer_id, paid=True)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return customer


@app.post("/customers/{customer_id}/mark-unpaid")
def mark_customer_unpaid(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    try:
        customer = db.set_customer_paid(customer_id, paid=False)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return customer


@app.post("/customers/{customer_id}/payment")
def record_payment(
    customer_id: int,
    payload: PaymentRequest,
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    if not math.isfinite(payload.amount) or payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Payment amount must be greater than zero.")
    try:
        return db.record_payment(customer_id, payload.amount, payload.method)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/customers/{customer_id}/payments")
def create_payment(
    customer_id: int,
    payload: PaymentRequest,
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    if not math.isfinite(payload.amount) or payload.amount <= 0:
        raise HTTPException(status_code=422, detail="Payment amount must be greater than zero.")
    try:
        return db.record_payment(customer_id, payload.amount, payload.method)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/dashboard/summary")
def dashboard_summary(_shopkeeper: dict = Depends(require_shopkeeper)):
    return db.dashboard_summary()


@app.get("/dashboard/followups")
def dashboard_followups(
    page: int = 1,
    page_size: int = 25,
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid pagination.")
    return db.dashboard_followups(page, page_size)


@app.post("/customers/{customer_id}/do-not-call")
def set_do_not_call(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    try:
        return db.set_do_not_call(customer_id, True)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/customers/{customer_id}/allow-calls")
def allow_calls(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    try:
        return db.set_do_not_call(customer_id, False)
    except db.CustomerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/shop-profile")
def shop_profile(_shopkeeper: dict = Depends(require_shopkeeper)):
    """Return the configured profile for the single-shop MVP."""
    return {
        "name": SHOP_NAME,
        "type": SHOP_TYPE,
        "location": SHOP_LOCATION,
        "language": SHOP_LANGUAGE,
        "calling_hours": SHOP_CALLING_HOURS,
        "validation_stage": "Initial MVP validation with one shopkeeper",
    }


@app.get("/calls")
def calls(_shopkeeper: dict = Depends(require_shopkeeper)):
    return db.list_calls()


@app.post("/calls/{call_id}/sync")
async def sync_call_from_bolna(call_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    """Fetch call details from Bolna when a webhook was unavailable or incomplete."""
    call = db.get_call_by_id(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found.")
    execution_id = call.get("bolna_execution_id")
    if not execution_id:
        raise HTTPException(status_code=409, detail="This call has no Bolna execution ID to sync.")
    if not BOLNA_API_KEY:
        raise HTTPException(status_code=503, detail="Bolna API access is not configured.")

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                f"https://api.bolna.ai/executions/{quote(str(execution_id), safe='')}",
                headers={"Authorization": f"Bearer {BOLNA_API_KEY}"},
            )
    except httpx.RequestError as exc:
        logger.warning("Bolna execution lookup failed for call %s: %s", call_id, exc)
        raise HTTPException(status_code=502, detail="Could not retrieve call details from Bolna.") from exc

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Bolna does not have this execution.")
    if response.status_code >= 400:
        logger.warning("Bolna execution lookup returned HTTP %s for call %s", response.status_code, call_id)
        raise HTTPException(status_code=502, detail="Bolna could not return this call's details.")
    try:
        execution = response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Bolna returned invalid call details.") from exc
    call_data = execution.get("data", execution) if isinstance(execution, dict) else None
    if not isinstance(call_data, dict):
        raise HTTPException(status_code=502, detail="Bolna returned invalid call details.")

    artifacts = bolna_call_artifacts(call_data)
    db.save_call_details(
        call_id,
        duration_seconds=artifacts["duration_seconds"],
        agent_phone=str(artifacts["agent_phone"]) if artifacts["agent_phone"] else None,
        called_at=artifacts["called_at"],
    )
    db.save_call_content(
        call_id,
        transcript=str(artifacts["transcript"]) if artifacts["transcript"] is not None else None,
        summary=str(artifacts["summary"]) if artifacts["summary"] is not None else None,
        recording_url=str(artifacts["recording_url"]) if artifacts["recording_url"] is not None else None,
    )

    provider_status = str(call_data.get("status") or "")
    if provider_status:
        target_state = bolna_status_to_state(provider_status)
        if target_state != call["status"]:
            try:
                db.transition_call(call_id, target_state, f"Bolna execution sync status {provider_status}", execution_id=str(execution_id))
            except db.InvalidTransitionError:
                logger.info("Kept call %s in %s after out-of-order Bolna sync status %s", call_id, call["status"], provider_status)

    return db.get_call_by_id(call_id)


@app.get("/customers/{customer_id}")
def customer(customer_id: int, _shopkeeper: dict = Depends(require_shopkeeper)):
    row = db.get_customer(customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@app.post("/calls/trigger")
async def trigger_call(
    payload: CallTriggerRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    """Triggers an outbound Bolna voice call to a customer for udhaar collection."""
    db.ensure_customer_features()
    customer = db.get_customer(payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    if not calling_hours_open():
        raise HTTPException(status_code=409, detail=f"Calls are allowed only between {SHOP_CALLING_HOURS} (India time).")
    if customer.get("do_not_call"):
        raise HTTPException(status_code=409, detail="This customer has asked not to receive calls.")
    if str(customer.get("status", "")).lower() == "paid" or float(customer["amount_due"]) <= 0:
        raise HTTPException(status_code=409, detail="This customer has no unpaid balance.")
    attempts = db.count_call_attempts(customer["id"])
    if attempts >= MAX_CALL_ATTEMPTS:
        raise HTTPException(status_code=409, detail=f"Maximum call attempts reached ({MAX_CALL_ATTEMPTS}).")

    if not BOLNA_API_KEY or not BOLNA_AGENT_ID:
        raise HTTPException(status_code=500, detail="Bolna API key or Agent ID is not configured in environment variables.")
    try:
        call = db.create_queued_call(customer["id"], CALL_TRIGGER_COOLDOWN_MINUTES, idempotency_key)
    except (ValueError, db.CustomerNotFoundError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if call.get("idempotent_replay"):
        return {
            "status": "accepted",
            "message": f"Call request already accepted for {customer['name']}",
            "call_id": call["id"],
        }

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
                db.transition_call(call["id"], "failed", "Bolna rejected outbound call", failure_reason=response.text[:500])
                raise HTTPException(status_code=response.status_code, detail=f"Bolna API error: {response.text}")
            
            bolna_data = response.json()
        except httpx.RequestError as exc:
            db.transition_call(call["id"], "failed", "Bolna request failed", failure_reason=str(exc))
            raise HTTPException(status_code=500, detail=f"Failed to connect to Bolna API: {exc}")

    execution_id = bolna_data.get("id") or bolna_data.get("execution_id")
    db.set_call_initiated(call["id"], str(execution_id) if execution_id else None)
    return {
        "status": "success",
        "message": f"Call triggered successfully for {customer['name']}",
        "bolna_response": bolna_data
    }


def authenticate_bolna_webhook(request: Request) -> None:
    """Bolna documents IP allowlisting, not webhook signatures; secret supports local development."""
    client_ip = request.client.host if request.client else ""
    supplied_secret = request.headers.get("X-Bolna-Webhook-Secret")
    if BOLNA_WEBHOOK_SECRET:
        if not constant_time_equal(supplied_secret, BOLNA_WEBHOOK_SECRET):
            logger.warning("Rejected Bolna webhook authentication from %s", client_ip)
            raise HTTPException(status_code=401, detail="Webhook authentication failed.")
        return
    if client_ip not in BOLNA_WEBHOOK_ALLOWED_IPS:
        logger.warning("Rejected Bolna webhook source %s", client_ip)
        raise HTTPException(status_code=401, detail="Webhook source is not allowed.")


def provider_datetime(value) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed


def bolna_call_artifacts(call_data: dict) -> dict[str, object]:
    telephony_data = call_data.get("telephony_data")
    if not isinstance(telephony_data, dict):
        telephony_data = {}
    duration_value = call_data.get("conversation_duration")
    if duration_value is None:
        duration_value = telephony_data.get("duration")
    try:
        duration_seconds = float(duration_value) if duration_value is not None else None
        if duration_seconds is not None and (not math.isfinite(duration_seconds) or duration_seconds < 0):
            duration_seconds = None
    except (TypeError, ValueError):
        duration_seconds = None

    extracted_data = call_data.get("extracted_data") or {}
    summary = call_data.get("summary")
    if not summary and isinstance(extracted_data, dict):
        general = extracted_data.get("General")
        summary_data = general.get("Call Summary") if isinstance(general, dict) else None
        if isinstance(summary_data, dict):
            summary = summary_data.get("subjective")

    return {
        "duration_seconds": duration_seconds,
        "agent_phone": call_data.get("agent_number") or telephony_data.get("from_number"),
        "called_at": provider_datetime(call_data.get("initiated_at") or call_data.get("created_at")),
        "recording_url": telephony_data.get("recording_url") or call_data.get("recording_url"),
        "transcript": call_data.get("transcript"),
        "summary": summary,
        "extracted_data": extracted_data,
    }


@app.post("/webhook/call-ended")
async def call_ended_webhook(request: Request, payload: dict):
    """Persist an authenticated, idempotent Bolna execution event."""
    authenticate_bolna_webhook(request)
    try:
        redacted_payload = redact_webhook_payload(payload)
        WEBHOOK_PAYLOAD_PATH.write_text(
            json.dumps(redacted_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        logger.exception("Could not save redacted Bolna webhook payload")

    call_data = payload.get("data", payload)
    event_id = str(payload.get("id") or call_data.get("id") or "")
    status_value = str(call_data.get("status") or payload.get("status") or "completed")
    if not event_id:
        raise HTTPException(status_code=400, detail="Webhook is missing Bolna execution id.")
    provider_event_id = f"{event_id}:{status_value}"
    if not db.register_webhook_event(provider_event_id, payload):
        return {"status": "ok", "duplicate": True}

    try:
        call = db.get_call_by_execution(event_id)
        if not call and call_data.get("recipient_phone_number"):
            phone = normalize_phone(str(call_data["recipient_phone_number"]))
            with db.get_cursor() as cur:
                cur.execute("SELECT id FROM customers WHERE phone = %s", (phone,))
                customer = cur.fetchone()
            if customer:
                call = db.create_queued_call(customer["id"], 0)
                db.set_call_initiated(call["id"], event_id)
        if not call:
            db.finish_webhook_event(provider_event_id, error="No matching call")
            return {"status": "ignored", "message": "No matching call found."}

        target_state = bolna_status_to_state(status_value)
        if target_state != call["status"]:
            try:
                db.transition_call(call["id"], target_state, f"Bolna webhook status {status_value}", execution_id=event_id)
            except db.InvalidTransitionError:
                logger.warning("Ignored out-of-order Bolna status %s for call %s", status_value, call["id"])

        artifacts = bolna_call_artifacts(call_data)
        db.save_call_details(
            call["id"],
            duration_seconds=artifacts["duration_seconds"],
            agent_phone=str(artifacts["agent_phone"]) if artifacts["agent_phone"] else None,
            called_at=artifacts["called_at"],
        )

        if target_state == "completed":
            customer = db.get_customer(call["customer_id"])
            recording_url = artifacts["recording_url"]
            extracted_data = artifacts["extracted_data"]
            call_summary = artifacts["summary"]
            extracted = None
            try:
                extracted = parse_extraction(extracted_data)
            except (ValidationError, json.JSONDecodeError, TypeError, ValueError):
                extracted = None
            if extracted:
                date_valid, amount_valid = validate_promise(
                    extracted.promise_date,
                    extracted.promise_amount,
                    float(customer["amount_due"]),
                    today=datetime.now(INDIA_TIMEZONE).date(),
                )
                db.save_completed_call(
                    call["id"],
                    transcript=str(artifacts["transcript"] or ""),
                    summary=call_summary,
                    recording_url=recording_url,
                    outcome="disputed" if extracted.dispute else ("promised" if date_valid and amount_valid else "needs_review"),
                    promise_date=extracted.promise_date if date_valid else None,
                    promise_amount=extracted.promise_amount if amount_valid else None,
                    dispute=extracted.dispute,
                    do_not_call=extracted.customer_requested_no_calls,
                )
            else:
                db.save_unverified_call(
                    call["id"],
                    transcript=str(artifacts["transcript"] or ""),
                    summary=call_summary,
                    recording_url=recording_url,
                )
        db.finish_webhook_event(provider_event_id)
        return {"status": "success", "message": "Webhook processed"}
    except Exception as exc:
        db.finish_webhook_event(provider_event_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Webhook error: {str(exc)}")


async def close_recording_stream(response: httpx.Response, client: httpx.AsyncClient):
    await response.aclose()
    await client.aclose()


def validate_recording_host(url: str) -> str:
    try:
        parsed = urlsplit(url)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Bolna returned an invalid recording URL.") from exc
    if parsed.scheme != "https" or port not in (None, 443) or not (host == "api.bolna.ai" or host.endswith(".amazonaws.com")):
        raise HTTPException(status_code=502, detail="Bolna returned an unsupported recording URL.")
    return host


@app.get("/calls/{call_id}/recording")
async def stream_call_recording(
    call_id: int,
    range_header: str | None = Header(default=None, alias="Range"),
    _shopkeeper: dict = Depends(require_shopkeeper),
):
    recording_url = db.get_call_recording_url(call_id)
    if not recording_url:
        raise HTTPException(status_code=404, detail="Call recording is unavailable or has expired.")

    client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=None), follow_redirects=False)
    current_url = str(recording_url)
    upstream = None
    try:
        for _ in range(4):
            host = validate_recording_host(current_url)
            headers = {"Range": range_header} if range_header else {}
            if host == "api.bolna.ai":
                if not BOLNA_API_KEY:
                    raise HTTPException(status_code=503, detail="Bolna recording access is not configured.")
                headers["Authorization"] = f"Bearer {BOLNA_API_KEY}"
            request = client.build_request("GET", current_url, headers=headers)
            upstream = await client.send(request, stream=True)
            if upstream.status_code not in {301, 302, 303, 307, 308}:
                break
            location = upstream.headers.get("location")
            await upstream.aclose()
            upstream = None
            if not location:
                raise HTTPException(status_code=502, detail="Bolna recording redirect had no destination.")
            current_url = urljoin(current_url, location)
        else:
            raise HTTPException(status_code=502, detail="Bolna recording redirected too many times.")

        if upstream.status_code >= 400:
            status_code = 404 if upstream.status_code == 404 else 502
            await upstream.aclose()
            upstream = None
            raise HTTPException(status_code=status_code, detail="Bolna recording could not be retrieved.")

        response_headers = {"Cache-Control": "private, no-store"}
        for header in ("content-length", "content-range", "accept-ranges"):
            if header in upstream.headers:
                response_headers[header.title()] = upstream.headers[header]
        return StreamingResponse(
            upstream.aiter_bytes(),
            status_code=upstream.status_code,
            media_type=upstream.headers.get("content-type", "audio/mpeg"),
            headers=response_headers,
            background=BackgroundTask(close_recording_stream, upstream, client),
        )
    except HTTPException:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        raise
    except httpx.RequestError as exc:
        if upstream is not None:
            await upstream.aclose()
        await client.aclose()
        logger.warning("Bolna recording request failed for call %s: %s", call_id, exc)
        raise HTTPException(status_code=502, detail="Bolna recording could not be retrieved.") from exc
