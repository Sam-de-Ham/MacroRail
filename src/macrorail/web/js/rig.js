// The Rig tab (3D workspace): the scan module's tilt and yaw (homing, jogging, going to a pose,
// quick poses), its pose gauges, and the Scan module card in the System tab.
//
// Angles follow the module's conventions: tilt 0 is level and + turns the insect's back
// towards the camera; yaw + turns the head counter-clockwise seen from above, and at yaw 0
// centring screw X points at the camera.

import { post } from "./api.js";
import { $, el, setChecked, setText } from "./dom.js";
import { readPref, writePref } from "./prefs.js";

const STEPS_DEG = [1, 5, 15, 45];
const UNHOMED_TILT_JOG_DEG = 10; // the server's limit before tilt is homed
const SVG = "http://www.w3.org/2000/svg";

let drawn = null; // what the gauges last showed
let stepDeg = STEPS_DEG.includes(readPref("rotary-step", 5)) ? readPref("rotary-step", 5) : 5;

export const actions = {
  "module-home": (button) => post("module/home", { axes: button.dataset.axes.split(",") }),
  "module-jog": (button) =>
    post("module/jog", { axis: button.dataset.axis, delta_deg: Number(button.dataset.direction) * stepDeg }),
  "rotary-step": (button, app) => {
    stepDeg = Number(button.dataset.deg);
    writePref("rotary-step", stepDeg);
    app.render();
  },
  "pose-go": () => {
    const tilt = angleField("pose-tilt");
    const yaw = angleField("pose-yaw");
    if (tilt === null && yaw === null) throw new Error("Enter a tilt, a yaw or both.");
    return post("module/pose", { tilt, yaw });
  },
  "calibrate-yaw": () => post("module/calibrate/yaw"),
  "calibrate-tilt": () => post("module/calibrate/tilt"),
  pose: (button, app) => {
    const { tilt, yaw } = button.dataset;
    return post("module/pose", {
      tilt: tilt === undefined ? null : tilt === "min" ? app.state.module.tilt_min_deg : Number(tilt),
      yaw: yaw === undefined ? null : Number(yaw),
    });
  },
};

$("rotary-steps").append(
  ...STEPS_DEG.map((deg) =>
    el("button", { "data-action": "rotary-step", "data-deg": String(deg), role: "radio" }, `${deg}°`),
  ),
);

function angleField(id) {
  const raw = $(id).value.trim();
  if (raw === "") return null;
  const value = Number(raw);
  if (!Number.isFinite(value)) throw new Error("Enter angles in degrees.");
  return value;
}

export function render({ s, mine, busy }) {
  const m = s.module;
  const can = mine && m.connected && !busy;
  const badge = !m.connected ? "Offline" : m.tilt_homed && m.yaw_homed ? "Homed" : "Not homed";
  for (const id of ["module-badge", "module-system-badge"]) {
    setText(id, badge);
    $(id).classList.toggle("ok", badge === "Homed");
  }
  $("module-problem").hidden = m.connected;
  setText("module-problem", m.connected ? "" : m.problem || "");

  setText("tilt-value", m.tilt_homed ? `${m.tilt_deg.toFixed(1)}°` : "–");
  setText("yaw-value", m.yaw_homed ? `${m.yaw_deg.toFixed(1)}°` : "–");
  // Redrawn only when what they show changes: state pushes arrive several times a second.
  const gauges = JSON.stringify([m.tilt_homed && m.tilt_deg, m.tilt_min_deg, m.tilt_max_deg, m.yaw_homed && m.yaw_deg]);
  if (gauges !== drawn) {
    drawn = gauges;
    drawTilt($("tilt-gauge"), m.tilt_homed ? m.tilt_deg : null, m.tilt_min_deg, m.tilt_max_deg);
    drawYaw($("yaw-gauge"), m.yaw_homed ? m.yaw_deg : null);
  }

  setChecked($("rotary-steps"), "data-deg", stepDeg);
  for (const button of $("rotary-steps").children) button.disabled = !mine;
  for (const id of ["module-home", "module-home-tilt", "module-home-yaw"]) $(id).disabled = !can;
  for (const button of document.querySelectorAll("[data-action=module-jog]")) {
    const tiltTooFar = button.dataset.axis === "tilt" && !m.tilt_homed && stepDeg > UNHOMED_TILT_JOG_DEG;
    button.disabled = !can || tiltTooFar;
  }
  $("pose-go").disabled = !can || !(m.tilt_homed || m.yaw_homed);
  for (const id of ["pose-tilt", "pose-yaw"]) $(id).disabled = !mine;
  for (const button of document.querySelectorAll("[data-action=pose]")) {
    const needs = button.dataset.tilt !== undefined ? m.tilt_homed : m.yaw_homed;
    button.disabled = !can || !needs;
  }
  setText(
    "tilt-range-note",
    `Tilt goes from ${m.tilt_min_deg}° (belly towards the lens) to ${m.tilt_max_deg}° (top view).` +
      (m.calibration.tilt_calibrated ? "" : " The belly side opens up to the full range once tilt is calibrated."),
  );

  renderSystemCard(m);
  $("calibrate-yaw").disabled = !can;
  const liveView = s.camera.connected && s.camera.live_view;
  $("calibrate-tilt").disabled = !can || !(m.tilt_homed && m.yaw_homed && s.rail.homed && liveView);
}

