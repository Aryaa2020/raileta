import React, { useState } from 'react';
import { ChevronRight, Search, TrainFront } from 'lucide-react';

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
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('all');
  const [sort, setSort] = useState('number');
  if (!corridorData) return null;
  const trains = corridorData.trains || [];
  const visible = trains.filter(train => {
    const matchesText = [train.train_number, train.train_name, train.current_station].join(' ').toLowerCase().includes(query.trim().toLowerCase());
    const delay = train.delay_minutes;
    return matchesText && (filter === 'all' || filter === 'unknown' && !Number.isFinite(delay) || Number.isFinite(delay) && (filter === 'low' && delay < 10 || filter === 'medium' && delay >= 10 && delay < 30 || filter === 'high' && delay >= 30));
  }).sort((a, b) => sort === 'delay' ? (Number.isFinite(b.delay_minutes) ? b.delay_minutes : -Infinity) - (Number.isFinite(a.delay_minutes) ? a.delay_minutes : -Infinity) || String(a.train_number).localeCompare(String(b.train_number), undefined, { numeric: true }) : String(a.train_number).localeCompare(String(b.train_number), undefined, { numeric: true }));
  const historical = corridorData.data_mode === 'historical_replay';
  const selected = corridorData.trains?.find((train) => train.train_number === selectedTrainNumber);
  const geometry = selected?.route_geometry || corridorData.route_geometry;
  const projected = projectGeometry(geometry);
  const pointFor = (code) => {
    const stop = geometry?.stops?.find((item) => item.station_code === code);
    return stop && projected && Number.isFinite(stop.lat) && Number.isFinite(stop.lng) ? projected.project([stop.lng, stop.lat]) : null;
  };
  return <section className="ops-panel corridor-panel" aria-label="Train list">
    <div className="ops-panel-heading"><div><h2>Trains</h2><span>{historical ? 'Past average delay by train' : 'Latest reported delay by train'}</span></div><span className="ops-list-count" role="status">{visible.length} of {trains.length}</span></div>
    <div className="ops-list-tools">
      <label className="ops-search"><Search aria-hidden="true" /><input type="search" aria-label="Search trains" placeholder="Train name, number, or station" value={query} onChange={event => setQuery(event.target.value)} /></label>
      <div className="ops-filter-row"><label>Delay<select aria-label="Filter by delay" value={filter} onChange={event => setFilter(event.target.value)}><option value="all">All delays</option><option value="low">Under 10 min</option><option value="medium">10–29 min</option><option value="high">30+ min</option><option value="unknown">No report</option></select></label><label>Sort<select aria-label="Sort trains" value={sort} onChange={event => setSort(event.target.value)}><option value="number">Train number</option><option value="delay">Highest delay</option></select></label></div>
    </div>
    <div className="ops-table-labels" aria-hidden="true"><span>Train</span><span>Station</span><span>Delay</span><span /></div>
    <div className="train-overview-list">{visible.map(train => <button type="button" key={train.train_number} aria-pressed={selectedTrainNumber === train.train_number} onClick={() => onTrainClick(train)} className={`overview-train ${selectedTrainNumber === train.train_number ? 'is-selected' : ''}`}><div><strong>{train.train_name}</strong><span>{train.train_number}</span></div><span className="ops-row-station">{train.current_station || '—'}</span><span className={`ops-row-delay ${status(train.delay_minutes)}`}>{delayLabel(train.delay_minutes)}</span><ChevronRight aria-hidden="true" /></button>)}</div>
    {!trains.length ? <p role="status" className="ops-list-empty">No train records are available yet. Use refresh to check again.</p> : !visible.length && <div className="ops-list-empty" role="status"><p>No trains match your filters.</p><button className="ops-action" onClick={() => { setQuery(''); setFilter('all'); }}>Clear filters</button></div>}
    <div className="ops-list-footnote">{historical ? 'Station refers to the past record, not the train’s current location.' : 'Station is the last reported location, not GPS.'}</div>
    {!historical && <details className="ops-disclosure ops-map-disclosure"><summary>View station map</summary><div className="corridor-track" aria-label="Station event corridor"><div className="corridor-map-note">{projected ? `Station-coordinate schematic · ${geometry.source || 'public feed'} · station events · ${geometry.stops?.filter((stop) => stop.stop !== false && Number.isFinite(stop.lat)).length || 0} stops · ${geometry.fetched_at ? new Date(geometry.fetched_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : 'awaiting update'}` : 'Station-coordinate schematic is unavailable from the latest source snapshot.'}</div>{projected && <svg className="corridor-route-geometry" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true"><polyline points={projected.points.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="rgba(205,173,255,.15)" strokeWidth="5" strokeLinejoin="round" strokeLinecap="round" /><polyline points={projected.points.map(([x, y]) => `${x},${y}`).join(' ')} fill="none" stroke="#a76bf5" strokeWidth="1.5" strokeLinejoin="round" strokeLinecap="round" />{geometry.stops?.filter((stop) => stop.stop !== false && Number.isFinite(stop.lat) && Number.isFinite(stop.lng)).map((stop) => { const point = projected.project([stop.lng, stop.lat]); return <circle key={`stop-${stop.station_code}-${stop.sequence || point.join('-')}`} cx={point[0]} cy={point[1]} r="1.3" fill="#241b31" stroke="#d6b8ff" strokeWidth=".55" />; })}</svg>}{stations.map((station, index) => { const point = pointFor(station.code); if (!point) return null; return <div className="track-station" key={station.code} style={{ left: `${point[0]}%`, top: `${point[1]}%` }}><i /><strong>{station.code}</strong><span>{station.name}</span></div>; })}{corridorData.trains?.map((train, index) => { const point = pointFor(train.current_station); if (!point) return null; return <button type="button" key={train.train_number} onClick={() => onTrainClick(train)} className={`corridor-train corridor-train-${status(train.delay_minutes)} ${selectedTrainNumber === train.train_number ? 'is-selected' : ''}`} style={{ left: `${point[0]}%`, top: `${Math.max(18, Math.min(82, point[1] + (index % 2 ? -9 : 9)))}%` }}><span className="train-marker"><TrainFront /></span><span className="corridor-train-label"><strong>{train.train_number}</strong><small>{delayLabel(train.delay_minutes)}</small></span></button>; })}</div></details>}
  </section>;
};
export default CorridorMap;
