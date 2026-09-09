import React from 'react';
import { ChevronDown, Clock3 } from 'lucide-react';
import JourneyProgress from './JourneyProgress';

const dateTime = value => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' }) : 'Unavailable';
const decimal = value => Number.isFinite(value) ? new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 }).format(value) : '—';
const readableName = value => value && value === value.toUpperCase()
  ? value.toLowerCase().replace(/\b\w/g, letter => letter.toUpperCase()) : value;
const factorName = reason => ({ service_type: 'Type of train', station_name_context: 'Type of station', station_profile: 'The station' }[reason.category] || reason.description);

export default function HistoricalReplayDetail({ train }) {
  const replay = train.historical_replay || {};
  const metrics = replay.test_metrics || {};
  const aggregate = train.dataset_kind === 'aggregate_profiles';
  const recorded = aggregate ? replay.recorded_average_delay_minutes : replay.actual_delay_minutes;
  const predicted = aggregate ? replay.predicted_average_delay_minutes : replay.predicted_delay_minutes;
  const difference = replay.absolute_error_minutes;
  const station = readableName(replay.station_name || replay.destination_name);

  return <div className="simple-report animate-enter">
    <section className="simple-train-summary solid-panel">
      <header className="simple-report-heading"><div><p className="eyebrow">Your train, at a glance</p><h2>{train.train_name}</h2><p className="simple-train-meta">Train {train.train_number}{station ? ` · ${station}` : ''}{replay.station_code ? ` (${replay.station_code})` : ''}</p></div><span className="past-data-badge"><Clock3 /> Past records</span></header>
      <p className="simple-report-intro">{aggregate ? 'Here’s how RailETA’s estimate compares with this train’s past average delay.' : 'Here’s how RailETA’s estimate compares with a recorded journey.'}</p>
      <dl className="simple-delay-metrics">
        <div><dt>{aggregate ? 'Past average delay' : 'Recorded delay'}</dt><dd>{decimal(recorded)} <span>min</span></dd><p>{aggregate ? 'Average lateness in the records' : 'Lateness in this past journey'}</p></div>
        <div><dt>RailETA estimate</dt><dd>{decimal(predicted)} <span>min</span></dd><p>{aggregate ? 'The model’s estimate of that average' : 'The model’s estimate for that journey'}</p></div>
        <div><dt>Difference</dt><dd>{decimal(difference)} <span>min</span></dd><p>{Number.isFinite(predicted) && Number.isFinite(recorded) ? predicted > recorded ? 'The estimate was higher' : predicted < recorded ? 'The estimate was lower' : 'The estimate matched the record' : 'Not enough data to compare'}</p></div>
      </dl>
      <p className="past-data-note">Past data, not a live update or a prediction for today. Source not independently verified.</p>
      <JourneyProgress train={train} />
    </section>

    <details className="report-details solid-panel"><summary><span>How this estimate was calculated</span><ChevronDown /></summary>
      <div className="report-details-body">
        <section><h3>What the model considered</h3><p>These inputs influenced the estimate. They do not tell us what actually caused the delay.</p><div className="simple-factor-list">{(train.overall_delay_reasons || []).slice(0, 3).map((reason, index) => <div key={index}><span>{factorName(reason)}</span><strong>{Number.isFinite(reason.minutes) ? `${decimal(Math.abs(reason.minutes))} min ${reason.minutes < 0 ? 'lower' : reason.minutes > 0 ? 'higher' : 'change'}` : 'Unavailable'}</strong></div>)}</div><p className="detail-small">Technical method: SHAP. Baseline estimate: {decimal(replay.shap_base_minutes)} min.</p></section>
        <section><h3>How reliable is it?</h3><p>Across {metrics.n_test ?? 'the tested'} {aggregate ? 'station averages' : 'past journeys'}, the estimates differed from the records by {decimal(metrics.mae_minutes)} minutes on average.</p><p>The model’s range covered {decimal(metrics.coverage_percent)}% of test records. The target was 80%; this is not a guarantee for an individual journey.</p>{aggregate && <p>Range for this average: {decimal(replay.lower_minutes)}–{decimal(replay.upper_minutes)} min. This is not an arrival-time window.</p>}<p className="detail-small">Test set: {metrics.test_trains ?? '—'} trains excluded from training. Simple baseline error: {decimal(metrics.train_median_baseline_mae_minutes)} min. The range was calibrated on training data.</p></section>
        {!aggregate && <section><h3>Times in the original record</h3><p>Scheduled: {dateTime(replay.original_scheduled_arrival)} IST</p><p>Arrived: {dateTime(replay.original_actual_arrival)} IST</p><p>Estimated arrival: {dateTime(train.upcoming_stations?.[0]?.predicted_arrival)} IST</p><p>Estimated range: {dateTime(train.upcoming_stations?.[0]?.confidence_lower)}–{dateTime(train.upcoming_stations?.[0]?.confidence_upper)} IST</p></section>}
        <section><h3>About the data</h3><p>{aggregate ? 'The supplied etrain export contains train–station averages, not individual journeys. Its source has not been independently verified.' : 'This is an old arrival record, not a live train feed. Its source has not been independently verified.'} The model was tested on trains it had not seen during training.</p><p className="detail-small">Collected: {dateTime(replay.scraped_at)} IST · Replayed: {dateTime(replay.replayed_at)} IST. These are data timestamps, not the train’s current location.{replay.record_interval_seconds ? ` A record is replayed every ${replay.record_interval_seconds} seconds.` : ''}</p><p className="detail-small">Model: {train.model_version || 'Unavailable'} · Record: {replay.record_id || 'Unavailable'}</p></section>
      </div>
    </details>
  </div>;
}
