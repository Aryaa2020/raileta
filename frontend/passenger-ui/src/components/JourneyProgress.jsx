import React from 'react';
import { Check, TrainFront } from 'lucide-react';

export default function JourneyProgress({ train }) {
  const historical = train.data_mode === 'historical_replay' || train.dataset_kind === 'aggregate_profiles';
  const stops = (train.route_stops || []).filter(stop => stop.stop !== false && stop.station_code);
  const current = train.current_status?.last_reported_station;
  const matches = stops.filter(stop => stop.station_code === current);
  const index = matches.length === 1 ? stops.findIndex(stop => stop.station_code === current) : -1;
  const available = !historical && stops.length >= 2 && index >= 0;
  const percent = available ? Math.round(index / (stops.length - 1) * 100) : null;
  const eventTime = train.current_status?.last_reported_time;
  const time = eventTime && Number.isFinite(Date.parse(eventTime))
    ? new Date(eventTime).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : null;

  return <section className={`journey-progress ${available ? 'has-progress' : 'no-progress'}`} aria-label="Journey progress">
    <div className="journey-progress-heading"><div><h3>Journey progress</h3><p>{available ? `${index + 1} of ${stops.length} stations reached` : 'Current location is not available'}</p></div><span className="journey-progress-value">{available ? `${percent}%` : 'Not live'}</span></div>
    {available ? <>
      <div className="progress-a11y" role="progressbar" aria-label="Journey progress based on station reports" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent} aria-valuetext={`${index + 1} of ${stops.length} stations reached. ${percent}% between the first and last stop. ${train.is_stale ? 'Based on an older report.' : ''}`} />
      <div className="journey-stations-scroller" tabIndex={0} aria-label="Route stations"><ol className="journey-stations" style={{ gridTemplateColumns: `repeat(${stops.length}, minmax(100px, 1fr))` }}>
        {stops.map((stop, stopIndex) => <li key={`${stop.station_code}-${stopIndex}`} className={`${stopIndex <= index ? 'is-reached' : ''} ${stopIndex === index ? 'is-current' : ''}`} aria-current={stopIndex === index ? 'step' : undefined}>
          <span className="journey-station-point">{stopIndex === index ? <TrainFront /> : stopIndex < index ? <Check /> : null}</span><strong>{stop.station_name || stop.name || stop.station_code}</strong><span>{stopIndex === index ? 'Last reported here' : stopIndex < index ? 'Reached' : stopIndex === stops.length - 1 ? 'Destination' : 'Ahead'}</span>
        </li>)}
      </ol></div>
      <p className="journey-progress-note">{train.data_mode === 'simulated' ? 'Demo station updates. ' : ''}Progress is based on stops reached, not distance or time.{train.is_stale ? ' This report is old; the train may have moved.' : ''}{time ? ` Last report: ${time} IST.` : ''}</p>
    </> : <>
      <div className="journey-placeholder" aria-hidden="true"><div><i /><span>Start</span></div><div><i /><span>Location unknown</span></div><div><i /><span>Finish</span></div></div>
      <p className="journey-progress-note">{historical ? 'This record contains past delays, not today’s train location. Station updates are needed to show how much of the journey is done.' : 'There are not enough station updates to calculate progress yet.'}</p>
    </>}
  </section>;
}
