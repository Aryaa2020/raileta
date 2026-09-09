"""Reproducible, explicitly synthetic corridor events. Never an official feed.

Separate random streams for operational outcomes and telemetry. Future section
shocks never enter issuance-time features. No fitted aggregate-profile inputs.
"""
import gzip
import hashlib
import json
import math
import random
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

IST = ZoneInfo('Asia/Kolkata')
REFERENCE = Path(__file__).resolve().parent.parent / 'data/reference/chennai_bengaluru.json'
SOURCE = 'SYNTHETIC_MAS_SBC_V1'
CONTEXT_FEATURES = ['delay_trend', 'average_section_speed', 'trains_ahead', 'junction_occupancy', 'precedence_risk', 'rain_mm', 'visibility_m', 'month', 'gps_age_seconds', 'report_latency_seconds']
SIMULATION_CONDITIONS = ['condition_severity','restriction_speed_kmph','restriction_count','block_count','congestion_count']


def rng_for(*parts):
    return random.Random(int(hashlib.sha256('|'.join(map(str, parts)).encode()).hexdigest()[:16], 16))


def reference():
    return json.loads(REFERENCE.read_text(encoding='utf-8'))


def timetable(train, day, ref=None):
    ref = ref or reference()
    result, last = [], None
    for index, (code, arrival, departure) in enumerate(train['stops']):
        values = []
        for clock in (arrival, departure):
            if clock is None:
                values.append(None)
                continue
            moment = datetime.combine(day, datetime.strptime(clock, '%H:%M').time(), IST)
            while last and moment < last:
                moment += timedelta(days=1)
            values.append(moment)
            last = moment
        name, km, lon, lat = ref['stations'][code]
        row = dict(sequence=index, station_code=code, station_name=name, distance_km=km, scheduled_arrival=values[0], scheduled_departure=values[1], longitude=lon, latitude=lat, is_junction=code in ('AJJ','KPD','JTJ','BWT','SBC'), recovery_minutes=0.)
        if index:
            running = (values[0]-result[-1]['scheduled_departure']).total_seconds()/60
            # Plausible allowance, NOT an assertion about the official WTT.
            row['recovery_minutes'] = min(8., running*.10)
        result.append(row)
    return result


def daily_context(day, seed, stress=False):
    rng = rng_for(seed, day, 'shared-corridor-weather')
    wet = day.month in (6,7,8,9,10,11)
    rain = rng.gammavariate(1.5, 5 if wet else 1) if rng.random() < (.6 if wet else .15) else 0.
    visibility = rng.uniform(600, 2200) if day.month in (12,1,2) and rng.random() < .15 else rng.uniform(6000, 18000)
    # Shared daily congestion/shocks couple different services; this is a
    # corridor scenario prior, not a railway dispatch optimiser.
    congestion = rng.betavariate(2,4)
    severity = rng.uniform(.2,.8) if rng.random() < .22 else 0.
    block = int(rng.random() < (.08 if stress else .025))
    return dict(rain_mm=rain*(1.5 if stress else 1), visibility_m=visibility, junction_occupancy=congestion, trains_ahead=rng.randint(0,4), precedence_risk=congestion*.65, condition_severity=severity, restriction_speed_kmph=60 if severity else None, restriction_count=int(bool(severity)), block_count=block, congestion_count=int(congestion>.5))


