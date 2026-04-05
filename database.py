import sqlite3
from datetime import datetime

DB_PATH = "payments.db"

def get_conn():
    return sqlite3.connect(DB_PATH)

def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS payments (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                telegram_user_id BIGINT NOT NULL,
                username         TEXT,
                plan             TEXT NOT NULL,
                amount_cents     INTEGER NOT NULL,
                mp_payment_id    TEXT UNIQUE,
                status           TEXT DEFAULT 'pending',
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                paid_at          TIMESTAMP
            )
        """)
        conn.commit()

def insert_pending(telegram_user_id: int, username: str, plan: str, amount_cents: int) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO payments (telegram_user_id, username, plan, amount_cents) VALUES (?, ?, ?, ?)",
            (telegram_user_id, username, plan, amount_cents)
        )
        conn.commit()
        return cur.lastrowid

def update_mp_payment_id(row_id: int, mp_payment_id: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE payments SET mp_payment_id = ? WHERE id = ?",
            (mp_payment_id, row_id)
        )
        conn.commit()

def mark_as_paid(mp_payment_id: str) -> dict | None:
    """Marca como pago e retorna dados da venda, ou None se já processado."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE payments SET status = 'paid', paid_at = ? WHERE mp_payment_id = ? AND status = 'pending'",
            (datetime.utcnow(), mp_payment_id)
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT telegram_user_id, username, plan, amount_cents FROM payments WHERE mp_payment_id = ?",
            (mp_payment_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "telegram_user_id": row[0],
            "username": row[1],
            "plan": row[2],
            "amount_cents": row[3],
        }
