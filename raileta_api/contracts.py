from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Dict, Optional


EVENT_TYPES = {
    "rtis_position",
    "coa_arrival",
    "coa_departure",
    "caution_order",
    "weather_observation",
}


@dataclass(frozen=True)
class CanonicalEvent:
    event_id: str
    event_type: str
    source: str
    event_time: datetime
    received_at: datetime
    train_number: str = ""
    station_code: str = ""
    section_code: str = ""
    sequence: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def validate(self):
        if self.event_type not in EVENT_TYPES:
            raise ValueError(f"Unsupported event_type: {self.event_type}")
        if not self.event_id or not self.source:
            raise ValueError("event_id and source are required")
        if not self.train_number and self.event_type in {
            "rtis_position",
            "coa_arrival",
            "coa_departure",
        }:
            raise ValueError("train_number is required for train movement events")
        for name, limit in (
            ("event_id", 180),
            ("source", 40),
            ("train_number", 20),
            ("station_code", 20),
            ("section_code", 40),
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or len(value) > limit:
                raise ValueError(
                    f"{name} must be a string of at most {limit} characters"
                )
        for name in ("event_time", "received_at"):
            value = getattr(self, name)
            if not isinstance(value, datetime) or value.utcoffset() is None:
                raise ValueError(f"{name} must include a timezone")
            if value > datetime.now(timezone.utc) + timedelta(minutes=5):
                raise ValueError(f"{name} is too far in the future")
        if self.sequence is not None and (
            type(self.sequence) is not int or not 0 <= self.sequence < 2**63
        ):
            raise ValueError("sequence must be a non-negative 64-bit integer")
        if not isinstance(self.payload, dict):
            raise ValueError("payload must be a JSON object")
        for key, lower, upper in (
            ("latitude", -90, 90),
            ("longitude", -180, 180),
            ("delay_minutes", -1440, 10080),
        ):
            value = self.payload.get(key)
            if value is not None and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or not lower <= value <= upper
            ):
                raise ValueError(f"Invalid {key}")
        return self
