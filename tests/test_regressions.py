"""Regression coverage for the September audit; no broker or network needed."""

import json
from datetime import timedelta
from unittest.mock import Mock, patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from raileta_api.contracts import CanonicalEvent
from raileta_api.event_store import store_event
from raileta_api.ingestion import (
    CrisRestAdapter,
    SimulatedFeedAdapter,
    collect_public_batch,
    get_train_adapter,
)
from raileta_api.models import FeedSnapshot, TrainEvent, TrainForecast
from raileta_api.services import (
    forecast_train,
    resolve_train_state,
    state_metadata,
    station_departures,
    corridor_status,
)
from raileta_api.tasks import _ingest_data_sources


@override_settings(
    OPEN_METEO_ENABLED=False,
    IMD_WEATHER_URL="",
    RAILETA_DATA_ADAPTER="simulated",
    RAILETA_STORE_RAW_PAYLOADS=False,
)
class RegressionTests(TestCase):
    def event(
        self,
        event_id="event",
        kind="coa_departure",
        station="AJJ",
        age=0,
        source="SIMULATED_CRIS",
        sequence=1,
        **payload
    ):
        now = timezone.now()
        return CanonicalEvent(
            event_id,
            kind,
            source,
            now - timedelta(seconds=age),
            now,
            train_number="12007",
            station_code=station,
            sequence=sequence,
            payload=payload,
        )

    def route(self, source="SIMULATED_CRIS", **extra):
        return FeedSnapshot.objects.create(
            source=source,
            endpoint="http://localhost/fixture",
            payload={
                "train_number": "12007",
                "route": [
                    {"station_code": "MAS", "lat": 13.08, "lng": 80.27},
                    {
                        "station_code": "AJJ",
                        "lat": 13.08,
                        "lng": 79.67,
                        "scheduled_departure": "08:35",
                    },
                    {"station_code": "SBC", "lat": 12.97, "lng": 77.57},
                ],
                **extra,
            },
        )

    def test_tests_cannot_reach_runtime_redis(self):
        self.assertTrue(settings.CELERY_TASK_ALWAYS_EAGER)
        self.assertEqual(settings.CELERY_BROKER_URL, "memory://")
        self.assertEqual(settings.CELERY_RESULT_BACKEND, "cache+memory://")

    @patch("raileta_api.ingestion.OpenMeteoWeatherAdapter.collect")
    @override_settings(OPEN_METEO_ENABLED=True)
    def test_weather_is_not_requested_every_train_tick(self, collect):
        FeedSnapshot.objects.create(
            source="PUBLIC_WEATHER_MODEL", endpoint="http://localhost/weather"
        )
        events, _ = collect_public_batch()
        self.assertTrue(events)
        collect.assert_not_called()

    @patch("raileta_api.tasks.reforecast_train.delay")
    def test_broker_failure_reports_durable_event(self, delay):
        from kombu.exceptions import OperationalError

        delay.side_effect = OperationalError("Broker offline")
        body = {
            "event_id": "broker-down",
            "event_type": "coa_departure",
            "source": "COA",
            "train_number": "12007",
            "station_code": "AJJ",
            "event_time": timezone.now().isoformat(),
        }
        response = self.client.post(
            "/api/v1/events", json.dumps(body), content_type="application/json"
        )
        self.assertEqual(response.status_code, 201)
        self.assertFalse(response.json()["forecast_queued"])
        self.assertTrue(TrainEvent.objects.filter(event_id="broker-down").exists())

    def test_no_events_does_not_invent_current_station_or_freshness(self):
        payload = forecast_train("12007")
        self.assertIsNone(payload["current_status"]["last_reported_station"])
        self.assertIsNone(payload["data_freshness"])
        self.assertEqual(payload["upcoming_stations"], [])
        self.assertTrue(payload["is_stale"])
        self.assertFalse(payload["baseline_available"])
        health = self.client.get("/api/v1/health").json()
        self.assertEqual(health["status"], "degraded")
        self.assertIsNone(health["data_freshness"])

    def test_unknown_train_returns_404_without_writing_forecasts(self):
        self.assertEqual(self.client.get("/api/v1/eta/99999").status_code, 404)
        self.assertFalse(TrainForecast.objects.exists())

    def test_observed_delay_unchanged_and_eta_get_is_read_only(self):
        self.route()
        store_event(self.event(delay_minutes=11))
        result = forecast_train("12007")
        self.assertEqual(result["current_status"]["current_delay_minutes"], 11)
        self.assertEqual(result["prediction_mode"], "mock")
        self.assertEqual(result["calibration_status"], "unvalidated_demo_window")
        self.assertFalse(TrainForecast.objects.exists())

    def test_refresh_does_not_push_eta_forward_without_new_event(self):
        self.route()
        store_event(self.event(delay_minutes=11))
        first = forecast_train("12007")
        with patch(
            "raileta_api.services.timezone.now",
            return_value=timezone.now() + timedelta(minutes=1),
        ):
            second = forecast_train("12007")
        self.assertEqual(first["upcoming_stations"], second["upcoming_stations"])

    def test_stale_fallback_holds_latest_position_and_widens_mock_window(self):
        self.route()
        store_event(self.event("old-coa", age=240, station="MAS"))
        store_event(
            self.event("new-rtis", kind="rtis_position", age=200, station="AJJ")
        )
        state = resolve_train_state("12007")
        self.assertEqual(state.station_code, "AJJ")
        meta = state_metadata("12007")
        self.assertEqual(meta["fallback_kind"], "WTT")
        self.assertTrue(meta["position_held"])
        self.assertFalse(meta["baseline_available"])

    def test_newer_coa_not_overridden_by_older_fresh_rtis(self):
        store_event(self.event("rtis", kind="rtis_position", station="MAS", age=20))
        store_event(self.event("coa", station="AJJ", age=1))
        self.assertEqual(resolve_train_state("12007").station_code, "AJJ")

    def test_late_coa_is_retained_for_fallback_independent_of_rtis_sequence(self):
        store_event(self.event("rtis", kind="rtis_position", age=1, sequence=999))
        row, _ = store_event(self.event("coa", age=5, sequence=1))
        self.assertTrue(row.accepted)
        self.assertEqual(resolve_train_state("12007").event_id, "rtis")

    def test_caution_does_not_replace_movement_state(self):
        store_event(self.event("movement", age=5))
        store_event(self.event("caution", kind="caution_order", station="MAS"))
        self.assertEqual(resolve_train_state("12007").event_id, "movement")

    def test_duplicates_and_late_same_stream_events(self):
        event = self.event("new", age=1)
        _, created = store_event(event)
        self.assertTrue(created)
        self.assertFalse(store_event(event)[1])
        self.assertFalse(store_event(self.event("old", age=10))[0].accepted)

    def test_malformed_http_events_return_400_not_500(self):
        base = {
            "event_id": "bad",
            "source": "RTIS",
            "event_type": "rtis_position",
            "train_number": "12007",
            "event_time": timezone.now().isoformat(),
        }
        cases = [
            [],
            5,
            {**base, "payload": [1]},
            {**base, "sequence": "one"},
            {**base, "payload": {"latitude": 100}},
            {**base, "event_time": "2026-01-01T10:00:00"},
            {**base, "event_time": (timezone.now() + timedelta(days=1)).isoformat()},
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(
                    self.client.post(
                        "/api/v1/events",
                        json.dumps(body),
                        content_type="application/json",
                    ).status_code,
                    400,
                )

    @override_settings(RAILETA_DATA_ADAPTER="typo")
    def test_unknown_adapter_does_not_silently_generate_simulation(self):
        with self.assertRaises(ValueError):
            get_train_adapter()

    def test_cris_adapter_requires_url_and_event_time(self):
        with self.assertRaises(ValueError):
            CrisRestAdapter("").poll()
        session = Mock()
        session.get.return_value.json.return_value = {
            "events": [
                {
                    "event_id": "missing-time",
                    "event_type": "rtis_position",
                    "train_number": "12007",
                }
            ]
        }
        with self.assertRaises(ValueError):
            CrisRestAdapter("http://localhost/events", session=session).poll()

    @override_settings(RAILETA_DATA_ADAPTER="cris_rest")
    def test_structured_adapter_trains_reach_corridor_and_forecaster(self):
        adapter = Mock(spec=CrisRestAdapter)
        adapter.url = "http://localhost/events"
        adapter.poll.return_value = [
            self.event(
                source="CRIS_REST",
                delay_minutes=7,
                route=[{"station_code": "AJJ"}, {"station_code": "SBC"}],
            )
        ]
        with patch("raileta_api.ingestion.get_train_adapter", return_value=adapter):
            _ingest_data_sources()
        self.assertEqual(corridor_status("MAS-SBC")["total_trains"], 1)
        self.assertEqual(
            forecast_train("12007")["current_status"]["current_delay_minutes"], 7
        )
        self.assertTrue(
            TrainForecast.objects.filter(
                train_number="12007", station_code="SBC"
            ).exists()
        )

    @patch("raileta_api.tasks.reforecast_train.delay")
    def test_batch_deduplicates_forecast_jobs_per_train(self, delay):
        events = [self.event("coa", age=1), self.event("rtis", kind="rtis_position")]
        with patch(
            "raileta_api.ingestion.collect_public_batch", return_value=(events, [])
        ):
            self.assertEqual(_ingest_data_sources(), 2)
            self.assertEqual(_ingest_data_sources(), 0)
        delay.assert_called_once_with("12007")

    def test_station_does_not_show_non_stopping_services(self):
        self.route(route=[{"station_code": "AJJ", "stop": False}])
        self.assertEqual(station_departures("AJJ")["departures"], [])

    def test_station_actual_departure_survives_later_ping_and_uses_ist(self):
        self.route()
        event = self.event("departure", age=10)
        store_event(event)
        store_event(self.event("ping", kind="rtis_position"))
        row = station_departures("AJJ")["departures"][0]
        self.assertEqual(row["status"], "Departed")
        self.assertEqual(
            row["predicted_departure"],
            timezone.localtime(event.event_time).strftime("%H:%M"),
        )
        self.assertEqual(row["scheduled_departure"], "08:35")

    def test_previous_simulated_run_departure_not_reused(self):
        self.route(run_id="new-run")
        store_event(self.event(run_id="old-run"))
        self.assertEqual(
            station_departures("AJJ")["departures"][0]["status"], "Scheduled"
        )

    def test_simulator_reaches_destination_and_labels_every_ping(self):
        now = timezone.now()
        base_tick = int(now.timestamp() // 30)
        destination_tick = base_tick - base_tick % 36 + 32
        # Choose the latest completed cycle so validation never sees the future.
        if destination_tick > base_tick:
            destination_tick -= 36
        clock = timezone.datetime.fromtimestamp(
            destination_tick * 30, tz=timezone.get_default_timezone()
        )
        with patch("raileta_api.ingestion.datetime") as dt:
            dt.now.return_value = clock
            dt.fromtimestamp.side_effect = timezone.datetime.fromtimestamp
            events = SimulatedFeedAdapter(["12007"]).poll()
        self.assertTrue(
            any(
                e.station_code == "SBC" and e.event_type == "coa_arrival"
                for e in events
            )
        )
        self.assertFalse(
            any(
                e.station_code == "SBC" and e.event_type == "coa_departure"
                for e in events
            )
        )
        self.assertTrue(all(e.payload.get("simulated") for e in events))
