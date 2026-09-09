"""Trusted, atomic import boundary. No operator condition editing over HTTP."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from raileta_api.journey_models import RailSection
from raileta_api.journeys import import_journey, record_event, record_condition, finite


class Command(BaseCommand):
    help = 'Import sourced dated timetables/events/conditions from a trusted JSON adapter export'

    def add_arguments(self, parser):
        parser.add_argument('path')

    @transaction.atomic
    def handle(self, *args, **options):
        data = json.loads(Path(options['path']).read_text(encoding='utf-8'))
        try:
            for row in data.get('sections', []):
                if row['mode'] not in ('live', 'simulation') or not row.get('source'):
                    raise ValueError('Section mode and source are required')
                finite(row['distance_km'], 'section distance')
                if row.get('tracks') is not None:
                    finite(row['tracks'], 'tracks', 1, 20)
                for point in row.get('geometry', []):
                    if len(point) != 2:
                        raise ValueError('Geometry points must be [longitude, latitude]')
                    finite(point[0], 'longitude', -180, 180); finite(point[1], 'latitude', -90, 90)
                section = RailSection(**row)
                section.full_clean(); section.save(force_insert=True)
            ids = []
            for row in data.get('journeys', []):
                journey = import_journey(row)
                ids.append(str(journey.pk))
                for event in row.get('events', []):
                    record_event(journey.pk, event)
            for event in data.get('events', []):
                record_event(event['journey_id'], event)
            for condition in data.get('conditions', []):
                record_condition(condition)
        except (ValueError, KeyError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(json.dumps({'journey_ids': ids}))
