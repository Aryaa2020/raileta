/** Render-contract tests only: the fixture below is not an ML evaluation result. */
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const require = createRequire(new URL('../passenger-ui/package.json', import.meta.url));
const { createServer } = require('vite');

const train = {
  train_number: 'TEST-TRAIN', train_name: 'UI fixture train', data_mode: 'historical_replay',
  model_version: 'ui-fixture', route_stops: [], route_geometry: null,
  current_status: { last_reported_station: 'DATASET_DESTINATION' },
  historical_replay: {
    record_id: 'ui-fixture', source_name: 'Dataset origin', destination_name: 'Dataset destination',
    original_scheduled_arrival: '2020-01-01T05:00:00+05:30',
    original_actual_arrival: '2020-01-01T05:20:00+05:30',
    actual_delay_minutes: 20, predicted_delay_minutes: 18, absolute_error_minutes: 2,
    replayed_at: '2026-09-06T05:00:00+05:30',
    test_metrics: { mae_minutes: 6.25, coverage_percent: 75, n_test: 20 },
  },
  overall_delay_reasons: [{ category: 'distance', description: 'Distance contribution', minutes: -2.5 }],
  upcoming_stations: [{
    station_code: 'DATASET_DESTINATION', station_name: 'Dataset destination',
    scheduled_arrival: '2020-01-01T05:00:00+05:30', predicted_arrival: '2020-01-01T05:18:00+05:30',
    confidence_lower: '2020-01-01T05:05:00+05:30', confidence_upper: '2020-01-01T05:35:00+05:30',
    delay_minutes: 18, prediction_mode: 'trained_historical', delay_reasons: [],
  }],
};

let assertions = 0;
for (const app of ['passenger-ui', 'controller-dashboard', 'station-display']) {
  const root = fileURLToPath(new URL(`../${app}/`, import.meta.url));
  const appRequire = createRequire(new URL(`../${app}/package.json`, import.meta.url));
  const React = appRequire('react');
  const { renderToStaticMarkup } = appRequire('react-dom/server');
  const server = await createServer({ root, server: { middlewareMode: true, hmr: false }, logLevel: 'error' });
  try {
    const render = async (path, props) => {
      const { default: Component } = await server.ssrLoadModule(path);
      return renderToStaticMarkup(React.createElement(Component, props));
    };
    if (app === 'passenger-ui') {
      const html = await render('/src/components/HistoricalReplayDetail.jsx', { train });
      for (const text of ['provenance unverified', 'held-out trains', '2020', '2026', '-2.5', '75.0%', '6.3', 'Retrospective destination prediction']) { assert.ok(html.includes(text), text); assertions++; }
      for (const text of ['Mock expected arrival', 'Next stop', 'GPS position']) { assert.ok(!html.includes(text), text); assertions++; }
      const search = await render('/src/components/TrainSearch.jsx', { trains: [], onSearch() {} });
      assert.ok(!search.includes('12007') && !search.includes('12639')); assertions++;
      const aggregate = { ...train, dataset_kind: 'aggregate_profiles', historical_replay: { ...train.historical_replay,
        station_code: 'TEST', station_name: 'Dataset station', recorded_average_delay_minutes: 20,
        predicted_average_delay_minutes: 18, lower_minutes: 5, upper_minutes: 35, scraped_at: '2025-09-27T12:00:00Z',
        shap_base_minutes: 20.5, record_interval_seconds: 15 } };
      const profile = await render('/src/components/HistoricalReplayDetail.jsx', { train: aggregate });
      for (const text of ['Recorded average delay', 'Model-predicted average delay', 'Collection time is not arrival time', '-2.5', 'model has not seen these trains']) { assert.ok(profile.includes(text),text); assertions++; }
      for (const text of ['Recorded actual arrival', 'Original scheduled arrival', 'Retrospective destination prediction']) { assert.ok(!profile.includes(text),text); assertions++; }
    } else if (app === 'controller-dashboard') {
      const html = await render('/src/components/TrainDetailPanel.jsx', { train, onClose() {} });
      for (const text of ['provenance unverified', '-2.5m', '2020', '2026', '75.0%', 'Model-predicted arrival']) { assert.ok(html.includes(text), text); assertions++; }
      for (const text of ['Estimated journey complete', 'Next station ETA', 'Mock prediction factors']) { assert.ok(!html.includes(text), text); assertions++; }
      const profile = await render('/src/components/TrainDetailPanel.jsx', { train: { ...train, dataset_kind: 'aggregate_profiles', historical_replay: { ...train.historical_replay,
        station_code: 'TEST', recorded_average_delay_minutes: 20, predicted_average_delay_minutes: 18, lower_minutes: 5, upper_minutes: 35 } }, onClose() {} });
      for (const text of ['Recorded average delay','Profile absolute error','Collection time is not arrival time','-2.5m']) { assert.ok(profile.includes(text),text); assertions++; }
      assert.ok(!profile.includes('Model-predicted arrival')); assertions++;
      const corridor = await render('/src/components/CorridorMap.jsx', { corridorData: { data_mode: 'historical_replay', corridor_name: 'Historical dataset replay', trains: [{ train_number: 'TEST-TRAIN', train_name: 'Dataset train', current_station: 'DATASET_DESTINATION', delay_minutes: 20 }] }, onTrainClick() {} });
      assert.ok(!corridor.includes('class="corridor-track"') && !corridor.includes('MAS')); assertions++;
    } else {
      const html = await render('/src/components/Header.jsx', { historical: true, stationName: 'CHENNAI CENTRAL', stationCode: 'MAS' });
      assert.ok(html.includes('HISTORICAL DELAY PROFILES')); assertions++;
      assert.ok(!html.includes('CHENNAI CENTRAL') && !html.includes('Station Code: MAS')); assertions++;
    }
  } finally { await server.close(); }
}
console.log(`Historical UI smoke tests passed (${assertions} assertions).`);
