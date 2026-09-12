const BASE = "";

function networkError() {
  return new Error(
    "Sunucuya ulaşılamıyor. Docker konteyneri (docker compose up -d) veya 'cdr serve' komutu çalışıyor mu?"
  );
}

async function request(path, { timeoutMs = 60000, ...options } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  let response;
  try {
    response = await fetch(`${BASE}${path}`, {
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      ...options,
    });
  } catch (error) {
    if (error.name === "AbortError") {
      throw new Error("İstek zaman aşımına uğradı. Sunucu yoğun olabilir; lütfen tekrar deneyin.");
    }
    throw networkError();
  } finally {
    clearTimeout(timer);
  }
  if (!response.ok) {
    let detail = `Sunucu hatası (${response.status})`;
    try {
      const data = await response.json();
      detail = data.detail || detail;
    } catch {
      // JSON olmayan yanıt
    }
    throw new Error(detail);
  }
  return response.json();
}

export const api = {
  health: () => request("/api/health", { timeoutMs: 15000 }),
  analyses: () => request("/api/analyses"),
  items: () => request("/api/items"),
  snapshot: (coin) => request(`/api/snapshot/${encodeURIComponent(coin)}`),
  analyze: (payload) =>
    request("/api/analyze", { method: "POST", body: JSON.stringify(payload), timeoutMs: 300000 }),
  deepResearch: (payload) =>
    request("/api/deep-research", { method: "POST", body: JSON.stringify(payload), timeoutMs: 900000 }),
  startDeepResearch: (payload) =>
    request("/api/deep-research/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
      timeoutMs: 30000,
    }),
  jobStatus: (jobId) =>
    request(`/api/deep-research/jobs/${encodeURIComponent(jobId)}`, { timeoutMs: 90000 }),
  ragSearch: (payload) =>
    request("/api/rag/search", { method: "POST", body: JSON.stringify(payload) }),
  ragAsk: (payload) =>
    request("/api/rag/ask", { method: "POST", body: JSON.stringify(payload), timeoutMs: 180000 }),
  reports: () => request("/api/reports"),
  report: (name) => request(`/api/reports/${encodeURIComponent(name)}`),
  runs: (coin) => request(`/api/runs${coin ? `?coin=${encodeURIComponent(coin)}` : ""}`),
  run: (runId) => request(`/api/runs/${runId}`),
  ragStats: () => request("/api/rag/stats"),
};
