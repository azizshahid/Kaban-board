#!/usr/bin/env python3
"""Import tasks from a JSON file into the running board (local only).

    python3 scripts/import_tasks.py plan.json --dry-run   # check first, writes nothing
    python3 scripts/import_tasks.py plan.json             # create the new tasks
    cat plan.json | python3 scripts/import_tasks.py -     # read from stdin

The file is a JSON array. Every field except title is optional:
  [{"title": "...", "label": "Agency", "status": "todo|progress|done",
    "description": "...", "dueDate": "2026-11-20", "dueTime": "17:30",
    "commitDate": "2026-12-01", "blockStart": "09:00", "blockMinutes": 90,
    "estimateMinutes": 120}]

Rules:
  * Duplicates (same title + label, ignoring case) are skipped, on the board or in the file.
  * The import only CREATES tasks. Existing tasks are never modified, so a commitment
    deadline can never be changed or removed by an import. A new task's commitDate starts
    with its one allowed change still unused.
  * If any row is invalid, nothing is written unless you pass --skip-invalid.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

FIELDS = {
    "title", "label", "status", "description", "dueDate", "dueTime",
    "commitDate", "blockStart", "blockMinutes", "estimateMinutes",
}
STATUS_ALIASES = {
    "todo": "todo", "to do": "todo", "to-do": "todo",
    "progress": "progress", "in progress": "progress", "in-progress": "progress", "inprogress": "progress",
    "done": "done", "completed": "done", "complete": "done",
}


# ---------------------------------------------------------------- local API
def call(base, method, path, body=None):
    request = urllib.request.Request(
        base + path,
        data=None if body is None else json.dumps(body).encode(),
        method=method,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        try:
            detail = json.loads(detail).get("error", detail)
        except ValueError:
            pass
        raise RuntimeError(f"{method} {path} returned {error.code}: {detail}") from None
    except (urllib.error.URLError, OSError) as error:
        sys.exit(f"Could not reach {base} ({error}). Is ./start-board.sh running?")


# ---------------------------------------------------------------- validation
def valid_date(value):
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return len(value) == 10
    except (TypeError, ValueError):
        return False


def valid_time(value):
    try:
        datetime.strptime(value, "%H:%M")
        return len(value) == 5
    except (TypeError, ValueError):
        return False


def whole(value, low, high):
    return isinstance(value, int) and not isinstance(value, bool) and low <= value <= high


def clean_row(row):
    """Return (task_dict, warnings) or raise ValueError with a readable reason."""
    if not isinstance(row, dict):
        raise ValueError("row must be a JSON object")
    warnings = []
    unknown = sorted(set(row) - FIELDS)
    if unknown:
        warnings.append(f"ignored unknown field(s): {', '.join(unknown)}")

    title = row.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title is required")
    title = title.strip()
    if len(title) > 200:
        raise ValueError("title is longer than 200 characters")

    label = row.get("label")
    if label is not None and not isinstance(label, str):
        raise ValueError("label must be text")
    label = (label or "").strip() or "General"  # same default as the board's form

    status = STATUS_ALIASES.get(str(row.get("status", "todo")).strip().lower())
    if status is None:
        raise ValueError(f"status must be todo, progress or done (got {row.get('status')!r})")

    description = row.get("description") or ""
    if not isinstance(description, str):
        raise ValueError("description must be text")

    task = {"title": title, "label": label, "status": status, "description": description.strip()}

    for key in ("dueDate", "commitDate"):
        if row.get(key) is not None:
            if not valid_date(row[key]):
                raise ValueError(f"{key} must look like 2026-11-20")
            task[key] = row[key]
    for key in ("dueTime", "blockStart"):
        if row.get(key) is not None:
            if not valid_time(row[key]):
                raise ValueError(f"{key} must look like 09:30 (24-hour)")
            task[key] = row[key]

    if "dueTime" in task and "dueDate" not in task:
        raise ValueError("dueTime needs a dueDate")
    if "dueDate" in task and "commitDate" in task and task["dueDate"] > task["commitDate"]:
        raise ValueError("dueDate is after commitDate")

    if row.get("blockMinutes") is not None and "blockStart" not in task:
        raise ValueError("blockMinutes needs a blockStart")
    if "blockStart" in task:
        if "dueDate" not in task:
            raise ValueError("a time block needs a dueDate (the block happens on that day)")
        minutes = row.get("blockMinutes", 30)
        if not whole(minutes, 5, 1440):
            raise ValueError("blockMinutes must be a whole number from 5 to 1440")
        task["blockMinutes"] = minutes

    if row.get("estimateMinutes") is not None:
        if not whole(row["estimateMinutes"], 1, 1440):
            raise ValueError("estimateMinutes must be a whole number from 1 to 1440")
        task["estimateMinutes"] = row["estimateMinutes"]

    return task, warnings


def show(verb, text):
    print(f"  {verb:<13}{text}")


def key_of(title, label):
    return (title.strip().casefold(), (label or "").strip().casefold())


# ---------------------------------------------------------------- main
def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("file", help="JSON file, or - for stdin")
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="board address (local only)")
    parser.add_argument("--dry-run", action="store_true", help="show what would happen, write nothing")
    parser.add_argument("--skip-invalid", action="store_true", help="import the valid rows even if some are invalid")
    args = parser.parse_args()

    host = urlparse(args.url).hostname
    if host not in {"127.0.0.1", "localhost"}:
        sys.exit(f"Refusing to import to {host}: this script only talks to this machine.")
    base = args.url.rstrip("/") + "/api"

    try:
        text = sys.stdin.read() if args.file == "-" else open(args.file, encoding="utf-8").read()
        rows = json.loads(text)
    except (OSError, ValueError) as error:
        sys.exit(f"Could not read {args.file}: {error}")
    if not isinstance(rows, list):
        sys.exit("The file must contain a JSON array of tasks: [ {...}, {...} ]")

    existing = {key_of(t["title"], t.get("label")) for t in call(base, "GET", "/tasks")}
    seen, to_create, on_board, repeated, invalid = set(), [], 0, 0, 0

    print(f"Read {len(rows)} row(s) from {'stdin' if args.file == '-' else args.file}")
    for number, row in enumerate(rows, start=1):
        try:
            task, warnings = clean_row(row)
        except ValueError as error:
            invalid += 1
            show("invalid", f"row {number}: {error}")
            continue
        for warning in warnings:
            show("note", f"row {number}: {warning}")

        key = key_of(task["title"], task["label"])
        name = f"{task['title']} [{task['label']}]"
        if key in existing:
            on_board += 1
            show("skip", f"already on the board: {name}")
        elif key in seen:
            repeated += 1
            show("skip", f"repeated in this file: {name}")
        else:
            seen.add(key)
            to_create.append(task)
            show("would create" if args.dry_run else "create", name)

    created = failed = 0
    stop = invalid and not args.skip_invalid
    if not args.dry_run and not stop:
        now = int(time.time() * 1000)
        for task in to_create:
            payload = dict(task, deadlineStage=0)
            if task["status"] == "progress":
                payload["startedAt"] = now  # same as the board does when a task is started
            if task["status"] == "done":
                payload["completedAt"] = now
            try:
                saved = call(base, "POST", "/tasks", payload)
                if task["status"] == "done":  # keep the completion history in step with the board
                    call(base, "PUT", f"/completions/{saved['id']}", {
                        "taskId": saved["id"], "title": task["title"], "label": task["label"],
                        "completedAt": now, "completedDate": datetime.now().strftime("%Y-%m-%d"),
                    })
                created += 1
            except RuntimeError as error:
                failed += 1
                show("FAILED", f"{task['title']}: {error}")

    skipped = on_board + repeated
    print()
    if args.dry_run:
        print(f"Dry run: {len(to_create)} to create, {skipped} skipped ({on_board} on the board, "
              f"{repeated} repeated in the file), {invalid} invalid. Nothing was written.")
    elif stop:
        print(f"Nothing written: {invalid} invalid row(s). Fix them, or use --skip-invalid to import the rest.")
    else:
        print(f"Created {created}, skipped {skipped} ({on_board} on the board, {repeated} repeated in the file), "
              f"{invalid} invalid, {failed} failed.")
    print("Existing tasks were not modified.")
    sys.exit(2 if invalid and (args.dry_run or stop) else 1 if failed else 0)


if __name__ == "__main__":
    main()
