import { load, save } from "./storage.js";

/* ---------- Data ---------- */

const DEFAULT_TASKS = [
  { id: 1, title: "Create homepage wireframe", description: "Designing the wireframe", label: "Design", color: "purple", status: "todo", dueDate: "2026-10-12" },
  { id: 2, title: "Market research for Yarnanimal.in", description: "Market research for Yarnanimal.in", label: "Market Research", color: "blue", status: "todo", dueDate: "2026-10-13" },
  { id: 3, title: "Talk to Yarnanimal developer", description: "Talk to the developer", label: "Communication", color: "pink", status: "todo", dueDate: "2026-10-11" },
  { id: 4, title: "Raise complaint with AWS", description: "Raise complaint with AWS", label: "Tools", color: "purple", status: "done", dueDate: "2026-10-09" },
  { id: 5, title: "Ask for social media credentials", description: "Then create the strategy", label: "Strategy", color: "orange", status: "progress", dueDate: "2026-10-15" },
];

const state = {
  tasks: load("tasks", DEFAULT_TASKS),
  notes: load("notes", []),
  settings: load("settings", { reminderMinutes: 30 }),
  editingId: null,
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

function persistTasks() {
  save("tasks", state.tasks);
  render();
}

/* ---------- Task cards ---------- */

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
  const isOverdue = !isDone && task.dueDate && task.dueDate < todayISO();
  const labelClass = isDone ? "green-label" : task.color;
  const footer = isDone
    ? `<span class="done-date">✓ Completed</span>`
    : `<span class="due-date ${isOverdue ? "overdue" : ""}">◷ ${formatDate(task.dueDate)}</span>`;

  return `
    <article class="task-card ${isDone ? "completed-card" : ""}" data-id="${task.id}">
      <div class="task-top">
        <span class="task-label ${labelClass}">${escapeHtml(task.label)}</span>
        <button type="button" class="menu-btn" aria-label="Edit task">•••</button>
      </div>
      <h3>${escapeHtml(task.title)}</h3>
      <p>${escapeHtml(task.description)}</p>
      <div class="task-footer">${footer}</div>
      <div class="card-actions">${ACTION_BUTTONS[task.status]}</div>
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
}

/* ---------- Add / edit / delete ---------- */

function openAddDialog(status) {
  state.editingId = null;
  els.taskForm.reset();
  $("dialog-title").textContent = "New Task";
  $("submit-btn").textContent = "Add";
  $("delete-btn").hidden = true;
  $("task-status").value = status;
  $("task-date").value = todayISO();
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
  $("task-color").value = task.color;
  $("task-status").value = task.status;
  $("task-date").value = task.dueDate;
  els.taskDialog.showModal();
}

function readTaskForm() {
  return {
    title: $("task-title").value.trim(),
    description: $("task-desc").value.trim(),
    label: $("task-label").value.trim() || "General",
    color: $("task-color").value,
    status: $("task-status").value,
    dueDate: $("task-date").value,
  };
}

els.taskForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const values = readTaskForm();
  const task = state.editingId === null ? { id: Date.now() } : findTask(state.editingId);

  Object.assign(task, values);
  if (task.status === "progress" && !task.startedAt) task.startedAt = Date.now();
  if (task.status === "done" && !task.completedAt) task.completedAt = Date.now();
  if (state.editingId === null) state.tasks.push(task);

  persistTasks();
  els.taskDialog.close();
});

$("delete-btn").addEventListener("click", () => {
  if (!confirm("Delete this task?")) return;
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

  const button = event.target.closest(".action-btn");
  if (!button) return;
  if (button.dataset.action === "start") requestNotificationPermission();
  ACTIONS[button.dataset.action](task);
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
  let changed = false;

  state.tasks
    .filter((task) => task.status === "progress" && task.startedAt)
    .forEach((task) => {
      const lastPing = task.lastReminderAt || task.startedAt;
      if (now - lastPing >= minutes * 60000) {
        const elapsed = Math.round((now - task.startedAt) / 60000);
        notify(`"${task.title}" has been in progress for ${elapsed} min. Still on it?`);
        task.lastReminderAt = now;
        changed = true;
      }
    });

  if (changed) save("tasks", state.tasks);
}

els.interval.value = String(state.settings.reminderMinutes);
els.interval.addEventListener("change", () => {
  state.settings.reminderMinutes = Number(els.interval.value);
  save("settings", state.settings);
});
setInterval(checkReminders, 30000);

/* ---------- Notes ---------- */

function renderNotes() {
  els.notesList.innerHTML = state.notes
    .map(
      (note) => `
      <li class="note" data-id="${note.id}">
        <div class="note-meta">
          <span class="note-tag">${escapeHtml(note.category)}</span>
          <span>${formatDate(note.date)}</span>
          <button type="button" class="note-delete" aria-label="Delete note">✕</button>
        </div>
        <p>${escapeHtml(note.text)}</p>
      </li>`
    )
    .join("");
}

function addNote(category, text) {
  state.notes.unshift({ id: Date.now(), category, text, date: todayISO() });
  save("notes", state.notes);
  renderNotes();
}

els.noteForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = $("note-text").value.trim();
  if (!text) return;
  addNote($("note-category").value, text);
  els.noteForm.reset();
});

els.notesList.addEventListener("click", (event) => {
  const deleteBtn = event.target.closest(".note-delete");
  if (!deleteBtn) return;
  const id = Number(deleteBtn.closest(".note").dataset.id);
  state.notes = state.notes.filter((note) => note.id !== id);
  save("notes", state.notes);
  renderNotes();
});

/* ---------- End-of-day review ---------- */

function renderReview() {
  const today = todayISO();
  const doneToday = state.tasks.filter(
    (task) => task.status === "done" && task.completedAt && toISO(new Date(task.completedAt)) === today
  ).length;
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
  findTask(Number(moveBtn.dataset.move)).dueDate = tomorrowISO();
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

/* ---------- Start ---------- */

els.today.textContent = new Date().toLocaleDateString("en-GB", {
  weekday: "long", day: "numeric", month: "long", year: "numeric",
});
render();
renderNotes();
checkReminders();
