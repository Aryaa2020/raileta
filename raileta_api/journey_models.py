"""Dated operational records. Deliberately separate from aggregate experiments."""
import uuid
from django.db import models
from django.db.models import Q
from django.utils import timezone


class RailSection(models.Model):
    code = models.CharField(max_length=80, primary_key=True)
    from_station = models.CharField(max_length=20)
    to_station = models.CharField(max_length=20)
    distance_km = models.FloatField()
    tracks = models.PositiveSmallIntegerField(null=True, blank=True)
    speed_kmph = models.FloatField(null=True, blank=True)
    geometry = models.JSONField(default=list, blank=True)
    source = models.CharField(max_length=120)
    mode = models.CharField(max_length=12, choices=[('live', 'Live'), ('simulation', 'Simulation')])


class Journey(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    train_number = models.CharField(max_length=20)
    train_name = models.CharField(max_length=120)
    start_date = models.DateField()
    mode = models.CharField(max_length=12, choices=[('live', 'Live'), ('simulation', 'Simulation')])
    priority = models.PositiveSmallIntegerField(null=True)
    source = models.CharField(max_length=120)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['train_number', 'start_date', 'mode'], name='dated_train_mode_unique')]
        ordering = ['-start_date', 'train_number']


class JourneyStop(models.Model):
    journey = models.ForeignKey(Journey, on_delete=models.PROTECT, related_name='stops')
    sequence = models.PositiveIntegerField()
    station_code = models.CharField(max_length=20)
    station_name = models.CharField(max_length=120)
    scheduled_arrival = models.DateTimeField(null=True, blank=True)
    scheduled_departure = models.DateTimeField(null=True, blank=True)
    distance_km = models.FloatField()
    recovery_minutes = models.FloatField(default=0)
    is_junction = models.BooleanField(default=False)
    section = models.ForeignKey(RailSection, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ['sequence']
        constraints = [models.UniqueConstraint(fields=['journey', 'sequence'], name='journey_stop_order_unique')]


class JourneyEvent(models.Model):
    event_id = models.CharField(max_length=180, unique=True)
    journey = models.ForeignKey(Journey, on_delete=models.PROTECT, related_name='events')
    stop = models.ForeignKey(JourneyStop, on_delete=models.PROTECT)
    kind = models.CharField(max_length=12, choices=[('arrival', 'Arrival'), ('departure', 'Departure')])
    event_time = models.DateTimeField()
    received_at = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=120)
    platform = models.CharField(max_length=30, blank=True)
    accepted = models.BooleanField(default=True)
    context = models.JSONField(default=dict, blank=True)

    class Meta:
        indexes = [models.Index(fields=['journey', 'event_time'])]


class SectionCondition(models.Model):
    external_id = models.CharField(max_length=120, unique=True)
    section = models.ForeignKey(RailSection, on_delete=models.PROTECT)
    kind = models.CharField(max_length=20, choices=[('restriction', 'Speed restriction'), ('block', 'Block'), ('congestion', 'Congestion')])
    severity = models.FloatField()
    starts_at = models.DateTimeField()
    expires_at = models.DateTimeField(null=True)
    speed_limit_kmph = models.FloatField(null=True)
    note = models.CharField(max_length=250, blank=True)
    source = models.CharField(max_length=120)
    updated_at = models.DateTimeField(default=timezone.now)


class ForecastIssue(models.Model):
    """Append-only issuance; never overwritten by a page read or later actual."""
    journey = models.ForeignKey(Journey, on_delete=models.PROTECT, related_name='forecasts')
    stop = models.ForeignKey(JourneyStop, on_delete=models.PROTECT)
    source_event = models.ForeignKey(JourneyEvent, on_delete=models.PROTECT)
    issued_at = models.DateTimeField(default=timezone.now)
    trigger_key = models.CharField(max_length=180)
    predicted_arrival = models.DateTimeField()
    lower = models.DateTimeField(null=True)
    upper = models.DateTimeField(null=True)
    baseline_arrival = models.DateTimeField()
    model_version = models.CharField(max_length=80)
    calibration_status = models.CharField(max_length=80)
    features = models.JSONField(default=dict)
    reasons = models.JSONField(default=list)

    class Meta:
        ordering = ['issued_at', 'id']
        constraints = [models.UniqueConstraint(fields=['journey', 'stop', 'trigger_key', 'model_version'], name='forecast_issuance_unique')]
        indexes = [models.Index(fields=['journey', 'stop', 'issued_at'])]


class ModelRelease(models.Model):
    version = models.CharField(max_length=80, primary_key=True)
    mode = models.CharField(max_length=12)
    artifact_dir = models.CharField(max_length=250)
    manifest_sha256 = models.CharField(max_length=64)
    metrics = models.JSONField(default=dict)
    active = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['mode'], condition=Q(active=True), name='one_active_model_per_mode')]


class SimulationSession(models.Model):
    name = models.CharField(max_length=50, primary_key=True)
    scenario_start = models.DateTimeField()
    wall_start = models.DateTimeField(default=timezone.now)
    speed = models.FloatField(default=10)
    last_tick = models.DateTimeField(null=True)
