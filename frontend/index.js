import { api, load, save } from "./storage.js";

/* ---------- Data ---------- */

const state = {
  tasks: [],
  notes: [],
  completions: [],
  settings: { reminderMinutes: 30, theme: "system", ...load("settings", {}) },
  editingId: null,
  noteFilter: null,
  view: "board",
  cursor: new Date(),
};

/* ---------- DOM references ---------- */

const $ = (id) => document.getElementById(id);

const els = {
  lists: { todo: $("list-todo"), progress: $("list-progress"), done: $("list-done") },
  counts: { todo: $("count-todo"), progress: $("count-progress"), done: $("count-done") },
  total: $("total-count"),
  today: $("today-label"),
  board: document.querySelector(".kanban-columns"),
  taskDialog: $("task-dialog"),
  taskForm: $("task-form"),
  interval: $("reminder-interval"),
  theme: $("theme-select"),
  noteTask: $("note-task"),
  noteFilter: $("note-filter"),
  planner: $("planner"),
  plannerGrid: $("planner-grid"),
  plannerTitle: $("planner-title"),
  toast: $("toast"),
  notesList: $("notes-list"),
  noteForm: $("note-form"),
  reviewDialog: $("review-dialog"),
  reviewForm: $("review-form"),
  reviewSummary: $("review-summary"),
  reviewList: $("review-list"),
};

/* ---------- Helpers ---------- */

const escapeHtml = (text) =>
  String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const toISO = (date) => date.toLocaleDateString("en-CA"); // YYYY-MM-DD in local time
const todayISO = () => toISO(new Date());
const tomorrowISO = () => {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  return toISO(d);
};
const formatDate = (iso) =>
  iso ? new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short" }) : "No date";

const findTask = (id) => state.tasks.find((task) => task.id === id);

/* Time blocks: a start time plus a length in minutes, on the task's date */
const toMinutes = (time) => {
  const [hours, minutes] = time.split(":").map(Number);
  return hours * 60 + minutes;
};
const pad = (n) => String(n).padStart(2, "0");
const blockRange = (task) => {
  const end = toMinutes(task.blockStart) + (task.blockMinutes || 30);
  return `${task.blockStart}–${pad(Math.floor(end / 60) % 24)}:${pad(end % 60)}`;
};
const taskStart = (task) => task.blockStart || task.dueTime || "99:99";
const byTime = (a, b) => taskStart(a).localeCompare(taskStart(b));

function findOverlap(candidate) {
  if (!candidate.blockStart || candidate.status === "done") return null;
  const start = toMinutes(candidate.blockStart);
  const end = start + (candidate.blockMinutes || 30);
  return (
    state.tasks.find(
      (other) =>
        other.id !== candidate.id &&
        other.status !== "done" &&
        other.dueDate === candidate.dueDate &&
        other.blockStart &&
        toMinutes(other.blockStart) < end &&
        start < toMinutes(other.blockStart) + (other.blockMinutes || 30)
    ) || null
  );
}

/* Completion history: stays even after the task is deleted, so you can reflect later */
function syncCompletion(task) {
  const existing = state.completions.find((entry) => entry.taskId === task.id);

  if (task.status === "done" && !existing) {
    const when = task.completedAt || (task.dueDate ? new Date(`${task.dueDate}T12:00`).getTime() : Date.now());
    const entry = {
      taskId: task.id,
      title: task.title,
      label: task.label,
      completedAt: when,
      completedDate: toISO(new Date(when)),
    };
    state.completions.push(entry);
    sync(api.saveCompletion(entry));
  } else if (task.status !== "done" && existing) {
    state.completions = state.completions.filter((entry) => entry.taskId !== task.id);
    sync(api.deleteCompletion(task.id));
  }
}

/* A task may have a date and an optional deadline time */
const deadlineOf = (task) => (task.dueDate && task.dueTime ? new Date(`${task.dueDate}T${task.dueTime}`) : null);
const formatDeadline = (task) =>
  task.dueTime ? `${formatDate(task.dueDate)} · ${task.dueTime}` : formatDate(task.dueDate);

