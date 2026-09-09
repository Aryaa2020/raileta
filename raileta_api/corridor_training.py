"""Offline training from an immutable, simulation-only corpus; no legacy CSV.
Chronological date groups prevent the same dated run leaking across partitions.
Calibration and test are each a full season cycle for the five-year default.
"""
import gzip
import json
import math
import re
from pathlib import Path
import numpy as np
import lightgbm as lgb
from .journey_ml import FEATURES, artifact_root, digest
from .journey_models import ModelRelease


def corpus_rows(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('mode') != 'simulation' or manifest.get('generator') != 'SYNTHETIC_MAS_SBC_V1':
        raise ValueError('Only the explicitly synthetic corridor corpus is accepted')
    if digest(directory/'samples.jsonl.gz') != manifest['hashes']['samples.jsonl.gz']:
        raise ValueError('Training corpus checksum mismatch')
    with gzip.open(directory/'samples.jsonl.gz','rt',encoding='utf-8') as stream:
        rows = [json.loads(line) for line in stream]
    if len(rows) != manifest['counts']['samples']:
        raise ValueError('Training sample count mismatch')
    return rows, manifest


def train_corpus(directory, version):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',version):
        raise ValueError('Use a safe version name')
    destination = artifact_root()/version
    if destination.exists() or ModelRelease.objects.filter(pk=version).exists():
        raise ValueError('Model versions are immutable')
    rows, corpus = corpus_rows(directory)
    dates = sorted({r['start_date'] for r in rows})
    if len(dates)<365*3:
        raise ValueError('Corridor releases require at least three years of dated simulation samples')
    cut1, cut2 = int(len(dates)*.6), int(len(dates)*.8)
    indices = [np.array([i for i,r in enumerate(rows) if r['start_date'] in days]) for days in (set(dates[:cut1]),set(dates[cut1:cut2]),set(dates[cut2:]))]
    x = np.array([[r['features'].get(k) if r['features'].get(k) is not None else np.nan for k in FEATURES] for r in rows],dtype=np.float32)
    y = np.array([r['target_delay'] for r in rows])
    if not np.isfinite(y).all() or any(len(i)<200 for i in indices):
        raise ValueError('Invalid or insufficient labels')
    train,cal,test = indices
    models = {name:lgb.train(dict(objective='quantile',alpha=alpha,verbosity=-1,num_threads=2,seed=26028,deterministic=True,force_col_wise=True,num_leaves=31,min_data_in_leaf=80,learning_rate=.06),lgb.Dataset(x[train],label=y[train],feature_name=FEATURES),num_boost_round=220) for name,alpha in [('q10',.1),('q50',.5),('q90',.9)]}
    calibration = np.sort(np.stack([m.predict(x[cal],num_threads=2) for m in models.values()]),axis=0)
    scores = np.maximum(calibration[0]-y[cal],y[cal]-calibration[2])
    def correction(values):
        return max(0.,float(np.sort(values)[min(len(values),math.ceil((len(values)+1)*.8))-1]))
    global_correction = correction(scores)
    monthly = {str(month):correction(scores[np.array([rows[i]['features']['month']==month for i in cal])]) for month in range(1,13) if sum(rows[i]['features']['month']==month for i in cal)>=200}
    pred = np.stack([m.predict(x[test],num_threads=2) for m in models.values()])
    corrections = np.array([monthly.get(str(rows[i]['features']['month']),global_correction) for i in test])
    lower, point, upper = pred.min(axis=0)-corrections,pred[1],pred.max(axis=0)+corrections
    baseline = x[test,FEATURES.index('current_delay')]
    error, baseline_error = abs(point-y[test]),abs(baseline-y[test])
    covered = (lower<=y[test]) & (y[test]<=upper)
    def metrics(mask):
        return dict(samples=int(mask.sum()),mae_minutes=float(error[mask].mean()),baseline_mae_minutes=float(baseline_error[mask].mean()),coverage_percent=float(covered[mask].mean()*100),mean_window_minutes=float((upper-lower)[mask].mean()))
    report = dict(metrics(np.ones(len(test),dtype=bool)),mode='simulation',target_coverage_percent=80,evaluation_scope='held-out synthetic dates; NOT real-world validation')
    report['by_lead_time'] = {label:metrics(mask) for label,mask in [(label,np.array([lo<=rows[i]['lead_minutes']<hi for i in test])) for label,lo,hi in [('0–30 min',0,30),('30–60 min',30,60),('1–2 hours',60,120),('2+ hours',120,float('inf'))]] if mask.any()}
    report['by_month'] = {str(month):metrics(mask) for month,mask in [(month,np.array([rows[i]['features']['month']==month for i in test])) for month in range(1,13)] if mask.any()}
    # A predeclared harder scenario is reported independently, never calibrated
    # away or used to pick the candidate. Simulator mismatch remains unavoidable.
    from .corridor_simulation import reference,simulate_run,sample_rows
    from datetime import date,timedelta
    stress_rows = []
    ref = reference()
    for offset in range(90):
        day = date(2026,1,1)+timedelta(days=offset)
        for service in ref['trains']:
            if day.weekday() in service['weekdays']:
                stress_rows.extend(sample_rows(simulate_run(service,day,seed=91377,stress=True,ref=ref)))
    sx = np.array([[r['features'].get(k) if r['features'].get(k) is not None else np.nan for k in FEATURES] for r in stress_rows])
    sy = np.array([r['target_delay'] for r in stress_rows])
    sp = np.stack([m.predict(sx,num_threads=2) for m in models.values()])
    sc = np.array([monthly.get(str(r['features']['month']),global_correction) for r in stress_rows])
    report['stress_scenario'] = dict(samples=len(sy),mae_minutes=float(abs(sp[1]-sy).mean()),baseline_mae_minutes=float(abs(sx[:,0]-sy).mean()),coverage_percent=float(((sp.min(axis=0)-sc<=sy)&(sy<=sp.max(axis=0)+sc)).mean()*100),note='Different seed, increased unobserved shocks, blocks and rain; not used for fitting or calibration')
    destination.mkdir(parents=True)
    for name,model in models.items():
        model.save_model(str(destination/(name+'.txt')))
    manifest = dict(version=version,mode='simulation',target='dated_arrival_delay_minutes',features=FEATURES,conformal_correction=global_correction,monthly_corrections=monthly,metrics=report,split_dates=[[dates[0],dates[cut1-1]],[dates[cut1],dates[cut2-1]],[dates[cut2],dates[-1]]],split_sizes=[len(i) for i in indices],corpus_manifest_sha256=digest(Path(directory)/'manifest.json'),corpus_counts=corpus['counts'],hashes={name:digest(destination/(name+'.txt')) for name in models})
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    ModelRelease.objects.create(version=version,mode='simulation',artifact_dir=version,manifest_sha256=digest(destination/'manifest.json'),metrics=report)
    return manifest
