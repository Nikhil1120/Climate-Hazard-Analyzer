const BASE = import.meta.env.VITE_API_URL || "";

export function buildParams(region, opts) {
  const p = new URLSearchParams();
  if (region.kind === "box") {
    p.set("min_lat", region.min_lat.toFixed(4));
    p.set("max_lat", region.max_lat.toFixed(4));
    p.set("min_lon", region.min_lon.toFixed(4));
    p.set("max_lon", region.max_lon.toFixed(4));
  } else {
    p.set("lat", region.lat.toFixed(4));
    p.set("lon", region.lon.toFixed(4));
  }
  if (region.name) p.set("name", region.name);
  p.set("start_year", opts.startYear);
  p.set("end_year", opts.endYear);
  p.set("hazard", opts.hazard);
  p.set("percentile", opts.percentile);
  p.set("min_days", opts.hazard === "heavy_rainfall" ? 1 : opts.minDays);
  p.set("method", opts.method);
  return p;
}

async function getJson(url, signal) {
  const r = await fetch(url, { signal });
  if (!r.ok) {
    let msg = `Request failed (${r.status})`;
    try {
      const body = await r.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d) => `${d.loc?.slice(-1)[0]}: ${d.msg}`).join("; ");
    } catch {}
    throw new Error(msg);
  }
  return r.json();
}

export const fetchAnalysis = (region, opts, signal) => getJson(`${BASE}/api/analysis?${buildParams(region, opts)}`, signal);
export const csvUrl = (region, opts) => `${BASE}/api/analysis.csv?${buildParams(region, opts)}`;
export const geocode = (q, signal) => getJson(`${BASE}/api/geocode?q=${encodeURIComponent(q)}`, signal);
