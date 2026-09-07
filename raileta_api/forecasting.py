"""Quantile and calibration helpers shared by demo and trained-model paths."""
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class QuantileForecast:
    q10: datetime
    q50: datetime
    q90: datetime
    coverage: float = 0.80


def monotonic_quantiles(q10: datetime, q50: datetime, q90: datetime) -> QuantileForecast:
    ordered = sorted((q10, q50, q90))
    return QuantileForecast(ordered[0], ordered[1], ordered[2])


def calibrated_window(point: datetime, spread_minutes: int = 12, coverage: float = 0.80) -> QuantileForecast:
    """Return a monotonic q10/q50/q90 window for the configured coverage target."""
    spread = max(1, int(spread_minutes))
    quantiles = monotonic_quantiles(
        point - timedelta(minutes=spread),
        point,
        point + timedelta(minutes=spread),
    )
    return QuantileForecast(quantiles.q10, quantiles.q50, quantiles.q90, coverage)
