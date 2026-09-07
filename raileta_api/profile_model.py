"""Offline LightGBM experiment on train/station *average* delay profiles.

These are not dated train runs. No timetable, RTIS/COA event or individual
arrival window can be reconstructed from this dataset. Outcome percentages
are intentionally excluded from features to avoid a same-period target proxy.
"""
import csv
import hashlib
import json
import math
import random
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np

FEATURES = ("station_code", "service_type", "junction_in_station_name")
REASONS = {
    "station_code": ("station_profile", "Station identity"),
    "service_type": ("service_type", "Service category in recorded train name"),
    "junction_in_station_name": ("station_name_context", "Junction designation in recorded station name"),
}


def service_type(name):
    text = name.lower().replace("-", " ")
    for phrase in ("vande bharat", "rajdhani", "shatabdi", "garib rath", "duronto", "intercity", "mail", "superfast", "express"):
        if phrase in text:
            return phrase
    return "other"


def load_profiles(path):
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    required = {"train_number", "train_name", "station_code", "station_name", "average_delay_minutes", "scraped_at", "source_url"}
    if not rows or not required <= rows[0].keys():
        raise ValueError("Expected the etrain aggregate-profile CSV schema")
    latest, excluded = {}, []
    # Latest capture per train/station, chosen without using its target value.
    for line, raw in enumerate(rows, 2):
        key = (raw["train_number"].strip(), raw["station_code"].strip())
        captured = datetime.fromisoformat(raw["scraped_at"])
        if captured.tzinfo is None:
            raise ValueError("scraped_at must include a timezone")
        prior = latest.get(key)
        if prior and prior[0] > captured:
            excluded.append({"csv_line": line, "reason": "Older duplicate train/station profile"})
            continue
        if prior:
            excluded.append({"csv_line": prior[1], "reason": "Older duplicate train/station profile"})
        latest[key] = (captured, line, raw)
    records = []
    for (_, line, raw) in latest.values():
        try:
            target = float(raw["average_delay_minutes"])
            if not math.isfinite(target) or target < 0:
                raise ValueError("Invalid average delay")
        except (TypeError, ValueError):
            excluded.append({"csv_line": line, "reason": "Missing or invalid average delay target"})
            continue
        records.append({"record_id": f"{digest[:12]}-row-{line}", "csv_line": line,
            **{k: raw[k].strip() for k in ("train_number", "train_name", "station_code", "station_name", "scraped_at", "source_url")},
            "average_delay_minutes": target, "raw": raw})
    return records, {"file": str(path.resolve()), "sha256": digest, "original_rows": len(rows),
        "unique_profiles": len(latest), "usable_rows": len(records), "excluded": excluded,
        "granularity": "Aggregate train/station delay profile, not an individual train run",
        "provenance": "user_supplied_etrain_export_unverified", "time_semantics": "scraped_at is collection time, never arrival/departure time",
        "history_period": "Source URLs request d=1y; exact averaging dates and sample counts are not supplied"}


def split_profiles(records, seed=2026):
    trains = sorted({r["train_number"] for r in records})
    random.Random(seed).shuffle(trains)
    if len(trains) < 30:
        raise ValueError("This experiment requires at least 30 distinct train groups")
    n_demo = round(len(trains) * .2)
    n_test = round(len(trains) * .2)
    groups = {"live_demo": trains[:n_demo], "test": trains[n_demo:n_demo+n_test], "train": trains[n_demo+n_test:]}
    parts = {k: sorted([r for r in records if r["train_number"] in members], key=lambda r: (r["scraped_at"], r["csv_line"])) for k, members in groups.items()}
    # Calibration train numbers are disjoint from fitting train numbers too.
    n_cal = math.ceil(len(groups["train"]) * .2)
    calibration_groups = groups["train"][-n_cal:]
    fit = [r for r in parts["train"] if r["train_number"] not in calibration_groups]
    calibration = [r for r in parts["train"] if r["train_number"] in calibration_groups]
    return parts, fit, calibration, groups


