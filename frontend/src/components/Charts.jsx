import React from "react";
import { Chart as ChartJS, CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend } from "chart.js";
import { Chart } from "react-chartjs-2";

ChartJS.register(CategoryScale, LinearScale, BarElement, LineElement, PointElement, Tooltip, Legend);

const RED = "#c8412f";
const RED_LIGHT = "rgba(200,65,47,0.28)";
const BLUE = "#1f5f99";
const GREY = "#6b6b6b";

const baseOpts = (yTitle, extra = {}) => ({
  responsive: true,
  maintainAspectRatio: false,
  interaction: { mode: "index", intersect: false },
  plugins: { legend: { position: "bottom", labels: { boxWidth: 12 } } },
  scales: { y: { beginAtZero: true, title: { display: true, text: yTitle }, ...extra }, x: { ticks: { maxTicksLimit: 12 } } },
});

export function FrequencyChart({ annual, label }) {
  const labels = annual.map((r) => r.year);
  const data = {
    labels,
    datasets: [
      {
        type: "bar",
        label: `${label} days per year`,
        data: annual.map((r) => r.hazard_days),
        backgroundColor: annual.map((r) => (r.complete ? RED : RED_LIGHT)),
        order: 3,
      },
      { type: "line", label: "5-year rolling mean", data: annual.map((r) => r.rolling_5y_days), borderColor: BLUE, backgroundColor: BLUE, pointRadius: 0, borderWidth: 2.5, tension: 0.25, spanGaps: false, order: 1 },
      { type: "line", label: "Linear trend (OLS)", data: annual.map((r) => r.trend_fit ?? null), borderColor: "#1a1a1a", borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5, order: 2 },
    ],
  };
  return <div className="chart-box"><Chart type="bar" data={data} options={baseOpts("Days per year")} /></div>;
}

export function EventsChart({ annual, unit }) {
  const labels = annual.map((r) => r.year);
  const data = {
    labels,
    datasets: [
      { type: "bar", label: "Events per year", data: annual.map((r) => r.event_count), backgroundColor: annual.map((r) => (r.complete ? "#d98e3f" : "rgba(217,142,63,0.3)")), yAxisID: "y" },
      { type: "line", label: "Longest event (days)", data: annual.map((r) => r.max_duration), borderColor: GREY, backgroundColor: GREY, pointRadius: 2, borderWidth: 1.5, yAxisID: "y1" },
    ],
  };
  const o = baseOpts("Events per year");
  o.scales.y1 = { position: "right", beginAtZero: true, grid: { drawOnChartArea: false }, title: { display: true, text: "Longest event (days)" } };
  return <div className="chart-box"><Chart type="bar" data={data} options={o} /></div>;
}

export function IntensityChart({ annual, unit, excessUnit }) {
  const labels = annual.map((r) => r.year);
  const data = {
    labels,
    datasets: [
      { type: "line", label: `Mean intensity (${excessUnit})`, data: annual.map((r) => (r.event_count ? r.mean_intensity : null)), borderColor: RED, backgroundColor: RED, pointRadius: 3, borderWidth: 1.5, spanGaps: true },
    ],
  };
  return <div className="chart-box"><Chart type="line" data={data} options={baseOpts(`Mean excess over threshold (${unit})`)} /></div>;
}
