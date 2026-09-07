import React from 'react';
import { AlertTriangle, Gauge, Sparkles, TrainFront, X } from 'lucide-react';
import HistoricalReplayPanel from './HistoricalReplayPanel';


const time = (value) => value && Number.isFinite(Date.parse(value)) ? new Intl.DateTimeFormat('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'Asia/Kolkata' }).format(new Date(value)) : '—';

const TrainDetailPanel = ({ train, onClose }) => {
  if (train.data_mode === 'historical_replay') return <HistoricalReplayPanel train={train} onClose={onClose} />;
  const { train_number, train_name, train_class, current_status, upcoming_stations = [], overall_delay_reasons = [], data_freshness, fallback_source, calibration_level } = train;
  const corridor = (train.route_stops || []).map((stop) => stop.station_code);
  const currentIndex = corridor.indexOf(current_status.last_reported_station);
  const progress = currentIndex >= 0 && corridor.length > 1 ? Math.round((currentIndex / (corridor.length - 1)) * 100) : null;
  const nextStation = upcoming_stations[0];
  return <section className="ops-panel train-focus-panel"><div className="focus-header"><div><p className="ops-eyebrow"><Sparkles /> Train focus</p><h2>{train_name}</h2><span>Train {train_number} <b>·</b> {train_class}</span></div><button className="ops-icon-button" onClick={onClose} title="Close train view"><X /></button></div>
    <div className="focus-summary"><div className="progress-card"><div className="progress-ring" style={{ '--progress': `${progress || 0}%` }}><span>{progress == null ? '—' : `${progress}%`}</span></div><div><p>Estimated journey complete</p><span>Calculated from the last station event, not GPS</span></div></div><div className="summary-divider" /><div className="next-eta"><p>Next station ETA</p>{nextStation ? <><strong>{time(nextStation.predicted_arrival)}</strong><span>{nextStation.station_name} <b>·</b> {Math.round(nextStation.delay_minutes)} min delay</span></> : <strong>—</strong>}</div><div className="summary-divider" /><div className="last-event"><p>Last confirmed event</p><strong>{current_status.last_reported_station}</strong><span>{time(current_status.last_reported_time)} <b>·</b> departure/arrival report</span></div></div>
    <div className="station-route"><div className="route-caption"><div><p className="ops-eyebrow"><TrainFront /> Route progress</p><h3>Reported and upcoming stops</h3></div><span><Gauge /> Mock window · {Math.round((calibration_level || 0.8) * 100)}% target</span></div><div className="route-event-line">{corridor.map((code, index) => { const station = upcoming_stations.find((item) => item.station_code === code); const isCurrent = index === currentIndex; const isDone = index < currentIndex; const isNext = code === current_status.next_station || index === currentIndex + 1; return <div className={`route-event ${isDone ? 'is-done' : ''} ${isCurrent ? 'is-current' : ''} ${isNext ? 'is-next' : ''}`} key={code}><i>{isCurrent && <TrainFront />}</i><div><strong>{code}</strong><span>{station ? station.station_name : code === current_status.last_reported_station ? 'Last reported' : 'Scheduled stop'}</span>{station && <time>{time(station.predicted_arrival)}</time>}</div></div>; })}</div></div>
    <div className="focus-bottom-grid"><div className="factor-list"><div className="route-caption"><div><p className="ops-eyebrow"><AlertTriangle /> Prediction factors</p><h3>Mock prediction factors</h3></div></div>{overall_delay_reasons.slice(0, 3).map((reason, index) => <div className="factor-row" key={index}><span>{reason.icon || '◌'}</span><div><strong>{reason.description}</strong><small>{reason.category}</small></div><time>{reason.minutes > 0 ? '+' : ''}{Number(reason.minutes || 0).toFixed(1)}m</time></div>)}</div><div className="what-if-card"><div><p className="ops-eyebrow"><Gauge /> Data quality</p><h3>{fallback_source || 'Unavailable'} · {train.is_stale ? 'Stale / held position' : 'Source event'}</h3><span>Mock forecast; calibration not yet validated. Source time: {data_freshness ? time(data_freshness) : '—'}.</span></div></div></div>
  </section>;
};
export default TrainDetailPanel;
