import React, { useState } from 'react';
import { TrainFront, MapPin, Check } from 'lucide-react';
import { JourneyDetail } from '../../../shared/JourneyTools';
import './passenger-journey.css';

const clock = value => value ? new Date(value).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: '2-digit', hour12: true }) : '—';
const day = value => value ? new Date(value).toLocaleDateString('en-IN', { timeZone: 'Asia/Kolkata', day: 'numeric', month: 'short', year: 'numeric' }) : '';

export default function PassengerJourney({ journey }) {
  const stops = journey.stops || [];
  const [selected, setSelected] = useState(String(stops.at(-1)?.sequence ?? 0));
  const stop = stops.find(item => String(item.sequence) === selected) || stops.at(-1);
  if (!stop) return <p>No station timings have been supplied for this journey.</p>;
  const reached = stops.filter(item => item.actual_arrival || item.actual_departure);
  const last = reached.at(-1);
  const actual = stop.actual_arrival || (!stop.scheduled_arrival && stop.actual_departure);
  const expected = !actual && stop.forecast?.predicted_arrival;
  const scheduled = stop.scheduled_arrival || stop.scheduled_departure;
  const shown = actual || expected;
  const window = stop.forecast;
  const sameWindowDay = window?.confidence_lower && day(window.confidence_lower) === day(window.confidence_upper) && day(window.confidence_lower) === day(expected);
  const difference = shown && scheduled ? Math.round((new Date(shown) - new Date(scheduled)) / 60000) : null;
  const timing = difference === null ? '' : difference === 0 ? 'On time' : `${Math.abs(difference)} min ${difference > 0 ? 'later' : 'earlier'} than scheduled`;
  const heading = actual ? (stop.actual_arrival ? 'Arrived at' : 'Departed at') : expected ? (journey.is_stale ? 'Last arrival estimate' : 'Expected arrival') : 'Waiting for an arrival estimate';
  return <section className="passenger-journey" aria-label="Your journey">
    <p className="pj-source">{journey.mode === 'simulation' ? `SIMULATION ONLY · Demo clock: ${clock(journey.scenario_time)}, ${day(journey.scenario_time)} IST` : 'Station report'}{journey.mode === 'simulation' && <span>Generated train movements. This is not today’s service.</span>}</p>
    <header><span className="pj-train-number"><TrainFront aria-hidden="true" /> {journey.train_number}</span><h2>{journey.train_name}</h2><p>Departure date: {journey.start_date} · All times IST</p></header>
    <div className="pj-layout" tabIndex={-1} role="region" aria-label="Arrival estimate and route"><div className="pj-arrival">
      <label htmlFor={`arrival-${journey.id}`}>Where are you getting off?</label><select id={`arrival-${journey.id}`} aria-label="Your arrival station" value={String(stop.sequence)} onChange={e => setSelected(e.target.value)}>{stops.map(item => <option key={item.sequence} value={item.sequence}>{item.station_name} ({item.station_code})</option>)}</select>
      <div className="pj-arrival-result" aria-live="polite"><p>{heading}</p><strong className="pj-arrival-time">{shown ? clock(shown) : 'Not available yet'}</strong>{shown && <span>{day(shown)} · {stop.station_name}</span>}
      {expected && window?.confidence_lower && window?.confidence_upper && <p className="pj-window">Arrival window: {clock(window.confidence_lower)}{!sameWindowDay && `, ${day(window.confidence_lower)}`} – {clock(window.confidence_upper)}{!sameWindowDay && `, ${day(window.confidence_upper)}`} IST</p>}
      <p className="pj-scheduled">Scheduled {stop.scheduled_arrival ? 'arrival' : 'departure'}: {clock(scheduled)}{scheduled && `, ${day(scheduled)}`}{timing && <span>{timing}</span>}</p>
      {!shown && <p>The timetable is shown above. A prediction will appear when a station report is available.</p>}
      {expected && <p className="pj-estimate-note">An estimate, not a guaranteed arrival time.</p>}
      </div>
      {journey.is_stale && journey.status !== 'completed' && <p className="pj-stale">Waiting for a newer report. Estimates may have changed. Last report: {clock(journey.last_reported_time)}{journey.last_reported_time && `, ${day(journey.last_reported_time)}`} IST.</p>}
    </div><section className="pj-route" aria-label="Journey stops"><div className="pj-route-heading"><h3>Your route</h3><p>Choose a stop to see its arrival time.</p></div><ol>{stops.map((item, index) => {
      const reported = !!(item.actual_arrival || item.actual_departure);
      const atLast = item === last;
      const isSelected = item.sequence === stop.sequence;
      const arrival = item.actual_arrival || item.actual_departure || item.forecast?.predicted_arrival;
      return <li key={item.sequence} className={`${reported ? 'is-reported' : ''} ${atLast ? 'is-last-report' : ''} ${isSelected ? 'is-selected' : ''}`}><button type="button" aria-pressed={isSelected} onClick={() => setSelected(String(item.sequence))}>
        <span className="pj-stop-marker" aria-hidden="true">{atLast ? <TrainFront /> : isSelected ? <MapPin /> : reported ? <Check /> : <i />}</span>
        <span className="pj-stop-copy"><small>{atLast ? 'Last reported stop' : isSelected ? 'Your selected stop' : index === 0 ? 'Starting station' : index === stops.length - 1 ? 'Final station' : reported ? 'Stop completed' : 'Upcoming stop'}</small><strong>{item.station_name}</strong><span>{item.station_code}{arrival ? ` · ${item.actual_arrival ? 'Arrived' : item.actual_departure ? 'Departed' : journey.is_stale ? 'Last estimate' : 'Expected'} ${clock(arrival)}, ${day(arrival)}` : ' · Awaiting report'}</span></span>
      </button></li>;
    })}</ol></section>
    <div className="pj-progress"><label htmlFor={`pj-progress-${journey.id}`}>{journey.status === 'completed' ? 'Journey completed' : last ? `Last reported at ${last.station_name}` : 'Journey not yet reported'}</label><progress id={`pj-progress-${journey.id}`} value={last ? stops.indexOf(last) : 0} max={Math.max(1, stops.length - 1)} /><span>{reached.length} of {stops.length} stops reported · station updates, not live GPS</span></div></div>
    <details className="pj-more"><summary>Full timetable & forecast history</summary><JourneyDetail key={journey.id} journey={journey} /></details>
  </section>;
}
