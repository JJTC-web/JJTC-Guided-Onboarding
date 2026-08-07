import hmac
import os
from datetime import datetime
from functools import wraps

import psycopg2
import resend
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

import db
import policy
import situations
from integrations import pandadoc, financial_cents, resend_email, google_translate, supabase_auth

resend.api_key = os.environ.get("RESEND_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")
app.jinja_env.filters["language_name"] = google_translate.language_name
app.jinja_env.globals["policy"] = policy

db.init_db()


def get_db_connection():
    return psycopg2.connect(DATABASE_URL)


def current_client_id():
    if "client_id" not in session:
        session["client_id"] = db.create_client()
    return session["client_id"]


def current_year():
    return datetime.utcnow().year


def ensure_engagement_letter(client_id, service_code, client_name, client_email):
    """
    The gate from Section 3.2: "Does this client have a signed EL covering
    [service code] for this engagement year? If no -> block, send addendum
    for signature, do not proceed." Returns (covered, document_id).
    document_id is only set when a new addendum was just generated and sent.
    """
    if db.has_signed_engagement_letter(client_id, service_code, current_year()):
        return True, None
    document_id = pandadoc.generate_addendum(service_code, client_name, client_email)
    db.create_pending_addendum(client_id, service_code, current_year(), document_id)
    return False, document_id


def check_portal_upload(client_id, source, email, full_name):
    """
    Confirms via the Financial Cents API - not self-reported - that a
    client's documents are landing in their portal, and flags an anomalous
    batch size as possible bookkeeping/cleanup scope (Section 2.2). Shared
    by the onboarding "Portal Upload Confirmed" step and the annual
    portal-compliance checkpoint, so both apply the same anomaly rule.
    Returns (fc_client, file_count); fc_client is None if no Financial
    Cents record was found.
    """
    fc_client, file_count = financial_cents.get_portal_upload_count(email)
    if not fc_client:
        return None, 0
    db.set_portal_upload_confirmed(client_id, file_count)
    if file_count >= situations.FILE_COUNT_ANOMALY_THRESHOLD:
        db.add_intake_flag(
            client_id, source, "file_count_anomaly", file_count=file_count,
            detail=f"{file_count} files in one portal batch - possible cleanup/bookkeeping scope.",
        )
        try:
            ensure_engagement_letter(client_id, "BOOKKEEPING", full_name or "Client", email)
        except Exception:
            pass  # staff can still see the flag and follow up manually
    return fc_client, file_count


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


@app.route("/challenge-signup")
def challenge_signup():
    return render_template("challenge_signup.html")


CHALLENGE_LENGTH_DAYS = 31

# Placeholder day-by-day content for the 31-Day Discipline Challenge workbook
# emails. Fill in the real body per day here; any day without a specific
# entry falls back to a generic placeholder so send_workbook_batch() never
# breaks on a missing day.
WORKBOOK_DAYS = {
    # 1: {"subject": "Day 1: ...", "html": "<p>...</p>"},
}


def _workbook_content_for_day(day_number):
    entry = WORKBOOK_DAYS.get(day_number)
    if entry:
        return entry
    return {
        "subject": f"Day {day_number} of your 31-Day Discipline Challenge",
        "html": f"<p>Day {day_number} content coming soon — check back in your workbook.</p>",
    }


def _ensure_workbook_progress_column(cur):
    cur.execute(
        "ALTER TABLE subscribers ADD COLUMN IF NOT EXISTS last_workbook_day_sent INTEGER NOT NULL DEFAULT 0"
    )