function isPastDeadline(task) {
  if (!task.dueDate) return false;
  const deadline = deadlineOf(task);
  return deadline ? deadline < new Date() : task.dueDate < todayISO();
}

// Optimistic UI: the board updates instantly, the server is updated in the background.
function sync(request) {
  request.catch((error) => {
    console.error(error);
    notify("Could not reach the server. Changes may not be saved.");
  });
}

function persistTasks() {
  render();
}

/* ---------- Task cards ---------- */

// Label color is decided by the column, not chosen per task
const LABEL_CLASS = { todo: "purple", progress: "orange", done: "green-label" };

const ACTION_BUTTONS = {
  todo: `<button type="button" class="action-btn" data-action="start">▶ Start</button>`,
  progress: `
    <button type="button" class="action-btn" data-action="complete">✓ Done</button>
    <button type="button" class="action-btn secondary" data-action="back">↩ Back</button>`,
  done: `<button type="button" class="action-btn secondary" data-action="reopen">↩ Reopen</button>`,
};

const ACTIONS = {
  start: (task) => Object.assign(task, { status: "progress", startedAt: Date.now(), lastReminderAt: null }),
  complete: (task) => Object.assign(task, { status: "done", completedAt: Date.now() }),
  back: (task) => Object.assign(task, { status: "todo", startedAt: null }),
  reopen: (task) => Object.assign(task, { status: "progress", startedAt: Date.now(), lastReminderAt: null, completedAt: null }),
};

function createCard(task) {
  const isDone = task.status === "done";
  const isOverdue = !isDone && isPastDeadline(task);
  const noteCount = state.notes.filter((note) => note.taskId === task.id).length;
    const footer = isDone
    ? `<span class="done-date">✓ Completed</span>`
    : `<span class="due-date ${isOverdue ? "overdue" : ""}">◷ ${formatDeadline(task)}</span>${task.blockStart ? `<span class="block-tag">▦ ${blockRange(task)}</span>` : ""}`;

  return `
    <article class="task-card ${isDone ? "completed-card" : ""}" data-id="${task.id}">
      <div class="task-top">
        <span class="task-label ${LABEL_CLASS[task.status]}">${escapeHtml(task.label)}</span>
        <button type="button" class="menu-btn" aria-label="Edit task">•••</button>
      </div>
      <h3>${escapeHtml(task.title)}</h3>
      <p>${escapeHtml(task.description)}</p>
      <div class="task-footer">${footer}</div>
      <div class="card-actions">${ACTION_BUTTONS[task.status]}<button type="button" class="note-btn" title="Notes for this task">📝${noteCount ? ` ${noteCount}` : ""}</button></div>
    </article>`;
}

function render() {
  const cards = { todo: [], progress: [], done: [] };
  state.tasks.forEach((task) => cards[task.status].push(createCard(task)));

  Object.keys(cards).forEach((status) => {
    els.lists[status].innerHTML = cards[status].join("");
    els.counts[status].textContent = cards[status].length;
  });
  els.total.textContent = state.tasks.length;
  renderNotes();
  if (planningEls.dialog.open) renderPlanningLists();
  if (state.view !== "board") renderPlanner();
}

/* ---------- Add / edit / delete ---------- */

function openAddDialog(status, date = todayISO(), blockStart = "") {
  state.editingId = null;
  els.taskForm.reset();
  $("dialog-title").textContent = "New Task";
  $("submit-btn").textContent = "Add";
  $("delete-btn").hidden = true;
  $("task-status").value = status;
  $("task-date").value = date;
  $("task-time").value = "";
  $("task-block-start").value = blockStart;
  $("task-block-minutes").value = blockStart ? "30" : "";
  els.taskDialog.showModal();
}

function openEditDialog(task) {
  state.editingId = task.id;
  $("dialog-title").textContent = "Edit Task";
  $("submit-btn").textContent = "Save";
  $("delete-btn").hidden = false;
  $("task-title").value = task.title;
  $("task-desc").value = task.description;
  $("task-label").value = task.label;
  $("task-status").value = task.status;
  $("task-date").value = task.dueDate;
  $("task-time").value = task.dueTime || "";
  $("task-block-start").value = task.blockStart || "";
  $("task-block-minutes").value = task.blockMinutes ? String(task.blockMinutes) : "";
  els.taskDialog.showModal();
}

