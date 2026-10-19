// Small DOM helpers shared by the panels.

export const $ = (id) => document.getElementById(id);

export function setText(id, text) {
  const el = $(id);
  if (el.textContent !== text) el.textContent = text;
}

/** Marks the button whose `attribute` equals `value` as the checked radio in `container`. */
export function setChecked(container, attribute, value) {
  for (const button of container.querySelectorAll(`[${attribute}]`)) {
    button.setAttribute("aria-checked", String(button.getAttribute(attribute) === String(value)));
  }
}

/** Updates an input unless the user is typing in it (or `force`). */
export function setField(input, value, force) {
  if (!force && document.activeElement === input) return;
  if (input.type === "checkbox") input.checked = Boolean(value);
  else if (input.value !== String(value)) input.value = value;
}

export function disable(selector, disabled) {
  for (const el of document.querySelectorAll(selector)) el.disabled = disabled;
}

export function el(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.includes("-") || key === "role") node.setAttribute(key, value);
    else node[key] = value;
  }
  node.append(...children);
  return node;
}
