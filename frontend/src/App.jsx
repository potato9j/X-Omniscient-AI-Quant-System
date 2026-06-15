import { createChart } from "lightweight-charts";
import {
  Activity,
  ArrowDownAZ,
  ArrowUpAZ,
  BarChart3,
  Database,
  Gauge,
  Home,
  Newspaper,
  Search,
  Server,
  TrendingDown,
  TrendingUp,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  getCandles,
  getHealth,
  getMarketIndexSeries,
  getMarketLeaders,
  getMarketNews,
  getMarketSignals,
  getMarketSummary,
  getModelStatus,
  getNews,
  getPrediction,
  getPredictionExplanation,
  getSentimentStatus,
  searchStocks,
  startSentimentAnalysis,
} from "./api";

function formatNumber(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function formatPercent(value) {
  if (value === null || value === undefined) {
    return "--%";
  }
  return `${(Number(value) * 100).toFixed(1)}%`;
}

function formatSignedPercent(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const number = Number(value) * 100;
  return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
}

function nextTradeTime(dateText, steps) {
  const date = new Date(`${dateText}T00:00:00`);
  date.setDate(date.getDate() + steps);
  return date.toISOString().slice(0, 10);
}

function delay(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="metric">
      <Icon size={16} />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function MarketLineChart({ kospi, kosdaq }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#4f596b",
        fontFamily: "Inter, Segoe UI, Noto Sans KR, sans-serif",
      },
      grid: {
        vertLines: { color: "#eef1f5" },
        horzLines: { color: "#eef1f5" },
      },
      rightPriceScale: { borderColor: "#d9dee7" },
      timeScale: { borderColor: "#d9dee7" },
    });
    const kospiSeries = chart.addLineSeries({ color: "#d92525", lineWidth: 2, title: "KOSPI" });
    const kosdaqSeries = chart.addLineSeries({ color: "#1f5fbf", lineWidth: 2, title: "KOSDAQ" });
    chartRef.current = { chart, kospiSeries, kosdaqSeries };
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) {
      return;
    }
    chartRef.current.kospiSeries.setData(kospi.map((item) => ({ time: item.time, value: item.value })));
    chartRef.current.kosdaqSeries.setData(kosdaq.map((item) => ({ time: item.time, value: item.value })));
    chartRef.current.chart.timeScale().fitContent();
  }, [kospi, kosdaq]);

  return <div className="chart-canvas" ref={containerRef} />;
}

function CandleChart({ candles, prediction }) {
  const containerRef = useRef(null);
  const chartRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) {
      return undefined;
    }
    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { color: "#ffffff" },
        textColor: "#4f596b",
        fontFamily: "Inter, Segoe UI, Noto Sans KR, sans-serif",
      },
      grid: {
        vertLines: { color: "#eef1f5" },
        horzLines: { color: "#eef1f5" },
      },
      rightPriceScale: { borderColor: "#d9dee7" },
      timeScale: { borderColor: "#d9dee7" },
    });
    const candlesSeries = chart.addCandlestickSeries({
      upColor: "#d92525",
      downColor: "#1f5fbf",
      borderUpColor: "#d92525",
      borderDownColor: "#1f5fbf",
      wickUpColor: "#d92525",
      wickDownColor: "#1f5fbf",
    });
    const forecastSeries = chart.addLineSeries({
      color: "#252a35",
      lineWidth: 2,
      lineStyle: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chartRef.current = { chart, candlesSeries, forecastSeries };
    return () => {
      chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current || !candles.length) {
      return;
    }
    chartRef.current.candlesSeries.setData(
      candles.map((item) => ({
        time: item.trade_date,
        open: item.open_price,
        high: item.high_price,
        low: item.low_price,
        close: item.close_price,
      })),
    );

    const last = candles[candles.length - 1];
    if (prediction) {
      const direction = prediction.expected_direction === "UP" ? 1 : -1;
      chartRef.current.forecastSeries.applyOptions({
        color: direction > 0 ? "#d92525" : "#1f5fbf",
      });
      chartRef.current.forecastSeries.setData([
        { time: last.trade_date, value: last.close_price },
        {
          time: nextTradeTime(last.trade_date, prediction.horizon_steps),
          value: Math.max(1, last.close_price * (1 + direction * 0.018)),
        },
      ]);
    } else {
      chartRef.current.forecastSeries.setData([]);
    }
    chartRef.current.chart.timeScale().fitContent();
  }, [candles, prediction]);

  return <div className="chart-canvas" ref={containerRef} />;
}

