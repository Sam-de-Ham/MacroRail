// The Review tab: finished stacks, each with its quick preview stack and a frame scrubber.
// The list is fetched when the server's review revision changes (pushed in the state).

import { getJson, post, remove } from "./api.js";
import { $, el, setChecked, setText } from "./dom.js";
import { showToast } from "./toast.js";

let stacks = [];
let loadedRevision = -1;
let loading = false;
let selected = null; // stack id shown in the viewer
let mode = "preview"; // or "frames"
let frame = 0; // index into the selected stack's frames

const OUTCOME = { done: "Complete", stopped: "Stopped", failed: "Failed" };

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
  "viewer-mode": (button, app) => {
    mode = button.dataset.mode;
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

let lastCtx = null;

export function render(ctx) {
  lastCtx = ctx;
  const revision = ctx.s.review.revision;
  if (ctx.tab === "review" && revision !== loadedRevision && !loading) load(revision, ctx);
  renderList(ctx);
  renderViewer(ctx);
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

function thumb(stack, revision) {
  if (stack.preview) return `/api/stacks/${stack.id}/preview?v=${revision}`;
  if (stack.frames.length) return `/api/stacks/${stack.id}/frames/${stack.frames[0]}`;
  return null;
}

function renderList({ s }) {
  const list = $("stack-list");
  const key = JSON.stringify([stacks, s.review.revision]);
  if (list.dataset.key === key) return;
  list.dataset.key = key;
  list.replaceChildren(
    ...stacks.map((stack) => {
      const src = thumb(stack, s.review.revision);
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
  const stack = stacks.find((x) => x.id === selected);
  $("review-viewer").hidden = !stack;
  $("review-list-card").hidden = Boolean(stack);
  if (!stack) return;

  setText("viewer-title", title(stack));
  const previews = stack.frames.length ? `${stack.frames.length} previews` : "no previews downloaded";
  setText("viewer-meta", `${when(stack)} · ${stack.shots} shots · ${previews}`);
  setChecked($("viewer-mode"), "data-mode", mode);

  const building = s.review.building === stack.id;
  const image = $("viewer-image");
  let src = null;
  let empty = "";
  if (mode === "preview") {
    if (stack.preview) src = `/api/stacks/${stack.id}/preview?v=${s.review.revision}`;
    else empty = building ? "Making the preview stack…" : "No preview stack yet.";
  } else if (stack.frames.length) {
    frame = Math.min(frame, stack.frames.length - 1);
    src = `/api/stacks/${stack.id}/frames/${stack.frames[frame]}`;
  } else {
    empty = "No frames were downloaded for this stack.";
  }
  if (src && image.getAttribute("src") !== src) image.setAttribute("src", src);
  image.hidden = !src;
  setText("viewer-empty", empty);
  $("viewer-empty").hidden = !empty;

  const slider = $("frame-slider");
  $("frame-scrubber").hidden = mode !== "frames" || stack.frames.length < 2;
  slider.max = String(Math.max(0, stack.frames.length - 1));
  if (document.activeElement !== slider) slider.value = String(frame);
  setText("frame-label", stack.frames.length ? `Shot ${stack.frames[frame]} of ${stack.shots}` : "");

  const download = $("download-stack");
  download.hidden = !stack.frames.length;
  download.href = `/api/stacks/${stack.id}/zip`;
  download.title = `The ${stack.frames.length} previews, the preview stack and the record, as a zip`;

  const button = $("build-preview");
  button.disabled = !mine || stack.frames.length < 2 || s.review.building !== null;
  button.textContent = building ? "Making preview stack…" : stack.preview ? "Remake preview stack" : "Make preview stack";
  $("delete-stack").disabled = !mine || (s.stack?.id === stack.id && !["done", "stopped", "failed"].includes(s.stack.phase));
}
