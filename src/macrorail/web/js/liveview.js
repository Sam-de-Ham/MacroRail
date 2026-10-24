// Live view: the MJPEG stream, tap-to-zoom and the per-browser pause toggle. While a stack
// runs (live view is off then), it shows each shot's preview as it arrives; pausing holds the
// one on screen.

import { $ } from "./dom.js";
import * as fmt from "./format.js";
import { readPref, writePref } from "./prefs.js";
import { isActive } from "./shoot.js";

const PLAY = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
const PAUSE = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>';

const figure = $("liveview");
const image = $("liveview-image");
let off = readPref("liveview-off", false); // this browser paused it
let hold = false; // keep the stack shot on screen instead of following new ones
let showingShots = false;

figure.addEventListener("click", (event) => {
  if (event.target.closest("button") || !image.getAttribute("src")) return;
  if (figure.classList.toggle("zoomed")) {
    const box = figure.getBoundingClientRect();
    const x = ((event.clientX - box.left) / box.width) * 100;
    const y = ((event.clientY - box.top) / box.height) * 100;
    image.style.transformOrigin = `${x}% ${y}%`;
    image.style.transform = "scale(3)";
  } else {
    image.style.transform = "";
  }
  $("liveview-hint").textContent = figure.classList.contains("zoomed") ? "Tap to fit" : "Tap to zoom";
});

export const actions = {
  "toggle-liveview": (_el, app) => {
    if (showingShots) {
      hold = !hold;
    } else {
      off = !off;
      writePref("liveview-off", off);
    }
    app.render();
  },
};

export function render({ s, connected, workspace }) {
  const stack = s.stack;
  const shot = connected && stack && isActive(stack) && stack.latest_preview;
  showingShots = Boolean(shot);
  if (!shot) hold = false;
  if (shot) {
    renderShot(stack, shot);
  } else {
    renderStream(s, connected);
  }
  const rail = s.rail.connected ? `${fmt.mm(s.rail.position, s.rail.steps_per_mm)} mm` : "–";
  const m = s.module;
  const pose =
    workspace === "3d" && m.connected
      ? ` · T ${m.tilt_homed ? `${m.tilt_deg.toFixed(1)}°` : "–"} · Y ${m.yaw_homed ? `${m.yaw_deg.toFixed(1)}°` : "–"}`
      : "";
  $("liveview-position").textContent = rail + pose;
  // Where the yaw axis appears (learnt by centring): the insect should sit on this line.
  const axis = m.centring.axis_image_x;
  const showAxis = workspace === "3d" && axis !== null && !shot;
  $("liveview-axis").hidden = !showAxis;
  if (showAxis) $("liveview-axis").style.left = `${(axis * 100).toFixed(2)}%`;
}

/** The newest shot of the running stack, or the one held while paused. */
function renderShot(stack, shot) {
  const current = image.getAttribute("src") || "";
  const showing = current.startsWith(`/api/stacks/${stack.id}/frames/`);
  const newest = `/api/stacks/${stack.id}/frames/${shot}`;
  if ((!hold || !showing) && current !== newest) image.setAttribute("src", newest);
  const shown = Number(image.getAttribute("src").split("/").pop());
  figure.classList.remove("paused");
  $("liveview-message").hidden = true;
  $("liveview-shot").hidden = false;
  $("liveview-shot").textContent = `Shot ${shown} of ${stack.total}${hold ? " · held" : ""}`;
  $("liveview-hint").hidden = false;
  setToggle(true, hold, hold ? "Show new shots" : "Hold this shot");
}

function renderStream(s, connected) {
  const available = connected && s.live_view.available;
  // Closing the stream when paused stops the camera from sending frames at all.
  const wanted = available && !off ? "/api/liveview" : "";
  if (image.getAttribute("src") !== wanted) {
    if (wanted) image.setAttribute("src", wanted);
    else image.removeAttribute("src");
  }
  $("liveview-shot").hidden = true;
  figure.classList.toggle("paused", s.live_view.paused);
  const message = !connected
    ? "Not connected"
    : !s.camera.connected
      ? s.camera.problem || "No camera"
      : !s.live_view.available
        ? "This camera has no live view"
        : s.live_view.paused
          ? "Live view is paused while stacking"
          : off
            ? "Live view paused"
            : "";
  $("liveview-message").textContent = message;
  $("liveview-message").hidden = !message;
  $("liveview-hint").hidden = !available || s.live_view.paused || off;
  setToggle(available, off, off ? "Resume live view" : "Pause live view");
  if (!wanted && figure.classList.contains("zoomed")) {
    figure.classList.remove("zoomed");
    image.style.transform = "";
  }
}

function setToggle(visible, paused, label) {
  const toggle = $("liveview-toggle");
  toggle.hidden = !visible;
  toggle.innerHTML = paused ? PLAY : PAUSE;
  toggle.title = label;
  toggle.setAttribute("aria-label", label);
}
