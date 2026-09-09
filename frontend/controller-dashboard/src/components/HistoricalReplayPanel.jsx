import React from 'react';
import { X } from 'lucide-react';

const dateTime = value => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) + ' IST' : 'Unavailable';
const decimal = value => Number.isFinite(value) ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(value) : '—';

export default function HistoricalReplayPanel({ train, onClose }) {
  const replay = train.historical_replay || {};
  const metrics = replay.test_metrics || {};
  const forecast = train.upcoming_stations?.[0];
  const aggregate = train.dataset_kind === 'aggregate_profiles';
  const recorded = aggregate ? replay.recorded_average_delay_minutes : replay.actual_delay_minutes;
  const predicted = aggregate ? replay.predicted_average_delay_minutes : replay.predicted_delay_minutes;
  return <section className="ops-panel train-focus-panel">
    <header className="focus-header"><div><p className="ops-eyebrow">Selected train</p><h2>{train.train_name}</h2><span>Train {train.train_number} · {replay.station_name || replay.destination_name || 'Station unavailable'}{replay.station_code ? ` (${replay.station_code})` : ''}</span></div><button type="button" className="ops-icon-button" onClick={onClose} title="Close train view" aria-label="Close train view"><X /></button></header>
    <p className="ops-report-notice">Historical record · not live</p>
    <dl className="ops-report-metrics">
      <div><dt>{aggregate ? 'Past average delay' : 'Recorded delay'}</dt><dd>{decimal(recorded)} <small>min</small></dd></div>
      <div><dt>RailETA estimate</dt><dd>{decimal(predicted)} <small>min</small></dd></div>
      <div><dt>Difference</dt><dd>{decimal(replay.absolute_error_minutes)} <small>min</small></dd></div>
    </dl>
    <p className="ops-report-context">{aggregate ? 'The estimate is for a past station average, not today’s journey.' : 'The estimate is for a recorded journey, not today’s arrival.'} No live location is available.</p>
    <dl className="ops-key-values"><div><dt>Data collected</dt><dd>{dateTime(replay.scraped_at)}</dd></div><div><dt>Record replayed</dt><dd>{dateTime(replay.replayed_at)}</dd></div><div><dt>Source status</dt><dd>Not independently verified</dd></div></dl>
    <details className="ops-disclosure" key={train.train_number}><summary>Model details & reliability</summary><div className="ops-disclosure-body">
      <h3>Estimate range</h3><p>{aggregate ? `${decimal(replay.lower_minutes)}–${decimal(replay.upper_minutes)} min for the average. This is not an arrival-time window.` : `${dateTime(forecast?.confidence_lower)} – ${dateTime(forecast?.confidence_upper)}.`} The range was calibrated on training data with an 80% target.</p>
      <h3>Test results</h3><dl className="ops-key-values"><div><dt>Average prediction error</dt><dd>{decimal(metrics.mae_minutes)} min</dd></div><div><dt>Records within the range</dt><dd>{decimal(metrics.coverage_percent)}% (target: 80%)</dd></div><div><dt>Test set</dt><dd>{metrics.n_test ?? '—'} records · {metrics.test_trains ?? '—'} trains</dd></div><div><dt>Simple baseline error</dt><dd>{decimal(metrics.train_median_baseline_mae_minutes)} min</dd></div></dl><p>Test trains were excluded from training. These results do not guarantee accuracy for an individual journey.</p>
      <h3>What influenced the estimate</h3><p>Signed SHAP effects relative to a {decimal(replay.shap_base_minutes)} min baseline. These are associations, not proven causes of delay.</p><div className="ops-factor-rows">{(train.overall_delay_reasons || []).slice(0, 3).map((reason, index) => <div key={index}><span>{reason.description}<small>{reason.category}</small></span><strong>{Number.isFinite(reason.minutes) && reason.minutes > 0 ? '+' : ''}{decimal(reason.minutes)} min</strong></div>)}</div>
      {!aggregate && <><h3>Original journey</h3><dl className="ops-key-values"><div><dt>Scheduled arrival</dt><dd>{dateTime(replay.original_scheduled_arrival)}</dd></div><div><dt>Actual arrival</dt><dd>{dateTime(replay.original_actual_arrival)}</dd></div><div><dt>Predicted arrival</dt><dd>{dateTime(forecast?.predicted_arrival)}</dd></div></dl></>}
      <h3>Source & model</h3><p>{aggregate ? 'Supplied etrain export of train–station averages. No schedules, GPS, movement events, or weather are supplied.' : 'Supplied historical arrival records, not a live feed.'} Source authenticity has not been independently verified. Collection and replay timestamps are not train-location updates.</p><dl className="ops-key-values"><div><dt>Model</dt><dd>{train.model_version || 'Unavailable'}</dd></div><div><dt>Record</dt><dd>{replay.record_id || 'Unavailable'}</dd></div></dl>
    </div></details>
  </section>;
}
