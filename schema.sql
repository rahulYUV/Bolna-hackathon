CREATE TABLE IF NOT EXISTS customers (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    phone TEXT NOT NULL UNIQUE,
    amount_due NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (amount_due >= 0),
    paid_amount NUMERIC(12, 2),
    do_not_call BOOLEAN NOT NULL DEFAULT FALSE,
    next_followup_date DATE,
    status TEXT NOT NULL DEFAULT 'pending',
    promise_date DATE
    ,promise_amount NUMERIC(12, 2)
    ,promise_status TEXT NOT NULL DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS calls (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    called_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    outcome TEXT,
    promise_date DATE,
    notes TEXT,
    summary TEXT,
    transcript TEXT,
    recording_url TEXT,
    status TEXT NOT NULL DEFAULT 'completed',
    bolna_execution_id TEXT,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    scheduled_for TIMESTAMPTZ,
    started_at TIMESTAMPTZ,
    ended_at TIMESTAMPTZ,
    duration_seconds NUMERIC(10, 2),
    agent_phone TEXT,
    failure_reason TEXT,
    promise_amount NUMERIC(12, 2),
    idempotency_key TEXT
    ,dispute BOOLEAN NOT NULL DEFAULT FALSE
    ,complaint BOOLEAN NOT NULL DEFAULT FALSE
    ,opt_out BOOLEAN NOT NULL DEFAULT FALSE
    ,early_hangup BOOLEAN NOT NULL DEFAULT FALSE
    ,blocked_by_do_not_call BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS payments (
    id BIGSERIAL PRIMARY KEY,
    customer_id BIGINT NOT NULL REFERENCES customers(id),
    amount NUMERIC(12, 2) NOT NULL CHECK (amount > 0),
    paid_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    method TEXT,
    source TEXT NOT NULL DEFAULT 'manual',
    related_call_id BIGINT REFERENCES calls(id)
);

CREATE TABLE IF NOT EXISTS webhook_events (
    id BIGSERIAL PRIMARY KEY,
    provider_event_id TEXT NOT NULL UNIQUE,
    raw_payload JSONB NOT NULL,
    received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    status TEXT NOT NULL DEFAULT 'received',
    error TEXT
);

CREATE TABLE IF NOT EXISTS call_state_audit (
    id BIGSERIAL PRIMARY KEY,
    call_id BIGINT NOT NULL REFERENCES calls(id),
    from_state TEXT,
    to_state TEXT NOT NULL,
    reason TEXT,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE calls ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed';
ALTER TABLE calls ADD COLUMN IF NOT EXISTS bolna_execution_id TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS attempt_number INTEGER NOT NULL DEFAULT 1;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS scheduled_for TIMESTAMPTZ;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS ended_at TIMESTAMPTZ;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC(10, 2);
ALTER TABLE calls ADD COLUMN IF NOT EXISTS agent_phone TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS failure_reason TEXT;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS promise_amount NUMERIC(12, 2);
ALTER TABLE calls ADD COLUMN IF NOT EXISTS idempotency_key TEXT;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS paid_amount NUMERIC(12, 2);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS do_not_call BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS next_followup_date DATE;
ALTER TABLE customers ADD COLUMN IF NOT EXISTS promise_amount NUMERIC(12, 2);
ALTER TABLE customers ADD COLUMN IF NOT EXISTS promise_status TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE calls ADD COLUMN IF NOT EXISTS dispute BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS complaint BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS opt_out BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS early_hangup BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE calls ADD COLUMN IF NOT EXISTS blocked_by_do_not_call BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS calls_customer_id_idx ON calls(customer_id);
CREATE INDEX IF NOT EXISTS calls_called_at_idx ON calls(called_at DESC);
CREATE INDEX IF NOT EXISTS customers_followup_idx ON customers(next_followup_date);
CREATE UNIQUE INDEX IF NOT EXISTS calls_bolna_execution_idx ON calls(bolna_execution_id) WHERE bolna_execution_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS calls_idempotency_key_idx ON calls(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS calls_active_customer_idx ON calls(customer_id, status, called_at DESC);
CREATE INDEX IF NOT EXISTS payments_paid_at_idx ON payments(paid_at);
CREATE INDEX IF NOT EXISTS payments_customer_idx ON payments(customer_id, paid_at DESC);
CREATE INDEX IF NOT EXISTS customers_status_followup_idx ON customers(status, next_followup_date);
