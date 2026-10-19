// The Shoot tab: position and jogging, the focus range (manual or found automatically),
// the stack itself, and the step-size helper.

import { patch, post } from "./api.js";
import { $, disable, el, setChecked, setField, setText } from "./dom.js";
import * as fmt from "./format.js";
import { readPref, writePref } from "./prefs.js";

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
  scanning: "Scanning…",
};
// Common objectives for the step helper: [label, magnification, NA].
const LENSES = [
  ["2× objective, NA 0.06", 2, 0.06],
  ["4× objective, NA 0.10", 4, 0.1],
  ["5× Mitutoyo, NA 0.14", 5, 0.14],
  ["10× objective, NA 0.25", 10, 0.25],
  ["10× Mitutoyo, NA 0.28", 10, 0.28],
  ["20× objective, NA 0.40", 20, 0.4],
];

let jogUm = readPref("jog-um", 50);

export const isActive = (stack) => stack !== null && ACTIVE_PHASES.has(stack.phase);
export const activityText = (activity) => ACTIVITY_TEXT[activity] || "";
export const phaseText = (stack) =>
  stack.stopping ? "Stopping…" : stack.pausing ? "Pausing after this shot…" : PHASE_TEXT[stack.phase];

export const actions = {
  home: () => post("rail/home"),
  motors: (_el, app) => post("rail/motors", { enabled: !app.state.rail.enabled }),
  jog: (button, app) => {
    const steps = Math.max(1, fmt.fromUm(jogUm, app.state.rail.steps_per_mm));
    return post("rail/jog", { delta: Number(button.dataset.direction) * steps });
  },
  "jog-step": (button, app) => {
    jogUm = Number(button.dataset.um);
    writePref("jog-um", jogUm);
    app.render();
  },
  mode: (button) => patch("settings", { stack: { mode: button.dataset.mode } }),
  direction: (button) => patch("settings", { stack: { direction: Number(button.dataset.direction) } }),
  "set-point": (button) => post(`points/${button.dataset.point}`, {}),
  "go-point": (button) => post(`points/${button.dataset.point}/go`),
  "find-range": () => post("scan/range"),
  "apply-range": () => post("scan/range/apply"),
  preview: () => post("preview"),
  "stack-start": () => post("stack/start"),
  "stack-pause": () => post("stack/pause"),
  "stack-resume": () => post("stack/resume"),
  "open-step-helper": (_el, app) => {
    app.render(true);
    $("step-helper").showModal();
  },
  "use-suggested-step": (_el, app) => patch("settings", { stack: { step: app.state.optics.suggested_step } }),
};

// Fields this tab converts before saving (the rest use data-setting directly).
export const fields = {
  "step-input": (value, app) => ({ stack: { step: Math.max(1, fmt.fromUm(value, app.state.rail.steps_per_mm)) } }),
  "count-input": (value) => ({ stack: { count: Math.round(value) } }),
};

$("lens-preset").append(
  el("option", { value: "" }, "Custom"),
  ...LENSES.map(([label], i) => el("option", { value: String(i) }, label)),
);
$("lens-preset").addEventListener("change", async (event) => {
  const lens = LENSES[Number(event.target.value)];
  if (lens) await patch("settings", { optics: { magnification: lens[1], na: lens[2] } }).catch(() => {});
});

export function render(ctx) {
  renderPosition(ctx);
  renderRange(ctx);
  renderStack(ctx);
  renderHelper(ctx);
}

function renderPosition({ s, spm, canMove }) {
  const { rail } = s;
  setText("position-mm", rail.connected ? fmt.mm(rail.position, spm) : "–");
  $("position-mm").parentElement.classList.toggle("unhomed", !rail.homed);
  setText(
    "position-detail",
    rail.problem ||
      activityText(s.activity) ||
      (rail.endstop ? "Home switch pressed" : rail.homed ? "Ready" : "Home the rail to use positions and stacks"),
  );
  const badge = $("homed-badge");
  badge.textContent = rail.homed ? "Homed" : "Not homed";
  badge.classList.toggle("ok", rail.homed);
  $("home").disabled = !canMove;
  $("motors").disabled = !canMove;
  $("motors").textContent = rail.enabled ? "Motor off" : "Motor on";

  const steps = $("jog-steps");
  if (!steps.childElementCount) {
    for (const um of JOG_STEPS_UM) {
      const label = um < 100 ? `${um} µm` : `${um / 1000} mm`;
      steps.append(el("button", { "data-action": "jog-step", "data-um": String(um), role: "radio" }, label));
    }
  }
  setChecked(steps, "data-um", jogUm);
  for (const button of steps.children) button.disabled = !canMove;
  disable('[data-action="jog"]', !canMove);
}

