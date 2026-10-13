import React from "react";

const fmt = (v, d = 2) => (v === null || v === undefined ? "–" : Number(v).toFixed(d));

export default function Insights({ data }) {
  const t = data.trends?.hazard_days;
  const sig = data.insight.significance;
  const q = data.quality;
  const decade = (x) => (x === null || x === undefined ? "–" : `${x * 10 >= 0 ? "+" : ""}${(x * 10).toFixed(2)}`);
  return (
    <section className="panel">
      <div className={`headline ${sig}`}>
        <span className="badge">{sig === "significant" ? "Significant trend" : sig === "not_significant" ? "Not significant" : sig === "none" ? "No change" : "Insufficient data"}</span>
        <p>{data.insight.headline}</p>
      </div>

      {t && (
        <div className="stats">
          <div><b>{decade(t.mann_kendall.sen_slope)}</b><span>Sen's slope, days / decade</span></div>
          <div><b>{decade(t.ols.slope)}</b><span>OLS slope, days / decade</span></div>
          <div><b>{fmt(t.mann_kendall.p, 3)}</b><span>Mann-Kendall p-value</span></div>
          <div><b>{fmt(t.ols.r2, 2)}</b><span>OLS R²</span></div>
          <div><b>{q.years_used_for_trend}/{q.years_requested}</b><span>years used</span></div>
          {data.trends.mean_tmax && <div><b>{decade(data.trends.mean_tmax.ols.slope)} °C</b><span>mean Tmax / decade</span></div>}
        </div>
      )}

      <h3>How it was defined</h3>
      <p className="muted">
        {data.hazard.label}: {data.hazard.definition}. Threshold:{" "}
        {data.hazard.threshold.type === "calendar-day"
          ? `${data.hazard.threshold.min_c}–${data.hazard.threshold.max_c} °C depending on season`
          : data.hazard.threshold.value_c != null
          ? `${data.hazard.threshold.value_c} °C`
          : data.hazard.threshold.value_mm != null
          ? `${data.hazard.threshold.value_mm} mm/day`
          : "n/a"}
        . Source: {data.meta.source}. Served from: {data.meta.served_from}.
      </p>

      <h3>Data quality</h3>
      <p className="muted">
        {q.rows_received.toLocaleString()} daily records · {q.outliers_removed} implausible values removed · {q.gaps_interpolated} short gaps (≤2 days) interpolated ·{" "}
        {q.missing_days_remaining} days still missing. {q.years_excluded.length > 0 && <>Excluded from trend (incomplete): {q.years_excluded.join(", ")}.</>}
      </p>

      <h3>Caveats</h3>
      <ul className="muted">{data.insight.caveats.map((c, i) => <li key={i}>{c}</li>)}</ul>

      {data.top_events.length > 0 && (
        <>
          <h3>Longest events</h3>
          <table>
            <thead><tr><th>Start</th><th>End</th><th>Days</th><th>Peak ({data.hazard.unit})</th><th>Mean excess</th></tr></thead>
            <tbody>
              {data.top_events.slice(0, 8).map((e, i) => (
                <tr key={i}><td>{e.start}</td><td>{e.end}</td><td>{e.duration}</td><td>{e.peak}</td><td>{e.mean_excess}</td></tr>
              ))}
            </tbody>
          </table>
        </>
      )}
    </section>
  );
}
