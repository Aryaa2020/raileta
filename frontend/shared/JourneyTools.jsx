import React, { useEffect, useState } from 'react';
import './journeys.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
const time = value => value ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
const minutes = value => Number.isFinite(value) ? `${Math.round(value)} min` : '—';

function useData(path, refreshKey = 0) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    let pending = false;
    let controller;
    let timeout;
    setState({ key: path, data: null, loading: true, error: null });
    if (!path) { setState({ key: path, data: null, loading: false, error: null }); return; }
    const load = async () => {
      if (pending) return;
      pending = true;
      controller = new AbortController();
      timeout = setTimeout(() => controller.abort(), 10000);
      try {
        const response = await fetch(API + path, { signal: controller.signal });
        if (!response.ok) throw new Error('This report is unavailable. Please retry.');
        const data = await response.json();
        if (active) setState({ key: path, data, loading: false, error: null });
      } catch (error) {
        if (active) setState(previous => ({ ...previous, loading: false, error: 'Refresh failed. Any displayed report is from the last successful fetch.' }));
      } finally { clearTimeout(timeout); pending = false; }
    };
    load();
    const poll = setInterval(load, 30000);
    return () => { active = false; clearInterval(poll); clearTimeout(timeout); controller?.abort(); };
  }, [path, refresh, refreshKey]);
  return { ...(state.key === path ? state : { data: null, loading: !!path, error: null }), retry: () => setRefresh(value => value + 1) };
}

function LoadState({ request }) {
  if (request.loading) return <p role="status" className="jt-note">Loading dated records…</p>;
  if (request.error) return <div role="alert" className="jt-note">{request.error} <button type="button" onClick={request.retry}>Retry</button></div>;
  return null;
}

function Mode({ mode, onChange }) {
  return <label>Data source<select aria-label="Journey data source" value={mode} onChange={event => onChange(event.target.value)}><option value="live">Sourced journeys</option><option value="simulation">Simulation only</option></select></label>;
}

export function JourneyWorkspace({ trainNumber = '', initialMode = 'live', initialDate, renderDetail }) {
  const [mode, setMode] = useState(initialMode);
  useEffect(() => { setMode(initialMode); }, [initialMode]);
  const [date, setDate] = useState(initialDate || today);
  useEffect(() => { if (initialDate) setDate(initialDate); }, [initialDate]);
  const [number, setNumber] = useState(trainNumber);
  const [selected, setSelected] = useState('');
  const [allDates, setAllDates] = useState(false);
  useEffect(() => { setNumber(trainNumber); setSelected(''); }, [trainNumber]);
  const query = new URLSearchParams({ mode, ...(date && !allDates ? { date } : {}), ...(number.trim() ? { train_number: number.trim() } : {}) });
  const list = useData('/journeys?' + query);
  const detail = useData(selected ? `/journeys/${selected}?mode=${mode}` : null);
  const change = fn => value => { fn(value); setSelected(''); };
  return <div className="jt-workspace">
    <div className="jt-controls"><Mode mode={mode} onChange={change(setMode)} /><label>Train number<input aria-label="Dated train number" value={number} onChange={e => change(setNumber)(e.target.value)} placeholder="All trains" /></label><label>Origin departure date (IST)<input type="date" aria-label="Journey start date" disabled={allDates} value={date} onChange={e => change(setDate)(e.target.value)} /></label><label className="jt-checkbox"><input type="checkbox" checked={allDates} onChange={e => change(setAllDates)(e.target.checked)} /> Include previous runs</label><button type="button" onClick={() => { list.retry(); detail.retry(); }}>Refresh</button></div>
    <p className="jt-note">{mode === 'simulation' ? 'SIMULATION · Synthetic journeys and outcomes. Not a live service or evidence of real-world accuracy.' : 'The date is when the train leaves its origin, even if it reaches your station the following day. Aggregate delay profiles cannot populate this view.'} Reports refresh every 30 seconds.</p>
    <LoadState request={list} />
    {list.data && !list.data.journeys.length && <p className="jt-empty">No dated journeys available for this selection. Try another date or choose Simulation only to view an explicitly synthetic demo.</p>}
    {!!list.data?.journeys.length && <label className="jt-run-select">Journey<select aria-label="Choose dated journey" value={selected} onChange={e => setSelected(e.target.value)}><option value="">Choose a dated run</option>{list.data.journeys.map(run => <option key={run.id} value={run.id}>{run.train_number} · {run.train_name} · {run.start_date} · {run.status}{run.is_stale ? ' · old report' : ''}</option>)}</select></label>}
    {selected && <LoadState request={detail} />}
    {detail.data && (renderDetail ? renderDetail(detail.data) : <JourneyDetail key={detail.data.id} journey={detail.data} />)}
  </div>;
}

