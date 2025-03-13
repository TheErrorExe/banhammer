from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bootstrap import Bootstrap
from pymongo import MongoClient
import sqlite3
import os

app = Flask(__name__)
app.secret_key = os.urandom(24)
Bootstrap(app)

DATABASE_TYPE = "sqlite"
DATABASE_NAME = "modbot.db"
MONGO_URI = "mongodb://localhost:27017"

if DATABASE_TYPE == "sqlite":
    conn = sqlite3.connect(DATABASE_NAME, check_same_thread=False)
    cursor = conn.cursor()
elif DATABASE_TYPE == "mongodb":
    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client["modbot"]
    cases_collection = db["cases"]
    warnings_collection = db["warnings"]

def load_cases():
    if DATABASE_TYPE == "sqlite":
        cursor.execute("SELECT * FROM cases")
        cases = cursor.fetchall()
    elif DATABASE_TYPE == "mongodb":
        cases = list(cases_collection.find())
    return cases

def load_warnings():
    if DATABASE_TYPE == "sqlite":
        cursor.execute("SELECT * FROM warnings")
        warnings = cursor.fetchall()
    elif DATABASE_TYPE == "mongodb":
        warnings = list(warnings_collection.find())
    return warnings

def delete_case(case_id):
    if DATABASE_TYPE == "sqlite":
        cursor.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        conn.commit()
    elif DATABASE_TYPE == "mongodb":
        cases_collection.delete_one({"_id": case_id})

def update_case_status(case_id, status):
    if DATABASE_TYPE == "sqlite":
        cursor.execute("UPDATE cases SET status = ? WHERE case_id = ?", (status, case_id))
        conn.commit()
    elif DATABASE_TYPE == "mongodb":
        cases_collection.update_one({"_id": case_id}, {"$set": {"status": status}})

def add_warning(user_id, reason, guild_id):
    if DATABASE_TYPE == "sqlite":
        cursor.execute("INSERT INTO warnings (user_id, reason, guild_id) VALUES (?, ?, ?)", (user_id, reason, guild_id))
        conn.commit()
    elif DATABASE_TYPE == "mongodb":
        warnings_collection.insert_one({"user_id": user_id, "reason": reason, "guild_id": guild_id})

def remove_warning(user_id, index, guild_id):
    if DATABASE_TYPE == "sqlite":
        cursor.execute("SELECT reason FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        warnings = cursor.fetchall()
        if 0 < index <= len(warnings):
            cursor.execute("DELETE FROM warnings WHERE user_id = ? AND reason = ? AND guild_id = ?", (user_id, warnings[index - 1][0], guild_id))
            conn.commit()
    elif DATABASE_TYPE == "mongodb":
        warnings = list(warnings_collection.find({"user_id": user_id, "guild_id": guild_id}))
        if 0 < index <= len(warnings):
            warnings_collection.delete_one({"_id": warnings[index - 1]["_id"]})

@app.route("/")
def index():
    cases = load_cases()
    warnings = load_warnings()
    return render_template("index.html", cases=cases, warnings=warnings)

@app.route("/cases")
def cases():
    cases = load_cases()
    return render_template("cases.html", cases=cases)

@app.route("/cases/delete/<case_id>", methods=["POST"])
def delete_case_route(case_id):
    delete_case(case_id)
    flash("Case deleted successfully!", "success")
    return redirect(url_for("cases"))

@app.route("/cases/close/<case_id>", methods=["POST"])
def close_case_route(case_id):
    update_case_status(case_id, "closed")
    flash("Case closed successfully!", "success")
    return redirect(url_for("cases"))

@app.route("/cases/reopen/<case_id>", methods=["POST"])
def reopen_case_route(case_id):
    update_case_status(case_id, "open")
    flash("Case reopened successfully!", "success")
    return redirect(url_for("cases"))

@app.route("/warnings")
def warnings():
    warnings = load_warnings()
    return render_template("warnings.html", warnings=warnings)

@app.route("/warnings/add", methods=["GET", "POST"])
def add_warning_route():
    if request.method == "POST":
        user_id = request.form.get("user_id")
        reason = request.form.get("reason")
        guild_id = request.form.get("guild_id")
        add_warning(user_id, reason, guild_id)
        flash("Warning added successfully!", "success")
        return redirect(url_for("warnings"))
    return render_template("add_warning.html")

@app.route("/warnings/delete/<user_id>/<index>", methods=["POST"])
def delete_warning_route(user_id, index):
    remove_warning(user_id, int(index), 0)
    flash("Warning deleted successfully!", "success")
    return redirect(url_for("warnings"))

@app.route("/settings", methods=["GET", "POST"])
def settings():
    if request.method == "POST":
        new_prefix = request.form.get("prefix")
        flash("Settings updated successfully!", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