function readTaskForm() {
  return {
    title: $("task-title").value.trim(),
    description: $("task-desc").value.trim(),
    label: $("task-label").value.trim() || "General",
    status: $("task-status").value,
    dueDate: $("task-date").value,
    dueTime: $("task-time").value || null,
    blockStart: $("task-block-start").value || null,
    blockMinutes: $("task-block-start").value ? Number($("task-block-minutes").value) || 30 : null,
  };
}

els.taskForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const values = readTaskForm();
  const clash = findOverlap({ id: state.editingId, ...values });
  if (clash && !confirm(`This time block overlaps with "${clash.title}" (${blockRange(clash)}). Save anyway?`)) return;
  const task = state.editingId === null ? { id: Date.now() } : findTask(state.editingId);

  if (task.dueDate !== values.dueDate || task.dueTime !== values.dueTime) task.deadlineStage = 0;
  Object.assign(task, values);
  if (task.status === "progress" && !task.startedAt) task.startedAt = Date.now();
  if (task.status === "done" && !task.completedAt) task.completedAt = Date.now();
  syncCompletion(task);
  if (state.editingId === null) state.tasks.push(task);
  sync(state.editingId === null ? api.createTask(task) : api.updateTask(task.id, task));

  persistTasks();
  els.taskDialog.close();
});

$("delete-btn").addEventListener("click", () => {
  if (!confirm("Delete this task?")) return;
  sync(api.deleteTask(state.editingId));
  state.tasks = state.tasks.filter((task) => task.id !== state.editingId);
  persistTasks();
  els.taskDialog.close();
});

$("cancel-btn").addEventListener("click", () => els.taskDialog.close());
$("add-task-btn").addEventListener("click", () => openAddDialog("todo"));
document.querySelectorAll(".column-add").forEach((btn) => {
  btn.addEventListener("click", () => openAddDialog(btn.dataset.status));
});

/* One listener for every card button (cards are rebuilt on each render) */
els.board.addEventListener("click", (event) => {
  const card = event.target.closest(".task-card");
  if (!card) return;
  const task = findTask(Number(card.dataset.id));
  if (!task) return;

  if (event.target.closest(".menu-btn")) {
    openEditDialog(task);
    return;
  }

  if (event.target.closest(".note-btn")) {
    focusNotesFor(task.id);
    return;
  }

  const button = event.target.closest(".action-btn");
  if (!button) return;
  if (button.dataset.action === "start") requestNotificationPermission();
  ACTIONS[button.dataset.action](task);
  syncCompletion(task);
  sync(api.updateTask(task.id, task));
  persistTasks();
});

/* ---------- Reminders ---------- */

function requestNotificationPermission() {
  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission();
  }
}

function notify(message) {
  els.toast.textContent = message;
  els.toast.hidden = false;
  setTimeout(() => (els.toast.hidden = true), 8000);
  if ("Notification" in window && Notification.permission === "granted") {
    new Notification("Task reminder", { body: message });
  }
}

function checkReminders() {
  const minutes = Number(state.settings.reminderMinutes);
  if (!minutes) return;

  const now = Date.now();

  state.tasks
    .filter((task) => task.status === "progress" && task.startedAt)
    .forEach((task) => {
      const lastPing = task.lastReminderAt || task.startedAt;
      if (now - lastPing >= minutes * 60000) {
        const elapsed = Math.round((now - task.startedAt) / 60000);
        notify(`"${task.title}" has been in progress for ${elapsed} min. Still on it?`);
        task.lastReminderAt = now;
        sync(api.updateTask(task.id, { lastReminderAt: now }));
      }
    });

}

