"""Operational journey services; no aggregate-to-journey inference."""
import hashlib
import json
import math
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from .journey_models import Journey, JourneyStop, JourneyEvent, RailSection, SectionCondition, ForecastIssue

IST = ZoneInfo('Asia/Kolkata')
MODES = ('live', 'simulation')


def timestamp(value):
    result = parse_datetime(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or timezone.is_naive(result):
        raise ValueError('Timestamps must be ISO-8601 with an explicit timezone')
    return result


def finite(value, name, minimum=0, maximum=100000):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f'Invalid {name}')
    return value


@transaction.atomic
def import_journey(data):
    """Trusted adapter/CLI only. Explicit absolute times support overnight stops."""
    mode = data.get('mode')
    if mode not in MODES or not data.get('source') or not data.get('train_number'):
        raise ValueError('mode, source and train_number are required')
    day = date.fromisoformat(data['start_date'])
    rows = data.get('stops', [])
    if len(rows) < 2 or len(rows) > 500:
        raise ValueError('Supply 2–500 ordered timetable stops')
    parsed = []
    last_time = None
    last_distance = -1
    for index, row in enumerate(rows):
        arrival = timestamp(row['scheduled_arrival']) if row.get('scheduled_arrival') else None
        departure = timestamp(row['scheduled_departure']) if row.get('scheduled_departure') else None
        distance = finite(row.get('distance_km'), 'distance_km')
        if not row.get('station_code') or (index > 0 and arrival is None) or (index < len(rows)-1 and departure is None):
            raise ValueError('Every non-origin needs arrival and every non-destination needs departure')
        for time in (arrival, departure):
            if time and (last_time and time < last_time):
                raise ValueError('Timetable must be chronological; include overnight dates explicitly')
            if time:
                last_time = time
        if index == 0 and departure.astimezone(IST).date() != day:
            raise ValueError('start_date must match origin departure in India Standard Time')
        if distance < last_distance:
            raise ValueError('Cumulative distance must be non-decreasing')
        last_distance = distance
        section = RailSection.objects.get(pk=row['section_code']) if row.get('section_code') else None
        if section and (section.mode != mode or index == 0 or section.from_station != rows[index-1]['station_code'] or section.to_station != row['station_code']):
            raise ValueError('Section must connect consecutive stops and match journey mode')
        parsed.append(dict(sequence=index, station_code=row['station_code'], station_name=row.get('station_name', row['station_code']), scheduled_arrival=arrival, scheduled_departure=departure, distance_km=distance, recovery_minutes=finite(row.get('recovery_minutes', 0), 'recovery_minutes'), is_junction=bool(row.get('is_junction', False)), section=section))
    journey = Journey.objects.create(train_number=str(data['train_number']), train_name=data.get('train_name', str(data['train_number'])), start_date=day, mode=mode, source=data['source'], priority=data.get('priority'))
    for row in parsed:
        stop = JourneyStop(journey=journey, **row)
        stop.full_clean()
        stop.save()
    return journey


@transaction.atomic
def record_event(journey_id, data, enqueue=True):
    journey = Journey.objects.select_for_update().get(pk=journey_id)
    stop = journey.stops.get(sequence=data['sequence'])
    at = timestamp(data['event_time'])
    received = timezone.now()
    if journey.mode == 'simulation' and data.get('received_at'):
        received = timestamp(data['received_at'])
        if received > timezone.now() or received < at:
            raise ValueError('Synthetic receipt time must follow the event and not be in the future')
    if data.get('kind') not in ('arrival', 'departure') or not data.get('source') or not data.get('event_id'):
        raise ValueError('event_id, kind and source are required')
    if at > received + timedelta(minutes=5):
        raise ValueError('Future events are not accepted')
    origin = journey.stops.first().scheduled_departure
    if at < origin - timedelta(hours=12) or at > (journey.stops.last().scheduled_arrival + timedelta(days=7)):
        raise ValueError('Event is outside this dated journey; verify the journey ID')
    from .corridor_simulation import CONTEXT_FEATURES, SIMULATION_CONDITIONS, SOURCE
    context_keys = CONTEXT_FEATURES + (SIMULATION_CONDITIONS if journey.mode == 'simulation' and journey.source == SOURCE else [])
    context = {key: data.get('context', {}).get(key) for key in context_keys}
    for key, value in context.items():
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
            raise ValueError('Invalid numeric event context: ' + key)
    latest = journey.events.filter(accepted=True).order_by('-event_time', '-id').first()
    # Retain delayed reports as actual evidence, but never move the current state backwards.
    accepted = not latest or (at >= latest.event_time and stop.sequence >= latest.stop.sequence)
    event, created = JourneyEvent.objects.get_or_create(event_id=data['event_id'], defaults=dict(journey=journey, stop=stop, kind=data['kind'], event_time=at, received_at=received, source=data['source'], context=context, platform=str(data.get('platform') or '') if journey.mode == 'live' else '', accepted=accepted))
    if not created and (event.journey_id != journey.id or event.stop_id != stop.id or event.kind != data['kind'] or event.event_time != at):
        raise ValueError('Event ID already belongs to a different report')
    if created and accepted and enqueue:
        transaction.on_commit(lambda: queue_journey(journey.id))
    return event, created


