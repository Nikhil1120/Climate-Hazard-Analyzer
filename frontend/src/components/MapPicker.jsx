import React from "react";
import { MapContainer, TileLayer, CircleMarker, Rectangle, useMap, useMapEvents } from "react-leaflet";

function Clicks({ mode, pending, onPoint, onPending, onBox }) {
  useMapEvents({
    click(e) {
      const { lat, lng } = e.latlng;
      if (mode === "point") return onPoint(lat, lng);
      if (!pending) return onPending({ lat, lng });
      onBox(
        Math.min(pending.lat, lat),
        Math.max(pending.lat, lat),
        Math.min(pending.lng, lng),
        Math.max(pending.lng, lng)
      );
    },
  });
  return null;
}

function Recenter({ region }) {
  const map = useMap();
  React.useEffect(() => {
    if (region.kind === "point") map.setView([region.lat, region.lon], Math.max(map.getZoom(), 6));
    else map.fitBounds([[region.min_lat, region.min_lon], [region.max_lat, region.max_lon]], { maxZoom: 8 });
  }, [region, map]);
  return null;
}

export default function MapPicker({ region, mode, onPoint, onBox }) {
  const [pending, setPending] = React.useState(null);
  React.useEffect(() => setPending(null), [mode]);
  const center = region.kind === "point" ? [region.lat, region.lon] : [(region.min_lat + region.max_lat) / 2, (region.min_lon + region.max_lon) / 2];
  return (
    <div className="map-wrap">
      <MapContainer center={center} zoom={6} scrollWheelZoom style={{ height: "100%", width: "100%" }}>
        <TileLayer attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <Clicks
          mode={mode}
          pending={pending}
          onPoint={(la, lo) => onPoint(la, lo)}
          onPending={setPending}
          onBox={(a, b, c, d) => {
            setPending(null);
            onBox(a, b, c, d);
          }}
        />
        <Recenter region={region} />
        {region.kind === "point" && <CircleMarker center={[region.lat, region.lon]} radius={9} pathOptions={{ color: "#b3261e", fillColor: "#e8554d", fillOpacity: 0.85 }} />}
        {region.kind === "box" && <Rectangle bounds={[[region.min_lat, region.min_lon], [region.max_lat, region.max_lon]]} pathOptions={{ color: "#b3261e", weight: 2, fillOpacity: 0.12 }} />}
        {pending && <CircleMarker center={[pending.lat, pending.lng]} radius={5} pathOptions={{ color: "#1a1a1a" }} />}
      </MapContainer>
      <div className="map-hint">
        {mode === "point" ? "Click the map to pick a location" : pending ? "Click the opposite corner" : "Click two opposite corners to draw a box"}
      </div>
    </div>
  );
}
