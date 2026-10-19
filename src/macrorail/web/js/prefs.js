// Per-browser preferences (tab, jog step, live view, alerts). Storage may be unavailable;
// then the defaults simply apply for this page.

const PREFIX = "macrorail.";

export function readPref(key, fallback) {
  try {
    const raw = localStorage.getItem(PREFIX + key);
    return raw === null ? fallback : JSON.parse(raw);
  } catch {
    return fallback;
  }
}

export function writePref(key, value) {
  try {
    localStorage.setItem(PREFIX + key, JSON.stringify(value));
  } catch {
    // not persisted; fine
  }
}
