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