export function JourneyDetail({ journey }) {
  const reached = journey.stops.reduce((last, stop) => stop.actual_arrival || stop.actual_departure ? stop.sequence : last, -1);
  const [sequence, setSequence] = useState(String(journey.next_stop?.sequence ?? journey.stops.at(-1)?.sequence ?? 0));
  const [tab, setTab] = useState('timeline');
  const history = useData(tab === 'history' ? `/journeys/${journey.id}/history?mode=${journey.mode}&sequence=${sequence}` : null);
  return <section className="jt-detail">
    {journey.mode === 'simulation' && <p className="jt-warning">SIMULATION ONLY · Generated movements on published train routes. Scenario time: {time(journey.scenario_time)} IST. Not a live railway service.</p>}<header><h3>{journey.train_name}</h3><p>{journey.train_number} · Started {journey.start_date} · {journey.mode === 'simulation' ? 'Synthetic' : journey.source}</p></header>
    {journey.status === 'completed' ? <p className="jt-note">Completed journey · archived forecasts and actual timings, not a live service.</p> : journey.is_stale && <p className="jt-warning">Old or missing station report. Last predictions are held; do not treat this as the train’s current position. Last report: {time(journey.last_reported_time)} IST.</p>}
    <dl className="jt-outlook"><div><dt>{journey.status === 'completed' ? 'Final reported delay' : 'Current reported delay'}</dt><dd>{minutes(journey.current_delay_minutes)}</dd></div><div><dt>{journey.status === 'completed' ? 'Actual destination arrival' : 'Next-stop estimate'}</dt><dd>{time(journey.status === 'completed' ? journey.stops.at(-1)?.actual_arrival : journey.next_stop?.forecast?.predicted_arrival)}<small>{journey.status === 'completed' ? journey.stops.at(-1)?.station_name : journey.next_stop?.station_name || 'No upcoming stop'}</small></dd></div><div><dt>{journey.status === 'completed' ? 'Last destination estimate' : 'Destination delay'}</dt><dd>{minutes(journey.destination_delay_minutes)}<small>{journey.status === 'completed' ? `Actual delay: ${minutes(journey.destination_actual_delay_minutes)}` : Number.isFinite(journey.delay_change_minutes) ? Math.abs(journey.delay_change_minutes) < 1 ? 'No material change expected' : `${Math.round(Math.abs(journey.delay_change_minutes))} min ${journey.delay_change_minutes < 0 ? 'recovery' : 'more delay'} expected` : 'No destination forecast'}</small></dd></div></dl>
    <div className="jt-progress"><label htmlFor={`progress-${journey.id}`}>Journey progress · {Math.max(0, reached + 1)} of {journey.stops.length} stops reported</label><progress id={`progress-${journey.id}`} value={Math.max(0,reached)} max={Math.max(1,journey.stops.length-1)} /><small>Based on station reports, not live distance travelled.</small></div>
    <div className="jt-tabs" aria-label="Journey detail view"><button aria-pressed={tab === 'timeline'} onClick={() => setTab('timeline')}>Station timeline</button><button aria-pressed={tab === 'history'} onClick={() => setTab('history')}>Forecast changes</button></div>
    {tab === 'timeline' ? <div className="jt-table-scroll"><table><caption>Complete dated station timeline · all times IST</caption><thead><tr><th>Station</th><th>Scheduled arrival / departure</th><th>Actual arrival / departure</th><th>Latest estimate / window</th></tr></thead><tbody>{journey.stops.map(stop => <tr key={stop.sequence}><th scope="row">{stop.sequence + 1}. {stop.station_name}<small>{stop.station_code}</small></th><td>{time(stop.scheduled_arrival)}<small>{time(stop.scheduled_departure)}</small></td><td>{time(stop.actual_arrival)}<small>{time(stop.actual_departure)}</small></td><td>{stop.actual_arrival ? 'Arrived' : time(stop.forecast?.predicted_arrival)}<small>{stop.actual_arrival ? 'Actual shown in previous column' : stop.forecast?.confidence_lower ? `${time(stop.forecast.confidence_lower)} – ${time(stop.forecast.confidence_upper)}` : 'No validated arrival window'}</small></td></tr>)}</tbody></table></div> : <><label className="jt-run-select">Station<select aria-label="Forecast history station" value={sequence} onChange={e => setSequence(e.target.value)}>{journey.stops.filter(s => s.scheduled_arrival).map(stop => <option key={stop.sequence} value={stop.sequence}>{stop.station_name}</option>)}</select></label><LoadState request={history} />{history.data && <ForecastChart data={history.data} />}</>}
    {journey.stops.some(s => s.forecast?.reasons?.length) && <details><summary>Model version & prediction factors</summary><p className="jt-note">{journey.stops.find(s => s.forecast)?.forecast.model_version} · SHAP associations, not proven causes.</p>{(journey.next_stop?.forecast || journey.stops.at(-1)?.forecast)?.reasons?.map(reason => <p className="jt-note" key={reason.feature}>{reason.description}: {reason.minutes > 0 ? '+' : ''}{reason.minutes.toFixed(1)} min</p>)}</details>}
    <p className="jt-note">Predictions are not guarantees. Missing windows mean no validated journey model is active. SHAP describes model associations, not proven causes. Platform assignments are never inferred.</p>
    {!!journey.conditions.length && <details><summary>Conditions on this route ({journey.conditions.length})</summary><ConditionRows rows={journey.conditions} /></details>}
  </section>;
}

