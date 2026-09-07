"""Export the immutable collector history for training and audit workflows."""
import csv
import json
from datetime import datetime
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from raileta_api.models import FeedSnapshot, TrainEvent


class Command(BaseCommand):
    help = "Export collected feed snapshots and canonical events as JSONL or CSV."

    def add_arguments(self, parser):
        parser.add_argument("--output", default=None, help="Destination file (default: data/exports/raileta_<timestamp>.<format>)")
        parser.add_argument("--format", choices=("jsonl", "csv"), default="jsonl")
        parser.add_argument("--kind", choices=("all", "snapshots", "events"), default="all")
        parser.add_argument("--source", default=None, help="Filter by source, e.g. PUBLIC_NTES or PUBLIC_WEATHER_MODEL")
        parser.add_argument("--since", default=None, help="ISO-8601 lower bound for fetched/event time")

    def handle(self, *args, **options):
        since = None
        if options["since"]:
            since = parse_datetime(options["since"])
            if since is None:
                raise CommandError("--since must be a valid ISO-8601 timestamp")
            if timezone.is_naive(since):
                since = timezone.make_aware(since, timezone.get_current_timezone())

        records = []
        kind = options["kind"]
        if kind in {"all", "snapshots"}:
            snapshots = FeedSnapshot.objects.order_by("fetched_at")
            if options["source"]:
                snapshots = snapshots.filter(source=options["source"])
            if since:
                snapshots = snapshots.filter(fetched_at__gte=since)
            records.extend({
                "record_type": "feed_snapshot",
                "id": row.pk,
                "source": row.source,
                "timestamp": row.fetched_at.isoformat(),
                "endpoint": row.endpoint,
                "http_status": row.http_status,
                "parser_version": row.parser_version,
                "raw_path": row.raw_path,
                "content_sha256": row.content_sha256,
                "content_bytes": row.content_bytes,
                "event_type": "",
                "train_number": "",
                "station_code": "",
                "event_time": "",
                "accepted": "",
                "payload": row.payload,
                "error": row.error,
            } for row in snapshots)

        if kind in {"all", "events"}:
            events = TrainEvent.objects.order_by("event_time")
            if options["source"]:
                events = events.filter(source=options["source"])
            if since:
                events = events.filter(event_time__gte=since)
            records.extend({
                "record_type": "train_event",
                "id": row.pk,
                "source": row.source,
                "timestamp": row.received_at.isoformat(),
                "endpoint": "",
                "http_status": "",
                "parser_version": "",
                "raw_path": "",
                "content_sha256": "",
                "content_bytes": "",
                "event_type": row.event_type,
                "train_number": row.train_number,
                "station_code": row.station_code,
                "event_time": row.event_time.isoformat(),
                "accepted": row.accepted,
                "payload": row.payload,
                "error": "",
            } for row in events)

        output = options["output"]
        if output:
            target = Path(output)
        else:
            target = Path("data/exports") / f"raileta_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{options['format']}"
        if not target.is_absolute():
            target = Path.cwd() / target
        target.parent.mkdir(parents=True, exist_ok=True)

        with target.open("w", encoding="utf-8", newline="") as handle:
            if options["format"] == "jsonl":
                for record in records:
                    handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            else:
                fields = ["record_type", "id", "source", "timestamp", "endpoint", "http_status", "parser_version", "raw_path", "content_sha256", "content_bytes", "event_type", "train_number", "station_code", "event_time", "accepted", "payload", "error"]
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for record in records:
                    row = dict(record)
                    row["payload"] = json.dumps(row["payload"], ensure_ascii=False, default=str)
                    writer.writerow(row)
        self.stdout.write(self.style.SUCCESS(f"Exported {len(records)} records to {target}"))
