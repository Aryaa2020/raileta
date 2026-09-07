"""Replay real CSV aggregate profiles, never manufacture railway events."""
import json
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import FeedSnapshot, HistoricalReplaySession, HistoricalRunPrediction
from .profile_model import get_profile_model

SOURCE = "HISTORICAL_PROFILES"
NOTE = "Replaying recorded aggregate delay profiles; model has not seen these trains. Not live, not individual train runs."


def enabled():
    return settings.RAILETA_DATA_ADAPTER == "historical_profiles"


class HistoricalProfileReplayAdapter:
    """Profile contract deliberately separate from RTIS/COA Event contract."""
    def __init__(self):
        self.path = Path(settings.RAILETA_HISTORICAL_MODEL_DIR)
        self.model = get_profile_model(str(self.path))
        self.manifest = self.model.manifest
        self.records = json.loads((self.path / "live_demo.json").read_text(encoding="utf-8"))
        sets = {name: json.loads((self.path / f"{name}.json").read_text(encoding="utf-8")) for name in ("train", "test", "live_demo")}
        ids = {name: {r["record_id"] for r in rows} for name, rows in sets.items()}
        groups = {name: {r["train_number"] for r in rows} for name, rows in sets.items()}
        for a,b in (("train","test"), ("train","live_demo"), ("test","live_demo")):
            if ids[a]&ids[b] or groups[a]&groups[b]:
                raise ValueError("Split overlap; replay refused")
        for name, rows in sets.items():
            if len(ids[name]) != len(rows) or groups[name] != set(self.manifest["train_groups"][name]):
                raise ValueError("Split identities do not match manifest")
        # Round-robin trains provides a useful roster promptly, not a fake route
        # sequence. Original capture times remain visible and unmodified.
        per_train = {n: sorted([r for r in self.records if r["train_number"] == n], key=lambda r:r["scraped_at"]) for n in sorted(groups["live_demo"])}
        self.records = [rows[i] for i in range(max(map(len, per_train.values()))) for rows in per_train.values() if i < len(rows)]
        self.interval = max(1, settings.RAILETA_REPLAY_INTERVAL_SECONDS)
        self.key = self.manifest["version"]

    def session(self):
        return HistoricalReplaySession.objects.get_or_create(key=self.key, defaults={"model_version": self.key})[0]

    def poll(self) -> list[dict]:
        session = self.session()
        if session.next_index >= len(self.records) or timezone.now() < session.next_due_at:
            return []
        return [{"record": self.records[session.next_index], "index": session.next_index, "generation": session.generation}]


