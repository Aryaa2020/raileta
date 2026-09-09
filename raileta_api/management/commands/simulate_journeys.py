"""Small deterministic event replay inspired by the secondary simulator.

Only SIM-prefixed trains/sections are created, in the simulation namespace.
No synthetic model is activated and the configured data adapter is not changed.
"""
import json
import re
from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.db import transaction
from raileta_api.journey_models import RailSection, Journey
from raileta_api.journeys import IST, import_journey, record_event, record_condition, issue_forecasts


class Command(BaseCommand):
    help = 'Create/replay two explicitly synthetic dated services without touching real journeys or aggregate experiments'

    def add_arguments(self, parser):
        parser.add_argument('--train-number', default='SIM001', help='Use a new SIM-prefixed ID to create another demo without overwriting old runs')

    @transaction.atomic
    def handle(self, *args, **options):
        number = options['train_number']
        if not re.fullmatch(r'SIM[A-Za-z0-9_-]{1,17}', number):
            raise CommandError('Synthetic train numbers must begin with SIM and be at most 20 characters')
        now = timezone.now().replace(second=0, microsecond=0)
        coords = [[80.27,13.08],[79.66,13.08],[79.13,12.92],[77.58,12.97]]
        names = [('MAS','Chennai Central'),('AJJ','Arakkonam'),('KPD','Katpadi Junction'),('SBC','KSR Bengaluru')]
        for i in range(1,4):
            RailSection.objects.get_or_create(code=f'SIM-{i}', defaults=dict(from_station=names[i-1][0], to_station=names[i][0], distance_km=70, tracks=2, speed_kmph=100, geometry=coords[i-1:i+1], source='SYNTHETIC_DEMO', mode='simulation'))
        ids = []
        for previous in (True, False):
            origin = now-timedelta(minutes=40, days=int(previous))
            day = origin.astimezone(IST).date()
            if Journey.objects.filter(train_number=number, start_date=day, mode='simulation').exists():
                continue
            stops = []
            for i,(code,name) in enumerate(names):
                scheduled = origin+timedelta(minutes=60*i)
                stops.append(dict(station_code=code, station_name=name, distance_km=i*70, scheduled_arrival=scheduled.isoformat() if i else None, scheduled_departure=(scheduled+timedelta(minutes=3)).isoformat() if i<3 else None, section_code=f'SIM-{i}' if i else None, recovery_minutes=3 if i else 0, is_junction=i==2))
            journey = import_journey(dict(train_number=number, train_name='Synthetic corridor service', start_date=day.isoformat(), mode='simulation', source='SYNTHETIC_DEMO', priority=2, stops=stops))
            ids.append(str(journey.pk))
            if not previous:
                record_condition(dict(external_id='SIM-speed-demo', section_code='SIM-2', kind='restriction', severity=.6, speed_limit_kmph=40, starts_at=(now-timedelta(minutes=10)).isoformat(), expires_at=(now+timedelta(hours=2)).isoformat(), source='SYNTHETIC_DEMO', note='Synthetic speed restriction for demonstration'), enqueue=False)
            for minute in (10,20,39):
                at = origin+timedelta(minutes=minute)
                event,_ = record_event(journey.pk, dict(event_id=f'{journey.pk}-origin-{minute}', sequence=0, kind='departure', event_time=at.isoformat(), received_at=at.isoformat(), source='SYNTHETIC_DEMO'), enqueue=False)
                issue_forecasts(journey.pk, now=at)
            if previous:
                for i in range(1,4):
                    at = origin+timedelta(minutes=60*i+30-i*3)
                    record_event(journey.pk, dict(event_id=f'{journey.pk}-arrival-{i}', sequence=i, kind='arrival', event_time=at.isoformat(), received_at=at.isoformat(), source='SYNTHETIC_DEMO'), enqueue=False)
                    issue_forecasts(journey.pk, now=at)
        self.stdout.write(json.dumps({'mode':'simulation','created':ids,'note':'Synthetic baseline forecasts only; no claimed 80% windows or model accuracy.'}))
