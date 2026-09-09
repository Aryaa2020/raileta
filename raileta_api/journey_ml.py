"""LightGBM q10/q50/q90, separate-date CQR calibration, signed TreeSHAP.

No model artifact is unpickled. Activation is a trusted offline operation.
Each worker reads the DB release pointer and verifies content hashes on load.
"""
import hashlib
import json
import math
import re
from functools import lru_cache
from pathlib import Path
from django.conf import settings
from django.db import transaction
from .journey_models import ModelRelease, ForecastIssue

FEATURES = ['current_delay', 'remaining_km', 'remaining_stops', 'scheduled_minutes', 'scheduled_running_minutes', 'scheduled_halt_minutes', 'recovery_minutes', 'junctions', 'mean_tracks', 'single_track_km', 'priority', 'condition_severity', 'restriction_speed_kmph', 'restriction_count', 'block_count', 'congestion_count', 'hour', 'weekday']
from .corridor_simulation import CONTEXT_FEATURES
FEATURES = FEATURES + CONTEXT_FEATURES

REASONS = {
    'current_delay': 'Delay already carried into this section',
    'delay_trend': 'Recent change in reported delay',
    'average_section_speed': 'Recently observed section speed',
    'recovery_minutes': 'Recovery allowance ahead',
    'scheduled_minutes': 'Scheduled journey time remaining',
    'scheduled_running_minutes': 'Running time remaining',
    'scheduled_halt_minutes': 'Scheduled stops ahead',
    'remaining_km': 'Distance still to travel',
    'remaining_stops': 'Number of stops remaining',
    'junctions': 'Junctions on the remaining route',
    'junction_occupancy': 'Reported junction congestion',
    'trains_ahead': 'Reported traffic ahead',
    'precedence_risk': 'Estimated precedence exposure',
    'rain_mm': 'Reported seasonal rain context',
    'visibility_m': 'Reported visibility context',
    'month': 'Seasonal running pattern',
    'condition_severity': 'Reported disruption severity',
    'block_count': 'Blocks reported on the route',
    'restriction_count': 'Active speed restrictions',
    'restriction_speed_kmph': 'Restricted section speed',
    'priority': 'Service priority assumption',
    'gps_age_seconds': 'Age of the latest position report',
    'report_latency_seconds': 'Delay in receiving the station report',
}


def active_version(mode):
    return ModelRelease.objects.filter(mode=mode, active=True).values_list('version', flat=True).first()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def artifact_root():
    return (settings.BASE_DIR / 'data' / 'models' / 'journeys').resolve()


@lru_cache(maxsize=4)
def load_bundle(version, manifest_hash):
    import lightgbm as lgb
    release = ModelRelease.objects.get(version=version)
    directory = (artifact_root() / release.artifact_dir).resolve()
    if not directory.is_relative_to(artifact_root()) or digest(directory/'manifest.json') != manifest_hash:
        raise ValueError('Model manifest integrity failure')
    manifest = json.loads((directory/'manifest.json').read_text())
    if manifest['features'] != FEATURES or manifest['mode'] != release.mode or manifest['target'] != 'dated_arrival_delay_minutes':
        raise ValueError('Incompatible model schema or data mode')
    models = {}
    for quantile in ('q10', 'q50', 'q90'):
        path = directory/(quantile+'.txt')
        if digest(path) != manifest['hashes'][quantile]:
            raise ValueError('Model checksum mismatch')
        models[quantile] = lgb.Booster(model_file=str(path))
        if models[quantile].feature_name() != FEATURES:
            raise ValueError('Model feature order mismatch')
    return models, manifest


def predict(features, mode, version=None):
    fallback = dict(delay=features['current_delay'], lower=None, upper=None, version='schedule-current-delay-v1', calibration='unavailable_no_validated_journey_model', reasons=[])
    if not version:
        return fallback
    try:
        import numpy as np
        release = ModelRelease.objects.get(version=version, mode=mode)
        models, manifest = load_bundle(version, release.manifest_sha256)
        row = np.array([[features.get(k) if features.get(k) is not None else np.nan for k in FEATURES]], dtype=float)
        values = [float(models[k].predict(row, num_threads=1)[0]) for k in ('q10', 'q50', 'q90')]
        if not all(math.isfinite(v) for v in values):
            raise ValueError('Non-finite prediction')
        lower, point, upper = min(values), values[1], max(values)
        correction = manifest.get('monthly_corrections', {}).get(str(int(features.get('month') or 0)), manifest['conformal_correction'])
        if not math.isfinite(correction) or correction < 0:
            raise ValueError('Invalid conformal correction')
        effects = models['q50'].predict(row, pred_contrib=True, num_threads=1)[0]
        reasons = [dict(feature=FEATURES[i], code=FEATURES[i].upper(), minutes=float(effects[i]), description=REASONS.get(FEATURES[i], FEATURES[i].replace('_', ' ').capitalize())) for i in sorted(range(len(FEATURES)), key=lambda i: abs(effects[i]), reverse=True)[:3]]
        return dict(delay=point, lower=lower-correction, upper=upper+correction, version=version, calibration='split_conformal_target_80_measured_not_guaranteed', reasons=reasons)
    except (ValueError, OSError, KeyError, ModelRelease.DoesNotExist):
        return {**fallback, 'calibration': 'model_rejected_baseline_fallback'}


