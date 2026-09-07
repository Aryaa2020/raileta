/**
 * Station Display Board App
 * LED-style display mimicking traditional railway boards
 */
import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import Header from './components/Header';
import DisplayRow from './components/DisplayRow';
import Ticker from './components/Ticker';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

function App() {
  const [departures, setDepartures] = useState([]);
  const [stationCode, setStationCode] = useState('MAS');
  const [stationName, setStationName] = useState('CHENNAI CENTRAL');
  const [loading, setLoading] = useState(true);
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
      if (!controller.signal.aborted) setLoading(false);
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
  }, [fetchDepartures, historical]);

  return (
    <div className="h-screen bg-black flex flex-col">
      {/* Header */}
      <Header stationName={stationName} stationCode={stationCode} historical={historical} />

      {/* Display Board */}
      <div className="flex-1 min-h-0 overflow-auto">
        {loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-6xl font-black led-text text-yellow-400 blink">
              LOADING...
            </div>
          </div>
        )}

        {error && (
          <div className="flex items-center justify-center h-full">
            <div className="text-5xl font-black led-text text-red-500 blink">
              ⚠ ERROR: {error}
            </div>
          </div>
        )}

        {!loading && !error && departures.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="max-w-5xl px-8 text-center font-black led-text text-yellow-400">
              <p className="text-3xl sm:text-5xl">{historical ? 'DEPARTURE DATA NOT AVAILABLE' : 'NO DEPARTURES SCHEDULED'}</p>
              {historical && <><p className="mt-6 text-lg sm:text-2xl">{sourceNote || 'This dataset contains average delays, not arrival/departure events or schedules.'}</p><p className="mt-5 text-sm leading-relaxed text-green-400">Historical dataset replay · held-out trains · provenance unverified.<br />Inspect average-delay predictions in the passenger or controller dashboard.</p></>}
            </div>
          </div>
        )}

        {!loading && !error && departures.length > 0 && (
          <div>
            {/* Column Headers */}
            <DisplayRow isHeader={true} />
            
            {/* Departure Rows */}
            <div className="min-w-0">
              {departures.map((departure, index) => (
                <DisplayRow key={index} departure={departure} />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bottom Ticker */}
      <Ticker message={historical ? '★ Historical dataset replay ★ Held-out trains ★ Provenance unverified ★ Aggregate profiles only — no movement events or schedules ★' : '★ RailETA Prototype ★ Check row source data before operational use ★ Forecasts are mock; 80% coverage is an unvalidated target ★'} />

      {/* Keyboard Shortcuts Info (bottom right corner) */}
      <div className="shrink-0 border-t border-yellow-900 bg-black px-4 py-2 text-xs text-yellow-400">
        <div className="font-bold mb-2">Keyboard Shortcuts:</div>
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          {!historical && <><div>1 - Chennai Central</div>
          <div>2 - Katpadi Jn</div>
          <div>3 - KSR Bengaluru</div></>}
          <div>R - Refresh</div>
        </div>
      </div>

      {/* Branding */}
      <div className="shrink-0 flex items-center justify-center gap-4 border-t border-yellow-900 bg-black px-4 py-2">
        <div className="text-lg font-black led-text text-yellow-300">
          RailETA
        </div>
        <div className="text-xs text-green-400">
          {historical ? 'HISTORICAL DATASET · PROVENANCE UNVERIFIED' : 'DEMO · CHECK SOURCE'}
        </div>
      </div>
    </div>
  );
}

export default App;
