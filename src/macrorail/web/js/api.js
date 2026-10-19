// Commands to the server. Every request identifies this browser for the control lease.

const CLIENT_KEY = "macrorail.client";

// crypto.randomUUID only exists on HTTPS/localhost pages; the Pi serves plain HTTP on the LAN.
function newClientId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function loadClientId() {
  try {
    const existing = localStorage.getItem(CLIENT_KEY);
    if (existing) return existing;
    const id = newClientId();
    localStorage.setItem(CLIENT_KEY, id);
    return id;
  } catch {
    return newClientId(); // storage unavailable: control lasts for this page only
  }
}

export const clientId = loadClientId();

export class CommandError extends Error {}

export async function command(method, path, body) {
  const response = await fetch(`/api/${path}`, {
    method,
    headers: { "Content-Type": "application/json", "X-Client-Id": clientId },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.ok) return;
  let message = `Request failed (${response.status}).`;
  try {
    const { detail } = await response.json();
    if (typeof detail === "string") message = detail;
    else if (Array.isArray(detail)) message = detail.map((d) => d.msg).join(" ");
  } catch {
    // keep the generic message
  }
  throw new CommandError(message);
}

export const post = (path, body) => command("POST", path, body);
export const patch = (path, body) => command("PATCH", path, body);
export const remove = (path) => command("DELETE", path);

export async function getJson(path) {
  const response = await fetch(`/api/${path}`, { headers: { "X-Client-Id": clientId } });
  if (!response.ok) throw new CommandError(`Request failed (${response.status}).`);
  return response.json();
}

// Keeps a WebSocket to the server open, reconnecting with backoff.
export function connectUpdates({ onState, onLog, onConnection }) {
  let delay = 500;
  const open = () => {
    const scheme = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${scheme}://${location.host}/api/ws?client=${clientId}`);
    socket.addEventListener("open", () => {
      delay = 500;
      onConnection(true);
    });
    socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.type === "state") onState(message.state);
      else if (message.type === "log") onLog(message.entries);
    });
    socket.addEventListener("close", () => {
      onConnection(false);
      setTimeout(open, delay);
      delay = Math.min(delay * 2, 5000);
    });
  };
  open();
}
