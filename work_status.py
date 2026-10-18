"""
Client-facing work status: where each client's return stands after their
documents are in.

    Documents received -> Under review -> Bookkeeping -> Return in preparation
    -> Ready for your signature -> Filed

One tracker per client, per business, per tax year (an owner with several
businesses gets one tracker for each). JJTC staff move a tracker forward from
the admin dashboard; the client sees it on their progress page or through a
private link, and gets a short email at each step.

Stages can be skipped (for example, no bookkeeping needed). Skipped stages
show the client "Not needed" instead of a checkmark.

Tables live here, not in db.py, so this feature can be added or removed on
its own.
"""

import secrets
import uuid
from datetime import datetime

import db

# (key, label the client sees, one-line explanation the client sees)
STAGES = [
    ("received", "Documents received", "We have your documents and your file is in line for review."),
    ("review", "Under review", "We're checking your documents and will reach out if anything is missing."),
    ("bookkeeping", "Bookkeeping", "We're entering and reconciling your books so your return is accurate."),
    ("preparing", "Return in preparation", "We're preparing your tax return."),
    ("signature", "Ready for your signature", "Your return is ready. Please review and sign so we can file."),
    ("filed", "Filed", "Your return has been filed. Thank you for trusting JJTC."),
]
STAGE_KEYS = [s[0] for s in STAGES]
STAGE_LABELS = {key: label for key, label, _ in STAGES}
STAGE_DESCRIPTIONS = {key: desc for key, _, desc in STAGES}


def init_tables():
    conn = db.get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS work_trackers (
            id TEXT PRIMARY KEY,
            client_id TEXT,
            business_name TEXT,
            tax_year INTEGER,
            token TEXT UNIQUE,
            created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS work_status_events (
            id TEXT PRIMARY KEY,
            tracker_id TEXT,
            stage TEXT,
            note TEXT,
            updated_by TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def create_tracker(client_id, business_name, tax_year, updated_by=None):
    """Creates a tracker that starts at 'Documents received'."""
    tracker_id = str(uuid.uuid4())
    conn = db.get_db()
    conn.execute(
        "INSERT INTO work_trackers (id, client_id, business_name, tax_year, token, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (tracker_id, client_id, business_name, tax_year, secrets.token_urlsafe(24), datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()
    add_event(tracker_id, "received", None, updated_by)
    return tracker_id


def add_event(tracker_id, stage, note=None, updated_by=None):
    if stage not in STAGE_KEYS:
        raise ValueError(f"Unknown stage: {stage}")
    conn = db.get_db()
    conn.execute(
        "INSERT INTO work_status_events (id, tracker_id, stage, note, updated_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), tracker_id, stage, note or None, updated_by, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def _events(tracker_id):
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM work_status_events WHERE tracker_id = ? ORDER BY created_at, rowid", (tracker_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _with_timeline(tracker):
    """
    Adds the current stage, latest note and a per-stage timeline:
    done (with date), current, skipped ("Not needed") or upcoming.
    """
    events = _events(tracker["id"])
    current = events[-1]["stage"] if events else "received"
    current_index = STAGE_KEYS.index(current)
    reached = {}
    for e in events:
        reached[e["stage"]] = e["created_at"]
    # A note belongs to the update it was written with; moving to the next
    # stage without a note clears it, so clients never see a stale request.
    latest_note = events[-1]["note"] if events else None

    timeline = []
    for i, (key, label, desc) in enumerate(STAGES):
        if key == current:
            state = "done" if key == "filed" else "current"
        elif i < current_index:
            state = "done" if key in reached else "skipped"
        else:
            state = "upcoming"
        timeline.append({
            "key": key, "label": label, "description": desc, "state": state,
            "date": (reached.get(key) or "")[:10],
        })

    tracker = dict(tracker)
    tracker.update({
        "current": current,
        "current_label": STAGE_LABELS[current],
        "current_description": STAGE_DESCRIPTIONS[current],
        "updated_at": events[-1]["created_at"] if events else tracker["created_at"],
        "latest_note": latest_note,
        "timeline": timeline,
        "history": list(reversed(events)),
    })
    return tracker


def get_tracker(tracker_id):
    conn = db.get_db()
    row = conn.execute("SELECT * FROM work_trackers WHERE id = ?", (tracker_id,)).fetchone()
    conn.close()
    return _with_timeline(dict(row)) if row else None


def get_tracker_by_token(token):
    conn = db.get_db()
    row = conn.execute("SELECT * FROM work_trackers WHERE token = ?", (token,)).fetchone()
    conn.close()
    return _with_timeline(dict(row)) if row else None


def trackers_for_client(client_id):
    conn = db.get_db()
    rows = conn.execute(
        "SELECT * FROM work_trackers WHERE client_id = ? ORDER BY tax_year DESC, business_name", (client_id,)
    ).fetchall()
    conn.close()
    return [_with_timeline(dict(r)) for r in rows]


def all_trackers():
    conn = db.get_db()
    rows = conn.execute(
        "SELECT t.*, c.full_name, c.email FROM work_trackers t LEFT JOIN clients c ON c.id = t.client_id "
        "ORDER BY t.tax_year DESC, t.created_at DESC"
    ).fetchall()
    conn.close()
    return [_with_timeline(dict(r)) for r in rows]


def send_status_email(to, client_name, tracker, link):
    """Short client email when their file moves to a new stage."""
    from html import escape
    from integrations import resend_email

    first = escape((client_name or "there").split(" ")[0])
    note = f"<p><strong>Note from our team:</strong> {escape(tracker['latest_note'])}</p>" \
        if tracker.get("latest_note") else ""
    html = f"""
    <p>Hi {first},</p>
    <p>Your {tracker['tax_year']} return for <strong>{escape(tracker['business_name'])}</strong> has moved to:
    <strong>{escape(tracker['current_label'])}</strong>.</p>
    <p>{escape(tracker['current_description'])}</p>
    {note}
    <p><a href="{escape(link)}">See where your return stands</a></p>
    <p>Lady Emily<br>Jehovah Jireh Tax Consultants<br><em>Your Vision Is Our Mission.</em></p>
    """
    subject = f"{tracker['business_name']}: {tracker['current_label']}"
    return resend_email.send_email(to=to, subject=subject, html=html)
