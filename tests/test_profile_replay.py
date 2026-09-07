import copy
import json
import math
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import numpy as np
from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from raileta_api.models import TrainEvent, HistoricalRunPrediction, HistoricalReplaySession
from raileta_api.profile_model import load_profiles, split_profiles, feature_row, matrix, get_profile_model, quantiles
from raileta_api.profile_replay import HistoricalProfileReplayAdapter, replay_tick, profile_forecast

ARTIFACTS = Path(__file__).resolve().parents[1] / 'data/models/etrain-profiles-v1'


@override_settings(RAILETA_DATA_ADAPTER='historical_profiles', RAILETA_HISTORICAL_MODEL_DIR=str(ARTIFACTS), RAILETA_REPLAY_INTERVAL_SECONDS=15)
class ProfileExperimentTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.model = get_profile_model(str(ARTIFACTS))
        cls.manifest = cls.model.manifest
        cls.parts = {name: json.loads((ARTIFACTS / f'{name}.json').read_text(encoding='utf-8')) for name in ('train','test','live_demo')}

    def test_audit_and_deduplication(self):
        rows, audit = load_profiles(settings.BASE_DIR / 'etrain_delays.csv')
        self.assertEqual(audit['original_rows'], 1900)
        self.assertEqual(audit['unique_profiles'], 1829)
        self.assertEqual(len(rows),1595)
        self.assertEqual(len(audit['excluded']),305)
        self.assertEqual(len({(r['train_number'],r['station_code']) for r in rows}),1595)
        self.assertTrue(all('scheduled_arrival' not in r and 'actual_arrival' not in r for r in rows))

    def test_grouped_split_reproducible_and_disjoint(self):
        rows, _ = load_profiles(settings.BASE_DIR / 'etrain_delays.csv')
        parts, fit, cal, groups = split_profiles(rows)
        self.assertEqual(parts,self.parts)
        self.assertEqual({k:len(v) for k,v in parts.items()}, {'train':1035,'test':276,'live_demo':284})
        self.assertEqual((len(fit),len(cal)),(805,230))
        for a,b in (('train','test'),('train','live_demo'),('test','live_demo')):
            self.assertFalse(set(groups[a]) & set(groups[b]))
            self.assertFalse({r['record_id'] for r in parts[a]} & {r['record_id'] for r in parts[b]})
        self.assertFalse({r['train_number'] for r in fit} & {r['train_number'] for r in cal})
        self.assertEqual(set(self.manifest['vocabulary']['station_code']),{r['station_code'] for r in fit})

    def test_no_target_or_same_period_percentages_in_features(self):
        row = copy.deepcopy(self.parts['live_demo'][0])
        before = feature_row(row,self.manifest['vocabulary'])
        row.update(average_delay_minutes=999999, train_number='OTHER', scraped_at='2099-01-01', raw={})
        row.update({k:99999 for k in ('pct_right_time','pct_slight_delay','pct_significant_delay','pct_cancelled_unknown')})
        self.assertEqual(before,feature_row(row,self.manifest['vocabulary']))

    def test_conformal_calibration_reproduces_from_train_only(self):
        ids = set(self.manifest['calibration_ids'])
        cal = [r for r in self.parts['train'] if r['record_id'] in ids]
        q = quantiles(self.model.models,matrix(cal,self.manifest['vocabulary']))
        y = np.asarray([r['average_delay_minutes'] for r in cal])
        rank = math.ceil((len(cal)+1)*.8)
        radius = max(0.,float(np.sort(np.maximum(q[:,0]-y,y-q[:,2]))[rank-1]))
        self.assertAlmostEqual(radius,self.manifest['conformal_radius_minutes'])

    def test_test_metrics_are_actual_saved_residuals(self):
        rows = json.loads((ARTIFACTS/'test_predictions.json').read_text())
        metrics = self.manifest['test_metrics']
        self.assertAlmostEqual(sum(r['absolute_error_minutes'] for r in rows)/len(rows),24.5212881670546)
        self.assertEqual(sum(r['covered'] for r in rows),194)
        self.assertEqual(len(rows),276)
        self.assertAlmostEqual(metrics['coverage_percent'],100*194/276)
        q = quantiles(self.model.models,matrix(self.parts['test'],self.manifest['vocabulary']))
        np.testing.assert_allclose(q[:,1],[r['predicted_average_delay_minutes'] for r in rows])

    def test_demo_scoring_is_frozen_ordered_and_shap_additive(self):
        with patch('lightgbm.train',side_effect=AssertionError('Runtime fit forbidden')):
            for row in self.parts['live_demo'][:3]:
                score = self.model.score(row)
                self.assertLessEqual(score['lower_minutes'],score['q10_minutes'])
                self.assertLessEqual(score['q10_minutes'],score['q50_minutes'])
                self.assertLessEqual(score['q50_minutes'],score['q90_minutes'])
                self.assertLessEqual(score['q90_minutes'],score['upper_minutes'])
                self.assertEqual(len(score['reason_codes']),3)
                self.assertAlmostEqual(score['shap_base_minutes']+score['shap_sum_minutes'],score['q50_minutes'])
                self.assertEqual({r['category'] for r in score['reason_codes']},{'station_profile','service_type','station_name_context'})

    def test_replay_persists_exact_profile_without_movement_or_network(self):
        from raileta_api.tasks import _ingest_data_sources
        from raileta_api.ingestion import collect_public_batch
        with patch('requests.sessions.Session.request',side_effect=AssertionError('Network forbidden')):
            self.assertEqual(collect_public_batch(),([],[]))
            self.assertEqual(_ingest_data_sources(),1)
            self.assertEqual(_ingest_data_sources(),0)
            adapter = HistoricalProfileReplayAdapter()
            result = HistoricalRunPrediction.objects.get()
            self.assertEqual(result.original_record,adapter.records[0])
            self.assertIsNone(result.event)
            self.assertEqual(TrainEvent.objects.count(),0)
            self.assertEqual(self.client.get('/api/v1/eta/'+result.train_number).status_code,200)
            self.assertFalse(self.client.get('/api/v1/health').json()['network_collection_enabled'])

    def test_restart_resumes_cursor_and_old_simulated_state_cannot_override(self):
        replay_tick()
        adapter = HistoricalProfileReplayAdapter()
        session = adapter.session()
        HistoricalReplaySession.objects.filter(pk=session.pk).update(next_due_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(replay_tick(),1)
        self.assertEqual(adapter.session().next_index,2)
        number = adapter.records[0]['train_number']
        TrainEvent.objects.create(event_id='unrelated-newer-simulated',event_type='rtis_position',source='SIMULATED_CRIS',train_number=number,
            station_code='MAS',event_time=timezone.now(),payload={'delay_minutes':999})
        response=profile_forecast(number)
        self.assertIsNone(response['current_status']['current_delay_minutes'])
        self.assertEqual(response['historical_replay']['recorded_average_delay_minutes'],adapter.records[0]['average_delay_minutes'])
        self.assertEqual(response['upcoming_stations'],[])

    def test_empty_completion_and_departures_are_honest(self):
        adapter=HistoricalProfileReplayAdapter()
        HistoricalReplaySession.objects.filter(pk=adapter.session().pk).update(next_index=len(adapter.records))
        self.assertEqual(replay_tick(),0)
        self.assertTrue(self.client.get('/api/v1/health').json()['replay']['complete'])
        board=self.client.get('/api/v1/stations/MAS/departures').json()
        self.assertEqual(board['departures'],[])
        self.assertIn('average delays',board['note'])
        self.assertEqual(self.client.get('/api/v1/eta/12007').status_code,404)
