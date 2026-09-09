import json
from datetime import datetime, timedelta
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from raileta_api.corridor_replay import tick, replay_run
from raileta_api.corridor_simulation import reference,simulate_run,IST
from raileta_api.journey_models import SimulationSession


class Command(BaseCommand):
    help='Start an explicit synthetic scenario clock; the existing collector/Celery tick advances its dated reports'

    def add_arguments(self,parser):
        parser.add_argument('--at',default='2026-01-15T18:30:00+05:30')
        parser.add_argument('--speed',type=float,default=10)
        parser.add_argument('--history-days',type=int,default=7)

    def handle(self,*args,**options):
        at=datetime.fromisoformat(options['at'])
        if timezone.is_naive(at) or at+timedelta(days=2)>=timezone.now() or not 0<=options['speed']<=60 or not 0<=options['history_days']<=31:
            raise CommandError('Use an aware past scenario time, speed 0–60 and history-days 0–31')
        if SimulationSession.objects.filter(pk='mas-sbc').exists():
            raise CommandError('A replay session already exists; do not rewind issued history. Resume its collector instead.')
        ref=reference()
        for offset in range(options['history_days'],1,-1):
            day=at.astimezone(IST).date()-timedelta(days=offset)
            for service in ref['trains']:
                if day.weekday() in service['weekdays']:
                    replay_run(simulate_run(service,day,seed=91377,ref=ref),at)
            self.stdout.write(f'Imported synthetic history {day}')
        SimulationSession.objects.create(name='mas-sbc',scenario_start=at,wall_start=timezone.now(),speed=options['speed'])
        self.stdout.write(json.dumps(tick()))
