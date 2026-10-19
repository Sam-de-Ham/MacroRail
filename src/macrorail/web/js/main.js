import { connectUpdates, patch, post } from "./api.js";
import * as fmt from "./format.js";

const $ = (id) => document.getElementById(id);

const JOG_STEPS_UM = [2.5, 10, 50, 100, 1000, 5000];
const ACTIVE_PHASES = new Set(["preparing", "running", "paused", "camera_error", "returning"]);
const PHASE_TEXT = {
  preparing: "Moving to the start…",
  running: "Shooting",
  paused: "Paused",
  camera_error: "Camera problem: fix it, then resume to retake this shot",
  returning: "Returning to the start…",
  done: "Complete",
  stopped: "Stopped",
  failed: "Failed",
};
const ACTIVITY_TEXT = {
  homing: "Homing…",
  moving: "Moving…",
  previewing: "Previewing the range…",
  stacking: "Stacking",
  capturing: "Taking a test shot…",
};
const LOG_LIMIT = 200;

let state = null;
let connected = false;
let receivedHistory = false;
let jogUm = readPreference("jog-um", 50);
let toastTimer = 0;

// -- preferences (per browser, optional) ------------------------------------------------------

function readPreference(key, fallback) {
  try {
    const value = Number(localStorage.getItem(`macrorail.${key}`));
    return Number.isFinite(value) && value > 0 ? value : fallback;
  } catch {
    return fallback;
  }
}

function writePreference(key, value) {
  try {
    localStorage.setItem(`macrorail.${key}`, String(value));
  } catch {
    // not persisted; fine
  }
}

// -- actions ------------------------------------------------------------------------------------

const stepsPerMm = () => state.rail.steps_per_mm;

const actions = {
  "take-control": () => post("control/take"),
  "open-settings": openSettings,
  stop: () => post("stop"),
  home: () => post("rail/home"),
  motors: () => post("rail/motors", { enabled: !state.rail.enabled }),
  jog: (el) => post("rail/jog", { delta: Number(el.dataset.direction) * Math.max(1, fmt.fromUm(jogUm, stepsPerMm())) }),
  "jog-step": (el) => {
    jogUm = Number(el.dataset.um);
    writePreference("jog-um", jogUm);
    render();
  },
  mode: (el) => patch("settings", { stack: { mode: el.dataset.mode } }),
  direction: (el) => patch("settings", { stack: { direction: Number(el.dataset.direction) } }),
  "set-point": (el) => post(`points/${el.dataset.point}`, {}),
  "go-point": (el) => post(`points/${el.dataset.point}/go`),
  preview: () => post("preview"),
  "stack-start": () => post("stack/start"),
  "stack-pause": () => post("stack/pause"),
  "stack-resume": () => post("stack/resume"),
  "test-shot": () => post("camera/test"),
};

document.addEventListener("click", async (event) => {
  const el = event.target.closest("[data-action]");
  if (!el || el.disabled || !state) return;
  const action = actions[el.dataset.action];
  if (!action) return;
  try {
    await action(el);
  } catch (error) {
    showToast(error.message, "error");
  }
});

// Number fields save when they change; a rejected value is put back by the next render.
const fieldSettings = {
  "step-input": (value) => ({ stack: { step: Math.max(1, fmt.fromUm(value, stepsPerMm())) } }),
  "settle-input": (value) => ({ stack: { settle_s: value } }),
  "count-input": (value) => ({ stack: { count: Math.round(value) } }),
};

document.addEventListener("change", async (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !state) return;
  const value = Number(input.value);
  let body;
  if (input.dataset.setting) {
    const [section, key] = input.dataset.setting.split(".");
    body = { [section]: { [key]: value } };
  } else if (fieldSettings[input.id]) {
    body = fieldSettings[input.id](value);
  } else {
    return;
  }
  try {
    if (input.value === "" || !Number.isFinite(value)) throw new Error("Enter a number.");
    await patch("settings", body);
  } catch (error) {
    showToast(error.message, "error");
    render(true);
  }
});

// Enter in a field commits it, like leaving the field.
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target instanceof HTMLInputElement) event.target.blur();
});

// -- live view ----------------------------------------------------------------------------------

const liveview = $("liveview");
const liveImage = $("liveview-image");

liveview.addEventListener("click", (event) => {
  if (liveview.classList.toggle("zoomed")) {
    const box = liveview.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 100;
    const y = ((event.clientY - box.top) / box.height) * 100;
    liveImage.style.transformOrigin = `${x}% ${y}%`;
    liveImage.style.transform = "scale(3)";
  } else {
    liveImage.style.transform = "";
  }
  $("liveview-hint").textContent = liveview.classList.contains("zoomed") ? "Tap to fit" : "Tap to zoom";
});

