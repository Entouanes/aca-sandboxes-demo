import { colorForState, summarize } from "./state.js";

const $ = (id) => document.getElementById(id);
const tiles = new Map();
let connected = false;
let pending = false;
let current = { sandboxes: [], busy: false };
let key = "";
let pollTimer;

function notify(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}

async function api(method = "GET", body) {
  const response = await fetch("/api/sandboxes", {
    method,
    headers: { "X-Demo-Key": key, ...(body ? { "Content-Type": "application/json" } : {}) },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(method === "DELETE" ? 360000 : 15000),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(typeof error.detail === "string" ? error.detail : "Invalid request.");
  }
  return response.json();
}

function controls() {
  $("launch").disabled = !connected || pending || current.busy || current.systemError || current.sandboxes.length > 0;
  $("cleanup").disabled = !connected || pending || current.busy || !current.sandboxes.length;
  $("connect").disabled = pending;
  $("count").disabled = pending || current.sandboxes.length > 0;
}

function details(id) {
  const item = current.sandboxes.find((sandbox) => sandbox.id === id);
  if (!item) return;
  $("detail-title").textContent = item.id;
  $("detail-message").textContent = item.message;
  $("detail-output").textContent = [
    `Azure ID: ${item.sandboxName || "Not allocated yet"}`,
    `CLI: ${item.version || "Not ready"}`,
    "",
    ...item.history.map((entry) => `${entry.at.toFixed(1).padStart(6)}s  ${entry.state}`),
  ].join("\n");
  $("details").showModal();
}

function render(data) {
  current = data;
  const counts = summarize(data.sandboxes);
  for (const state of ["provisioning", "initializing", "ready"]) {
    $(`${state}-count`).textContent = String(counts[state]).padStart(2, "0");
  }
  $("error-count").textContent = `${counts.error} ERROR${counts.error === 1 ? "" : "S"}`;
  $("elapsed").replaceChildren(document.createTextNode(data.elapsed.toFixed(1)), Object.assign(document.createElement("span"), { textContent: "s" }));
  $("progress").max = counts.total || 1;
  $("progress").value = counts.ready;
  $("progress-label").textContent = counts.total ? `${counts.ready} / ${counts.total} ready` : "Awaiting launch";
  $("empty").hidden = counts.total > 0;
  $("mode").textContent = data.mode === "simulation" ? "SIMULATION / NO AZURE" : "LIVE / AZURE";
  $("empty").querySelector("p").textContent = data.mode === "simulation"
    ? "Local rehearsal mode. No Azure resources will be created."
    : "Choose your fleet size and launch. Each tile is a real, hardware-isolated Azure workspace.";
  $("count").max = data.limit;
  $("limit-label").textContent = `up to ${data.limit} workspaces`;
  const ids = new Set(data.sandboxes.map((item) => item.id));
  for (const [id, tile] of tiles) {
    if (!ids.has(id)) { tile.remove(); tiles.delete(id); }
  }
  for (const [index, item] of data.sandboxes.entries()) {
    let tile = tiles.get(item.id);
    if (!tile) {
      tile = document.createElement("button");
      tile.type = "button";
      tile.innerHTML = '<span class="tile-head"><span>WORKSPACE</span><i class="dot"></i></span><strong class="tile-number"></strong><span class="tile-status"></span><span class="tile-foot"></span>';
      tile.addEventListener("click", () => details(item.id));
      tiles.set(item.id, tile);
      $("grid").append(tile);
    }
    const color = colorForState(item.state);
    tile.className = `tile ${color}${item.state === "error" ? " failed" : ""}`;
    tile.querySelector(".dot").className = `dot ${color}`;
    tile.querySelector(".tile-number").textContent = String(index + 1).padStart(2, "0");
    tile.querySelector(".tile-status").textContent = item.state;
    tile.querySelector(".tile-foot").textContent = item.readyAfter !== null ? `ready in ${item.readyAfter}s` : item.state === "error" ? "View error details" : "Click for telemetry";
    tile.setAttribute("aria-label", `${item.id}: ${item.state}. ${item.message}`);
    tile.title = item.message;
  }
  $("updated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  controls();
}

async function poll() {
  clearTimeout(pollTimer);
  if (!key || pending) return;
  try {
    const data = await api();
    connected = true;
    $("connection").textContent = "Telemetry connected";
    $("connection").className = "connection live";
    render(data);
    notify(data.systemError || "");
  } catch (error) {
    connected = false;
    $("connection").textContent = "Telemetry unavailable";
    $("connection").className = "connection";
    $("mode").textContent = "DISCONNECTED";
    notify(`${error.message} Displayed tiles are the last known state.`);
    controls();
  } finally {
    pollTimer = setTimeout(poll, 1500);
  }
}

$("connect").addEventListener("click", () => {
  key = $("access-key").value.trim();
  if (!key) { notify("Enter the presenter access key first."); return; }
  poll();
});
$("launch-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  pending = true;
  clearTimeout(pollTimer);
  controls();
  notify();
  try {
    render(await api("POST", { count: Number($("count").value) }));
  } catch (error) {
    notify(error.message);
  } finally {
    pending = false;
    controls();
    pollTimer = setTimeout(poll, 1500);
  }
});
$("cleanup").addEventListener("click", async () => {
  if (!window.confirm("Permanently delete every sandbox in this demo fleet?")) return;
  pending = true;
  clearTimeout(pollTimer);
  controls();
  $("cleanup").textContent = "Deleting...";
  try {
    render(await api("DELETE"));
    notify();
  } catch (error) {
    notify(error.message);
  } finally {
    pending = false;
    $("cleanup").textContent = "Delete fleet";
    controls();
    pollTimer = setTimeout(poll, 1500);
  }
});
$("close-details").addEventListener("click", () => $("details").close());