def train_candidate(version, mode):
    import numpy as np
    import lightgbm as lgb
    if mode not in ('live', 'simulation') or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', version):
        raise ValueError('Explicit mode and a safe unique version name are required')
    directory = artifact_root()/version
    if directory.exists() or ModelRelease.objects.filter(pk=version).exists():
        raise ValueError('Versions are immutable; choose a new version')
    samples = {}
    for issue in ForecastIssue.objects.filter(journey__mode=mode).select_related('journey', 'stop', 'source_event').order_by('issued_at'):
        actual = issue.journey.events.filter(stop=issue.stop, kind='arrival').order_by('event_time').first()
        if actual and issue.issued_at < actual.event_time and issue.source_event.received_at <= issue.issued_at:
            # One sample per source event/target, not one per condition-trigger duplicate.
            samples[(issue.source_event_id, issue.stop_id)] = (issue, (actual.event_time-issue.stop.scheduled_arrival).total_seconds()/60)
    dates = sorted({s[0].journey.start_date for s in samples.values()})
    if len(dates) < 10:
        raise ValueError('Need labelled operational forecasts from at least 10 distinct journey dates; aggregate profiles cannot train this model')
    cut1, cut2 = max(1, int(len(dates)*.6)), max(2, int(len(dates)*.8))
    date_sets = (set(dates[:cut1]), set(dates[cut1:cut2]), set(dates[cut2:]))
    splits = [[s for s in samples.values() if s[0].journey.start_date in days] for days in date_sets]
    if any(len(split) < 30 for split in splits):
        raise ValueError('Need at least 30 samples in each chronological train/calibration/test split')
    def arrays(split):
        return np.array([[s[0].features.get(k) if s[0].features.get(k) is not None else np.nan for k in FEATURES] for s in split]), np.array([s[1] for s in split])
    x_train, y_train = arrays(splits[0]); x_cal, y_cal = arrays(splits[1]); x_test, y_test = arrays(splits[2])
    models = {name: lgb.train(dict(objective='quantile', alpha=alpha, verbosity=-1, num_threads=1, seed=42, num_leaves=15, min_data_in_leaf=10), lgb.Dataset(x_train, label=y_train, feature_name=FEATURES), num_boost_round=100) for name, alpha in [('q10', .1), ('q50', .5), ('q90', .9)]}
    cal = np.sort(np.stack([model.predict(x_cal) for model in models.values()]), axis=0)
    scores = np.maximum(cal[0]-y_cal, y_cal-cal[2])
    rank = min(len(scores), math.ceil((len(scores)+1)*.8))
    correction = max(0., float(np.sort(scores)[rank-1]))
    predicted = np.stack([model.predict(x_test) for model in models.values()])
    baseline = np.array([s[0].features['current_delay'] for s in splits[2]])
    metrics = dict(samples=len(y_test), mae_minutes=float(np.mean(abs(predicted[1]-y_test))), baseline_mae_minutes=float(np.mean(abs(baseline-y_test))), coverage_percent=float(np.mean((np.min(predicted,axis=0)-correction <= y_test) & (y_test <= np.max(predicted,axis=0)+correction))*100), target_coverage_percent=80, mode=mode)
    directory.mkdir(parents=True, exist_ok=False)
    for name, model in models.items():
        model.save_model(str(directory/(name+'.txt')))
    manifest = dict(version=version, mode=mode, target='dated_arrival_delay_minutes', features=FEATURES, conformal_correction=correction, metrics=metrics, split_dates=[[d.isoformat() for d in sorted(ds)] for ds in date_sets], split_sizes=[len(s) for s in splits], hashes={name: digest(directory/(name+'.txt')) for name in models})
    (directory/'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    ModelRelease.objects.create(version=version, mode=mode, artifact_dir=version, manifest_sha256=digest(directory/'manifest.json'), metrics=metrics)
    return manifest


@transaction.atomic
def activate(version):
    release = ModelRelease.objects.select_for_update().get(pk=version)
    _, manifest = load_bundle(version, release.manifest_sha256)
    metrics = manifest['metrics']
    if metrics['samples'] < 30 or metrics['mae_minutes'] > metrics['baseline_mae_minutes'] or metrics['coverage_percent'] < 75:
        raise ValueError('Activation rejected: require >=30 held-out samples, MAE no worse than baseline and >=75% measured coverage (80% target)')
    ModelRelease.objects.filter(mode=release.mode, active=True).update(active=False)
    release.active = True
    release.save(update_fields=['active'])
    return metrics