def fit_vocabulary(fit):
    return {"station_code": sorted({r["station_code"] for r in fit}), "service_type": sorted({service_type(r["train_name"]) for r in fit})}


def feature_row(record, vocabulary):
    """Use only station/name metadata. No labels, percentages, dates or IDs."""
    values = (record["station_code"], service_type(record["train_name"]))
    codes = [vocabulary[key].index(value) if value in vocabulary[key] else -1 for key, value in zip(FEATURES, values)]
    return codes + [int("JN" in record["station_name"].upper().split() or "JUNCTION" in record["station_name"].upper())]


def matrix(records, vocabulary):
    return np.asarray([feature_row(r, vocabulary) for r in records], dtype=float)


def quantiles(models, x):
    return np.sort(np.column_stack([m.predict(x, num_threads=1) for m in models]), axis=1)


def train_profiles(dataset_path, output_dir):
    records, audit = load_profiles(dataset_path)
    parts, fit, calibration, groups = split_profiles(records)
    path = Path(output_dir)
    if path.exists() and any(path.iterdir()):
        raise ValueError("Frozen artifacts are never overwritten; choose an empty output directory")
    path.mkdir(parents=True, exist_ok=True)
    vocabulary = fit_vocabulary(fit)
    # Fixed before looking at TEST. No tuning, early stopping or fitting on TEST.
    params = {"objective": "quantile", "learning_rate": .04, "num_leaves": 12, "max_depth": 4,
        "min_data_in_leaf": 15, "min_data_per_group": 5, "cat_smooth": 10, "lambda_l2": 2,
        "verbosity": -1, "seed": 2026, "deterministic": True, "force_col_wise": True, "num_threads": 1}
    models = []
    for alpha in (.1, .5, .9):
        data = lgb.Dataset(matrix(fit, vocabulary), label=[r["average_delay_minutes"] for r in fit],
            feature_name=list(FEATURES), categorical_feature=[0, 1])
        model = lgb.train({**params, "alpha": alpha}, data, num_boost_round=150)
        model.save_model(str(path / f"q{round(alpha*100)}.txt"))
        models.append(model)
    q = quantiles(models, matrix(calibration, vocabulary))
    y = np.asarray([r["average_delay_minutes"] for r in calibration])
    scores = np.maximum(q[:, 0]-y, y-q[:, 2])
    rank = math.ceil((len(scores)+1)*.8)
    radius = max(0., float(np.sort(scores)[rank-1]))
    evaluation = []
    for row, (low, point, high) in zip(parts["test"], quantiles(models, matrix(parts["test"], vocabulary))):
        actual = row["average_delay_minutes"]
        low, high = float(low-radius), float(high+radius)
        evaluation.append({"record_id": row["record_id"], "train_number": row["train_number"], "station_code": row["station_code"],
            "actual_average_delay_minutes": actual, "predicted_average_delay_minutes": float(point),
            "lower_minutes": low, "upper_minutes": high, "absolute_error_minutes": abs(float(point)-actual), "covered": bool(low <= actual <= high)})
    baseline = float(np.median([r["average_delay_minutes"] for r in fit]))
    metrics = {"n_test": len(evaluation), "test_trains": len(groups["test"]),
        "mae_minutes": float(np.mean([r["absolute_error_minutes"] for r in evaluation])),
        "covered_count": sum(r["covered"] for r in evaluation),
        "coverage_percent": 100 * sum(r["covered"] for r in evaluation) / len(evaluation),
        "mean_window_width_minutes": float(np.mean([r["upper_minutes"]-r["lower_minutes"] for r in evaluation])),
        "train_median_baseline_mae_minutes": float(np.mean([abs(r["actual_average_delay_minutes"]-baseline) for r in evaluation])),
        "measurement_unit": "held-out train/station average delay profiles, NOT individual arrivals"}
    model_hash = hashlib.sha256(b"".join((path / f"q{q}.txt").read_bytes() for q in (10,50,90))).hexdigest()
    manifest = {"version": f"profile-lgbm-{audit['sha256'][:12]}-{model_hash[:8]}", "model_sha256": model_hash,
        "dataset": audit, "dataset_kind": "aggregate_profiles", "seed": 2026, "train_groups": groups,
        "sizes": {k: len(v) for k,v in parts.items()}, "ratios_by_train": {"train": .6, "test": .2, "live_demo": .2},
        "fit_size": len(fit), "calibration_size": len(calibration),
        "fit_ids": [r["record_id"] for r in fit], "calibration_ids": [r["record_id"] for r in calibration],
        "fit_train_numbers": sorted({r["train_number"] for r in fit}), "calibration_train_numbers": sorted({r["train_number"] for r in calibration}),
        "features": list(FEATURES), "vocabulary": vocabulary, "coverage_target": .8,
        "conformal_radius_minutes": radius, "conformal_order_statistic": rank,
        "parameters": params, "boosting_rounds": 150, "test_metrics": metrics,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "limitations": ["Aggregate averages cannot train or validate individual-run ETA accuracy or arrival coverage",
            "No scheduled/actual arrival times, run dates, positions, weather or event sequences",
            "Profiles within each train are correlated; pooled conformal calibration does not guarantee unseen-train coverage",
            "No sample counts: each profile weighted equally, not by number of actual journeys",
            "Unseen station/category values use missing-category handling; no target-based encoding",
            "No verified MAS-SBC service in this export; demo scope is the supplied held-out dataset",
            "Source URLs supplied in CSV, not independently fetched or authenticated"]}
    for name, value in {**parts, "manifest": manifest, "test_predictions": evaluation}.items():
        (path / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


class ProfileModel:
    def __init__(self, path):
        self.path = Path(path)
        self.manifest = json.loads((self.path / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("dataset_kind") != "aggregate_profiles":
            raise ValueError("Wrong model kind: aggregate profiles required")
        digest = hashlib.sha256(b"".join((self.path / f"q{q}.txt").read_bytes() for q in (10,50,90))).hexdigest()
        if digest != self.manifest["model_sha256"]:
            raise ValueError("Model checksum mismatch")
        self.models = [lgb.Booster(model_file=str(self.path / f"q{q}.txt")) for q in (10,50,90)]
        self.explainers = {}

    def score(self, record, explain=True):
        x = matrix([record], self.manifest["vocabulary"])
        raw = np.asarray([m.predict(x, num_threads=1)[0] for m in self.models])
        low, point, high = map(float, np.sort(raw))
        radius = self.manifest["conformal_radius_minutes"]
        result = {"q10_minutes": low, "q50_minutes": point, "q90_minutes": high,
            "lower_minutes": low-radius, "upper_minutes": high+radius, "model_version": self.manifest["version"], "reason_codes": []}
        if explain:
            import shap
            index = int(np.argsort(raw, kind="stable")[1])
            if index not in self.explainers:
                self.explainers[index] = shap.TreeExplainer(self.models[index], feature_perturbation="tree_path_dependent")
            explainer = self.explainers[index]
            values = np.asarray(explainer.shap_values(x)).reshape(-1)
            base = float(np.asarray(explainer.expected_value).reshape(-1)[0])
            if not np.isclose(base + values.sum(), point, atol=1e-6):
                raise ValueError("SHAP does not reconcile to median prediction")
            result.update(shap_base_minutes=base, shap_sum_minutes=float(values.sum()))
            for i in np.argsort(-np.abs(values), kind="stable")[:3]:
                code, description = REASONS[FEATURES[i]]
                result["reason_codes"].append({"category": code, "description": description, "minutes": float(values[i]),
                    "feature": FEATURES[i], "explanation_kind": "SHAP association, not causal attribution"})
        return result


@lru_cache(maxsize=2)
def get_profile_model(path):
    return ProfileModel(path)
