"""Offline, auditable replay of held-out terminal arrivals through frozen ML.

The CSV has no intermediate events. We replay one terminal COA arrival per row
and expose a retrospective prediction using pre-arrival features only. Original
timestamps are preserved; the configurable interval accelerates *records*, not
the original train clock. Nothing in this module makes a network request.
"""
import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.db import OperationalError, transaction
from django.utils import timezone

from .contracts import CanonicalEvent
from .historical_model import get_model
from .models import FeedSnapshot, HistoricalReplaySession, HistoricalRunPrediction, TrainEvent, TrainForecast

SOURCE = "HISTORICAL_REPLAY"
DATE_NOTE = "CSV Date meaning is unconfirmed; provisionally interpreted as the scheduled arrival date (Asia/Kolkata)."
PREDICTION_CONTEXT = "Retrospective prediction using pre-arrival fields only"


def enabled():
    return getattr(settings, "RAILETA_DATA_ADAPTER", "").strip().lower() == "historical_replay"


def interval_seconds():
    return max(1, int(getattr(settings, "RAILETA_REPLAY_INTERVAL_SECONDS", 15)))


class HistoricalReplayAdapter:
    source = SOURCE

    def __init__(self, artifact_dir=None, clock=None):
        self.path = Path(artifact_dir or settings.RAILETA_HISTORICAL_MODEL_DIR)
        self.clock = clock or timezone.now
        self.manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        self.records = json.loads((self.path / "live_demo.json").read_text(encoding="utf-8"))
        training = json.loads((self.path / "train.json").read_text(encoding="utf-8"))
        testing = json.loads((self.path / "test.json").read_text(encoding="utf-8"))
        splits = {"train": training, "test": testing, "live_demo": self.records}
        groups = {name: {r["train_number"] for r in rows} for name, rows in splits.items()}
        ids = {name: {r["record_id"] for r in rows} for name, rows in splits.items()}
        for left, right in (("train", "test"), ("train", "live_demo"), ("test", "live_demo")):
            if groups[left] & groups[right] or ids[left] & ids[right]:
                raise ValueError("Historical artifacts overlap by train or record; refusing replay")
        for name, rows in splits.items():
            if len(ids[name]) != len(rows) or groups[name] != set(self.manifest["train_groups"][name]):
                raise ValueError("Historical split identity does not match its manifest")
        if not self.records:
            raise ValueError("LIVE-DEMO contains no records")
        model_hash = hashlib.sha256(b"".join((self.path / f"q{q}.txt").read_bytes() for q in (10, 50, 90))).hexdigest()
        if self.manifest.get("model_sha256") != model_hash:
            raise ValueError("Frozen LightGBM model checksum does not match its manifest")
        self.records.sort(key=lambda r: (r["actual_arrival"], r["record_id"]))
        self.key = self.manifest["version"]

    def session(self):
        row, _ = HistoricalReplaySession.objects.get_or_create(
            key=self.key, defaults={"model_version": self.manifest["version"], "next_due_at": self.clock()},
        )
        return row

    def poll(self) -> list[CanonicalEvent]:
        # Poll is non-destructive: a crash before scoring cannot skip a row.
        # Ingestion atomically acknowledges this cursor only after persistence.
        session = self.session()
        now = self.clock()
        if session.next_index >= len(self.records) or now < session.next_due_at:
            return []
        record = self.records[session.next_index]
        scheduled, actual = (datetime.fromisoformat(record[k]) for k in ("scheduled_arrival", "actual_arrival"))
        return [CanonicalEvent(
            event_id=f"historical:{self.key}:{session.generation}:{record['record_id']}",
            event_type="coa_arrival", source=SOURCE, event_time=actual,
            received_at=now, train_number=record["train_number"], station_code="DEST",
            sequence=session.next_index,
            payload={
                "historical_replay": True, "session_key": self.key, "generation": session.generation,
                "record_id": record["record_id"], "run_id": record["record_id"],
                "scheduled_time": scheduled.isoformat(), "actual_time": actual.isoformat(),
                "delay_minutes": record["delay_minutes"], "distance_km": record["distance_km"],
                "timestamp": actual.isoformat(), "station_name": record["destination_name"],
                "record": record, "provenance": "user_supplied_unverified",
                "timestamp_note": DATE_NOTE, "record_interval_seconds": interval_seconds(),
                "replay_timing": "Accelerated record replay; original inter-run intervals are not reproduced",
            },
        ).validate()]