/* Deadline alerts: once 15 minutes before, once when the time has passed */
function checkDeadlines() {
  const now = Date.now();

  state.tasks
    .filter((task) => task.status !== "done" && deadlineOf(task))
    .forEach((task) => {
      const minutesLeft = (deadlineOf(task) - now) / 60000;
      const stage = task.deadlineStage || 0;

      if (minutesLeft <= 0 && stage < 2) {
        notify(`"${task.title}" is past its deadline (${task.dueTime}).`);
        task.deadlineStage = 2;
      } else if (minutesLeft > 0 && minutesLeft <= 15 && stage < 1) {
        notify(`"${task.title}" is due in ${Math.ceil(minutesLeft)} min (${task.dueTime}).`);
        task.deadlineStage = 1;
      } else {
        return;
      }
      sync(api.updateTask(task.id, { deadlineStage: task.deadlineStage }));
    });
}

els.interval.value = String(state.settings.reminderMinutes);
els.interval.addEventListener("change", () => {
  state.settings.reminderMinutes = Number(els.interval.value);
  save("settings", state.settings);
});
setInterval(() => {
  checkReminders();
  checkDeadlines();
}, 30000);

/* ---------- Notes ---------- */

function renderNoteTaskOptions() {
  const current = els.noteTask.value;
  els.noteTask.innerHTML =
    `<option value="">Attach to task: none</option>` +
    state.tasks.map((task) => `<option value="${task.id}">${escapeHtml(task.title)}</option>`).join("");
  els.noteTask.value = current;
}

function renderNotes() {
  const filterTask = findTask(state.noteFilter);
  if (!filterTask) state.noteFilter = null;
  const visible = filterTask ? state.notes.filter((note) => note.taskId === filterTask.id) : state.notes;

  els.noteFilter.hidden = !filterTask;
  els.noteFilter.firstElementChild.textContent = filterTask ? `Notes for: ${filterTask.title}` : "";
  renderNoteTaskOptions();

  els.notesList.innerHTML =
    visible
      .map((note) => {
        const task = findTask(note.taskId);
        const link = task
          ? `<button type="button" class="note-task" data-task="${task.id}">↗ ${escapeHtml(task.title)}</button>`
          : "";
        return `
      <li class="note" data-id="${note.id}">
        <div class="note-meta">
          <span class="note-tag">${escapeHtml(note.category)}</span>
          <span>${formatDate(note.date)}</span>
          <button type="button" class="note-delete" aria-label="Delete note">✕</button>
        </div>
        <p>${escapeHtml(note.text)}</p>
        ${link}
      </li>`;
      })
      .join("") || `<li class="note-empty">No notes yet.</li>`;
}

function focusNotesFor(taskId) {
  state.noteFilter = taskId;
  renderNotes();
  els.noteTask.value = String(taskId);
  $("note-text").focus();
}

$("note-filter-clear").addEventListener("click", () => {
  state.noteFilter = null;
  renderNotes();
});

function addNote(category, text, taskId = null) {
  const note = { id: Date.now(), category, text, taskId, date: todayISO() };
  state.notes.unshift(note);
  sync(api.createNote(note));
  render();
}

els.noteForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("note-text").value.trim();
  if (!text) return;
  addNote($("note-category").value, text, Number(els.noteTask.value) || null);
  els.noteForm.reset();
  els.noteTask.value = state.noteFilter ? String(state.noteFilter) : "";
});

els.notesList.addEventListener("click", (event) => {
  const taskLink = event.target.closest(".note-task");
  if (taskLink) {
    openEditDialog(findTask(Number(taskLink.dataset.task)));
    return;
  }

  const deleteBtn = event.target.closest(".note-delete");
  if (!deleteBtn) return;
  const id = Number(deleteBtn.closest(".note").dataset.id);
  state.notes = state.notes.filter((note) => note.id !== id);
  sync(api.deleteNote(id));
  render();
});

/* ---------- End-of-day review ---------- */

function renderReview() {
  const today = todayISO();
  const doneToday = state.completions.filter((entry) => entry.completedDate === today).length;
  const open = state.tasks.filter((task) => task.status !== "done" && task.dueDate && task.dueDate <= today);

  els.reviewSummary.textContent = `${doneToday} completed today · ${open.length} still open`;
  els.reviewList.innerHTML =
    open
      .map(
        (task) => `
      <li>
        <span>${escapeHtml(task.title)}</span>
        <button type="button" class="action-btn" data-move="${task.id}">Move to tomorrow</button>
      </li>`
      )
      .join("") || "<li>Nothing left over for today.</li>";
}

