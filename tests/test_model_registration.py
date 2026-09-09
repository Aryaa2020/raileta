import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from raileta_api.journey_ml import load_bundle
from raileta_api.journey_models import ModelRelease
from raileta_api.management.commands.journey_model import register_bundle


class BundledModelRegistrationTests(TestCase):
    version = 'mas-sbc-synthetic-v1'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.directory = root / self.version
        shutil.copytree(settings.BASE_DIR / 'data/models/journeys' / self.version, self.directory)
        for module in ['raileta_api.journey_ml', 'raileta_api.management.commands.journey_model']:
            patcher = patch(module + '.artifact_root', return_value=root)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.addCleanup(load_bundle.cache_clear)

    def test_registration_is_idempotent_and_never_activates(self):
        self.assertTrue(register_bundle(self.version, 'simulation')['created'])
        self.assertFalse(register_bundle(self.version, 'simulation')['created'])
        self.assertFalse(ModelRelease.objects.get(pk=self.version).active)

    def test_synthetic_bundle_cannot_register_as_live(self):
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            register_bundle(self.version, 'live')
        self.assertFalse(ModelRelease.objects.exists())

    def test_corrupted_model_rolls_back_registration(self):
        (self.directory / 'q50.txt').write_text('corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            register_bundle(self.version, 'simulation')
        self.assertFalse(ModelRelease.objects.exists())

    def test_existing_manifest_cannot_be_replaced(self):
        register_bundle(self.version, 'simulation')
        path = self.directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest['metrics']['samples'] += 1
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            register_bundle(self.version, 'simulation')

    def test_unsafe_version_rejected(self):
        with self.assertRaisesRegex(ValueError, 'safe'):
            register_bundle('../outside', 'simulation')
