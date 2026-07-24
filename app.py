import os
from flask import Flask, render_template, request, redirect, url_for, session, flash

import db
import situations
from integrations import pandadoc, financial_cents

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

db.init_db()


def current_client_id():
    if "client_id" not in session:
        session["client_id"] = db.create_client()
    return session["client_id"]


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
                statuses = db.get_step_statuses(client_id)
                conn = db.get_db()
                conn.execute(
                    "UPDATE step_status SET status = 'pending_verification', external_ref = ? "
                    "WHERE client_id = ? AND step_id = ?",
                    (document_id, client_id, step_id),
                )
                conn.commit()
                conn.close()
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

        return redirect(url_for("step_detail", step_id=step_id))

    if step["type"] == "esign" and step_status == "pending_verification":
        external_ref = statuses.get(step_id, {}).get("external_ref")
        if external_ref:
            try:
                if pandadoc.is_signed(external_ref):
                    db.complete_step(client_id, step_id, step_ids, external_ref=external_ref)
                    return redirect(url_for("checklist"))
            except Exception:
                pass

    uploaded_files = db.get_uploaded_files(client_id, step_id) if step["type"] == "upload" else []

    return render_template(
        "step_detail.html",
        step=step,
        status=step_status,
        uploaded_files=uploaded_files,
    )


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
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
