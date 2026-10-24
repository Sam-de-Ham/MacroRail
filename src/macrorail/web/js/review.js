// The Review tab: finished stacks, each with its quick preview stack, its depth map (flat in
// false colour, or as a 3D relief) and a frame scrubber. In the 3D workspace it lists scans
// instead: a scan shows its poses as thumbnails, and each pose opens in the same viewer.
// Lists are fetched when the server's review revision changes (pushed in the state).

import { getJson, post, remove } from "./api.js";
import { $, el, setChecked, setText } from "./dom.js";
import { readPref, writePref } from "./prefs.js";
import { Relief } from "./relief.js";
import { showToast } from "./toast.js";

let stacks = [];
let loadedRevision = -1;
let loading = false;
let scans = [];
let scansKey = null; // what the scan list was loaded for
let scan = null; // the open scan: { id, record, stacks }
let scanKey = null;
let selected = null; // stack id shown in the viewer
let mode = "preview"; // or "depth", "relief", "frames"
let frame = 0; // index into the selected stack's frames
let relief = null; // created when first shown
let reliefHeight = readPref("reliefHeight", 0.3);
let reliefFlipped = readPref("reliefFlipped", false);

const OUTCOME = { done: "Complete", stopped: "Stopped", failed: "Failed" };
const SCAN_OUTCOME = { ...OUTCOME, running: "Running", pausing: "Running", paused: "Paused", stopping: "Stopping" };
const RUNNING = new Set(["running", "pausing", "paused", "stopping"]);

export const actions = {
  "open-stack": (button, app) => {
    selected = button.dataset.id;
    const stack = stacks.find((s) => s.id === selected);
    mode = stack?.preview ? "preview" : "frames";
    frame = 0;
    app.render();
    $("review-viewer").scrollIntoView({ behavior: "smooth", block: "start" });
  },
  "close-viewer": (_el, app) => {
    selected = null;
    app.render();
  },
  "open-scan": (button, app) => {
    scan = { id: button.dataset.id, record: null, stacks: [] };
    scanKey = null;
    selected = null;
    $("pose-grid").replaceChildren();
    delete $("pose-grid").dataset.key;
    app.render();
  },
  "close-scan": (_el, app) => {
    scan = null;
    app.render();
  },
  "open-pose": (button, app) => {
    selected = button.dataset.id;
    const stack = scan?.stacks.find((x) => x.id === selected);
    mode = stack?.preview ? "preview" : "frames";
    frame = 0;
    app.render();
  },
  "delete-scan": async (_el, app) => {
    if (!scan || !confirm("Delete this scan and all its poses' previews from the Pi? The camera's own files are kept.")) return;
    await remove(`scans/${scan.id}`);
    scan = null;
    scansKey = null;
    app.render();
  },
  "viewer-mode": (button, app) => {
    mode = button.dataset.mode;
    app.render();
  },
  "relief-flip": (_el, app) => {
    reliefFlipped = !reliefFlipped;
    writePref("reliefFlipped", reliefFlipped);
    relief?.set(reliefHeight, reliefFlipped);
    app.render();
  },
  "build-preview": () => post(`stacks/${selected}/preview`),
  "delete-stack": async (_el, app) => {
    const stack = stacks.find((s) => s.id === selected);
    if (!stack || !confirm(`Delete "${title(stack)}" and its previews from the Pi? The camera's own files are kept.`)) return;
    await remove(`stacks/${selected}`);
    selected = null;
    app.render();
  },
};

$("frame-slider").addEventListener("input", (event) => {
  frame = Number(event.target.value);
  renderViewer(lastCtx);
});

$("relief-height").addEventListener("input", (event) => {
  reliefHeight = Number(event.target.value);
  writePref("reliefHeight", reliefHeight);
  relief?.set(reliefHeight, reliefFlipped);
});

let lastCtx = null;

export function render(ctx) {
  lastCtx = ctx;
  const revision = ctx.s.review.revision;
  if (ctx.workspace === "3d") {
    // Scans change as their poses finish: each pose's stack bumps the revision.
    const run = ctx.s.scan3d.run;
    const key = `${revision}:${run ? `${run.id}:${run.done}:${run.phase}` : ""}`;
    if (ctx.tab === "review" && !loading) {
      if (key !== scansKey) loadScans(key, ctx);
      else if (scan && key !== scanKey) loadScan(key, ctx);
    }
    // A stack chosen elsewhere (2D, or another scan) isn't shown here.
    if (selected && scan?.record && !scan.stacks.some((x) => x.id === selected)) selected = null;
    if (selected && !scan) selected = null;
    renderScanList(ctx);
    renderScanView(ctx);
  } else {
    if (selected && loadedRevision >= 0 && !stacks.some((x) => x.id === selected)) selected = null;
    if (ctx.tab === "review" && revision !== loadedRevision && !loading) load(revision, ctx);
    renderList();
  }
  renderViewer(ctx);
}

async function loadScans(key, ctx) {
  loading = true;
  try {
    scans = await getJson("scans");
    scansKey = key;
    if (scan && !scans.some((x) => x.id === scan.id)) scan = null;
  } catch (error) {
    showToast(`Could not load scans: ${error.message}`, "error");
  } finally {
    loading = false;
    ctx.render();
  }
}

