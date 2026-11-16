#!/usr/bin/env python3
"""Step 5: warn (never block) when more than 3 cards are In Progress,
and flag cards that have been delayed twice or more.

Run from the repo root:  python3 apply_step5.py
Frontend only. Every edit is checked first and ALL problems are reported at once;
if anything does not match, nothing is written. Running it twice is safe.
The HTML edits ignore whitespace, so a formatter re-wrapping lines does not matter.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def exact(old, new):
    def apply(text):
        return text.replace(old, new) if text.count(old) == 1 else None
    return old.strip().splitlines()[0][:90], apply


def before(pattern, insertion):
    """Insert text before the single place where the (whitespace-tolerant) pattern matches."""
    def apply(text):
        matches = list(re.finditer(pattern, text, flags=re.S))
        if len(matches) != 1:
            return None
        start = matches[0].start()
        line_start = text.rfind("\n", 0, start) + 1
        indent = text[line_start:start] if not text[line_start:start].strip() else ""
        return text[:start] + insertion.replace("\n", "\n" + indent) + "\n" + indent + text[start:]
    return pattern[:90], apply


HTML = [
    before(
        r'<span\s+class="late-count"\s*>\s*⏳\s*<span\s+id="delayed-count"',
        '<span class="late-count">⚠ <span id="chronic-count">0</span> delayed 2×+</span>',
    ),
    before(
        r'<div\s+class="task-list"\s+id="list-progress"\s*>',
        '<p id="wip-warning" class="wip-warning" hidden></p>',
    ),
]

JS = [
    exact(
        "/* Delay history: logged whenever an open task is moved to a later date or time */",
        '''/* Focus limit: more than this many cards in progress triggers a warning (it never blocks) */
const WIP_LIMIT = 3;
const delayCountOf = (task) => state.delays.filter((delay) => delay.taskId === task.id).length;

/* Delay history: logged whenever an open task is moved to a later date or time */''',
    ),
    exact(
        "  els.total.textContent = state.tasks.length;\n",
        '''  const inProgress = cards.progress.length;
  const wipWarning = $("wip-warning");
  wipWarning.hidden = inProgress <= WIP_LIMIT;
  wipWarning.textContent = `⚠ ${inProgress} cards in progress. Finish or pause some: more than ${WIP_LIMIT} at once spreads your focus thin.`;
  els.counts.progress.classList.toggle("over-limit", inProgress > WIP_LIMIT);
  $("chronic-count").textContent = state.tasks.filter(
    (task) => task.status !== "done" && delayCountOf(task) >= 2
  ).length;
  els.total.textContent = state.tasks.length;
''',
    ),
    exact(
        '    (delayCount ? `<span class="delay-tag soft">↻ Rescheduled ×${delayCount}</span>` : "");',
        '''    (delayCount >= 2 && !isDone
      ? `<span class="delay-tag chronic">⚠ Delayed ×${delayCount}: do it, split it or drop it</span>`
      : delayCount
        ? `<span class="delay-tag soft">↻ Rescheduled ×${delayCount}</span>`
        : "");''',
    ),
    exact(
        'class="task-card ${isDone ? "completed-card" : ""} ${isCommitSoon(task) ? "commit-soon" : ""}"',
        'class="task-card ${isDone ? "completed-card" : ""} ${isCommitSoon(task) ? "commit-soon" : ""} ${delayCount >= 2 && !isDone ? "chronic-delay" : ""}"',
    ),
    exact(
        "function notify(message) {",
        '''/* A lighter alert for warnings: on-page toast only, no system notification */
function warn(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  setTimeout(() => (els.toast.hidden = true), 8000);
}

function checkWip(task) {
  const count = state.tasks.filter((item) => item.status === "progress").length;
  if (task.status === "progress" && count > WIP_LIMIT) {
    warn(`You now have ${count} cards in progress. Consider finishing one before starting more.`);
  }
}

function notify(message) {''',
    ),
    exact(
        "  ACTIONS[button.dataset.action](task);\n  syncCompletion(task);\n",
        "  ACTIONS[button.dataset.action](task);\n  syncCompletion(task);\n  checkWip(task);\n",
    ),
    exact(
        "  sync(state.editingId === null ? api.createTask(task) : api.updateTask(task.id, task));\n",
        "  sync(state.editingId === null ? api.createTask(task) : api.updateTask(task.id, task));\n  checkWip(task);\n",
    ),
    exact(
        '${late ? "⏳ " : ""}${time ? ',
        '${late ? "⏳ " : ""}${delayCountOf(task) >= 2 ? "⚠ " : ""}${time ? ',
    ),
]

CSS = """
/* Focus limits and repeated delays */
.wip-warning {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-left: 3px solid #f59e0b;
  border-radius: 6px;
  background: #fffbeb;
  color: #92400e;
  font-size: 10px;
  font-weight: 700;
  line-height: 1.4;
}
.wip-warning[hidden] { display: none; }
.task-count.over-limit { background: #f59e0b; color: #ffffff; }
.task-card.chronic-delay { border-color: #dc2626; box-shadow: 0 0 0 1px #dc2626; }
.delay-tag.chronic { background: #7f1d1d; color: #ffffff; font-size: 9px; text-transform: none; }
"""

THEME = """
/* Focus limits and repeated delays */
[data-theme="dark"] .wip-warning { background: #2a1f0a; color: #fcd34d; }
[data-theme="dark"] .delay-tag.chronic { background: #991b1b; color: #ffffff; }
"""

FILES = [
    ("frontend/index.html", "wip-warning", HTML, ""),
    ("frontend/index.js", "WIP_LIMIT", JS, ""),
    ("frontend/panels.css", "/* Focus limits", [], CSS),
    ("frontend/theme.css", "/* Focus limits", [], THEME),
]

problems, results = [], []
for rel_path, marker, edits, append in FILES:
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
    results.append((path, rel_path, text + append, len(edits)))

if problems:
    print("Nothing was written. These edits did not match your files:")
    print("\n".join(problems))
    print("\nPaste the lines above, plus the output of:")
    print('  grep -n "delayed-count\\|list-progress\\|Rescheduled\\|task-card " frontend/index.html frontend/index.js')
    sys.exit(1)

for path, rel_path, text, count in results:
    path.write_text(text, encoding="utf-8")
    print(f"{rel_path}: patched ({count} edits)" if count else f"{rel_path}: patched (styles added)")
print("Done. Review with: git diff --stat")
