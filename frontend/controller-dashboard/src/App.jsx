import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { Activity, CloudSun, RefreshCw, Route, TrainFront } from 'lucide-react';
import CorridorMap from './components/CorridorMap';
import TrainDetailPanel from './components/TrainDetailPanel';
import { getCorridorStatus, getTrainETA } from './services/api';

function App() {
  const [corridorData, setCorridorData] = useState(null);
  const [selectedTrain, setSelectedTrain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [error, setError] = useState(null);
  const [detailError, setDetailError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailRefresh, setDetailRefresh] = useState(0);
  const [selectedNumber, setSelectedNumber] = useState(null);
  const corridorRequest = useRef(null);
  const historical = corridorData?.data_mode === 'historical_replay';

  const fetchCorridorData = useCallback(async () => {
    // Do not cancel a slow but valid response every time the polling timer
    // fires. Cleanup still cancels requests when this effect is superseded.
    if (corridorRequest.current && !corridorRequest.current.signal.aborted) return;
    const controller = new AbortController();
    corridorRequest.current = controller;
    setRefreshing(true);
    try {
      const data = await getCorridorStatus('MAS-SBC', { signal: controller.signal });
      if (controller.signal.aborted) return;
      setCorridorData(data);
      setLastUpdate(data.timestamp ? new Date(data.timestamp) : null);
      setError(null);
    } catch (error) {
      if (controller.signal.aborted) return;
      console.error('Error fetching corridor data:', error);
      setError('Corridor refresh failed. Previously received data may be stale.');
    } finally {
      if (!controller.signal.aborted) {
        if (corridorRequest.current === controller) corridorRequest.current = null;
        setRefreshing(false);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    fetchCorridorData();
    const interval = setInterval(fetchCorridorData, historical ? 5000 : 30000);
    return () => { corridorRequest.current?.abort(); clearInterval(interval); };
  }, [historical, fetchCorridorData]);

  const handleRefresh = () => {
    fetchCorridorData();
    setDetailRefresh((value) => value + 1);
  };

  const handleTrainClick = (train) => {
    if (selectedNumber === train.train_number) return;
    setSelectedTrain(null);
    setDetailError(null);
    setDetailLoading(true);
    setSelectedNumber(train.train_number);
  };

  useEffect(() => {
    if (!selectedNumber) return undefined;
    let active = true;
    let pending = false;
    const controller = new AbortController();
    setDetailLoading(true);
    const refresh = async () => {
      if (pending) return;
      pending = true;
      try {
        const data = await getTrainETA(selectedNumber, { signal: controller.signal });
        if (active) {
          setSelectedTrain(data);
          setDetailError(null);
        }
      } catch {
        if (active) setDetailError('Selected train refresh failed. Its last report may be stale.');
      } finally {
        pending = false;
        if (active) setDetailLoading(false);
      }
    };
    refresh();
    const interval = setInterval(refresh, historical ? 5000 : 30000);
    return () => { active = false; controller.abort(); clearInterval(interval); };
  }, [selectedNumber, historical, detailRefresh]);

  const stats = useMemo(() => ({
    onTime: corridorData?.trains?.filter((train) => Number.isFinite(train.delay_minutes) && train.delay_minutes < 10).length || 0,
    attention: corridorData?.trains?.filter((train) => Number.isFinite(train.delay_minutes) && train.delay_minutes >= 10 && train.delay_minutes < 30).length || 0,
    late: corridorData?.trains?.filter((train) => Number.isFinite(train.delay_minutes) && train.delay_minutes >= 30).length || 0,
  }), [corridorData]);

  return <div className="ops-app min-h-screen">
    <div className="ops-orb ops-orb-one" /><div className="ops-orb ops-orb-two" />
    <header className="ops-header"><div className="ops-header-inner"><div className="ops-brand"><span className="ops-brand-mark"><TrainFront /></span><div><p>RailETA</p><span>Operations desk</span></div></div><div className="ops-header-status"><span className="live-indicator"><i /> {historical ? 'Historical replay' : 'Event feed'}</span><span className="hidden text-xs text-slate-500 lg:block">{historical ? 'Replay refreshed' : 'Updated'} {lastUpdate ? lastUpdate.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', ...(historical ? { dateStyle: 'medium', timeStyle: 'short' } : { hour: '2-digit', minute: '2-digit' }) }) : 'awaiting source data'}</span><button className="ops-icon-button" onClick={handleRefresh} disabled={refreshing || detailLoading} aria-busy={refreshing || detailLoading} title="Refresh corridor and selected train"><RefreshCw className={refreshing || detailLoading ? 'animate-spin' : ''} /></button></div></div></header>
    <main className="ops-main">
      {error && <p role="alert" className="ops-panel p-4 text-amber-200">{error}</p>}
      <section className="ops-intro"><div><div className="ops-eyebrow"><Activity /> {historical ? 'Historical evaluation' : 'Corridor watch'}</div><h1>{historical ? 'Train predictions, made ' : 'Train movement, made '}<span>legible.</span></h1><p>{historical ? 'Inspect held-out station-delay averages and trained-model predictions. These are aggregate profiles, not train movements or the MAS–SBC pilot corridor.' : 'Use station departure and arrival events to monitor the corridor. Select a train for its estimated route progress and next-stop ETA.'}</p></div><div className="ops-disclaimer"><Route /><span><strong>{historical ? 'Held-out historical trains' : 'Station-event estimate'}</strong>{historical ? 'Dataset provenance unverified' : 'Source freshness is shown per forecast'}</span></div></section>
      {loading ? <div className="ops-loading"><RefreshCw className="animate-spin" /><span>Loading corridor signals</span></div> : <div className="space-y-5">
        <section className="ops-stats"><Stat label={historical ? 'Replayed trains' : 'In corridor'} value={corridorData?.total_trains || 0} accent="violet" /><Stat label={historical ? 'Average under 10 min' : 'On schedule'} value={stats.onTime} accent="emerald" /><Stat label={historical ? 'Average 10–29 min' : 'Needs attention'} value={stats.attention} accent="amber" /><Stat label={historical ? 'Average 30+ min' : 'Late'} value={stats.late} accent="rose" /></section>
        {!historical && <WeatherStrip observations={corridorData?.weather_observations || []} />}
        <CorridorMap corridorData={corridorData} onTrainClick={handleTrainClick} selectedTrainNumber={selectedNumber} />
        {detailError && <div role="alert" className="ops-panel flex flex-wrap items-center justify-between gap-3 p-4 text-sm text-amber-200"><p>{detailError}</p><button type="button" className="rounded-lg border border-amber-200/30 px-3 py-2 disabled:opacity-50" disabled={detailLoading} onClick={() => setDetailRefresh((value) => value + 1)}>Retry selected train</button></div>}
        {selectedTrain ? <TrainDetailPanel train={selectedTrain} onClose={() => { setSelectedNumber(null); setSelectedTrain(null); setDetailError(null); setDetailLoading(false); }} /> : <section className="ops-empty-selection" aria-live="polite"><span className="ops-empty-icon">{detailLoading ? <RefreshCw className="animate-spin" /> : <TrainFront />}</span><div><p className="ops-eyebrow">Train focus</p><h2>{selectedNumber ? (detailLoading ? `Loading train ${selectedNumber}` : `Train ${selectedNumber} is unavailable`) : `Select a train to inspect its ${historical ? 'held-out prediction' : 'route view'}`}</h2><p>{selectedNumber ? 'The selected train will appear here when its report is available.' : historical ? 'Compare recorded and predicted station averages, inspect signed SHAP contributions, and review frozen TEST metrics.' : 'The overview remains focused on every train until you need an ETA, station-event progress, or delay factors.'}</p></div></section>}
      </div>}
    </main>
    <footer className="ops-footer">RailETA Operations Desk <span>·</span> {historical ? 'Historical dataset replay · held-out trains · provenance unverified' : 'Estimated progress is derived from reported station events'}</footer>
  </div>;
}

function Stat({ label, value, accent }) { return <div className={`ops-stat ops-stat-${accent}`}><p>{label}</p><strong>{value}</strong></div>; }
function WeatherStrip({ observations }) {
  const visible = observations.filter((item) => ['MAS', 'KPD', 'JTJ', 'SBC'].includes(item.station_code));
  if (!visible.length) return null;
  const latest = visible.map((item) => item.event_time).filter(Boolean).sort().at(-1);
  return <section className="ops-panel p-4"><div className="mb-3 flex items-center justify-between gap-3"><span className="ops-eyebrow"><CloudSun /> Corridor weather context</span><small className="text-right text-[10px] text-slate-500">Open-Meteo current model · station coordinates{latest ? ` · ${new Date(latest).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}</small></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{visible.map((item) => { const data = item.data || {}; return <div className="rounded-xl border border-white/[0.07] bg-black/10 p-3" key={item.station_code}><strong className="block text-xs text-slate-200">{item.station_code}</strong><span className="mt-1 block text-lg font-semibold text-violet-100">{data.temperature_c == null ? '—' : `${Math.round(data.temperature_c)}°C`}</span><small className="block text-[10px] text-slate-500">{data.visibility_m == null ? 'Visibility —' : `Visibility ${(data.visibility_m / 1000).toFixed(1)} km`}</small></div>; })}</div></section>;
}
export default App;