async function loadScan(key, ctx) {
  loading = true;
  const id = scan.id;
  try {
    const [record, poseStacks] = await Promise.all([getJson(`scans/${id}`), getJson(`scans/${id}/stacks`)]);
    if (scan?.id === id) {
      scan = { id, record, stacks: poseStacks };
      scanKey = key;
    }
  } catch (error) {
    showToast(`Could not load the scan: ${error.message}`, "error");
    if (scan?.id === id) scan = null;
  } finally {
    loading = false;
    ctx.render();
  }
}

function scanTitle(x) {
  return (x.name || x.plan?.name || "Untitled scan") + (x.test || x.plan?.test ? " (test pose)" : "");
}

/** What a scan's record says, except that one left "running" by a restart was interrupted. */
function scanOutcome(x, ctx) {
  const outcome = x.outcome ?? x.phase;
  const live = ctx.s.scan3d.run;
  if (RUNNING.has(outcome) && !(live && live.id === x.id && RUNNING.has(live.phase))) return "Interrupted";
  return SCAN_OUTCOME[outcome] || "Running";
}

function renderScanList(ctx) {
  const list = $("scan-list");
  const key = JSON.stringify([scans, ctx.s.scan3d.run?.phase]);
  if (list.dataset.key !== key) {
    list.dataset.key = key;
    list.replaceChildren(
      ...scans.map((x) =>
        el(
          "li",
          {},
          el(
            "button",
            { class: "stack-item no-image", "data-action": "open-scan", "data-id": x.id },
            el("span", { class: "stack-text" }, el("strong", {}, scanTitle(x)), el("span", { class: "muted small-text" }, when(x)), el("span", { class: "muted small-text" }, `${x.done} of ${x.total} poses`)),
            el("span", { class: `badge ${x.outcome === "done" ? "ok" : ""}` }, scanOutcome(x, ctx)),
          ),
        ),
      ),
    );
  }
  $("scan-list-empty").hidden = scans.length > 0;
  $("scan-list-card").hidden = Boolean(scan) || Boolean(selected);
}

function renderScanView(ctx) {
  const card = $("scan-view");
  card.hidden = !scan || !scan.record || Boolean(selected); // hidden until the record arrives
  if (!scan || !scan.record) return;
  const record = scan.record;
  setText("scan-view-title", scanTitle(record));
  const results = record.results || {};
  const done = Object.values(results).filter((r) => r.outcome === "done").length;
  setText("scan-view-meta", `${when(record)} · ${done} of ${record.poses.length} poses · ${scanOutcome(record, ctx)}`);
  const byId = new Map(scan.stacks.map((x) => [x.id, x]));
  const grid = $("pose-grid");
  const key = JSON.stringify([results, scan.stacks.map((x) => [x.id, x.made_at])]);
  if (grid.dataset.key !== key) {
    grid.dataset.key = key;
    grid.replaceChildren(
      ...record.poses.map((pose) => {
        const result = results[String(pose.index)];
        const stack = result ? byId.get(result.stack) : null;
        const src = stack ? thumb(stack) : null;
        const image = src ? el("img", { src, alt: "", loading: "lazy" }) : el("span", { class: "no-thumb" }, result ? result.outcome : "–");
        return el(
          "button",
          { class: "pose-tile", "data-action": "open-pose", "data-id": stack?.id || "", disabled: !stack, title: `Pose ${pose.index + 1}: tilt ${pose.tilt_deg}°, yaw ${pose.yaw_deg}°` },
          image,
          el("span", {}, `${pose.tilt_deg > 0 ? "+" : ""}${pose.tilt_deg}° · ${pose.yaw_deg}°`),
        );
      }),
    );
  }
  const download = $("download-scan");
  download.href = `/api/scans/${scan.id}/zip`;
  download.hidden = done === 0;
  const running = ctx.s.scan3d.run && ctx.s.scan3d.run.id === scan.id && ["running", "pausing", "paused", "stopping"].includes(ctx.s.scan3d.run.phase);
  $("delete-scan").disabled = !ctx.mine || running;
}

async function load(revision, ctx) {
  loading = true;
  try {
    stacks = await getJson("stacks");
    loadedRevision = revision;
    if (selected && !stacks.some((s) => s.id === selected)) selected = null;
  } catch (error) {
    showToast(`Could not load stacks: ${error.message}`, "error");
  } finally {
    loading = false;
    ctx.render();
  }
}

function title(stack) {
  return stack.name || "Untitled stack";
}


function when(stack) {
  const started = stack.started_at ? new Date(stack.started_at * 1000) : null;
  return started ? started.toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) : stack.id;
}

function thumb(stack) {
  if (stack.preview) return `/api/stacks/${stack.id}/preview?v=${stack.made_at}`;
  if (stack.frames.length) return `/api/stacks/${stack.id}/frames/${stack.frames[0]}`;
  return null;
}

