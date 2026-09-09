import copy
from datetime import date, timedelta
from unittest.mock import patch
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from raileta_api.corridor_simulation import reference, timetable, simulate_run, sample_rows, features_at, feed_rows, SOURCE
from raileta_api.corridor_replay import register, replay_run, clock
from raileta_api.journey_models import JourneyEvent, ForecastIssue, SimulationSession
from raileta_api.journeys import feature_row, current_event, record_event, issue_forecasts


class SimulatorTests(SimpleTestCase):
    def setUp(self):
        self.ref=reference()

    def test_real_roster_and_train_specific_stops(self):
        self.assertEqual({t['number'] for t in self.ref['trains']},{'12607','12639','12657','12027'})
        shatabdi=self.ref['trains'][0]
        self.assertEqual([s[0] for s in shatabdi['stops']],['MAS','KPD','JTJ','BNC','SBC'])
        self.assertNotIn(1,shatabdi['weekdays'])

    def test_overnight_schedule_and_causal_physics(self):
        day=date(2025,12,31)
        for train in self.ref['trains']:
            run=simulate_run(train,day)
            self.assertEqual(run,simulate_run(train,day))
            for a,b in zip(run['stops'],run['stops'][1:]):
                self.assertLess(a['actual_departure'],b['actual_arrival'])
                speed=(b['distance_km']-a['distance_km'])/(b['actual_arrival']-a['actual_departure']).total_seconds()*3600
                self.assertLessEqual(speed,130.000001)
                if b['actual_departure']:
                    self.assertGreaterEqual(b['actual_departure'],b['scheduled_departure'])
            if train['number']=='12657':
                self.assertEqual(run['stops'][-1]['scheduled_arrival'].date(),date(2026,1,1))

    def test_no_future_label_in_features_and_late_report_hold(self):
        run=simulate_run(self.ref['trains'][1],date(2025,6,12))
        original=features_at(run,0,3)
        changed=copy.deepcopy(run)
        changed['stops'][3]['actual_arrival']+=timedelta(minutes=90)
        self.assertEqual(features_at(changed,0,3),original)
        run['stops'][0]['context']['report_latency_seconds']=600
        self.assertFalse(any(s['source_sequence']==0 for s in sample_rows(run)))

    def test_raw_feed_labels_no_platform_and_nominal_gps_cadence(self):
        run=simulate_run(self.ref['trains'][0],date(2025,6,12))
        records=list(feed_rows(run,26028))
        self.assertTrue(all(r['mode']=='simulation' and r['source']==SOURCE for r in records))
        self.assertTrue(all(r.get('platform') is None for r in records))
        self.assertTrue({'rtis_position','coa_arrival','coa_departure','weather','caution_order','network_state','icms_consist'} <= {r['event_type'] for r in records})


@override_settings(RAILETA_DATA_ADAPTER='corridor_simulation')
class ReplayTests(TestCase):
    def setUp(self):
        self.run=simulate_run(reference()['trains'][0],date(2026,1,15),seed=91377)
        self.journey=register(self.run)

    def test_runtime_feature_parity_and_no_get_writes(self):
        stop=self.run['stops'][0]
        at=stop['actual_departure'];received=at+timedelta(seconds=stop['context']['report_latency_seconds'])
        record_event(self.journey.pk,dict(event_id='origin',sequence=0,kind='departure',event_time=at,received_at=received,source=SOURCE,context=stop['context']),enqueue=False)
        event=current_event(self.journey)
        target=self.journey.stops.get(sequence=3)
        self.assertEqual(feature_row(self.journey,event,target,[]),features_at(self.run,0,3))
        counts=(JourneyEvent.objects.count(),ForecastIssue.objects.count())
        self.assertEqual(self.client.get('/api/v1/eta/12027').json()['data_mode'],'corridor_simulation')
        roster=self.client.get('/api/v1/corridor/MAS-SBC').json()['trains']
        self.assertEqual([s['station_code'] for s in roster[0]['stops']],['MAS','KPD','JTJ','BNC','SBC'])
        self.assertIn('Chennai',roster[0]['stops'][0]['station_name'])
        self.assertEqual(counts,(JourneyEvent.objects.count(),ForecastIssue.objects.count()))
        self.assertEqual(self.client.get('/api/v1/journeys?mode=live').json()['journeys'],[])

    def test_replay_idempotent_and_uses_dated_forecasts(self):
        until=self.run['stops'][1]['actual_arrival']+timedelta(minutes=1)
        self.assertGreater(replay_run(self.run,until),0)
        before=(JourneyEvent.objects.count(),ForecastIssue.objects.count())
        self.assertEqual(replay_run(self.run,until),0)
        self.assertEqual(before,(JourneyEvent.objects.count(),ForecastIssue.objects.count()))
        self.assertGreater(before[1],0)
        self.assertTrue(all(i.source_event.received_at<=i.issued_at for i in ForecastIssue.objects.select_related('source_event')))

    def test_scenario_clock_bounded_and_not_wall_clock(self):
        start=self.run['stops'][0]['scheduled_departure']
        wall=timezone.now()
        SimulationSession.objects.create(name='mas-sbc',scenario_start=start,wall_start=wall,speed=10)
        with patch('raileta_api.corridor_replay.timezone.now',return_value=wall+timedelta(seconds=5)):
            self.assertEqual(clock(),start+timedelta(seconds=50))
        with patch('raileta_api.corridor_replay.timezone.now',return_value=wall+timedelta(days=2)):
            self.assertEqual(clock(),start+timedelta(days=1))

    def test_future_receipt_cannot_generate_a_backdated_forecast(self):
        stop=self.run['stops'][0]
        at=stop['actual_departure']
        record_event(self.journey.pk,dict(event_id='future-receipt',sequence=0,kind='departure',event_time=at,received_at=at+timedelta(seconds=90),source=SOURCE,context=stop['context']),enqueue=False)
        self.assertEqual(issue_forecasts(self.journey.pk,now=at+timedelta(seconds=30))['issued'],0)
        self.assertEqual(ForecastIssue.objects.count(),0)
