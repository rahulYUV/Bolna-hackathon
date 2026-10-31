from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2 import extras
from psycopg2.extras import RealDictCursor

from app.config import DATABASE_URL
from app.reliability import can_transition


class DuplicatePhoneError(Exception):
    """Raised when a customer phone number already exists."""


class CustomerNotFoundError(Exception):
    """Raised when a customer mutation targets a missing customer."""


class InvalidTransitionError(Exception):
    """Raised when a call state transition is not allowed."""


class DuplicateWebhookError(Exception):
    """Raised when a provider event has already been received."""


@contextmanager
def get_cursor():
    """Open a connection, give back a dict cursor, commit on success, roll back on error."""
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def ensure_customer_features():
    """Apply additive columns needed by the customer/payment MVP."""
    with get_cursor() as cur:
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12, 2)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS do_not_call BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS next_followup_date DATE")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS summary TEXT")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed'")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS promise_amount NUMERIC(12, 2)")
        cur.execute("ALTER TABLE customers ADD COLUMN IF NOT EXISTS promise_status TEXT NOT NULL DEFAULT 'pending'")
        for column in ("dispute", "complaint", "opt_out", "early_hangup", "blocked_by_do_not_call"):
            cur.execute(f"ALTER TABLE calls ADD COLUMN IF NOT EXISTS {column} BOOLEAN NOT NULL DEFAULT FALSE")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS payments (
                id BIGSERIAL PRIMARY KEY,
                customer_id BIGINT NOT NULL REFERENCES customers(id),
                amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
                paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                method TEXT,
                source TEXT NOT NULL DEFAULT 'manual',
                related_call_id BIGINT REFERENCES calls(id)
            )
            """
        )


def ensure_reliability_schema():
    with get_cursor() as cur:
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS bolna_execution_id TEXT")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS attempt_number INTEGER NOT NULL DEFAULT 1")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC(10, 2)")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS agent_phone TEXT")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS failure_reason TEXT")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS promise_amount NUMERIC(12, 2)")
        cur.execute("ALTER TABLE calls ADD COLUMN IF NOT EXISTS idempotency_key TEXT")
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS webhook_events (
                id BIGSERIAL PRIMARY KEY,
                provider_event_id TEXT NOT NULL UNIQUE,
                raw_payload JSONB NOT NULL,
                received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                processed_at TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'received',
                error TEXT
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS call_state_audit (
                id BIGSERIAL PRIMARY KEY,
                call_id BIGINT NOT NULL REFERENCES calls(id),
                from_state TEXT,
                to_state TEXT NOT NULL,
                reason TEXT,
                at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )


def list_customers():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, phone, amount_due,
                   CASE WHEN amount_due > 0
                             AND next_followup_date < CURRENT_DATE
                             AND NOT do_not_call
                        THEN 'payment_overdue'
                        ELSE status END AS status,
                   promise_date,
                   do_not_call, next_followup_date
            FROM customers
            ORDER BY id
            """
        )
        return cur.fetchall()


