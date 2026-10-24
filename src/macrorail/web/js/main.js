// Entry point: keeps the state pushed by the server, routes clicks to actions, renders.
//
// Each tab lives in its own module exporting `actions` (click handlers by data-action) and
// `render(ctx)`. Everything shown is derived from the latest state; nothing is polled.
//
// Two workspaces share the page: 2D (focus stacking, today's app) and 3D (scanning with the
// scan module). Elements marked data-only="2d" or "3d" show in that workspace only; the rail's
// Position card is moved into whichever workspace is showing, so it exists once.

import { connectUpdates, patch, post } from "./api.js";
import * as alerts from "./alerts.js";
import * as camera from "./camera.js";
import * as centre from "./centre.js";
import { $, setChecked, setField, setText } from "./dom.js";
import * as fmt from "./format.js";
import * as liveview from "./liveview.js";
import { readPref, writePref } from "./prefs.js";
import * as review from "./review.js";
import * as rig from "./rig.js";
import * as scan from "./scan.js";
import * as shoot from "./shoot.js";
import * as system from "./system.js";
import { showToast } from "./toast.js";

const PANELS = [liveview, shoot, rig, centre, scan, camera, review, system, alerts];
const TABS = { "2d": ["shoot", "camera", "review", "system"], "3d": ["rig", "centre", "scan", "camera", "review", "system"] };
const TAB_PREF = { "2d": "tab", "3d": "tab-3d" };
const LOG_LIMIT = 200;
const SCAN_TASKS = {
  range: "Finding the focus range…",
  backlash: "Measuring backlash…",
  "tilt level": "Levelling tilt…",
  centring: "Centring: looking from four sides…",
  height: "Measuring the height…",
};

const app = {
  state: null,
  connected: false,
  workspace: readPref("workspace", "2d") === "3d" ? "3d" : "2d",
  tab: null,
  render,
};
app.tab = savedTab(app.workspace);
let receivedHistory = false;

const actions = {
  "take-control": () => post("control/take"),
  stop: () => post("stop"),
  workspace: (button) => showWorkspace(button.dataset.workspace),
  ...Object.assign({}, ...PANELS.map((panel) => panel.actions || {})),
};
const fieldHandlers = shoot.fields;

// -- input --------------------------------------------------------------------------------------

document.addEventListener("click", async (event) => {
  const tab = event.target.closest("[role=tab]");
  if (tab) {
    app.tab = tab.dataset.tab;
    writePref(TAB_PREF[app.workspace], app.tab);
    render();
    return;
  }
  const target = event.target.closest("[data-action]");
  if (!target || target.disabled || !app.state) return;
  const action = actions[target.dataset.action];
  if (!action) return;
  try {
    await action(target, app);
  } catch (error) {
    showToast(error.message, "error");
  }
});

// Settings fields save when they change; a rejected value is put back by the next render.
document.addEventListener("change", async (event) => {
  const input = event.target;
  if (!(input instanceof HTMLInputElement) || !app.state) return;
  const handler = fieldHandlers[input.id];
  if (input.dataset.plan) {
    try {
      await patch("scan3d/plan", scan.planPatch(input));
    } catch (error) {
      showToast(error.message, "error");
      render(true);
    }
    return;
  }
  if (!input.dataset.setting && !handler) return;
  try {
    let body;
    if (handler) body = handler(readInput(input), app);
    else {
      const [section, key] = input.dataset.setting.split(".");
      body = { [section]: { [key]: readInput(input) } };
    }
    await patch("settings", body);
  } catch (error) {
    showToast(error.message, "error");
    render(true);
  }
});

function readInput(input) {
  if (input.type === "checkbox") return input.checked;
  if (input.type === "text") return input.value.trim();
  if (input.value === "" || !Number.isFinite(Number(input.value))) throw new Error("Enter a number.");
  return Number(input.value);
}

// Enter in a field commits it, like leaving the field.
document.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && event.target instanceof HTMLInputElement) event.target.blur();
});

// -- workspaces ---------------------------------------------------------------------------------

function savedTab(workspace) {
  const tab = readPref(TAB_PREF[workspace], TABS[workspace][0]);
  return TABS[workspace].includes(tab) ? tab : TABS[workspace][0];
}

function showWorkspace(workspace) {
  if (!(workspace in TABS) || workspace === app.workspace) return;
  app.workspace = workspace;
  writePref("workspace", workspace);
  app.tab = savedTab(workspace);
  placeWorkspace();
  render();
}

/** Show the workspace's elements and move the rail's Position card into it. */
function placeWorkspace() {
  document.body.dataset.workspace = app.workspace;
  setChecked($("workspace-switch"), "data-workspace", app.workspace);
  const card = $("position-card");
  if (app.workspace === "3d") $("position-slot-3d").append(card);
  else document.querySelector("[data-panel=shoot]").prepend(card);
}