function renderRange({ s, spm, mine, canPosition, force }) {
  const st = s.settings.stack;
  const countMode = st.mode === "count";
  setChecked($("mode-switch"), "data-mode", st.mode);
  setChecked($("direction-switch"), "data-direction", st.direction);
  $("end-row").hidden = countMode;
  $("count-row").hidden = !countMode;
  setText("start-value", st.start === null ? "–" : `${fmt.mm(st.start, spm)} mm`);
  setText("end-value", st.end === null ? "–" : `${fmt.mm(st.end, spm)} mm`);
  disable('[data-action="set-point"]', !canPosition);
  for (const button of document.querySelectorAll('[data-action="go-point"]')) {
    button.disabled = !canPosition || st[button.dataset.point] === null;
  }
  disable('[data-action="mode"], [data-action="direction"]', !mine);
  setField($("count-input"), st.count, force);
  $("count-input").disabled = !mine;
  $("preview").disabled = !canPosition || Boolean(s.plan.error);

  const liveView = s.camera.connected && s.camera.live_view;
  $("find-range").disabled = !canPosition || !liveView;
  const result = s.scan.range;
  $("range-result").hidden = !result;
  if (result) {
    drawCoverage(result, s.rail.position);
    const applied = st.start === result.start && st.end === result.end && st.mode === "range";
    setText(
      "range-text",
      `Subject in focus from ${fmt.mm(result.start, spm)} to ${fmt.mm(result.end, spm)} mm ` +
        `(${fmt.length(result.end - result.start, spm)} deep).`,
    );
    $("range-clipped").hidden = !result.clipped;
    $("apply-range").disabled = !mine || applied || s.activity !== "idle";
    $("apply-range").textContent = applied ? "Range in use" : "Use this range";
  }
}

/** Coverage (share of the subject in focus) along the scan, with the found range marked. */
function drawCoverage(result, position) {
  const svg = $("range-chart");
  const key = `${result.positions[0]}:${result.positions.length}:${result.start}:${result.end}:${position}`;
  if (svg.dataset.key === key) return;
  svg.dataset.key = key;
  const first = result.positions[0];
  const span = result.positions[result.positions.length - 1] - first || 1;
  const x = (p) => ((p - first) / span) * 300;
  const peak = Math.max(...result.coverage, 0.01);
  const points = result.positions.map((p, i) => `${x(p).toFixed(1)},${(66 - (result.coverage[i] / peak) * 60).toFixed(1)}`);
  const band = `<rect class="chart-band" x="${x(result.start)}" y="0" width="${Math.max(1, x(result.end) - x(result.start))}" height="70"/>`;
  const here = position >= first && position <= first + span ? `<line class="chart-here" x1="${x(position)}" x2="${x(position)}" y1="0" y2="70"/>` : "";
  svg.innerHTML = `${band}<polyline class="chart-line" points="${points.join(" ")}"/>${here}`;
}

function renderStack({ s, spm, mine, canPosition, force }) {
  const { stack, plan, settings } = s;
  const st = settings.stack;
  const active = isActive(stack);
  setField($("step-input"), fmt.um(st.step, spm), force);
  $("step-input").disabled = !mine;
  $("step-input").step = String(1000 / spm);
  setText("step-detail", `${st.step} microstep${st.step === 1 ? "" : "s"} per shot · the rail moves in ${fmt.um(1, spm)} µm increments`);

  const summary = $("plan-summary");
  summary.hidden = active;
  if (plan.error) summary.textContent = plan.error;
  else {
    summary.replaceChildren(
      el("strong", {}, `${plan.count} shots`),
      ` over ${fmt.length(plan.end - plan.start, spm)}, about ${fmt.duration(plan.estimate_s)}`,
    );
  }

  setText("stack-status", stack ? (active || stack.phase !== "done" ? phaseText(stack) : `Complete: ${stack.taken} shots`) : "");
  $("stack-progress").hidden = !stack;
  if (stack) {
    $("stack-progress-fill").style.width = `${(100 * stack.taken) / stack.total}%`;
    setText("stack-count", `${stack.taken} / ${stack.total}`);
    const times = [`${fmt.duration(stack.elapsed_s)} elapsed`];
    if (stack.remaining_s !== null) times.push(`${fmt.duration(stack.remaining_s)} left`);
    setText("stack-times", times.join(" · "));
    const file = stack.last_file ? `Last file: ${stack.last_file}` : "";
    setText("stack-file", stack.previews ? `${file} · ${stack.previews} previews` : file);
    setText("stack-error", stack.error || "");
    $("stack-error").hidden = !stack.error;
  }

  const start = $("stack-start");
  start.hidden = active;
  start.textContent = plan.error ? "Start stack" : `Start stack · ${plan.count} shots`;
  start.disabled = !canPosition || Boolean(plan.error) || !s.camera.connected;
  const pausable = active && ["preparing", "running"].includes(stack.phase) && !stack.pausing && !stack.stopping;
  $("stack-pause").hidden = !pausable;
  $("stack-pause").disabled = !mine;
  $("stack-resume").hidden = !(active && ["paused", "camera_error"].includes(stack.phase) && !stack.stopping);
  $("stack-resume").disabled = !mine;
}

function renderHelper({ s, spm, mine, force }) {
  const { optics, settings, plan } = s;
  setText("helper-dof", `${optics.dof_um.toFixed(1)} µm`);
  setText("helper-step", `${fmt.um(optics.suggested_step, spm)} µm`);
  const range = plan.error ? 0 : Math.abs(plan.end - plan.start);
  setText("helper-shots", range ? `For the current range that is about ${Math.ceil(range / optics.suggested_step) + 1} shots.` : "");
  const preset = LENSES.findIndex(([, m, na]) => m === settings.optics.magnification && na === settings.optics.na);
  if (force || document.activeElement !== $("lens-preset")) $("lens-preset").value = preset < 0 ? "" : String(preset);
  $("lens-preset").disabled = !mine;
  $("use-suggested-step").disabled = !mine || settings.stack.step === optics.suggested_step;
}
