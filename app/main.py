import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app import db
from app.config import BOLNA_API_KEY, BOLNA_AGENT_ID

app = FastAPI(title="Hisaab")

class CallTriggerRequest(BaseModel):
    customer_id: int


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


@app.get("/customers")
def customers():
    return db.list_customers()


@app.get("/customers/{customer_id}")
def customer(customer_id: int):
    row = db.get_customer(customer_id)
    if not row:
        raise HTTPException(status_code=404, detail="Customer not found")
    return row


@app.post("/calls/trigger")
async def trigger_call(payload: CallTriggerRequest):
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