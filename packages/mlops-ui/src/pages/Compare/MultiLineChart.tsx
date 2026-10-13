import React from 'react';

// One line per run, over the logged steps. Each series is [step, value].
export default function MultiLineChart({
  series,
  label,
}: {
  series: { name: string; color: string; points: [number, number][] }[];
  label: string;
}) {
  const width = 560;
  const height = 200;
  const pad = 28;
  const all = series.flatMap((s) => s.points);
  if (all.length === 0) {
    return null;
  }
  const xs = all.map((p) => p[0]);
  const ys = all.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const sx = (x: number) =>
    pad + ((x - x0) / (x1 - x0 || 1)) * (width - 2 * pad);
  const sy = (y: number) =>
    height - pad - ((y - y0) / (y1 - y0 || 1)) * (height - 2 * pad);
  return (
    <svg
      className='Compare__chart'
      viewBox={`0 0 ${width} ${height}`}
      role='img'
      aria-label={label}
    >
      {series.map((s) => (
        <g key={s.name}>
          <polyline
            points={s.points.map(([x, y]) => `${sx(x)},${sy(y)}`).join(' ')}
            fill='none'
            stroke={s.color}
            strokeWidth={2}
          />
        </g>
      ))}
      <text x={pad} y={height - 6} className='Compare__axis'>
        {x0}
      </text>
      <text
        x={width - pad}
        y={height - 6}
        textAnchor='end'
        className='Compare__axis'
      >
        {x1}
      </text>
    </svg>
  );
}