def replay_tick():
    adapter = HistoricalProfileReplayAdapter()
    batch = adapter.poll()
    if not batch:
        return 0
    item = batch[0]
    record, index, generation = item["record"], item["index"], item["generation"]
    score = adapter.model.score(record)
    now = timezone.now()
    session = adapter.session()
    # Anchor to the existing schedule, not completion time. Otherwise a task
    # finishing 0.1s after a beat tick skips every other 15-second tick.
    steps = max(1, int((now-session.next_due_at).total_seconds() // adapter.interval)+1)
    next_due = session.next_due_at + timedelta(seconds=steps*adapter.interval)
    with transaction.atomic():
        changed = HistoricalReplaySession.objects.filter(pk=session.pk, next_index=index, generation=generation, next_due_at__lte=now).update(
            next_index=index+1, next_due_at=next_due, last_replayed_at=now)
        if not changed:
            return 0
        HistoricalRunPrediction.objects.create(session=session, generation=generation, record_id=record["record_id"],
            train_number=record["train_number"], event=None, model_version=adapter.key, original_record=record, prediction=score, replayed_at=now)
        FeedSnapshot.objects.create(source=SOURCE, endpoint="http://localhost/internal/profile-replay", fetched_at=now,
            parser_version="etrain-profiles-v1", payload={"record_id": record["record_id"], "record": record,
                "model_version": adapter.key, "network_request": False, "granularity": "aggregate_profile"})
    return 1


def latest(adapter):
    session = adapter.session()
    return HistoricalRunPrediction.objects.filter(session=session, generation=session.generation).order_by("-pk")


def metadata(adapter):
    return {"data_mode": "historical_replay", "dataset_kind": "aggregate_profiles", "prediction_mode": "trained_aggregate_profile",
        "source": SOURCE, "fallback_source": SOURCE, "model_version": adapter.key,
        "calibration_level": .8, "calibration_status": "train_calibrated_test_evaluated",
        "is_stale": False, "gps_available": False, "position_mode": "unavailable", "note": NOTE,
        "route_geometry": None, "weather_observations": [], "source_freshness_seconds": None}


def profile_forecast(train_number):
    adapter = HistoricalProfileReplayAdapter()
    result = latest(adapter).filter(train_number=str(train_number)).first()
    if not result:
        raise LookupError("Train has no replayed held-out aggregate profile yet")
    row, score = result.original_record, result.prediction
    return {**metadata(adapter), "train_number": row["train_number"], "train_name": row["train_name"], "train_class": "Dataset profile",
        "last_updated": result.replayed_at, "data_freshness": None,
        "current_status": {"current_delay_minutes": None, "last_reported_station": None, "last_reported_time": None, "next_station": None},
        "upcoming_stations": [], "route_stops": [], "overall_delay_reasons": score["reason_codes"], "ntes_comparison": None,
        "historical_replay": {"record_id": row["record_id"], "station_code": row["station_code"], "station_name": row["station_name"],
            "recorded_average_delay_minutes": row["average_delay_minutes"], "predicted_average_delay_minutes": score["q50_minutes"],
            "lower_minutes": score["lower_minutes"], "upper_minutes": score["upper_minutes"],
            "absolute_error_minutes": abs(score["q50_minutes"]-row["average_delay_minutes"]),
            "scraped_at": row["scraped_at"], "replayed_at": result.replayed_at, "source_url": row["source_url"],
            "provenance": "user_supplied_etrain_export_unverified", "record_interval_seconds": adapter.interval,
            "prediction_context": "Predicting a historical station average, not an individual arrival",
            "test_metrics": adapter.manifest["test_metrics"], "shap_base_minutes": score["shap_base_minutes"],
            "shap_sum_minutes": score["shap_sum_minutes"], "held_out_train": True}}


def profile_corridor():
    adapter = HistoricalProfileReplayAdapter()
    trains, seen = [], set()
    for item in latest(adapter):
        if item.train_number in seen:
            continue
        seen.add(item.train_number)
        row = item.original_record
        trains.append({**metadata(adapter), "train_number": row["train_number"], "train_name": row["train_name"],
            "current_station": row["station_code"], "profile_station": row["station_code"], "next_station": None,
            # Legacy roster numeric display; explicitly labelled average in UI.
            "delay_minutes": row["average_delay_minutes"], "average_delay_minutes": row["average_delay_minutes"],
            "status": "Historical average", "last_event_time": None})
    return {**metadata(adapter), "corridor_name": "Historical station-delay profiles", "trains": trains, "total_trains": len(trains),
        "congestion_hotspots": [], "timestamp": timezone.now(), "data_freshness": None,
        "coverage": {"observed_train_count": len(trains), "configured_train_count": len(adapter.manifest["train_groups"]["live_demo"]),
            "source_scope": "Supplied aggregate dataset; not MAS-SBC movement data"}, "test_metrics": adapter.manifest["test_metrics"]}


def profile_departures(station_code):
    return {"station_code": station_code, "station_name": "Historical profiles", "departures": [],
        "timestamp": timezone.now(), "data_mode": "historical_replay", "dataset_kind": "aggregate_profiles",
        "data_freshness": None, "note": "This dataset contains average delays, not arrival/departure events or schedules."}


def profile_health():
    try:
        adapter = HistoricalProfileReplayAdapter()
        session = adapter.session()
        complete = session.next_index >= len(adapter.records)
        return {**metadata(adapter), "status": "healthy", "version": "2.0.0", "model_status": "trained_lightgbm_aggregate_profiles",
            "configured_sources": [SOURCE], "network_collection_enabled": False, "accepted_events": 0,
            "collector_interval_seconds": settings.RAILETA_COLLECTOR_INTERVAL_SECONDS,
            "integration_status": "replay_complete" if complete else "profile_replay_active",
            "test_metrics": adapter.manifest["test_metrics"], "split_sizes": adapter.manifest["sizes"],
            "last_adapter_fetch": session.last_replayed_at, "last_model_update": adapter.manifest["created_at"],
            "replay": {"generation": session.generation, "played_records": session.next_index, "total_records": len(adapter.records),
                "complete": complete, "loops": False, "record_interval_seconds": adapter.interval, "next_due_at": None if complete else session.next_due_at}}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "degraded", "data_mode": "historical_replay", "dataset_kind": "aggregate_profiles", "detail": str(exc), "network_collection_enabled": False}