@app.route("/api/send-workbook-batch", methods=["POST"])
def send_workbook_batch():
    """
    Meant to be triggered once a day by an external scheduler (see
    env.example's SCHEDULED_TASK_SECRET). For each subscriber, sends
    whichever challenge day matches how long they've been subscribed - at
    most one email per subscriber per run, and never a day they've already
    received, so a missed cron run doesn't cause a pile of backdated emails.
    """
    secret = os.environ.get("SCHEDULED_TASK_SECRET")
    authorized = session.get("is_admin") or (
        secret and hmac.compare_digest(request.headers.get("X-Task-Secret", ""), secret)
    )
    if not authorized:
        return "unauthorized", 401

    conn = get_db_connection()
    cur = conn.cursor()
    sent = skipped = errors = 0
    try:
        _ensure_workbook_progress_column(cur)
        conn.commit()

        cur.execute(
            """
            SELECT email, first_name, welcome_email_sent_at, last_workbook_day_sent
            FROM subscribers
            WHERE welcome_email_sent_at IS NOT NULL
              AND last_workbook_day_sent < %s
            """,
            (CHALLENGE_LENGTH_DAYS,),
        )
        rows = cur.fetchall()

        for email, first_name, welcome_email_sent_at, last_day_sent in rows:
            current_day = (datetime.utcnow().date() - welcome_email_sent_at.date()).days + 1
            current_day = min(current_day, CHALLENGE_LENGTH_DAYS)
            if current_day <= last_day_sent:
                skipped += 1
                continue

            content = _workbook_content_for_day(current_day)
            try:
                resend.Emails.send({
                    "from": "Lady Emily <hello@jjtc.info>",
                    "to": email,
                    "subject": content["subject"],
                    "html": content["html"],
                })
                cur.execute(
                    "UPDATE subscribers SET last_workbook_day_sent = %s WHERE email = %s",
                    (current_day, email),
                )
                conn.commit()
                sent += 1
            except Exception:
                conn.rollback()
                errors += 1
    finally:
        cur.close()
        conn.close()

    return jsonify({"sent": sent, "skipped": skipped, "errors": errors}), 200


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

    # Lock enforcement: only the current unlocked step (or a completed one) is viewable
    current_step_id = db.get_current_step_id(client_id, step_ids)
    step_status = statuses.get(step_id, {}).get("status", "locked")
    if step_status == "locked":
        flash("That step isn't unlocked yet.")
        return redirect(url_for("checklist"))

    step = situations.get_step(client["situation"], step_id)

    if request.method == "POST":
        if step["type"] == "intake":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            db.set_client_contact(client_id, full_name, email)
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
            # Kick off a PandaDoc document for this step
            client_name = request.form.get("name", "Client")
            client_email = request.form.get("email")
            try:
                document_id = pandadoc.create_document_from_template(step_id, client_name, client_email)
                statuses = db.get_step_statuses(client_id)
                conn = db.get_db()
                conn.execute(
                    "UPDATE step_status SET status = 'pending_verification', external_ref = ? "
                    "WHERE client_id = ? AND step_id = ?",
                    (document_id, client_id, step_id),
                )
                conn.commit()
                conn.close()
                if step_id == "engagement_letter":
                    # Tracked in engagement_letters too so the annual
                    # portal-compliance checkpoint (Section 2.2) knows this
                    # year's standing TAX-PREP letter is already in flight.
                    db.create_pending_addendum(client_id, "TAX-PREP", current_year(), document_id)
                flash("Document sent to your email for signature. Refresh this page once you've signed.")
            except Exception as e:
                flash(f"Couldn't send document for signature: {e}")

        elif step["type"] == "financial_cents":
            client_email = request.form.get("email")
            try:
                connected, fc_client = financial_cents.is_connected_and_current(client_email)
                if connected:
                    db.complete_step(client_id, step_id, step_ids, external_ref=str(fc_client.get("id")))
                    return redirect(url_for("checklist"))
                else:
                    flash("We couldn't find your Financial Cents record yet. Please try again shortly or contact us.")
            except Exception as e:
                flash(f"Couldn't verify Financial Cents connection: {e}")

        elif step["type"] == "portal_confirm":
            email = request.form.get("email") or client.get("email")
            if not email:
                flash("We don't have your email on file yet. Please complete the intake step first.")
                return redirect(url_for("step_detail", step_id=step_id))
            try:
                fc_client, file_count = check_portal_upload(
                    client_id, step_id, email, client.get("full_name"),
                )
                if not fc_client:
                    flash("We couldn't find your Financial Cents portal record yet. Please try again shortly or contact us.")
                else:
                    if file_count >= situations.FILE_COUNT_ANOMALY_THRESHOLD:
                        flash(
                            f"You uploaded {file_count} files in this batch, which looks like bookkeeping/"
                            "cleanup work rather than standard document intake. We're handling the paperwork "
                            "for that scope separately - it starts once its addendum is signed and invoiced."
                        )
                    db.complete_step(client_id, step_id, step_ids, external_ref=str(file_count))
                    return redirect(url_for("checklist"))
            except Exception as e:
                flash(f"Couldn't confirm your portal upload: {e}")

        return redirect(url_for("step_detail", step_id=step_id))

    # GET: for esign steps pending verification, check PandaDoc status
    if step["type"] == "esign" and step_status == "pending_verification":
        external_ref = statuses.get(step_id, {}).get("external_ref")
        if external_ref:
            try:
                if pandadoc.is_signed(external_ref):
                    db.complete_step(client_id, step_id, step_ids, external_ref=external_ref)
                    if step_id == "engagement_letter":
                        db.mark_addendum_signed(external_ref)
                    return redirect(url_for("checklist"))
            except Exception:
                pass  # fall through and just show current status

    uploaded_files = db.get_uploaded_files(client_id, step_id) if step["type"] == "upload" else []

    return render_template(
        "step_detail.html",
        step=step,
        status=step_status,
        uploaded_files=uploaded_files,
    )


