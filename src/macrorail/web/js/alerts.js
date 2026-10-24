// Tells you when a stack needs you: it finished, stopped, failed, or paused on a camera
// problem. During a 3D scan, the scan's own end and pauses are told instead of each pose's
// stack (a camera problem still is). A chime and vibration on this device, the tab title, and
// (where the browser allows it: HTTPS or localhost) a system notification.

import { $ } from "./dom.js";
import { readPref, writePref } from "./prefs.js";

const ACTIVE = new Set(["preparing", "running", "paused", "returning"]);
const MESSAGES = {
  done: ["Stack complete", "All shots taken; the rail is back at the start."],
  stopped: ["Stack stopped", "The rail is back at the start."],
  failed: ["Stack failed", "Open MacroRail to see why."],
  camera_error: ["Stack paused: camera problem", "Fix the camera, then resume to retake the shot."],
};
const SCAN_ACTIVE = new Set(["running", "pausing", "paused", "stopping"]);
const SCAN_MESSAGES = {
  done: ["Scan complete", "Every pose is shot."],
  stopped: ["Scan stopped", "Continue it from the Scan tab."],
  failed: ["Scan failed", "Open MacroRail to see why."],
};
const TITLE = document.title;
const canNotify = "Notification" in window && window.isSecureContext;

let sound = readPref("alert-sound", true);
let seenId = null;
let seenPhase = null;
let seenScan = null; // [id, phase, error] of the 3D scan last seen
let audio = null;

$("alert-sound").checked = sound;
$("alert-sound").addEventListener("change", (event) => {
  sound = event.target.checked;
  writePref("alert-sound", sound);
});

// Browsers only allow sound and vibration after the page has been touched: prepare on first touch.
document.addEventListener(
  "pointerdown",
  () => {
    audio ??= new AudioContext();
  },
  { once: true },
);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) document.title = TITLE;
});

export const actions = {
  "enable-notifications": async (_el, app) => {
    await Notification.requestPermission();
    app.render();
  },
};

export function render({ s }) {
  renderSettings();
  const scanning = renderScan(s.scan3d.run);
  const stack = s.stack;
  if (!stack) return;
  if (stack.id !== seenId) {
    // A stack seen for the first time (e.g. on page load) is not news.
    seenId = stack.id;
    seenPhase = stack.phase;
    return;
  }
  if (stack.phase === seenPhase) return;
  const previous = seenPhase;
  seenPhase = stack.phase;
  if (stack.phase === "camera_error" || (!scanning && ACTIVE.has(previous) && MESSAGES[stack.phase])) {
    alert(...MESSAGES[stack.phase], stack.phase === "done");
  }
}

/** Alerts for the 3D scan; returns whether one is running (its poses' stacks stay quiet). */
function renderScan(run) {
  if (!run) return false;
  const now = [run.id, run.phase, run.error];
  const before = seenScan;
  seenScan = now;
  const active = SCAN_ACTIVE.has(run.phase);
  if (!before || before[0] !== run.id) return active; // not news on page load
  if (before[1] !== run.phase && SCAN_ACTIVE.has(before[1]) && SCAN_MESSAGES[run.phase]) {
    alert(...SCAN_MESSAGES[run.phase], run.phase === "done");
  } else if (run.error && run.error !== before[2] && run.phase === "paused") {
    alert("Scan paused", run.error, false); // e.g. the specimen wasn't found
  }
  return active;
}

function renderSettings() {
  const row = $("notify-row");
  const note = $("notify-note");
  if (!canNotify) {
    row.hidden = true;
    note.textContent =
      "System notifications need the app to be opened over HTTPS (or on the Pi itself). Sound, vibration and the tab title work anyway.";
    return;
  }
  const permission = Notification.permission;
  row.hidden = permission !== "default";
  note.textContent =
    permission === "granted"
      ? "Notifications are on for this device."
      : permission === "denied"
        ? "Notifications are blocked for this site in the browser's settings."
        : "";
}

function alert(title, body, success) {
  if (sound && audio) {
    chime(success);
    navigator.vibrate?.(success ? [200, 100, 200] : [400, 150, 400]);
  }
  if (document.hidden) document.title = `● ${title} · MacroRail`;
  if (canNotify && Notification.permission === "granted") {
    new Notification(title, { body, icon: "icons/icon-192.png", tag: "macrorail-stack" });
  }
}

/** Two short tones: rising when all went well, falling when it needs attention. */
function chime(success) {
  const notes = success ? [660, 880] : [660, 440];
  notes.forEach((frequency, i) => {
    const start = audio.currentTime + i * 0.22;
    const oscillator = audio.createOscillator();
    const gain = audio.createGain();
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.0001, start);
    gain.gain.exponentialRampToValueAtTime(0.25, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.2);
    oscillator.connect(gain).connect(audio.destination);
    oscillator.start(start);
    oscillator.stop(start + 0.21);
  });
}