def queue_journey(journey_id):
    from kombu.exceptions import OperationalError
    from .tasks import reforecast_journey
    try:
        reforecast_journey.delay(str(journey_id))
        return True
    except OperationalError:
        # The periodic sweep retries durable events when the broker/worker recovers.
        return False


def record_canonical(event):
    """Dated adapter events require a registered journey, not an inferred date."""
    journey = Journey.objects.get(pk=event.payload['journey_id'])
    if str(journey.train_number) != event.train_number or event.event_type not in ('coa_arrival', 'coa_departure'):
        raise ValueError('Dated event must match its train and be a station arrival/departure')
    stop = journey.stops.get(sequence=event.payload['stop_sequence'])
    if stop.station_code != event.station_code:
        raise ValueError('Dated event station does not match stop sequence')
    return record_event(journey.pk, dict(event_id=event.event_id, sequence=stop.sequence, kind='arrival' if event.event_type == 'coa_arrival' else 'departure', event_time=event.event_time, source=event.source, platform=event.payload.get('platform')))


def active_conditions(mode, at=None):
    from .corridor_replay import scenario_now
    at = at or scenario_now(mode)
    return SectionCondition.objects.filter(section__mode=mode, starts_at__lte=at).filter(Q(expires_at__isnull=True) | Q(expires_at__gt=at)).select_related('section')


@transaction.atomic
def record_condition(data, enqueue=True):
    """Trusted ingestion only; there is deliberately no public condition-write API."""
    section = RailSection.objects.get(pk=data['section_code'])
    starts = timestamp(data['starts_at'])
    expires = timestamp(data['expires_at']) if data.get('expires_at') else None
    severity = finite(data['severity'], 'severity', 0, 1)
    speed = finite(data['speed_limit_kmph'], 'speed limit', 1, 400) if data.get('speed_limit_kmph') is not None else None
    if data.get('kind') not in ('restriction', 'block', 'congestion') or not data.get('source') or expires and expires <= starts:
        raise ValueError('Invalid condition kind, source, or expiry')
    existing = SectionCondition.objects.filter(external_id=data['external_id']).first()
    if existing and existing.section_id != section.pk:
        raise ValueError('A condition cannot be moved to another section; expire it and issue a new sourced ID')
    condition, _ = SectionCondition.objects.update_or_create(external_id=data['external_id'], defaults=dict(section=section, kind=data['kind'], severity=severity, starts_at=starts, expires_at=expires, speed_limit_kmph=speed, note=data.get('note', ''), source=data['source'], updated_at=timezone.now()))
    if enqueue:
        transaction.on_commit(lambda: queue_affected(section.pk))
    return condition


def queue_affected(section_code):
    for journey_id in JourneyStop.objects.filter(section_id=section_code).values_list('journey_id', flat=True).distinct():
        queue_journey(journey_id)


def current_event(journey):
    return journey.events.filter(accepted=True).select_related('stop').order_by('-event_time', '-id').first()


def delay_for(event):
    schedule = event.stop.scheduled_departure if event.kind == 'departure' else event.stop.scheduled_arrival
    return (event.event_time - schedule).total_seconds()/60 if schedule else None