def create_customer(name: str, phone: str, amount_due: float):
    ensure_customer_features()
    with get_cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO customers (name, phone, amount_due, status, paid_amount)
                VALUES (%s, %s, %s, %s, NULL)
                RETURNING id, name, phone, amount_due, status, promise_date
                """,
                (name, phone, amount_due, "pending"),
            )
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicatePhoneError("A customer with this phone number already exists.") from exc
        return cur.fetchone()


def update_customer(customer_id: int, name: str, phone: str, amount_due: float):
    ensure_customer_features()
    with get_cursor() as cur:
        try:
            cur.execute(
                """
                UPDATE customers
                SET name = %s, phone = %s, amount_due = %s,
                    status = CASE WHEN %s <= 0 THEN 'paid' ELSE 'pending' END,
                    promise_date = CASE WHEN %s <= 0 THEN NULL ELSE promise_date END,
                    next_followup_date = CASE WHEN %s <= 0 THEN NULL ELSE next_followup_date END,
                    paid_amount = CASE WHEN %s <= 0 THEN paid_amount ELSE NULL END
                WHERE id = %s
                RETURNING id, name, phone, amount_due, status, promise_date
                """,
                (name, phone, amount_due, amount_due, amount_due, amount_due, amount_due, customer_id),
            )
        except psycopg2.errors.UniqueViolation as exc:
            raise DuplicatePhoneError("A customer with this phone number already exists.") from exc
        customer = cur.fetchone()
        if not customer:
            raise CustomerNotFoundError("Customer not found")
        return customer


def set_customer_paid(customer_id: int, *, paid: bool):
    ensure_customer_features()
    with get_cursor() as cur:
        cur.execute("SELECT amount_due FROM customers WHERE id = %s FOR UPDATE", (customer_id,))
        original = cur.fetchone()
        if not original:
            raise CustomerNotFoundError("Customer not found")
        original_due = float(original["amount_due"])
        cur.execute(
            """
            UPDATE customers
            SET paid_amount = CASE WHEN %s THEN amount_due ELSE NULL END,
                amount_due = CASE
                    WHEN %s THEN 0
                    ELSE COALESCE(NULLIF(paid_amount, 0), amount_due)
                END,
                status = CASE WHEN %s THEN 'paid' ELSE 'pending' END,
                promise_date = CASE WHEN %s THEN NULL ELSE promise_date END,
                next_followup_date = CASE WHEN %s THEN NULL ELSE next_followup_date END
            WHERE id = %s
            RETURNING id, name, phone, amount_due, status, promise_date
            """,
            (paid, paid, paid, paid, paid, customer_id),
        )
        customer = cur.fetchone()
        if not customer:
            raise CustomerNotFoundError("Customer not found")
        if paid and original_due > 0:
            cur.execute(
                """
                INSERT INTO payments (customer_id, amount, source)
                VALUES (%s, %s, 'mark_paid')
                """,
                (customer_id, original_due),
            )
            cur.execute(
                """
                UPDATE calls
                SET status = 'cancelled'
                WHERE customer_id = %s AND status IN ('pending', 'scheduled')
                """,
                (customer_id,),
            )
        return customer


def record_payment(customer_id: int, amount: float, method: str | None = None):
    ensure_customer_features()
    with get_cursor() as cur:
        cur.execute("SELECT id, amount_due FROM customers WHERE id = %s FOR UPDATE", (customer_id,))
        current = cur.fetchone()
        if not current:
            raise CustomerNotFoundError("Customer not found")
        if amount > float(current["amount_due"]):
            raise ValueError("Payment exceeds the current balance.")
        cur.execute(
            """
            UPDATE customers
            SET paid_amount = COALESCE(paid_amount, 0) + %s,
                amount_due = GREATEST(amount_due - %s, 0),
                status = CASE WHEN amount_due - %s <= 0 THEN 'paid' ELSE 'pending' END,
                promise_date = CASE WHEN amount_due - %s <= 0 THEN NULL ELSE promise_date END,
                next_followup_date = CASE WHEN amount_due - %s <= 0 THEN NULL ELSE next_followup_date END
            WHERE id = %s
            RETURNING id, name, phone, amount_due, status, promise_date, do_not_call, next_followup_date
            """,
            (amount, amount, amount, amount, amount, customer_id),
        )
        customer = cur.fetchone()
        cur.execute(
            "INSERT INTO payments (customer_id, amount, method, source) VALUES (%s, %s, %s, 'manual')",
            (customer_id, amount, method),
        )
        if float(customer["amount_due"]) <= 0:
            cur.execute(
                """
                UPDATE calls
                SET status = 'cancelled'
                WHERE customer_id = %s AND status IN ('pending', 'scheduled', 'queued', 'initiated')
                """,
                (customer_id,),
            )
        return customer


def set_do_not_call(customer_id: int, value: bool):
    ensure_customer_features()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE customers
            SET do_not_call = %s,
                status = CASE WHEN %s THEN 'do_not_call' ELSE
                CASE WHEN amount_due <= 0 THEN 'paid'
                     WHEN promise_date IS NOT NULL THEN 'promised_payment'
                     ELSE 'pending' END END
            WHERE id = %s
            RETURNING id, name, phone, amount_due, status, promise_date, do_not_call, next_followup_date
            """,
            (value, value, customer_id),
        )
        customer = cur.fetchone()
        if not customer:
            raise CustomerNotFoundError("Customer not found")
        return customer


