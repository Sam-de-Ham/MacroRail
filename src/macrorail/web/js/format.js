// Unit conversion and formatting. The server works in motor steps; people read mm and µm.

export const toMm = (steps, stepsPerMm) => steps / stepsPerMm;
export const toUm = (steps, stepsPerMm) => (steps * 1000) / stepsPerMm;
export const fromUm = (um, stepsPerMm) => Math.round((um * stepsPerMm) / 1000);

export function mm(steps, stepsPerMm) {
  return toMm(steps, stepsPerMm).toFixed(3);
}

export function um(steps, stepsPerMm) {
  const value = toUm(steps, stepsPerMm);
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function length(steps, stepsPerMm) {
  const value = Math.abs(toUm(steps, stepsPerMm));
  return value < 1000 ? `${um(Math.abs(steps), stepsPerMm)} µm` : `${(value / 1000).toFixed(3)} mm`;
}

export function duration(seconds) {
  if (seconds == null) return "–";
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h) return `${h} h ${m} min`;
  if (m) return `${m} min ${String(s).padStart(2, "0")} s`;
  return `${s} s`;
}

export function clock(timestamp) {
  return new Date(timestamp * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