@app.route("/request-service", methods=["GET", "POST"])
def request_service():
    """
    Client-facing entry point for Section 3/4's scope gate: any work that
    doesn't map to an already-signed, current-year service code goes
    through here rather than being silently absorbed into the existing
    engagement. Covers the "annual report renewal + zero sales tax return"
    half of the incident this spec was written for.
    """
    client_id = current_client_id()
    client = db.get_client(client_id)

    if request.method == "POST":
        service_code = request.form.get("service_code")
        if service_code not in situations.OUT_OF_SCOPE_SERVICE_CODES:
            flash("Please select a valid service.")
            return redirect(url_for("request_service"))

        full_name = request.form.get("name", "").strip() or (client and client.get("full_name")) or "Client"
        email = request.form.get("email", "").strip() or (client and client.get("email"))
        if not email:
            flash("We need an email address to send the addendum.")
            return redirect(url_for("request_service"))

        db.set_client_contact(client_id, full_name, email)
        try:
            covered, document_id = ensure_engagement_letter(client_id, service_code, full_name, email)
            if covered:
                flash(
                    f"You already have a signed {situations.SERVICE_CODES[service_code]} engagement letter for "
                    "this year - we'll invoice this separately and get started."
                )
            else:
                flash(
                    f"{situations.SERVICE_CODES[service_code]} isn't covered by your current engagement letter. "
                    "We've sent a short addendum to your email for signature - work begins once it's signed and "
                    "invoiced."
                )
        except Exception as e:
            flash(f"Couldn't process this request: {e}")
        return redirect(url_for("request_service"))

    return render_template(
        "request_service.html",
        service_codes=situations.OUT_OF_SCOPE_SERVICE_CODES,
        service_labels=situations.SERVICE_CODES,
        client=client,
    )


@app.route("/webhooks/pandadoc/signed", methods=["POST"])
def pandadoc_signed_webhook():
    """
    Section 6.5's signature webhook handler: on addendum signature, records
    it, creates the invoice, and (if this is the client's 2nd+ out-of-scope
    addendum this year) flags them as a repeat-offender candidate for
    retainer renegotiation (Section 4).
    """
    signature = request.headers.get("PandaDoc-Signature") or request.headers.get("X-PandaDoc-Signature")
    if not pandadoc.verify_webhook_signature(request.get_data(), signature):
        return "invalid signature", 403

    payload = request.get_json(silent=True) or {}
    events = payload if isinstance(payload, list) else [payload]

    for event in events:
        data = event.get("data", event)
        document_id = data.get("id")
        status = data.get("status")
        if not document_id or status != "document.completed":
            continue

        pending = db.get_pending_addendum_by_document(document_id)
        if not pending:
            continue  # not one of our tracked addenda (e.g. an intake esign step)

        addendum = db.mark_addendum_signed(document_id)
        client_id = addendum["client_id"]
        service_code = addendum["service_code"]
        client = db.get_client(client_id)

        try:
            fc_client = financial_cents.find_client_by_email(client.get("email")) if client else None
            if fc_client:
                financial_cents.create_invoice_for_service(
                    fc_client["id"], service_code, situations.SERVICE_CODES.get(service_code)
                )
        except Exception:
            pass  # invoicing failure shouldn't block recording the signature

        offender_count = db.count_signed_addenda_for_year(
            client_id, addendum["year"], exclude_service_codes=("TAX-PREP", "BACK-TAX")
        )
        if offender_count >= 2:
            db.add_intake_flag(
                client_id, service_code, "repeat_offender",
                detail=f"{offender_count} out-of-scope addenda signed in {addendum['year']} - retainer review candidate.",
            )

    return "", 200


