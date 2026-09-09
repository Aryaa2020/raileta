import React, { useMemo } from 'react';
import { Crosshair, Navigation, TrainFront } from 'lucide-react';

const VIEW = { width: 800, height: 250, pad: 28 };
function projectRoute(geometry) {
  const coordinates = (geometry?.coordinates || []).filter((point) => Array.isArray(point) && point.length >= 2 && point.every((value) => typeof value === 'number' && Number.isFinite(value)));
  if (coordinates.length < 2) return null;
  const lngs = coordinates.map(([lng]) => Number(lng)).filter(Number.isFinite);
  const lats = coordinates.map(([, lat]) => Number(lat)).filter(Number.isFinite);
  if (lngs.length < 2 || lats.length < 2) return null;
  const minLng = Math.min(...lngs); const maxLng = Math.max(...lngs);
  const minLat = Math.min(...lats); const maxLat = Math.max(...lats);
  const lngSpan = Math.max(0.001, maxLng - minLng); const latSpan = Math.max(0.001, maxLat - minLat);
  const project = ([lng, lat]) => [VIEW.pad + ((Number(lng) - minLng) / lngSpan) * (VIEW.width - VIEW.pad * 2), VIEW.pad + ((maxLat - Number(lat)) / latSpan) * (VIEW.height - VIEW.pad * 2)];
  return { points: coordinates.map(project), project };
}

const RouteNavigator = ({ stations = [], currentStation, routeGeometry }) => {
  const projected = useMemo(() => projectRoute(routeGeometry), [routeGeometry]);
  const upcoming = stations.slice(0, 4);
  const observedStops = (routeGeometry?.stops || []).filter((stop) => stop.stop !== false && Number.isFinite(stop.lat) && Number.isFinite(stop.lng));
  const currentStop = (routeGeometry?.stops || []).find((stop) => stop.station_code === currentStation);
  const trainPoint = currentStop && projected && Number.isFinite(currentStop.lat) && Number.isFinite(currentStop.lng) ? projected.project([currentStop.lng, currentStop.lat]) : null;
  const polyline = projected?.points.map(([x, y]) => `${x},${y}`).join(' ');
  return <section className="route-navigator solid-panel">
    <div className="route-toolbar"><div><p className="route-kicker"><Navigation className="h-3.5 w-3.5" /> Corridor schematic</p><h3>Observed route ahead</h3></div><span className="map-control" title="Station-coordinate schematic"><Crosshair className="h-4 w-4" /></span></div>
    <div className="map-canvas">
      <div className="map-grid" /><div className="map-label map-label-one">MAS<br /><strong>CHENNAI</strong></div><div className="map-label map-label-two">SBC<br /><strong>BENGALURU</strong></div>
      {projected ? <svg className="route-line" viewBox={`0 0 ${VIEW.width} ${VIEW.height}`} aria-label="Station-coordinate schematic, not railway track geometry"><defs><linearGradient id="routeGradient" x1="0" x2="1"><stop stopColor="#d6aeff" /><stop offset=".5" stopColor="#a65dff" /><stop offset="1" stopColor="#6944cf" /></linearGradient></defs><polyline points={polyline} fill="none" stroke="rgba(205,173,255,.15)" strokeWidth="14" strokeLinejoin="round" strokeLinecap="round" /><polyline points={polyline} fill="none" stroke="url(#routeGradient)" strokeWidth="4" strokeLinejoin="round" strokeLinecap="round" />{observedStops.map((stop) => { const point = projected.project([stop.lng, stop.lat]); return <circle key={`${stop.station_code}-${stop.sequence || point.join('-')}`} cx={point[0]} cy={point[1]} r="4" fill="#241b31" stroke="#d6b8ff" strokeWidth="2" />; })}{trainPoint && <g transform={`translate(${trainPoint[0]} ${trainPoint[1]})`}><circle r="18" fill="rgba(167,139,250,.16)" /><circle r="12" fill="#8b5cf6" stroke="#1b1720" strokeWidth="3" /><foreignObject x="-8" y="-8" width="16" height="16"><TrainFront className="map-train-icon" /></foreignObject></g>}</svg> : <div className="map-unavailable">Observed route geometry is unavailable from the latest source snapshot.</div>}
      <div className="train-pin"><p>{currentStation || 'Waiting for station event'}</p></div><div className="map-scale"><span /> {routeGeometry?.source || 'Route source'} · station event · {routeGeometry?.fetched_at ? new Date(routeGeometry.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'awaiting update'}</div>
    </div>
    <div className="route-stops"><span className="route-origin"><i /> Current</span>{upcoming.map((station, index) => <div className="route-stop" key={`${station.station_code}-${index}`}><i className={index === 0 ? 'active' : ''} /><div><strong>{station.station_name}</strong><span>{station.station_code}</span></div><time>{station.predicted_arrival ? new Date(station.predicted_arrival).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}</time></div>)}</div>
  </section>;
};
export default RouteNavigator;