// -- rendering ----------------------------------------------------------------------------------

function render(force = false) {
  const s = app.state;
  renderTabs();
  if (!s) return;
  const { rail } = s;
  const mine = s.control.mine && app.connected;
  const busy = s.activity !== "idle";
  const canMove = mine && rail.connected && rail.driver_ok && !busy;
  const ctx = {
    s,
    spm: rail.steps_per_mm,
    connected: app.connected,
    mine,
    busy,
    canMove,
    canPosition: canMove && rail.homed,
    force,
    tab: app.tab,
    workspace: app.workspace,
    render,
  };

  $("connection-banner").hidden = app.connected;
  $("control-banner").hidden = !app.connected || s.control.mine;
  if (!rail.connected) setPill("rail-pill", "bad", "Rail offline");
  else if (!rail.driver_ok) setPill("rail-pill", "bad", "No driver power");
  else if (rail.homed) setPill("rail-pill", "ok", "Homed");
  else setPill("rail-pill", "warn", "Not homed");
  setPill("camera-pill", s.camera.connected ? "ok" : "bad", s.camera.connected ? s.camera.model : "No camera");
  const m = s.module;
  if (!m.connected) setPill("module-pill", "bad", "Module offline");
  else if (m.tilt_homed && m.yaw_homed) setPill("module-pill", "ok", "Module homed");
  else setPill("module-pill", "warn", "Module not homed");
  $("stop").hidden = !app.connected || !busy;

  renderStatus(s);
  renderSettingFields(ctx);
  for (const panel of PANELS) panel.render(ctx);
}

function renderTabs() {
  for (const button of document.querySelectorAll("[role=tab]")) {
    const selected = button.dataset.tab === app.tab;
    button.setAttribute("aria-selected", String(selected));
  }
  for (const panel of document.querySelectorAll(".tab-panel")) panel.hidden = panel.dataset.panel !== app.tab;
}

/** One line under the live view about whatever is running, visible from every tab. */
function renderStatus(s) {
  const strip = $("status-strip");
  const stack = s.stack;
  let text = "";
  let detail = "";
  let progress = null; // null: indeterminate
  if (stack && shoot.isActive(stack)) {
    text = `Stack: ${shoot.phaseText(stack)}`;
    detail = `${stack.taken} / ${stack.total}${stack.remaining_s !== null ? ` · ${fmt.duration(stack.remaining_s)} left` : ""}`;
    progress = stack.taken / stack.total;
  } else if ((s.activity === "scanning" || s.activity === "scanning_3d") && s.scan.task) {
    text = SCAN_TASKS[s.scan.task] || "Scanning…";
    detail = `${s.scan.done} / ${s.scan.total}`;
    progress = s.scan.total ? s.scan.done / s.scan.total : 0;
  } else if (s.activity !== "idle") {
    text = shoot.activityText(s.activity);
  }
  strip.hidden = !text;
  setText("status-text", text);
  setText("status-detail", detail);
  strip.classList.toggle("indeterminate", progress === null);
  $("status-fill").style.width = progress === null ? "" : `${Math.round(progress * 100)}%`;
}

/** Inputs bound to a setting with data-setting="section.key". */
function renderSettingFields({ s, mine, force }) {
  for (const input of document.querySelectorAll("input[data-setting]")) {
    const [section, key] = input.dataset.setting.split(".");
    setField(input, s.settings[section][key], force);
    input.disabled = !mine;
  }
}

function setPill(id, tone, text) {
  const pill = $(id);
  pill.className = `pill ${tone}`;
  pill.querySelector("span").textContent = text;
  pill.title = text;
}

// -- activity log -------------------------------------------------------------------------------

function addLog(entries) {
  const list = $("log-list");
  if (!receivedHistory) list.replaceChildren();
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
  setText("log-latest", latest ? latest.lastElementChild.textContent : "");
  receivedHistory = true;
}

// -- start ----------------------------------------------------------------------------------

// The service worker makes the app installable; browsers only allow it on HTTPS or localhost.
if ("serviceWorker" in navigator && window.isSecureContext) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}

placeWorkspace();
renderTabs();
connectUpdates({
  onState(next) {
    const first = app.state === null;
    app.state = next;
    // A 3D scan runs for hours: whoever opens the app then wants to see it.
    if (first && next.activity === "scanning_3d" && app.workspace !== "3d") showWorkspace("3d");
    else render();
  },
  onLog: addLog,
  onConnection(isConnected) {
    app.connected = isConnected;
    if (!isConnected) receivedHistory = false;
    render();
    if (!app.state) $("connection-banner").hidden = isConnected;
  },
});
