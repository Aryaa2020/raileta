"""Inspect, advance or explicitly restart the offline profile replay."""
import json
from django.core.management.base import BaseCommand, CommandError
from django.db.models import F
from django.utils import timezone
from raileta_api.profile_replay import HistoricalProfileReplayAdapter, enabled, profile_health, replay_tick


class Command(BaseCommand):
    help = "Offline profile replay: --once, --reset, or status (default). Reset preserves prior generations."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--reset", action="store_true")

    def handle(self, *args, **options):
        if not enabled():
            raise CommandError("Set RAILETA_DATA_ADAPTER=historical_profiles first")
        adapter = HistoricalProfileReplayAdapter()
        if options["reset"]:
            session = adapter.session()
            type(session).objects.filter(pk=session.pk).update(generation=F("generation")+1, next_index=0, next_due_at=timezone.now(), last_replayed_at=None)
        if options["once"]:
            self.stdout.write(f"Profiles processed: {replay_tick()}")
        self.stdout.write(json.dumps(profile_health(), indent=2, default=str))
