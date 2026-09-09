from celery import shared_task


@shared_task(name='raileta.reforecast_journey')
def reforecast_journey(journey_id):
    from .journeys import issue_forecasts
    return issue_forecasts(journey_id)


@shared_task(name='raileta.sweep_journeys')
def sweep_journeys():
    from django.utils import timezone
    from .journey_models import Journey
    # Rechecks expiry/model changes and retries durable events after broker outages.
    from django.db.models import Q
    from .corridor_simulation import SOURCE
    from .corridor_replay import scenario_now
    ids = Journey.objects.filter(Q(source=SOURCE, mode='simulation', stops__scheduled_arrival__gte=scenario_now('simulation')) | (~Q(source=SOURCE) & Q(stops__scheduled_arrival__gte=timezone.now()))).values_list('id', flat=True).distinct()
    for journey_id in ids:
        reforecast_journey.delay(str(journey_id))
    return {'queued': len(ids)}


@shared_task(name="raileta.reforecast_train")
def reforecast_train(train_number: str):
    from .services import forecast_train

    return forecast_train(train_number, persist=True)["train_number"]


def _ingest_data_sources():
    """Poll the configured adapter and persist accepted canonical events."""
    from .corridor_replay import enabled as simulation_enabled, tick
    if simulation_enabled():
        return tick()
    from .profile_replay import enabled, replay_tick
    if enabled():
        return replay_tick()
    from .ingestion import collect_public_batch
    from .models import FeedSnapshot
    from .event_store import store_event, MOVEMENT_TYPES

    events, snapshots = collect_public_batch()
    for snapshot in snapshots:
        FeedSnapshot.objects.create(**snapshot)
    count = 0
    changed_trains = set()
    for event in events:
        if event.payload.get('journey_id'):
            from .journeys import record_canonical
            record, created = record_canonical(event)
            count += int(created)
            continue
        record, created = store_event(event)
        if created and record.accepted:
            count += 1
            if event.train_number and event.event_type in MOVEMENT_TYPES:
                changed_trains.add(event.train_number)
    for number in sorted(changed_trains):
        reforecast_train.delay(number)
    return count


@shared_task(name="raileta.ingest_data_sources")
def ingest_data_sources():
    return _ingest_data_sources()


@shared_task(name="raileta.ingest_public_feeds")
def ingest_public_feeds():
    """Backward-compatible task name for existing local commands."""
    return _ingest_data_sources()


@shared_task(name="raileta.nightly_retrain")
def nightly_retrain():
    """Opt-in dated operational candidates; activation remains an offline review."""
    from django.conf import settings
    from django.utils import timezone
    from .journey_ml import train_candidate
    if not getattr(settings, 'RAILETA_JOURNEY_RETRAIN_ENABLED', False):
        return {'status': 'disabled', 'message': 'Dated journey retraining is opt-in; no aggregate experiment is changed'}
    version = 'journey-live-' + timezone.now().strftime('%Y%m%dT%H%M%S')
    try:
        manifest = train_candidate(version, 'live')
        return {'status': 'candidate_awaiting_review', 'version': version, 'metrics': manifest['metrics']}
    except ValueError as exc:
        return {'status': 'insufficient_data_or_rejected', 'message': str(exc)}
