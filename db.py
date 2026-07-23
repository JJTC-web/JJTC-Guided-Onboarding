import sqlite3
import os
import uuid
from datetime import datetime

DB_PATH = os.environ.get("DATABASE_PATH", "onboarding.db")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            id TEXT PRIMARY KEY,
            situation TEXT,
            video_watched_at TEXT,
            status TEXT DEFAULT 'onboarding',
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS step_status (
            client_id TEXT,
            step_id TEXT,
            status TEXT DEFAULT 'locked',
            completed_at TEXT,
            external_ref TEXT,
            PRIMARY KEY (client_id, step_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            step_id TEXT,
            filename TEXT,
            uploaded_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_client():
    client_id = str(uuid.uuid4())
    conn = get_db()
    conn.execute(
        "INSERT INTO clients (id, created_at) VALUES (?, ?)",
        (client_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return client_id


def get_client(client_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_video_watched(client_id):
    conn = get_db()
    conn.execute(
        "UPDATE clients SET video_watched_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), client_id),
    )
    conn.commit()
    conn.close()


def set_situation(client_id, situation_key, step_ids):
    conn = get_db()
    conn.execute("UPDATE clients SET situation = ? WHERE id = ?", (situation_key, client_id))
    for i, step_id in enumerate(step_ids):
        status = "action_required" if i == 0 else "locked"
        conn.execute(
            "INSERT OR REPLACE INTO step_status (client_id, step_id, status) VALUES (?, ?, ?)",
            (client_id, step_id, status),
        )
    conn.commit()
    conn.close()


def get_step_statuses(client_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM step_status WHERE client_id = ?", (client_id,)
    ).fetchall()
    conn.close()
    return {row["step_id"]: dict(row) for row in rows}


def get_current_step_id(client_id, step_ids):
    statuses = get_step_statuses(client_id)
    for step_id in step_ids:
        if statuses.get(step_id, {}).get("status") != "complete":
            return step_id
    return None  # all complete


def complete_step(client_id, step_id, step_ids, external_ref=None):
    conn = get_db()
    conn.execute(
        "UPDATE step_status SET status = 'complete', completed_at = ?, external_ref = ? "
        "WHERE client_id = ? AND step_id = ?",
        (datetime.utcnow().isoformat(), external_ref, client_id, step_id),
    )
    # unlock the next step
    idx = step_ids.index(step_id)
    if idx + 1 < len(step_ids):
        next_id = step_ids[idx + 1]
        conn.execute(
            "UPDATE step_status SET status = 'action_required' WHERE client_id = ? AND step_id = ?",
            (client_id, next_id),
        )
    else:
        conn.execute("UPDATE clients SET status = 'active' WHERE id = ?", (client_id,))
    conn.commit()
    conn.close()


def add_uploaded_file(client_id, step_id, filename):
    conn = get_db()
    conn.execute(
        "INSERT INTO uploaded_files (id, client_id, step_id, filename, uploaded_at) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), client_id, step_id, filename, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def get_uploaded_files(client_id, step_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM uploaded_files WHERE client_id = ? AND step_id = ?",
        (client_id, step_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