$("review-btn").addEventListener("click", () => {
  renderReview();
  els.reviewDialog.showModal();
});

els.reviewList.addEventListener("click", (event) => {
  const moveBtn = event.target.closest("[data-move]");
  if (!moveBtn) return;
  const task = findTask(Number(moveBtn.dataset.move));
  task.dueDate = tomorrowISO();
  sync(api.updateTask(task.id, { dueDate: task.dueDate }));
  persistTasks();
  renderReview();
});

els.reviewForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("review-text").value.trim();
  if (text) addNote("reflection", text);
  els.reviewForm.reset();
  els.reviewDialog.close();
});

$("review-close").addEventListener("click", () => els.reviewDialog.close());

/* ---------- Planner (day / week / month) ---------- */

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const addDays = (date, days) => {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
};
const startOfWeek = (date) => addDays(date, -((date.getDay() + 6) % 7)); // weeks start on Monday
const shortDate = (date) => date.toLocaleDateString("en-GB", { day: "numeric", month: "short" });

function plannerRange() {
  const cursor = state.cursor;
  if (state.view === "day") {
    const title = cursor.toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });
    return { start: cursor, count: 1, title };
  }
  if (state.view === "week") {
    const start = startOfWeek(cursor);
    const end = addDays(start, 6);
    return { start, count: 7, title: `${shortDate(start)} – ${shortDate(end)} ${end.getFullYear()}` };
  }
  const firstOfMonth = new Date(cursor.getFullYear(), cursor.getMonth(), 1);
  const title = cursor.toLocaleDateString("en-GB", { month: "long", year: "numeric" });
  return { start: startOfWeek(firstOfMonth), count: 42, title };
}

const dayItems = (iso) => ({
  open: state.tasks.filter((task) => task.status !== "done" && task.dueDate === iso).sort(byTime),
  done: state.completions.filter((entry) => entry.completedDate === iso),
  notes: state.notes.filter((note) => note.date === iso),
});

const plannerChip = (task) => {
  const time = task.blockStart || task.dueTime;
  return `<button type="button" class="chip ${task.status}" data-id="${task.id}">${time ? `${time} ` : ""}${escapeHtml(task.title)}</button>`;
};

const doneChip = (entry) => `<span class="chip done-log" title="Completed">✓ ${escapeHtml(entry.title)}</span>`;

const noteChip = (note) =>
  `<button type="button" class="chip note-chip" data-note-date="${note.date}" title="Open this day">📝 ${escapeHtml(note.category)}: ${escapeHtml(note.text)}</button>`;

const dayNote = (note) => {
  const task = findTask(note.taskId);
  return `<div class="day-note">
    <span class="note-tag">${escapeHtml(note.category)}</span>${task ? ` <small>↗ ${escapeHtml(task.title)}</small>` : ""}
    <p>${escapeHtml(note.text)}</p>
  </div>`;
};

function renderDayDetail(iso) {
  const { open, done, notes } = dayItems(iso);
  const hourOf = (task) => Math.min(22, Math.max(6, Number(task.blockStart.slice(0, 2))));

  const rows = Array.from({ length: 17 }, (_, i) => {
    const hour = i + 6;
    const label = `${pad(hour)}:00`;
    const blocks = open
      .filter((task) => task.blockStart && hourOf(task) === hour)
      .map((task) => `<button type="button" class="chip block ${task.status}" data-id="${task.id}">${blockRange(task)} · ${escapeHtml(task.title)}</button>`)
      .join("");
    return `<div class="hour-row" data-hour="${label}"><span class="hour-label">${label}</span><div class="hour-slot">${blocks}</div></div>`;
  }).join("");

  const loose = open.filter((task) => !task.blockStart);
  return `<div class="day-cell day-detail" data-date="${iso}">
    <div class="day-section">Time blocks (click an hour to add one)</div>${rows}
    <div class="day-section">No time block (${loose.length})</div>
    ${loose.map(plannerChip).join("") || '<p class="day-empty">Nothing here.</p>'}
    <div class="day-section">Completed (${done.length})</div>
    ${done.map(doneChip).join("") || '<p class="day-empty">Nothing completed this day.</p>'}
    <div class="day-section">Notes &amp; reflections (${notes.length})</div>
    ${notes.map(dayNote).join("") || '<p class="day-empty">No notes written this day.</p>'}
  </div>`;
}

