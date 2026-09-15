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
  profiles: () => request("/api/profiles"),
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
  promptRun: (payload) =>
    request("/api/prompt/run", { method: "POST", body: JSON.stringify(payload), timeoutMs: 300000 }),
  latestPrompt: (coin) =>
    request(`/api/prompts/${encodeURIComponent(coin)}`, { timeoutMs: 60000 }),
  reports: () => request("/api/reports"),
  report: (name) => request(`/api/reports/${encodeURIComponent(name)}`),
  translateReport: (name, language = "en") =>
    request(`/api/reports/${encodeURIComponent(name)}/translate`, {
      method: "POST",
      body: JSON.stringify({ language }),
      timeoutMs: 300000,
    }),
  accuracy: (coin) =>
    request(`/api/accuracy${coin ? `?coin=${encodeURIComponent(coin)}` : ""}`, { timeoutMs: 120000 }),
  calibration: (horizon = 7, coin) =>
    request(
      `/api/calibration?horizon=${horizon}${coin ? `&coin=${encodeURIComponent(coin)}` : ""}`,
      { timeoutMs: 60000 }
    ),
  learningStatus: () => request("/api/learning/status", { timeoutMs: 30000 }),
  models: () => request("/api/models", { timeoutMs: 30000 }),
  retrainModels: () => request("/api/models/retrain", { method: "POST", timeoutMs: 60000 }),
  predictions: (coin) =>
    request(`/api/predictions/${encodeURIComponent(coin)}`, { timeoutMs: 60000 }),
  watchlist: () => request("/api/watchlist"),
  watchlistSeed: () => request("/api/watchlist/seed", { method: "POST", timeoutMs: 60000 }),
  watchlistAdd: (payload) =>
    request("/api/watchlist", { method: "POST", body: JSON.stringify(payload), timeoutMs: 60000 }),
  watchlistUpdate: (coin, payload) =>
    request(`/api/watchlist/${encodeURIComponent(coin)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    }),
  watchlistRemove: (coin) =>
    request(`/api/watchlist/${encodeURIComponent(coin)}`, { method: "DELETE" }),
  watchlistRun: (coin) =>
    request(`/api/watchlist/${encodeURIComponent(coin)}/run`, { method: "POST", timeoutMs: 60000 }),
  carry: () => request("/api/carry/status", { timeoutMs: 60000 }),
  carryRanking: () => request("/api/carry/ranking", { timeoutMs: 300000 }),
  carryStep: () => request("/api/carry/step", { method: "POST", timeoutMs: 300000 }),
  carryReset: () => request("/api/carry/reset", { method: "POST" }),
  portfolio: () => request("/api/portfolio", { timeoutMs: 120000 }),
  portfolioAdd: (payload) =>
    request("/api/portfolio", { method: "POST", body: JSON.stringify(payload), timeoutMs: 60000 }),
  portfolioUpdate: (id, payload) =>
    request(`/api/portfolio/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  portfolioRemove: (id) => request(`/api/portfolio/${id}`, { method: "DELETE" }),
  telegramStatus: () => request("/api/telegram/status", { timeoutMs: 15000 }),
  telegramStart: (token) =>
    request("/api/telegram/start", {
      method: "POST",
      body: JSON.stringify({ token: token || null }),
      timeoutMs: 30000,
    }),
  telegramStop: () => request("/api/telegram/stop", { method: "POST", timeoutMs: 30000 }),
  runs: (coin) => request(`/api/runs${coin ? `?coin=${encodeURIComponent(coin)}` : ""}`),
  run: (runId) => request(`/api/runs/${runId}`),
  ragStats: () => request("/api/rag/stats"),
};
