import React from 'react';
import DelayChip from './DelayChip';
import StationCard from './StationCard';

const dateTime = (value) => value && Number.isFinite(Date.parse(value))
  ? new Date(value).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })
  : '—';
const decimal = (value) => Number.isFinite(value) ? value.toFixed(1) : '—';

export default function HistoricalReplayDetail({ train }) {
  const replay = train.historical_replay || {};
  const metrics = replay.test_metrics || {};
  if (train.dataset_kind === 'aggregate_profiles') return <div className="mt-8 space-y-5 animate-enter">
    <section className="glass-panel p-5 sm:p-7">
      <p className="eyebrow mb-3">Held-out historical delay profile</p>
      <h2 className="text-2xl font-semibold text-white">{train.train_name}</h2>
      <p className="mt-2 text-sm text-slate-400">{train.train_number} · {replay.station_name} ({replay.station_code})</p>
      <p className="mt-4 text-sm text-violet-200" role="status">Replaying recorded aggregate profiles · model has not seen these trains</p>
      <p className="mt-2 text-xs leading-relaxed text-slate-400">This is a train–station average from the supplied etrain export, not an individual journey or a live train feed. Source authenticity is unverified. No arrival times or moving positions can be inferred.</p>
      <dl className="mt-6 grid gap-5 sm:grid-cols-3">
        <div><dt className="text-xs text-slate-500">Recorded average delay</dt><dd className="mt-2 text-3xl text-amber-100">{decimal(replay.recorded_average_delay_minutes)} <span className="text-sm">min</span></dd></div>
        <div><dt className="text-xs text-slate-500">Model-predicted average delay</dt><dd className="mt-2 text-3xl text-violet-100">{decimal(replay.predicted_average_delay_minutes)} <span className="text-sm">min</span></dd></div>
        <div><dt className="text-xs text-slate-500">Absolute error for this profile</dt><dd className="mt-2 text-3xl text-white">{decimal(replay.absolute_error_minutes)} <span className="text-sm">min</span></dd></div>
      </dl>
      <p className="mt-6 text-sm text-slate-200">TRAIN-calibrated interval for the average: {decimal(replay.lower_minutes)}–{decimal(replay.upper_minutes)} min</p>
      <p className="mt-2 text-xs text-slate-400">80% target for profile averages—not an arrival window. TEST coverage: {decimal(metrics.coverage_percent)}%.</p>
      <p className="mt-5 border-t border-white/10 pt-4 text-xs leading-relaxed text-slate-400">Separate TEST: MAE {decimal(metrics.mae_minutes)} min · {metrics.n_test} profiles · {metrics.test_trains} unseen trains. TRAIN-median baseline: {decimal(metrics.train_median_baseline_mae_minutes)} min MAE.</p>
    </section>
    <section className="glass-panel p-5 sm:p-6"><h3 className="font-semibold text-white">Top model contributions · SHAP</h3><p className="mt-2 text-xs text-slate-400">Signed effects relative to the model baseline of {decimal(replay.shap_base_minutes)} min. Associations, not proven delay causes.</p><div className="mt-4 grid gap-2 sm:grid-cols-2">{(train.overall_delay_reasons || []).slice(0,3).map((reason,index)=><DelayChip key={index} reason={reason}/>)}</div></section>
    <p className="px-2 text-xs leading-relaxed text-slate-500">Page collected: {dateTime(replay.scraped_at)} IST · Replayed: {dateTime(replay.replayed_at)} IST. Collection time is not arrival time. One profile every {replay.record_interval_seconds}s; original train timing is unavailable.</p>
    <p className="px-2 text-xs text-slate-500">Model {train.model_version} · Record {replay.record_id}</p>
  </div>;
  return <div className="mt-8 space-y-5 animate-enter">
    <section className="glass-panel p-5 sm:p-7">
      <p className="eyebrow mb-3">Historical arrival record</p>
      <h2 className="text-2xl font-semibold text-white">{train.train_name}</h2>
      <p className="mt-2 text-sm text-slate-400">Train {train.train_number} · {replay.source_name} → {replay.destination_name}</p>
      <p className="mt-4 text-sm text-violet-200" role="status">Historical dataset replay · held-out trains · provenance unverified</p>
      <p className="mt-2 text-xs leading-relaxed text-slate-400">The model has not seen these trains or runs during fitting or calibration. This is a retrospective prediction using pre-arrival fields, not a live train feed. Source authenticity has not been independently verified.</p>
      <dl className="mt-6 grid gap-5 sm:grid-cols-2">
        <div><dt className="text-xs text-slate-500">Recorded actual arrival · IST</dt><dd className="mt-1 text-lg text-amber-100">{dateTime(replay.original_actual_arrival)}</dd><dd className="text-sm text-slate-400">{decimal(replay.actual_delay_minutes)} min recorded delay</dd></div>
        <div><dt className="text-xs text-slate-500">Model prediction error for this run</dt><dd className="mt-1 text-lg text-violet-100">{decimal(replay.absolute_error_minutes)} min absolute error</dd><dd className="text-sm text-slate-400">{decimal(replay.predicted_delay_minutes)} min predicted delay</dd></div>
        <div><dt className="text-xs text-slate-500">Original scheduled arrival · IST</dt><dd className="mt-1 text-sm text-slate-200">{dateTime(replay.original_scheduled_arrival)}</dd></div>
        <div><dt className="text-xs text-slate-500">Replayed at · IST</dt><dd className="mt-1 text-sm text-slate-200">{dateTime(replay.replayed_at)}</dd></div>
      </dl>
      <p className="mt-5 border-t border-white/10 pt-4 text-xs leading-relaxed text-slate-400">Separate TEST set: MAE {decimal(metrics.mae_minutes)} min · empirical window coverage {decimal(metrics.coverage_percent)}% · {metrics.n_test ?? '—'} runs. The 80% target is not a guarantee for an individual run.</p>
    </section>
    <section><h3 className="mb-4 px-1 text-xl font-semibold text-white">Retrospective destination prediction</h3><div className="space-y-3">{(train.upcoming_stations || []).map((station) => <StationCard key={station.station_code} station={station} />)}</div></section>
    <section className="glass-panel p-5 sm:p-6"><h3 className="font-semibold text-white">Top model contributions · SHAP</h3><p className="mt-1 text-xs text-slate-400">Signed effects on predicted delay, relative to the model baseline—not proven causes of this delay.</p><div className="mt-4 grid gap-2 sm:grid-cols-2">{(train.overall_delay_reasons || []).slice(0, 3).map((reason, index) => <DelayChip key={index} reason={reason} />)}</div></section>
    <p className="px-2 text-center text-xs text-slate-500">Arrival-only dataset: no intermediate station positions, GPS, or departure events. Model {train.model_version} · record {replay.record_id}</p>
  </div>;
}
