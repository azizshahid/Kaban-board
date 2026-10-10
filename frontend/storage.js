// All persistence lives here.
// - Tasks and notes talk to the Flask API (SQLite on the server).
// - Settings (theme, reminder interval) are per-device, so they stay in localStorage.

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(`/api${path}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${method} ${path} failed (${response.status})`);
  return response.status === 204 ? null : response.json();
}

export const api = {
  listTasks: () => request("/tasks"),
  createTask: (task) => request("/tasks", { method: "POST", body: task }),
  updateTask: (id, changes) => request(`/tasks/${id}`, { method: "PUT", body: changes }),
  deleteTask: (id) => request(`/tasks/${id}`, { method: "DELETE" }),
  listNotes: () => request("/notes"),
  createNote: (note) => request("/notes", { method: "POST", body: note }),
  deleteNote: (id) => request(`/notes/${id}`, { method: "DELETE" }),
};

const PREFIX = "productivity-board.";

export function load(key, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw ? JSON.parse(raw) : fallback;
  } catch {
    return fallback;
  }
}

export function save(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch (error) {
    console.error("Could not save", key, error);
  }
}