function renderLiveView(s) {
  const available = connected && s.live_view.available;
  const wanted = available ? "/api/liveview" : "";
  if (liveImage.getAttribute("src") !== wanted) {
    if (wanted) liveImage.setAttribute("src", wanted);
    else liveImage.removeAttribute("src");
  }
  liveview.classList.toggle("paused", s.live_view.paused);
  const message = !connected
    ? "Not connected"
    : !s.camera.connected
      ? s.camera.problem || "No camera"
      : !s.live_view.available
        ? "This camera has no live view"
        : s.live_view.paused
          ? "Live view is paused while stacking"
          : "";
  $("liveview-message").textContent = message;
  $("liveview-message").hidden = !message;
  $("liveview-hint").hidden = !available || s.live_view.paused;
  $("liveview-position").textContent = s.rail.connected ? `${fmt.mm(s.rail.position, s.rail.steps_per_mm)} mm` : "–";
}

// -- rendering ----------------------------------------------------------------------------------

function setPill(id, tone, text) {
  const pill = $(id);
  pill.className = `pill ${tone}`;
  pill.querySelector("span").textContent = text;
  pill.title = text;
}

function setChecked(container, attribute, value) {
  for (const button of container.querySelectorAll(`[${attribute}]`)) {
    button.setAttribute("aria-checked", String(button.getAttribute(attribute) === String(value)));
  }
}

function setField(id, value, force) {
  const input = $(id);
  if (force || document.activeElement !== input) input.value = value;
}

function renderJogSteps(enabled) {
  const container = $("jog-steps");
  if (!container.childElementCount) {
    for (const value of JOG_STEPS_UM) {
      const button = document.createElement("button");
      button.dataset.action = "jog-step";
      button.dataset.um = String(value);
      button.setAttribute("role", "radio");
      button.textContent = value < 100 ? `${value} µm` : `${value / 1000} mm`;
      container.append(button);
    }
  }
  setChecked(container, "data-um", jogUm);
  for (const button of container.children) button.disabled = !enabled;
}

function render(forceFields = false) {
  if (!state) return;
  const s = state;
  const { rail, camera, settings, plan, stack } = s;
  const spm = rail.steps_per_mm;
  const mine = s.control.mine && connected;
  const busy = s.activity !== "idle";
  const railReady = mine && rail.connected && rail.driver_ok;
  const canMove = railReady && !busy;
  const canPosition = canMove && rail.homed;
  const stackActive = stack !== null && ACTIVE_PHASES.has(stack.phase);

  $("connection-banner").hidden = connected;
  $("control-banner").hidden = !connected || s.control.mine;

  if (!rail.connected) setPill("rail-pill", "bad", "Rail offline");
  else if (!rail.driver_ok) setPill("rail-pill", "bad", "No driver power");
  else if (rail.homed) setPill("rail-pill", "ok", "Homed");
  else setPill("rail-pill", "warn", "Not homed");
  setPill("camera-pill", camera.connected ? "ok" : "bad", camera.connected ? camera.model : "No camera");

  // Position
  $("position-mm").textContent = rail.connected ? fmt.mm(rail.position, spm) : "–";
  $("position-mm").parentElement.classList.toggle("unhomed", !rail.homed);
  $("position-detail").textContent =
    rail.problem || ACTIVITY_TEXT[s.activity] || (rail.homed ? "Ready" : "Home the rail to use positions and stacks");
  const homedBadge = $("homed-badge");
  homedBadge.textContent = rail.homed ? "Homed" : "Not homed";
  homedBadge.classList.toggle("ok", rail.homed);
  $("home").disabled = !canMove;
  $("motors").disabled = !canMove;
  $("motors").textContent = rail.enabled ? "Motor off" : "Motor on";
  renderJogSteps(canMove);
  for (const button of document.querySelectorAll('[data-action="jog"]')) button.disabled = !canMove;

  // Focus range
  const st = settings.stack;
  const countMode = st.mode === "count";
  for (const group of document.querySelectorAll('.segmented:has([data-mode])')) setChecked(group, "data-mode", st.mode);
  setChecked($("count-row"), "data-direction", st.direction);
  $("end-row").hidden = countMode;
  $("count-row").hidden = !countMode;
  $("start-value").textContent = st.start === null ? "–" : `${fmt.mm(st.start, spm)} mm`;
  $("end-value").textContent = st.end === null ? "–" : `${fmt.mm(st.end, spm)} mm`;
  for (const button of document.querySelectorAll('[data-action="set-point"]')) button.disabled = !canPosition;
  for (const button of document.querySelectorAll('[data-action="go-point"]')) {
    button.disabled = !canPosition || st[button.dataset.point] === null;
  }
  for (const button of document.querySelectorAll('[data-action="mode"], [data-action="direction"]')) button.disabled = !mine;
  setField("step-input", fmt.um(st.step, spm), forceFields);
  setField("settle-input", st.settle_s, forceFields);
  setField("count-input", st.count, forceFields);
  for (const id of ["step-input", "settle-input", "count-input"]) $(id).disabled = !mine;
  $("step-input").step = String(1000 / spm);
  $("step-detail").textContent = `${st.step} microstep${st.step === 1 ? "" : "s"} per shot · the rail moves in ${fmt.um(1, spm)} µm increments`;
  $("preview").disabled = !canPosition || Boolean(plan.error);

  // Stack
  $("plan-summary").innerHTML = plan.error
    ? escapeHtml(plan.error)
    : `<strong>${plan.count} shots</strong> over ${fmt.length(plan.end - plan.start, spm)}, about ${fmt.duration(plan.estimate_s)}`;
  $("plan-summary").hidden = stackActive;
  renderStack(stack, stackActive);
  $("stack-start").hidden = stackActive;
  $("stack-start").disabled = !canPosition || Boolean(plan.error) || !camera.connected;
  const pausable = stackActive && ["preparing", "running"].includes(stack.phase) && !stack.pausing && !stack.stopping;
  $("stack-pause").hidden = !pausable;
  $("stack-pause").disabled = !mine;
  $("stack-resume").hidden = !(stackActive && ["paused", "camera_error"].includes(stack.phase) && !stack.stopping);
  $("stack-resume").disabled = !mine;
  $("camera-detail").textContent = camera.connected
    ? [camera.model, camera.battery && `battery ${camera.battery}`].filter(Boolean).join(" · ")
    : camera.problem || "No camera";
  $("test-shot").disabled = !mine || busy || !camera.connected;

  $("stop").hidden = !connected || !busy;
  renderLiveView(s);
  $("about").textContent = `MacroRail ${s.version}${rail.firmware ? ` · rail firmware ${rail.firmware}` : ""}`;
  renderSettingsFields(forceFields);
}