@app.route("/tasks/poll-scope-triggers", methods=["POST"])
def poll_scope_triggers():
    """
    Section 6.5's `check_for_scope_triggers`: polls Financial Cents for
    client-portal tasks that indicate a scope change (e.g. a client checking
    "I need help sorting these"), and for each one either clears it straight
    to invoicing (already-signed EL) or generates and sends a PandaDoc
    addendum. Meant to be hit on a schedule (Railway Cron / Zapier) using
    SCHEDULED_TASK_SECRET, or manually from the admin dashboard.
    """
    secret = os.environ.get("SCHEDULED_TASK_SECRET")
    authorized = session.get("is_admin") or (
        secret and hmac.compare_digest(request.headers.get("X-Task-Secret", ""), secret)
    )
    if not authorized:
        return "unauthorized", 401

    poll_started_at = datetime.utcnow().isoformat()
    processed = 0
    try:
        since = db.get_last_scope_poll_time()
        for task in financial_cents.get_completed_client_tasks(since=since):
            service_code = situations.map_task_to_service_code(task.get("label", ""))
            if not service_code:
                continue
            task_client = task.get("client", {})
            client = db.get_client_by_email(task_client.get("email", ""))
            if not client:
                continue

            covered, _ = ensure_engagement_letter(
                client["id"], service_code, client.get("full_name") or "Client", client.get("email")
            )
            if covered:
                fc_client_id = task_client.get("id")
                if fc_client_id:
                    financial_cents.create_invoice_for_service(
                        fc_client_id, service_code, situations.SERVICE_CODES.get(service_code)
                    )
            processed += 1
        db.set_last_scope_poll_time(poll_started_at)
    except Exception as e:
        flash(f"Scope-trigger poll failed: {e}")

    if session.get("is_admin"):
        flash(f"Scope-trigger poll complete - {processed} task(s) processed.")
        return redirect(url_for("dashboard"))
    return {"processed": processed}, 200


@app.route("/tasks/annual-reengagement-check", methods=["POST"])
def annual_reengagement_check():
    """
    Section 2.2's last bullet: recurring clients get an annual portal-
    compliance checkpoint at re-engagement time, confirming (via Financial
    Cents, not self-reported) that they're still uploading correctly before
    that year's engagement letter goes out. Compliant clients get this
    year's TAX-PREP letter generated and sent automatically; anyone with an
    open intake flag or no live Financial Cents connection is held back and
    flagged for staff review instead. Meant to run once a year at
    re-engagement time via the same scheduler/secret as
    poll_scope_triggers, or manually from the admin dashboard.
    """
    secret = os.environ.get("SCHEDULED_TASK_SECRET")
    authorized = session.get("is_admin") or (
        secret and hmac.compare_digest(request.headers.get("X-Task-Secret", ""), secret)
    )
    if not authorized:
        return "unauthorized", 401

    year = current_year()
    sent = flagged = skipped = 0
    for client in db.get_active_clients():
        email = client.get("email")
        if not email or db.has_pending_or_signed_engagement_letter(client["id"], "TAX-PREP", year):
            skipped += 1
            continue

        try:
            fc_client, _ = check_portal_upload(
                client["id"], "annual_reengagement_check", email, client.get("full_name"),
            )
            if not fc_client or db.get_open_intake_flags_for_client(client["id"]):
                db.add_intake_flag(
                    client["id"], "annual_reengagement_check", "portal_compliance_review",
                    detail=(
                        "No live Financial Cents portal connection found."
                        if not fc_client else
                        "Open intake flag(s) on file - review before sending this year's engagement letter."
                    ),
                )
                flagged += 1
                continue

            document_id = pandadoc.generate_addendum("TAX-PREP", client.get("full_name") or "Client", email)
            db.create_pending_addendum(client["id"], "TAX-PREP", year, document_id)
            sent += 1
        except Exception:
            flagged += 1

    if session.get("is_admin"):
        flash(f"Annual re-engagement check complete - {sent} letter(s) sent, {flagged} flagged for review, {skipped} skipped.")
        return redirect(url_for("dashboard"))
    return {"sent": sent, "flagged": flagged, "skipped": skipped}, 200


