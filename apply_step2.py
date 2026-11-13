#!/usr/bin/env python3
"""Step 2: add the estimate_minutes field.

Run from the repo root:  python3 apply_step2.py

It edits backend/app.py, frontend/index.html, frontend/index.js,
frontend/panels.css and frontend/theme.css. Every edit is checked first:
if any file does not look as expected, NOTHING is written.
Running it twice is safe (already patched files are skipped).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def plan(rel_path, marker, edits=(), append=""):
    """Return (path, new_text) or None if already patched. Exits on any mismatch."""
    path = ROOT / rel_path
    if not path.exists():
        sys.exit(f"{rel_path}: not found. Run this script from the repo root.")
    text = path.read_text(encoding="utf-8")
    if marker in text:
        print(f"{rel_path}: already patched, skipped")
        return None
    for old, new in edits:
        if text.count(old) != 1:
            sys.exit(f"{rel_path}: expected exactly one match for:\n{old}\nNothing was written.")
        text = text.replace(old, new)
    return path, rel_path, text + append, len(edits)


# ---------------------------------------------------------------- backend/app.py
APP = [
    (
        '    "commit_date", "commit_changes", "commit_original",\n}',
        '    "commit_date", "commit_changes", "commit_original", "estimate_minutes",\n}',
    ),
    (
        '            ("tasks", "commit_original", "TEXT"),\n',
        '            ("tasks", "commit_original", "TEXT"),\n'
        '            ("tasks", "estimate_minutes", "INTEGER"),\n',
    ),
    (
        "# ---------- Tasks API ----------",
        '''def check_estimate(values):
    """estimate_minutes is optional; when given it must be a whole number of minutes."""
    value = values.get("estimate_minutes")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
        return "estimate_minutes must be a whole number between 1 and 1440"
    return None


# ---------- Tasks API ----------''',
    ),
    (
        '    task.pop("commit_original", None)\n',
        '    task.pop("commit_original", None)\n'
        '    estimate_error = check_estimate(task)\n'
        '    if estimate_error:\n'
        '        return jsonify(error=estimate_error), 400\n',
    ),
    (
        '    changes.pop("id", None)  # the id never changes\n',
        '    changes.pop("id", None)  # the id never changes\n'
        '    estimate_error = check_estimate(changes)\n'
        '    if estimate_error:\n'
        '        return jsonify(error=estimate_error), 400\n',
    ),
]

# ---------------------------------------------------------------- frontend/index.html
HTML = [
    (
        '        <label class="field-label">\n          Time block (optional)',
        '        <label class="field-label">\n'
        '          Estimate in minutes (optional)\n'
        '          <input type="number" id="task-estimate" min="1" max="1440" step="5" placeholder="e.g. 90" />\n'
        '        </label>\n'
        '        <label class="field-label">\n          Time block (optional)',
    ),
    (
        '        <p class="planner-hint">',
        '        <p id="planner-total" class="planner-total"></p>\n        <p class="planner-hint">',
    ),
]

# ---------------------------------------------------------------- frontend/index.js
JS = [
    (
        'const taskStart = (task) => task.blockStart || task.dueTime || "99:99";',
        '''/* Estimates: minutes of work, shown as 1h 30m */
const formatMinutes = (minutes) => {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? (rest ? `${hours}h ${rest}m` : `${hours}h`) : `${rest}m`;
};
const sumEstimates = (tasks) => tasks.reduce((total, task) => total + (task.estimateMinutes || 0), 0);

const taskStart = (task) => task.blockStart || task.dueTime || "99:99";''',
    ),
    (
        '    commitDate: $("task-commit").value || null,',
        '    commitDate: $("task-commit").value || null,\n'
        '    estimateMinutes: Number($("task-estimate").value) || null,',
    ),
    ('  setCommitField(null);', '  setCommitField(null);\n  $("task-estimate").value = "";'),
    ('  setCommitField(task);', '  setCommitField(task);\n  $("task-estimate").value = task.estimateMinutes || "";'),
    (
        '${task.blockStart ? `<span class="block-tag">▦ ${blockRange(task)}</span>` : ""}',
        '${task.blockStart ? `<span class="block-tag">▦ ${blockRange(task)}</span>` : ""}'
        '${task.estimateMinutes ? `<span class="estimate-tag">⏱ ${formatMinutes(task.estimateMinutes)}</span>` : ""}',
    ),
    (
        '${time ? `${time} ` : ""}${escapeHtml(task.title)}</button>',
        '${time ? `${time} ` : ""}${escapeHtml(task.title)}'
        '${task.estimateMinutes ? ` · ${formatMinutes(task.estimateMinutes)}` : ""}</button>',
    ),
    (
        '    const openCommit = commits.some((task) => task.status !== "done");\n',
        '    const openCommit = commits.some((task) => task.status !== "done");\n'
        '    const dayTotal = sumEstimates(open);\n',
    ),
    (
        '      <div class="day-head">${head}</div>${chips}</div>',
        '      <div class="day-head">${head}${dayTotal ? ` <span class="day-total">⏱ ${formatMinutes(dayTotal)}</span>` : ""}</div>${chips}</div>',
    ),
    (
        "function renderYear(year) {",
        '''/* Total estimated work for whatever the planner is showing (day, week or month) */
function plannerTotalText() {
  if (state.view === "year") return "";

  const { start, count } = plannerRange();
  let from = toISO(start);
  let to = toISO(addDays(start, Math.max(count, 1) - 1));
  if (state.view === "month") {
    const cursor = state.cursor;
    from = toISO(new Date(cursor.getFullYear(), cursor.getMonth(), 1));
    to = toISO(new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0));
  }

  const tasks = state.tasks.filter((task) => task.status !== "done" && task.dueDate >= from && task.dueDate <= to);
  const withoutEstimate = tasks.filter((task) => !task.estimateMinutes).length;
  const plural = tasks.length === 1 ? "" : "s";
  return `Estimated work: ${formatMinutes(sumEstimates(tasks))} across ${tasks.length} open task${plural}${withoutEstimate ? ` (${withoutEstimate} without an estimate)` : ""}`;
}

function renderYear(year) {''',
    ),
    (
        "  els.plannerTitle.textContent = title;\n",
        '  els.plannerTitle.textContent = title;\n  $("planner-total").textContent = plannerTotalText();\n',
    ),
]

CSS = """
/* Estimates */
.estimate-tag { color: #0f766e; font-size: 9px; font-weight: 700; }
.day-total { margin-left: 6px; color: #0f766e; font-size: 9px; font-weight: 700; }
.planner-total { margin: 0 0 12px; color: #0f766e; font-size: 11px; font-weight: 700; }
.planner-total:empty { display: none; }
"""

THEME = """
/* Estimates */
[data-theme="dark"] .estimate-tag,
[data-theme="dark"] .day-total,
[data-theme="dark"] .planner-total { color: #5eead4; }
"""

planned = [
    plan("backend/app.py", "estimate_minutes", APP),
    plan("frontend/index.html", "task-estimate", HTML),
    plan("frontend/index.js", "estimateMinutes", JS),
    plan("frontend/panels.css", "/* Estimates */", append=CSS),
    plan("frontend/theme.css", "/* Estimates */", append=THEME),
]

# Everything checked: now write.
for item in planned:
    if item is None:
        continue
    path, rel_path, text, count = item
    path.write_text(text, encoding="utf-8")
    print(f"{rel_path}: patched ({count} edit{'s' if count != 1 else ''})" if count else f"{rel_path}: patched (styles added)")

print("Done. Review with: git diff --stat")