def set_call_scheduled(customer_id: int):
    ensure_customer_features()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE customers
            SET status = 'call_scheduled'
            WHERE id = %s AND amount_due > 0 AND do_not_call = FALSE
            """,
            (customer_id,),
        )


def apply_call_outcome(customer_id: int, outcome: str, promise_date):
    ensure_customer_features()
    status_map = {
        "promised": "promised_payment",
        "no_answer": "no_answer",
        "disputed": "disputed",
        "no_money_now": "pending",
        "completed": "pending",
    }
    status = status_map.get(outcome, "pending")
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE customers
            SET status = CASE WHEN do_not_call THEN 'do_not_call' ELSE %s END,
                promise_date = %s,
                next_followup_date = %s
            WHERE id = %s AND amount_due > 0
            """,
            (status, promise_date, promise_date, customer_id),
        )


def get_customer(customer_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
        return cur.fetchone()


def count_call_attempts(customer_id: int) -> int:
    with get_cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS attempts FROM calls WHERE customer_id = %s AND status <> 'cancelled'",
            (customer_id,),
        )
        return int(cur.fetchone()["attempts"])


def create_queued_call(customer_id: int, cooldown_minutes: int, idempotency_key: str | None = None):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute("SELECT id, amount_due, do_not_call FROM customers WHERE id = %s FOR UPDATE", (customer_id,))
        customer = cur.fetchone()
        if not customer:
            raise CustomerNotFoundError("Customer not found")
        if customer["do_not_call"] or float(customer["amount_due"]) <= 0:
            raise ValueError("Customer is not eligible for a call.")
        if idempotency_key:
            cur.execute("SELECT id, attempt_number FROM calls WHERE idempotency_key = %s", (idempotency_key,))
            existing = cur.fetchone()
            if existing:
                existing["idempotent_replay"] = True
                return existing
        cur.execute(
            """
            SELECT id FROM calls
            WHERE customer_id = %s
              AND status IN ('queued', 'initiated', 'in_progress')
            LIMIT 1
            """,
            (customer_id,),
        )
        if cur.fetchone():
            raise ValueError("A call is already active for this customer.")
        cur.execute(
            """
            SELECT id FROM calls
            WHERE customer_id = %s
              AND called_at >= NOW() - (%s * INTERVAL '1 minute')
            LIMIT 1
            """,
            (customer_id, cooldown_minutes),
        )
        if cur.fetchone():
            raise ValueError("A call was already placed recently for this customer.")
        cur.execute(
            """
            INSERT INTO calls (customer_id, status, attempt_number, scheduled_for, idempotency_key)
            SELECT %s, 'queued', COUNT(*) + 1, NOW()
            , %s FROM calls WHERE customer_id = %s
            RETURNING id, attempt_number
            """,
            (customer_id, idempotency_key, customer_id),
        )
        created = cur.fetchone()
        created["idempotent_replay"] = False
        return created


def set_call_initiated(call_id: int, execution_id: str | None):
    transition_call(call_id, "initiated", "Bolna accepted outbound call", execution_id=execution_id)


def transition_call(
    call_id: int,
    target: str,
    reason: str,
    *,
    execution_id: str | None = None,
    failure_reason: str | None = None,
):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute("SELECT status FROM calls WHERE id = %s FOR UPDATE", (call_id,))
        row = cur.fetchone()
        if not row:
            raise ValueError("Call not found")
        current = str(row["status"])
        if not can_transition(current, target):
            raise InvalidTransitionError(f"Cannot transition call {call_id} from {current} to {target}.")
        cur.execute(
            """
            UPDATE calls
            SET status = %s,
                bolna_execution_id = COALESCE(%s, bolna_execution_id),
                started_at = CASE WHEN %s IN ('initiated', 'in_progress') THEN COALESCE(started_at, NOW()) ELSE started_at END,
                ended_at = CASE WHEN %s IN ('completed', 'no_answer', 'busy', 'failed', 'timed_out', 'cancelled') THEN NOW() ELSE ended_at END,
                failure_reason = COALESCE(%s, failure_reason)
            WHERE id = %s
            """,
            (target, execution_id, target, target, failure_reason, call_id),
        )
        cur.execute(
            """
            INSERT INTO call_state_audit (call_id, from_state, to_state, reason)
            VALUES (%s, %s, %s, %s)
            """,
            (call_id, current, target, reason),
        )


