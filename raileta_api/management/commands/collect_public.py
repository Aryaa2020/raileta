"""Run one or more structured ingestion polls for the MAS→SBC pilot.

The command is retained for operator convenience; production scheduling is
owned by Celery beat and execution by a separate Celery worker.
"""
import time

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError

from raileta_api.tasks import ingest_public_feeds


class Command(BaseCommand):
    help = "Poll the configured structured adapter and persist canonical events."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Collect one batch and exit")
        parser.add_argument("--interval", type=int, default=None, help="Seconds between batches (default: settings value)")

    def handle(self, *args, **options):
        from django.conf import settings

        interval = options["interval"] or settings.RAILETA_COLLECTOR_INTERVAL_SECONDS
        while True:
            try:
                accepted = ingest_public_feeds.run()
                self.stdout.write(self.style.SUCCESS(f"Collected {accepted} new MAS-SBC events."))
            except Exception as exc:  # keep a background collector alive across upstream failures
                if options["once"]:
                    raise CommandError(f"Collector cycle failed: {exc}") from exc
                self.stderr.write(self.style.WARNING(f"Collector cycle failed: {exc}"))
            if options["once"]:
                return
            time.sleep(max(30, interval))
