import { useMemo, useRef, useState } from "react";
import { formatDateTime, money, score as fmtScore } from "./format.js";

const WIDTH = 720;
const HEIGHT = 236;
const PAD = { top: 16, right: 58, bottom: 30, left: 42 };

export default function ScoreHistoryChart({ runs }) {
  const svgRef = useRef(null);
  const [hover, setHover] = useState(null);

  const data = useMemo(
    () => runs.filter((run) => run.weighted_score !== null && run.weighted_score !== undefined),
    [runs]
  );

  if (data.length < 2) return null;

  const innerW = WIDTH - PAD.left - PAD.right;
  const innerH = HEIGHT - PAD.top - PAD.bottom;
  const xAt = (index) => PAD.left + (index / (data.length - 1)) * innerW;
  const yScore = (value) => PAD.top + (1 - (Math.max(-1, Math.min(1, value)) + 1) / 2) * innerH;
  const yProb = (value) => PAD.top + (1 - Math.max(0, Math.min(100, value)) / 100) * innerH;

  const scorePath = data
    .map((run, index) => `${index === 0 ? "M" : "L"}${xAt(index).toFixed(1)},${yScore(run.weighted_score).toFixed(1)}`)
    .join(" ");
  const probPath = data
    .map((run, index) => {
      const probability = run.up_probability ?? 50;
      return `${index === 0 ? "M" : "L"}${xAt(index).toFixed(1)},${yProb(probability).toFixed(1)}`;
    })
    .join(" ");

  const handleMove = (event) => {
    if (!svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const px = ((event.clientX - rect.left) / rect.width) * WIDTH;
    const ratio = (px - PAD.left) / innerW;
    const index = Math.round(ratio * (data.length - 1));
    setHover(Math.max(0, Math.min(data.length - 1, index)));
  };

  const active = hover !== null ? data[hover] : null;
  const first = data[0];
  const last = data[data.length - 1];

  const tooltipWidth = 208;
  const tooltipHeight = 84;
  const activeX = hover !== null ? xAt(hover) : 0;
  const activeY = active ? yScore(active.weighted_score) : 0;
  const tooltipX = Math.min(
    Math.max(activeX - tooltipWidth / 2, PAD.left),
    WIDTH - PAD.right - tooltipWidth
  );
  const tooltipY = Math.max(PAD.top, Math.min(activeY - tooltipHeight - 12, HEIGHT - PAD.bottom - tooltipHeight));

  return (
    <div className="history-chart">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label="Skor geçmişi grafiği"
        onMouseMove={handleMove}
        onMouseLeave={() => setHover(null)}
      >
        {[-1, -0.5, 0, 0.5, 1].map((value) => (
          <g key={value}>
            <line
              x1={PAD.left}
              x2={WIDTH - PAD.right}
              y1={yScore(value)}
              y2={yScore(value)}
              className={value === 0 ? "history-zero" : "history-grid"}
            />
            <text x={PAD.left - 8} y={yScore(value) + 4} textAnchor="end" className="history-axis">
              {value > 0 ? `+${value}` : value}
            </text>
          </g>
        ))}
        {[0, 50, 100].map((value) => (
          <text
            key={`p${value}`}
            x={WIDTH - PAD.right + 8}
            y={yProb(value) + 4}
            textAnchor="start"
            className="history-axis"
          >
            %{value}
          </text>
        ))}

        <path d={probPath} className="history-prob-line" />
        <path d={scorePath} className="history-score-line" />

        {data.map((run, index) => (
          <circle
            key={run.run_id}
            cx={xAt(index)}
            cy={yScore(run.weighted_score)}
            r={hover === index ? 5.5 : 3.2}
            className={run.weighted_score >= 0 ? "history-dot positive" : "history-dot negative"}
          />
        ))}

        <text x={PAD.left} y={HEIGHT - 8} className="history-axis">
          {formatDateTime(first.created_at * 1000)}
        </text>
        <text x={WIDTH - PAD.right} y={HEIGHT - 8} textAnchor="end" className="history-axis">
          {formatDateTime(last.created_at * 1000)}
        </text>

        {active && hover !== null && (
          <g>
            <line
              x1={activeX}
              x2={activeX}
              y1={PAD.top}
              y2={HEIGHT - PAD.bottom}
              className="history-cursor"
            />
            <rect x={tooltipX} y={tooltipY} width={tooltipWidth} height={tooltipHeight} rx={8} className="history-tooltip" />
            <text x={tooltipX + 10} y={tooltipY + 18} className="history-tooltip-title">
              {formatDateTime(active.created_at * 1000)}
            </text>
            <text x={tooltipX + 10} y={tooltipY + 36} className="history-tooltip-text">
              Skor: {fmtScore(active.weighted_score)} · Yükseliş %{(active.up_probability ?? 50).toFixed(1)}
            </text>
            <text x={tooltipX + 10} y={tooltipY + 52} className="history-tooltip-text">
              Fiyat: {money(active.current_price, { exact: true })}
            </text>
            <text x={tooltipX + 10} y={tooltipY + 70} className="history-tooltip-muted">
              {active.timeframe || "1d"} · {data.length} koşu içinde {hover + 1}.
            </text>
          </g>
        )}
      </svg>
      <div className="history-legend">
        <span className="legend-item history-score"><i /> Skor (−1…+1, sol eksen)</span>
        <span className="legend-item history-prob"><i /> Yükseliş olasılığı (%, sağ eksen)</span>
      </div>
    </div>
  );
}