function NewsList({ news, compact = false, loading = false }) {
  if (!news.length) {
    return <div className="empty-state">{loading ? "뉴스 불러오는 중" : "표시할 뉴스 없음"}</div>;
  }
  return (
    <div className={compact ? "news-banner-list" : "news-list"}>
      {news.map((item) => {
        const score = item.sentiment_score;
        const tone = score == null ? "flat" : score > 0.05 ? "good" : score < -0.05 ? "bad" : "flat";
        return (
          <a className={`news-card ${compact ? "compact" : ""}`} href={item.url} key={item.id} rel="noreferrer" target="_blank">
            <strong>{item.title}</strong>
            <span>
              {item.source || "Naver"} · {item.published_at || "-"}
            </span>
            {item.ai_summary && !compact ? <p>{item.ai_summary}</p> : null}
            <em className={`sentiment ${tone}`}>{score == null ? "미분석" : score.toFixed(2)}</em>
          </a>
        );
      })}
    </div>
  );
}

function LeaderTable({ rows, onSelect, loading = false }) {
  if (!rows.length) {
    return <div className="empty-state">{loading ? "랭킹 불러오는 중" : "랭킹 데이터 없음"}</div>;
  }
  return (
    <div className="leader-list">
      {rows.map((item, index) => {
        const tone = (item.change_rate ?? 0) >= 0 ? "up-text" : "down-text";
        return (
          <button className="leader-row" key={item.symbol} onClick={() => onSelect(item)} type="button">
            <span className="rank">{index + 1}</span>
            <span>
              <strong>{item.name}</strong>
              <small>
                {item.symbol} · {item.market}
              </small>
            </span>
            <span className="leader-numbers">
              <strong>{formatNumber(item.volume)}</strong>
              <small className={tone}>{formatSignedPercent(item.change_rate)}</small>
            </span>
          </button>
        );
      })}
    </div>
  );
}

function SignalList({ title, rows, direction, onSelect, loading = false }) {
  const tone = direction === "up" ? "up-text" : "down-text";
  return (
    <section className="signal-column">
      <h3>{title}</h3>
      {!rows.length && loading ? <div className="empty-state compact">신호 계산 중</div> : null}
      {rows.map((item) => (
        <button className="signal-row" key={`${direction}-${item.symbol}`} onClick={() => onSelect(item)} type="button">
          <span>
            <strong>{item.name}</strong>
            <small>{item.symbol}</small>
          </span>
          <em className={tone}>
            {direction === "up" ? formatPercent(item.up_probability) : formatPercent(item.down_probability)}
          </em>
        </button>
      ))}
    </section>
  );
}

