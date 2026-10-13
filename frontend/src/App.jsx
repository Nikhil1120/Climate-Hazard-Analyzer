import React from "react";
import MapPicker from "./components/MapPicker.jsx";
import Insights from "./components/Insights.jsx";
import { FrequencyChart, EventsChart, IntensityChart } from "./components/Charts.jsx";
import { fetchAnalysis, csvUrl, geocode } from "./api.js";

const THIS_YEAR = new Date().getFullYear();
const DEFAULT_REGION = { kind: "point", lat: 28.6139, lon: 77.209, name: "New Delhi, India" };

export default function App() {
  const [region, setRegion] = React.useState(DEFAULT_REGION);
  const [mode, setMode] = React.useState("point");
  const [opts, setOpts] = React.useState({ hazard: "heatwave", startYear: 1990, endYear: 2020, percentile: 95, minDays: 3, method: "calendar" });
  const [query, setQuery] = React.useState("");
  const [matches, setMatches] = React.useState([]);
  const [searchErr, setSearchErr] = React.useState("");
  const [state, setState] = React.useState({ status: "idle", data: null, error: "" });
  const abortRef = React.useRef(null);

  const set = (k, v) => setOpts((o) => ({ ...o, [k]: v }));

  async function search(e) {
    e.preventDefault();
    setSearchErr("");
    setMatches([]);
    if (query.trim().length < 2) return;
    try {
      const { results } = await geocode(query.trim());
      if (!results.length) setSearchErr("No places found");
      setMatches(results);
    } catch (err) {
      setSearchErr(err.message);
    }
  }

  function pickMatch(m) {
    setRegion({ kind: "point", lat: m.lat, lon: m.lon, name: [m.name, m.admin1, m.country].filter(Boolean).join(", ") });
    setMode("point");
    setMatches([]);
  }

  async function run() {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState({ status: "loading", data: null, error: "" });
    try {
      const data = await fetchAnalysis(region, opts, ctrl.signal);
      setState({ status: "done", data, error: "" });
    } catch (err) {
      if (err.name !== "AbortError") setState({ status: "error", data: null, error: err.message });
    }
  }

  const d = state.data;
  const regionLabel =
    region.kind === "point"
      ? `${region.name || ""} (${region.lat.toFixed(2)}, ${region.lon.toFixed(2)})`
      : `Box ${region.min_lat.toFixed(2)}–${region.max_lat.toFixed(2)}°N, ${region.min_lon.toFixed(2)}–${region.max_lon.toFixed(2)}°E (analysed at its centre)`;

  return (
    <div className="app">
      <header>
        <h1>Climate Hazard Trend Analyzer</h1>
        <p>Historical heatwave frequency, duration and intensity for any location, from ERA5 reanalysis data.</p>
      </header>

      <div className="layout">
        <aside className="panel controls">
          <h2>Region</h2>
          <form onSubmit={search} className="row">
            <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search city or state" maxLength={80} aria-label="Search place" />
            <button type="submit" className="secondary">Search</button>
          </form>
          {searchErr && <p className="error small">{searchErr}</p>}
          {matches.length > 0 && (
            <ul className="matches">
              {matches.map((m, i) => (
                <li key={i}><button type="button" onClick={() => pickMatch(m)}>{[m.name, m.admin1, m.country].filter(Boolean).join(", ")}</button></li>
              ))}
            </ul>
          )}

          <div className="seg" role="group" aria-label="Selection mode">
            <button className={mode === "point" ? "on" : ""} onClick={() => setMode("point")}>Point</button>
            <button className={mode === "box" ? "on" : ""} onClick={() => setMode("box")}>Lat-lon box</button>
          </div>
          <MapPicker
            region={region}
            mode={mode}
            onPoint={(lat, lon) => setRegion({ kind: "point", lat, lon, name: "" })}
            onBox={(min_lat, max_lat, min_lon, max_lon) => setRegion({ kind: "box", min_lat, max_lat, min_lon, max_lon, name: "Custom box" })}
          />
          <p className="small muted">{regionLabel}</p>

          <h2>Hazard & period</h2>
          <label>Hazard
            <select value={opts.hazard} onChange={(e) => set("hazard", e.target.value)}>
              <option value="heatwave">Heatwave</option>
              <option value="heavy_rainfall">Heavy rainfall</option>
            </select>
          </label>
          <div className="row">
            <label>From
              <input type="number" min={1950} max={THIS_YEAR - 1} value={opts.startYear} onChange={(e) => set("startYear", +e.target.value)} />
            </label>
            <label>To
              <input type="number" min={1950} max={THIS_YEAR} value={opts.endYear} onChange={(e) => set("endYear", +e.target.value)} />
            </label>
          </div>
          <div className="row">
            <label>Percentile
              <input type="number" min={80} max={99} step={0.5} value={opts.percentile} onChange={(e) => set("percentile", +e.target.value)} />
            </label>
            {opts.hazard === "heatwave" && (
              <label>Min. days
                <input type="number" min={1} max={14} value={opts.minDays} onChange={(e) => set("minDays", +e.target.value)} />
              </label>
            )}
          </div>
          {opts.hazard === "heatwave" && (
            <label>Threshold method
              <select value={opts.method} onChange={(e) => set("method", e.target.value)}>
                <option value="calendar">Calendar-day percentile (±7 days)</option>
                <option value="fixed">Single percentile of all days</option>
              </select>
            </label>
          )}
          <button className="primary" onClick={run} disabled={state.status === "loading"}>
            {state.status === "loading" ? "Analysing…" : "Analyse"}
          </button>
        </aside>

        <main>
          {state.status === "idle" && <div className="panel empty">Choose a region and period, then press <b>Analyse</b>. The first request for a new area downloads and stores the data (can take 10–30 s); repeats are instant.</div>}
          {state.status === "loading" && <div className="panel empty" role="status">Fetching and analysing data… new locations can take up to 30 s.</div>}
          {state.status === "error" && <div className="panel error" role="alert">{state.error}</div>}
          {d && (
            <>
              <div className="toolbar no-print">
                <h2>{d.region.name} · {d.hazard.label} · {d.range.start_year}–{d.range.end_year}</h2>
                <div>
                  <a className="btn" href={csvUrl(region, opts)}>Download CSV</a>
                  <button className="btn" onClick={() => window.print()}>Save as PDF</button>
                </div>
              </div>
              <Insights data={d} />
              <section className="panel">
                <h3>{d.hazard.label} days per year</h3>
                <FrequencyChart annual={d.annual} label={d.hazard.label} />
                <p className="small muted">Pale bars are years excluded from trend statistics (incomplete data). Dashed line: least-squares fit.</p>
              </section>
              <div className="grid2">
                <section className="panel"><h3>Events and longest duration</h3><EventsChart annual={d.annual} /></section>
                <section className="panel"><h3>Intensity</h3><IntensityChart annual={d.annual} unit={d.hazard.unit} excessUnit={d.hazard.excess_unit} /></section>
              </div>
            </>
          )}
        </main>
      </div>
      <footer className="small muted">Data: Open-Meteo Historical Weather API (ERA5). Map © OpenStreetMap contributors.</footer>
    </div>
  );
}
