import os
import re
import sqlite3
from datetime import date, datetime, timedelta
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
    "due_time", "deadline_stage", "block_start", "block_minutes",
    "commit_date", "commit_changes", "commit_original", "estimate_minutes",
}
NOTE_FIELDS = {"id", "category", "text", "date", "task_id"}
COMPLETION_FIELDS = {"task_id", "title", "label", "completed_at", "completed_date"}
DELAY_FIELDS = {
    "id", "task_id", "title", "from_date", "from_time",
    "to_date", "to_time", "created_at", "created_date",
}
CHECKLIST_FIELDS = {"id", "text", "category", "created_date"}
DEFAULT_CHECKLIST = [
    ("Read yesterday's notes and reflection", "planning"),
    ("Review today's tasks and priorities", "planning"),
    ("Check emails", "work"),
    ("Check messages and notifications", "work"),
    ("Review calendar and meetings", "work"),
    ("Follow up on pending replies", "work"),
    ("Check assignments and deadlines", "study"),
    ("Review class notes", "study"),
    ("Check university portal and announcements", "study"),
    ("Revise or study for 30 minutes", "study"),
    ("Log progress and plan tomorrow", "wrap-up"),
]
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
                completed_at INTEGER,
                due_time TEXT,
                deadline_stage INTEGER DEFAULT 0
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY,
                category TEXT NOT NULL,
                text TEXT NOT NULL,
                date TEXT,
                task_id INTEGER
            )"""
        )
        # History of completed tasks. It survives deleting the task itself.
        db.execute(
            """CREATE TABLE IF NOT EXISTS completions (
                task_id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                label TEXT,
                completed_at INTEGER,
                completed_date TEXT NOT NULL
            )"""
        )
        # Daily checklist: the items, and which item was checked on which day
        first_time = db.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'checklist_items'"
        ).fetchone() is None
        db.execute(
            """CREATE TABLE IF NOT EXISTS checklist_items (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                category TEXT,
                created_date TEXT
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS checklist_log (
                item_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                PRIMARY KEY (item_id, date)
            )"""
        )
        if first_time:  # start with a useful set for a working professional / student
            db.executemany(
                "INSERT INTO checklist_items (id, text, category, created_date) "
                "VALUES (?, ?, ?, date('now', 'localtime'))",
                [(i + 1, text, category) for i, (text, category) in enumerate(DEFAULT_CHECKLIST)],
            )

        # Every time a task is rescheduled to a later date or time
        db.execute(
            """CREATE TABLE IF NOT EXISTS delays (
                id INTEGER PRIMARY KEY,
                task_id INTEGER,
                title TEXT NOT NULL,
                from_date TEXT NOT NULL,
                from_time TEXT,
                to_date TEXT NOT NULL,
                to_time TEXT,
                created_at INTEGER,
                created_date TEXT
            )"""
        )
        # Older databases: add the columns that were introduced later
        for table, column, ddl in (
            ("tasks", "due_time", "TEXT"),
            ("tasks", "deadline_stage", "INTEGER DEFAULT 0"),
            ("tasks", "block_start", "TEXT"),
            ("tasks", "block_minutes", "INTEGER"),
            ("tasks", "commit_date", "TEXT"),
            ("tasks", "commit_changes", "INTEGER DEFAULT 0"),
            ("tasks", "commit_original", "TEXT"),
            ("tasks", "estimate_minutes", "INTEGER"),
            ("notes", "task_id", "INTEGER"),
        ):
            existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


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


def check_estimate(values):
    """estimate_minutes is optional; when given it must be a whole number of minutes."""
    value = values.get("estimate_minutes")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
        return "estimate_minutes must be a whole number between 1 and 1440"
    return None


# ---------- Tasks API ----------

@app.get("/api/tasks")
def list_tasks():
    rows = get_db().execute("SELECT * FROM tasks ORDER BY id").fetchall()
    return jsonify([row_to_json(row) for row in rows])


@app.post("/api/tasks")
def create_task():
    task = clean(request.get_json(silent=True), TASK_FIELDS)
    task.pop("commit_changes", None)   # only the server decides these two
    task.pop("commit_original", None)
    estimate_error = check_estimate(task)
    if estimate_error:
        return jsonify(error=estimate_error), 400
    if not task.get("title") or task.get("status") not in VALID_STATUSES:
        return jsonify(error="A title and a valid status are required"), 400

    new_id = insert("tasks", task)
    return jsonify(row_to_json(fetch_one("tasks", new_id))), 201


@app.put("/api/tasks/<int:task_id>")
def update_task(task_id):
    changes = clean(request.get_json(silent=True), TASK_FIELDS)
    changes.pop("id", None)  # the id never changes
    estimate_error = check_estimate(changes)
    if estimate_error:
        return jsonify(error=estimate_error), 400
    if not changes:
        return jsonify(error="Nothing to update"), 400
    if "status" in changes and changes["status"] not in VALID_STATUSES:
        return jsonify(error="Invalid status"), 400
    existing = fetch_one("tasks", task_id)
    if existing is None:
        return jsonify(error="Task not found"), 404

    # Commitment deadline: once set, it can be changed exactly one time and never removed.
    changes.pop("commit_changes", None)
    changes.pop("commit_original", None)
    if "commit_date" in changes:
        new_commit, old_commit = changes["commit_date"], existing["commit_date"]
        if new_commit == old_commit:
            changes.pop("commit_date")
        elif old_commit:
            if not new_commit:
                return jsonify(error="A commitment deadline cannot be removed"), 400
            if (existing["commit_changes"] or 0) >= 1:
                return jsonify(error="The commitment deadline was already changed once"), 409
            changes["commit_original"] = old_commit
            changes["commit_changes"] = 1
    if not changes:
        return jsonify(row_to_json(existing))

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
    db.execute("UPDATE notes SET task_id = NULL WHERE task_id = ?", (task_id,))  # keep the notes
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


# ---------- Completion history API ----------

@app.get("/api/completions")
def list_completions():
    rows = get_db().execute("SELECT * FROM completions ORDER BY completed_at").fetchall()
    return jsonify([row_to_json(row) for row in rows])


@app.put("/api/completions/<int:task_id>")
def save_completion(task_id):
    data = clean(request.get_json(silent=True), COMPLETION_FIELDS)
    if not data.get("title") or not data.get("completed_date"):
        return jsonify(error="A title and a completed date are required"), 400

    db = get_db()
    db.execute(
        "INSERT OR REPLACE INTO completions (task_id, title, label, completed_at, completed_date) "
        "VALUES (?, ?, ?, ?, ?)",
        (task_id, data["title"], data.get("label"), data.get("completed_at"), data["completed_date"]),
    )
    db.commit()
    row = db.execute("SELECT * FROM completions WHERE task_id = ?", (task_id,)).fetchone()
    return jsonify(row_to_json(row))


@app.delete("/api/completions/<int:task_id>")
def delete_completion(task_id):
    db = get_db()
    db.execute("DELETE FROM completions WHERE task_id = ?", (task_id,))
    db.commit()
    return "", 204


# ---------- Delay history API ----------

@app.get("/api/delays")
def list_delays():
    rows = get_db().execute("SELECT * FROM delays ORDER BY id").fetchall()
    return jsonify([row_to_json(row) for row in rows])


@app.post("/api/delays")
def create_delay():
    delay = clean(request.get_json(silent=True), DELAY_FIELDS)
    if not (delay.get("title") and delay.get("from_date") and delay.get("to_date")):
        return jsonify(error="A title, from date and to date are required"), 400

    new_id = insert("delays", delay)
    return jsonify(row_to_json(fetch_one("delays", new_id))), 201


# ---------- Daily checklist API ----------

DATE_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}")


@app.get("/api/checklist")
def get_checklist():
    db = get_db()
    items = db.execute("SELECT * FROM checklist_items ORDER BY id").fetchall()
    checks = db.execute("SELECT * FROM checklist_log").fetchall()
    return jsonify(
        items=[row_to_json(row) for row in items],
        checks=[row_to_json(row) for row in checks],
    )


@app.post("/api/checklist/items")
def create_checklist_item():
    item = clean(request.get_json(silent=True), CHECKLIST_FIELDS)
    if not item.get("text"):
        return jsonify(error="Text is required"), 400

    new_id = insert("checklist_items", item)
    return jsonify(row_to_json(fetch_one("checklist_items", new_id))), 201


@app.delete("/api/checklist/items/<int:item_id>")
def delete_checklist_item(item_id):
    db = get_db()
    db.execute("DELETE FROM checklist_log WHERE item_id = ?", (item_id,))
    db.execute("DELETE FROM checklist_items WHERE id = ?", (item_id,))
    db.commit()
    return "", 204


@app.put("/api/checklist/checks/<int:item_id>/<date>")
def check_item(item_id, date):
    if not DATE_PATTERN.fullmatch(date):
        return jsonify(error="Date must look like 2026-10-25"), 400
    db = get_db()
    db.execute("INSERT OR IGNORE INTO checklist_log (item_id, date) VALUES (?, ?)", (item_id, date))
    db.commit()
    return jsonify(itemId=item_id, date=date)


@app.delete("/api/checklist/checks/<int:item_id>/<date>")
def uncheck_item(item_id, date):
    db = get_db()
    db.execute("DELETE FROM checklist_log WHERE item_id = ? AND date = ?", (item_id, date))
    db.commit()
    return "", 204


# ---------- Snapshot export (read-only) ----------

def build_snapshot(include_notes=False):
    """One JSON document with everything needed to plan from the board.
    Notes are personal, so they are left out unless include_notes is True."""
    db = get_db()
    today = date.today()
    today_iso = today.isoformat()
    now_time = datetime.now().strftime("%H:%M")

    def all_rows(table, order="id"):  # table and order are fixed strings, never user input
        return [row_to_json(row) for row in db.execute(f"SELECT * FROM {table} ORDER BY {order}")]

    tasks = all_rows("tasks")
    delays = all_rows("delays")
    since = (today - timedelta(days=30)).isoformat()
    checks = [
        row_to_json(row)
        for row in db.execute("SELECT * FROM checklist_log WHERE date >= ? ORDER BY date", (since,))
    ]

    def brief(task):
        keys = ("id", "title", "label", "status", "dueDate", "dueTime", "commitDate")
        return {key: task.get(key) for key in keys}

    def is_overdue(task):
        due = task.get("dueDate")
        if not due:
            return False
        if due < today_iso:
            return True
        return due == today_iso and bool(task.get("dueTime")) and task["dueTime"] < now_time

    open_tasks = [task for task in tasks if task["status"] != "done"]
    overdue = [brief(task) for task in open_tasks if is_overdue(task)]

    limit = (today + timedelta(days=7)).isoformat()
    commitments = [
        {
            **brief(task),
            "daysLeft": (date.fromisoformat(task["commitDate"]) - today).days,
            "commitChanges": task.get("commitChanges") or 0,
        }
        for task in open_tasks
        if task.get("commitDate") and task["commitDate"] <= limit
    ]
    commitments.sort(key=lambda task: task["daysLeft"])

    delayed = {}
    for delay in delays:
        entry = delayed.setdefault(
            delay["taskId"], {"taskId": delay["taskId"], "title": delay["title"], "delays": 0}
        )
        entry["delays"] += 1
    status_by_id = {task["id"]: task["status"] for task in tasks}
    delayed_twice = [
        {**entry, "status": status_by_id.get(entry["taskId"], "deleted")}
        for entry in delayed.values()
        if entry["delays"] >= 2
    ]

    counts_by_label = {}
    for task in tasks:
        row = counts_by_label.setdefault(task.get("label") or "(none)", {"todo": 0, "progress": 0, "done": 0})
        row[task["status"]] = row.get(task["status"], 0) + 1

    snapshot = {
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "tasks": tasks,
        "delays": delays,
        "completions": all_rows("completions", "completed_at"),
        "checklist": {"items": all_rows("checklist_items"), "checks": checks},
        "derived": {
            "overdue": overdue,
            "commitmentsDueIn7Days": commitments,
            "delayedTwiceOrMore": delayed_twice,
            "countsByLabel": counts_by_label,
        },
    }
    if include_notes:
        snapshot["notes"] = all_rows("notes")
    return snapshot


@app.get("/api/export")
def export_snapshot():
    include_notes = request.args.get("include_notes", "").lower() in {"1", "true", "yes"}
    return jsonify(build_snapshot(include_notes))


if __name__ == "__main__":
    init_db()
    app.run(host="127.0.0.1", port=5000, debug=os.environ.get("BOARD_DEBUG") == "1")