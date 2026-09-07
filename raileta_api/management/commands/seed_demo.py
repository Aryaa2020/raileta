from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from raileta_api.models import TrainEvent
from raileta_api.services import TRAIN_PROFILES, STATIONS


class Command(BaseCommand):
    help = "Seed deterministic station-event data for the SIH demo."

    def handle(self, *args, **options):
        now = timezone.now().replace(second=0, microsecond=0)
        created = 0
        for index, (train_number, profile) in enumerate(TRAIN_PROFILES.items()):
            station_index = next(i for i, (code, _) in enumerate(STATIONS) if code == profile["current"])
            event_id = f"demo-coa-{train_number}-{now:%Y%m%d%H%M}"
            _, was_created = TrainEvent.objects.update_or_create(
                event_id=event_id,
                defaults={
                    "event_type": "coa_departure",
                    "source": "DEMO_FIXTURE",
                    "event_time": now - timedelta(minutes=28 + index),
                    "train_number": train_number,
                    "station_code": profile["current"],
                    "sequence": station_index,
                    "payload": {"delay_minutes": profile["delay"], "demo": True},
                },
            )
            created += int(was_created)
        TrainEvent.objects.update_or_create(
            event_id=f"demo-weather-KPD-{now:%Y%m%d%H%M}",
            defaults={
                "event_type": "weather_observation",
                "source": "DEMO_FIXTURE",
                "event_time": now - timedelta(minutes=3),
                "station_code": "KPD",
                "payload": {"visibility_m": 850, "has_fog": True, "impact": "moderate", "demo": True},
            },
        )
        self.stdout.write(self.style.SUCCESS(f"Seeded {created} new demo train events."))
