import React, { useCallback, useEffect, useMemo, useState, useRef } from 'react';
import { CloudSun, TrainFront } from 'lucide-react';
import Navigation from '../../shared/Navigation';
import { OperationalTools } from '../../shared/JourneyTools';
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
  const focusPanel = useRef(null);
  const historical = corridorData?.data_mode === 'historical_replay';

  useEffect(() => {
    if (selectedTrain?.train_number && window.innerWidth < 1100) focusPanel.current?.scrollIntoView({ behavior: 'instant', block: 'start' });
  }, [selectedTrain?.train_number]);

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
    <Navigation active="controller" sourceLabel={corridorData?.data_mode === 'corridor_simulation' ? 'Simulation only' : undefined} historical={corridorData ? historical : null} onRefresh={handleRefresh} refreshing={refreshing || detailLoading} />
    <main className="ops-main" id="main-content">
      <header className="ops-intro"><div><p className="ops-eyebrow">Controller dashboard</p><h1>Train overview</h1><p>{historical ? 'Compare recorded delays and model estimates across your trains.' : 'Review reported delays, station updates, and upcoming arrivals.'}</p></div><div className="ops-update"><span className="ops-mode">{corridorData?.data_mode === 'corridor_simulation' ? 'SIMULATION · generated journeys' : historical ? 'Historical records · not live' : corridorData ? 'Prototype station feed' : 'Connecting to data'}</span><p>{lastUpdate && Number.isFinite(lastUpdate.getTime()) ? (corridorData?.data_mode === 'corridor_simulation' ? 'Scenario time ' : 'Source updated ') + lastUpdate.toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : 'Awaiting source data'}</p><small>Auto-refresh every {historical ? '5' : '30'} seconds</small></div></header>
      {error && <p role="alert" className="ops-panel ops-alert">{error}</p>}
      {loading ? <div className="ops-loading" role="status"><span>Loading train records…</span></div> : <div className="ops-workspace">
        <section className="ops-stats" aria-label="Train delay summary"><Stat label="All trains" value={corridorData ? corridorData.trains?.length ?? 0 : '—'} accent="violet" /><Stat label="Under 10 min" value={corridorData ? stats.onTime : '—'} accent="emerald" /><Stat label="10–29 min" value={corridorData ? stats.attention : '—'} accent="amber" /><Stat label="30+ min" value={corridorData ? stats.late : '—'} accent="rose" /></section>
        <p className="ops-data-note">{corridorData?.data_mode === 'corridor_simulation' ? corridorData.note : historical ? 'Delay bands show past station averages, not today’s delays. Source not independently verified.' : 'Delay bands use the latest received station reports. Missing delay values are excluded from bands.'}</p>
        <div className="ops-board">
          <CorridorMap corridorData={corridorData} onTrainClick={handleTrainClick} selectedTrainNumber={selectedNumber} />
          <aside className="ops-detail-column" aria-label="Selected train details">
            {detailError && <div role="alert" className="ops-panel ops-alert"><p>{detailError}</p><button type="button" className="ops-action" disabled={detailLoading} onClick={() => setDetailRefresh(value => value + 1)}>Retry selected train</button></div>}
            {selectedTrain ? <div ref={focusPanel} className="ops-focus-anchor"><TrainDetailPanel train={selectedTrain} onClose={() => { setSelectedNumber(null); setSelectedTrain(null); setDetailError(null); setDetailLoading(false); }} /></div> : <section className="ops-empty-selection" aria-live="polite"><TrainFront /><div><h2>{selectedNumber ? (detailLoading ? `Loading train ${selectedNumber}` : `Train ${selectedNumber} is unavailable`) : 'Select a train'}</h2><p>{selectedNumber ? 'Its report will appear here when available.' : 'Choose a row to view delays, estimates, and source details.'}</p></div></section>}
          </aside>
        </div>
        <OperationalTools initialMode={corridorData?.data_mode === 'corridor_simulation' ? 'simulation' : 'live'} initialDate={corridorData?.data_mode === 'corridor_simulation' ? corridorData.scenario_date : undefined} />
        {!historical && <WeatherStrip observations={corridorData?.weather_observations || []} />}
      </div>}
    </main>
    <footer className="ops-footer">RailETA Operations <span>·</span> {historical ? 'Past records only · no live train positions or arrival forecasts' : 'Prototype forecasts · check source freshness before use'}</footer>
  </div>;
}

function Stat({ label, value, accent }) { return <div className={`ops-stat ops-stat-${accent}`}><p>{label}</p><strong>{value}</strong></div>; }
function WeatherStrip({ observations }) {
  const visible = observations.filter((item) => ['MAS', 'KPD', 'JTJ', 'SBC'].includes(item.station_code));
  if (!visible.length) return null;
  const latest = visible.map((item) => item.event_time).filter(Boolean).sort().at(-1);
  return <section className="ops-panel p-4"><div className="mb-3 flex items-center justify-between gap-3"><span className="ops-eyebrow"><CloudSun /> Corridor weather context</span><small className="text-right text-[10px] text-slate-500">Open-Meteo current model · station coordinates{latest ? ` · ${new Date(latest).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}</small></div><div className="grid grid-cols-2 gap-2 sm:grid-cols-4">{visible.map((item) => { const data = item.data || {}; return <div className="rounded-xl border border-[#332d3c] bg-[#211c28] p-3" key={item.station_code}><strong className="block text-xs text-slate-200">{item.station_code}</strong><span className="mt-1 block text-lg font-semibold text-violet-100">{data.temperature_c == null ? '—' : `${Math.round(data.temperature_c)}°C`}</span><small className="block text-[10px] text-slate-500">{data.visibility_m == null ? 'Visibility —' : `Visibility ${(data.visibility_m / 1000).toFixed(1)} km`}</small></div>; })}</div></section>;
}
export default App;
