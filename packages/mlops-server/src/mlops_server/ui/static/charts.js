import { colorFor } from "./lib.js";

export function lineChart(canvas, series, title) {
  return new window.Chart(canvas, {
    type: "line",
    data: {
      datasets: series.map((s, i) => ({
        label: s.label, data: s.points.map(([x, y]) => ({ x, y })),
        borderColor: s.color || colorFor(i), backgroundColor: s.color || colorFor(i),
        borderWidth: 1.5, pointRadius: 0, tension: 0,
      })),
    },
    options: {
      animation: false, parsing: false, responsive: true, maintainAspectRatio: false,
      scales: { x: { type: "linear", title: { display: true, text: "step" } } },
      plugins: { title: { display: Boolean(title), text: title }, legend: { position: "bottom" } },
    },
  });
}
