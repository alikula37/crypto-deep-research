const BASE = "";

async function request(path, options = {}) {
  const response = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // yoksay
    }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  health: () => request("/api/health"),
  analyses: () => request("/api/analyses"),
  items: () => request("/api/items"),
  snapshot: (coin) => request(`/api/snapshot/${encodeURIComponent(coin)}`),
  analyze: (payload) =>
    request("/api/analyze", { method: "POST", body: JSON.stringify(payload) }),
  deepResearch: (payload) =>
    request("/api/deep-research", { method: "POST", body: JSON.stringify(payload) }),
  ragSearch: (payload) =>
    request("/api/rag/search", { method: "POST", body: JSON.stringify(payload) }),
  ragAsk: (payload) =>
    request("/api/rag/ask", { method: "POST", body: JSON.stringify(payload) }),
  reports: () => request("/api/reports"),
  report: (name) => request(`/api/reports/${encodeURIComponent(name)}`),
  runs: (coin) => request(`/api/runs${coin ? `?coin=${encodeURIComponent(coin)}` : ""}`),
  run: (runId) => request(`/api/runs/${runId}`),
  ragStats: () => request("/api/rag/stats"),
};
