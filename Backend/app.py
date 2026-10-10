import re
import sqlite3
from pathlib import Path

from flask import Flask, g, jsonify, request

DB_PATH = Path(__file__).resolve().parent / "board.db"

# static_folder points at the frontend, so Flask serves index.html, index.js, etc.
app = Flask(__name__, static_folder="../frontend", static_url_path="")

# Only these columns may ever be written. Column names go into the SQL text,
# so they must come from this whitelist, never straight from the request.
TASK_FIELDS = {
    "id", "title", "description", "label", "status",
    "due_date", "started_at", "last_reminder_at", "completed_at",
}
NOTE_FIELDS = {"id", "category", "text", "date"}
VALID_STATUSES = {"todo", "progress", "done"}


# ---------- Database ----------

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row  # rows behave like dicts
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                description TEXT,
                label TEXT,
                status TEXT NOT NULL,
                due_date TEXT,
                started_at INTEGER,
                last_reminder_at INTEGER,
                completed_at INTEGER
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                text TEXT NOT NULL,
                date TEXT
            )"""
        )


# ---------- Helpers: JavaScript uses camelCase, the database uses snake_case ----------

def to_camel(name):
    first, *rest = name.split("_")
    return first + "".join(part.title() for part in rest)


def to_snake(name):
    return re.sub(r"([A-Z])", lambda match: "_" + match.group(1).lower(), name)


def row_to_json(row):
    return {to_camel(key): row[key] for key in row.keys()}


def clean(data, allowed):
    """Convert keys to snake_case and drop anything not in the whitelist."""
    converted = {to_snake(key): value for key, value in (data or {}).items()}
    return {key: value for key, value in converted.items() if key in allowed}


def fetch_one(table, item_id):
    return get_db().execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()


def insert(table, values):
    columns = ", ".join(values)
    placeholders = ", ".join("?" for _ in values)
    db = get_db()
    cursor = db.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders})", list(values.values())
    )
    db.commit()
    return cursor.lastrowid


# ---------- Pages ----------

@app.get("/")
def index():
    return app.send_static_file("index.html")


# ---------- Tasks API ----------

@app.get("/api/tasks")
def list_tasks():
    rows = get_db().execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return jsonify([row_to_json(row) for row in rows])


@app.post("/api/tasks")
def create_task():
    task = clean(request.get_json(silent=True), TASK_FIELDS)
    if not task.get("title") or task.get("status") not in VALID_STATUSES:
        return jsonify(error="A title and a valid status are required"), 400

    new_id = insert("tasks", task)
    return jsonify(row_to_json(fetch_one("tasks", new_id))), 201


@app.put("/api/tasks/<int:task_id>")
def update_task(task_id):
    changes = clean(request.get_json(silent=True), TASK_FIELDS)
    changes.pop("id", None)  # the id never changes
    if not changes:
        return jsonify(error="Nothing to update"), 400
    if "status" in changes and changes["status"] not in VALID_STATUSES:
        return jsonify(error="Invalid status"), 400
    if fetch_one("tasks", task_id) is None:
        return jsonify(error="Task not found"), 404

    assignments = ", ".join(f"{column} = ?" for column in changes)
    db = get_db()
    db.execute(
        f"UPDATE tasks SET {assignments} WHERE id = ?", [*changes.values(), task_id]
    )
    db.commit()
    return jsonify(row_to_json(fetch_one("tasks", task_id)))


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    db = get_db()
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return "", 204


# ---------- Notes API ----------

@app.get("/api/notes")
def list_notes():
    rows = get_db().execute("SELECT * FROM notes ORDER BY id DESC").fetchall()
    return jsonify([row_to_json(row) for row in rows])


@app.post("/api/notes")
def create_note():
    note = clean(request.get_json(silent=True), NOTE_FIELDS)
    if not note.get("text") or not note.get("category"):
        return jsonify(error="A category and text are required"), 400

    new_id = insert("notes", note)
    return jsonify(row_to_json(fetch_one("notes", new_id))), 201


@app.delete("/api/notes/<int:note_id>")
def delete_note(note_id):
    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
    db.commit()
    return "", 204


if __name__ == "__main__":
    init_db()
    app.run(debug=True)