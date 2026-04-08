import { useEffect, useRef, useState } from "react";
import {
  getCoinbaseLiveHealth,
  getCoinbaseLiveStatus,
  getHealth,
  getSecondaryLiveHealth,
  getSecondaryLiveStatus,
  resetStream,
  streamNext,
} from "./api";

const MODE_CONFIG = {
  simulation: {
    label: "Simulation",
    subtitle: "Historical replay from stored Coinbase trade data",
    pollMs: 45,
    fetchStatus: streamNext,
  },
  coinbase: {
    label: "BTC-USD Live",
    subtitle: "Coinbase exchange live market flow",
    pollMs: 450,
    fetchStatus: getCoinbaseLiveStatus,
  },
  secondary: {
    label: "ETH-USD Live",
    subtitle: "Second live market stream from Coinbase",
    pollMs: 450,
    fetchStatus: getSecondaryLiveStatus,
  },
};

function signalClass(signal) {
  return (signal || "NORMAL").toLowerCase();
}

function formatSignal(signal) {
  return (signal || "NORMAL").replaceAll("_", " ");
}

function formatProvider(value) {
  if (!value) {
    return "simulation";
  }
  return value.replaceAll("_", " ");
}

function normalizeModePayload(mode, payload) {
  if (mode === "simulation") {
    return payload;
  }
  return payload?.latest_event || null;
}

function formatPrice(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "--";
  }
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatVolume(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "--";
  }
  return Number(value).toLocaleString(undefined, {
    minimumFractionDigits: 4,
    maximumFractionDigits: 6,
  });
}

function formatScore(value) {
  if (value == null || Number.isNaN(Number(value))) {
    return "--";
  }
  return Number(value).toFixed(4);
}

function formatTimestamp(value) {
  if (!value) {
    return "Waiting...";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function detectionNote(event) {
  if (!event) {
    return "Waiting for enough market activity to score the next event.";
  }
  if (event.confirmed_simulation_case) {
    return event.alert_message || "Injected manipulation scenario active in simulation mode.";
  }
  if (event.signal === "HIGH_RISK") {
    return "Price displacement and event volume both moved far enough from the short-term baseline to trigger a high-risk alert.";
  }
  if (event.signal === "SUSPICIOUS") {
    return "The latest print is unusual relative to the recent tape, but it does not meet the stronger high-risk threshold.";
  }
  return "The latest print remains inside the short-term baseline learned from the current rolling window.";
}

function feedSummary(mode, activeHealth) {
  if (mode === "simulation") {
    return "Streaming recorded market tape";
  }
  if (!activeHealth) {
    return "Connecting to live exchange";
  }
  return activeHealth.connection_status || "connecting";
}

function alertHeadline(event) {
  if (!event) {
    return "";
  }
  if (event.confirmed_simulation_case) {
    return event.scenario_label || "Injected manipulation case";
  }
  if (event.signal === "HIGH_RISK") {
    return "High-Risk anomaly detected";
  }
  if (event.signal === "SUSPICIOUS") {
    return "Suspicious activity detected";
  }
  return "";
}

function shouldShowAlertPopup(event) {
  return Boolean(event && (event.confirmed_simulation_case || event.signal === "HIGH_RISK"));
}

function spreadLabel(event) {
  if (!event || event.best_bid == null || event.best_ask == null) {
    return "--";
  }
  return formatPrice(Number(event.best_ask) - Number(event.best_bid));
}

function ChartEmptyState({ mode }) {
  return (
    <div className="empty-chart">
      <strong>{MODE_CONFIG[mode].label}</strong>
      <p>{MODE_CONFIG[mode].subtitle}</p>
      <span>Waiting for the first scored event...</span>
    </div>
  );
}

function MarketChart({ events, mode }) {
  const visibleEvents = events.slice(-160);

  if (visibleEvents.length === 0) {
    return <ChartEmptyState mode={mode} />;
  }

  const width = 1120;
  const height = 430;
  const leftPad = 18;
  const rightPad = 78;
  const topPad = 26;
  const priceBottom = 246;
  const volumeTop = 290;
  const bottomPad = 30;
  const chartWidth = width - leftPad - rightPad;
  const prices = visibleEvents.map((event) => Number(event.price));
  const volumes = visibleEvents.map((event) => Number(event.volume));
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const maxVolume = Math.max(...volumes, 1);
  const pointCount = visibleEvents.length;
  const stepX = pointCount > 1 ? chartWidth / (pointCount - 1) : 0;
  const eventX = (index) =>
    pointCount > 1 ? leftPad + stepX * index : leftPad + chartWidth / 2;

  const priceToY = (price) => {
    if (maxPrice === minPrice) {
      return (topPad + priceBottom) / 2;
    }
    const ratio = (price - minPrice) / (maxPrice - minPrice);
    return priceBottom - ratio * (priceBottom - topPad);
  };

  const volumeToHeight = (volume) => {
    const ratio = volume / maxVolume;
    return Math.max(6, ratio * (height - volumeTop - bottomPad));
  };

  const pricePoints =
    pointCount === 1
      ? [
          { x: leftPad, y: priceToY(prices[0]) },
          { x: width - rightPad, y: priceToY(prices[0]) },
        ]
      : visibleEvents.map((event, index) => ({
          x: eventX(index),
          y: priceToY(Number(event.price)),
        }));

  const pricePolyline = pricePoints.map((point) => `${point.x},${point.y}`).join(" ");
  const priceArea = `${leftPad},${priceBottom} ${pricePolyline} ${width - rightPad},${priceBottom}`;
  const priceTicks = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const value = maxPrice - (maxPrice - minPrice) * ratio;
    const y = topPad + (priceBottom - topPad) * ratio;
    return { value, y };
  });
  const timeIndices = Array.from(new Set([0, Math.floor((pointCount - 1) * 0.33), Math.floor((pointCount - 1) * 0.66), pointCount - 1]));
  const lastEvent = visibleEvents[visibleEvents.length - 1];
  const lastY = priceToY(Number(lastEvent.price));

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="chart" role="img" aria-label="Real-time price and volume chart">
      <defs>
        <linearGradient id="terminalArea" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(0, 240, 255, 0.2)" />
          <stop offset="100%" stopColor="rgba(0, 240, 255, 0.0)" />
        </linearGradient>
        <linearGradient id="volumeUp" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(0, 240, 255, 0.8)" />
          <stop offset="100%" stopColor="rgba(0, 240, 255, 0.1)" />
        </linearGradient>
        <linearGradient id="volumeDown" x1="0%" y1="0%" x2="0%" y2="100%">
          <stop offset="0%" stopColor="rgba(255, 0, 85, 0.8)" />
          <stop offset="100%" stopColor="rgba(255, 0, 85, 0.1)" />
        </linearGradient>
      </defs>

      <rect x="0" y="0" width={width} height={height} rx="24" className="chart-shell" />

      {priceTicks.map((tick, index) => (
        <g key={`price-grid-${index}`}>
          <line x1={leftPad} y1={tick.y} x2={width - rightPad} y2={tick.y} className="chart-grid" />
          <text x={width - rightPad + 10} y={tick.y + 4} className="chart-price-label">
            {formatPrice(tick.value)}
          </text>
        </g>
      ))}

      <line x1={leftPad} y1={volumeTop - 14} x2={width - rightPad} y2={volumeTop - 14} className="chart-divider" />
      <text x={leftPad} y={18} className="chart-panel-label">
        Price
      </text>
      <text x={leftPad} y={volumeTop - 20} className="chart-panel-label">
        Volume
      </text>

      {visibleEvents.map((event, index) => {
        if (event.signal === "NORMAL") {
          return null;
        }
        const x = eventX(index);
        return (
          <line
            key={`alert-band-${event.timestamp}-${index}`}
            x1={x}
            y1={topPad}
            x2={x}
            y2={height - bottomPad}
            className={`chart-alert-band ${signalClass(event.signal)}`}
          />
        );
      })}

      <polygon points={priceArea} className="chart-area" />
      <polyline points={pricePolyline} className="chart-line" />

      {visibleEvents.map((event, index) => {
        const x = eventX(index);
        const previous = visibleEvents[index - 1];
        const trendClass = previous && Number(event.price) < Number(previous.price) ? "down" : "up";
        const barHeight = volumeToHeight(Number(event.volume));
        const barWidth = Math.max(3, Math.min(10, stepX * 0.56 || 8));
        const y = height - bottomPad - barHeight;
        return (
          <rect
            key={`volume-${event.timestamp}-${index}`}
            x={x - barWidth / 2}
            y={y}
            width={barWidth}
            height={barHeight}
            rx="2"
            className={`chart-volume ${trendClass}`}
          />
        );
      })}

      <line x1={leftPad} y1={lastY} x2={width - rightPad} y2={lastY} className="chart-last-line" />
      <rect x={width - rightPad + 6} y={lastY - 12} width="66" height="24" rx="8" className="chart-last-pill" />
      <text x={width - 8} y={lastY + 4} textAnchor="end" className="chart-last-price">
        {formatPrice(lastEvent.price)}
      </text>

      {timeIndices.map((index) => (
        <text key={`time-${index}`} x={eventX(index)} y={height - 8} textAnchor="middle" className="chart-time-label">
          {formatTimestamp(visibleEvents[index]?.timestamp)}
        </text>
      ))}
    </svg>
  );
}

