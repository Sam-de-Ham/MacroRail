// The Scan tab (3D workspace): the scan plan (tilt rings, yaw step), its pose map, what it will
// cost, the pre-flight checks, and the running scan's progress. A scan that was stopped (or
// cut short by a restart) can be continued from here.

import { post } from "./api.js";
import { $, el, setField, setText } from "./dom.js";
import * as fmt from "./format.js";
import { svgEl } from "./rig.js";

const STAGE = {
  turning: "turning to the pose",
  "finding the range": "finding the front and back",
  shooting: "shooting",
  saving: "saving",
};
const PHASE = { pausing: "Pausing…", paused: "Paused", stopping: "Stopping…", done: "Complete", stopped: "Stopped", failed: "Failed" };

let drawnMap = null;

export const actions = {
  "scan-start": () => post("scan3d/start", { test: false }),
  "scan-test": () => post("scan3d/start", { test: true }),
  "scan-pause": () => post("scan3d/pause"),
  "scan-resume": () => post("scan3d/resume"),
  "scan-continue": (button) => post(`scans/${button.dataset.id}/continue`),
  "scan-pose": (button) => post("module/pose", { tilt: Number(button.dataset.tilt), yaw: Number(button.dataset.yaw) }),
};

/** The change to send for a plan field (data-plan="key"); saved like the settings fields. */
export function planPatch(input) {
  const key = input.dataset.plan;
  if (key === "tilts") {
    const tilts = input.value.replaceAll("−", "-").split(/[,;\s]+/).filter(Boolean).map(Number);
    if (!tilts.length || tilts.some((t) => !Number.isFinite(t))) throw new Error("Enter tilts like 60, 30, 0, -30.");
    return { tilts };
  }
  if (input.type === "number") {
    if (input.value === "" || !Number.isFinite(Number(input.value))) throw new Error("Enter a number.");
    return { [key]: Number(input.value) };
  }
  return { [key]: input.value.trim() };
}

export function render({ s, mine, busy, force }) {
  const scan = s.scan3d;
  const plan = scan.plan;
  for (const input of document.querySelectorAll("[data-plan]")) {
    const value = plan[input.dataset.plan];
    setField(input, Array.isArray(value) ? value.join(", ") : value, force);
    input.disabled = !mine || s.activity === "scanning_3d";
  }

  const run = scan.run && ["running", "pausing", "paused", "stopping"].includes(scan.run.phase) ? scan.run : null;
  setText("scan-plan-error", scan.error || "");
  $("scan-plan-error").hidden = !scan.error;
  setText("scan-summary", summary(scan));
  renderPreflight(scan.preflight);

  const blocked = scan.preflight.some((c) => c.blocking && !c.ok);
  $("scan-start").disabled = !mine || busy || Boolean(scan.error) || blocked;
  const liveView = s.camera.connected && s.camera.live_view;
  $("scan-test").disabled = !mine || busy || !(s.module.tilt_homed && s.module.yaw_homed && s.rail.homed && liveView);
  $("scan-controls").hidden = !run;
  $("scan-idle-buttons").hidden = Boolean(run);
  if (run) {
    const held = run.phase === "paused" || run.stack?.phase === "paused" || run.stack?.phase === "camera_error";
    $("scan-pause").hidden = held || run.phase === "pausing";
    $("scan-resume").hidden = !held && run.phase !== "pausing";
    $("scan-pause").disabled = !mine || run.phase !== "running";
    $("scan-resume").disabled = !mine;
  }
  setText("scan-progress", progress(scan.run));
  $("scan-progress").hidden = !scan.run;
  const fill = scan.run ? (100 * scan.run.done) / Math.max(1, scan.run.total) : 0;
  $("scan-fill").style.width = `${fill.toFixed(1)}%`;
  $("scan-bar").hidden = !run;

  renderMap(scan, mine && !busy && s.module.tilt_homed && s.module.yaw_homed);
  renderUnfinished(scan.unfinished, mine && !busy);
}

function summary(scan) {
  const poses = scan.poses.length;
  if (!poses) return "";
  const rings = new Set(scan.poses.map(([tilt]) => tilt)).size;
  const head = `${poses} poses (${rings} ${rings === 1 ? "ring" : "rings"} of ${poses / rings})`;
  const e = scan.estimate;
  if (!e) return `${head}. Find the specimen's range once (Test this pose, or the Shoot tab) to estimate the shots and time.`;
  return `${head} · about ${e.shots_per_pose} shots each, ${e.shots.toLocaleString()} in all · about ${fmt.duration(e.seconds)} · Pi ${gb(e.pi_bytes)} · camera card ${gb(e.card_bytes)}`;
}

