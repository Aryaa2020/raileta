from celery import shared_task


@shared_task(name="raileta.reforecast_train")
def reforecast_train(train_number: str):
    from .services import forecast_train

    return forecast_train(train_number, persist=True)["train_number"]


def _ingest_data_sources():
    """Poll the configured adapter and persist accepted canonical events."""
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
    """Retraining hook; production deployments attach the LightGBM pipeline here."""
    return {
        "status": "scheduled",
        "message": "Model retraining hook ready for the LightGBM pipeline",
    }
