#!/usr/bin/env python3
"""Import tasks from a JSON array into the local board. Usage: python3 import_tasks.py tasks.json [--dry-run]"""
import json, sys, urllib.request

BASE = "http://127.0.0.1:5000/api/tasks"
ALLOWED = {"title", "label", "status", "description", "dueDate", "dueTime",
           "commitDate", "blockStart", "blockMinutes"}

def call(data=None):
    req = urllib.request.Request(BASE, method="POST" if data else "GET",
          data=json.dumps(data).encode() if data else None,
          headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)

path = sys.argv[1]
dry = "--dry-run" in sys.argv
existing = {(t["title"].strip().lower(), (t.get("label") or "").lower()) for t in call()}
created = skipped = 0
for t in json.load(open(path)):
    key = (t["title"].strip().lower(), (t.get("label") or "").lower())
    if key in existing:
        print("skip (exists):", t["title"]); skipped += 1; continue
    if "estimateMinutes" in t:  # no estimate field on the board yet: keep it in the description
        t["description"] = ((t.get("description") or "") + f" [est {t['estimateMinutes']}m]").strip()
    t = {k: v for k, v in t.items() if k in ALLOWED}
    t.setdefault("status", "todo")
    print(("would create: " if dry else "create: ") + t["title"])
    if not dry:
        call(t)
    created += 1
print(f"done: {created} {'would be ' if dry else ''}created, {skipped} skipped")