def feature_row(journey, event, target, conditions):
    stops = list(journey.stops.filter(sequence__gt=event.stop.sequence, sequence__lte=target.sequence).select_related('section'))
    sections = [stop.section for stop in stops if stop.section]
    relevant = [c for c in conditions if c.section_id in {s.pk for s in sections}]
    halt = sum((s.scheduled_departure-s.scheduled_arrival).total_seconds()/60 for s in stops[:-1] if s.scheduled_departure and s.scheduled_arrival)
    total_minutes = (target.scheduled_arrival-(event.stop.scheduled_departure or event.stop.scheduled_arrival)).total_seconds()/60
    # Missing infrastructure/conditions are not replaced by invented defaults.
    features = dict(current_delay=delay_for(event), remaining_km=target.distance_km-event.stop.distance_km, remaining_stops=len(stops), scheduled_minutes=total_minutes, scheduled_running_minutes=total_minutes-halt, scheduled_halt_minutes=halt, recovery_minutes=sum(s.recovery_minutes for s in stops), junctions=sum(s.is_junction for s in stops), mean_tracks=sum(s.tracks for s in sections if s.tracks is not None)/len(sections) if sections and all(s.tracks is not None for s in sections) else None, single_track_km=sum(s.distance_km for s in sections if s.tracks == 1) if len(sections) == len(stops) else None, priority=journey.priority, condition_severity=sum(c.severity for c in relevant), restriction_speed_kmph=min((c.speed_limit_kmph for c in relevant if c.speed_limit_kmph is not None), default=None), restriction_count=sum(c.kind == 'restriction' for c in relevant), block_count=sum(c.kind == 'block' for c in relevant), congestion_count=sum(c.kind == 'congestion' for c in relevant), hour=event.event_time.astimezone(IST).hour, weekday=event.event_time.astimezone(IST).weekday())
    from .corridor_simulation import CONTEXT_FEATURES, SIMULATION_CONDITIONS, SOURCE
    context_keys = CONTEXT_FEATURES + (SIMULATION_CONDITIONS if journey.mode == 'simulation' and journey.source == SOURCE else [])
    features.update({key: event.context.get(key) for key in context_keys})
    features['month'] = event.event_time.astimezone(IST).month
    return features


@transaction.atomic
def issue_forecasts(journey_id, now=None):
    from .journey_ml import predict, active_version
    journey = Journey.objects.select_for_update().get(pk=journey_id)
    from .corridor_replay import scenario_now
    now = now or scenario_now(journey.mode, journey.source)
    event = current_event(journey)
    if not event or event.event_time > now or event.received_at > now or (now-event.event_time).total_seconds() > settings.RAILETA_EVENT_STALE_SECONDS or delay_for(event) is None:
        return {'issued': 0, 'status': 'held_stale_or_missing_event'}
    section_ids = set(journey.stops.filter(sequence__gt=event.stop.sequence).values_list('section_id', flat=True))
    revisions = list(SectionCondition.objects.filter(section_id__in=section_ids, section__mode=journey.mode).order_by('pk'))
    enabled = lambda c: c.starts_at <= now and (c.expires_at is None or c.expires_at > now)
    conditions = [c for c in revisions if enabled(c)]
    key = hashlib.sha256(json.dumps([event.pk, [(c.pk, c.updated_at.isoformat(), enabled(c)) for c in revisions]], sort_keys=True).encode()).hexdigest()
    version = active_version(journey.mode)
    count = 0
    for stop in journey.stops.filter(sequence__gt=event.stop.sequence).select_related('section'):
        if not stop.scheduled_arrival or journey.events.filter(stop=stop, kind='arrival').exists():
            continue
        features = feature_row(journey, event, stop, conditions)
        result = predict(features, journey.mode, version)
        predicted = stop.scheduled_arrival + timedelta(minutes=result['delay'])
        # Do not issue predictions already in the past as upcoming arrivals.
        if predicted < now:
            continue
        _, created = ForecastIssue.objects.get_or_create(journey=journey, stop=stop, trigger_key=key, model_version=result['version'], defaults=dict(source_event=event, issued_at=now, predicted_arrival=predicted, lower=stop.scheduled_arrival+timedelta(minutes=result['lower']) if result['lower'] is not None else None, upper=stop.scheduled_arrival+timedelta(minutes=result['upper']) if result['upper'] is not None else None, baseline_arrival=stop.scheduled_arrival+timedelta(minutes=delay_for(event)), calibration_status=result['calibration'], features=features, reasons=result['reasons']))
        count += int(created)
    return {'issued': count, 'status': 'ready'}


def forecast_json(issue):
    return dict(id=issue.pk, issued_at=issue.issued_at, predicted_arrival=issue.predicted_arrival, confidence_lower=issue.lower, confidence_upper=issue.upper, baseline_arrival=issue.baseline_arrival, model_version=issue.model_version, source_event=issue.source_event.event_id, source_time=issue.source_event.event_time, calibration_status=issue.calibration_status, reasons=issue.reasons)


