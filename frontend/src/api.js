const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

async function getJson(path) {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

export function getHealth() {
  return getJson("/health");
}

export function searchStocks(query, limit = 30) {
  return getJson(`/stocks/search?q=${encodeURIComponent(query)}&limit=${limit}`);
}

export function getCandles(symbol, limit = 160) {
  return getJson(`/stocks/${symbol}/candles?limit=${limit}`);
}

export function getNews(symbol, limit = 30) {
  return getJson(`/stocks/${symbol}/news?limit=${limit}`);
}

export function getPrediction(symbol) {
  return getJson(`/stocks/${symbol}/prediction`);
}

export function getModelStatus() {
  return getJson("/models/status");
}

export function getMarketSummary() {
  return getJson("/markets/summary");
}

export function getMarketIndexSeries(market, limit = 160) {
  return getJson(`/markets/index-series?market=${market}&limit=${limit}`);
}

export function getMarketLeaders({ sort = "volume", order = "desc", market = "", limit = 30 } = {}) {
  const params = new URLSearchParams({ sort, order, limit: String(limit) });
  if (market) {
    params.set("market", market);
  }
  return getJson(`/markets/leaders?${params.toString()}`);
}

export function getMarketSignals(direction, limit = 10) {
  return getJson(`/markets/signals?direction=${direction}&limit=${limit}`);
}

export function getMarketNews(limit = 12) {
  return getJson(`/markets/news?limit=${limit}`);
}

export function getPredictionExplanation(symbol) {
  return getJson(`/stocks/${symbol}/explanation`);
}