def register_webhook_event(provider_event_id: str, raw_payload: dict) -> bool:
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            INSERT INTO webhook_events (provider_event_id, raw_payload)
            VALUES (%s, %s)
            ON CONFLICT (provider_event_id) DO NOTHING
            RETURNING id
            """,
            (provider_event_id, extras.Json(raw_payload)),
        )
        return cur.fetchone() is not None


def finish_webhook_event(provider_event_id: str, *, error: str | None = None):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE webhook_events
            SET processed_at = NOW(), status = %s, error = %s
            WHERE provider_event_id = %s
            """,
            ("failed" if error else "processed", error, provider_event_id),
        )


def get_call_by_execution(execution_id: str):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM calls WHERE bolna_execution_id = %s FOR UPDATE", (execution_id,))
        return cur.fetchone()


def save_call_details(
    call_id: int,
    *,
    duration_seconds: float | None,
    agent_phone: str | None,
    called_at: datetime | None,
):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE calls
            SET duration_seconds = COALESCE(%s, duration_seconds),
                agent_phone = COALESCE(%s, agent_phone),
                called_at = COALESCE(%s, called_at)
            WHERE id = %s
            """,
            (duration_seconds, agent_phone, called_at, call_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Call not found")


def get_call_recording_url(call_id: int):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute("SELECT recording_url FROM calls WHERE id = %s", (call_id,))
        row = cur.fetchone()
        return row["recording_url"] if row else None


def get_call_by_id(call_id: int):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT calls.id, calls.customer_id, customers.name AS customer_name,
                   customers.phone, calls.called_at, calls.outcome,
                   calls.promise_date, calls.notes, calls.summary,
                   calls.transcript, calls.status, calls.bolna_execution_id,
                   calls.attempt_number, calls.scheduled_for, calls.started_at,
                   calls.ended_at, calls.failure_reason, calls.promise_amount,
                   calls.duration_seconds, calls.agent_phone,
                   CASE WHEN calls.recording_url IS NULL THEN NULL
                        ELSE '/calls/' || calls.id::text || '/recording' END AS recording_url
            FROM calls
            JOIN customers ON customers.id = calls.customer_id
            WHERE calls.id = %s
            """,
            (call_id,),
        )
        return cur.fetchone()


def save_call_content(
    call_id: int,
    *,
    transcript: str | None,
    summary: str | None,
    recording_url: str | None,
):
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE calls
            SET transcript = COALESCE(%s, transcript),
                summary = COALESCE(%s, summary),
                recording_url = COALESCE(%s, recording_url)
            WHERE id = %s
            """,
            (transcript, summary, recording_url, call_id),
        )
        if cur.rowcount == 0:
            raise ValueError("Call not found")


def purge_expired_call_data(retention_days: int):
    """Remove call content and webhook payloads after the configured retention period."""
    ensure_reliability_schema()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, retention_days))
    with get_cursor() as cur:
        cur.execute(
            """
            DELETE FROM call_state_audit
            WHERE call_id IN (SELECT id FROM calls WHERE called_at < %s)
            """,
            (cutoff,),
        )
        cur.execute(
            """
            UPDATE payments
            SET related_call_id = NULL
            WHERE related_call_id IN (SELECT id FROM calls WHERE called_at < %s)
            """,
            (cutoff,),
        )
        cur.execute("DELETE FROM calls WHERE called_at < %s", (cutoff,))
        cur.execute("DELETE FROM webhook_events WHERE received_at < %s", (cutoff,))


def save_completed_call(
    call_id: int,
    *,
    transcript: str,
    summary: str | None,
    recording_url: str | None,
    outcome: str,
    promise_date,
    promise_amount: float | None,
    dispute: bool,
    do_not_call: bool,
):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE calls
            SET transcript = %s, summary = %s, recording_url = %s,
                outcome = %s, promise_date = %s, promise_amount = %s,
                dispute = %s, opt_out = %s,
                ended_at = COALESCE(ended_at, NOW())
            WHERE id = %s
            RETURNING customer_id
            """,
            (transcript, summary, recording_url, outcome, promise_date, promise_amount,
             dispute, do_not_call, call_id),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError("Call not found")
        if dispute or do_not_call:
            cur.execute(
                """
                UPDATE customers
                SET status = CASE WHEN %s THEN 'do_not_call' ELSE 'disputed' END,
                    do_not_call = do_not_call OR %s,
                    promise_date = NULL, promise_amount = NULL,
                    promise_status = CASE WHEN %s THEN 'unverified' ELSE promise_status END,
                    next_followup_date = NULL
                WHERE id = %s
                """,
                (do_not_call, do_not_call, do_not_call, row["customer_id"]),
            )
        elif outcome == "promised":
            cur.execute(
                """
                UPDATE customers
                SET status = 'promised_payment', promise_date = %s,
                    promise_amount = %s, promise_status = 'pending',
                    next_followup_date = %s
                WHERE id = %s AND amount_due > 0
                """,
                (promise_date, promise_amount, promise_date, row["customer_id"]),
            )


