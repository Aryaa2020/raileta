import json
import tempfile
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from django.test import TestCase, override_settings
from django.utils import timezone
from raileta_api.journey_models import Journey, JourneyEvent, RailSection, ForecastIssue, ModelRelease
from raileta_api.journeys import (IST, import_journey, record_event, issue_forecasts, record_condition, journey_json, accuracy, current_event)
from raileta_api.journey_ml import predict, train_candidate, activate, active_version, load_bundle, FEATURES


@override_settings(RAILETA_EVENT_STALE_SECONDS=180)
class JourneyTests(TestCase):
    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)
        self.section = RailSection.objects.create(code='SIM-A-B', from_station='AAA', to_station='BBB', distance_km=80, tracks=2, source='TEST', mode='simulation')
        self.run = self.make_run()

    def make_run(self, days=0, mode='simulation'):
        origin = self.now-timedelta(minutes=20, days=days)
        return import_journey(dict(train_number='12345', train_name='Test service', start_date=origin.astimezone(IST).date().isoformat(), mode=mode, source='TEST', stops=[
            dict(station_code='AAA', distance_km=0, scheduled_departure=origin.isoformat()),
            dict(station_code='BBB', distance_km=80, scheduled_arrival=(origin+timedelta(hours=2)).isoformat(), section_code=self.section.pk if mode == 'simulation' else None),
        ]))

    def event(self, run=None, at=None, sequence=0, kind='departure', key='first'):
        run = run or self.run
        at = at or self.now
        return record_event(run.pk, dict(event_id=key, sequence=sequence, kind=kind, event_time=at.isoformat(), received_at=at.isoformat(), source='TEST', platform='4'), enqueue=False)[0]

    def test_dated_runs_and_modes_never_mix(self):
        old = self.make_run(days=1)
        live = self.make_run(mode='live')
        self.event(old, at=self.now-timedelta(days=1), key='old')
        event = self.event()
        self.assertEqual(current_event(self.run), event)
        self.assertIsNone(current_event(live))
        self.assertEqual(len(self.client.get('/api/v1/journeys?mode=simulation').json()['journeys']), 2)
        self.assertEqual(len(self.client.get('/api/v1/journeys?mode=live').json()['journeys']), 1)
        self.assertEqual(self.client.get(f'/api/v1/journeys/{old.pk}?mode=live').status_code, 404)

    def test_no_invented_windows_and_immutable_idempotent_versions(self):
        self.event()
        self.assertEqual(issue_forecasts(self.run.pk, self.now)['issued'], 1)
        self.assertEqual(issue_forecasts(self.run.pk, self.now)['issued'], 0)
        first = ForecastIssue.objects.get()
        self.assertIsNone(first.lower)
        self.assertIsNone(first.upper)
        self.event(at=self.now-timedelta(seconds=30), key='older')
        self.assertEqual(issue_forecasts(self.run.pk, self.now)['issued'], 0)
        self.assertEqual(ForecastIssue.objects.get().predicted_arrival, first.predicted_arrival)
        self.assertEqual(journey_json(self.run, True)['stops'][0]['platform'], None)

    def test_condition_changes_expiry_and_unrelated_sections(self):
        self.event(); issue_forecasts(self.run.pk, self.now)
        condition = record_condition(dict(external_id='c1', section_code=self.section.pk, kind='block', severity=.8, source='TEST', starts_at=(self.now-timedelta(seconds=5)).isoformat(), expires_at=(self.now+timedelta(seconds=10)).isoformat()), enqueue=False)
        self.assertEqual(issue_forecasts(self.run.pk, self.now)['issued'], 1)
        self.assertEqual(issue_forecasts(self.run.pk, self.now+timedelta(seconds=20))['issued'], 1)
        self.assertEqual(ForecastIssue.objects.count(), 3)
        self.assertEqual(self.client.post('/api/v1/conditions', {}, content_type='application/json').status_code, 405)

    def test_stale_data_holds_exact_forecast(self):
        self.event(); issue_forecasts(self.run.pk, self.now)
        before = list(ForecastIssue.objects.values())
        self.assertEqual(issue_forecasts(self.run.pk, self.now+timedelta(minutes=5))['status'], 'held_stale_or_missing_event')
        self.assertEqual(list(ForecastIssue.objects.values()), before)

    def test_history_and_accuracy_only_use_prearrival_forecasts(self):
        start = self.now-timedelta(minutes=15)
        self.event(at=start)
        issue_forecasts(self.run.pk, start)
        actual = self.event(at=self.now, sequence=1, kind='arrival', key='actual')
        measured = accuracy('simulation')
        self.assertEqual(measured['sample_count'], 1)
        self.assertIsNone(measured['rows'][0]['coverage_percent'])
        self.assertEqual(accuracy('live')['sample_count'], 0)
        payload = self.client.get(f'/api/v1/journeys/{self.run.pk}/history?mode=simulation&sequence=1').json()
        self.assertEqual(len(payload['forecasts']), 1)
        self.assertIsNotNone(payload['actual_arrival'])
        self.assertEqual(journey_json(self.run)['status'], 'completed')

    def test_invalid_dates_and_event_identity(self):
        self.assertEqual(self.client.get('/api/v1/journeys?date=bad').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/journeys?mode=bogus').status_code, 400)
        self.event()
        with self.assertRaises(ValueError):
            self.event(sequence=1, kind='arrival')
        with self.assertRaises(ValueError):
            self.event(at=self.now+timedelta(hours=1), key='future')
        self.assertEqual(JourneyEvent.objects.count(), 1)

    def test_arrivals_time_window_and_no_platform_inference(self):
        self.event(); issue_forecasts(self.run.pk, self.now)
        data = self.client.get('/api/v1/stations/BBB/arrivals?mode=simulation&hours=3').json()
        self.assertEqual(len(data['arrivals']), 1)
        self.assertIsNone(data['arrivals'][0]['platform'])
        self.assertEqual(self.client.get('/api/v1/stations/BBB/arrivals?hours=25').status_code, 400)
        self.assertEqual(self.client.get('/api/v1/stations/BBB/arrivals?mode=live').json()['arrivals'], [])

    def test_dated_ingestion_requires_token_and_exact_journey(self):
        body = dict(event_id='http', event_type='coa_departure', source='TEST', event_time=self.now.isoformat(), train_number='12345', station_code='AAA', payload={'journey_id': str(self.run.pk), 'stop_sequence': 0})
        self.assertEqual(self.client.post('/api/v1/events', json.dumps(body), content_type='application/json').status_code, 403)
        with override_settings(RAILETA_JOURNEY_INGEST_TOKEN='test-only'), self.captureOnCommitCallbacks(execute=False):
            response = self.client.post('/api/v1/events', json.dumps(body), content_type='application/json', HTTP_AUTHORIZATION='Bearer test-only')
            self.assertEqual(response.status_code, 201)
            body['station_code'] = 'WRONG'
            self.assertEqual(self.client.post('/api/v1/events', json.dumps(body), content_type='application/json', HTTP_AUTHORIZATION='Bearer test-only').status_code, 400)

    def test_training_refuses_insufficient_dated_labels(self):
        with self.assertRaisesMessage(ValueError, '10 distinct journey dates'):
            train_candidate('test-insufficient', 'simulation')
        result = predict({'current_delay': 17}, 'simulation')
        self.assertEqual(result['delay'], 17)
        self.assertIsNone(result['lower'])

    def test_quantile_training_calibration_activation_and_integrity(self):
        # Synthetic TEST-ONLY labels with a deliberately learnable constant
        # target. Never persisted in the demo DB or used to claim accuracy.
        for days in range(2, 12):
            run = self.make_run(days=days)
            origin, target = list(run.stops.all())
            actual = target.scheduled_arrival+timedelta(minutes=10)
            JourneyEvent.objects.create(event_id=f'label-{days}', journey=run, stop=target, kind='arrival', event_time=actual, received_at=actual, source='TEST')
            for index in range(20):
                at = origin.scheduled_departure+timedelta(minutes=20, seconds=index)
                event = JourneyEvent.objects.create(event_id=f'feature-{days}-{index}', journey=run, stop=origin, kind='departure', event_time=at, received_at=at, source='TEST')
                features = {key: 0 for key in FEATURES}
                features.update(current_delay=20+index/60, remaining_km=80, remaining_stops=1, scheduled_minutes=120)
                ForecastIssue.objects.create(journey=run, stop=target, source_event=event, issued_at=at, trigger_key=str(index), predicted_arrival=target.scheduled_arrival+timedelta(minutes=20), baseline_arrival=target.scheduled_arrival+timedelta(minutes=20), model_version='test-baseline', calibration_status='none', features=features)
        with tempfile.TemporaryDirectory(prefix='raileta-model-test-') as temporary, patch('raileta_api.journey_ml.artifact_root', return_value=Path(temporary)):
            manifest = train_candidate('test-quantiles', 'simulation')
            self.assertEqual(manifest['split_sizes'], [120, 40, 40])
            self.assertEqual(active_version('simulation'), None)
            activate('test-quantiles')
            self.assertEqual(active_version('simulation'), 'test-quantiles')
            self.assertIsNone(active_version('live'))
            forecast = predict(features, 'simulation', 'test-quantiles')
            self.assertEqual(forecast['version'], 'test-quantiles')
            self.assertLessEqual(forecast['lower'], forecast['delay'])
            self.assertLessEqual(forecast['delay'], forecast['upper'])
            self.assertTrue(forecast['reasons'])
            self.assertEqual(predict(features, 'live', 'test-quantiles')['version'], 'schedule-current-delay-v1')
            ModelRelease.objects.create(version='bad-gates', mode='simulation', artifact_dir='unused', manifest_sha256='0'*64)
            with patch('raileta_api.journey_ml.load_bundle', return_value=({}, {'metrics': {'samples': 2, 'mae_minutes': 10, 'baseline_mae_minutes': 1, 'coverage_percent': 50}})):
                with self.assertRaises(ValueError):
                    activate('bad-gates')
            self.assertEqual(active_version('simulation'), 'test-quantiles')
            # Simulate storage tampering, then force a fresh worker-equivalent load.
            (Path(temporary)/'test-quantiles'/'q50.txt').write_text('invalid model', encoding='utf-8')
            load_bundle.cache_clear()
            self.assertEqual(predict(features, 'simulation', 'test-quantiles')['calibration'], 'model_rejected_baseline_fallback')
        load_bundle.cache_clear()