function renderSystemCard(m) {
  const link = m.link;
  const rows = [
    ["Connection", m.connected ? "Connected" : m.problem || "Offline", m.connected ? "" : "warn"],
    ["Firmware", m.firmware],
    ["Port", link.port],
    ["Status round trip", link.status_ms === null ? null : `${link.status_ms} ms`],
    ["Tilt switch", m.connected ? (m.switch ? "Pressed" : "Released") : null],
    ["Half-steps per turn", m.calibration.half_steps_per_turn.toFixed(2) + (m.calibration.yaw_calibrated ? "" : " (nominal)")],
    ["Tilt switch angle", `${m.calibration.tilt_switch_deg.toFixed(2)}°` + (m.calibration.tilt_calibrated ? "" : " (from the CAD)")],
  ];
  const key = JSON.stringify(rows);
  const container = $("module-diagnostics");
  if (container.dataset.key !== key) {
    container.dataset.key = key;
    container.replaceChildren(
      el(
        "dl",
        {},
        ...rows
          .filter(([, value]) => value !== undefined && value !== null && value !== "")
          .flatMap(([label, value, tone]) => [el("dt", {}, label), el("dd", { class: tone || "" }, String(value))]),
      ),
    );
  }
  const hall = m.connected && m.hall !== null ? m.hall : null;
  setText("hall-value", hall === null ? "–" : String(hall));
  // The bar shows how far the reading is from the no-field level, either way.
  const deviation = hall === null ? 0 : Math.min(1, Math.abs(hall - 512) / 200);
  $("hall-fill").style.width = `${Math.round(deviation * 100)}%`;
}

// -- gauges -----------------------------------------------------------------------------------

/** Side view, camera on the right: the line is the insect's "up", which tilts towards the
 * camera as the angle grows. The shaded wedge is the range the lens allows. */
function drawTilt(svg, deg, minDeg, maxDeg) {
  const c = 60;
  const r = 44;
  const point = (angle, radius = r) => {
    const a = (angle * Math.PI) / 180;
    return [c + radius * Math.sin(a), c - radius * Math.cos(a)];
  };
  const [x0, y0] = point(minDeg);
  const [x1, y1] = point(maxDeg);
  const large = maxDeg - minDeg > 180 ? 1 : 0;
  const parts = [
    svgEl("circle", { cx: c, cy: c, r, class: "gauge-ring" }),
    svgEl("path", { d: `M${c},${c} L${x0},${y0} A${r},${r} 0 ${large} 1 ${x1},${y1} Z`, class: "gauge-range" }),
    svgEl("path", { d: lensPath(), class: "gauge-lens" }),
  ];
  if (deg !== null) {
    const [x, y] = point(deg, r - 4);
    parts.push(
      svgEl("line", { x1: c, y1: c, x2: x, y2: y, class: "gauge-needle" }),
      svgEl("circle", { cx: x, cy: y, r: 4.5, class: "gauge-tip" }),
    );
  }
  parts.push(svgEl("circle", { cx: c, cy: c, r: 3.5, class: "gauge-hub" }));
  svg.replaceChildren(...parts);
}

/** Top view, camera on the right: the head's two centring screws and its spring. */
function drawYaw(svg, deg) {
  const c = 60;
  const r = 40;
  const parts = [svgEl("circle", { cx: c, cy: c, r, class: "gauge-ring" }), svgEl("path", { d: lensPath(), class: "gauge-lens" })];
  if (deg !== null) {
    const mark = (offset, label, cls) => {
      const a = ((deg + offset) * Math.PI) / 180;
      const [x, y] = [c + r * Math.cos(a), c - r * Math.sin(a)];
      const [tx, ty] = [c + (r - 15) * Math.cos(a), c - (r - 15) * Math.sin(a)];
      parts.push(
        svgEl("circle", { cx: x, cy: y, r: 6, class: cls }),
        svgEl("text", { x: tx, y: ty, class: "gauge-label" }, label),
      );
    };
    mark(0, "X", "gauge-screw");
    mark(90, "Y", "gauge-screw");
    mark(225, "S", "gauge-spring");
  }
  parts.push(svgEl("circle", { cx: c, cy: c, r: 3.5, class: "gauge-hub" }));
  svg.replaceChildren(...parts);
}

/** A small objective at the right edge, pointing at the centre. */
function lensPath() {
  return "M112,52 L104,52 L100,56 L100,64 L104,68 L112,68 Z";
}

function svgEl(tag, attributes, text) {
  const node = document.createElementNS(SVG, tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, String(value));
  if (text !== undefined) node.textContent = text;
  return node;
}