def save_unverified_call(call_id: int, *, transcript: str, summary: str | None, recording_url: str | None):
    with get_cursor() as cur:
        cur.execute(
            """
            UPDATE calls
            SET transcript = %s, summary = %s, recording_url = %s, outcome = 'needs_review'
            WHERE id = %s
            """,
            (transcript, summary, recording_url, call_id),
        )


def list_calls():
    """Lists recorded calls with their customer details for the dashboard."""
    # Older databases may predate the reliability columns selected below.
    ensure_reliability_schema()
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT calls.id, calls.customer_id, customers.name AS customer_name,
                   customers.phone, calls.called_at, calls.outcome,
                   calls.promise_date, calls.notes, calls.summary,
                   calls.transcript, calls.status,
                   calls.bolna_execution_id, calls.attempt_number,
                   calls.scheduled_for, calls.started_at, calls.ended_at,
                   calls.failure_reason, calls.promise_amount,
                   calls.duration_seconds, calls.agent_phone,
                   CASE WHEN calls.recording_url IS NULL THEN NULL
                        ELSE '/calls/' || calls.id::text || '/recording' END AS recording_url
            FROM calls
            JOIN customers ON customers.id = calls.customer_id
            ORDER BY calls.called_at DESC, calls.id DESC
            """
        )
        return cur.fetchall()


def dashboard_summary():
    ensure_customer_features()
    with get_cursor() as cur:
        cur.execute(
            """
            WITH bounds AS (
                SELECT
                    (date_trunc('week', NOW() AT TIME ZONE 'Asia/Kolkata')
                        AT TIME ZONE 'Asia/Kolkata') AS week_start,
                    (date_trunc('day', NOW() AT TIME ZONE 'Asia/Kolkata')
                        AT TIME ZONE 'Asia/Kolkata') AS today_start
            ),
            payments_week AS (
                SELECT COALESCE(SUM(amount), 0) AS recovered
                FROM payments, bounds
                WHERE paid_at >= bounds.week_start
            ),
            customer_totals AS (
                SELECT
                    COALESCE(SUM(amount_due) FILTER (WHERE amount_due > 0), 0) AS outstanding,
                    COUNT(*) FILTER (WHERE amount_due > 0 AND promise_date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date) AS promised_today,
                    COUNT(*) FILTER (WHERE amount_due > 0 AND promise_date < (NOW() AT TIME ZONE 'Asia/Kolkata')::date AND NOT do_not_call) AS overdue_promises,
                    COUNT(*) FILTER (WHERE status = 'disputed' AND NOT do_not_call) AS disputes,
                    COUNT(*) FILTER (WHERE status = 'no_answer' AND NOT do_not_call) AS no_answer
                FROM customers
            ),
            calls_week AS (
                SELECT
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) FILTER (WHERE status IN ('completed','no_answer','busy','failed')) AS attempted,
                    COUNT(*) FILTER (WHERE status IN ('completed','in_progress')) AS connected,
                    COUNT(*) FILTER (WHERE opt_out OR dispute OR complaint OR early_hangup OR blocked_by_do_not_call) AS safety
                FROM calls, bounds
                WHERE called_at >= bounds.week_start
            ),
            after_call AS (
                SELECT COALESCE(SUM(p.amount), 0) AS recovered_after_call
                FROM payments p
                JOIN calls c ON c.customer_id = p.customer_id
                    AND c.status = 'completed'
                    AND p.paid_at >= c.ended_at
                    AND p.paid_at < c.ended_at + INTERVAL '7 days'
                JOIN bounds ON p.paid_at >= bounds.week_start
            )
            SELECT customer_totals.*, payments_week.recovered,
                   after_call.recovered_after_call, calls_week.completed,
                   calls_week.attempted, calls_week.connected, calls_week.safety,
                   CASE WHEN customer_totals.outstanding + payments_week.recovered = 0
                        THEN NULL
                        ELSE payments_week.recovered /
                            (customer_totals.outstanding + payments_week.recovered)
                   END AS recovery_rate
            FROM customer_totals, payments_week, calls_week, after_call
            """
        )
        row = dict(cur.fetchone())
        overdue = []
        cur.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(SUM(amount_due), 0) AS amount,
                   COALESCE(MAX(((NOW() AT TIME ZONE 'Asia/Kolkata')::date - promise_date)), 0) AS max_days
            FROM customers
            WHERE amount_due > 0 AND promise_date < (NOW() AT TIME ZONE 'Asia/Kolkata')::date
              AND NOT do_not_call
            """
        )
        overdue = dict(cur.fetchone())
        cur.execute(
            """
            SELECT
              COUNT(*) FILTER (WHERE opt_out) AS opt_outs,
              COUNT(*) FILTER (WHERE dispute) AS disputes,
              COUNT(*) FILTER (WHERE complaint) AS complaints,
              COUNT(*) FILTER (WHERE early_hangup) AS early_hangups,
              COUNT(*) FILTER (WHERE blocked_by_do_not_call) AS blocked_calls
            FROM calls, (SELECT (date_trunc('week', NOW() AT TIME ZONE 'Asia/Kolkata')
                AT TIME ZONE 'Asia/Kolkata') AS week_start) b
            WHERE called_at >= b.week_start
            """
        )
        safety = dict(cur.fetchone())
        row["overdue_promises_detail"] = overdue
        row["safety_events"] = {
            "opt_outs": safety.get("opt_outs", 0),
            "disputes": safety.get("disputes", 0),
            "complaints": safety.get("complaints", 0),
            "early_hangups": safety.get("early_hangups", 0),
            "blocked_calls": safety.get("blocked_calls", 0),
        }
        row["overdue_promises"] = overdue
        row["recovered_after_call"] = row.pop("recovered_after_call", 0)
        row["attribution_label"] = "Recovered this week; payments within 7 days after a completed Hisaab call are attributed, not claimed as caused."
        row["connected_rate"] = (float(row["connected"]) / float(row["attempted"])) if row["attempted"] else None
        return row


