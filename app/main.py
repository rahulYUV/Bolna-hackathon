from fastapi import FastAPI, HTTPException

from app import db

app = FastAPI(title="Hisaab")


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