import json
from django.conf import settings
from django.core.management.base import BaseCommand
from raileta_api.profile_model import train_profiles


class Command(BaseCommand):
    help = "Freeze grouped TRAIN/TEST/DEMO splits and fit aggregate-delay LightGBM models offline"

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default=str(settings.BASE_DIR / "etrain_delays.csv"))
        parser.add_argument("--output", default=str(settings.BASE_DIR / "data/models/etrain-profiles-v1"))

    def handle(self, *args, **options):
        manifest = train_profiles(options["dataset"], options["output"])
        self.stdout.write(json.dumps({k: manifest[k] for k in ("version", "sizes", "fit_size", "calibration_size", "test_metrics")}, indent=2))