function renderList() {
  const list = $("stack-list");
  const key = JSON.stringify(stacks);
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren(
    ...stacks.map((stack) => {
      const src = thumb(stack);
      const image = src ? el("img", { src, alt: "", loading: "lazy" }) : el("span", { class: "no-thumb" }, "No previews");
      const shots = stack.planned ? `${stack.shots} of ${stack.planned} shots` : `${stack.shots} shots`;
      const outcome = OUTCOME[stack.outcome] || "Running";
      return el(
        "li",
        {},
        el(
          "button",
          { class: "stack-item", "data-action": "open-stack", "data-id": stack.id },
          image,
          el("span", { class: "stack-text" }, el("strong", {}, title(stack)), el("span", { class: "muted small-text" }, when(stack)), el("span", { class: "muted small-text" }, shots)),
          el("span", { class: `badge ${stack.outcome === "done" ? "ok" : ""}` }, outcome),
        ),
      );
    }),
  );
  $("stack-list-empty").hidden = stacks.length > 0;
}

function renderViewer(ctx) {
  if (!ctx) return;
  const { s, mine } = ctx;
  const pose = ctx.workspace === "3d";
  const stack = (pose ? scan?.stacks || [] : stacks).find((x) => x.id === selected);
  $("review-viewer").hidden = !stack;
  $("review-list-card").hidden = Boolean(stack);
  if (!stack) return;

  setText("viewer-title", pose ? `${scanTitle(scan.record)}: ${title(stack)}` : title(stack));
  const previews = stack.frames.length ? `${stack.frames.length} previews` : "no previews downloaded";
  setText("viewer-meta", `${when(stack)} · ${stack.shots} shots · ${previews}`);
  setChecked($("viewer-mode"), "data-mode", mode);

  const building = s.review.building === stack.id;
  const version = `v=${stack.made_at}`;
  const image = $("viewer-image");
  let src = null;
  let empty = "";
  const stacked = mode === "preview" ? stack.preview : stack.depth;
  if (mode !== "frames" && !stacked) {
    const what = mode === "preview" ? "preview stack" : "depth map";
    const remake = pose ? "" : ": remake the preview stack";
    empty = building ? `Making the ${what}…` : stack.preview ? `No depth map yet${remake}.` : `No ${what} yet.`;
  } else if (mode === "preview") {
    src = `/api/stacks/${stack.id}/preview?${version}`;
  } else if (mode === "depth") {
    src = `/api/stacks/${stack.id}/depth?colour=true&${version}`;
  } else if (mode === "relief") {
    showRelief(stack, version);
    if (!relief.supported) empty = "This browser can't show 3D (no WebGL 2).";
  } else if (stack.frames.length) {
    frame = Math.min(frame, stack.frames.length - 1);
    src = `/api/stacks/${stack.id}/frames/${stack.frames[frame]}`;
  } else {
    empty = "No frames were downloaded for this stack.";
  }
  if (src && image.getAttribute("src") !== src) image.setAttribute("src", src);
  image.hidden = !src;
  $("relief").hidden = mode !== "relief" || !stacked || Boolean(empty);
  setText("viewer-empty", empty);
  $("viewer-empty").hidden = !empty;

  $("depth-legend").hidden = mode !== "depth" || !stack.depth;
  setText("depth-span", stack.depth_mm ? `${Math.round(stack.depth_mm * 1000)} µm deep` : "");
  $("depth-download").href = `/api/stacks/${stack.id}/depth?${version}`;
  $("relief-controls").hidden = $("relief").hidden;
  $("relief-flip").setAttribute("aria-pressed", String(reliefFlipped));

  const slider = $("frame-slider");
  $("frame-scrubber").hidden = mode !== "frames" || stack.frames.length < 2;
  slider.max = String(Math.max(0, stack.frames.length - 1));
  if (document.activeElement !== slider) slider.value = String(frame);
  setText("frame-label", stack.frames.length ? `Shot ${stack.frames[frame]} of ${stack.shots}` : "");

  const download = $("download-stack");
  download.hidden = !stack.frames.length;
  download.href = `/api/stacks/${stack.id}/zip`;
  download.title = `The ${stack.frames.length} previews, the preview stack, its depth maps and the record, as a zip`;

  const button = $("build-preview");
  button.disabled = !mine || stack.frames.length < 2 || s.review.building !== null;
  button.textContent = building ? "Making preview stack…" : stack.preview ? "Remake preview stack" : "Make preview stack";
  $("delete-stack").disabled = !mine || (s.stack?.id === stack.id && !["done", "stopped", "failed"].includes(s.stack.phase));
  $("delete-stack").hidden = pose; // a pose goes with its scan
  button.hidden = pose; // its preview used every frame; only some are kept, so don't remake it
}

function showRelief(stack, version) {
  if (!relief) {
    relief = new Relief($("relief"));
    relief.set(reliefHeight, reliefFlipped);
    $("relief-height").value = String(reliefHeight);
  }
  const base = `/api/stacks/${stack.id}`;
  relief.show(`${base}/preview?${version}`, `${base}/depth?${version}`).catch((error) => {
    showToast(`Could not show the 3D view: ${error.message}`, "error");
  });
}
