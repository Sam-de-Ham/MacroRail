// Live view: the MJPEG stream, tap-to-zoom and the per-browser pause toggle.

import { $ } from "./dom.js";
import * as fmt from "./format.js";
import { readPref, writePref } from "./prefs.js";

const PLAY = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M8 5v14l11-7z"/></svg>';
const PAUSE = '<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path fill="currentColor" d="M7 5h4v14H7zm6 0h4v14h-4z"/></svg>';

const figure = $("liveview");
const image = $("liveview-image");
let off = readPref("liveview-off", false); // this browser paused it

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
    off = !off;
    writePref("liveview-off", off);
    app.render();
  },
};

export function render({ s, connected }) {
  const available = connected && s.live_view.available;
  // Closing the stream when paused stops the camera from sending frames at all.
  const wanted = available && !off ? "/api/liveview" : "";
  if (image.getAttribute("src") !== wanted) {
    if (wanted) image.setAttribute("src", wanted);
    else image.removeAttribute("src");
  }
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
  const toggle = $("liveview-toggle");
  toggle.hidden = !available;
  toggle.innerHTML = off ? PLAY : PAUSE;
  const label = off ? "Resume live view" : "Pause live view";
  toggle.title = label;
  toggle.setAttribute("aria-label", label);
  if (off && figure.classList.contains("zoomed")) {
    figure.classList.remove("zoomed");
    image.style.transform = "";
  }
  $("liveview-position").textContent = s.rail.connected ? `${fmt.mm(s.rail.position, s.rail.steps_per_mm)} mm` : "–";
}
