from django.db import models
from django.utils import timezone
from .journey_models import (Journey, JourneyStop, JourneyEvent, RailSection, SectionCondition, ForecastIssue, ModelRelease, SimulationSession)


class TrainEvent(models.Model):
    EVENT_TYPES = (
        ("rtis_position", "RTIS position"),
        ("coa_arrival", "COA arrival"),
        ("coa_departure", "COA departure"),
        ("caution_order", "Caution order"),
        ("weather_observation", "Weather observation"),
    )
    event_id = models.CharField(max_length=180, unique=True)
    event_type = models.CharField(max_length=40, choices=EVENT_TYPES)
    train_number = models.CharField(max_length=20, blank=True)
    station_code = models.CharField(max_length=20, blank=True)
    section_code = models.CharField(max_length=40, blank=True)
    event_time = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=40)
    sequence = models.BigIntegerField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    accepted = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["train_number", "event_time"]),
            models.Index(fields=["event_type", "event_time"]),
        ]


class TrainForecast(models.Model):
    train_number = models.CharField(max_length=20)
    station_code = models.CharField(max_length=20)
    station_name = models.CharField(max_length=120)
    scheduled_arrival = models.DateTimeField()
    predicted_arrival = models.DateTimeField()
    confidence_lower = models.DateTimeField()
    confidence_upper = models.DateTimeField()
    delay_minutes = models.FloatField(default=0)
    source_freshness = models.DateTimeField()
    fallback_source = models.CharField(max_length=40, default="WTT")
    model_version = models.CharField(max_length=80, default="event-v1")
    calibration_level = models.FloatField(default=0.80)
    reason_codes = models.JSONField(default=list)
    generated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["train_number", "station_code"], name="unique_train_station_forecast")]
        indexes = [models.Index(fields=["train_number", "generated_at"])]


class FeedSnapshot(models.Model):
    """Compact, immutable observation of a public endpoint fetch."""
    source = models.CharField(max_length=40)
    endpoint = models.URLField(max_length=500)
    fetched_at = models.DateTimeField(default=timezone.now)
    http_status = models.PositiveIntegerField(default=200)
    parser_version = models.CharField(max_length=40, default="public-v1")
    payload = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    raw_path = models.CharField(max_length=500, blank=True)
    content_sha256 = models.CharField(max_length=64, blank=True)
    content_bytes = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [models.Index(fields=["source", "fetched_at"], name="raileta_api_source_f4dfc8_idx")]


class HistoricalReplaySession(models.Model):
    """Durable, non-looping cursor; a reset starts an auditable generation."""

    key = models.CharField(max_length=160, unique=True)
    model_version = models.CharField(max_length=80)
    generation = models.PositiveIntegerField(default=1)
    next_index = models.PositiveIntegerField(default=0)
    next_due_at = models.DateTimeField(default=timezone.now)
    last_replayed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class HistoricalRunPrediction(models.Model):
    """Immutable result for one held-out row, not just a train's latest ETA."""

    session = models.ForeignKey(HistoricalReplaySession, on_delete=models.PROTECT)
    generation = models.PositiveIntegerField()
    record_id = models.CharField(max_length=100)
    train_number = models.CharField(max_length=20)
    # Aggregate profiles have no movement event. Never fabricate one to fill FK.
    event = models.OneToOneField(TrainEvent, on_delete=models.PROTECT, null=True, blank=True)
    model_version = models.CharField(max_length=80)
    original_record = models.JSONField()
    prediction = models.JSONField()
    replayed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["session", "generation", "record_id"],
            name="unique_historical_run_generation",
        )]
        indexes = [models.Index(fields=["session", "generation", "train_number"], name="historical_session_train_idx")]
