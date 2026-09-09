from datetime import date, timedelta
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_GET
from .journey_models import Journey, JourneyStop, ForecastIssue, ModelRelease, RailSection
from .journeys import journey_json, forecast_json, conditions_json, accuracy


def mode_of(request):
    mode = request.GET.get('mode', 'live')
    if mode not in ('live', 'simulation'):
        raise ValueError('mode must be live or simulation')
    return mode


@require_GET
def journeys(request):
    try:
        mode = mode_of(request)
        query = Journey.objects.filter(mode=mode)
        if request.GET.get('train_number'):
            query = query.filter(train_number=request.GET['train_number'])
        if request.GET.get('date'):
            query = query.filter(start_date=date.fromisoformat(request.GET['date']))
        return JsonResponse(dict(mode=mode, journeys=[journey_json(j) for j in query[:200]], note='Dated journeys only. Aggregate delay profiles are not journeys.'))
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


@require_GET
def journey_detail(request, journey_id):
    try:
        return JsonResponse(journey_json(Journey.objects.get(pk=journey_id, mode=mode_of(request)), detail=True))
    except Journey.DoesNotExist:
        return JsonResponse({'detail': 'No journey in this data mode'}, status=404)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


@require_GET
def history(request, journey_id):
    try:
        journey = Journey.objects.get(pk=journey_id, mode=mode_of(request))
        sequence = int(request.GET.get('sequence', '0'))
        stop = journey.stops.get(sequence=sequence)
        issues = journey.forecasts.filter(stop=stop).select_related('source_event').order_by('-issued_at', '-id')[:200]
        actual = journey.events.filter(stop=stop, kind='arrival').order_by('event_time').first()
        return JsonResponse(dict(journey_id=str(journey.pk), sequence=sequence, mode=journey.mode, scheduled_arrival=stop.scheduled_arrival, actual_arrival=actual.event_time if actual else None, forecasts=[forecast_json(i) for i in reversed(list(issues))]))
    except (Journey.DoesNotExist, ValueError, JourneyStop.DoesNotExist):
        return JsonResponse({'detail': 'Journey or station not found; check mode and sequence'}, status=404)


@require_GET
def conditions(request):
    try:
        mode = mode_of(request)
        return JsonResponse(dict(mode=mode, conditions=conditions_json(mode), sections=list(RailSection.objects.filter(mode=mode).values('code', 'from_station', 'to_station', 'geometry')), read_only=True, note='Only supplied active conditions are shown; no records does not establish a clear route.'))
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


@require_GET
def metrics(request):
    try:
        mode = mode_of(request)
        result = accuracy(mode, request.GET.get('model_version'))
        releases = list(ModelRelease.objects.filter(mode=mode).values('version', 'active', 'metrics'))
        result['releases'] = releases
        result['drift_status'] = 'insufficient_samples' if result['sample_count'] < 30 else 'review_required' if any(r['mae_minutes'] > r['baseline_mae_minutes'] or r['coverage_percent'] is not None and r['window_samples'] >= 30 and r['coverage_percent'] < 75 for r in result['rows']) else 'no_threshold_breach'
        for release in releases:
            report = release['metrics']
            if release['active'] and (report.get('stress_scenario', {}).get('coverage_percent', 100) < 75 or any(row.get('coverage_percent', 100) < 75 for row in report.get('by_month', {}).values())):
                result['drift_status'] = 'review_required'
        return JsonResponse(result)
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)


@require_GET
def arrivals(request, station_code):
    try:
        mode = mode_of(request)
        hours = int(request.GET.get('hours', '3'))
        if not 1 <= hours <= 24:
            raise ValueError('hours must be between 1 and 24')
        from .corridor_replay import scenario_now
        now = scenario_now(mode)
        end = now + timedelta(hours=hours)
        rows = []
        for journey in Journey.objects.filter(mode=mode, stops__station_code=station_code).distinct():
            detail = journey_json(journey, detail=True)
            for stop in detail['stops']:
                forecast = stop['forecast']
                if stop['station_code'] != station_code or stop['actual_arrival'] or not forecast:
                    continue
                if now <= forecast['predicted_arrival'] <= end:
                    rows.append(dict(journey_id=str(journey.id), train_number=journey.train_number, train_name=journey.train_name, start_date=journey.start_date, mode=mode, is_stale=detail['is_stale'], **stop))
        rows.sort(key=lambda row: row['forecast']['predicted_arrival'])
        return JsonResponse(dict(mode=mode, arrivals=rows[:100], window_start=now, window_end=end, note='Dated journey forecasts only. Stale predictions remain labelled; platforms require a supplied report.'))
    except ValueError as exc:
        return JsonResponse({'detail': str(exc)}, status=400)