export function ForecastChart({ data }) {
  const forecasts = data.forecasts;
  if (!forecasts.length) return <p className="jt-empty">No issued forecasts for this station yet.</p>;
  const times = forecasts.flatMap(f => [f.predicted_arrival, f.confidence_lower, f.confidence_upper]).concat(data.actual_arrival || []).filter(Boolean).map(Date.parse);
  const low = Math.min(...times)-60000, high = Math.max(...times)+60000;
  const issued = forecasts.map(f => Date.parse(f.issued_at));
  const x = t => 65+(t-issued[0])/Math.max(60000, issued.at(-1)-issued[0])*580;
  const y = t => 210-(Date.parse(t)-low)/(high-low)*165;
  return <div className="jt-history"><p className="jt-note">Horizontal: time the prediction was issued. Vertical: predicted arrival time. Purple line: estimate; bars: supplied arrival windows; green line: actual arrival.</p><svg viewBox="0 0 690 260" role="img" aria-label="Forecast evolution and supplied arrival windows"><line x1="65" y1="210" x2="645" y2="210" stroke="#655b71" /><text x="5" y="45">{new Date(high).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit'})}</text><text x="5" y="210">{new Date(low).toLocaleTimeString('en-IN',{timeZone:'Asia/Kolkata',hour:'2-digit',minute:'2-digit'})}</text>{data.actual_arrival && <line x1="65" x2="645" y1={y(data.actual_arrival)} y2={y(data.actual_arrival)} stroke="#a9d9bb" strokeDasharray="5 4" />}<polyline points={forecasts.map(f => `${x(Date.parse(f.issued_at))},${y(f.predicted_arrival)}`).join(' ')} fill="none" stroke="#c6a3ff" strokeWidth="2" />{forecasts.map(f => <g key={f.id}>{f.confidence_lower && f.confidence_upper && <line x1={x(Date.parse(f.issued_at))} x2={x(Date.parse(f.issued_at))} y1={y(f.confidence_lower)} y2={y(f.confidence_upper)} stroke="#8e6abb" strokeWidth="5" />}<circle cx={x(Date.parse(f.issued_at))} cy={y(f.predicted_arrival)} r="4" fill="#e6d5ff" /></g>)}<text x="65" y="245">{time(forecasts[0].issued_at)}</text><text x="645" y="245" textAnchor="end">{time(forecasts.at(-1).issued_at)}</text></svg><details><summary>Exact predictions, source reports & explanations ({forecasts.length})</summary><div className="jt-table-scroll"><table><thead><tr><th>Issued / source report</th><th>Estimate / window</th><th>Model / explanations</th></tr></thead><tbody>{forecasts.map(f => <tr key={f.id}><td>{time(f.issued_at)}<small>{f.source_event} · {time(f.source_time)}</small></td><td>{time(f.predicted_arrival)}<small>{f.confidence_lower ? `${time(f.confidence_lower)} – ${time(f.confidence_upper)}` : 'Window unavailable'}</small></td><td>{f.model_version}<small>{f.reasons.map(r => `${r.description}: ${r.minutes > 0 ? '+' : ''}${r.minutes.toFixed(1)} min`).join('; ') || 'Baseline; no model explanations'}</small></td></tr>)}</tbody></table></div></details>{data.actual_arrival && <p className="jt-note">Actual arrival: {time(data.actual_arrival)} IST</p>}</div>;
}

function ConditionRows({ rows }) {
  return <div className="jt-table-scroll"><table><thead><tr><th>Section / condition</th><th>Severity</th><th>Expiry / source</th></tr></thead><tbody>{rows.map(c => <tr key={c.id}><td>{c.from_station} → {c.to_station}<small>{c.kind}{c.speed_limit_kmph ? ` · ${c.speed_limit_kmph} km/h` : ''} · {c.note}</small></td><td>{Math.round(c.severity * 100)} / 100</td><td>{c.expires_at ? time(c.expires_at) + ' IST' : 'No expiry supplied'}<small>{c.source}</small></td></tr>)}</tbody></table></div>;
}

function Conditions({ mode }) {
  const request = useData('/conditions?mode=' + mode);
  const rows = request.data?.conditions || [];
  const sections = request.data?.sections || [];
  const coords = sections.flatMap(s => s.geometry || []);
  const xs = coords.map(p => p[0]), ys = coords.map(p => p[1]);
  const point = p => `${25+(p[0]-Math.min(...xs))/Math.max(.01,Math.max(...xs)-Math.min(...xs))*590},${190-(p[1]-Math.min(...ys))/Math.max(.01,Math.max(...ys)-Math.min(...ys))*150}`;
  return <><LoadState request={request} /><p className="jt-note">Read-only supplied conditions. Amber sections have an active restriction, block, or congestion report. An empty list does not establish that a route is clear.</p>{coords.length > 1 && <svg className="jt-condition-map" viewBox="0 0 650 240" role="img" aria-label="Corridor section conditions map">{sections.map(s => <g key={s.code}><polyline points={s.geometry.map(point).join(' ')} fill="none" stroke={rows.some(c => c.section === s.code) ? '#edc991' : '#645773'} strokeWidth="5"><title>{s.from_station} to {s.to_station}{rows.filter(c => c.section === s.code).map(c => ': ' + c.kind).join('')}</title></polyline>{s.geometry.length > 0 && <text x={point(s.geometry[0]).split(',')[0]} y={Number(point(s.geometry[0]).split(',')[1])-12}>{s.from_station}</text>}</g>)}</svg>}{rows.length ? <ConditionRows rows={rows} /> : !request.loading && <p className="jt-empty">No active condition records supplied for this mode.</p>}</>;
}

function Accuracy({ mode }) {
  const request = useData('/accuracy?mode=' + mode);
  return <><LoadState request={request} />{request.data && <>{request.data.releases?.filter(release => release.active).map(release => <section key={release.version}><h3>Active model · {release.version}</h3><p className="jt-note">{mode === 'simulation' ? 'Held-out synthetic test' : 'Held-out dated test'}: {release.metrics.samples.toLocaleString()} examples · error {release.metrics.mae_minutes.toFixed(2)} min vs {release.metrics.baseline_mae_minutes.toFixed(2)} min baseline · measured coverage {release.metrics.coverage_percent.toFixed(1)}%. {mode === 'simulation' ? 'Not real-world accuracy.' : 'Limited to the measured evaluation sample.'}</p>{release.metrics.stress_scenario && <p className="jt-warning">Harder synthetic scenario: {release.metrics.stress_scenario.mae_minutes.toFixed(2)} min error · {release.metrics.stress_scenario.coverage_percent.toFixed(1)}% coverage. Wider disruptions can reduce reliability.</p>}</section>)}<p className="jt-note">{request.data.note} Review status: {request.data.drift_status.replaceAll('_',' ')}.</p>{request.data.rows.length ? <div className="jt-table-scroll"><table><thead><tr><th>Lead time / model</th><th>Samples</th><th>Mean error / baseline</th><th>Measured coverage</th></tr></thead><tbody>{request.data.rows.map(row => <tr key={row.lead_time+row.model_version}><th>{row.lead_time}<small>{row.model_version}</small></th><td>{row.samples}</td><td>{minutes(row.mae_minutes)}<small>Baseline {minutes(row.baseline_mae_minutes)}</small></td><td>{row.coverage_percent == null ? 'No windows' : row.coverage_percent.toFixed(1)+'%'}<small>{row.window_samples} window samples · 80% target, not a guarantee</small></td></tr>)}</tbody></table></div> : <p className="jt-empty">No matched pre-arrival forecasts and actual arrivals yet. Aggregate-profile test results cannot establish operational arrival accuracy.</p>}</>}</>;
}

export function OperationalTools({ initialMode = 'live', initialDate }) {
  const [tab,setTab] = useState('journeys');
  const [mode,setMode] = useState(initialMode);
  useEffect(() => { setMode(initialMode); }, [initialMode]);
  return <details className="jt-operational"><summary>Journey history, section conditions & accuracy</summary><div className="jt-tabs"><button aria-pressed={tab==='journeys'} onClick={()=>setTab('journeys')}>Dated journeys</button><button aria-pressed={tab==='conditions'} onClick={()=>setTab('conditions')}>Section conditions</button><button aria-pressed={tab==='accuracy'} onClick={()=>setTab('accuracy')}>Accuracy monitoring</button></div>{tab==='journeys' ? <JourneyWorkspace initialMode={initialMode} initialDate={initialDate} /> : <><div className="jt-controls"><Mode mode={mode} onChange={setMode}/></div>{mode==='simulation' && <p className="jt-warning">SIMULATION · Synthetic conditions and evaluation only.</p>}{tab==='conditions' ? <Conditions mode={mode}/> : <Accuracy mode={mode}/>}</>}</details>;
}

export function ArrivalsPanel({ stationCode = 'MAS', refreshKey = 0, initialMode = 'live' }) {
  const [station,setStation] = useState(stationCode);
  const [hours,setHours] = useState('3');
  const [mode,setMode] = useState(initialMode);
  useEffect(() => { setMode(initialMode); }, [initialMode]);
  const request = useData(`/stations/${encodeURIComponent(station)}/arrivals?hours=${hours}&mode=${mode}`, refreshKey);
  return <section className="jt-arrivals"><h2>Expected arrivals</h2><div className="jt-controls"><label>Station<select aria-label="Arrival station" value={station} onChange={e=>setStation(e.target.value)}><option value="MAS">Chennai Central</option><option value="AJJ">Arakkonam</option><option value="KPD">Katpadi Junction</option><option value="SBC">KSR Bengaluru</option></select></label><label>Time window<select aria-label="Arrival time window" value={hours} onChange={e=>setHours(e.target.value)}>{[1,3,6,12,24].map(n=><option key={n} value={n}>Next {n} {n===1?'hour':'hours'}</option>)}</select></label><Mode mode={mode} onChange={setMode}/><button onClick={request.retry}>Refresh arrivals</button></div><p className="jt-note">{mode==='simulation'?'SIMULATION · Synthetic arrivals only.':'Sourced dated forecasts only. Platform assignments require an actual source.'}</p><LoadState request={request}/>{request.data && (request.data.arrivals.length ? <div className="jt-table-scroll"><table><thead><tr><th>Train / origin date</th><th>Expected / window (IST)</th><th>Platform / freshness</th></tr></thead><tbody>{request.data.arrivals.map(row=><tr key={row.journey_id+'-'+row.sequence}><th>{row.train_number} · {row.train_name}<small>{row.start_date}</small></th><td>{time(row.forecast.predicted_arrival)}<small>{row.forecast.confidence_lower?`${time(row.forecast.confidence_lower)} – ${time(row.forecast.confidence_upper)}`:'No validated window'}</small></td><td>{row.platform || 'Not supplied'}<small>{row.is_stale?'Old report · prediction held':'Recent report'}</small></td></tr>)}</tbody></table></div>:<p className="jt-empty">No dated arrival forecasts in this time window. Aggregate profiles cannot supply an arrivals board.</p>)}</section>;
}
