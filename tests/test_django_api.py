import json
from datetime import timedelta, timezone as dt_timezone
from unittest.mock import Mock, patch

from django.test import TestCase
from django.test import override_settings
from django.utils import timezone

from raileta_api.ingestion import CrisRestAdapter, OpenMeteoWeatherAdapter, SimulatedFeedAdapter
from raileta_api.models import TrainEvent, FeedSnapshot
from raileta_api.services import resolve_train_state


@override_settings(RAILETA_DATA_ADAPTER="simulated", RAILETA_COLLECTOR_INTERVAL_SECONDS=30, RAILETA_TRAIN_NUMBERS=('12007','12639','12607','22625','12609'))
class RailEtaApiTests(TestCase):
    def test_eta_contract_has_calibrated_window_and_monotonic_bounds(self):
        now = timezone.now()
        TrainEvent.objects.create(event_id="eta-state", event_type="coa_departure", source="SIMULATED_CRIS", train_number="12007", station_code="MAS", event_time=now, payload={"delay_minutes": 8})
        FeedSnapshot.objects.create(source="SIMULATED_CRIS", endpoint="http://localhost/demo", payload={"train_number": "12007", "route": [{"station_code": "MAS"}, {"station_code": "AJJ"}]})
        response = self.client.get("/api/v1/eta/12007")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["calibration_level"], 0.8)
        self.assertEqual(payload["current_status"]["last_reported_station"], "MAS")
        self.assertTrue(payload["upcoming_stations"])
        for station in payload["upcoming_stations"]:
            self.assertLessEqual(station["confidence_lower"], station["predicted_arrival"])
            self.assertLessEqual(station["predicted_arrival"], station["confidence_upper"])

    def test_event_deduplication_and_stale_rejection(self):
        now = timezone.now()
        body = {
            "event_id": "test-event-1",
            "event_type": "coa_departure",
            "source": "TEST",
            "event_time": now.isoformat(),
            "train_number": "12007",
            "station_code": "AJJ",
            "sequence": 10,
            "payload": {"delay_minutes": 20},
        }
        first = self.client.post("/api/v1/events", data=json.dumps(body), content_type="application/json")
        duplicate = self.client.post("/api/v1/events", data=json.dumps(body), content_type="application/json")
        stale = dict(body, event_id="test-event-2", event_time=(now - timedelta(hours=1)).isoformat(), sequence=1)
        stale_response = self.client.post("/api/v1/events", data=json.dumps(stale), content_type="application/json")
        self.assertEqual(first.status_code, 201)
        self.assertTrue(first.json()["accepted"])
        self.assertTrue(duplicate.json()["deduplicated"])
        self.assertFalse(stale_response.json()["accepted"])
        self.assertEqual(TrainEvent.objects.filter(event_id="test-event-1").count(), 1)
        progressed = self.client.get("/api/v1/eta/12007").json()
        self.assertEqual(progressed["current_status"]["last_reported_station"], "AJJ")
        self.assertEqual(progressed["fallback_source"], "TEST")

    def test_public_endpoints_remain_available(self):
        self.assertEqual(self.client.get("/api/v1/health").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/corridor/MAS-SBC").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/stations/MAS/departures?limit=3").json()["departures"].__len__(), 0)

    def test_simulated_adapter_emits_structured_cris_events(self):
        events = SimulatedFeedAdapter(["12007"], interval_seconds=30).poll()
        self.assertTrue(events)
        self.assertIn("rtis_position", {event.event_type for event in events})
        self.assertTrue({event.event_type for event in events} <= {"rtis_position", "coa_arrival", "coa_departure", "caution_order"})
        self.assertTrue(all(event.source == "SIMULATED_CRIS" for event in events))

    def test_state_resolution_prefers_fresh_rtis_over_coa(self):
        now = timezone.now()
        TrainEvent.objects.create(event_id="coa-state", event_type="coa_departure", source="SIMULATED_COA", train_number="12007", station_code="AJJ", event_time=now - timedelta(seconds=5), received_at=now, sequence=1, payload={"delay_minutes": 9})
        TrainEvent.objects.create(event_id="rtis-state", event_type="rtis_position", source="SIMULATED_RTIS", train_number="12007", station_code="KPD", event_time=now, received_at=now, sequence=2, payload={"delay_minutes": 10})
        state = resolve_train_state("12007")
        self.assertEqual(state.event_type, "rtis_position")
        self.assertEqual(state.station_code, "KPD")

    @patch("raileta_api.ingestion.requests.Session.get")
    def test_structured_cris_adapter_normalizes_json_events(self, get):
        response = Mock(status_code=200)
        response.json.return_value = {"events": [{
            "event_id": "cris-1", "event_type": "rtis_position", "source": "RTIS",
            "event_time": timezone.now().isoformat(), "train_number": "12007",
            "station_code": "AJJ", "payload": {"latitude": 13.08, "longitude": 79.67},
        }]}
        get.return_value = response
        events = CrisRestAdapter("https://cris.example/events").poll()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_id, "cris-1")
        self.assertEqual(events[0].event_type, "rtis_position")

    @override_settings(RAILETA_STORE_RAW_PAYLOADS=False)
    @patch("raileta_api.ingestion.requests.get")
    def test_open_meteo_normalizes_current_weather_without_a_key(self, get):
        response = Mock(status_code=200, url="https://api.open-meteo.com/v1/forecast")
        response.json.return_value = {
            "current": {
                "time": "2026-09-06T01:45",
                "temperature_2m": 28.1,
                "relative_humidity_2m": 86,
                "precipitation": 0.1,
                "visibility": 9360,
                "weather_code": 51,
                "wind_speed_10m": 11.8,
            }
        }
        get.return_value = response
        events = OpenMeteoWeatherAdapter("https://api.open-meteo.com/v1/forecast").collect({"MAS": {"latitude": 13.08, "longitude": 80.27}})
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].source, "PUBLIC_WEATHER_MODEL")
        self.assertEqual(events[0].station_code, "MAS")
        self.assertEqual(events[0].event_time.astimezone(dt_timezone.utc).isoformat(), "2026-09-05T20:15:00+00:00")
        self.assertFalse(events[0].payload["has_fog"])
        get.assert_called_once()