def dashboard_followups(page: int, page_size: int):
    ensure_customer_features()
    offset = max(page - 1, 0) * page_size
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.name,
                   CONCAT('******', RIGHT(REGEXP_REPLACE(c.phone, '\D', '', 'g'), 4)) AS masked_phone,
                   c.amount_due, c.status, c.promise_date, c.next_followup_date,
                   CASE
                     WHEN c.status = 'disputed' THEN 'Dispute needs review'
                     WHEN c.promise_date < (NOW() AT TIME ZONE 'Asia/Kolkata')::date THEN 'Overdue promise'
                     WHEN c.promise_date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date THEN 'Promised today'
                     WHEN c.status = 'no_answer' THEN 'Retry after no answer'
                     ELSE 'First reminder'
                   END AS reason,
                   latest.outcome AS last_call_outcome,
                   COALESCE(latest.summary, latest.notes) AS last_call_summary,
                   latest.scheduled_for AS next_scheduled_call,
                   COUNT(*) OVER() AS total
            FROM customers c
            LEFT JOIN LATERAL (
              SELECT outcome, summary, notes, scheduled_for
              FROM calls WHERE customer_id = c.id ORDER BY called_at DESC LIMIT 1
            ) latest ON TRUE
            WHERE c.amount_due > 0 AND NOT c.do_not_call
            ORDER BY CASE
              WHEN c.status = 'disputed' THEN 1
              WHEN c.promise_date < (NOW() AT TIME ZONE 'Asia/Kolkata')::date THEN 2
              WHEN c.promise_date = (NOW() AT TIME ZONE 'Asia/Kolkata')::date THEN 3
              WHEN c.status = 'no_answer' THEN 4 ELSE 5 END,
              c.promise_date NULLS LAST, c.id
            LIMIT %s OFFSET %s
            """,
            (page_size, offset),
        )
        rows = [dict(row) for row in cur.fetchall()]
        total = int(rows[0]["total"]) if rows else 0
        for row in rows:
            row.pop("total", None)
        return {"items": rows, "page": page, "page_size": page_size, "total": total}


# --- Group & Expense Functions for Hisaab ---

def create_group(name: str):
    """Creates a new group and returns its ID and name."""
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO groups (name) VALUES (%s) RETURNING id, name, created_at;",
            (name,)
        )
        return cur.fetchone()


def list_groups():
    """Lists all expense groups."""
    with get_cursor() as cur:
        cur.execute("SELECT id, name, created_at FROM groups ORDER BY created_at DESC;")
        return cur.fetchall()


def add_group_member(group_id: int, customer_id: int):
    """Adds a customer to a specific expense group."""
    with get_cursor() as cur:
        cur.execute(
            "INSERT INTO group_members (group_id, customer_id) VALUES (%s, %s) ON CONFLICT DO NOTHING;",
            (group_id, customer_id)
        )
        return {"status": "success", "group_id": group_id, "customer_id": customer_id}


def create_expense(group_id: int, description: str, amount: float, paid_by: int, splits: list):
    """
    Creates an expense and splits it among specified members.
    splits is a list of dicts: [{"customer_id": 1, "amount_owed": 50.0}, ...]
    """
    with get_cursor() as cur:
        # 1. Insert the main expense record
        cur.execute(
            """
            INSERT INTO expenses (group_id, description, amount, paid_by)
            VALUES (%s, %s, %s, %s) RETURNING id, group_id, description, amount, paid_by, created_at;
            """,
            (group_id, description, amount, paid_by)
        )
        expense = cur.fetchone()
        expense_id = expense["id"]

        # 2. Insert the splits
        for split in splits:
            cur.execute(
                """
                INSERT INTO expense_splits (expense_id, customer_id, amount_owed)
                VALUES (%s, %s, %s);
                """,
                (expense_id, split["customer_id"], split["amount_owed"])
            )
            
        return {"expense": expense, "splits_count": len(splits)}





def get_group_expenses(group_id: int):
    """Fetches all expenses for a specific group, including who paid."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT e.id, e.description, e.amount, e.paid_by, c.name as paid_by_name, e.created_at
            FROM expenses e
            LEFT JOIN customers c ON e.paid_by = c.id
            WHERE e.group_id = %s
            ORDER BY e.created_at DESC;
            """,
            (group_id,)
        )
        return cur.fetchall()


def get_group_balances(group_id: int):
    """Calculates the net balance for each member in a group (Paid - Owed)."""
    with get_cursor() as cur:
        cur.execute(
            """
            WITH paid_totals AS (
                SELECT paid_by AS customer_id, SUM(amount) AS total_paid
                FROM expenses
                WHERE group_id = %s
                GROUP BY paid_by
            ),
            owed_totals AS (
                SELECT es.customer_id, SUM(es.amount_owed) AS total_owed
                FROM expense_splits es
                JOIN expenses e ON es.expense_id = e.id
                WHERE e.group_id = %s
                GROUP BY es.customer_id
            ),
            group_customers AS (
                SELECT customer_id FROM group_members WHERE group_id = %s
            )
            SELECT 
                gc.customer_id,
                c.name,
                COALESCE(pt.total_paid, 0) AS total_paid,
                COALESCE(ot.total_owed, 0) AS total_owed,
                (COALESCE(pt.total_paid, 0) - COALESCE(ot.total_owed, 0)) AS net_balance
            FROM group_customers gc
            JOIN customers c ON gc.customer_id = c.id
            LEFT JOIN paid_totals pt ON gc.customer_id = pt.customer_id
            LEFT JOIN owed_totals ot ON gc.customer_id = ot.customer_id;
            """,
            (group_id, group_id, group_id)
        )
        return cur.fetchall()
