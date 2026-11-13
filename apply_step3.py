#!/usr/bin/env python3
"""Step 3: add GET /api/export to backend/app.py.

Run from the repo root:  python3 apply_step3.py
Checks every edit first; if the file does not look as expected nothing is written.
Running it twice is safe.
"""
import sys
from pathlib import Path

path = Path(__file__).resolve().parent / "backend" / "app.py"
if not path.exists():
    sys.exit("backend/app.py not found. Run this script from the repo root.")
text = path.read_text(encoding="utf-8")
if "/api/export" in text:
    print("backend/app.py: already patched, skipped")
    sys.exit(0)

EDITS = [
    (
        "import sqlite3\nfrom pathlib import Path\n",
        "import sqlite3\nfrom datetime import date, datetime, timedelta\nfrom pathlib import Path\n",
    ),
    (
        'if __name__ == "__main__":',
        '''# ---------- Snapshot export (read-only) ----------

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


if __name__ == "__main__":''',
    ),
]

for old, new in EDITS:
    if text.count(old) != 1:
        sys.exit(f"backend/app.py: expected exactly one match for:\n{old}\nNothing was written.")
    text = text.replace(old, new)

path.write_text(text, encoding="utf-8")
print("backend/app.py: patched (2 edits)")
print("Done. Review with: git diff --stat")