def simulate_run(train, day, seed=26028, stress=False, ref=None):
    stops = timetable(train, day, ref)
    rng = rng_for(seed, day, train['number'], 'outcomes')
    shared = daily_context(day, seed, stress)
    origin_delay = rng.gammavariate(1.4, 5) + (rng.uniform(25,100) if rng.random()<.06 else 0)
    previous_departure = stops[0]['scheduled_departure'] + timedelta(minutes=origin_delay)
    previous_delay = origin_delay
    for i, stop in enumerate(stops):
        if i == 0:
            stop.update(actual_arrival=None, actual_departure=previous_departure)
            speed, trend = None, 0.
        else:
            before = stops[i-1]
            scheduled_run = (stop['scheduled_arrival']-before['scheduled_departure']).total_seconds()/60
            distance = stop['distance_km']-before['distance_km']
            recovery = min(max(previous_delay,0)*.45, stop['recovery_minutes'])
            rain_penalty = scheduled_run*min(.20, shared['rain_mm']*.005)
            caution = scheduled_run*.10*shared['condition_severity']
            congestion = shared['junction_occupancy']*(3 if stop['is_junction'] else 1.2)
            block = shared['block_count']*rng.uniform(5,18) if stop['is_junction'] else 0
            # Unobserved future shocks stay label-only. Heavy tails matter.
            shock = rng.expovariate(1/18) if rng.random() < (.07 if stress else .025) else 0.
            noise = rng.gauss(0, 1.5 + math.sqrt(scheduled_run)*.2)
            runtime = max(distance/130*60, scheduled_run-recovery+rain_penalty+caution+congestion+block+shock+noise)
            arrival = previous_departure+timedelta(minutes=runtime)
            stop['actual_arrival'] = arrival
            speed = distance/runtime*60
            new_delay = (arrival-stop['scheduled_arrival']).total_seconds()/60
            trend = new_delay-previous_delay
            if stop['scheduled_departure']:
                halt = (stop['scheduled_departure']-stop['scheduled_arrival']).total_seconds()/60
                dwell = max(.5, halt+rng.gauss(.2,.5)+shared['junction_occupancy']*.5)
                previous_departure = max(stop['scheduled_departure'], arrival+timedelta(minutes=dwell))
                stop['actual_departure'] = previous_departure
                previous_delay = (previous_departure-stop['scheduled_departure']).total_seconds()/60
            else:
                stop['actual_departure'] = None
        telemetry = rng_for(seed, day, train['number'], i, 'receipt')
        latency = telemetry.uniform(2,25) if telemetry.random()>.06 else telemetry.uniform(180,600)
        stop['context'] = dict(shared, delay_trend=trend, average_section_speed=speed, month=day.month, gps_age_seconds=telemetry.uniform(0,30) if telemetry.random()>.08 else telemetry.uniform(181,900), report_latency_seconds=latency)
    return dict(journey_key=f"{train['number']}:{day}:simulation", train_number=train['number'], train_name=train['name'], start_date=day.isoformat(), mode='simulation', source=SOURCE, priority=train['priority_assumption'], stops=stops)


def features_at(run, index, target):
    stops = run['stops']; origin = stops[index]; end = stops[target]
    upcoming = stops[index+1:target+1]
    delay = (origin['actual_departure']-origin['scheduled_departure']).total_seconds()/60
    halt = sum((s['scheduled_departure']-s['scheduled_arrival']).total_seconds()/60 for s in upcoming[:-1])
    total = (end['scheduled_arrival']-origin['scheduled_departure']).total_seconds()/60
    context = origin['context']
    return dict(current_delay=delay, remaining_km=end['distance_km']-origin['distance_km'], remaining_stops=target-index, scheduled_minutes=total, scheduled_running_minutes=total-halt, scheduled_halt_minutes=halt, recovery_minutes=sum(s['recovery_minutes'] for s in upcoming), junctions=sum(s['is_junction'] for s in upcoming), mean_tracks=2., single_track_km=0., priority=run['priority'], hour=origin['actual_departure'].hour, weekday=origin['actual_departure'].weekday(), **context)


def sample_rows(run):
    for i, stop in enumerate(run['stops'][:-1]):
        received = stop['actual_departure']+timedelta(seconds=stop['context']['report_latency_seconds'])
        # Stale inputs are retained in the raw feed but not falsely used as
        # fresh issues. GPS gaps fall back to the current COA departure.
        if stop['context']['report_latency_seconds'] > 180:
            continue
        for j, target in enumerate(run['stops'][i+1:], i+1):
            if target['actual_arrival'] <= received:
                continue
            yield dict(journey_key=run['journey_key'], start_date=run['start_date'], train_number=run['train_number'], source_sequence=i, target_sequence=j, issued_at=received.isoformat(), actual_arrival=target['actual_arrival'].isoformat(), target_delay=(target['actual_arrival']-target['scheduled_arrival']).total_seconds()/60, lead_minutes=(target['actual_arrival']-received).total_seconds()/60, features=features_at(run,i,j))