function App() {
  const [backendHealth, setBackendHealth] = useState(null);
  const [providerHealth, setProviderHealth] = useState({
    coinbase: null,
    secondary: null,
  });
  const [mode, setMode] = useState("simulation");
  const [current, setCurrent] = useState(null);
  const [events, setEvents] = useState([]);
  const [error, setError] = useState("");
  const [pollingPaused, setPollingPaused] = useState(false);
  const [alertPopup, setAlertPopup] = useState(null);
  const pollTimeoutRef = useRef(null);
  const alertTimeoutRef = useRef(null);
  const audioContextRef = useRef(null);
  const activeAlertIdRef = useRef("");
  const isLiveMode = mode !== "simulation";

  useEffect(() => {
    function primeAudio() {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) {
        return;
      }
      if (!audioContextRef.current) {
        audioContextRef.current = new AudioContextClass();
      }
      if (audioContextRef.current.state === "suspended") {
        audioContextRef.current.resume().catch(() => {});
      }
    }

    window.addEventListener("pointerdown", primeAudio, { passive: true });
    window.addEventListener("keydown", primeAudio);

    return () => {
      window.removeEventListener("pointerdown", primeAudio);
      window.removeEventListener("keydown", primeAudio);
    };
  }, []);

  useEffect(() => {
    if (!shouldShowAlertPopup(current)) {
      activeAlertIdRef.current = "";
      return;
    }

    const alertId = current.confirmed_simulation_case
      ? `${current.manipulation_tag || current.scenario_label || "simulation-alert"}`
      : `${current.product_id || "market"}-${current.signal}`;

    if (activeAlertIdRef.current === alertId) {
      return;
    }
    activeAlertIdRef.current = alertId;
    setAlertPopup(current);
    window.clearTimeout(alertTimeoutRef.current);
    alertTimeoutRef.current = window.setTimeout(() => {
      setAlertPopup(null);
    }, 2600);

    const audioContext = audioContextRef.current;
    if (!audioContext) {
      return;
    }

    const now = audioContext.currentTime;
    const master = audioContext.createGain();
    master.gain.setValueAtTime(0.0001, now);
    master.gain.exponentialRampToValueAtTime(0.18, now + 0.03);
    master.gain.exponentialRampToValueAtTime(0.0001, now + 1.1);
    master.connect(audioContext.destination);

    [0, 0.32, 0.64].forEach((offset, index) => {
      const oscillator = audioContext.createOscillator();
      const gain = audioContext.createGain();
      oscillator.type = index % 2 === 0 ? "sawtooth" : "square";
      oscillator.frequency.setValueAtTime(index % 2 === 0 ? 880 : 660, now + offset);
      gain.gain.setValueAtTime(0.0001, now + offset);
      gain.gain.exponentialRampToValueAtTime(0.45, now + offset + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + offset + 0.22);
      oscillator.connect(gain);
      gain.connect(master);
      oscillator.start(now + offset);
      oscillator.stop(now + offset + 0.24);
    });
  }, [current]);

  useEffect(() => () => window.clearTimeout(alertTimeoutRef.current), []);

  useEffect(() => {
    let cancelled = false;

    async function loadHealth() {
      const responses = await Promise.allSettled([
        getHealth(),
        getCoinbaseLiveHealth(),
        getSecondaryLiveHealth(),
      ]);

      if (cancelled) {
        return;
      }

      if (responses[0].status === "fulfilled") {
        setBackendHealth(responses[0].value);
      }
      if (responses[1].status === "fulfilled") {
        setProviderHealth((previous) => ({ ...previous, coinbase: responses[1].value }));
      }
      if (responses[2].status === "fulfilled") {
        setProviderHealth((previous) => ({ ...previous, secondary: responses[2].value }));
      }

      const firstFailure = responses.find((response) => response.status === "rejected");
      if (firstFailure && firstFailure.status === "rejected") {
        setError(firstFailure.reason?.message || "Unable to reach the backend.");
      }
    }

    loadHealth();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    window.clearTimeout(pollTimeoutRef.current);
    setEvents([]);
    setCurrent(null);
    setError("");

    const selected = MODE_CONFIG[mode];

    if (isLiveMode && pollingPaused) {
      return () => {
        cancelled = true;
        window.clearTimeout(pollTimeoutRef.current);
      };
    }

    async function poll() {
      try {
        const payload = await selected.fetchStatus();
        if (cancelled) {
          return;
        }

        if (mode !== "simulation") {
          setProviderHealth((previous) => ({
            ...previous,
            [mode]: {
              enabled: payload.enabled,
              provider: payload.provider,
              product_id: payload.product_id,
              connection_status: payload.connection_status,
              model_ready: payload.model_ready,
              last_error: payload.last_error,
              last_update_at: payload.last_update_at,
            },
          }));
        }

        const next = normalizeModePayload(mode, payload);
        if (next) {
          setCurrent(next);
          setEvents((previous) => [...previous, next].slice(-220));
        }
        setError("");
      } catch (nextError) {
        if (!cancelled) {
          setError(nextError.message);
        }
      } finally {
        if (!cancelled) {
          pollTimeoutRef.current = window.setTimeout(poll, selected.pollMs);
        }
      }
    }

    poll();

    return () => {
      cancelled = true;
      window.clearTimeout(pollTimeoutRef.current);
    };
  }, [mode, pollingPaused, isLiveMode]);

  async function handleReset() {
    if (mode === "simulation") {
      await resetStream();
    }
    setEvents([]);
    setCurrent(null);
    setError("");
    setAlertPopup(null);
    activeAlertIdRef.current = "";
  }

  const activeHealth = mode === "simulation" ? null : providerHealth[mode];

  return (
    <main className="terminal-shell">
      <section className="topbar">
        <div className="title-block">
          <div className="title-chip">AI HFT Manipulation Detector</div>
          <h1>Live Market Surveillance Desk</h1>
          <p className="subcopy">
            Simulation mode replays stored real market data. Live modes score exchange prints directly as they arrive.
          </p>
        </div>

        <div className="topbar-actions">
          <div className="status-badge">
            <span className={`status-dot ${signalClass(current?.signal)}`} />
            <div>
              <strong>{backendHealth?.status || "connecting"}</strong>
              <small>{isLiveMode && pollingPaused ? "Polling paused" : feedSummary(mode, activeHealth)}</small>
            </div>
          </div>
          {isLiveMode ? (
            <button
              type="button"
              className={pollingPaused ? "ghost-button active-toggle" : "ghost-button"}
              onClick={() => setPollingPaused((previous) => !previous)}
            >
              {pollingPaused ? "Resume Feed" : "Pause Feed"}
            </button>
          ) : null}
          <button type="button" className="ghost-button" onClick={handleReset}>
            {mode === "simulation" ? "Restart Simulation" : "Clear Tape"}
          </button>
        </div>
      </section>

      {current && (current.confirmed_simulation_case || current.signal === "HIGH_RISK") ? (
        <section className="alert-banner">
          <div>
            <p className="section-kicker">Alert Warning</p>
            <h2>{alertHeadline(current)}</h2>
          </div>
          <p>{detectionNote(current)}</p>
        </section>
      ) : null}

      {alertPopup ? (
        <section className="alert-modal-backdrop" role="dialog" aria-modal="false">
          <div className="alert-modal">
            <div className="alert-modal-glow" />
            <p className="alert-modal-kicker">Critical Warning</p>
            <h2>{alertHeadline(alertPopup)}</h2>
            <p className="alert-modal-copy">{detectionNote(alertPopup)}</p>
            <div className="alert-modal-grid">
              <div>
                <span>Signal</span>
                <strong>{formatSignal(alertPopup.signal)}</strong>
              </div>
              <div>
                <span>Market</span>
                <strong>{alertPopup.product_id || "Replay"}</strong>
              </div>
              <div>
                <span>Price</span>
                <strong>{formatPrice(alertPopup.price)}</strong>
              </div>
              <div>
                <span>Volume</span>
                <strong>{formatVolume(alertPopup.volume)}</strong>
              </div>
            </div>
            <div className="alert-modal-tags">
              <span className="alert-tag">Real-Risk Visual</span>
              <span className="alert-tag">{alertPopup.scenario_label || "High-Risk anomaly"}</span>
              <span className="alert-tag">{formatTimestamp(alertPopup.timestamp)}</span>
            </div>
            <button
              type="button"
              className="alert-dismiss"
              onClick={() => {
                setAlertPopup(null);
              }}
            >
              Dismiss Alert
            </button>
          </div>
        </section>
      ) : null}

      <section className="mode-strip">
        {Object.entries(MODE_CONFIG).map(([key, value]) => (
          <button
            key={key}
            type="button"
            className={mode === key ? "mode-tab active" : "mode-tab"}
            onClick={() => setMode(key)}
          >
            <span>{value.label}</span>
            <small>{value.subtitle}</small>
          </button>
        ))}
      </section>

      <section className="metric-grid">
        <article className="metric-card">
          <span className="metric-label">Signal</span>
          <strong className={`signal-value ${signalClass(current?.signal)}`}>
            {current ? formatSignal(current.signal) : "Waiting"}
          </strong>
          <small>{detectionNote(current)}</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Last Price</span>
          <strong>{formatPrice(current?.price)}</strong>
          <small>{current?.product_id || "Historical replay"}</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Anomaly Score</span>
          <strong>{formatScore(current?.anomaly_score)}</strong>
          <small>{formatTimestamp(current?.timestamp)}</small>
        </article>
        <article className="metric-card">
          <span className="metric-label">Bid / Ask Spread</span>
          <strong>{spreadLabel(current)}</strong>
          <small>{mode === "simulation" ? "Unavailable in replay mode" : "Computed from live top of book"}</small>
        </article>
      </section>

      <section className="main-grid">
        <section className="chart-card">
          <div className="section-head">
            <div>
              <p className="section-kicker">Market View</p>
              <h2>{MODE_CONFIG[mode].label}</h2>
            </div>
            <div className="chart-meta">
              <span>{formatProvider(current?.provider || activeHealth?.provider)}</span>
              <span>{formatTimestamp(current?.timestamp || activeHealth?.last_update_at)}</span>
            </div>
          </div>
          <MarketChart events={events} mode={mode} />
        </section>

        <aside className="side-panel">
          <section className="side-card">
            <div className="section-head compact">
              <div>
                <p className="section-kicker">Feed State</p>
                <h3>Connection</h3>
              </div>
            </div>
            <div className="detail-row">
              <span>Mode</span>
              <strong>{MODE_CONFIG[mode].label}</strong>
            </div>
            <div className="detail-row">
              <span>Provider</span>
              <strong>{formatProvider(current?.provider || activeHealth?.provider)}</strong>
            </div>
            <div className="detail-row">
              <span>Status</span>
              <strong>{isLiveMode && pollingPaused ? "Polling paused" : feedSummary(mode, activeHealth)}</strong>
            </div>
            <div className="detail-row">
              <span>Scenario</span>
              <strong>{current?.scenario_label || "Live flow"}</strong>
            </div>
            <div className="detail-row">
              <span>Volume</span>
              <strong>{formatVolume(current?.volume)}</strong>
            </div>
            <div className="detail-row">
              <span>24h Volume</span>
              <strong>{formatVolume(current?.volume_24h)}</strong>
            </div>
          </section>

          <section className="side-card">
            <div className="section-head compact">
              <div>
                <p className="section-kicker">Model View</p>
                <h3>Interpretation</h3>
              </div>
            </div>
            <p className="note-copy">{detectionNote(current)}</p>
          </section>

          {error ? (
            <section className="side-card side-error">
              <div className="section-head compact">
                <div>
                  <p className="section-kicker">Attention</p>
                  <h3>Connection Error</h3>
                </div>
              </div>
              <p className="note-copy">{error}</p>
            </section>
          ) : null}
        </aside>
      </section>

      <section className="table-card">
        <div className="section-head">
          <div>
            <p className="section-kicker">Event Tape</p>
            <h2>Recent Prints</h2>
          </div>
          <div className="chart-meta">
            <span>{MODE_CONFIG[mode].label}</span>
          </div>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Market</th>
                <th>Price</th>
                <th>Volume</th>
                <th>Score</th>
                <th>Signal</th>
                <th>Context</th>
              </tr>
            </thead>
            <tbody>
              {[...events].reverse().slice(0, 24).map((event, index) => (
                <tr key={`${event.timestamp}-${event.trade_id || event.price}-${index}`}>
                  <td>{formatTimestamp(event.timestamp)}</td>
                  <td>{event.product_id || "Replay"}</td>
                  <td>{formatPrice(event.price)}</td>
                  <td>{formatVolume(event.volume)}</td>
                  <td>{formatScore(event.anomaly_score)}</td>
                  <td>
                    <span className={`signal-chip ${signalClass(event.signal)}`}>
                      {formatSignal(event.signal)}
                    </span>
                  </td>
                  <td>{event.scenario_label || event.manipulation_tag || "Baseline flow"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}

export default App;