function renderPlanner() {
  const { start, count, title } = plannerRange();
  const today = todayISO();
  const isMonth = state.view === "month";

  els.plannerTitle.textContent = title;
  els.plannerGrid.className = `planner-grid ${state.view}`;

  if (state.view === "day") {
    els.plannerGrid.innerHTML = renderDayDetail(toISO(start));
    return;
  }

  const labels = isMonth ? WEEKDAYS.map((day) => `<div class="weekday-label">${day}</div>`).join("") : "";
  const cells = Array.from({ length: count }, (_, i) => {
    const date = addDays(start, i);
    const iso = toISO(date);
    const { open, done, notes } = dayItems(iso);
    const chips = open.map(plannerChip).join("") + done.map(doneChip).join("") + notes.map(noteChip).join("");
    const outside = isMonth && date.getMonth() !== state.cursor.getMonth();
    const head = isMonth ? date.getDate() : date.toLocaleDateString("en-GB", { weekday: "short", day: "numeric" });
    return `<div class="day-cell ${iso === today ? "today" : ""} ${outside ? "outside" : ""}" data-date="${iso}">
      <div class="day-head">${head}</div>${chips}</div>`;
  }).join("");

  els.plannerGrid.innerHTML = labels + cells;
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".view-btn").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === view));
  els.board.hidden = view !== "board";
  els.planner.hidden = view === "board";
  if (view !== "board") renderPlanner();
}

function movePlanner(direction) {
  const cursor = state.cursor;
  if (state.view === "month") {
    state.cursor = new Date(cursor.getFullYear(), cursor.getMonth() + direction, 1);
  } else {
    state.cursor = addDays(cursor, direction * (state.view === "week" ? 7 : 1));
  }
  renderPlanner();
}

document.querySelector(".view-switcher").addEventListener("click", (event) => {
  const button = event.target.closest(".view-btn");
  if (button) setView(button.dataset.view);
});
$("planner-prev").addEventListener("click", () => movePlanner(-1));
$("planner-next").addEventListener("click", () => movePlanner(1));
$("planner-today").addEventListener("click", () => {
  state.cursor = new Date();
  renderPlanner();
});

els.plannerGrid.addEventListener("click", (event) => {
  const chip = event.target.closest(".chip");
  if (chip) {
    openEditDialog(findTask(Number(chip.dataset.id)));
    return;
  }
  const noteLink = event.target.closest(".note-chip");
  if (noteLink) {
    state.cursor = new Date(`${noteLink.dataset.noteDate}T00:00:00`);
    setView("day");
    return;
  }
  if (event.target.closest(".day-note")) return;

  const row = event.target.closest(".hour-row");
  if (row) {
    openAddDialog("todo", row.closest(".day-cell").dataset.date, row.dataset.hour);
    return;
  }

  const cell = event.target.closest(".day-cell");
  if (cell) openAddDialog("todo", cell.dataset.date);
});

/* ---------- Planning mode ---------- */

const planning = { timerId: null, endsAt: 0, minutes: 0 };
const planningEls = {
  dialog: $("planning-dialog"),
  setup: $("planning-setup"),
  session: $("planning-session"),
  timer: $("planning-timer"),
  progress: $("planning-progress"),
  carry: $("planning-carry"),
  today: $("planning-today"),
  notes: $("planning-notes"),
};

