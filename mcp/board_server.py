#!/usr/bin/env python3
"""Read-only MCP server for the Productivity Board (stdio transport).

It lets Claude READ deadlines, daily plans and weekly roadmaps from the board, which stays
the single source of truth. There are no write tools. The only network call it makes is
one read of http://127.0.0.1:5000/api/export, and it never asks for your notes.

Run it by path (not with `python -m`):  .venv-linux/bin/python mcp/board_server.py
Nothing may be printed to stdout here: stdout is the MCP protocol channel. Logs go to stderr.
"""
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

BOARD_URL = os.environ.get("BOARD_URL", "http://127.0.0.1:5000").rstrip("/")
if urlparse(BOARD_URL).hostname not in {"127.0.0.1", "localhost"}:
    sys.exit(f"board_server: refusing {BOARD_URL}. This server only talks to this machine.")

WIP_LIMIT = 3  # same focus limit as the board
STATUSES = {"todo": "todo", "to do": "todo", "progress": "progress", "in progress": "progress",
            "in-progress": "progress", "done": "done", "completed": "done"}
TASK_FIELDS = ("id", "title", "label", "status", "description", "dueDate", "dueTime", "commitDate",
               "commitChanges", "blockStart", "blockMinutes", "estimateMinutes")

READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)

mcp = MCPServer(
    "productivity-board",
    instructions=(
        "Read-only view of the user's Productivity Board: tasks, deadlines, delay history and weekly "
        "plans. It cannot create or change anything, and personal notes are never exposed. "
        "Dates are YYYY-MM-DD, times are 24-hour HH:MM, estimates and blocks are in minutes."
    ),
)