@app.route("/progress")
def progress():
    client_id = current_client_id()
    client = db.get_client(client_id)
    if not client or not client["situation"]:
        return redirect(url_for("situation_selector"))

    steps = situations.get_steps(client["situation"])
    step_ids = [s["id"] for s in steps]
    statuses = db.get_step_statuses(client_id)

    completed = [s for s in steps if statuses.get(s["id"], {}).get("status") == "complete"]
    remaining = [s for s in steps if statuses.get(s["id"], {}).get("status") != "complete"]
    pct = int((len(completed) / len(steps)) * 100) if steps else 0

    return render_template(
        "progress.html",
        completed=completed,
        remaining=remaining,
        percent=pct,
        statuses=statuses,
        all_complete=(len(remaining) == 0),
        client_status=client["status"],
        nps_submitted=db.has_nps_response(client_id),
    )


@app.route("/nps", methods=["POST"])
def submit_nps():
    client_id = current_client_id()
    try:
        score = int(request.form.get("score"))
        if not 0 <= score <= 10:
            raise ValueError
    except (TypeError, ValueError):
        flash("Please select a score between 0 and 10.")
        return redirect(url_for("progress"))

    comment = request.form.get("comment", "").strip()
    comment_en, comment_lang = None, None
    if comment:
        try:
            comment_en, comment_lang = google_translate.translate_to_english(comment)
        except Exception:
            pass  # the dashboard/digest will just fall back to the original text

    db.add_nps_response(client_id, score, comment, comment_en, comment_lang)
    return redirect(url_for("nps_thank_you"))


@app.route("/nps/thank-you")
def nps_thank_you():
    return render_template("thank_you.html")


@app.route("/dashboard/login", methods=["GET", "POST"])
def dashboard_login():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        next_url = request.form.get("next", "")

        try:
            authenticated_email = supabase_auth.sign_in_with_password(email, password)
        except Exception as e:
            flash(str(e))
            return redirect(url_for("dashboard_login", next=next_url))

        try:
            if not supabase_auth.is_admin(authenticated_email):
                flash("Your account doesn't have dashboard access.")
                return redirect(url_for("dashboard_login", next=next_url))
        except Exception as e:
            flash(f"Couldn't verify dashboard access: {e}")
            return redirect(url_for("dashboard_login", next=next_url))

        session["is_admin"] = True
        session["admin_email"] = authenticated_email
        return redirect(_safe_next_url(next_url))

    return render_template("dashboard_login.html", next=request.args.get("next", ""))


@app.route("/dashboard/logout", methods=["POST"])
def dashboard_logout():
    session.pop("is_admin", None)
    session.pop("admin_email", None)
    return redirect(url_for("dashboard_login"))


@app.route("/dashboard")
@require_admin
def dashboard():
    summary = db.get_nps_summary()
    open_flags = db.get_open_intake_flags()
    pending_addenda = db.list_pending_addenda()
    return render_template(
        "dashboard.html",
        summary=summary,
        open_flags=open_flags,
        pending_addenda=pending_addenda,
        service_labels=situations.SERVICE_CODES,
    )


@app.route("/dashboard/flags/<flag_id>/resolve", methods=["POST"])
@require_admin
def dashboard_resolve_flag(flag_id):
    db.resolve_intake_flag(flag_id)
    return redirect(url_for("dashboard"))


@app.route("/dashboard/digest", methods=["POST"])
@require_admin
def dashboard_send_digest():
    admin_email = os.environ.get("ADMIN_EMAIL")
    if not admin_email:
        flash("Set the ADMIN_EMAIL environment variable to send the digest.")
        return redirect(url_for("dashboard"))

    summary = db.get_nps_summary()
    try:
        resend_email.send_nps_digest(summary, admin_email)
        flash(f"Digest sent to {admin_email}.")
    except Exception as e:
        flash(f"Couldn't send digest: {e}")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
