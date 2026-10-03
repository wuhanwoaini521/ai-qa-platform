import React from 'react';

export interface TrendPoint {
  label: string;
  value: number;
}

interface TrendChartProps {
  points: TrendPoint[];
  /** Formats axis values. */
  format?: (value: number) => string;
  height?: number;
  ariaLabel: string;
}

const GRID_TICKS = 4;

/**
 * Minimal SVG trend line: barely-there gridlines, a hairline stroke and a soft area fill.
 * Dependency-free so charts keep the same visual weight as the rest of the UI.
 */
export const TrendChart: React.FC<TrendChartProps> = ({
  points,
  format = (value) => String(value),
  height = 200,
  ariaLabel,
}) => {
  if (points.length < 2) {
    return null;
  }

  const width = 640;
  const padX = 6;
  const padTop = 16;
  const padBottom = 28;
  const padLeft = 34;

  const values = points.map((point) => point.value);
  const rawMax = Math.max(...values);
  const rawMin = Math.min(...values);
  const span = rawMax - rawMin;
  const step = span > GRID_TICKS ? Math.ceil(span / GRID_TICKS) : Math.max(span / GRID_TICKS, 0.1);
  const max = rawMax + span * 0.08;
  const min = Math.max(0, Math.floor((rawMin - span * 0.08) / step) * step);

  const plotW = width - padX * 2 - padLeft;
  const plotH = height - padTop - padBottom;
  const x = (index: number) =>
    padLeft + (index / (points.length - 1)) * plotW;
  const y = (value: number) => padTop + plotH - ((value - min) / (max - min || 1)) * plotH;

  const line = points
    .map(
      (point, index) =>
        `${index === 0 ? 'M' : 'L'}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`,
    )
    .join(' ');
  const baseline = (padTop + plotH).toFixed(1);
  const area = `${line} L${x(points.length - 1).toFixed(1)},${baseline} L${x(0).toFixed(1)},${baseline} Z`;

  const ticks: number[] = [];
  for (let value = min; value <= max + step * 0.001; value += step) {
    ticks.push(Math.round(value * 100) / 100);
  }

  const labelEvery = Math.max(1, Math.ceil(points.length / 5));
  const last = points.length - 1;

  return (
    <svg
      className="trend-chart"
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={ariaLabel}
      preserveAspectRatio="none"
      style={{ height }}
    >
      <path className="trend-chart-area" d={area} />
      <path className="trend-chart-line" d={line} vectorEffect="non-scaling-stroke" />

      {ticks.map((tick) => (
        <line
          key={tick}
          className="trend-chart-grid"
          x1={padLeft}
          x2={width - padX}
          y1={y(tick)}
          y2={y(tick)}
          vectorEffect="non-scaling-stroke"
        />
      ))}

      {ticks.map((tick) => (
        <text key={`t-${tick}`} className="trend-chart-axis" x={padLeft - 8} y={y(tick) + 3} textAnchor="end">
          {format(tick)}
        </text>
      ))}

      {points.map((point, index) =>
        index % labelEvery === 0 || index === last ? (
          <text
            key={`${point.label}-${index}`}
            className="trend-chart-axis"
            x={x(index)}
            y={height - 8}
            textAnchor={index === 0 ? 'start' : index === last ? 'end' : 'middle'}
          >
            {point.label}
          </text>
        ) : null,
      )}

      <circle
        className="trend-chart-cap"
        cx={x(last)}
        cy={y(points[last].value)}
        r={2.5}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
};