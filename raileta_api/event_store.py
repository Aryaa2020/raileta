"""The same validation and stream-ordering rules for HTTP and polling jobs."""

from .models import TrainEvent

MOVEMENT_TYPES = ("rtis_position", "coa_arrival", "coa_departure")


def store_event(event):
    event.validate()
    # COA and RTIS have independent clocks/sequences. A late COA report still
    # belongs in history even when a newer RTIS ping has already been received.
    stream_types = (
        ("coa_arrival", "coa_departure")
        if event.event_type.startswith("coa_")
        else (event.event_type,)
    )
    latest = TrainEvent.objects.filter(
        train_number=event.train_number,
        source=event.source,
        event_type__in=stream_types,
        accepted=True,
    )
    if not event.train_number:
        latest = latest.filter(
            station_code=event.station_code, section_code=event.section_code
        )
    latest = latest.order_by("-event_time", "-sequence", "-pk").first()
    accepted = not latest or event.event_time >= latest.event_time
    if (
        latest
        and event.event_time == latest.event_time
        and event.sequence is not None
        and latest.sequence is not None
    ):
        accepted = event.sequence >= latest.sequence
    # The database unique constraint, not a check-then-insert, arbitrates retries.
    record, created = TrainEvent.objects.get_or_create(
        event_id=event.event_id,
        defaults={
            "event_type": event.event_type,
            "source": event.source,
            "event_time": event.event_time,
            "received_at": event.received_at,
            "train_number": event.train_number,
            "station_code": event.station_code,
            "section_code": event.section_code,
            "sequence": event.sequence,
            "payload": event.payload,
            "accepted": accepted,
        },
    )
    return record, created
