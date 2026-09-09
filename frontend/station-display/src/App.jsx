/**
 * Station Display Board App
 * Solid-surface departure board and historical-data context.
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import Header from './components/Header';
import DisplayRow from './components/DisplayRow';
import Ticker from './components/Ticker';
import KiroButton from '../../shared/KiroButton';
import Navigation, { RailMark, surfaceUrl } from '../../shared/Navigation';
import { ArrivalsPanel } from '../../shared/JourneyTools';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

function App() {
  const [boardView, setBoardView] = useState('departures');
  const [arrivalsRefresh, setArrivalsRefresh] = useState(0);
  const [departures, setDepartures] = useState([]);
  const [stationCode, setStationCode] = useState('MAS');
  const [stationName, setStationName] = useState('CHENNAI CENTRAL');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState(null);
  const [dataMode, setDataMode] = useState(null);
  const [sourceNote, setSourceNote] = useState('');
  const historical = dataMode === 'historical_replay';
  const activeRequest = useRef(null);

  // Fetch departures
  const fetchDepartures = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setRefreshing(true);
    try {
      const response = await axios.get(
        `${API_BASE_URL}/stations/${stationCode}/departures`,
        { params: { limit: 12 }, signal: controller.signal, timeout: 10000 }
      );
      if (controller.signal.aborted) return;
      setDepartures(response.data.departures || []);
      setDataMode(response.data.data_mode || null);
      setSourceNote(response.data.note || '');
      setError(null);
    } catch (err) {
      if (controller.signal.aborted) return;
      console.error('Error fetching departures:', err);
      setError('Failed to fetch data');
    } finally {
      if (!controller.signal.aborted) { setLoading(false); setRefreshing(false); }
    }
  }, [stationCode]);

  // Initial fetch and auto-refresh every 30 seconds
  useEffect(() => {
    setLoading(true);
    setDepartures([]);
    setError(null);
    fetchDepartures();
    const interval = setInterval(fetchDepartures, 30000);
    return () => { clearInterval(interval); activeRequest.current?.abort(); };
  }, [fetchDepartures]);

  // Keyboard shortcuts for demo
  useEffect(() => {
    const handleKeyPress = (e) => {
      if (boardView === 'arrivals' || e.target.closest?.('input,select,textarea,[contenteditable="true"]')) return;
      if (historical && e.key.toLowerCase() !== 'r') return;
      if (e.key === '1') {
        setStationCode('MAS');
        setStationName('CHENNAI CENTRAL');
      } else if (e.key === '2') {
        setStationCode('KPD');
        setStationName('KATPADI JUNCTION');
      } else if (e.key === '3') {
        setStationCode('SBC');
        setStationName('KSR BENGALURU');
      } else if (e.key.toLowerCase() === 'r') {
        fetchDepartures();
      }
    };

    window.addEventListener('keypress', handleKeyPress);
    return () => window.removeEventListener('keypress', handleKeyPress);
  }, [fetchDepartures, historical, boardView]);

  return <div className="station-app">
    <Navigation active="station" sourceLabel={dataMode === 'corridor_simulation' ? 'Simulation only' : undefined} historical={boardView === 'arrivals' ? null : dataMode ? historical : null} onRefresh={boardView === 'arrivals' ? () => setArrivalsRefresh(value => value + 1) : fetchDepartures} refreshing={boardView === 'departures' && (loading || refreshing)} />
    <main id="main-content" className="station-main">
      {boardView === 'departures' ? <Header stationName={stationName} stationCode={stationCode} historical={historical} /> : <header><h1>Station arrivals</h1><p className="jt-note">Choose a station, time window and data source below.</p></header>}
      <div className="jt-tabs" aria-label="Station board view"><button aria-pressed={boardView === 'departures'} onClick={() => setBoardView('departures')}>Departures</button><button aria-pressed={boardView === 'arrivals'} onClick={() => setBoardView('arrivals')}>Expected arrivals</button></div>
      {boardView === 'arrivals' ? <ArrivalsPanel stationCode={stationCode} refreshKey={arrivalsRefresh} initialMode={dataMode === 'corridor_simulation' ? 'simulation' : 'live'} /> : <section className="board-frame" aria-label="Station departure board">
        <div className="board-label"><span>{historical ? 'THE DATASET VIEW' : 'THE DEPARTURE BOARD'}</span><span>INDIA STANDARD TIME / UTC +05:30</span></div>
        <div className="board-surface">
          <div className="board-toolbar"><span><RailMark />{historical ? 'Aggregate profile replay' : 'Departures'}</span>{!historical && <label>Station <select aria-label="Station" value={stationCode} onChange={e => { const code = e.target.value; setStationCode(code); setStationName({ MAS: 'CHENNAI CENTRAL', KPD: 'KATPADI JUNCTION', SBC: 'KSR BENGALURU' }[code]); }}><option value="MAS">Chennai Central</option><option value="KPD">Katpadi Junction</option><option value="SBC">KSR Bengaluru</option></select></label>}</div>
          {loading && <div className="board-empty" role="status"><RailMark /><h2>Reading station data…</h2><p>The latest available information will appear here.</p></div>}
          {error && !loading && <div className="board-empty" role="alert"><RailMark /><p className="eyebrow">Connection interrupted</p><h2>Station data is unavailable.</h2><p>We could not refresh this board. Please try again.</p><KiroButton onClick={fetchDepartures}>Retry connection ↻</KiroButton></div>}
          {!loading && !error && departures.length === 0 && <div className="board-empty"><span className="empty-rail-mark"><RailMark /></span><p className="eyebrow">{historical ? 'DEPARTURE DATA NOT AVAILABLE' : 'NO DEPARTURES SCHEDULED'}</p><h2>{historical ? <>A different kind<br />of train data.</> : <>A quiet moment<br />at the station.</>}</h2><p>{historical ? sourceNote || 'This dataset contains average delays, not arrival/departure events or schedules.' : 'No departures are available in the latest station report.'}</p>{historical && <><p className="board-source">Historical dataset replay · held-out trains · provenance unverified.</p><KiroButton className="board-button" href={surfaceUrl('passenger')}>Explore delay profiles <span aria-hidden="true">↗</span></KiroButton></>}</div>}
          {!loading && !error && departures.length > 0 && <div className="departure-table"><DisplayRow isHeader /><div>{departures.map((departure, index) => <DisplayRow key={departure.train_number + '-' + index} departure={departure} />)}</div></div>}
        </div>
        <div className="board-footnote"><span>{historical ? 'Station averages. No movement events or schedules.' : 'Station-event estimates. Check source before operational use.'}</span><span><kbd>R</kbd> Refresh{!historical && <> · <kbd>1</kbd> Chennai · <kbd>2</kbd> Katpadi · <kbd>3</kbd> Bengaluru</>}</span></div>
      </section>}
    </main>
    <Ticker message={historical ? 'Historical dataset replay · Held-out trains · Provenance unverified · Aggregate profiles only — no movement events or schedules' : 'RailETA prototype · Check row source data before operational use · Forecasts are mock; 80% coverage is an unvalidated target'} />
    <footer className="station-footer"><span>RAILETA / STATION BOARD</span><span>A clearer view of the journey.</span></footer>
  </div>;
}
export default App;