def feed_rows(run, seed):
    rng = rng_for(seed,run['journey_key'],'gps')
    common = dict(journey_id=run['journey_key'], train_number=run['train_number'], mode='simulation', source=SOURCE)
    for stop in run['stops']:
        for kind in ('arrival','departure'):
            moment = stop['actual_'+kind]
            if moment:
                yield dict(common, event_type='coa_'+kind, event_id=f"{run['journey_key']}:{stop['sequence']}:{kind}", station_code=stop['station_code'], event_time=moment.isoformat(), received_at=(moment+timedelta(seconds=stop['context']['report_latency_seconds'])).isoformat(), platform=None, payload=stop['context'])
    for a,b in zip(run['stops'],run['stops'][1:]):
        duration = (b['actual_arrival']-a['actual_departure']).total_seconds()
        for seconds in range(0,int(duration),30):
            if rng.random()<.04:  # missing pings; do not invent delivered reports
                continue
            fraction = seconds/duration
            moment = a['actual_departure']+timedelta(seconds=seconds)
            yield dict(common,event_type='rtis_position',event_time=moment.isoformat(),received_at=(moment+timedelta(seconds=rng.uniform(1,20))).isoformat(),payload=dict(chainage_km=round(a['distance_km']+fraction*(b['distance_km']-a['distance_km']),3), longitude=round(a['longitude']+fraction*(b['longitude']-a['longitude']),5), latitude=round(a['latitude']+fraction*(b['latitude']-a['latitude']),5), speed_kmph=round((b['distance_km']-a['distance_km'])/duration*3600,2), geometry_quality='synthetic_schematic_not_track_survey'))
    first = run['stops'][0]
    for kind in ('weather', 'caution_order', 'network_state', 'icms_consist'):
        payload = first['context'] if kind != 'icms_consist' else dict(coaches=18, traction='electric', priority=run['priority'], provenance='simulation_assumption')
        yield dict(common,event_type=kind,event_time=first['scheduled_departure'].isoformat(),received_at=first['scheduled_departure'].isoformat(),payload=payload)


def generate(directory, start, end, seed=26028, include_gps=True, progress=print):
    directory = Path(directory)
    if directory.exists():
        raise ValueError('Dataset versions are immutable; use a new output directory')
    directory.mkdir(parents=True)
    counts = dict(journeys=0,samples=0,feed_events=0,gps_pings=0)
    ref = reference()
    with gzip.open(directory/'journeys.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as runs, gzip.open(directory/'samples.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as samples, gzip.open(directory/'feed.jsonl.gz','wt',encoding='utf-8',compresslevel=1) as feed:
        day = start
        while day <= end:
            for train in ref['trains']:
                if day.weekday() not in train['weekdays']:
                    continue
                run = simulate_run(train,day,seed,ref=ref)
                runs.write(json.dumps(run,default=lambda value:value.isoformat(),separators=(',',':'))+'\n')
                counts['journeys'] += 1
                for row in sample_rows(run):
                    samples.write(json.dumps(row,separators=(',',':'))+'\n'); counts['samples'] += 1
                if include_gps:
                    for row in feed_rows(run,seed):
                        feed.write(json.dumps(row,separators=(',',':'))+'\n'); counts['feed_events'] += 1
                        counts['gps_pings'] += int(row['event_type']=='rtis_position')
            if day.day == 1:
                progress(f'{day}: {counts}')
            day += timedelta(days=1)
    manifest = dict(schema=1, mode='simulation', generator=SOURCE, seed=seed, start=start.isoformat(), end=end.isoformat(), counts=counts, reference=ref, gps_cadence_seconds=30, feed_order='grouped by journey/type; replay by received_at, never file order', limitations=['Not calibrated to observed Indian Railways delay distributions.', 'Fixed published timetable, not historical WTT.', 'Schematic GPS, assumed infrastructure and background traffic.', 'Evaluation on generated data cannot establish operational accuracy.'])
    manifest['hashes'] = {name: hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ('journeys.jsonl.gz','samples.jsonl.gz','feed.jsonl.gz')}
    (directory/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest
