import json
import re
from django.db import transaction
from django.core.management.base import BaseCommand, CommandError
from raileta_api.journey_ml import train_candidate, activate, artifact_root, digest, load_bundle, FEATURES
from raileta_api.journey_models import ModelRelease


@transaction.atomic
def register_bundle(version, mode):
    """Register trusted release files without copying a development database.

    Checksums detect corruption, not publisher authenticity: invoke only on a
    reviewed source release. Registration never activates or changes a version.
    """
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', version):
        raise ValueError('Use a safe immutable model version')
    directory = (artifact_root() / version).resolve()
    if not directory.is_relative_to(artifact_root()):
        raise ValueError('Model directory must remain inside the artifact root')
    manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
    if (manifest.get('version') != version or manifest.get('mode') != mode
            or manifest.get('features') != FEATURES
            or manifest.get('target') != 'dated_arrival_delay_minutes'):
        raise ValueError('Model version, mode or feature schema mismatch')
    expected = dict(mode=mode, artifact_dir=version,
                    manifest_sha256=digest(directory / 'manifest.json'), metrics=manifest['metrics'])
    release, created = ModelRelease.objects.get_or_create(version=version, defaults=expected)
    if any(getattr(release, key) != value for key, value in expected.items()):
        raise ValueError('Registered model versions are immutable')
    load_bundle.cache_clear()
    load_bundle(version, release.manifest_sha256)
    return dict(version=version, mode=mode, registered=True, created=created, active=release.active)


class Command(BaseCommand):
    help = 'Train a dated-journey candidate or explicitly activate a validated version; never uses aggregate profiles'

    def add_arguments(self, parser):
        parser.add_argument('action', choices=['train', 'register', 'activate'])
        parser.add_argument('--model-version', required=True)
        parser.add_argument('--mode', choices=['live', 'simulation'], default='live')

    def handle(self, *args, **options):
        try:
            if options['action'] == 'register':
                result = register_bundle(options['model_version'], options['mode'])
            elif options['action'] == 'train':
                result = train_candidate(options['model_version'], options['mode'])
            else:
                result = activate(options['model_version'])
        except (ValueError, OSError, KeyError, ModelRelease.DoesNotExist) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps(result, indent=2))
