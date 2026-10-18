import sqlite3
import os
import uuid
from datetime import datetime

def _default_db_path():
    """
    Where the database file lives. Railway erases a service's files on every
    redeploy unless a Volume is attached, so:
      1. DATABASE_PATH, if set, always wins.
      2. Otherwise, if a Railway Volume is attached (Railway sets
         RAILWAY_VOLUME_MOUNT_PATH automatically), the database goes on it.
      3. Otherwise, a local file - fine for testing, NOT safe on Railway.
    """
    if os.environ.get("DATABASE_PATH"):
        return os.environ["DATABASE_PATH"]
    volume = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    if volume:
        return os.path.join(volume, "onboarding.db")
    return "onboarding.db"


DB_PATH = _default_db_path()


def storage_warning():
    """
    A warning for the admin dashboard when client data would be erased on
    the next redeploy (running on Railway with no Volume and no
    DATABASE_PATH). None when storage is safe.
    """
    on_railway = any(k.startswith("RAILWAY_") for k in os.environ)
    if on_railway and not os.environ.get("DATABASE_PATH") and not os.environ.get("RAILWAY_VOLUME_MOUNT_PATH"):
        return (
            "Client data is NOT being saved permanently. Railway erases it on every redeploy. "
            "Attach a Volume to this service in Railway (mount path /data) to fix this."
        )
    return None


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
    _ensure_column(conn, "clients", "full_name", "TEXT")
    _ensure_column(conn, "clients", "email", "TEXT")
    _ensure_column(conn, "clients", "portal_upload_confirmed_at", "TEXT")
    _ensure_column(conn, "clients", "portal_file_count", "INTEGER")
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
    conn.execute("""
        CREATE TABLE IF NOT EXISTS nps_responses (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            score INTEGER,
            comment TEXT,
            created_at TEXT
        )
    """)
    _ensure_column(conn, "nps_responses", "comment_en", "TEXT")
    _ensure_column(conn, "nps_responses", "comment_lang", "TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS engagement_letters (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            service_code TEXT,
            year INTEGER,
            status TEXT DEFAULT 'pending',
            document_id TEXT,
            sent_at TEXT,
            signed_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS poll_state (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intake_flags (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            step_id TEXT,
            flag_type TEXT,
            file_count INTEGER,
            detail TEXT,
            created_at TEXT,
            resolved_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS year_end_assessments (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            token TEXT UNIQUE,
            entity_name TEXT,
            tax_year INTEGER,
            status TEXT DEFAULT 'invited',
            answers_json TEXT,
            scope_json TEXT,
            total REAL,
            document_id TEXT,
            created_at TEXT,
            submitted_at TEXT,
            sent_at TEXT,
            signed_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def _ensure_column(conn, table, column, coltype):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")


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


def set_client_contact(client_id, full_name, email):
    conn = get_db()
    conn.execute(
        "UPDATE clients SET full_name = ?, email = ? WHERE id = ?",
        (full_name, email, client_id),
    )
    conn.commit()
    conn.close()


def get_client_by_email(email):
    conn = get_db()
    row = conn.execute("SELECT * FROM clients WHERE email = ?", (email,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_active_clients():
    """Clients who've completed onboarding - the "recurring clients" the
    annual portal-compliance checkpoint (Section 2.2) runs against."""
    conn = get_db()
    rows = conn.execute("SELECT * FROM clients WHERE status = 'active'").fetchall()
    conn.close()
    return [dict(r) for r in rows]


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


def add_nps_response(client_id, score, comment, comment_en=None, comment_lang=None):
    conn = get_db()
    conn.execute(
        "INSERT INTO nps_responses (id, client_id, score, comment, comment_en, comment_lang, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), client_id, score, comment, comment_en, comment_lang, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def has_nps_response(client_id):
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM nps_responses WHERE client_id = ? LIMIT 1", (client_id,)
    ).fetchone()
    conn.close()
    return row is not None


def get_nps_summary(recent_comments_limit=3):
    """
    Returns the current NPS summary: the NPS score (% promoters - % detractors,
    scores 0-10), total response count, and the N most recent comments.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT score, comment, comment_en, comment_lang, created_at FROM nps_responses ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    responses = [dict(r) for r in rows]
    response_count = len(responses)

    if response_count:
        promoters = sum(1 for r in responses if r["score"] >= 9)
        detractors = sum(1 for r in responses if r["score"] <= 6)
        score = round((promoters - detractors) / response_count * 100)
    else:
        score = 0

    recent_comments = [r for r in responses if r["comment"]][:recent_comments_limit]

    return {
        "score": score,
        "response_count": response_count,
        "recent_comments": recent_comments,
    }


# --- Scheduled poll state (6.5's `update_last_poll_time`) -------------------

def get_last_scope_poll_time():
    conn = get_db()
    row = conn.execute("SELECT value FROM poll_state WHERE key = 'last_scope_poll_at'").fetchone()
    conn.close()
    return row["value"] if row else None


def set_last_scope_poll_time(timestamp):
    conn = get_db()
    conn.execute(
        "INSERT INTO poll_state (key, value) VALUES ('last_scope_poll_at', ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (timestamp,),
    )
    conn.commit()
    conn.close()


# --- Portal intake gate (2.2) -----------------------------------------------

def set_portal_upload_confirmed(client_id, file_count):
    conn = get_db()
    conn.execute(
        "UPDATE clients SET portal_upload_confirmed_at = ?, portal_file_count = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), file_count, client_id),
    )
    conn.commit()
    conn.close()


def add_intake_flag(client_id, step_id, flag_type, file_count=None, detail=None):
    conn = get_db()
    flag_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO intake_flags (id, client_id, step_id, flag_type, file_count, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (flag_id, client_id, step_id, flag_type, file_count, detail, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return flag_id


def get_open_intake_flags():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM intake_flags WHERE resolved_at IS NULL ORDER BY created_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_open_intake_flags_for_client(client_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM intake_flags WHERE client_id = ? AND resolved_at IS NULL ORDER BY created_at DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_intake_flag(flag_id):
    conn = get_db()
    conn.execute(
        "UPDATE intake_flags SET resolved_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), flag_id),
    )
    conn.commit()
    conn.close()


# --- Engagement letter / addendum gate (Section 3 & 4) ----------------------

def has_signed_engagement_letter(client_id, service_code, year):
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM engagement_letters WHERE client_id = ? AND service_code = ? "
        "AND year = ? AND status = 'signed' LIMIT 1",
        (client_id, service_code, year),
    ).fetchone()
    conn.close()
    return row is not None


def has_pending_or_signed_engagement_letter(client_id, service_code, year):
    """
    Whether this year's letter/addendum for this service code is already
    in flight (signed or awaiting signature) - used to avoid re-sending the
    annual TAX-PREP renewal to a client who's already mid-signature on it.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT 1 FROM engagement_letters WHERE client_id = ? AND service_code = ? AND year = ? LIMIT 1",
        (client_id, service_code, year),
    ).fetchone()
    conn.close()
    return row is not None


def create_pending_addendum(client_id, service_code, year, document_id):
    conn = get_db()
    addendum_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO engagement_letters (id, client_id, service_code, year, status, document_id, sent_at) "
        "VALUES (?, ?, ?, ?, 'pending', ?, ?)",
        (addendum_id, client_id, service_code, year, document_id, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return addendum_id


def get_pending_addendum_by_document(document_id):
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM engagement_letters WHERE document_id = ? AND status = 'pending' LIMIT 1",
        (document_id,),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def mark_addendum_signed(document_id):
    conn = get_db()
    conn.execute(
        "UPDATE engagement_letters SET status = 'signed', signed_at = ? WHERE document_id = ?",
        (datetime.utcnow().isoformat(), document_id),
    )
    conn.commit()
    row = conn.execute(
        "SELECT * FROM engagement_letters WHERE document_id = ?", (document_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def count_signed_addenda_for_year(client_id, year, exclude_service_codes=()):
    conn = get_db()
    placeholders = ",".join("?" for _ in exclude_service_codes)
    query = (
        "SELECT COUNT(*) FROM engagement_letters WHERE client_id = ? AND year = ? AND status = 'signed'"
    )
    params = [client_id, year]
    if exclude_service_codes:
        query += f" AND service_code NOT IN ({placeholders})"
        params.extend(exclude_service_codes)
    count = conn.execute(query, params).fetchone()[0]
    conn.close()
    return count


def list_pending_addenda():
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM engagement_letters WHERE status = 'pending' ORDER BY sent_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# --- Year-end questionnaire and engagement letter ---------------------------
# status: invited -> submitted -> sent -> signed

def create_year_end_invite(client_id, entity_name, tax_year):
    import secrets
    conn = get_db()
    assessment_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(24)
    conn.execute(
        "INSERT INTO year_end_assessments (id, client_id, token, entity_name, tax_year, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, 'invited', ?)",
        (assessment_id, client_id, token, entity_name, tax_year, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    return assessment_id, token


def _year_end_row(where, params):
    conn = get_db()
    row = conn.execute(f"SELECT * FROM year_end_assessments WHERE {where} LIMIT 1", params).fetchone()
    conn.close()
    return dict(row) if row else None


def get_year_end(assessment_id):
    return _year_end_row("id = ?", (assessment_id,))


def get_year_end_by_token(token):
    return _year_end_row("token = ?", (token,))


def get_year_end_by_document(document_id):
    return _year_end_row("document_id = ?", (document_id,))


def has_year_end_invite(client_id, tax_year):
    return _year_end_row("client_id = ? AND tax_year = ?", (client_id, tax_year)) is not None


def list_year_end(limit=200):
    conn = get_db()
    rows = conn.execute(
        "SELECT y.*, c.full_name, c.email FROM year_end_assessments y "
        "LEFT JOIN clients c ON c.id = y.client_id ORDER BY y.created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def save_year_end_answers(assessment_id, entity_name, answers_json, scope_json, total):
    conn = get_db()
    conn.execute(
        "UPDATE year_end_assessments SET entity_name = ?, answers_json = ?, scope_json = ?, total = ?, "
        "status = 'submitted', submitted_at = ? WHERE id = ? AND status IN ('invited', 'submitted')",
        (entity_name, answers_json, scope_json, total, datetime.utcnow().isoformat(), assessment_id),
    )
    conn.commit()
    conn.close()


def update_year_end_scope(assessment_id, scope_json, total):
    conn = get_db()
    conn.execute(
        "UPDATE year_end_assessments SET scope_json = ?, total = ? WHERE id = ? AND status = 'submitted'",
        (scope_json, total, assessment_id),
    )
    conn.commit()
    conn.close()


def mark_year_end_sent(assessment_id, document_id, scope_json, total):
    conn = get_db()
    conn.execute(
        "UPDATE year_end_assessments SET status = 'sent', document_id = ?, scope_json = ?, total = ?, sent_at = ? "
        "WHERE id = ?",
        (document_id, scope_json, total, datetime.utcnow().isoformat(), assessment_id),
    )
    conn.commit()
    conn.close()


def mark_year_end_signed(document_id):
    conn = get_db()
    conn.execute(
        "UPDATE year_end_assessments SET status = 'signed', signed_at = ? WHERE document_id = ?",
        (datetime.utcnow().isoformat(), document_id),
    )
    conn.commit()
    conn.close()
