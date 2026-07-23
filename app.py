import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

DATA_FILE = "responses.json"


def load_responses():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {"skills": [], "nps": []}
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