function renderPlanningLists() {
  const today = todayISO();
  const yesterday = toISO(addDays(new Date(), -1));
  planningEls.notes.innerHTML =
    state.notes
      .filter((note) => note.date === yesterday)
      .map((note) => `<li><span><strong>${escapeHtml(note.category)}:</strong> ${escapeHtml(note.text)}</span></li>`)
      .join("") || "<li>No notes from yesterday.</li>";

  const open = state.tasks.filter((task) => task.status !== "done" && task.dueDate);
  const carried = open.filter((task) => task.dueDate < today);
  const todays = open.filter((task) => task.dueDate === today).sort(byTime);

  planningEls.carry.innerHTML =
    carried
      .map((task) => `<li><span>${escapeHtml(task.title)}</span><button type="button" class="action-btn" data-plan-move="${task.id}">Move to today</button></li>`)
      .join("") || "<li>Nothing carried over.</li>";

  planningEls.today.innerHTML =
    todays
      .map((task) => `<li><span>${task.blockStart ? `${blockRange(task)} · ` : ""}${escapeHtml(task.title)}</span><button type="button" class="action-btn secondary" data-plan-edit="${task.id}">Time block</button></li>`)
      .join("") || "<li>No tasks for today yet. Add some with ＋ Add Task.</li>";
}

function tickPlanning() {
  const total = planning.minutes * 60000;
  const left = Math.max(0, planning.endsAt - Date.now());
  planningEls.timer.textContent = `${pad(Math.floor(left / 60000))}:${pad(Math.floor((left % 60000) / 1000))}`;
  planningEls.progress.style.width = `${100 - (left / total) * 100}%`;

  if (left === 0) {
    clearInterval(planning.timerId);
    planning.timerId = null;
    notify("Planning time is up. Finish your plan and start the day.");
  }
}

function startPlanning(minutes) {
  planning.minutes = minutes;
  planning.endsAt = Date.now() + minutes * 60000;
  planningEls.setup.hidden = true;
  planningEls.session.hidden = false;
  renderPlanningLists();
  tickPlanning();
  clearInterval(planning.timerId);
  planning.timerId = setInterval(tickPlanning, 1000);
}

$("plan-btn").addEventListener("click", () => {
  planningEls.setup.hidden = false;
  planningEls.session.hidden = true;
  planningEls.dialog.showModal();
});

planningEls.dialog.addEventListener("close", () => {
  clearInterval(planning.timerId);
  planning.timerId = null;
});

planningEls.dialog.addEventListener("click", (event) => {
  const duration = event.target.closest("[data-minutes]");
  if (duration) startPlanning(Number(duration.dataset.minutes));

  if (event.target.closest("[data-close-planning]")) planningEls.dialog.close();

  const move = event.target.closest("[data-plan-move]");
  if (move) {
    const task = findTask(Number(move.dataset.planMove));
    task.dueDate = todayISO();
    sync(api.updateTask(task.id, { dueDate: task.dueDate }));
    persistTasks();
  }

  const edit = event.target.closest("[data-plan-edit]");
  if (edit) openEditDialog(findTask(Number(edit.dataset.planEdit)));
});

planningEls.session.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("planning-text").value.trim();
  if (text) addNote("planning", text);
  planningEls.session.reset();
  planningEls.dialog.close();
});

/* ---------- Theme ---------- */

const darkQuery = window.matchMedia("(prefers-color-scheme: dark)");

function applyTheme() {
  const useDark = state.settings.theme === "dark" || (state.settings.theme === "system" && darkQuery.matches);
  document.documentElement.dataset.theme = useDark ? "dark" : "light";
}

els.theme.value = state.settings.theme;
els.theme.addEventListener("change", () => {
  state.settings.theme = els.theme.value;
  save("settings", state.settings);
  applyTheme();
});
darkQuery.addEventListener("change", applyTheme);

/* ---------- Start ---------- */

applyTheme();

els.today.textContent = new Date().toLocaleDateString("en-GB", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});
async function init() {
  try {
    [state.tasks, state.notes, state.completions] = await Promise.all([
      api.listTasks(),
      api.listNotes(),
      api.listCompletions(),
    ]);
  } catch (error) {
    console.error(error);
    notify("Could not load data. Is the Flask server running?");
  }
  state.tasks.filter((task) => task.status === "done").forEach(syncCompletion); // backfill history
  render();
  renderNotes();
  checkReminders();
  checkDeadlines();
}

init();