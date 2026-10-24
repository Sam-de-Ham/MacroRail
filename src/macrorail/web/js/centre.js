// The Centre tab (3D workspace): the centring wizard. Each round looks at the specimen from four
// yaws and fits how far it sits off the yaw axis; the plot shows the rounds in the head's own
// frame (screw X to the right, screw Y up, as the yaw gauge at yaw 0), and each screw to turn
// gets a dial. Then the height: how far the specimen sits above or below the tilt axis.

import { post } from "./api.js";
import { $, el, setText } from "./dom.js";
import { svgEl } from "./rig.js";

const FRACTIONS = { 0.125: "⅛", 0.25: "¼", 0.375: "⅜", 0.5: "½", 0.625: "⅝", 0.75: "¾", 0.875: "⅞" };
const TASKS = { centring: "Looking from four sides…", height: "Focusing at two tilts…" };

let drawn = null; // what the plot and dials last showed

export const actions = {
  "measure-centring": () => post("module/centring"),
  "measure-height": () => post("module/height"),
  "new-specimen": () => post("module/specimen"),
  "face-screw": (button) => post("module/pose", { tilt: 0, yaw: Number(button.dataset.yaw) }),
};

export function render({ s, mine, busy }) {
  const m = s.module;
  const c = m.centring;
  const last = c.rounds.at(-1);
  const ready = mine && !busy && m.connected && m.tilt_homed && m.yaw_homed && s.rail.homed;
  const liveView = s.camera.connected && s.camera.live_view;

  const badge = !last ? "Not measured" : last.centred ? "Centred" : `${formatMm(last.distance_mm)} off`;
  setText("centring-badge", badge);
  $("centring-badge").classList.toggle("ok", Boolean(last?.centred));
  $("centring-badge").classList.toggle("warn", Boolean(last && !last.centred));
  $("measure-centring").disabled = !(ready && liveView);
  setText("measure-centring", c.rounds.length ? "Measure again" : "Measure");
  $("new-specimen").disabled = !mine || busy || (!c.rounds.length && c.height_mm === null);
  setText("centring-progress", busy && TASKS[c.task] ? TASKS[c.task] : "");
  setText("centring-caption", caption(c, last));

  const key = JSON.stringify([c.rounds, c.turns, ready]);
  if (key !== drawn) {
    drawn = key;
    drawPlot($("centring-plot"), c.rounds);
    $("screw-turns").replaceChildren(...c.turns.map((turn) => screwRow(turn, ready)));
  }

  // Height: needs the rail's direction, which the first centring round learns.
  const known = c.rail_sign !== 0;
  $("measure-height").disabled = !(ready && liveView && known);
  setText("height-text", heightText(c, known));
  const height = c.height_mm;
  setText("height-badge", height === null ? "–" : Math.abs(height) <= c.height_ok_mm ? "Good" : `${formatMm(Math.abs(height))} ${height > 0 ? "high" : "low"}`);
  $("height-badge").classList.toggle("ok", height !== null && Math.abs(height) <= c.height_ok_mm);
  $("height-badge").classList.toggle("warn", height !== null && Math.abs(height) > c.height_ok_mm);
}

function caption(c, last) {
  if (!last) return "Each round's offset from the yaw axis shows here, in the head's frame.";
  const rounds = c.rounds.length === 1 ? "1 round" : `${c.rounds.length} rounds`;
  if (last.centred) return `${rounds}: ${formatMm(last.distance_mm)} from the yaw axis. Centred.`;
  return `${rounds}: ${formatMm(last.distance_mm)} from the yaw axis. Turn the screws below, then measure again.`;
}

function heightText(c, known) {
  if (!known) return "Centre with yaw first: the first round also learns which way the rail moves.";
  const height = c.height_mm;
  if (height === null) return "";
  if (Math.abs(height) <= c.height_ok_mm) return `${formatMm(Math.abs(height))} from the tilt axis: good.`;
  return height > 0
    ? `${formatMm(height)} above the tilt axis: push the pin ${formatMm(height)} further into its clamp.`
    : `${formatMm(-height)} below the tilt axis: pull the pin ${formatMm(-height)} out of its clamp.`;
}

function formatMm(mm) {
  return mm < 1 ? `${Math.round(mm * 1000)} µm` : `${mm.toFixed(2)} mm`;
}

