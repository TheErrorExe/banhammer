from flask import Flask, render_template, request, redirect, url_for, flash
from flask_bootstrap import Bootstrap
import sqlite3
import os
import glob

app = Flask(__name__)
app.secret_key = os.urandom(24)
Bootstrap(app)

DATABASE_TYPE = "sqlite"
DATABASE_PATTERN = "server_*.db"

def get_database_files():
    return glob.glob(DATABASE_PATTERN)

def get_db_connection(db_name):
    conn = sqlite3.connect(db_name, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def load_cases():
    cases = []
    for db_file in get_database_files():
        conn = get_db_connection(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM cases")
        cases.extend(cursor.fetchall())
        conn.close()
    return cases

def load_warnings():
    warnings = []
    for db_file in get_database_files():
        conn = get_db_connection(db_file)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM warnings")
        warnings.extend(cursor.fetchall())
        conn.close()
    return warnings

def delete_case(case_id):
    for db_file in get_database_files():
        conn = get_db_connection(db_file)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM cases WHERE case_id = ?", (case_id,))
        conn.commit()
        conn.close()

def update_case_status(case_id, status):
    for db_file in get_database_files():
        conn = get_db_connection(db_file)
        cursor = conn.cursor()
        cursor.execute("UPDATE cases SET status = ? WHERE case_id = ?", (status, case_id))
        conn.commit()
        conn.close()

def add_warning(user_id, reason, guild_id):
    db_name = f"server_{guild_id}.db"
    if os.path.exists(db_name):
        conn = get_db_connection(db_name)
        cursor = conn.cursor()
        cursor.execute("INSERT INTO warnings (user_id, reason, guild_id) VALUES (?, ?, ?)", (user_id, reason, guild_id))
        conn.commit()
        conn.close()

def remove_warning(user_id, index, guild_id):
    db_name = f"server_{guild_id}.db"
    if os.path.exists(db_name):
        conn = get_db_connection(db_name)
        cursor = conn.cursor()
        cursor.execute("SELECT reason FROM warnings WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        warnings = cursor.fetchall()
        if 0 < index <= len(warnings):
            cursor.execute("DELETE FROM warnings WHERE user_id = ? AND reason = ? AND guild_id = ?", (user_id, warnings[index - 1][0], guild_id))
            conn.commit()
        conn.close()

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
        user_id = int(request.form.get("user_id"))
        reason = request.form.get("reason")
        guild_id = int(request.form.get("guild_id"))
        add_warning(user_id, reason, guild_id)
        flash("Warning added successfully!", "success")
        return redirect(url_for("warnings"))
    return render_template("add_warning.html")

@app.route("/warnings/delete/<user_id>/<index>", methods=["POST"])
def delete_warning_route(user_id, index):
    guild_id = 0
    remove_warning(int(user_id), int(index), guild_id)
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
