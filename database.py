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
                efi_txid         TEXT UNIQUE,
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

def update_efi_txid(row_id: int, efi_txid: str):
    with get_conn() as conn:
        conn.execute(
            "UPDATE payments SET efi_txid = ? WHERE id = ?",
            (efi_txid, row_id)
        )
        conn.commit()

def mark_as_paid(efi_txid: str) -> dict | None:
    """Marca como pago e retorna dados da venda, ou None se já processado."""
    with get_conn() as conn:
        cur = conn.execute(
            "UPDATE payments SET status = 'paid', paid_at = ? WHERE efi_txid = ? AND status = 'pending'",
            (datetime.utcnow(), efi_txid)
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute(
            "SELECT telegram_user_id, username, plan, amount_cents FROM payments WHERE efi_txid = ?",
            (efi_txid,)
        ).fetchone()
        if not row:
            return None
        return {
            "telegram_user_id": row[0],
            "username": row[1],
            "plan": row[2],
            "amount_cents": row[3],
        }