def journey_json(journey, detail=False):
    event = current_event(journey)
    from .corridor_replay import scenario_now
    now = scenario_now(journey.mode, journey.source)
    stale = not event or (now-event.event_time).total_seconds() > settings.RAILETA_EVENT_STALE_SECONDS
    last_stop = journey.stops.last()
    completed = bool(last_stop and journey.events.filter(stop=last_stop, kind='arrival').exists())
    data = dict(id=str(journey.id), train_number=journey.train_number, train_name=journey.train_name, start_date=journey.start_date, mode=journey.mode, source=journey.source, is_stale=stale, status='completed' if completed else 'running' if event else 'scheduled', current_delay_minutes=delay_for(event) if event else None, current_station=event.stop.station_code if event else None, last_reported_time=event.event_time if event else None)
    data['scenario_time'] = now if journey.mode == 'simulation' else None
    if not detail:
        return data
    timeline = []
    for stop in journey.stops.all():
        arrival = journey.events.filter(stop=stop, kind='arrival').order_by('event_time', 'id').first()
        departure = journey.events.filter(stop=stop, kind='departure').order_by('event_time', 'id').first()
        issue = journey.forecasts.filter(stop=stop).select_related('source_event').order_by('-issued_at', '-id').first()
        timeline.append(dict(sequence=stop.sequence, station_code=stop.station_code, station_name=stop.station_name, section_code=stop.section_id, scheduled_arrival=stop.scheduled_arrival, scheduled_departure=stop.scheduled_departure, actual_arrival=arrival.event_time if arrival else None, actual_departure=departure.event_time if departure else None, platform=(arrival or departure).platform or None if arrival or departure else None, forecast=forecast_json(issue) if issue else None))
    destination = timeline[-1] if timeline else None
    forecast = destination['forecast'] if destination else None
    dest_delay = (forecast['predicted_arrival']-destination['scheduled_arrival']).total_seconds()/60 if forecast else None
    actual_dest_delay = (destination['actual_arrival']-destination['scheduled_arrival']).total_seconds()/60 if destination and destination['actual_arrival'] and destination['scheduled_arrival'] else None
    next_stop = next((row for row in timeline if row['scheduled_arrival'] and not row['actual_arrival'] and (not event or row['sequence'] > event.stop.sequence)), None)
    data.update(stops=timeline, next_stop=next_stop, destination_delay_minutes=dest_delay, destination_actual_delay_minutes=actual_dest_delay, delay_change_minutes=dest_delay-data['current_delay_minutes'] if not completed and dest_delay is not None and data['current_delay_minutes'] is not None else None, conditions=[] if completed else conditions_json(journey.mode, set(row['section_code'] for row in timeline)))
    return data


def conditions_json(mode, section_ids=None):
    return [dict(id=c.external_id, section=c.section_id, from_station=c.section.from_station, to_station=c.section.to_station, kind=c.kind, severity=c.severity, starts_at=c.starts_at, expires_at=c.expires_at, source=c.source, speed_limit_kmph=c.speed_limit_kmph, note=c.note, geometry=c.section.geometry, mode=mode) for c in active_conditions(mode) if section_ids is None or c.section_id in section_ids]


def accuracy(mode, version=None):
    """Score issued predictions only; one latest issue per stop/lead band/version."""
    issues = ForecastIssue.objects.filter(journey__mode=mode).select_related('stop', 'journey', 'source_event').order_by('issued_at', 'id')
    if version:
        issues = issues.filter(model_version=version)
    actuals = {}
    for stop_id, event_time in JourneyEvent.objects.filter(journey__mode=mode, kind='arrival').order_by('event_time').values_list('stop_id','event_time').iterator():
        actuals.setdefault(stop_id,event_time)
    selected = {}
    for issue in issues:
        actual = actuals.get(issue.stop_id)
        if not actual or issue.issued_at >= actual or issue.source_event.received_at > issue.issued_at:
            continue
        lead = (actual-issue.issued_at).total_seconds()/60
        band = '0–30 min' if lead <= 30 else '30–60 min' if lead <= 60 else '1–2 hours' if lead <= 120 else '2+ hours'
        selected[(issue.journey_id, issue.stop_id, band, issue.model_version)] = (issue, actual)
    groups = {}
    for (_, _, band, model), (issue, actual) in selected.items():
        group = groups.setdefault((band, model), [])
        group.append((abs((issue.predicted_arrival-actual).total_seconds()/60), abs((issue.baseline_arrival-actual).total_seconds()/60), None if issue.lower is None or issue.upper is None else issue.lower <= actual <= issue.upper))
    rows = []
    for (band, model), values in groups.items():
        windows = [x[2] for x in values if x[2] is not None]
        rows.append(dict(lead_time=band, model_version=model, samples=len(values), mae_minutes=sum(x[0] for x in values)/len(values), baseline_mae_minutes=sum(x[1] for x in values)/len(values), window_samples=len(windows), coverage_percent=100*sum(windows)/len(windows) if windows else None))
    return dict(mode=mode, rows=rows, sample_count=len(selected), note='Synthetic outcomes only; not evidence of operational accuracy.' if mode == 'simulation' else 'Measured against dated actual arrivals. Latest pre-arrival forecast per stop, lead-time band and model; target coverage is not a guarantee.')
