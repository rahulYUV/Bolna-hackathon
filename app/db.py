from contextlib import contextmanager

import psycopg2
from psycopg2.extras import RealDictCursor

from app.config import DATABASE_URL


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


def list_customers():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, name, phone, amount_due, status, promise_date
            FROM customers
            ORDER BY id
            """
        )
        return cur.fetchall()


def get_customer(customer_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM customers WHERE id = %s", (customer_id,))
        return cur.fetchone()