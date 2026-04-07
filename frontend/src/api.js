const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "";

async function fetchJson(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, options);
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

export function getHealth() {
  return fetchJson("/health");
}

export function streamNext() {
  return fetchJson("/stream");
}

export function resetStream() {
  return fetchJson("/reset", { method: "POST" });
}

export function getLiveHealth() {
  return fetchJson("/live/health");
}

export function getLiveStatus() {
  return fetchJson("/live/status");
}

export function getCoinbaseLiveHealth() {
  return fetchJson("/live/coinbase/health");
}

export function getCoinbaseLiveStatus() {
  return fetchJson("/live/coinbase/status");
}

export function getSecondaryLiveHealth() {
  return fetchJson("/live/secondary/health");
}

export function getSecondaryLiveStatus() {
  return fetchJson("/live/secondary/status");
}
