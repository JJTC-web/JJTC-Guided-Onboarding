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
    return {"skills": [], "nps": []}


def save_response(kind, entry):
    data = load_responses()
    entry["timestamp"] = datetime.utcnow().isoformat()
    data[kind].append(entry)
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


@app.route("/")
def home():
    return render_template("home.html")


@app.route("/skills", methods=["GET", "POST"])
def skills():
    if request.method == "POST":
        entry = {
            "name": request.form.get("name", ""),
            "coding": request.form.get("coding"),
            "problem_solving": request.form.get("problem_solving"),
            "ai_tools": request.form.get("ai_tools"),
            "confidence": request.form.get("confidence"),
            "comments": request.form.get("comments", ""),
        }
        save_response("skills", entry)
        return redirect(url_for("thanks"))
    return render_template("skills.html")


@app.route("/nps", methods=["GET", "POST"])
def nps():
    if request.method == "POST":
        entry = {
            "name": request.form.get("name", ""),
            "score": request.form.get("score"),
            "comments": request.form.get("comments", ""),
        }
        save_response("nps", entry)
        return redirect(url_for("thanks"))
    return render_template("nps.html")


@app.route("/thanks")
def thanks():
    return render_template("thanks.html")


@app.route("/results")
def results():
    data = load_responses()
    return render_template("results.html", data=data)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
