"""Labelled, accelerated synthetic replay through the dated Celery pipeline.

GET requests never generate outcomes or forecasts. The simulation clock is
explicit and separate from the wall clock and all live-mode records.
"""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .corridor_simulation import SOURCE, IST, reference, simulate_run
from .journey_models import Journey, RailSection, SimulationSession, ModelRelease, SectionCondition
from .journeys import import_journey, record_event, issue_forecasts, journey_json, record_condition


def enabled():
    return settings.RAILETA_DATA_ADAPTER == 'corridor_simulation'


def clock():
    session = SimulationSession.objects.filter(pk='mas-sbc').first()
    if not session:
        return timezone.now()
    elapsed = max(0,(timezone.now()-session.wall_start).total_seconds())*session.speed
    return session.scenario_start + timedelta(seconds=min(elapsed,86400))


def scenario_now(mode, source=None):
    return clock() if mode=='simulation' and enabled() and source in (None,SOURCE) else timezone.now()


def register(run):
    existing = Journey.objects.filter(train_number=run['train_number'],start_date=run['start_date'],mode='simulation').first()
    if existing:
        if existing.source != SOURCE:
            raise ValueError('This dated simulation identity belongs to another source')
        return existing
    rows = []
    for index, stop in enumerate(run['stops']):
        section_code = None
        if index:
            previous = run['stops'][index-1]
            section_code = f"SYN-{previous['station_code']}-{stop['station_code']}"
            RailSection.objects.get_or_create(code=section_code,defaults=dict(from_station=previous['station_code'],to_station=stop['station_code'],distance_km=stop['distance_km']-previous['distance_km'],tracks=2,speed_kmph=130,geometry=[[previous['longitude'],previous['latitude']],[stop['longitude'],stop['latitude']]],source=SOURCE+' assumed infrastructure / schematic geometry',mode='simulation'))
        rows.append(dict(station_code=stop['station_code'],station_name=stop['station_name'],distance_km=stop['distance_km'],scheduled_arrival=stop['scheduled_arrival'],scheduled_departure=stop['scheduled_departure'],section_code=section_code,recovery_minutes=stop['recovery_minutes'],is_junction=stop['is_junction']))
    return import_journey(dict(run,stops=rows))


def replay_run(run, until):
    journey = register(run)
    context = run['stops'][0]['context']
    start = run['stops'][0]['scheduled_departure'].replace(hour=0,minute=0,second=0,microsecond=0)
    for field,kind in [('restriction_count','restriction'),('block_count','block'),('congestion_count','congestion')]:
        if not context[field] or start > until:
            continue
        for section in journey.stops.exclude(section=None).values_list('section_id',flat=True):
            identity=f"{SOURCE}:{run['start_date']}:{section}:{kind}"
            if not SectionCondition.objects.filter(external_id=identity).exists():
                record_condition(dict(external_id=identity,section_code=section,kind=kind,severity=context['condition_severity'] if kind=='restriction' else context['junction_occupancy'] if kind=='congestion' else 1.,starts_at=start,expires_at=start+timedelta(hours=30),speed_limit_kmph=context['restriction_speed_kmph'] if kind=='restriction' else None,source=SOURCE,note='Synthetic daily corridor scenario, not an official operational order'),enqueue=False)
    known = set(journey.events.values_list('event_id',flat=True))
    events = []
    for stop in run['stops']:
        for kind in ('arrival','departure'):
            at = stop['actual_'+kind]
            if not at:
                continue
            received = at+timedelta(seconds=stop['context']['report_latency_seconds'])
            identity = f"{run['journey_key']}:{stop['sequence']}:{kind}"
            if received<=until and identity not in known:
                events.append(dict(event_id=identity,sequence=stop['sequence'],kind=kind,event_time=at,received_at=received,source=SOURCE,context=stop['context']))
    for event in sorted(events,key=lambda item:item['received_at']):
        record,created=record_event(journey.pk,event,enqueue=False)
        if created and record.accepted:
            issue_forecasts(journey.pk,now=event['received_at'])
    return len(events)


@transaction.atomic
def tick():
    session = SimulationSession.objects.select_for_update().filter(pk='mas-sbc').first()
    if not session:
        return {'status':'simulation_session_not_started'}
    now = clock()
    ref = reference()
    count = 0
    for offset in (-1,0):
        day = now.astimezone(IST).date()+timedelta(days=offset)
        for service in ref['trains']:
            if day.weekday() in service['weekdays']:
                count += replay_run(simulate_run(service,day,seed=91377,ref=ref),now)
    session.last_tick=timezone.now();session.save(update_fields=['last_tick'])
    return dict(mode='simulation',events=count,scenario_time=now.isoformat())


def latest_runs():
    numbers = [t['number'] for t in reference()['trains']]
    return [run for number in numbers if (run:=Journey.objects.filter(train_number=number,mode='simulation',source=SOURCE).order_by('-start_date').first())]


def corridor(name='MAS-SBC'):
    rows=[]
    if name.upper()=='MAS-SBC':
        for run in latest_runs():
            detail=journey_json(run,detail=True)
            stops=[dict(station_code=s['station_code'],station_name=s['station_name']) for s in detail['stops']]
            rows.append(dict(train_number=run.train_number,train_name=run.train_name,stops=stops,train_class='Simulation',current_station=detail['current_station'],next_station=(detail['next_stop'] or {}).get('station_code'),delay_minutes=detail['current_delay_minutes'],is_stale=detail['is_stale'],status=detail['status'],source=SOURCE,journey_id=str(run.pk)))
    return dict(corridor_name=name,total_trains=len(rows),trains=rows,congestion_hotspots=[],timestamp=clock(),scenario_date=clock().astimezone(IST).date(),data_mode='corridor_simulation',note='SIMULATION ONLY · Published train numbers/stops, generated movements and delays. Scenario clock is not today’s service.',weather_observations=[])


def forecast(number):
    run=next((r for r in latest_runs() if r.train_number==str(number)),None)
    if not run:
        raise LookupError('Train is not in the Chennai–Bengaluru simulation roster')
    detail=journey_json(run,detail=True)
    return dict(train_number=run.train_number,train_name=run.train_name,data_mode='corridor_simulation',journey=detail,model_version=ModelRelease.objects.filter(mode='simulation',active=True).values_list('version',flat=True).first())


def departures(code,limit):
    rows=[]
    for run in latest_runs():
        detail=journey_json(run,detail=True)
        for stop in detail['stops']:
            if stop['station_code']!=code or not stop['scheduled_departure'] or stop['actual_departure']:
                continue
            rows.append(dict(train_number=run.train_number,train_name=run.train_name,destination='KSR Bengaluru',scheduled_departure=stop['scheduled_departure'].astimezone(IST).strftime('%d %b %H:%M'),predicted_departure=None,delay_minutes=None,platform=None,status='simulation schedule'))
    return dict(data_mode='corridor_simulation',departures=rows[:limit],scenario_time=clock(),note='SIMULATION · Timetabled departures, not a live station board. Platform assignments unavailable.')