function renderStack(stack, active) {
  const status = $("stack-status");
  if (!stack) {
    status.textContent = "";
    $("stack-progress").hidden = true;
    return;
  }
  let text = PHASE_TEXT[stack.phase];
  if (stack.stopping) text = "Stopping…";
  else if (stack.pausing) text = "Pausing after this shot…";
  status.textContent = active || stack.phase !== "done" ? text : `${text}: ${stack.taken} shots`;
  $("stack-progress").hidden = false;
  $("stack-progress-fill").style.width = `${(100 * stack.taken) / stack.total}%`;
  $("stack-count").textContent = `${stack.taken} / ${stack.total}`;
  const times = [`${fmt.duration(stack.elapsed_s)} elapsed`];
  if (stack.remaining_s !== null) times.push(`${fmt.duration(stack.remaining_s)} left`);
  $("stack-times").textContent = times.join(" · ");
  $("stack-file").textContent = stack.last_file ? `Last file: ${stack.last_file}` : "";
  $("stack-error").textContent = stack.error || "";
  $("stack-error").hidden = !stack.error;
}

// -- settings sheet -----------------------------------------------------------------------------

function openSettings() {
  render(true);
  $("settings").showModal();
}

function renderSettingsFields(force) {
  for (const input of document.querySelectorAll("[data-setting]")) {
    const [section, key] = input.dataset.setting.split(".");
    if (force || document.activeElement !== input) input.value = state.settings[section][key];
    input.disabled = !state.control.mine;
  }
}

// -- activity log and toasts --------------------------------------------------------------------

function addLog(entries) {
  const list = $("log-list");
  if (!receivedHistory) {
    list.replaceChildren();
  }
  for (const entry of entries) {
    const item = document.createElement("li");
    const time = document.createElement("time");
    time.textContent = fmt.clock(entry.time);
    const message = document.createElement("span");
    message.className = entry.level;
    message.textContent = entry.message;
    item.append(time, message);
    list.prepend(item);
    if (receivedHistory && entry.level !== "info") showToast(entry.message, entry.level);
  }
  while (list.childElementCount > LOG_LIMIT) list.lastElementChild.remove();
  const latest = list.firstElementChild;
  $("log-latest").textContent = latest ? latest.lastElementChild.textContent : "";
  receivedHistory = true;
}

function showToast(message, level = "info") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast ${level}`;
  toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.hidden = true;
  }, 5000);
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

// -- start ----------------------------------------------------------------------------------

connectUpdates({
  onState(next) {
    state = next;
    render();
  },
  onLog: addLog,
  onConnection(isConnected) {
    connected = isConnected;
    if (!isConnected) receivedHistory = false;
    render();
    if (!state) $("connection-banner").hidden = isConnected;
  },
});
