import React from 'react';
import { ArrowUpRight, CircleDot, TrainFront } from 'lucide-react';

const stations = [{ code: 'MAS', name: 'Chennai Central' }, { code: 'AJJ', name: 'Arakkonam' }, { code: 'KPD', name: 'Katpadi' }, { code: 'JTJ', name: 'Jolarpettai' }, { code: 'KPN', name: 'Kuppam' }, { code: 'BWT', name: 'Bangarapet' }, { code: 'KJM', name: 'Krishnarajapuram' }, { code: 'BNC', name: 'Bengaluru Cantt' }, { code: 'SBC', name: 'KSR Bengaluru' }];
const status = (delay) => !Number.isFinite(delay) ? 'unknown' : delay < 10 ? 'on-time' : delay < 30 ? 'attention' : 'late';
const delayLabel = (delay) => Number.isFinite(delay) ? `${delay > 0 ? '+' : ''}${Math.round(delay)} min` : 'No delay report';

const projectGeometry = (geometry) => {
  const coords = (geometry?.coordinates || []).filter((point) => Array.isArray(point) && point.length >= 2 && point.every((value) => typeof value === 'number' && Number.isFinite(value)));
  if (coords.length < 2) return null;
  const lngs = coords.map(([lng]) => Number(lng)).filter(Number.isFinite);
  const lats = coords.map(([, lat]) => Number(lat)).filter(Number.isFinite);
  if (lngs.length < 2 || lats.length < 2) return null;
  const minLng = Math.min(...lngs); const maxLng = Math.max(...lngs); const minLat = Math.min(...lats); const maxLat = Math.max(...lats);
  const project = ([lng, lat]) => [((Number(lng) - minLng) / Math.max(.001, maxLng - minLng)) * 94 + 3, ((maxLat - Number(lat)) / Math.max(.001, maxLat - minLat)) * 70 + 15];
  return { points: coords.map(project), project };
};

const CorridorMap = ({ corridorData, onTrainClick, selectedTrainNumber }) => {
  if (!corridorData) return null;
  const historical = corridorData.data_mode === 'historical_replay';
  const selected = corridorData.trains?.find((train) => train.train_number === selectedTrainNumber);
  const geometry = selected?.route_geometry || corridorData.route_geometry;
  const projected = projectGeometry(geometry);
  const pointFor = (code) => {
    const stop = geometry?.stops?.find((item) => item.station_code === code);
    return stop && projected && Number.isFinite(stop.lat) && Number.isFinite(stop.lng) ? projected.project([stop.lng, stop.lat]) : null;
  };
  return <section className="ops-panel corridor-panel"><div className="ops-panel-heading"><div><p className="ops-eyebrow"><CircleDot /> {historical ? 'Profile overview' : 'Corridor overview'}</p><h2>{corridorData.corridor_name}</h2><span>{historical ? 'Historical dataset replay · held-out trains · provenance unverified' : 'Train placement reflects the last confirmed station event'}</span></div>{!historical && <div className="ops-legend"><span><i className="legend-on-time" /> On schedule</span><span><i className="legend-attention" /> Attention</span><span><i className="legend-late" /> Late</span></div>}</div>
    {historical && <div className="border-b border-white/10 px-6 py-5 text-sm leading-relaxed text-slate-400">This dataset contains train–station average delay profiles, not movement events. Select a train below to inspect its recorded average and model prediction. No route position is implied.</div>}{!historical && <div className="corridor-track" aria-label="Station event corridor"><div className="corridor-map-note">{projected ? `Station-coordinate schematic · ${geometry.source || 'public feed'} · station events · ${geometry.stops?.filter((stop) => stop.stop !== false && Number.isFinite(stop.lat)).length || 0} stops · ${geometry.fetched_at ? new Date(geometry.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'awaiting update'}` : 'Station-coordinate schematic is unavailable from the latest source snapshot.'}</div>{projected && <svg className="corridor-route-geometry" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polyline points={projected.points.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="rgba(205,173,255,.15)" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" /><polyline points={projected.points.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="#a76bf5" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />{geometry.stops?.filter((stop) => stop.stop !== false && Number.isFinite(stop.lat) && Number.isFinite(stop.lng)).map((stop) => { const point = projected.project([stop.lng, stop.lat]); return <circle key={`stop-${stop.station_code}-${stop.sequence || point.join('-')}`} cx={point[0]} cy={point[1]} r="1.3" fill="#241b31" stroke="#d6b8ff" strokeWidth=".55" />; })}</svg>}{stations.map((station, index) => { const point = pointFor(station.code); if (!point) return null; return <div className="track-station" key={station.code} style={{ left: `${point[0]}%`, top: `${point[1]}%` }}><i /><strong>{station.code}</strong><span>{station.name}</span></div>; })}{corridorData.trains?.map((train, index) => { const point = pointFor(train.current_station); if (!point) return null; return <button type="button" key={train.train_number} onClick={() => onTrainClick(train)} className={`corridor-train corridor-train-${status(train.delay_minutes)} ${selectedTrainNumber === train.train_number ? 'is-selected' : ''}`} style={{ left: `${point[0]}%`, top: `${Math.max(18, Math.min(82, point[1] + (index % 2 ? -9 : 9)))}%` }}><span className="train-marker"><TrainFront /></span><span className="corridor-train-label"><strong>{train.train_number}</strong><small>{delayLabel(train.delay_minutes)}</small></span></button>; })}</div>}
    <div className="train-list-heading"><p>{historical ? 'Held-out dataset trains' : 'Configured feed services'}</p><span>{corridorData.coverage?.observed_train_count ?? corridorData.trains?.length ?? 0} configured · choose a train to inspect</span></div><div className="train-overview-list">{corridorData.trains?.map((train) => <button type="button" key={train.train_number} aria-pressed={selectedTrainNumber === train.train_number} onClick={() => onTrainClick(train)} className={`overview-train ${selectedTrainNumber === train.train_number ? 'is-selected' : ''}`}><span className={`overview-status ${status(train.delay_minutes)}`} /><div><strong>{train.train_name}</strong><span>{train.train_number} <b>·</b> {historical ? 'Profile station' : 'Last event'} {train.current_station}</span></div><time className={status(train.delay_minutes)}>{delayLabel(train.delay_minutes)}</time><ArrowUpRight /></button>)}{!corridorData.trains?.length && <p role="status" className="col-span-full py-4 text-sm text-slate-400">No train records are available yet. Use refresh to check again.</p>}</div>
  </section>;
};
export default CorridorMap;
