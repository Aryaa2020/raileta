import React, { useEffect, useRef, useState } from 'react';
import { AlertCircle, ArrowUpRight, ArrowLeft, BarChart3, Layers, RefreshCw, TrainFront, Activity } from 'lucide-react';
import Navigation, { RailMark, surfaceUrl } from '../../shared/Navigation';
import KiroButton from '../../shared/KiroButton';
import RevealText from '../../shared/RevealText';
import TrackJourney from './components/TrackJourney';
import HeroTrack from './components/HeroTrack';
import TrainSearch from './components/TrainSearch';
import StationCard from './components/StationCard';
import DelayChip from './components/DelayChip';
import RouteNavigator from './components/RouteNavigator';
import HistoricalReplayDetail from './components/HistoricalReplayDetail';
import JourneyProgress from './components/JourneyProgress';
import { JourneyWorkspace, JourneyDetail } from '../../shared/JourneyTools';
import { getCorridorStatus, getTrainETA } from './services/api';

export default function App() {
  const [trainData, setTrainData] = useState(null);
  const [corridorData, setCorridorData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [rosterLoading, setRosterLoading] = useState(true);
  const [error, setError] = useState(null);
  const [rosterError, setRosterError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const searchVersion = useRef(0);
  const historical = trainData?.data_mode === 'historical_replay' || corridorData?.data_mode === 'historical_replay';

  const handleSearch = async (trainNumber) => {
    const version = ++searchVersion.current;
    setLoading(true); setError(null); setTrainData(null);
    try { const data = await getTrainETA(trainNumber); if (version === searchVersion.current) setTrainData(data); }
    catch (err) { if (version === searchVersion.current) setError(err.response?.data?.detail || 'We could not find this train. Check the number and try again.'); }
    finally { if (version === searchVersion.current) setLoading(false); }
  };
  useEffect(() => {
    let active = true; let pending = false;
    const load = async () => {
      if (pending) return;
      pending = true;
      try { const data = await getCorridorStatus('MAS-SBC'); if (active) { setCorridorData(data); setRosterError(null); } }
      catch { if (active) setRosterError('Train data is temporarily unavailable. Any previous records may be out of date.'); }
      finally { pending = false; if (active) setRosterLoading(false); }
    };
    load(); const interval = setInterval(load, historical ? 5000 : 30000);
    return () => { active = false; clearInterval(interval); };
  }, [historical, refreshKey]);
  useEffect(() => {
    if (!trainData?.train_number) return;
    let active = true; let pending = false;
    const refresh = async () => {
      if (pending) return;
      pending = true;
      const version = searchVersion.current;
      try { const data = await getTrainETA(trainData.train_number); if (active && version === searchVersion.current) { setTrainData(data); setError(null); } }
      catch { if (active && version === searchVersion.current) setError('Refresh failed. Showing the last received train report.'); }
      finally { pending = false; }
    };
    const interval = setInterval(refresh, historical ? 5000 : 30000);
    return () => { active = false; clearInterval(interval); };
  }, [trainData?.train_number, historical]);
  const clearSelection = () => { ++searchVersion.current; setTrainData(null); setError(null); setLoading(false); };
  const goHome = () => { clearSelection(); window.scrollTo({ top: 0, behavior: 'smooth' }); };
  const trains = corridorData?.trains || [];

  return <div className="app-shell">
    <Navigation sourceLabel={corridorData?.data_mode === 'corridor_simulation' ? 'Simulation only' : undefined} historical={corridorData ? historical : null} onHome={goHome} />
    <main id="main-content">
      <div className="hero-stage">
        <HeroTrack />
      <section className="hero" aria-labelledby="hero-title">
        <div className="hero-copy"><p className="hero-kicker"><span /> A new perspective on rail</p><RevealText as="h1" id="hero-title" text={'Move beyond delays.\nSee the bigger picture.'} /><p className="hero-description">A little less guessing. A lot more clarity. Explore your train’s delay, understand the prediction, and see the data behind every number.</p><div className="hero-actions"><KiroButton className="primary-button" href="#train-search"><TrainFront /><span>Explore trains</span><ArrowUpRight /></KiroButton></div><p className="hero-footnote">Built for Indian Railways. Open about the data.</p></div>
        <aside className="hero-notes" aria-label="About this demo"><p className="eyebrow"><span className="square-dot" /> A little more context</p><div><span>01 / FIND</span><strong>Start with a train.</strong><p>Search a number. Open its report.</p></div><div><span>02 / UNDERSTAND</span><strong>Look beyond the delay.</strong><p>Recorded averages, predictions, and the difference.</p></div><div><span>03 / TRUST</span><strong>See what we know.</strong><p>Sources and limitations, always in view.</p></div></aside>
      </section>
      </div>

      <section className="explorer-frame" id="train-search" aria-labelledby="explorer-title">
        <div className="frame-heading"><div><p>THE TRAIN EXPLORER</p><h2 id="explorer-title">Your train. The full picture.</h2></div><span className="frame-decoration" aria-hidden="true"><span /><RailMark /><span /></span></div>
        <div className="explorer-window"><div className="window-bar"><span className="window-dots" aria-hidden="true"><i /><i /><i /></span><span className="window-title"><RailMark /> RailETA <span>/</span> train explorer</span><span className="window-mode"><i />{corridorData?.data_mode === 'corridor_simulation' ? 'Simulation · trained LightGBM' : corridorData ? historical ? 'Historical profiles' : 'Prototype events' : 'Connecting to data'}</span></div>
          <div className="explorer-body"><div className="explorer-intro"><div><p className="eyebrow">{historical ? 'Find a delay profile' : 'Find your train'}</p><h3>Where does your journey begin?</h3></div><KiroButton variant="outline" className="utility-button refresh-reports" type="button" disabled={loading || rosterLoading} aria-label={trainData ? 'Refresh report' : 'Refresh train list'} onClick={() => { if (trainData) handleSearch(trainData.train_number); else { setRosterLoading(true); setRefreshKey(value => value + 1); } }}><RefreshCw className={loading || rosterLoading ? 'animate-spin' : ''} /><span>Refresh</span></KiroButton></div>
            <TrainSearch trains={trains} onSearch={handleSearch} loading={loading} historical={historical} />
            <details className="jt-operational"><summary>Choose a journey date · station timeline & forecast history</summary><JourneyWorkspace trainNumber={trainData?.train_number || ''} initialMode={corridorData?.data_mode === 'corridor_simulation' ? 'simulation' : 'live'} initialDate={corridorData?.data_mode === 'corridor_simulation' ? corridorData.scenario_date : undefined} /></details>
            {rosterError && <div role="alert" className="inline-alert"><AlertCircle /><p>{rosterError}</p><button type="button" onClick={() => setRefreshKey(value => value + 1)}>Retry <RefreshCw /></button></div>}
            <div className="report-region" aria-label="Train reports" aria-busy={loading}>
              {(trainData || error || loading) && <button className="back-button" type="button" onClick={clearSelection}><ArrowLeft /> Back to trains</button>}
              {error && <div role="alert" className="inline-alert error"><AlertCircle /><p>{error}</p></div>}
              {loading && <div className="report-loading" role="status"><RefreshCw className="animate-spin" /><p>Finding the full picture…</p><span>Reading the latest available train record.</span></div>}
              {trainData && !loading && (trainData.journey ? <JourneyDetail journey={trainData.journey} /> : trainData.data_mode === 'historical_replay' ? <HistoricalReplayDetail train={trainData} /> : <EventReport train={trainData} />)}
              {!trainData && !loading && !error && <TrainRoster historical={historical} trains={trains} loading={rosterLoading} onSearch={handleSearch} />}
            </div>
            <div className="data-caption"><span className="square-dot" /><p>{corridorData?.data_mode === 'corridor_simulation' ? corridorData.note : historical ? 'Historical profile replay · held-out trains · provenance unverified. Station averages, not live journeys or arrival times.' : 'Prototype station events. Check each report for its source, freshness, and model status.'}</p><span className="caption-mark">RAILETA / 01</span></div>
          </div>
        </div><div className="frame-footer"><span>{trains.length} trains in the current dataset</span><span>Read the profile. Understand the context.</span></div>
      </section>

      <section className="how-section" id="how-it-works" aria-labelledby="how-title"><p className="eyebrow">Less noise. More understanding.</p><RevealText id="how-title" text={'Built for the way\nyou read a journey.'} /><div className="feature-grid">
        <article><div className="feature-top"><TrainFront /><span>01</span></div><h3>Start with your train.</h3><p>Enter a train number or pick a profile. Get the available information in one focused, readable report.</p></article>
        <article><div className="feature-top"><BarChart3 /><span>02</span></div><h3>Look past the number.</h3><p>Compare recorded delays with model predictions. See which inputs influenced the result, and by how much.</p></article>
        <article><div className="feature-top"><Layers /><span>03</span></div><h3>Know what’s underneath.</h3><p>Source context, uncertainty, and evaluation results stay with the data. A prediction should be something you can inspect.</p></article>
      </div></section>
      <section className="data-section" id="data-notes"><div><p className="eyebrow">Context is part of the picture</p><RevealText text={'Real clarity.\nHonest limits.'} /><p>{historical ? 'This demo explores recorded station-delay averages from the supplied dataset. The model is evaluated on trains it did not see during training.' : corridorData?.data_mode === 'corridor_simulation' ? 'This demo follows published Chennai–Bengaluru train routes using five years of generated journeys. LightGBM learns arrival estimates from these synthetic events, with separate calibration and test dates.' : 'This prototype explores station-event reports and mock arrival forecasts. Production forecasting depends on validated models and authorized railway feeds.'}</p></div><div className="data-notes"><div><span>01</span><p><strong>{historical ? 'Historical, not live' : 'Source comes first'}</strong>{historical ? 'Profiles describe averages. They cannot locate a train or tell you when it will arrive today.' : 'Each report identifies its source and whether the last event is stale.'}</p></div><div><span>02</span><p><strong>Predictions with context</strong>Model contributions describe associations. They are not proof of what caused a delay.</p></div><div><span>03</span><p><strong>Limitations stay visible</strong>{historical ? 'Dataset provenance is unverified. Actual test coverage and error are shown in each profile.' : corridorData?.data_mode === 'corridor_simulation' ? 'Synthetic test coverage is not proof of real-world accuracy. The harder disruption scenario shows why official operational validation is still needed.' : 'Mock arrival windows have not yet been validated against real train outcomes.'}</p></div></div></section>
      <TrackJourney />
    </main><footer className="site-footer"><a className="rail-brand" href="#main-content"><RailMark /><span>RAILETA</span></a><p>Arrival intelligence, thoughtfully presented.</p><div><a href={surfaceUrl('controller')}>Operations ↗</a><a href={surfaceUrl('station')}>Station board ↗</a><span>Made for the journey.</span></div></footer>
  </div>;
}

function TrainRoster({ trains, historical, loading, onSearch }) {
  const [expanded, setExpanded] = useState(false);
  const [sort, setSort] = useState('default');
  const sorted = [...trains];
  if (sort === 'delay') sorted.sort((a, b) => (Number.isFinite(b.delay_minutes) ? b.delay_minutes : -Infinity) - (Number.isFinite(a.delay_minutes) ? a.delay_minutes : -Infinity));
  if (sort === 'number') sorted.sort((a, b) => String(a.train_number).localeCompare(String(b.train_number), undefined, { numeric: true }));
  const visible = expanded ? sorted : sorted.slice(0, 6);
  return <section className="train-roster"><div className="roster-heading"><div><h4>{historical ? 'Held-out train profiles' : 'Available trains'}</h4><p>{historical ? 'Recorded average delays' : 'Latest reported delays'} · minutes</p></div><label className="roster-sort"><span>Sort by</span><select aria-label="Sort trains" value={sort} onChange={event => setSort(event.target.value)}><option value="default">Default order</option><option value="delay">Highest delay</option><option value="number">Train number</option></select></label></div>
    {loading ? <p className="empty-roster" role="status">Loading available trains…</p> : !trains.length ? <p className="empty-roster">No train records available yet. You can still search by train number.</p> : <div className="roster-grid">{visible.map(train => <button className="roster-train" type="button" key={train.train_number} onClick={() => onSearch(train.train_number)}><span className="train-number">{train.train_number}</span><span className="train-copy"><strong>{train.train_name}</strong><small>{historical ? 'Profile station' : 'Last reported'} <span>{train.current_station || '—'}</span></small></span><span className="train-delay">{Number.isFinite(train.delay_minutes) ? Math.round(train.delay_minutes) : '—'}<small>min</small></span><ArrowUpRight /></button>)}</div>}
    {!loading && trains.length > 6 && <div className="roster-footer"><span>Showing {visible.length} of {trains.length} trains</span><KiroButton variant="outline" className="utility-button" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>{expanded ? 'Show fewer trains' : 'Show all ' + trains.length + ' trains'}<span aria-hidden="true">{expanded ? '−' : '+'}</span></KiroButton></div>}
  </section>;
}

function EventReport({ train }) {
  const status = train.current_status || {};
  return <div className="event-report animate-enter"><section className="solid-panel p-6"><div className="event-summary"><div><p className="eyebrow"><Activity /> Station-event report</p><h2>{train.train_name}</h2><p className="text-sm text-slate-400">Train {train.train_number} · {train.train_class}</p></div><div className="event-delay"><span>Current delay</span><strong>{Number.isFinite(status.current_delay_minutes) ? Math.round(status.current_delay_minutes) : '—'} <small>min</small></strong></div></div><p className="mt-6 text-sm text-slate-400">Last reported: <strong>{status.last_reported_station || '—'}</strong> <span className="mx-3">→</span> Next: <strong>{status.next_station || '—'}</strong></p></section><p className="text-xs text-slate-400">{train.data_mode === 'simulated' ? 'Simulated CRIS events' : train.fallback_source} · Mock ETAs and reason codes · {train.is_stale ? 'Stale input; last position held' : 'Recent source event'}</p>
    <JourneyProgress train={train} />
    <details className="report-details solid-panel"><summary><span>View route map</span><span aria-hidden="true">+</span></summary><RouteNavigator stations={train.upcoming_stations || []} routeGeometry={train.route_geometry} currentStation={status.last_reported_station} /></details>
    {(train.weather_observations || []).length > 0 && <section className="solid-panel p-5"><p className="eyebrow mb-4">Weather context · Open-Meteo model</p><div className="grid grid-cols-2 gap-4 sm:grid-cols-4">{train.weather_observations.filter(item => ['MAS', 'KPD', 'JTJ', 'SBC'].includes(item.station_code)).map(item => <div key={item.station_code}><p className="text-sm text-slate-400">{item.station_code}</p><strong className="text-xl text-violet-200">{item.data?.temperature_c == null ? '—' : `${Math.round(item.data.temperature_c)}°C`}</strong><p className="text-xs text-slate-500">{item.data?.visibility_m == null ? 'Visibility —' : `Visibility ${(item.data.visibility_m / 1000).toFixed(1)} km`}</p></div>)}</div></section>}
    {!!train.overall_delay_reasons?.length && <section className="solid-panel p-5"><h3 className="mb-4">What is affecting this journey</h3><div className="grid gap-3 sm:grid-cols-2">{train.overall_delay_reasons.map((reason, index) => <DelayChip key={index} reason={reason} />)}</div></section>}
    <h3 className="text-xl">Upcoming arrivals</h3>{(train.upcoming_stations || []).map((station, index) => <StationCard key={station.station_code} station={station} isNext={index === 0} />)}<p className="text-xs text-slate-500">Last updated {train.last_updated ? new Date(train.last_updated).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata' }) : 'awaiting data'} · Mock prediction window · calibration not yet validated</p>
  </div>;
}