def process_event(event):
    """Score this exact run and advance once, even with concurrent poll tasks."""
    event.validate()
    if event.source != SOURCE or not event.payload.get("historical_replay"):
        raise ValueError("Only held-out historical arrival events are accepted here")
    adapter = HistoricalReplayAdapter()
    index = event.sequence
    if type(index) is not int or not 0 <= index < len(adapter.records):
        raise ValueError("Historical replay sequence is invalid")
    record = adapter.records[index]
    if (event.payload.get("record") != record or event.payload.get("session_key") != adapter.key
            or event.train_number != record["train_number"]
            or event.event_time != datetime.fromisoformat(record["actual_arrival"])):
        raise ValueError("Replay event does not match the frozen held-out artifact")
    generation = event.payload["generation"]
    session = adapter.session()
    if session.generation != generation or session.next_index != index:
        return False
    # Frozen model only; label/actual arrival never enter its allowlisted matrix.
    prediction = get_model(str(adapter.path)).score(record, explain=True)
    now = timezone.now()
    for attempt in range(4):
        try:
            with transaction.atomic():
                # Atomic compare-and-swap works on SQLite as well as PostgreSQL.
                advanced = HistoricalReplaySession.objects.filter(
                    pk=session.pk, generation=generation, next_index=index, next_due_at__lte=now,
                ).update(next_index=index + 1, next_due_at=now + timedelta(seconds=interval_seconds()), last_replayed_at=now)
                if not advanced:
                    return False
                stored, created = TrainEvent.objects.get_or_create(event_id=event.event_id, defaults={
                    "event_type": event.event_type, "source": SOURCE, "event_time": event.event_time,
                    "received_at": event.received_at, "train_number": event.train_number,
                    "station_code": "DEST", "sequence": index, "payload": event.payload, "accepted": True,
                })
                if not created:
                    raise ValueError("Replay cursor and event history are inconsistent; cursor was not advanced")
                HistoricalRunPrediction.objects.create(
                    session=session, generation=generation, record_id=record["record_id"],
                    train_number=record["train_number"], event=stored, model_version=prediction["model_version"],
                    original_record=record, prediction=prediction, replayed_at=now,
                )
                scheduled = datetime.fromisoformat(record["scheduled_arrival"])
                TrainForecast.objects.update_or_create(train_number=record["train_number"], station_code="DEST", defaults={
                    "station_name": record["destination_name"], "scheduled_arrival": scheduled,
                    "predicted_arrival": scheduled + timedelta(minutes=prediction["q50_minutes"]),
                    "confidence_lower": scheduled + timedelta(minutes=prediction["lower_minutes"]),
                    "confidence_upper": scheduled + timedelta(minutes=prediction["upper_minutes"]),
                    "delay_minutes": prediction["q50_minutes"], "source_freshness": event.event_time,
                    "fallback_source": SOURCE, "model_version": prediction["model_version"],
                    "calibration_level": adapter.manifest["coverage_target"], "reason_codes": prediction["reason_codes"],
                })
                FeedSnapshot.objects.create(source=SOURCE, endpoint="http://localhost/internal/historical-replay", parser_version="historical-csv-v2", payload={
                    "adapter": "HistoricalReplayAdapter", "record_id": record["record_id"],
                    "train_number": record["train_number"], "generation": generation,
                    "model_version": prediction["model_version"], "event_count": 1, "network_request": False,
                })
            return True
        except OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 3:
                raise
            time.sleep(.05 * (attempt + 1))
    return False


def _latest_runs(adapter):
    session = adapter.session()
    return HistoricalRunPrediction.objects.filter(session=session, generation=session.generation).order_by("-event__event_time", "-pk")


def _metadata(adapter, run):
    return {
        "data_mode": "historical_replay", "prediction_mode": "trained_historical",
        "calibration_status": "train_calibrated_test_evaluated", "calibration_level": adapter.manifest["coverage_target"],
        "model_version": adapter.manifest["version"], "source": SOURCE, "fallback_source": SOURCE,
        "is_stale": False, "source_freshness_seconds": None, "data_freshness": run.event.event_time if run else None,
        "last_updated": run.replayed_at if run else None, "position_mode": "historical_terminal_arrival",
        "gps_available": False, "timestamp_note": DATE_NOTE,
    }


