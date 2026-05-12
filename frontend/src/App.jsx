import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import {
  ComposedChart, Line, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine, Area, AreaChart,
} from "recharts";
import {
  getCoinbaseLiveHealth, getCoinbaseLiveStatus, getHealth,
  getSecondaryLiveHealth, getSecondaryLiveStatus,
  resetStream, streamNext,
} from "./api";

// ---- Config ----
const MODES = {
  simulation: { label: "Sim", subtitle: "Historical Replay", fetch: streamNext, color: "#00e5ff" },
  coinbase:   { label: "BTC",  subtitle: "Coinbase BTC-USD", fetch: getCoinbaseLiveStatus, color: "#10b981" },
  secondary:  { label: "ETH",  subtitle: "Coinbase ETH-USD", fetch: getSecondaryLiveStatus, color: "#a855f7" },
};

const MAX_CHART_POINTS = 150;

// ---- Helpers ----
const fmtPrice  = v => v != null ? `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}` : "--";
const fmtVol    = v => v != null ? Number(v).toLocaleString(undefined, { minimumFractionDigits: 4, maximumFractionDigits: 4 }) : "--";
const fmtScore  = v => v != null ? Number(v).toFixed(3) : "--";
const fmtTime   = v => v ? new Date(v).toLocaleTimeString([], { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "--";

const sigClass = s => ({ normal: "normal", suspicious: "suspicious", high_risk: "high_risk" }[s?.toLowerCase()] || "normal");
const sigLabel = s => s ? (s === "HIGH_RISK" ? "HIGH RISK" : s) : "NORMAL";
const cardTone = s => {
  const c = sigClass(s);
  return c === "high_risk" ? "signal-red" : c === "suspicious" ? "signal-amber" : "signal-green";
};

const sparklineTone = s => {
  const c = sigClass(s?.signal);
  return c === "high_risk" ? "red" : c === "suspicious" ? "amber" : "green";
};

function CustomTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={{
      background: "#161f2e", border: "1px solid #374151", borderRadius: 8,
      padding: "10px 14px", fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
      boxShadow: "0 6px 24px rgba(0,0,0,0.5)",
    }}>
      <p style={{ color: "#94a3b8", margin: 0, marginBottom: 6 }}>{label}</p>
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color || "#f0f5ff", margin: "2px 0" }}>
          {p.name}: <strong>{p.name === "Volume" ? fmtVol(p.value) : fmtPrice(p.value)}</strong>
        </p>
      ))}
    </div>
  );
}

