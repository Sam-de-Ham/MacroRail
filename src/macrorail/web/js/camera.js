// The Camera tab: status, the camera's own settings, a test shot.

import { post } from "./api.js";
import { $, el, setText } from "./dom.js";
import { showToast } from "./toast.js";

let shape = ""; // which settings and choices the controls were built for

export const actions = {
  "test-shot": () => post("camera/test"),
  "refresh-camera": () => post("camera/settings/refresh"),
};

$("camera-settings").addEventListener("change", async (event) => {
  const select = event.target;
  if (!(select instanceof HTMLSelectElement)) return;
  select.disabled = true;
  try {
    await post("camera/settings", { key: select.dataset.key, value: select.value });
  } catch (error) {
    showToast(error.message, "error");
    shape = ""; // rebuild from the camera's actual values
  } finally {
    select.disabled = false;
  }
});

export function render({ s, mine, busy }) {
  const { camera } = s;
  setText(
    "camera-detail",
    camera.connected
      ? [camera.model, camera.battery && `battery ${camera.battery}`].filter(Boolean).join(" · ")
      : camera.problem || "No camera",
  );
  $("test-shot").disabled = !mine || busy || !camera.connected;
  $("refresh-camera").disabled = !camera.connected;

  const settings = camera.connected ? camera.settings : [];
  const nextShape = JSON.stringify(settings.map((x) => [x.key, x.choices, x.readonly]));
  const container = $("camera-settings");
  if (nextShape !== shape) {
    shape = nextShape;
    container.replaceChildren(...settings.map(control));
  }
  for (const setting of settings) {
    const input = container.querySelector(`[data-key="${setting.key}"]`);
    if (!input) continue;
    if (input instanceof HTMLSelectElement) {
      if (document.activeElement !== input) input.value = setting.value;
      input.disabled = !mine || busy || setting.readonly;
    } else {
      input.textContent = setting.value;
    }
  }
  $("camera-settings-empty").hidden = !camera.connected || settings.length > 0;
}

function control(setting) {
  if (!setting.choices.length || setting.readonly) {
    return el("div", { class: "setting-row" }, el("span", { class: "muted" }, setting.label),
      el("span", { class: "setting-value", "data-key": setting.key }, setting.value));
  }
  const select = el("select", { class: "field", "data-key": setting.key, "aria-label": setting.label },
    ...setting.choices.map((choice) => el("option", { value: choice }, choice)));
  return el("label", { class: "setting-row" }, el("span", { class: "muted" }, setting.label), select);
}
