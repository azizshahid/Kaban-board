#!/usr/bin/env python3
"""Step 6: replace the student-style default checklist with an agency daily checklist.

Run from the repo root:  python3 apply_step6.py

This only edits CODE (backend/app.py, frontend/index.js, scripts/export_snapshot.py).
Your database is not touched until you restart the server; then a ONE-TIME migration
runs (recorded in a `meta` table, so it can never run twice):
  * the 11 old default items are ARCHIVED (hidden from today on, kept in the database),
  * 5 agency items are added,
  * no row in checklist_log is changed or deleted, so every existing check survives.
Items you added yourself are left alone.
All problems are reported at once; if anything does not match, nothing is written.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def exact(old, new):
    def apply(text):
        return text.replace(old, new) if text.count(old) == 1 else None
    return old.strip().splitlines()[0][:90], apply


def regex(pattern, replacement):
    """Replace the single place where a whitespace-tolerant pattern matches."""
    def apply(text):
        found = re.findall(pattern, text, flags=re.S)
        return re.sub(pattern, lambda _m: replacement, text, flags=re.S) if len(found) == 1 else None
    return pattern[:90], apply


APP = [
    exact(
        "DEFAULT_CHECKLIST = [\n",
        '''AGENCY_MIGRATION = "checklist_agency_v1"
AGENCY_CHECKLIST = [  # (id, text, category); fixed ids so the migration is repeatable
    (1001, "Pick at most 3 cards for today", "planning"),
    (1002, "Main-track block", "work"),
    (1003, "Second-track block", "work"),
    (1004, "Yarnimals slice", "work"),
    (1005, "Log progress and plan tomorrow", "wrap-up"),
]
OLD_DEFAULT_CHECKLIST = [  # the original starter list, ids 1..11, used only to find them
''',
    ),
    exact(
        '''        if first_time:  # start with a useful set for a working professional / student
            db.executemany(
                "INSERT INTO checklist_items (id, text, category, created_date) "
                "VALUES (?, ?, ?, date('now', 'localtime'))",
                [(i + 1, text, category) for i, (text, category) in enumerate(DEFAULT_CHECKLIST)],
            )
''',
        "        # The starter checklist is created by the one-time migration at the end of init_db.\n",
    ),
    exact(
        '''            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
''',
        '''            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

        # One-time migration to the agency checklist. Recorded in `meta`, so it never runs twice.
        db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
        if db.execute("SELECT 1 FROM meta WHERE key = ?", (AGENCY_MIGRATION,)).fetchone() is None:
            if not first_time:  # an existing board: hide the old defaults, never delete anything
                for item_id, (text, _category) in enumerate(OLD_DEFAULT_CHECKLIST, start=1):
                    db.execute(
                        "UPDATE checklist_items SET archived_date = date('now', 'localtime') "
                        "WHERE id = ? AND text = ? AND archived_date IS NULL",
                        (item_id, text),
                    )
            db.executemany(
                "INSERT OR IGNORE INTO checklist_items (id, text, category, created_date) "
                "VALUES (?, ?, ?, date('now', 'localtime'))",
                AGENCY_CHECKLIST,
            )
            db.execute(
                "INSERT INTO meta (key, value) VALUES (?, date('now', 'localtime'))", (AGENCY_MIGRATION,)
            )
''',
    ),
    exact(
        '            ("notes", "task_id", "INTEGER"),',
        '            ("notes", "task_id", "INTEGER"),\n            ("checklist_items", "archived_date", "TEXT"),',
    ),
]

JS = [
    exact(
        "const checkedOn = (date) =>",
        '''/* An item counts on a day if it existed then and had not been archived yet */
const isActiveOn = (item, iso) =>
  (item.createdDate || "0000-00-00") <= iso && (!item.archivedDate || iso < item.archivedDate);

const checkedOn = (date) =>''',
    ),
    exact(
        "  const items = state.checklist.items;\n",
        "  const items = state.checklist.items.filter((item) => isActiveOn(item, todayISO()));\n",
    ),
    regex(
        r'state\.checklist\.items\.filter\(\s*\(item\)\s*=>\s*\(item\.createdDate\s*\|\|\s*"0000-00-00"\)\s*<=\s*iso\s*,?\s*\)',
        "state.checklist.items.filter((item) => isActiveOn(item, iso))",
    ),
]

EXPORT = [
    exact(
        '''    rows = [
        f"- {day}: {sum(1 for c in checks if c['date'] == day)}/{len(items)} checked" for day in days
    ]
''',
        '''
    def active_ids(day):  # items that existed, and were not archived yet, on that day
        return {
            i["id"]
            for i in items
            if (i.get("createdDate") or "0000-00-00") <= day and (not i.get("archivedDate") or day < i["archivedDate"])
        }

    rows = []
    for day in days:
        ids = active_ids(day)
        done = sum(1 for c in checks if c["date"] == day and c["itemId"] in ids)
        rows.append(f"- {day}: {done}/{len(ids)} checked")
''',
    ),
]

FILES = [
    ("backend/app.py", "AGENCY_MIGRATION", APP),
    ("frontend/index.js", "isActiveOn", JS),
    ("scripts/export_snapshot.py", "archivedDate", EXPORT),
]

problems, results = [], []
for rel_path, marker, edits in FILES:
    path = ROOT / rel_path
    if not path.exists():
        sys.exit(f"{rel_path}: not found. Run this script from the repo root.")
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"{rel_path}: already patched, skipped")
        continue
    for description, apply in edits:
        changed = apply(text)
        if changed is None:
            problems.append(f"  {rel_path}: could not find exactly one match for: {description}")
        else:
            text = changed
    results.append((path, rel_path, text, len(edits)))

if problems:
    print("Nothing was written. These edits did not match your files:")
    print("\n".join(problems))
    sys.exit(1)

for path, rel_path, text, count in results:
    path.write_text(text, encoding="utf-8")
    print(f"{rel_path}: patched ({count} edits)")
print("Done. Your database is unchanged until you restart the server. Review with: git diff --stat")