function gb(bytes) {
  return bytes >= 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1e6))} MB`;
}

function progress(run) {
  if (!run) return "";
  const phase = PHASE[run.phase];
  const done = `${run.done} of ${run.total} poses done`;
  if (run.phase !== "running" && run.phase !== "pausing") return `${phase || run.phase}: ${done}.${run.error ? ` ${run.error}` : ""}`;
  const pose = run.current;
  const where = pose ? `Pose ${pose.index + 1} (tilt ${pose.tilt_deg}°, yaw ${pose.yaw_deg}°): ${STAGE[run.stage] || run.stage}` : "Starting";
  const shots = run.stack && run.stage === "shooting" ? `, shot ${run.stack.taken} of ${run.stack.total}` : "";
  const error = run.stack?.error ? ` ${run.stack.error}` : run.error ? ` ${run.error}` : "";
  return `${where}${shots}. ${done}.${phase ? ` ${phase}` : ""}${error}`;
}

function renderPreflight(checks) {
  const list = $("scan-preflight");
  const key = JSON.stringify(checks);
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren(
    ...checks.map((c) => el("li", { class: c.ok ? "ok" : c.blocking ? "bad" : "warn" }, c.text)),
  );
}

/** Yaw across, tilt rings down (highest first): each pose a dot, filled when done, ringed
 * while it runs. A planned pose can be clicked to go there. */
function renderMap(scan, canGo) {
  const run = scan.run && ["running", "pausing", "paused", "stopping"].includes(scan.run.phase) ? scan.run : null;
  const poses = run ? run.poses.map((p) => [p.tilt_deg, p.yaw_deg]) : scan.poses;
  const results = run ? run.results : {};
  const current = run?.current?.index ?? null;
  const key = JSON.stringify([poses, results, current, canGo]);
  if (key === drawnMap) return;
  drawnMap = key;
  const svg = $("pose-map");
  const tilts = [...new Set(poses.map(([tilt]) => tilt))];
  const width = 360;
  const rowH = 30;
  const left = 46;
  const height = Math.max(1, tilts.length) * rowH + 22;
  svg.setAttribute("viewBox", `0 0 ${width + left + 12} ${height}`);
  const parts = [];
  for (const [i, tilt] of tilts.entries()) {
    const y = 14 + i * rowH + rowH / 2;
    parts.push(svgEl("line", { x1: left, y1: y, x2: left + width, y2: y, class: "map-ring" }));
    parts.push(svgEl("text", { x: left - 8, y, class: "map-tilt" }, `${tilt > 0 ? "+" : ""}${tilt}°`));
  }
  for (const deg of [0, 90, 180, 270, 360]) {
    parts.push(svgEl("text", { x: left + deg, y: 8, class: "map-yaw" }, `${deg}°`));
  }
  poses.forEach(([tilt, yaw], index) => {
    const x = left + yaw;
    const y = 14 + tilts.indexOf(tilt) * rowH + rowH / 2;
    const outcome = results[String(index)];
    const cls = outcome === "done" ? "map-done" : outcome ? "map-failed" : index === current ? "map-current" : "map-planned";
    const dot = svgEl("circle", { cx: x, cy: y, r: index === current ? 8 : 6, class: cls });
    const label = `Pose ${index + 1}: tilt ${tilt}°, yaw ${yaw}°${outcome ? ` (${outcome})` : ""}`;
    dot.append(svgEl("title", {}, label));
    parts.push(dot);
    if (canGo && !run) {
      // A larger invisible target, so a finger can hit it on a phone.
      const target = svgEl("circle", { cx: x, cy: y, r: 13, class: "map-target", "data-action": "scan-pose", "data-tilt": tilt, "data-yaw": yaw });
      target.append(svgEl("title", {}, `Go to ${label.toLowerCase()}`));
      parts.push(target);
    }
  });
  svg.replaceChildren(...parts);
}

function renderUnfinished(scans, canContinue) {
  const list = $("scan-unfinished");
  $("scan-unfinished-card").hidden = !scans.length;
  const key = JSON.stringify([scans, canContinue]);
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren(
    ...scans.map((scan) => {
      const started = scan.started_at ? new Date(scan.started_at * 1000).toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : scan.id;
      return el(
        "li",
        { class: "unfinished-scan" },
        el("span", {}, el("strong", {}, scan.name || "Untitled scan"), el("span", { class: "muted small-text" }, ` ${started} · ${scan.done} of ${scan.total} poses`)),
        el("button", { class: "button small", "data-action": "scan-continue", "data-id": scan.id, disabled: !canContinue }, "Continue"),
      );
    }),
  );
}
