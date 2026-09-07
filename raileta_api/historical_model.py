"""Small, reproducible destination-delay experiment on the supplied CSV.

No network, target-derived features, or model fitting during requests. Split
membership is frozen before fitting. Calibration is a subset of TRAIN only.
"""
import csv
import hashlib
import json
import math
import random
import re
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import lightgbm as lgb

IST = ZoneInfo("Asia/Kolkata")
FEATURES = ("distance_km", "scheduled_hour", "calendar_year", "day_of_week", "day_of_year", "weekly_service")
REASONS = {
    "distance_km": ("journey_distance", "Recorded journey distance"),
    "scheduled_hour": ("scheduled_arrival_hour", "Scheduled arrival time of day"),
    "calendar_year": ("calendar_year", "Recorded calendar year"),
    "day_of_week": ("day_of_week", "Scheduled arrival day of week"),
    "day_of_year": ("day_of_year", "Scheduled arrival calendar day"),
    "weekly_service": ("service_frequency", "Recorded service frequency"),
}


def _clock(value):
    # Some schedule cells have an Excel 1900 date prefix. Only their time-of-day
    # belongs to the schedule; Date is kept separately and never overwritten.
    match = re.search(r"(?:^|\s)(\d{2}):(\d{2})(?::(\d{2}))?$", value.strip())
    if not match:
        raise ValueError("Invalid clock value")
    hour, minute, second = [int(item or 0) for item in match.groups()]
    if hour > 23 or minute > 59 or second > 59:
        raise ValueError("Clock outside valid range")
    return hour, minute, second