function formatTurns(turns) {
  const whole = Math.floor(turns);
  const fraction = FRACTIONS[Math.round((turns - whole) * 8) / 8] || "";
  const text = `${whole || ""}${fraction}` || "0";
  return `${text} ${turns > 1 ? "turns" : "turn"}`;
}

/** One screw to turn: a dial showing how far and which way, and a button that turns the
 * head so the screw points at you. */
function screwRow(turn, ready) {
  const amount = Math.abs(turn.turns);
  const inward = turn.turns > 0;
  const name = turn.screw.toUpperCase();
  return el(
    "div",
    { class: "screw-turn" },
    dial(amount, inward),
    el(
      "div",
      { class: "screw-text" },
      el("strong", {}, `Screw ${name}: ${formatTurns(amount)} ${inward ? "in" : "out"}`),
      el("span", { class: "muted small-text" }, inward ? "Clockwise, pushing the plate away from the screw." : "Anticlockwise, letting the spring push the plate back."),
    ),
    el("button", { class: "button small", "data-action": "face-screw", "data-yaw": String(turn.facing_yaw), disabled: !ready }, `Screw ${name} to you`),
  );
}

/** A hex-key dial: the arc is the part of a turn beyond whole turns (whole turns are
 * written in the middle), clockwise for in, anticlockwise for out. */
function dial(turns, clockwise) {
  const svg = svgEl("svg", { viewBox: "0 0 64 64", class: "screw-dial", "aria-hidden": "true" });
  const c = 32;
  const r = 24;
  const whole = Math.floor(turns);
  const fraction = turns - whole;
  const parts = [svgEl("circle", { cx: c, cy: c, r, class: "dial-ring" })];
  const sweep = (fraction || 1) * 2 * Math.PI * (clockwise ? 1 : -1);
  const end = [c + r * Math.sin(sweep), c - r * Math.cos(sweep)];
  const large = Math.abs(sweep) > Math.PI ? 1 : 0;
  if (fraction) {
    parts.push(svgEl("path", { d: `M${c},${c - r} A${r},${r} 0 ${large} ${clockwise ? 1 : 0} ${end[0]},${end[1]}`, class: "dial-arc" }));
  } else {
    parts.push(svgEl("circle", { cx: c, cy: c, r, class: "dial-arc" }));
  }
  parts.push(svgEl("circle", { cx: end[0], cy: end[1], r: 4, class: "dial-tip" }));
  parts.push(svgEl("text", { x: c, y: c, class: "dial-label" }, whole ? `${whole}×` : clockwise ? "in" : "out"));
  svg.replaceChildren(...parts);
  return svg;
}

/** The rounds in the head's frame: the yaw axis at the centre, the 0.1 mm target circle, each
 * round's offset (older ones faded), and where the screws sit. */
function drawPlot(svg, rounds) {
  const c = 100;
  const radius = 80;
  const largest = Math.max(0.5, ...rounds.map((r) => r.distance_mm * 1.2));
  const scale = radius / largest; // px per mm
  const point = (r) => [c + r.offset_x_mm * scale, c - r.offset_y_mm * scale];
  const parts = [
    svgEl("circle", { cx: c, cy: c, r: radius, class: "plot-field" }),
    svgEl("line", { x1: c - radius, y1: c, x2: c + radius, y2: c, class: "plot-axis" }),
    svgEl("line", { x1: c, y1: c - radius, x2: c, y2: c + radius, class: "plot-axis" }),
    svgEl("circle", { cx: c, cy: c, r: Math.max(2, 0.1 * scale), class: "plot-target" }),
    svgEl("text", { x: c + radius + 8, y: c, class: "plot-label" }, "X"),
    svgEl("text", { x: c, y: c - radius - 9, class: "plot-label" }, "Y"),
    svgEl("text", { x: 4, y: 196, class: "plot-scale" }, `circle: ${formatMm(largest)}`),
  ];
  if (rounds.length > 1) {
    parts.push(svgEl("polyline", { points: rounds.map((r) => point(r).join(",")).join(" "), class: "plot-path" }));
  }
  rounds.forEach((r, i) => {
    const [x, y] = point(r);
    const latest = i === rounds.length - 1;
    parts.push(svgEl("circle", { cx: x, cy: y, r: latest ? 6 : 4, class: latest ? "plot-latest" : "plot-old" }));
  });
  svg.replaceChildren(...parts);
}
