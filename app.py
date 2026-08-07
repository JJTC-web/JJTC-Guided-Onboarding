import os
import datetime
from functools import wraps

import psycopg2
import resend
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

import db
import situations
from integrations import pandadoc, financial_cents, resend_email, google_translate, supabase_auth

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.jinja_env.filters["language_name"] = google_translate.language_name

db.init_db()

resend.api_key = os.environ.get("RESEND_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
WORKBOOK_CRON_SECRET = os.environ.get("WORKBOOK_CRON_SECRET")
WORKBOOK_PDF_LINK = "https://web-production-51ad4.up.railway.app/static/workbook.pdf"


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def current_client_id():
    if "client_id" not in session:
        session["client_id"] = db.create_client()
    return session["client_id"]


def _safe_next_url(next_url):
    if next_url and next_url.startswith("/") and not next_url.startswith("//"):
        return next_url
    return url_for("dashboard")


def require_admin(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(url_for("dashboard_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/api/subscribe", methods=["POST"])
def subscribe():
    data = request.get_json()
    email = data.get("email")
    first_name = data.get("first_name", "")

    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO subscribers (email, first_name, source)
            VALUES (%s, %s, 'discipline_challenge')
            ON CONFLICT (email) DO NOTHING
            RETURNING id
            """,
            (email, first_name)
        )
        result = cur.fetchone()
        conn.commit()

        if result:
            send_welcome_email(email, first_name)
            cur.execute(
                "UPDATE subscribers SET welcome_email_sent_at = NOW() WHERE email = %s",
                (email,)
            )
            conn.commit()

        return jsonify({"success": True}), 200
    finally:
        cur.close()
        conn.close()


def send_welcome_email(email, first_name):
    resend.Emails.send({
        "from": "Lady Emily <hello@jjtc.info>",
        "to": email,
        "subject": "You're in! Let's start your 31 days",
        "html": f"""
            <p>Hi {first_name or 'there'},</p>
            <p>Welcome to the 31-Day Discipline Challenge — I'm so glad you're here.</p>
            <p>Your Day 1 starts now: [Day 1 content / link]</p>
            <p>Keep an eye on your inbox — I'll be with you each step of the way.</p>
            <p>Here's to your next 31 days,<br>Lady Emily<br>Jehovah Jireh Tax Consultants</p>
        """
    })


def send_workbook_email(email, first_name):
    resend.Emails.send({
        "from": "Lady Emily <hello@jjtc.info>",
        "to": email,
        "subject": "A little something for your finances too",
        "html": f"""
            <p>Hi {first_name or 'there'},</p>
            <p>You're a few days into the Challenge — how's it feeling so far?
            Discipline in one area of life has a way of spilling into others,
            and I wanted to hand you something that can help with one in particular:
            your finances.</p>
            <p>This free workbook, <strong>Funding the Mission</strong>, walks you
            through identifying funding opportunities, organizing next steps, and
            building financial readiness for your ministry.</p>
            <p><a href="{WORKBOOK_PDF_LINK}">Grab your free workbook here</a></p>
            <p>Keep going — you're building something real.</p>
            <p>Lady Emily<br>Jehovah Jireh Tax Consultants</p>
        """
    })


@app.route("/api/send-workbook-now", methods=["POST"])
def send_workbook_now():
    secret = request.headers.get("X-Cron-Secret")
    if secret != WORKBOOK_CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    data = request.get_json()
    email = data.get("email")
    if not email:
        return jsonify({"error": "Email is required"}), 400

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, first_name FROM subscribers WHERE email = %s", (email,))
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Subscriber not found"}), 404

        sub_id, first_name = row
        send_workbook_email(email, first_name)
        cur.execute(
            "UPDATE subscribers SET workbook_email_sent_at = NOW() WHERE id = %s",
            (sub_id,)
        )
        conn.commit()
        return jsonify({"success": True}), 200
    finally:
        cur.close()
        conn.close()


@app.route("/api/send-workbook-batch", methods=["POST"])
def send_workbook_batch():
    secret = request.headers.get("X-Cron-Secret")
    if secret != WORKBOOK_CRON_SECRET:
        return jsonify({"error": "Unauthorized"}), 401

    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, email, first_name FROM subscribers
            WHERE welcome_email_sent_at IS NOT NULL
              AND welcome_email_sent_at <= NOW() - INTERVAL '2 days'
              AND workbook_email_sent_at IS NULL
            """
        )
        rows = cur.fetchall()

        sent_count = 0
        for row in rows:
            sub_id, email, first_name = row
            send_workbook_email(email, first_name)
            cur.execute(
                "UPDATE subscribers SET workbook_email_sent_at = NOW() WHERE id = %s",
                (sub_id,)
            )
            sent_count += 1

        conn.commit()
        return jsonify({"success": True, "sent": sent_count}), 200
    finally:
        cur.close()
        conn.close()


@app.route("/")
def welcome():
    current_client_id()
    return render_template("welcome.html")


@app.route("/welcome/watched", methods=["POST"])
def welcome_watched():
    client_id = current_client_id()
    db.mark_video_watched(client_id)
    return redirect(url_for("situation_selector"))


@app.route("/situation", methods=["GET", "POST"])
def situation_selector():
    client_id = current_client_id()
    if request.method == "POST":
        situation_key = request.form.get("situation")
        if situation_key not in situations.SITUATIONS:
            flash("Please select a valid situation.")
            return redirect(url_for("situation_selector"))
        step_ids = [s["id"] for s in situations.get_steps(situation_key)]
        db.set_situation(client_id, situation_key, step_ids)
        return redirect(url_for("checklist"))

    return render_template("situation.html", situations=situations.SITUATIONS)


@app.route("/checklist")
def checklist():
    client_id = current_client_id()
    client = db.get_client(client_id)
    if not client or not client["situation"]:
        return redirect(url_for("situation_selector"))

    steps = situations.get_steps(client["situation"])
    step_ids = [s["id"] for s in steps]
    statuses = db.get_step_statuses(client_id)
    current_step_id = db.get_current_step_id(client_id, step_ids)

    checklist_items = []
    for step in steps:
        status = statuses.get(step["id"], {}).get("status", "locked")
        checklist_items.append({**step, "status": status})

    all_complete = current_step_id is None
    return render_template(
        "checklist.html",
        items=checklist_items,
        current_step_id=current_step_id,
        all_complete=all_complete,
        situation_label=situations.SITUATIONS[client["situation"]]["label"],
    )


@app.route("/step/<step_id>", methods=["GET", "POST"])
def step_detail(step_id):
    client_id = current_client_id()
    client = db.get_client(client_id)
    if not client or not client["situation"]:
        return redirect(url_for("situation_selector"))

    steps = situations.get_steps(client["situation"])
    step_ids = [s["id"] for s in steps]
    statuses = db.get_step_statuses(client_id)

    current_step_id = db.get_current_step_id(client_id, step_ids)
    step_status = statuses.get(step_id, {}).get("status", "locked")
    if step_status == "locked":
        flash("That step isn't unlocked yet.")
        return redirect(url_for("checklist"))

    step = situations.get_step(client["situation"], step_id)

    if request.method == "POST":
        if step["type"] == "intake":
            db.complete_step(client_id, step_id, step_ids)
            return redirect(url_for("checklist"))

        elif step["type"] == "upload":
            files = request.files.getlist("documents")
            for f in files:
                if f and f.filename:
                    upload_dir = os.path.join("uploads", client_id)
                    os.makedirs(upload_dir, exist_ok=True)
                    f.save(os.path.join(upload_dir, f.filename))
                    db.add_uploaded_file(client_id, step_id, f.filename)
            uploaded = db.get_uploaded_files(client_id, step_id)
            if uploaded:
                db.complete_step(client_id, step_id, step_ids)
                return redirect(url_for("checklist"))
            flash("Please upload at least one file.")

        elif step["type"] == "esign":
            client_name = request.form.get("name", "Client")
            client_email = request.form.get("email")
            try:
                document_id = pandadoc.create_document_from_template(step_id, client_name, client_email)