def load_dataset(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    records, excluded = [], []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    seen_runs = set()
    for line, raw in enumerate(rows, 2):
        row = {key: value.strip() for key, value in raw.items()}
        try:
            if not re.fullmatch(r"\d{2}:\d{2}:\d{2}", row["Dealy_min"]):
                raise ValueError("Ambiguous date-formatted duration; not silently repaired")
            hours, minutes, seconds = map(int, row["Dealy_min"].split(":"))
            if minutes > 59 or seconds > 59:
                raise ValueError("Invalid duration")
            delay = hours * 60 + minutes + seconds / 60
            day = datetime.strptime(row["Date"], "%d-%m-%Y %H:%M").replace(tzinfo=IST)
            scheduled = day.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(
                seconds=sum(x * k for x, k in zip(_clock(row["Sc_arr__time"]), (3600, 60, 1))))
            actual = scheduled + timedelta(minutes=delay)
            if (actual.hour, actual.minute, actual.second) != _clock(row["Act_arr_time"]):
                raise ValueError("Recorded delay conflicts with scheduled and actual arrival clocks")
            train = row["Train_no"]
            run_key = (train, day.date().isoformat())
            if run_key in seen_runs:
                raise ValueError("Duplicate train/date run")
            seen_runs.add(run_key)
            distance = float(row["Distance(Km)"])
            if not math.isfinite(distance) or distance <= 0:
                raise ValueError("Invalid journey distance")
            frequency = row["Run_frequency"].lower()
            if frequency not in {"daliy", "daily", "weekly", "tri-weekly"}:
                raise ValueError("Unknown service frequency")
            records.append({
                "record_id": f"{digest[:12]}-row-{line}", "csv_line": line,
                "original_row_id": row["Train_id"], "train_number": train,
                "train_name": row["Train_name"], "source_name": row["Source"],
                "destination_name": row["Destitnation"], "distance_km": distance,
                "scheduled_arrival": scheduled.isoformat(), "actual_arrival": actual.isoformat(),
                "delay_minutes": delay, "season": row["Season"],
                "run_frequency": "daily" if frequency in {"daliy", "daily"} else frequency,
                "raw": raw,
            })
        except (ValueError, KeyError, TypeError) as exc:
            excluded.append({"csv_line": line, "row_id": row.get("Train_id"), "train_number": row.get("Train_no"), "reason": str(exc), "raw": raw})
    return records, {"file": str(path.resolve()), "sha256": digest, "original_rows": len(rows),
        "usable_rows": len(records), "excluded": excluded,
        "provenance": "user_supplied_unverified", "timestamp_assumption": "Date is treated as scheduled arrival date, day-first, Asia/Kolkata; original cells retained",
        "granularity": "one terminal arrival per train/date; no intermediate or pre-arrival movement events"}


def feature_row(record):
    """Explicit allowlist: actual time, delay, train number and row ID are absent."""
    scheduled = datetime.fromisoformat(record["scheduled_arrival"])
    return [float(record["distance_km"]), scheduled.hour + scheduled.minute / 60,
        scheduled.year, scheduled.weekday(), scheduled.timetuple().tm_yday,
        float(record["run_frequency"] == "weekly")]


def matrix(records):
    return np.asarray([feature_row(row) for row in records], dtype=float)


def split_records(records, seed=2026):
    groups = sorted({row["train_number"] for row in records})
    if len(groups) < 5:
        raise ValueError("At least five train groups are required")
    random.Random(seed).shuffle(groups)
    n_demo = max(1, round(len(groups) * .2))
    n_test = max(1, round(len(groups) * .2))
    members = {"live_demo": groups[:n_demo], "test": groups[n_demo:n_demo+n_test], "train": groups[n_demo+n_test:]}
    parts = {name: sorted([row for row in records if row["train_number"] in trains], key=lambda r: (r["actual_arrival"], r["record_id"])) for name, trains in members.items()}
    # Most recent 30% of each TRAIN train's runs is calibration, never fitting.
    fit, calibration = [], []
    for train in members["train"]:
        runs = sorted([row for row in parts["train"] if row["train_number"] == train], key=lambda r: r["scheduled_arrival"])
        n_cal = max(1, math.ceil(len(runs) * .3))
        fit.extend(runs[:-n_cal])
        calibration.extend(runs[-n_cal:])
    if len(fit) < 20 or len(calibration) < 9:
        raise ValueError("Too few fitting/calibration records for this experiment")
    return parts, fit, calibration, members


def ordered_quantiles(models, features):
    return np.sort(np.column_stack([model.predict(features, num_threads=1) for model in models]), axis=1)


def conformal_radius(predictions, actual, coverage=.8):
    scores = np.maximum(predictions[:, 0] - actual, actual - predictions[:, 2])
    rank = math.ceil((len(scores) + 1) * coverage)
    if rank > len(scores):
        raise ValueError("Insufficient calibration size for a finite interval")
    # Never shrink the quantile interval. This remains conservative CQR.
    return max(0.0, float(np.sort(scores)[rank - 1])), rank


def train_experiment(dataset_path, output_dir):
    records, audit = load_dataset(dataset_path)
    parts, fit, calibration, members = split_records(records)
    output = Path(output_dir)
    if output.exists() and any(output.iterdir()):
        raise ValueError("Choose an empty artifact directory; existing frozen evaluations are not overwritten")
    output.mkdir(parents=True, exist_ok=True)
    params = {"objective": "quantile", "learning_rate": .05, "num_leaves": 4,
        "max_depth": 2, "min_data_in_leaf": 5, "lambda_l2": 1., "verbosity": -1,
        "seed": 2026, "deterministic": True, "force_col_wise": True, "num_threads": 1}
    models = []
    for alpha in (.1, .5, .9):
        ds = lgb.Dataset(matrix(fit), label=np.asarray([r["delay_minutes"] for r in fit]), feature_name=list(FEATURES))
        model = lgb.train({**params, "alpha": alpha}, ds, num_boost_round=80)
        model.save_model(str(output / f"q{round(alpha*100)}.txt"))
        models.append(model)
    radius, rank = conformal_radius(ordered_quantiles(models, matrix(calibration)), np.asarray([r["delay_minutes"] for r in calibration]))
    # Parameters are fixed above. TEST is scored exactly once, never used for
    # early stopping, calibration, preprocessing or trying another seed.
    test_predictions = ordered_quantiles(models, matrix(parts["test"]))
    prediction_rows = []
    for record, (low, point, high) in zip(parts["test"], test_predictions):
        low, high = float(low - radius), float(high + radius)
        actual = record["delay_minutes"]
        prediction_rows.append({"record_id": record["record_id"], "train_number": record["train_number"],
            "actual_delay_minutes": actual, "predicted_delay_minutes": float(point),
            "lower_minutes": low, "upper_minutes": high, "absolute_error_minutes": abs(float(point)-actual),
            "covered": bool(low <= actual <= high)})
    n = len(prediction_rows)
    metrics = {"n_test": n, "mae_minutes": float(np.mean([r["absolute_error_minutes"] for r in prediction_rows])),
        "covered_count": sum(r["covered"] for r in prediction_rows),
        "coverage_percent": 100 * sum(r["covered"] for r in prediction_rows) / n,
        "mean_window_width_minutes": float(np.mean([r["upper_minutes"]-r["lower_minutes"] for r in prediction_rows])),
        "train_median_baseline_mae_minutes": float(np.mean(np.abs(np.asarray([r["actual_delay_minutes"] for r in prediction_rows])-np.median([r["delay_minutes"] for r in fit]))))}
    model_digest = hashlib.sha256(b"".join((output / f"q{q}.txt").read_bytes() for q in (10, 50, 90))).hexdigest()
    manifest = {"version": f"historical-lgbm-{audit['sha256'][:12]}-{model_digest[:8]}", "dataset": audit,
        "preprocessing_version": 2, "model_sha256": model_digest,
        "seed": 2026, "ratios_by_train": {"train": .6, "test": .2, "live_demo": .2},
        "train_groups": members, "sizes": {key: len(value) for key, value in parts.items()},
        "fit_size": len(fit), "calibration_size": len(calibration),
        "fit_ids": [r["record_id"] for r in fit], "calibration_ids": [r["record_id"] for r in calibration],
        "features": list(FEATURES), "coverage_target": .8, "conformal_radius_minutes": radius,
        "conformal_order_statistic": rank, "parameters": params, "boosting_rounds": 80,
        "test_metrics": metrics, "created_at": datetime.now(IST).isoformat(),
        "limitations": ["Small sample: only 10 trains and winter observations", "Provenance not independently verified",
            "Calibration observations repeat trains; exchangeability and unseen-train coverage are not guaranteed",
            "Retrospective terminal-arrival scoring, not event-driven en-route ETA forecasting",
            "No weather/congestion/section data; SHAP explains model associations, not delay causes"]}
    for name, value in {**parts, "manifest": manifest, "test_predictions": prediction_rows}.items():
        (output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


class HistoricalModel:
    def __init__(self, artifact_dir):
        self.path = Path(artifact_dir)
        self.manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        self.models = [lgb.Booster(model_file=str(self.path / f"q{q}.txt")) for q in (10, 50, 90)]
        self._explainer = None

    def score(self, record, explain=True):
        features = matrix([record])
        raw = np.asarray([model.predict(features, num_threads=1)[0] for model in self.models])
        ordered = np.sort(raw)
        low, point, high = map(float, ordered)
        radius = self.manifest["conformal_radius_minutes"]
        result = {"q10_minutes": low, "q50_minutes": point, "q90_minutes": high,
            "lower_minutes": low-radius, "upper_minutes": high+radius,
            "model_version": self.manifest["version"], "reason_codes": []}
        if explain:
            import shap
            # Explain the member supplying the post-processed median. Usually
            # q50; if crossing occurred, do not explain a different prediction.
            median_index = int(np.argsort(raw, kind="stable")[1])
            explainer = shap.TreeExplainer(self.models[median_index], feature_perturbation="tree_path_dependent")
            values = np.asarray(explainer.shap_values(features)).reshape(-1)
            base = float(np.asarray(explainer.expected_value).reshape(-1)[0])
            if not np.isclose(base + values.sum(), point, atol=1e-6):
                raise ValueError("SHAP contributions do not reconcile to the point forecast")
            result.update(shap_base_minutes=base, shap_sum_minutes=float(values.sum()), shap_explained_quantile=(10,50,90)[median_index])
            for index in np.argsort(-np.abs(values), kind="stable")[:3]:
                code, description = REASONS[FEATURES[index]]
                result["reason_codes"].append({"category": code, "description": description,
                    "minutes": float(values[index]), "feature": FEATURES[index],
                    "feature_value": float(features[0, index]), "explanation_kind": "SHAP association, not causal attribution"})
        return result


@lru_cache(maxsize=2)
def get_model(artifact_dir):
    return HistoricalModel(artifact_dir)