// ---- Sparkline ----
function Sparkline({ data, dataKey, color }) {
  return (
    <ResponsiveContainer width="100%" height={60}>
      <AreaChart data={data}>
        <defs>
          <linearGradient id={`spark-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area type="monotone" dataKey={dataKey} stroke={color} strokeWidth={1.5}
          fill={`url(#spark-${dataKey})`} dot={false} isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

// ---- Main App ----
export default function App() {
  const [backendHealth, setBackendHealth] = useState(null);
  const [providerHealth, setProviderHealth] = useState({});
  const [mode, setMode] = useState("simulation");
  const [current, setCurrent] = useState(null);
  const [events, setEvents] = useState([]);
  const [chartData, setChartData] = useState([]);
  const [error, setError] = useState("");
  const pollRef = useRef(null);

  const modeCfg = MODES[mode];

  // health on mount
  useEffect(() => {
    (async () => {
      try {
        const [h, cb, sec] = await Promise.allSettled([
          getHealth(),
          getCoinbaseLiveHealth(),
          getSecondaryLiveHealth(),
        ]);
        setBackendHealth(h.status === "fulfilled" ? h.value : null);
        setProviderHealth({
          coinbase: cb.status === "fulfilled" ? cb.value : null,
          secondary: sec.status === "fulfilled" ? sec.value : null,
        });
      } catch (e) { setError(e.message); }
    })();
  }, []);

  // polling
  useEffect(() => {
    let cancelled = false;
    if (pollRef.current) clearTimeout(pollRef.current);

    const poll = async () => {
      try {
        const payload = await modeCfg.fetch();
        if (cancelled) return;
        const event = mode === "simulation" ? payload : payload?.latest_event;
        if (event) {
          setCurrent(event);
          setEvents(prev => [...prev, event].slice(-500));
          setChartData(prev => {
            const next = [...prev, {
              time: fmtTime(event.timestamp),
              price: event.price,
              volume: event.volume,
              score: event.anomaly_score,
              isAnomaly: event.is_anomaly,
              signalClass: sigClass(event.signal),
            }];
            return next.slice(-MAX_CHART_POINTS);
          });
        }
        setError("");
      } catch (e) { if (!cancelled) setError(e.message); }
      if (!cancelled) {
        pollRef.current = setTimeout(poll, mode === "simulation" ? 120 : 500);
      }
    };
    poll();
    return () => {
      cancelled = true;
      if (pollRef.current) clearTimeout(pollRef.current);
    };
  }, [mode, modeCfg]);

  const handleReset = useCallback(async () => {
    setEvents([]);
    setChartData([]);
    setCurrent(null);
    if (mode === "simulation") await resetStream();
  }, [mode]);

  const activeHealth = providerHealth[mode] || backendHealth;
  const showAlert = current?.signal === "HIGH_RISK";
  const sparklinePrices = useMemo(() => chartData.slice(-50), [chartData]);

  const latestAnomalyIdx = useMemo(() => {
    const indices = [];
    chartData.forEach((d, i) => { if (d.isAnomaly) indices.push(i); });
    return indices;
  }, [chartData]);

  // ---- Render ----
  return (
    <div className="dashboard">

      {/* HEADER */}
      <header className="header">
        <div className="logo-section">
          <div className="logo-icon">{">_"}</div>
          <div className="logo-text">
            <span className="logo-title">HFT Detector</span>
            <span className="logo-subtitle">Market Manipulation AI</span>
          </div>
        </div>

        <div className="mode-selector">
          {Object.entries(MODES).map(([key, cfg]) => (
            <button key={key}
              className={`mode-chip${mode === key ? " active" : ""}`}
              onClick={() => { setMode(key); setCurrent(null); }}>
              {cfg.label}
            </button>
          ))}
        </div>

        <div className="status-pill">
          <div className={`status-dot ${current ? sigClass(current.signal) : "normal"}`} />
          <span>{activeHealth?.connection_status || "idle"}</span>
        </div>
      </header>

      {/* ERROR */}
      {error && (
        <div className="error-banner">
          <span style={{ fontSize: 18 }}>&#x26A0;</span> {error}
        </div>
      )}

      {/* METRICS */}
      <div className="metrics-grid">
        <div className={`metric-card ${cardTone(current?.signal)}`}>
          <div className="metric-label">Signal</div>
          <div className={`metric-value ${sparklineTone(current)}`}>
            {sigLabel(current?.signal)}
          </div>
          <div className="metric-subtitle">
            {current ? (current.is_anomaly ? "Anomaly detected" : "Market normal") : "Waiting..."}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Price {current?.product_id ? `(${current.product_id})` : ""}</div>
          <div className="metric-value">{fmtPrice(current?.price)}</div>
          <div className="metric-subtitle">{fmtTime(current?.timestamp)}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Anomaly Score</div>
          <div className="metric-value">{fmtScore(current?.anomaly_score)}</div>
          <div className="metric-subtitle">
            z-score: {fmtScore(current?.price_zscore)} &middot; vol ratio: {fmtScore(current?.volume_spike_ratio)}
          </div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Volume</div>
          <div className="metric-value">{fmtVol(current?.volume)}</div>
          <div className="metric-subtitle">
            {current?.volume_24h ? `24h: ${fmtVol(current.volume_24h)}` : `Provider: ${modeCfg.subtitle}`}
          </div>
        </div>
      </div>

      {/* ALERT BANNER */}
      {showAlert && (
        <div className="alert-banner high_risk">
          <div className="alert-icon">!</div>
          <div className="alert-text">
            High Risk Alert &mdash; Extreme price/volume deviation detected. Anomaly score: {fmtScore(current?.anomaly_score)}
          </div>
        </div>
      )}

      {/* CHART */}
      <div className="chart-section">
        <div className="chart-header">
          <div className="chart-header-left">
            <div>
              <div className="chart-title">{modeCfg.label} &mdash; Live Feed</div>
              <div className="chart-subtitle">{modeCfg.subtitle} &middot; {chartData.length} points</div>
            </div>
          </div>
          <div className="chart-legend">
            <div className="legend-item"><div className="legend-dot" style={{ background: modeCfg.color }} /> Price</div>
            <div className="legend-item"><div className="legend-dot" style={{ background: "#64748b" }} /> Volume</div>
            <div className="legend-item"><div className="legend-dot" style={{ background: "#ef4444" }} /> Anomaly</div>
          </div>
        </div>

        {/* Sparkline */}
        <div className="chart-sparkline">
          <Sparkline data={sparklinePrices} dataKey="price" color={modeCfg.color} />
        </div>

        {/* Main Chart */}
        <div className="chart-container">
          {chartData.length > 1 ? (
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={chartData} margin={{ top: 5, right: 5, bottom: 5, left: 0 }}>
                <defs>
                  <linearGradient id="priceGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor={modeCfg.color} stopOpacity={0.25} />
                    <stop offset="100%" stopColor={modeCfg.color} stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
                <XAxis dataKey="time" tick={{ fontSize: 10 }} />
                <YAxis yAxisId="price" orientation="right" tick={{ fontSize: 10 }}
                  domain={["auto", "auto"]}
                  tickFormatter={v => `$${v?.toFixed(0)}`} />
                <YAxis yAxisId="volume" hide domain={[0, "auto"]} />
                <Tooltip content={<CustomTooltip />} />
                <Area yAxisId="price" type="monotone" dataKey="price" stroke={modeCfg.color}
                  strokeWidth={2} fill="url(#priceGrad)" dot={false} isAnimationActive={false} />
                <Bar yAxisId="volume" dataKey="volume" fill="#374151" opacity={0.6}
                  isAnimationActive={false} />
                {latestAnomalyIdx.map(idx => (
                  <ReferenceLine key={idx} yAxisId="price" x={chartData[idx]?.time}
                    stroke="#ef4444" strokeWidth={2} strokeDasharray="4 4"
                    strokeOpacity={0.7} />
                ))}
              </ComposedChart>
            </ResponsiveContainer>
          ) : (
            <div className="no-data">
              <div className="no-data-icon">~</div>
              <div className="no-data-text">Waiting for market data...</div>
              <div className="no-data-sub">Press play or switch to a live feed</div>
            </div>
          )}
        </div>
      </div>

      {/* EVENT TAPE */}
      <div className="tape-section">
        <div className="tape-header">
          <div className="tape-title">
            Event Tape
            <span className="tape-count">{events.length}</span>
          </div>
          <button className="tape-reset" onClick={handleReset}>Reset</button>
        </div>
        <div className="tape-table-container">
          <table className="tape-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Signal</th>
                <th>Price</th>
                <th>Volume</th>
                <th>Score</th>
                <th>z-Score</th>
                <th>Vol Ratio</th>
              </tr>
            </thead>
            <tbody>
              {events.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: "center", padding: 40, color: "var(--text-muted)" }}>
                    No events yet
                  </td>
                </tr>
              ) : (
                events.slice(-50).reverse().map((e, i) => (
                  <tr key={i}>
                    <td>{fmtTime(e.timestamp)}</td>
                    <td><span className={`signal-badge ${sigClass(e.signal)}`}>{sigLabel(e.signal)}</span></td>
                    <td style={{ color: "#f0f5ff" }}>{fmtPrice(e.price)}</td>
                    <td>{fmtVol(e.volume)}</td>
                    <td>{fmtScore(e.anomaly_score)}</td>
                    <td>{fmtScore(e.price_zscore)}</td>
                    <td>{fmtScore(e.volume_spike_ratio)}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}