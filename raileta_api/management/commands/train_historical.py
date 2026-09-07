from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Freeze train-group splits, fit LightGBM on TRAIN, calibrate within TRAIN and evaluate TEST once."

    def add_arguments(self, parser):
        parser.add_argument("--dataset", default=str(settings.BASE_DIR / "indian_railway_delay_data_.csv"))
        parser.add_argument("--output", default=str(settings.BASE_DIR / "data/models/historical-v1"))

    def handle(self, *args, **options):
        from raileta_api.historical_model import train_experiment
        import json
        try:
            manifest = train_experiment(Path(options["dataset"]), Path(options["output"]))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({"sizes": manifest["sizes"], "fit_size": manifest["fit_size"],
            "calibration_size": manifest["calibration_size"], "train_groups": manifest["train_groups"],
            "test_metrics": manifest["test_metrics"], "excluded_rows": len(manifest["dataset"]["excluded"])}, indent=2))