function Explanation({ explanation }) {
  if (!explanation) {
    return <div className="detail-section empty-state">예측 설명 없음</div>;
  }
  return (
    <section className="detail-section">
      <div className="detail-heading">
        <span>판단 근거</span>
        <h2>{explanation.headline}</h2>
        <p>{explanation.summary}</p>
        <strong>유효 기준: {explanation.valid_until_label}</strong>
      </div>
      <div className="reason-grid">
        <article>
          <h3>상승 근거</h3>
          <ul>
            {explanation.positive_reasons.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article>
          <h3>하락 근거</h3>
          <ul>
            {explanation.negative_reasons.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
        <article>
          <h3>주의점</h3>
          <ul>
            {explanation.risk_notes.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </article>
      </div>
    </section>
  );
}

function App() {
  const [view, setView] = useState("market");
  const [query, setQuery] = useState("");
  const [health, setHealth] = useState(null);
  const [modelStatus, setModelStatus] = useState(null);
  const [marketSummary, setMarketSummary] = useState([]);
  const [kospiSeries, setKospiSeries] = useState([]);
  const [kosdaqSeries, setKosdaqSeries] = useState([]);
  const [leaders, setLeaders] = useState([]);
  const [leaderSort, setLeaderSort] = useState("volume");
  const [leaderOrder, setLeaderOrder] = useState("desc");
  const [bullish, setBullish] = useState([]);
  const [bearish, setBearish] = useState([]);
  const [marketNews, setMarketNews] = useState([]);
  const [selected, setSelected] = useState(null);
  const [candles, setCandles] = useState([]);
  const [stockNews, setStockNews] = useState([]);
  const [prediction, setPrediction] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [sentimentStatus, setSentimentStatus] = useState(null);
  const [sentimentNotice, setSentimentNotice] = useState("");
  const [booting, setBooting] = useState(true);
  const [error, setError] = useState("");

  const opinion = useMemo(() => {
    if (!prediction) {
      return { label: "대기", className: "neutral", icon: Activity };
    }
    if (prediction.expected_direction === "UP") {
      return { label: "매수 우위", className: "up", icon: TrendingUp };
    }
    return { label: "방어 우위", className: "down", icon: TrendingDown };
  }, [prediction]);

  async function loadMarket(sort = leaderSort, order = leaderOrder) {
    const [
      healthData,
      modelData,
      summaryData,
      kospiData,
      kosdaqData,
      leaderData,
      bullishData,
      bearishData,
      newsData,
      sentimentData,
    ] =
      await Promise.all([
        getHealth(),
        getModelStatus(),
        getMarketSummary(),
        getMarketIndexSeries("KOSPI"),
        getMarketIndexSeries("KOSDAQ"),
        getMarketLeaders({ sort, order, limit: 30 }),
        getMarketSignals("up", 10),
        getMarketSignals("down", 10),
        getMarketNews(12),
        getSentimentStatus(),
      ]);
    setHealth(healthData);
    setModelStatus(modelData);
    setMarketSummary(summaryData);
    setKospiSeries(kospiData);
    setKosdaqSeries(kosdaqData);
    setLeaders(leaderData);
    setBullish(bullishData);
    setBearish(bearishData);
    setMarketNews(newsData);
    setSentimentStatus(sentimentData);
  }

  async function loadStock(stock) {
    const normalized = { symbol: stock.symbol, name: stock.name, market: stock.market };
    setSelected(normalized);
    setView("stock");
    const [candleRows, newsRows, predictionRow, explanationRow] = await Promise.all([
      getCandles(normalized.symbol, 120),
      getNews(normalized.symbol, 30),
      getPrediction(normalized.symbol).catch(() => null),
      getPredictionExplanation(normalized.symbol).catch(() => null),
    ]);
    setCandles(candleRows);
    setStockNews(newsRows);
    setPrediction(predictionRow);
    setExplanation(explanationRow);
    setSentimentStatus(await getSentimentStatus());
  }

  useEffect(() => {
    let cancelled = false;

    async function boot() {
      setBooting(true);
      for (let attempt = 1; attempt <= 8; attempt += 1) {
        try {
          setError(attempt === 1 ? "" : "API 연결 재시도 중");
          await loadMarket();
          if (cancelled) {
            return;
          }
          setError("");
          setBooting(false);
          return;
        } catch (bootError) {
          if (cancelled) {
            return;
          }
          if (attempt === 8) {
            setError(bootError.message);
            setBooting(false);
            return;
          }
          setError(`API 연결 대기 · ${bootError.message}`);
          await delay(2000);
        }
      }
    }

    boot();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    async function refreshLeaders() {
      try {
        const rows = await getMarketLeaders({ sort: leaderSort, order: leaderOrder, limit: 30 });
        setLeaders(rows);
      } catch (leaderError) {
        setError(leaderError.message);
      }
    }
    refreshLeaders();
  }, [leaderSort, leaderOrder]);

  async function handleSubmit(event) {
    event.preventDefault();
    const trimmed = query.trim();
    if (!trimmed) {
      setView("market");
      setSelected(null);
      return;
    }
    try {
      setError("");
      const rows = await searchStocks(trimmed, 1);
      if (rows[0]) {
        await loadStock(rows[0]);
      } else {
        setError("검색 결과 없음");
      }
    } catch (searchError) {
      setError(searchError.message);
    }
  }

  async function handleAnalyzeSentiment() {
    try {
      setError("");
      setSentimentNotice("");
      const response = await startSentimentAnalysis(5);
      setSentimentNotice(response.message);
      setSentimentStatus(await getSentimentStatus());
    } catch (sentimentError) {
      setError(sentimentError.message);
    }
  }

  useEffect(() => {
    const status = sentimentStatus?.job_status;
    if (status !== "queued" && status !== "running") {
      return undefined;
    }

    const timer = window.setInterval(async () => {
      try {
        const nextStatus = await getSentimentStatus();
        setSentimentStatus(nextStatus);
        if (nextStatus.job_status !== "queued" && nextStatus.job_status !== "running") {
          if (view === "stock" && selected?.symbol) {
            setStockNews(await getNews(selected.symbol, 30));
          } else {
            setMarketNews(await getMarketNews(12));
          }
          setSentimentNotice(
            nextStatus.last_error
              ? "감성 분석 실패"
              : `감성 분석 완료 · ${nextStatus.last_analyzed_count}건`,
          );
        }
      } catch (pollError) {
        setError(pollError.message);
      }
    }, 4000);

    return () => window.clearInterval(timer);
  }, [sentimentStatus?.job_status, selected?.symbol, view]);

  const DirectionIcon = opinion.icon;
  const visibleNews = view === "stock" ? stockNews : marketNews;
  const sentimentJobActive =
    sentimentStatus?.job_status === "queued" || sentimentStatus?.job_status === "running";
  const sentimentPending = sentimentStatus?.pending_news ?? 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <button className="brand-block" onClick={() => setView("market")} type="button">
            <div className="brand-mark">OX</div>
            <div>
              <h1>Omniscient Quant</h1>
            <p>
              {booting
                ? error || "데이터 동기화 중"
                : error
                  ? `API 오류 · ${error}`
                  : view === "market"
                    ? "시장 인사이트"
                    : "종목 리서치"}
            </p>
            </div>
        </button>

        <form className="search-form" onSubmit={handleSubmit}>
          <Search size={18} />
          <input
            autoComplete="off"
            onChange={(event) => setQuery(event.target.value)}
            placeholder="종목명 또는 코드 검색"
            type="search"
            value={query}
          />
          <button type="submit">검색</button>
        </form>

        <div className="metric-strip">
          <Metric icon={Database} label="Universe" value={health ? formatNumber(health.stock_count) : booting ? "..." : "0"} />
          <Metric icon={BarChart3} label="OHLCV" value={health ? formatNumber(health.ohlcv_rows) : booting ? "..." : "0"} />
          <Metric icon={Gauge} label="Signals" value={health ? formatNumber(health.prediction_rows) : booting ? "..." : "0"} />
          <Metric
            icon={Server}
            label="Model"
            value={modelStatus?.metadata?.model_version?.replace("predictor_", "") ?? (booting ? "..." : "-")}
          />
        </div>
      </header>

      <main className={`dashboard-grid ${view}`}>
        <aside className="panel left-panel">
          {view === "market" ? (
            <>
              <div className="panel-heading stacked">
                <div>
                  <h2>마켓 랭킹</h2>
                  <span>거래량 · 모멘텀</span>
                </div>
                <div className="segmented">
                  <button className={leaderSort === "volume" ? "active" : ""} onClick={() => setLeaderSort("volume")} type="button">
                    거래량
                  </button>
                  <button
                    className={leaderSort === "change_rate" ? "active" : ""}
                    onClick={() => setLeaderSort("change_rate")}
                    type="button"
                  >
                    변동폭
                  </button>
                  <button onClick={() => setLeaderOrder(leaderOrder === "desc" ? "asc" : "desc")} type="button">
                    {leaderOrder === "desc" ? <ArrowDownAZ size={15} /> : <ArrowUpAZ size={15} />}
                  </button>
                </div>
              </div>
              <LeaderTable loading={booting} onSelect={loadStock} rows={leaders} />
            </>
          ) : (
            <>
              <div className="panel-heading">
                <h2>종목 요약</h2>
                <button className="icon-button" onClick={() => setView("market")} title="시장 화면" type="button">
                  <Home size={16} />
                </button>
              </div>
              <div className="stock-summary">
                <span className="market-chip">{selected?.market}</span>
                <h2>
                  {selected?.symbol} {selected?.name}
                </h2>
                <p>{explanation?.summary || "예측 설명을 불러오는 중입니다."}</p>
                <strong>{explanation?.valid_until_label || "유효 시점 계산 중"}</strong>
              </div>
            </>
          )}
        </aside>

        <section className="center-stack">
          {view === "market" ? (
            <>
              <div className="chart-toolbar">
                <div className="toolbar-copy">
                  <span className="market-chip">MARKET INTELLIGENCE</span>
                  <h2>국내 증시 인사이트</h2>
                </div>
                <div className="index-card-row">
                  {marketSummary.map((item) => (
                    <div className="index-card" key={item.market}>
                      <span>{item.market}</span>
                      <strong>{item.current_value?.toLocaleString("ko-KR") ?? "-"}</strong>
                      <em className={(item.change_rate ?? 0) >= 0 ? "up-text" : "down-text"}>
                        {formatSignedPercent(item.change_rate)}
                      </em>
                    </div>
                  ))}
                </div>
              </div>
              <section className="chart-panel market-chart">
                <MarketLineChart kosdaq={kosdaqSeries} kospi={kospiSeries} />
              </section>
              <section className="signal-panel">
                <SignalList direction="up" loading={booting} onSelect={loadStock} rows={bullish} title="호황 예상 종목" />
                <SignalList direction="down" loading={booting} onSelect={loadStock} rows={bearish} title="불황 예상 종목" />
              </section>
            </>
          ) : (
            <>
              <div className="chart-toolbar">
                <div>
                  <span className="market-chip">{selected?.market}</span>
                  <h2>
                    {selected?.symbol} {selected?.name}
                  </h2>
                </div>
                <div className={`prediction-pill ${opinion.className}`}>
                  <DirectionIcon size={20} />
                  <span>{opinion.label}</span>
                  <strong>
                    {prediction
                      ? formatPercent(
                          prediction.expected_direction === "UP"
                            ? prediction.up_probability
                            : prediction.down_probability,
                        )
                      : "--%"}
                  </strong>
                </div>
              </div>
              <section className="chart-panel stock-chart">
                <div className="timeframe-row">
                  <button className="active" type="button">
                    일봉
                  </button>
                  <button disabled title="10분봉 수집 파이프라인 연결 후 활성화됩니다." type="button">
                    10분
                  </button>
                </div>
                <CandleChart candles={candles} prediction={prediction} />
              </section>
              <section className="opinion-panel">
                <Metric icon={TrendingUp} label="상승 확률" value={formatPercent(prediction?.up_probability)} />
                <Metric icon={TrendingDown} label="하락 확률" value={formatPercent(prediction?.down_probability)} />
                <Metric icon={Activity} label="현재가" value={formatNumber(prediction?.current_price)} />
                <Metric icon={Server} label="유효 기준" value={prediction ? `${prediction.horizon_steps} steps` : "-"} />
              </section>
            </>
          )}
        </section>

        <aside className="panel right-panel">
          <div className="panel-heading">
            <h2>
              <Newspaper size={16} />
              {view === "market" ? "시장 뉴스" : "뉴스 감성"}
            </h2>
            <div className="news-actions">
              <button
                className="mini-button"
                disabled={sentimentJobActive || sentimentPending <= 0}
                onClick={handleAnalyzeSentiment}
                type="button"
              >
                {sentimentJobActive ? "분석 중" : "감성 분석"}
              </button>
              <span>
                {sentimentStatus
                  ? `${sentimentStatus.analyzed_news}/${sentimentStatus.total_news}`
                  : booting
                    ? "..."
                    : visibleNews.length}
              </span>
            </div>
          </div>
          {sentimentNotice || sentimentStatus?.last_error ? (
            <div className={`sentiment-status-line ${sentimentStatus?.last_error ? "bad" : ""}`}>
              {sentimentStatus?.last_error || sentimentNotice}
            </div>
          ) : null}
          <NewsList compact={view === "market"} loading={booting} news={visibleNews} />
        </aside>
      </main>

      {view === "stock" ? <Explanation explanation={explanation} /> : null}
    </div>
  );
}

export default App;