def historical_forecast(train_number):
    adapter = HistoricalReplayAdapter()
    run = _latest_runs(adapter).select_related("event").filter(train_number=str(train_number)).first()
    if not run:
        raise LookupError("This train has no replayed held-out arrival in the current session")
    row, score = run.original_record, run.prediction
    scheduled = datetime.fromisoformat(row["scheduled_arrival"])
    metadata = _metadata(adapter, run)
    reasons = score["reason_codes"]
    replay = {
        "record_id": row["record_id"], "source_name": row["source_name"], "destination_name": row["destination_name"],
        "original_scheduled_arrival": row["scheduled_arrival"], "original_actual_arrival": row["actual_arrival"],
        "actual_delay_minutes": row["delay_minutes"], "predicted_delay_minutes": score["q50_minutes"],
        "absolute_error_minutes": abs(score["q50_minutes"] - row["delay_minutes"]),
        "replayed_at": run.replayed_at, "provenance": "user_supplied_unverified", "provenance_description": "User-supplied Kaggle CSV; source dataset and real-world provenance unverified",
        "record_interval_seconds": interval_seconds(), "prediction_context": PREDICTION_CONTEXT,
        "test_metrics": adapter.manifest["test_metrics"], "timestamp_note": DATE_NOTE,
        "replay_timing": "Accelerated record replay, not original inter-run timing",
        "held_out_train": True, "shap_base_minutes": score.get("shap_base_minutes"),
        "shap_sum_minutes": score.get("shap_sum_minutes"), "shap_explained_quantile": score.get("shap_explained_quantile"),
    }
    return {
        **metadata, "train_number": row["train_number"], "train_name": row["train_name"], "train_class": "Dataset service",
        "current_status": {**metadata, "train_number": row["train_number"], "train_name": row["train_name"],
            "train_class": "Dataset service", "current_delay_minutes": row["delay_minutes"],
            "last_reported_station": row["destination_name"], "last_reported_time": row["actual_arrival"], "next_station": None},
        "upcoming_stations": [{"station_code": "DEST", "station_name": row["destination_name"],
            "scheduled_arrival": scheduled, "predicted_arrival": scheduled + timedelta(minutes=score["q50_minutes"]),
            "confidence_lower": scheduled + timedelta(minutes=score["lower_minutes"]),
            "confidence_upper": scheduled + timedelta(minutes=score["upper_minutes"]),
            "delay_minutes": score["q50_minutes"], "delay_reasons": reasons, "loop_prediction": None,
            "platform": None, "prediction_mode": "trained_historical", "retrospective": True}],
        "overall_delay_reasons": reasons, "historical_replay": replay, "route_geometry": None, "route_stops": [],
        "weather_observations": [], "ntes_comparison": None,
    }


def historical_corridor():
    adapter = HistoricalReplayAdapter()
    rows, seen = [], set()
    for run in _latest_runs(adapter).select_related("event"):
        if run.train_number in seen:
            continue
        seen.add(run.train_number)
        record = run.original_record
        rows.append({**_metadata(adapter, run), "train_number": run.train_number, "train_name": record["train_name"],
            "train_class": "Dataset service", "current_station": record["destination_name"], "next_station": None,
            "delay_minutes": record["delay_minutes"], "status": "Held-out historical arrival replay",
            "last_event_time": record["actual_arrival"], "route_geometry": None, "historical_replay": {
                "source_name": record["source_name"], "destination_name": record["destination_name"],
                "original_actual_arrival": record["actual_arrival"], "replayed_at": run.replayed_at}})
    return {"data_mode": "historical_replay", "prediction_mode": "trained_historical", "corridor_name": "Historical dataset replay",
        "total_trains": len(rows), "trains": rows, "congestion_hotspots": [], "weather_observations": [],
        "timestamp": timezone.now(), "data_freshness": max((r["last_event_time"] for r in rows), default=None),
        "route_geometry": None, "timestamp_note": DATE_NOTE,
        "coverage": {"observed_train_count": len(rows), "configured_train_count": len(adapter.manifest["train_groups"]["live_demo"]),
            "source_scope": "Only held-out trains from the supplied historical CSV; not the MAS-SBC corridor"}}


def historical_departures(station_code):
    return {"station_code": station_code.upper(), "station_name": station_code.upper(), "departures": [],
        "timestamp": timezone.now(), "data_mode": "historical_replay", "data_freshness": None,
        "note": "This dataset contains terminal arrival records, not departures."}


def historical_health():
    try:
        adapter = HistoricalReplayAdapter()
        session = adapter.session()
        count = HistoricalRunPrediction.objects.filter(session=session, generation=session.generation).count()
        finished = session.next_index >= len(adapter.records)
        return {"status": "healthy" if count else "degraded", "version": "2.0.0",
            "model_status": "trained_historical_lightgbm", "data_mode": "historical_replay",
            "integration_status": "replay_complete" if finished else "historical_replay_active",
            "configured_sources": [SOURCE], "collector_interval_seconds": interval_seconds(),
            "live_position_mode": "historical_terminal_arrival", "live_position_note": PREDICTION_CONTEXT,
            "last_adapter_fetch": session.last_replayed_at, "last_public_fetch": None, "public_fetch_errors": 0,
            "last_model_update": adapter.manifest["created_at"], "model_version": adapter.manifest["version"],
            "accepted_events": count, "fallback_chain": [], "network_collection_enabled": False,
            "test_metrics": adapter.manifest["test_metrics"], "timestamp_note": DATE_NOTE,
            "replay": {"generation": session.generation, "played_records": session.next_index,
                "total_records": len(adapter.records), "complete": finished, "loops": False,
                "next_due_at": None if finished else session.next_due_at, "record_interval_seconds": interval_seconds()}}
    except (OSError, ValueError, KeyError) as exc:
        return {"status": "degraded", "data_mode": "historical_replay", "model_status": "historical_artifacts_unavailable",
            "detail": str(exc), "configured_sources": [SOURCE], "network_collection_enabled": False}