# ---------------------------------------------------------------- reading the board
# Expected problems are raised as ToolError so Claude reads the message (no crash, no traceback).
def snapshot() -> dict[str, Any]:
    """The one and only request this server makes: a plain read of the export (no notes)."""
    request = urllib.request.Request(f"{BOARD_URL}/api/export", method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise ToolError(
            f"Cannot read the board at {BOARD_URL} ({error}). Is it running? Start it with ./start-board.sh"
        ) from None


def parse_date(value: str | None, name: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise ToolError(f"{name} must look like 2026-11-20") from None


def delay_counts(snap: dict[str, Any]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for delay in snap["delays"]:
        counts[delay["taskId"]] = counts.get(delay["taskId"], 0) + 1
    return counts


def slim(task: dict[str, Any], counts: dict[int, int]) -> dict[str, Any]:
    out = {key: task.get(key) for key in TASK_FIELDS}
    out["delayCount"] = counts.get(task["id"], 0)
    return out


def start_key(task: dict[str, Any]) -> tuple[str, str]:
    return (task.get("dueDate") or "9999-99-99", task.get("blockStart") or task.get("dueTime") or "99:99")


def block_end(start: str, minutes: int | None) -> str:
    hours, mins = (int(part) for part in start.split(":"))
    total = hours * 60 + mins + (minutes or 30)
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


# ---------------------------------------------------------------- tools
@mcp.tool(annotations=READ_ONLY)
def list_tasks(label: str | None = None, status: str | None = None, due_before: str | None = None) -> dict[str, Any]:
    """List tasks, optionally filtered.

    label: exact label, ignoring case (for example "Agency").
    status: todo, progress or done.
    due_before: YYYY-MM-DD; only tasks due strictly before that date (tasks with no date are excluded).
    """
    snap = snapshot()
    counts = delay_counts(snap)
    wanted_status = None
    if status is not None:
        wanted_status = STATUSES.get(status.strip().lower())
        if wanted_status is None:
            raise ToolError("status must be todo, progress or done")
    limit = parse_date(due_before, "due_before").isoformat() if due_before is not None else None

    tasks = snap["tasks"]
    if label is not None:
        tasks = [t for t in tasks if (t.get("label") or "").casefold() == label.strip().casefold()]
    if wanted_status:
        tasks = [t for t in tasks if t["status"] == wanted_status]
    if limit:
        tasks = [t for t in tasks if t.get("dueDate") and t["dueDate"] < limit]

    tasks = sorted(tasks, key=start_key)
    return {"count": len(tasks), "tasks": [slim(t, counts) for t in tasks]}


@mcp.tool(annotations=READ_ONLY)
def overdue() -> dict[str, Any]:
    """Open tasks that are past their due date (or past their due time today), most late first."""
    snap = snapshot()
    counts = delay_counts(snap)
    by_id = {t["id"]: t for t in snap["tasks"]}
    today = date.today()
    rows = []
    for entry in snap["derived"]["overdue"]:
        task = slim(by_id[entry["id"]], counts)
        task["daysLate"] = (today - parse_date(task["dueDate"], "dueDate")).days
        rows.append(task)
    rows.sort(key=lambda t: -t["daysLate"])
    return {"count": len(rows), "tasks": rows}


@mcp.tool(annotations=READ_ONLY)
def week_plan(start_date: str | None = None) -> dict[str, Any]:
    """Seven days of the plan starting at start_date (default: today).

    Per day: open tasks, time blocks, commitment deadlines, what was completed and what was delayed
    from that day, with estimate totals. Also overdue carry-over, In Progress count (limit 3) and
    open tasks delayed twice or more.
    """
    snap = snapshot()
    counts = delay_counts(snap)
    start = parse_date(start_date, "start_date") if start_date else date.today()
    open_tasks = [t for t in snap["tasks"] if t["status"] != "done"]

    days = []
    for offset in range(7):
        iso = (start + timedelta(days=offset)).isoformat()
        due = sorted((t for t in open_tasks if t.get("dueDate") == iso), key=start_key)
        blocks = [
            {"taskId": t["id"], "title": t["title"], "start": t["blockStart"],
             "end": block_end(t["blockStart"], t.get("blockMinutes")), "minutes": t.get("blockMinutes") or 30}
            for t in due if t.get("blockStart")
        ]
        days.append({
            "date": iso,
            "weekday": (start + timedelta(days=offset)).strftime("%A"),
            "openTasks": [slim(t, counts) for t in due],
            "timeBlocks": blocks,
            "commitmentDeadlines": [
                {"taskId": t["id"], "title": t["title"], "status": t["status"]}
                for t in snap["tasks"] if t.get("commitDate") == iso
            ],
            "completed": [c["title"] for c in snap["completions"] if c.get("completedDate") == iso],
            "delayedFromThisDay": [
                {"taskId": d["taskId"], "title": d["title"], "movedTo": d["toDate"]}
                for d in snap["delays"] if d["fromDate"] == iso
            ],
            "estimatedMinutes": sum(t.get("estimateMinutes") or 0 for t in due),
            "blockedMinutes": sum(b["minutes"] for b in blocks),
            "tasksWithoutEstimate": sum(1 for t in due if not t.get("estimateMinutes")),
        })

    carry = [t for t in open_tasks if t.get("dueDate") and t["dueDate"] < start.isoformat()]
    in_progress = sum(1 for t in snap["tasks"] if t["status"] == "progress")
    return {
        "start": start.isoformat(),
        "end": (start + timedelta(days=6)).isoformat(),
        "days": days,
        "totals": {
            "openTasks": sum(len(d["openTasks"]) for d in days),
            "estimatedMinutes": sum(d["estimatedMinutes"] for d in days),
            "tasksWithoutEstimate": sum(d["tasksWithoutEstimate"] for d in days),
        },
        "overdueCarryOver": [slim(t, counts) for t in sorted(carry, key=start_key)],
        "inProgress": {"count": in_progress, "limit": WIP_LIMIT, "overLimit": in_progress > WIP_LIMIT},
        "delayedTwiceOrMore": [slim(t, counts) for t in open_tasks if counts.get(t["id"], 0) >= 2],
    }


@mcp.tool(annotations=READ_ONLY)
def commitments_due(days: int = 7) -> dict[str, Any]:
    """Open tasks whose commitment deadline is within the next `days` days (0 to 365), including
    ones already passed. A commitment deadline can be changed only once; deadlineLocked shows if it was."""
    if not 0 <= days <= 365:
        raise ToolError("days must be between 0 and 365")
    snap = snapshot()
    counts = delay_counts(snap)
    today = date.today()
    limit = (today + timedelta(days=days)).isoformat()

    rows = []
    for task in snap["tasks"]:
        if task["status"] == "done" or not task.get("commitDate") or task["commitDate"] > limit:
            continue
        row = slim(task, counts)
        row["daysLeft"] = (parse_date(task["commitDate"], "commitDate") - today).days
        row["deadlineLocked"] = (task.get("commitChanges") or 0) >= 1
        rows.append(row)
    rows.sort(key=lambda r: r["daysLeft"])
    return {"within_days": days, "count": len(rows), "tasks": rows}


@mcp.tool(annotations=READ_ONLY)
def delay_history(task_id: int) -> dict[str, Any]:
    """Every time a task was moved to a later date or time: from, to, and when it was rescheduled.
    Also works for tasks that were deleted, because the history is kept."""
    snap = snapshot()
    counts = delay_counts(snap)
    task = next((t for t in snap["tasks"] if t["id"] == task_id), None)
    history = [d for d in snap["delays"] if d["taskId"] == task_id]
    if task is None and not history:
        raise ToolError(f"No task or delay history found for id {task_id}")

    return {
        "taskId": task_id,
        "task": slim(task, counts) if task else None,
        "taskStatus": task["status"] if task else "deleted",
        "delayCount": len(history),
        "delays": [
            {"plannedFor": f"{d['fromDate']} {d['fromTime'] or ''}".strip(),
             "movedTo": f"{d['toDate']} {d['toTime'] or ''}".strip(),
             "rescheduledOn": d.get("createdDate")}
            for d in history
        ],
    }


if __name__ == "__main__":
    print(f"productivity-board MCP server (read-only) reading {BOARD_URL}", file=sys.stderr)
    mcp.run()  # stdio
