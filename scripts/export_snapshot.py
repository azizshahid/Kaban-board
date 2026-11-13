#!/usr/bin/env python3
"""Write snapshot.json and snapshot.md from the running board (local only).

    python3 scripts/export_snapshot.py                  # notes are NOT included
    python3 scripts/export_snapshot.py --include-notes  # explicit opt-in

The files go to the repo root and are listed in .gitignore. Upload snapshot.md
(or snapshot.json) to Claude when you want help planning.
"""
import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

STATUS_NAMES = {"progress": "In progress", "todo": "To do", "done": "Done"}


def fetch(base_url, include_notes):
    host = urlparse(base_url).hostname
    if host not in {"127.0.0.1", "localhost"}:
        sys.exit(f"Refusing to export from {host}: the snapshot must stay on this machine.")
    url = base_url.rstrip("/") + "/api/export" + ("?include_notes=1" if include_notes else "")
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError) as error:
        sys.exit(f"Could not reach {url} ({error}). Is ./start-board.sh running?")


def minutes(value):
    if not value:
        return ""
    hours, rest = divmod(value, 60)
    return f"{hours}h {rest}m" if hours and rest else f"{hours}h" if hours else f"{rest}m"


def cell(text):
    return str(text if text is not None else "").replace("|", "/").replace("\n", " ")


def task_line(task):
    parts = [f"**{cell(task['title'])}**"]
    if task.get("label"):
        parts.append(f"[{cell(task['label'])}]")
    due = " ".join(part for part in (task.get("dueDate"), task.get("dueTime")) if part)
    if due:
        parts.append(f"due {due}")
    if task.get("commitDate"):
        parts.append(f"commitment {task['commitDate']}")
    if task.get("blockStart"):
        parts.append(f"block {task['blockStart']} ({task.get('blockMinutes') or 30} min)")
    if task.get("estimateMinutes"):
        parts.append(f"est {minutes(task['estimateMinutes'])}")
    return "- " + " · ".join(parts)


def to_markdown(snap):
    derived, tasks = snap["derived"], snap["tasks"]
    lines = [
        "# Board snapshot",
        f"Generated: {snap['generatedAt']}  ",
        f"Notes included: {'yes' if 'notes' in snap else 'no'}",
        "",
    ]

    def section(title, rows, empty="Nothing."):
        lines.extend([f"## {title}", *(rows or [empty]), ""])

    section("Overdue", [task_line(t) for t in derived["overdue"]])
    section(
        "Commitments due within 7 days",
        [
            f"{task_line(t)} · {'passed ' + str(-t['daysLeft']) + ' days ago' if t['daysLeft'] < 0 else str(t['daysLeft']) + ' days left'}"
            f"{' · deadline already changed once' if t['commitChanges'] else ''}"
            for t in derived["commitmentsDueIn7Days"]
        ],
    )
    section(
        "Delayed twice or more",
        [f"- **{cell(d['title'])}** · {d['delays']} delays · {d['status']}" for d in derived["delayedTwiceOrMore"]],
    )

    label_rows = ["| Label | To do | In progress | Done |", "|---|---|---|---|"]
    label_rows += [
        f"| {cell(label)} | {c.get('todo', 0)} | {c.get('progress', 0)} | {c.get('done', 0)} |"
        for label, c in sorted(derived["countsByLabel"].items())
    ]
    section("Counts by label", label_rows if len(label_rows) > 2 else [])

    for status in ("progress", "todo"):
        group = [t for t in tasks if t["status"] == status]
        group.sort(key=lambda t: (t.get("dueDate") or "9999", t.get("dueTime") or "99:99"))
        total = sum(t.get("estimateMinutes") or 0 for t in group)
        suffix = f" ({len(group)}, estimated {minutes(total)})" if group else ""
        section(f"{STATUS_NAMES[status]}{suffix}", [task_line(t) for t in group])

    recent = (date.today() - timedelta(days=14)).isoformat()
    done = [c for c in snap["completions"] if (c.get("completedDate") or "") >= recent]
    section("Completed in the last 14 days", [f"- {c['completedDate']} · {cell(c['title'])}" for c in done])

    items, checks = snap["checklist"]["items"], snap["checklist"]["checks"]
    days = [(date.today() - timedelta(days=n)).isoformat() for n in range(7)]
    rows = [
        f"- {day}: {sum(1 for c in checks if c['date'] == day)}/{len(items)} checked" for day in days
    ]
    section("Daily checklist (last 7 days)", rows if items else [], "No checklist items.")

    if "notes" in snap:
        section("Notes", [f"- {n.get('date')} · {n['category']}: {cell(n['text'])}" for n in snap["notes"]])
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--url", default="http://127.0.0.1:5000", help="board address (local only)")
    parser.add_argument("--include-notes", action="store_true", help="also export your personal notes")
    parser.add_argument("--out-dir", default=str(Path(__file__).resolve().parent.parent), help="where to write")
    args = parser.parse_args()

    snap = fetch(args.url, args.include_notes)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "snapshot.json").write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "snapshot.md").write_text(to_markdown(snap), encoding="utf-8")

    derived = snap["derived"]
    print(f"Wrote {out / 'snapshot.json'} and {out / 'snapshot.md'}")
    print(
        f"{len(snap['tasks'])} tasks · {len(derived['overdue'])} overdue · "
        f"{len(derived['commitmentsDueIn7Days'])} commitments within 7 days · "
        f"notes {'included' if 'notes' in snap else 'excluded'}"
    )


if __name__ == "__main__":
    main()
