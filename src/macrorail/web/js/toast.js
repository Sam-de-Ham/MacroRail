// A short message at the bottom of the screen.

import { $ } from "./dom.js";

let timer = 0;

export function showToast(message, level = "info") {
  const toast = $("toast");
  toast.textContent = message;
  toast.className = `toast ${level}`;
  toast.hidden = false;
  clearTimeout(timer);
  timer = setTimeout(() => {
    toast.hidden = true;
  }, 5000);
}
