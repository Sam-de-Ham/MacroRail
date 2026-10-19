// The System tab: backlash calibration and diagnostics. (Its settings fields and the activity
// log are handled by main.js; the alert options by alerts.js.)

import { post } from "./api.js";
import { $, el, setText } from "./dom.js";
import * as fmt from "./format.js";

export const actions = {
  "measure-backlash": () => post("scan/backlash"),
  "apply-backlash": () => post("scan/backlash/apply"),
};

export function render(ctx) {
  renderCalibration(ctx);
  if (ctx.tab === "system") renderDiagnostics(ctx);
}

function renderCalibration({ s, spm, mine, canPosition }) {
  const liveView = s.camera.connected && s.camera.live_view;
  $("measure-backlash").disabled = !canPosition || !liveView;
  const result = s.scan.backlash;
  $("backlash-result").hidden = !result;
  if (!result) return;
  const um = (steps) => Math.round((steps * 1000) / spm);
  setText("backlash-text", `Backlash is about ${um(result.backlash)} µm (repeatability ±${um(result.spread / 2)} µm).`);
  const takeup = Math.min(2, Math.ceil((result.suggested_takeup / spm) * 100) / 100);
  const current = s.settings.motion.backlash_mm;
  const button = $("apply-backlash");
  button.textContent =
    Math.abs(current - takeup) < 0.005 ? `Take-up is ${takeup.toFixed(2)} mm` : `Set take-up to ${takeup.toFixed(2)} mm (now ${current.toFixed(2)} mm)`;
  button.disabled = !mine || Math.abs(current - takeup) < 0.005 || s.activity !== "idle";
}

const yes = (flag) => (flag ? "Yes" : "No");
const since = (timestamp) => (timestamp ? fmt.duration(Date.now() / 1000 - timestamp) : "–");

function renderDiagnostics({ s }) {
  const d = s.diagnostics;
  const sys = d.system;
  const driver = d.rail.driver;
  const sections = [
    [
      "Raspberry Pi",
      [
        ["Host", sys.host],
        ["CPU temperature", sys.cpu_temp_c !== undefined && `${sys.cpu_temp_c} °C`],
        ["Power", sys.power && (sys.power.length ? sys.power.join(", ") : "OK"), sys.power?.length ? "warn" : ""],
        ["Load (1 min)", sys.load],
        ["Memory used", sys.memory_used_pct !== undefined && `${sys.memory_used_pct} %`],
        ["Disk free", `${sys.disk_free_gb} GB`],
        ["Up", sys.uptime_s !== undefined && fmt.duration(sys.uptime_s)],
        ["System", sys.os],
      ],
    ],
    [
      "Rail controller",
      [
        ["Connected", d.rail.connected ? `Yes, for ${since(d.rail.connected_since)}` : "No", d.rail.connected ? "" : "bad"],
        ["Firmware", d.rail.firmware && `${d.rail.firmware} (protocol ${d.rail.protocol})`],
        ["Status round trip", d.rail.status_ms !== null && `${d.rail.status_ms} ms`],
        ["Connections since start", d.rail.connections],
        ["Port", d.rail.port],
      ],
    ],
    [
      "Motor driver",
      driver
        ? [
            ["Mode", driver.stealthchop ? "StealthChop (quiet)" : "SpreadCycle"],
            ["Microsteps", driver.microsteps],
            ["Current scale", `${driver.current_scale}/31 now · run ${driver.run_current_scale} · hold ${driver.hold_current_scale}`],
            ["Standstill", yes(driver.standstill)],
            ["Temperature", driver.temperature_above_c ? `Above ${driver.temperature_above_c} °C` : "Normal", driver.temperature_above_c ? "warn" : ""],
            ["Faults", faults(driver), faults(driver) === "None" ? "" : "bad"],
            ["Controller up", fmt.duration(driver.controller_uptime_s)],
          ]
        : [["Status", s.rail.connected && !s.rail.driver_ok ? "Not responding (no 12 V?)" : "Read while the rail is idle"]],
    ],
    [
      "Camera",
      [
        ["Connected", d.camera.connected ? "Yes" : d.camera.problem || "No", d.camera.connected ? "" : "bad"],
        ["Model", d.camera.model],
        ["Battery", d.camera.battery],
      ],
    ],
    ["MacroRail", [["Version", d.app.version], ["Running for", since(d.app.started_at)]]],
  ];
  const key = JSON.stringify(sections);
  const container = $("diagnostics");
  if (container.dataset.key === key) return;
  container.dataset.key = key;
  container.replaceChildren(
    ...sections.map(([heading, rows]) =>
      el(
        "section",
        {},
        el("h3", {}, heading),
        el(
          "dl",
          {},
          ...rows
            .filter(([, value]) => value !== undefined && value !== null && value !== false && value !== "")
            .flatMap(([label, value, tone]) => [el("dt", {}, label), el("dd", { class: tone || "" }, String(value))]),
        ),
      ),
    ),
  );
}

function faults(driver) {
  const found = [
    driver.overtemperature && "overheated",
    driver.overtemperature_warning && "hot",
    driver.short_circuit && "short circuit",
    driver.open_load && !driver.standstill && "motor disconnected?",
  ].filter(Boolean);
  return found.length ? found.join(", ") : "None";
}
