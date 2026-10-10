// All persistence lives here. At Level 9 only this file changes:
// load/save will call the Python API with fetch() instead of localStorage.
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