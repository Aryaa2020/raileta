import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Activity, AlertCircle, ArrowUpRight, CloudSun, Clock3, RefreshCw, Route, ShieldCheck, Train, Wifi } from 'lucide-react';
import TrainSearch from './components/TrainSearch';
import StationCard from './components/StationCard';
import DelayChip from './components/DelayChip';
import RouteNavigator from './components/RouteNavigator';
import HistoricalReplayDetail from './components/HistoricalReplayDetail';
import { getCorridorStatus, getTrainETA } from './services/api';

function App() {
  const [progress, setProgress] = useState(0);
  const sceneRef = useRef(null);
  const dashboardLockedRef = useRef(false);
  const searchAnchorRef = useRef(null);
  const lockAnchorTop = useRef(null);
  const [trainData, setTrainData] = useState(null);
  const [corridorData, setCorridorData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [rosterError, setRosterError] = useState(null);
  const searchVersion = useRef(0);
  const [dashboardLocked, setDashboardLocked] = useState(false);
  const historical = trainData?.data_mode === 'historical_replay' || corridorData?.data_mode === 'historical_replay';
  const phase = dashboardLocked ? 'dashboard' : progress <= 0.001 ? 'cover' : progress >= 0.999 ? 'dashboard' : 'transition';
  const dashboardReveal = dashboardLocked ? 1 : Math.min(1, Math.max(0, (progress - 0.5) / 0.5));
  const dashboardEase = dashboardReveal * dashboardReveal * (3 - (2 * dashboardReveal));

  useEffect(() => {
    let frame = null;
    let atDashboard = false;
    const update = () => {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        const scene = sceneRef.current;
        if (!scene) return;
        if (dashboardLockedRef.current) return;
        const distance = Math.max(1, scene.offsetHeight - scene.firstElementChild.clientHeight);
        const next = Math.min(1, Math.max(0, -scene.getBoundingClientRect().top / distance));
        atDashboard = next >= 0.999;
        // Never discard the exact endpoints as a sub-pixel change.
        setProgress((current) => next === 0 || next === 1 || Math.abs(current-next) >= .001 ? next : current);
      });
    };
    const resize = () => {
      const scene = sceneRef.current;
      // A taller window must not put an already-reached search back into the
      // faded/inert part of the introduction. Native scrolling is unchanged.
      if (atDashboard && scene && !dashboardLockedRef.current) {
        const distance = scene.offsetHeight - scene.firstElementChild.clientHeight;
        window.scrollTo({ top: window.scrollY + scene.getBoundingClientRect().top + distance, behavior: 'instant' });
      }
      update();
    };
    update();
    window.addEventListener('scroll', update, { passive: true });
    window.addEventListener('resize', resize);
    return () => {
      window.removeEventListener('scroll', update);
      window.removeEventListener('resize', resize);
      if (frame) window.cancelAnimationFrame(frame);
    };
  }, []);

  useLayoutEffect(() => {
    if (!dashboardLocked || lockAnchorTop.current === null || !searchAnchorRef.current) return;
    const nextAnchorTop = window.scrollY + searchAnchorRef.current.getBoundingClientRect().top;
    window.scrollTo({ top: Math.max(0, nextAnchorTop-lockAnchorTop.current), behavior: 'instant' });
    lockAnchorTop.current = null;
  }, [dashboardLocked]);

  const lockDashboard = () => {
    if (dashboardLockedRef.current) return;
    lockAnchorTop.current = searchAnchorRef.current?.getBoundingClientRect().top ?? 0;
    dashboardLockedRef.current = true;
    setDashboardLocked(true);
  };

  const returnHome = () => {
    if (dashboardLockedRef.current) return;
    setTrainData(null);
    setError(null);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSearch = async (trainNumber) => {
    lockDashboard();
    const version = ++searchVersion.current;
    setLoading(true); setError(null);
    setTrainData(null);
    try { const data = await getTrainETA(trainNumber); if (version === searchVersion.current) setTrainData(data); }
    catch (err) { if (version === searchVersion.current) { setError(err.response?.data?.detail || 'We could not find movement information for that train. Please check the number and try again.'); setTrainData(null); } }
    finally { if (version === searchVersion.current) setLoading(false); }
  };

  useEffect(() => {
    let active = true;
    let pending = false;
    const loadCorridor = async () => {
      if (pending) return;
      pending = true;
      try {
        const data = await getCorridorStatus('MAS-SBC');
        if (active) { setCorridorData(data); setRosterError(null); }
      } catch (err) {
        if (active) setRosterError('Train list could not be refreshed. Previously received entries may be out of date. Retrying automatically.');
      } finally { pending = false; }
    };
    loadCorridor();
    const interval = setInterval(loadCorridor, historical ? 5000 : 30000);
    return () => { active = false; clearInterval(interval); };
  }, [historical]);

  // Refresh the selected record without overlapping requests or overwriting a
  // newer search. Profile replay is read-only; this does not retrain the model.
  useEffect(() => {
    const trainNumber = trainData?.train_number;
    if (!trainNumber) return undefined;
    let active = true;
    let pending = false;
    const refreshSelectedTrain = async () => {
      if (pending) return;
      pending = true;
      const version = searchVersion.current;
      try {
        const data = await getTrainETA(trainNumber);
        if (active && version === searchVersion.current) { setTrainData(data); setError(null); }
      } catch (err) {
        console.error('Unable to refresh selected train:', err);
        if (active && version === searchVersion.current) setError('Refresh failed. Showing the last received train report.');
      } finally { pending = false; }
    };
    const interval = setInterval(refreshSelectedTrain, historical ? 5000 : 30000);
    return () => { active = false; clearInterval(interval); };
  }, [trainData?.train_number, historical]);

  return <div className="app-shell min-h-screen text-slate-100">
    <div className="rail-backdrop" aria-hidden="true">
      <div className="ambient-orb ambient-orb-one" /><div className="ambient-orb ambient-orb-two" />
      <div className="rail-grid" />
      <svg className="rail-network" viewBox="0 0 1200 900" preserveAspectRatio="none">
        <path className="rail-track rail-track-glow" d="M-80 720 C130 620 170 770 350 665 S610 470 790 585 S990 690 1280 470" />
        <path className="rail-track" d="M-80 720 C130 620 170 770 350 665 S610 470 790 585 S990 690 1280 470" />
        <path className="rail-track rail-track-secondary" d="M90 -40 C240 120 260 275 430 330 S730 250 900 365 S1050 600 1210 780" />
        <path className="rail-track rail-track-secondary" d="M-40 185 C180 240 265 120 470 150 S780 250 1215 105" />
        <circle className="rail-node" cx="350" cy="665" r="4" /><circle className="rail-node" cx="790" cy="585" r="4" /><circle className="rail-node" cx="900" cy="365" r="3" /><circle className="rail-node" cx="470" cy="150" r="3" />
      </svg>
    </div>
    <header className="passenger-header relative z-20 mx-auto flex max-w-7xl items-center justify-between px-5 py-5 sm:px-8">
      <button className="flex items-center gap-3 text-left" onClick={returnHome} disabled={dashboardLocked} aria-label="Return to RailETA home"><span className="brand-mark"><Train className="h-5 w-5" /></span><span><span className="block text-lg font-semibold tracking-tight text-white">RailETA</span><span className="block text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-500">Arrival intelligence</span></span></button>
      <div className="hidden items-center gap-5 text-sm text-slate-400 sm:flex"><span className="flex items-center gap-2"><span className="live-dot" /> {historical ? 'Historical replay' : 'Prototype feed'}</span><span className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs text-slate-300">India Rail</span></div>
    </header>

    <main id="top" style={{ '--transition-progress': dashboardLocked ? 1 : progress, '--dashboard-progress': dashboardEase }} className={`journey-stage journey-stage-${phase} ${dashboardLocked ? 'dashboard-locked' : ''} relative z-10 mx-auto max-w-7xl px-5 pb-14 sm:px-8`}>
      <section ref={sceneRef} className="scroll-scene" aria-label="RailETA introduction">
        <div className="scene-viewport">
          <section className="cover-layer" aria-hidden={phase !== 'cover'}>
        <div className="cover-inner">
          <div className="cover-orbit cover-orbit-one" /><div className="cover-orbit cover-orbit-two" />
          <div className="cover-kicker"><span className="live-dot" /> A calmer way to travel</div>
          <div className="cover-train-mark"><Train /></div>
          <div className="cover-route" aria-hidden="true"><span className="cover-route-line" /><span className="cover-route-point" style={{ left: `${3 + progress * 94}%` }}><span /></span><span className="cover-route-end" /></div>
          <h1>{historical ? 'Understand your' : 'Know when your'}<br /><span>{historical ? 'train’s delay.' : 'journey arrives.'}</span></h1>
          <p>{historical ? 'Explore held-out station-delay averages and the model’s predictions.' : 'One clear view of your train’s expected arrival.'}</p>
          <div className="cover-meta"><span><Activity /> {historical ? 'Historical dataset replay' : 'Event-led updates'}</span><i /><span><ShieldCheck /> {historical ? 'Held-out trains · provenance unverified' : 'Check source and model status'}</span></div>
        </div>
          </section>
        </div>
      </section>

      <div className="dashboard-layer" inert={phase !== 'dashboard' ? '' : undefined} aria-hidden={phase !== 'dashboard'}>
        <div id="train-search" ref={searchAnchorRef} className="mx-auto max-w-4xl pt-10 lg:pt-16"><TrainSearch trains={corridorData?.trains || []} onSearch={handleSearch} onAction={lockDashboard} loading={loading} />
          <div className="dashboard-content" role="region" aria-label="Train reports" tabIndex={0}>
          {rosterError && <p role="alert" className="mt-4 px-2 text-sm text-amber-200">{rosterError}</p>}
          {(trainData || error) && !loading && <button type="button" className="quick-train mt-5" onClick={() => { ++searchVersion.current; setTrainData(null); setError(null); }}>Back to trains</button>}
          {historical && <p className="mt-4 px-2 text-xs leading-relaxed text-violet-200" role="status">Historical profile replay · held-out trains · provenance unverified. These are average-delay profiles, not individual runs or the MAS–SBC pilot corridor.</p>}
          {trainData?.data_mode === 'historical_replay' && !loading && <HistoricalReplayDetail train={trainData} />}
          {error && <div className="mt-5 flex gap-3 rounded-2xl border border-rose-400/20 bg-rose-400/10 p-4 text-sm text-rose-100"><AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-300" /><p>{error}</p></div>}
          {loading && <div className="flex min-h-64 flex-col items-center justify-center text-center"><div className="loading-ring"><RefreshCw className="h-5 w-5 animate-spin text-violet-300" /></div><p className="mt-4 text-sm text-slate-400">{historical ? 'Scoring the latest held-out historical record' : 'Reading the latest movement and corridor conditions'}</p></div>}
            {trainData && trainData.data_mode !== 'historical_replay' && !loading && <div className="mt-8 space-y-5 animate-enter"><section className="glass-panel overflow-hidden"><div className="flex flex-col gap-5 p-5 sm:flex-row sm:items-start sm:justify-between sm:p-7"><div><div className="eyebrow mb-3"><Wifi className="h-3.5 w-3.5" /> Station-event status</div><h2 className="text-2xl font-semibold tracking-tight text-white">{trainData.train_name}</h2><p className="mt-1 text-sm text-slate-400">Train {trainData.train_number} <span className="mx-2 text-slate-700">/</span> {trainData.train_class}</p></div><div className="rounded-2xl border border-amber-300/15 bg-amber-300/[0.09] px-5 py-3 sm:text-right"><p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-amber-200/70">Current delay</p><p className="mt-1 text-3xl font-semibold tracking-tight text-amber-200">{trainData.current_status.current_delay_minutes == null ? '—' : Math.round(trainData.current_status.current_delay_minutes)}<span className="ml-1 text-sm font-medium">{trainData.current_status.current_delay_minutes == null ? 'awaiting report' : 'min'}</span></p></div></div><div className="flex flex-col gap-3 border-t border-white/10 bg-black/10 px-5 py-4 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-7"><div className="flex items-center gap-3 text-slate-400"><span className="route-icon rounded-full p-2"><Route className="h-4 w-4" /></span><span>Last reported station <strong className="font-medium text-slate-200">{trainData.current_status.last_reported_station}</strong></span></div><span className="text-slate-500">Next <span className="text-slate-300">{trainData.current_status.next_station}</span></span></div></section><p className="px-2 text-xs text-amber-200" role="status">{trainData.data_mode === 'simulated' ? 'Simulated CRIS events' : trainData.fallback_source} · Mock ETAs and reason codes · {trainData.is_stale ? 'Stale input; last position held' : 'Recent source event'}</p><WeatherContext observations={trainData.weather_observations || []} /><RouteNavigator stations={trainData.upcoming_stations} routeGeometry={trainData.route_geometry} currentStation={trainData.current_status.last_reported_station} onAction={lockDashboard} />
            {trainData.overall_delay_reasons?.length > 0 && <section className="glass-panel p-5 sm:p-6"><div className="mb-4 flex items-center justify-between"><div><h3 className="font-semibold text-white">What is affecting this journey</h3><p className="mt-1 text-xs text-slate-500">Factors currently included in the prediction</p></div><ArrowUpRight className="h-5 w-5 text-slate-600" /></div><div className="grid gap-2 sm:grid-cols-2">{trainData.overall_delay_reasons.map((reason, idx) => <DelayChip key={idx} reason={reason} />)}</div></section>}
            <section><div className="mb-4 flex items-end justify-between px-1"><div><div className="eyebrow mb-2">Journey ahead</div><h3 className="text-xl font-semibold tracking-tight text-white">Upcoming arrivals</h3></div><span className="hidden items-center gap-1.5 text-xs text-slate-500 sm:flex"><Clock3 className="h-3.5 w-3.5" /> India Standard Time</span></div><div className="space-y-3">{trainData.upcoming_stations.map((station, idx) => <StationCard key={station.station_code} station={station} isNext={idx === 0} />)}</div></section><p className="px-1 text-center text-xs text-slate-600">Last updated {trainData.last_updated ? new Date(trainData.last_updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'awaiting data'} <span className="mx-1">·</span> Mock prediction window · calibration not yet validated</p></div>}
          {!trainData && !loading && !error && <DelayedTrains historical={historical} trains={corridorData?.trains || []} coverage={corridorData?.coverage} onSearch={handleSearch} onAction={lockDashboard} />}
          </div>
        </div>
      </div>
    </main><footer className="relative z-10 border-t border-white/[0.07] px-5 py-6 text-center text-xs text-slate-600">RailETA <span className="mx-2">·</span> Event-driven ETA forecasting for Indian Railways</footer>
  </div>;
}
function DelayedTrains({ trains, coverage, onSearch, onAction, historical }) {
  const visibleTrains = (historical ? trains : trains.filter((train) => train.delay_minutes == null || train.delay_minutes > 0)).slice(0, 6);
  return <section className="delayed-trains-panel mt-12 glass-panel p-5 sm:p-6">
    <div className="delayed-trains-heading"><div><div className="eyebrow mb-2"><Clock3 /> {historical ? 'Profile explorer' : 'Service watch'}</div><h3>{historical ? 'Held-out train profiles' : 'Trains running behind'}</h3><p>{historical ? 'Select a replayed train–station average to inspect its held-out prediction.' : 'Start with a train already moving through the corridor.'}</p><small className="mt-2 block text-[10px] text-slate-600">{coverage?.observed_train_count || trains.length} configured services received · roster is configurable</small></div><span className="delayed-live"><i /> {historical ? 'Historical averages on a timer' : 'Updated from station events'}</span></div>
    <div className="delayed-trains-list">{visibleTrains.length === 0 ? <p className="text-sm text-slate-500">No train records have been received yet.</p> : visibleTrains.map((train) => <button type="button" key={train.train_number} className="delayed-train" onClick={() => { onAction?.(); onSearch(train.train_number); }}><span className="delayed-train-icon"><Train /></span><span className="delayed-train-copy"><strong>{train.train_name}</strong><small>{train.train_number} <b>·</b> {historical ? `Profile station: ${train.current_station || '—'}` : `${train.current_station || '—'} → ${train.next_station || '—'}`}</small></span><span className="delayed-train-time">{train.delay_minutes == null ? '—' : `${train.delay_minutes > 0 ? '+' : ''}${Math.round(train.delay_minutes)}`}<small>{train.delay_minutes == null ? 'unknown' : 'min'}</small></span><ArrowUpRight className="delayed-train-arrow" /></button>)}</div>
  </section>;
}

function WeatherContext({ observations }) {
  const visible = observations.filter((item) => ['MAS', 'KPD', 'JTJ', 'SBC'].includes(item.station_code));
  if (!visible.length) return null;
  const latest = visible.map((item) => item.event_time).filter(Boolean).sort().at(-1);
  return <section className="glass-panel p-4"><div className="mb-3 flex items-center justify-between"><div className="eyebrow"><CloudSun className="h-3.5 w-3.5" /> Weather context</div><span className="text-right text-[10px] text-slate-600">Open-Meteo current model{latest ? ` · ${new Date(latest).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}</span></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{visible.map((item) => { const data = item.data || {}; return <div className="rounded-xl border border-white/[0.07] bg-white/[0.025] p-3" key={item.station_code}><strong className="block text-xs text-slate-300">{item.station_code}</strong><span className="mt-1 block text-lg font-semibold text-violet-100">{data.temperature_c == null ? '—' : `${Math.round(data.temperature_c)}°C`}</span><small className="block text-[10px] text-slate-500">{data.visibility_m == null ? 'Visibility —' : `Visibility ${(data.visibility_m / 1000).toFixed(1)} km`}</small></div>; })}</div></section>;
}
export default App;
