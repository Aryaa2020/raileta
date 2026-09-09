import json
from datetime import date
from django.core.management.base import BaseCommand, CommandError
from raileta_api.corridor_simulation import generate
from raileta_api.corridor_training import train_corpus


class Command(BaseCommand):
    help = 'Generate immutable synthetic Chennai–Bengaluru years or train a simulation-only candidate'

    def add_arguments(self,parser):
        parser.add_argument('action',choices=['generate','train'])
        parser.add_argument('--directory',required=True)
        parser.add_argument('--start',default='2021-01-01')
        parser.add_argument('--end',default='2025-12-31')
        parser.add_argument('--seed',type=int,default=26028)
        parser.add_argument('--model-version')

    def handle(self,*args,**options):
        try:
            if options['action']=='generate':
                start,end = date.fromisoformat(options['start']),date.fromisoformat(options['end'])
                if start>end or (end-start).days>3653 or end>=date.today():
                    raise ValueError('Use a past interval of at most ten years')
                result=generate(options['directory'],start,end,options['seed'],progress=self.stdout.write)
            else:
                if not options['model_version']:
                    raise ValueError('--model-version is required for training')
                result=train_corpus(options['directory'],options['model_version'])
            self.stdout.write(json.dumps(result,indent=2))
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
