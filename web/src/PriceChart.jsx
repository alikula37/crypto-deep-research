import { useEffect, useMemo, useRef, useState } from "react";
import { formatAxisDate, formatDateTime, num, pct, price } from "./format.js";

const TIMEFRAMES = ["15m", "30m", "1h", "4h", "1d", "1w"];
const HEIGHT = 280;
const PADDING = { top: 16, right: 78, bottom: 26, left: 10 };
const TOOLTIP_WIDTH = 176;
const TOOLTIP_HEIGHT = 92;

export default function PriceChart({ coin, defaultTimeframe = "1d" }) {
  const [timeframe, setTimeframe] = useState(defaultTimeframe);
  const [candles, setCandles] = useState([]);
  const [source, setSource] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [hoverIndex, setHoverIndex] = useState(null);
  const containerRef = useRef(null);
  const [width, setWidth] = useState(760);

  useEffect(() => {
    if (!coin) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    fetch(`/api/ohlcv/${encodeURIComponent(coin)}?timeframe=${timeframe}&limit=300`)
      .then((response) => {
        if (!response.ok) throw new Error("Grafik verisi alınamadı");
        return response.json();
      })
      .then((data) => {
        if (cancelled) return;
        setCandles(data.candles || []);
        setSource(data.source || "");
      })
      .catch((err) => !cancelled && setError(err.message))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [coin, timeframe]);

  useEffect(() => {
    const element = containerRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const nextWidth = Math.max(320, entries[0].contentRect.width);
      setWidth(nextWidth);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const view = useMemo(() => {
    if (!candles.length) return null;
    const plotWidth = width - PADDING.left - PADDING.right;
    const plotHeight = HEIGHT - PADDING.top - PADDING.bottom;
    const highs = candles.map((candle) => candle.h);
    const lows = candles.map((candle) => candle.l);
    const max = Math.max(...highs);
    const min = Math.min(...lows);
    const span = max - min || max * 0.01 || 1;
    const xStep = plotWidth / candles.length;
    const bodyWidth = Math.max(1, xStep * 0.65);
    const x = (index) => PADDING.left + index * xStep + xStep / 2;
    const y = (value) => PADDING.top + ((max - value) / span) * plotHeight;
    const lineOnly = candles.every(
      (candle) => candle.o === candle.h && candle.h === candle.l && candle.l === candle.c
    );
    const linePath = candles
      .map((candle, index) => `${index === 0 ? "M" : "L"}${x(index)},${y(candle.c)}`)
      .join(" ");
    const gridLines = Array.from({ length: 5 }, (_, index) => {
      const value = min + (span * index) / 4;
      return { value, y: y(value) };
    });
    const volumes = candles.map((candle) => candle.v || 0);
    const maxVolume = Math.max(...volumes, 0);
    const hasVolume = maxVolume > 0;
    const volumeHeight = plotHeight * 0.16;
    const yVolume = (value) =>
      HEIGHT - PADDING.bottom - (maxVolume ? (value / maxVolume) * volumeHeight : 0);
    return {
      plotWidth,
      plotHeight,
      max,
      min,
      x,
      y,
      xStep,
      bodyWidth,
      lineOnly,
      linePath,
      gridLines,
      hasVolume,
      yVolume,
    };
  }, [candles, width]);

  const stats = useMemo(() => {
    if (candles.length < 2) return null;
    const first = candles[0].c;
    const last = candles[candles.length - 1].c;
    const change = (last / first - 1) * 100;
    const high = Math.max(...candles.map((candle) => candle.h));
    const low = Math.min(...candles.map((candle) => candle.l));
    return { last, change, high, low };
  }, [candles]);

  const hovered = hoverIndex !== null ? candles[hoverIndex] : null;

  const handleMouseMove = (event) => {
    if (!view || !candles.length) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const xPos = event.clientX - bounds.left - PADDING.left;
    const index = Math.min(candles.length - 1, Math.max(0, Math.floor(xPos / view.xStep)));
    setHoverIndex(index);
  };

  const tooltip = useMemo(() => {
    if (!view || !hovered || hoverIndex === null) return null;
    const tx = Math.min(
      Math.max(PADDING.left, view.x(hoverIndex) + 12),
      width - PADDING.right - TOOLTIP_WIDTH
    );
    const ty = Math.max(PADDING.top, view.y(hovered.c) - TOOLTIP_HEIGHT - 12);
    const change = hovered.o ? (hovered.c / hovered.o - 1) * 100 : 0;
    return { tx, ty, change };
  }, [hovered, hoverIndex, view, width]);

  return (
    <div className="card chart-card" ref={containerRef}>
      <div className="chart-head">
        <div className="chart-title">
          <h3>Fiyat Grafiği</h3>
          {stats && (
            <span className={`chart-change ${stats.change >= 0 ? "up" : "down"}`}>
              {price(stats.last)} ({pct(stats.change, { signed: true })})
            </span>
          )}
        </div>
        <div className="chart-toolbar">
          {TIMEFRAMES.map((value) => (
            <button
              key={value}
              className={`chip ${timeframe === value ? "active" : ""}`}
              onClick={() => setTimeframe(value)}
            >
              {value}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="chart-placeholder">Grafik yükleniyor…</div>}
      {error && <div className="chart-placeholder error-text">{error}</div>}
      {!loading && !error && !candles.length && (
        <div className="chart-placeholder">Bu varlık için grafik verisi bulunamadı.</div>
      )}

      {!loading && !error && view && (
        <svg
          width={width}
          height={HEIGHT}
          className="price-chart"
          onMouseMove={handleMouseMove}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {view.gridLines.map((line) => (
            <g key={line.value}>
              <line
                x1={PADDING.left}
                x2={width - PADDING.right}
                y1={line.y}
                y2={line.y}
                className="chart-grid"
              />
              <text x={width - PADDING.right + 6} y={line.y + 4} className="chart-axis">
                {num(line.value, 3)}
              </text>
            </g>
          ))}

          {view.hasVolume &&
            candles.map((candle, index) => {
              const top = view.yVolume(candle.v || 0);
              return (
                <rect
                  key={`vol-${candle.t}`}
                  x={view.x(index) - view.bodyWidth / 2}
                  y={top}
                  width={view.bodyWidth}
                  height={Math.max(0.5, HEIGHT - PADDING.bottom - top)}
                  className="chart-volume"
                />
              );
            })}

          {view.lineOnly && <path d={view.linePath} className="chart-line" />}

          {!view.lineOnly &&
            candles.map((candle, index) => {
              const rising = candle.c >= candle.o;
              const bodyTop = view.y(Math.max(candle.o, candle.c));
              const bodyBottom = view.y(Math.min(candle.o, candle.c));
              const bodyHeight = Math.max(1, bodyBottom - bodyTop);
              return (
                <g key={candle.t} className={rising ? "candle-up" : "candle-down"}>
                  <line
                    x1={view.x(index)}
                    x2={view.x(index)}
                    y1={view.y(candle.h)}
                    y2={view.y(candle.l)}
                    className="candle-wick"
                  />
                  <rect
                    x={view.x(index) - view.bodyWidth / 2}
                    y={bodyTop}
                    width={view.bodyWidth}
                    height={bodyHeight}
                    className="candle-body"
                  />
                </g>
              );
            })}

          {[0, Math.floor(candles.length / 3), Math.floor((2 * candles.length) / 3), candles.length - 1]
            .filter((value, index, array) => array.indexOf(value) === index)
            .map((index) => (
              <text
                key={index}
                x={view.x(index)}
                y={HEIGHT - 8}
                className="chart-axis"
                textAnchor="middle"
              >
                {formatAxisDate(candles[index].t, timeframe)}
              </text>
            ))}

          {hovered && hoverIndex !== null && (
            <g>
              <line
                x1={view.x(hoverIndex)}
                x2={view.x(hoverIndex)}
                y1={PADDING.top}
                y2={HEIGHT - PADDING.bottom}
                className="chart-crosshair"
              />
              <line
                x1={PADDING.left}
                x2={width - PADDING.right}
                y1={view.y(hovered.c)}
                y2={view.y(hovered.c)}
                className="chart-crosshair"
              />
              <circle cx={view.x(hoverIndex)} cy={view.y(hovered.c)} r={3.5} className="chart-dot" />
            </g>
          )}

          {tooltip && hovered && (
            <g>
              <rect
                x={tooltip.tx}
                y={tooltip.ty}
                width={TOOLTIP_WIDTH}
                height={TOOLTIP_HEIGHT}
                rx={8}
                className="chart-tooltip-box"
              />
              <text x={tooltip.tx + 10} y={tooltip.ty + 17} className="chart-tooltip-text">
                {formatDateTime(hovered.t)}
              </text>
              <text x={tooltip.tx + 10} y={tooltip.ty + 34} className="chart-tooltip-text">
                A {price(hovered.o)} · Y {price(hovered.h)}
              </text>
              <text x={tooltip.tx + 10} y={tooltip.ty + 51} className="chart-tooltip-text">
                D {price(hovered.l)} · K {price(hovered.c)}
              </text>
              <text
                x={tooltip.tx + 10}
                y={tooltip.ty + 68}
                className={`chart-tooltip-text ${tooltip.change >= 0 ? "up" : "down"}`}
              >
                Değişim {pct(tooltip.change, { signed: true })}
              </text>
              {hovered.v ? (
                <text x={tooltip.tx + 10} y={tooltip.ty + 85} className="chart-tooltip-text">
                  Hacim {num(hovered.v, 4)}
                </text>
              ) : null}
            </g>
          )}
        </svg>
      )}

      <div className="chart-footer">
        {hovered ? (
          <span>
            {formatDateTime(hovered.t)} · A {price(hovered.o)} · Y {price(hovered.h)} · D {price(hovered.l)} · K{" "}
            {price(hovered.c)}
            {hovered.v ? ` · Hacim ${num(hovered.v, 4)}` : ""}
          </span>
        ) : (
          <span className="muted">
            {source ? `Kaynak: ${source}` : ""}{" "}
            {stats ? `· En yüksek ${price(stats.high)} · En düşük ${price(stats.low)}` : ""}
          </span>
        )}
      </div>
    </div>
  );
}
