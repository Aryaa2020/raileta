"""Structured event-source adapters for the RailETA ingestion pipeline.

The default adapter is :class:`SimulatedFeedAdapter`, which emits the same
RTIS/COA/caution-order event contract expected from the SIH architecture. An
authorised CRIS JSON endpoint can be selected with one configuration change.
The legacy public HTML adapter remains available only behind the explicit
``RAILETA_ENABLE_PUBLIC_SCRAPING`` feature flag and is never the default path.
"""
import hashlib
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Any, Dict, Iterable, List, Protocol
from zoneinfo import ZoneInfo

import requests
from django.conf import settings
from bs4 import BeautifulSoup

from .contracts import CanonicalEvent

logger = logging.getLogger(__name__)
PILOT_STATIONS = {"MAS", "AJJ", "KPD", "JTJ", "KPN", "BWT", "KJM", "BNC", "SBC"}
Event = CanonicalEvent

SIMULATED_ROUTE = [
    {"station_code": "MAS", "station_name": "MGR Chennai Central", "lat": 13.0827, "lng": 80.2707},
    {"station_code": "AJJ", "station_name": "Arakkonam Junction", "lat": 13.0840, "lng": 79.6700},
    {"station_code": "KPD", "station_name": "Katpadi Junction", "lat": 12.9690, "lng": 79.1440},
    {"station_code": "JTJ", "station_name": "Jolarpettai Junction", "lat": 12.5700, "lng": 78.5700},
    {"station_code": "KPN", "station_name": "Kuppam", "lat": 12.7550, "lng": 78.3600},
    {"station_code": "BWT", "station_name": "Bangarapet Junction", "lat": 12.9910, "lng": 77.8640},
    {"station_code": "KJM", "station_name": "Krishnarajapuram", "lat": 13.0000, "lng": 77.6600},
    {"station_code": "BNC", "station_name": "Bengaluru Cantonment", "lat": 12.9930, "lng": 77.5980},
    {"station_code": "SBC", "station_name": "KSR Bengaluru City", "lat": 12.9780, "lng": 77.5700},
]


class DataSourceAdapter(Protocol):
    """Common boundary for RTIS/COA/CRIS event producers."""

    def poll(self) -> list[Event]:
        ...


def _event_from_mapping(row: Dict[str, Any], default_source: str = "CRIS_REST") -> Event:
    """Normalize one structured REST event without knowing its producer."""
    now = datetime.now(dt_timezone.utc)
    event_time = _parse_time(row.get("event_time"), dt_timezone.utc)
    if not event_time or not row.get("event_id"):
        raise ValueError("Structured events require event_id and a valid event_time")
    received_at = _parse_time(row.get("received_at"), dt_timezone.utc) or now
    payload = row.get("payload", {})
    return Event(
        event_id=str(row.get("event_id") or hashlib.sha1(json.dumps(row, sort_keys=True, default=str).encode()).hexdigest()),
        event_type=str(row.get("event_type", "")),
        source=str(row.get("source") or default_source),
        event_time=event_time,
        received_at=received_at,
        train_number=str(row.get("train_number", "")),
        station_code=str(row.get("station_code", "")),
        section_code=str(row.get("section_code", "")),
        sequence=row.get("sequence"),
        payload=payload,
    ).validate()


class SimulatedFeedAdapter:
    """Deterministic CRIS-shaped feed for local demos without railway access.

    It emits a position ping every poll, station events at section boundaries,
    and an occasional caution order. The event IDs/sequence values are derived
    from the 30-second epoch so repeated worker polls deduplicate naturally.
    """

    source = "SIMULATED_CRIS"

    def __init__(self, train_numbers: Iterable[str], interval_seconds: int = 30):
        self.train_numbers = tuple(str(number) for number in train_numbers)
        self.interval_seconds = max(1, int(interval_seconds))

    def poll(self) -> list[Event]:
        now = datetime.now(dt_timezone.utc)
        tick = int(now.timestamp() // self.interval_seconds)
        events: list[Event] = []
        route = SIMULATED_ROUTE
        for train_index, train_number in enumerate(self.train_numbers):
            # A two-minute section cadence keeps the demo visibly moving while
            # still looking like station-event progress rather than GPS replay.
            section_tick = (tick + train_index * 3) % (len(route) * 4)
            run_index = (tick + train_index * 3) // (len(route) * 4)
            run_id = f"sim-{train_number}-{run_index}"
            section_index = min(len(route) - 1, section_tick // 4)
            within_section = (section_tick % 4) / 4
            origin = route[section_index]
            destination = route[min(section_index + 1, len(route) - 1)]
            latitude = origin["lat"] + (destination["lat"] - origin["lat"]) * within_section
            longitude = origin["lng"] + (destination["lng"] - origin["lng"]) * within_section
            section_code = f"{origin['station_code']}-{destination['station_code']}"
            delay = float((int(train_number) + section_index * 3) % 17)
            rtis_payload = {
                "latitude": round(latitude, 6),
                "longitude": round(longitude, 6),
                "speed_kmh": None,
                "section_code": section_code,
                "delay_minutes": delay,
                "position_mode": "rtis_simulation",
                "simulated": True,
                "time_compressed": True,
                "run_id": run_id,
                "station_sequence": section_index,
            }
            events.append(Event(
                event_id=f"sim-rtis-{train_number}-{tick}", event_type="rtis_position", source=self.source,
                event_time=now, received_at=now, train_number=train_number,
                station_code=origin["station_code"], section_code=section_code, sequence=tick,
                payload=rtis_payload,
            ).validate())
            # Repeat the latest boundary reports with stable IDs: a missed
            # polling tick must not lose arrival/departure evidence entirely.
            boundary_tick = tick - section_tick % 4
            boundaries = [("coa_arrival", boundary_tick)]
            if section_tick % 4 >= 1 and section_index < len(route) - 1:
                boundaries.append(("coa_departure", boundary_tick + 1))
            for event_type, boundary in boundaries:
                events.append(Event(
                    event_id=f"sim-coa-{run_id}-{section_index}-{event_type}", event_type=event_type,
                    source=self.source, event_time=datetime.fromtimestamp(boundary * self.interval_seconds, dt_timezone.utc), received_at=now, train_number=train_number,
                    station_code=origin["station_code"], section_code=section_code, sequence=boundary,
                    payload={"delay_minutes": delay, "status": "departed" if event_type == "coa_departure" else "arrived", "simulated": True, "run_id": run_id, "station_sequence": section_index},
                ).validate())
            if (tick + train_index) % 10 == 0:
                events.append(Event(
                    event_id=f"sim-caution-{section_code}-{tick // 10}", event_type="caution_order",
                    source=self.source, event_time=now, received_at=now, train_number="",
                    station_code=origin["station_code"], section_code=section_code, sequence=tick // 10,
                    payload={"restriction_kmh": 45, "reason": "temporary engineering caution", "active": True, "simulated": True, "valid_until": (now + timedelta(minutes=5)).isoformat()},
                ).validate())
        return events


class CrisRestAdapter:
    """Structured CRIS/RTIS/COA REST adapter reserved for authorised access."""

    def __init__(self, url: str, timeout: int = 8, session: requests.Session | None = None):
        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    def poll(self) -> list[Event]:
        if not self.url:
            raise ValueError("CRIS_REST_URL is required when selecting the CRIS adapter")
        response = self.session.get(self.url, timeout=self.timeout, headers={"Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        rows = data if isinstance(data, list) else data.get("events", data.get("data", [])) if isinstance(data, dict) else []
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("CRIS response must contain a list of event objects")
        return [_event_from_mapping(row) for row in rows]


class PublicFeedAdapter:
    source = "PUBLIC"

    def __init__(self, url: str = "", timeout: int = 8):
        self.url = url
        self.timeout = timeout
        self.snapshots: List[Dict[str, Any]] = []

    def fetch_json(self) -> Any:
        if not self.url:
            return None
        response = requests.get(self.url, timeout=self.timeout, headers={"User-Agent": "RailETA-SIH-Demo/1.0"})
        response.raise_for_status()
        return response.json()

    def fetch_text(self, url: str) -> str:
        response = requests.get(url, timeout=self.timeout, headers={"User-Agent": "RailETA-SIH-Demo/1.0"})
        response.raise_for_status()
        return response.text

    def _event_id(self, event_type: str, payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return f"{self.source.lower()}-{event_type}-{hashlib.sha1(raw).hexdigest()[:20]}"

    def save_raw(self, key: str, payload: Any) -> Dict[str, Any]:
        """Persist the complete upstream payload to a date-partitioned file.

        The database keeps a compact index while the raw file provides a durable,
        replayable record for training-data extraction. Set
        ``RAILETA_STORE_RAW_PAYLOADS=false`` only when storage policy requires it.
        """
        if not getattr(settings, "RAILETA_STORE_RAW_PAYLOADS", True):
            return {"raw_path": "", "content_sha256": "", "content_bytes": 0}
        root = Path(getattr(settings, "RAILETA_RAW_DATA_DIR", "data/raw"))
        if not root.is_absolute():
            root = Path(settings.BASE_DIR) / root
        now = datetime.now(dt_timezone.utc)
        target_dir = root / self.source.lower() / now.strftime("%Y/%m/%d")
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_key = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(key))[:80]
        content = json.dumps(payload, ensure_ascii=False, default=str, indent=2).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        target = target_dir / f"{now.strftime('%H%M%S_%f')}_{safe_key}_{digest[:12]}.json"
        target.write_bytes(content)
        return {"raw_path": str(target), "content_sha256": digest, "content_bytes": len(content)}


class PublicNtesAdapter(PublicFeedAdapter):
    source = "PUBLIC_NTES"

    def poll(self) -> list[Event]:
        return self.collect()

    def collect(self) -> List[CanonicalEvent]:
        if not getattr(settings, "RAILETA_ENABLE_PUBLIC_SCRAPING", False):
            raise RuntimeError("Public HTML scraping is disabled; configure RAILETA_DATA_ADAPTER=simulated or cris_rest")
        if self.url and "enquiry.indianrail.gov.in" in self.url:
            try:
                return self.collect_official_ntes()
            except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("Official NTES page unavailable; trying configured public fallback: %s", exc)
                self.snapshots.append({
                    "source": self.source,
                    "endpoint": self.url,
                    "http_status": getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                    "parser_version": "ntes-html-v1",
                    "payload": {},
                    "error": str(exc),
                })
        try:
            data = self.fetch_json() if self.url else None
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            logger.warning("Configured public feed unavailable; trying page adapter: %s", exc)
            self.snapshots.append({
                "source": self.source,
                "endpoint": self.url,
                "http_status": getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                "parser_version": "public-json-v1",
                "payload": {},
                "error": str(exc),
            })
            data = None
        if data:
            raw_meta = self.save_raw("ntes", data)
            self.snapshots.append({
                "source": self.source,
                "endpoint": self.url,
                "http_status": 200,
                "parser_version": "public-json-v1",
                "payload": {"row_count": len(data) if isinstance(data, list) else len(data.get("trains", data.get("data", []))) if isinstance(data, dict) else 0},
                **raw_meta,
            })
            return self._events_from_rows(data if isinstance(data, list) else data.get("trains", data.get("data", [])))
        # NTES-compatible JSON is preferred. Until it is configured, use the
        # public RailYatri pages for the locked MAS→SBC train set. Keep the
        # source name honest so the API never presents RailYatri as NTES.
        self.source = "PUBLIC_RAILYATRI"
        return self.collect_railyatri()

    def collect_official_ntes(self) -> List[CanonicalEvent]:
        """Read the public CRIS/NTES running-status page.

        The NTES site is a form-backed HTML application rather than a public
        JSON API. We obtain its short-lived CSRF field, submit the same
        running-status form as the site, retain the complete HTML, and parse
        every stop row (including non-stopping stations).
        """
        base = self.url.rstrip("/") + "/"
        start_date = datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d-%b-%Y")
        events: List[CanonicalEvent] = []
        train_numbers = tuple(getattr(settings, "RAILETA_TRAIN_NUMBERS", ()))
        # Requests are independent: a slow/expired service must not hold the
        # entire public roster (and therefore the 30-second poller) hostage.
        with ThreadPoolExecutor(max_workers=max(1, min(5, len(train_numbers)))) as pool:
            futures = {pool.submit(self._collect_official_train, base, start_date, str(train_number)): str(train_number) for train_number in train_numbers}
            for future in as_completed(futures):
                train_number = futures[future]
                try:
                    snapshot, train_events = future.result()
                except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
                    endpoint = f"{base}tr?opt=TrainRunning&subOpt=fullR&trainNo={train_number}&jDate={start_date}"
                    logger.warning("Official NTES request failed (%s): %s", train_number, exc)
                    snapshot = {
                        "source": self.source,
                        "endpoint": endpoint,
                        "http_status": getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                        "parser_version": "ntes-html-v1",
                        "payload": {"train_number": train_number},
                        "error": str(exc),
                    }
                    train_events = []
                self.snapshots.append(snapshot)
                events.extend(train_events)
        return events

    def _collect_official_train(self, base: str, start_date: str, train_number: str):
        session = requests.Session()
        session.headers.update({"User-Agent": "RailETA-SIH-Demo/1.0", "Accept-Language": "en-IN,en;q=0.8"})
        landing = session.get(base, timeout=self.timeout)
        landing.raise_for_status()
        token_response = session.get(base + "GetCSRFToken?t=" + str(int(datetime.now(dt_timezone.utc).timestamp() * 1000)), timeout=self.timeout)
        token_response.raise_for_status()
        token_match = re.search(r"name=['\"]([^'\"]+)['\"]\s+value=['\"]([^'\"]+)['\"]", token_response.text)
        if not token_match:
            raise ValueError("NTES CSRF token was not returned")
        token_name, token_value = token_match.groups()
        form = {"lan": "en", "jDate": start_date, "trainNo": train_number, token_name: token_value}
        endpoint = f"{base}tr?opt=TrainRunning&subOpt=fullR&trainNo={train_number}&jDate={start_date}"
        response = session.post(endpoint, data=form, timeout=self.timeout, headers={"Referer": base})
        response.raise_for_status()
        if not response.text.strip():
            return ({
                "source": self.source,
                "endpoint": endpoint,
                "http_status": response.status_code,
                "parser_version": "ntes-html-v1",
                "payload": {"train_number": train_number},
                "error": "NTES returned an empty status page",
            }, [])
        parsed = _parse_ntes_running_page(response.text, train_number, start_date)
        raw_meta = self.save_raw(f"ntes_{train_number}", {"url": endpoint, "html": response.text})
        return ({
            "source": self.source,
            "endpoint": endpoint,
            "http_status": response.status_code,
            "parser_version": "ntes-html-v1",
            "payload": parsed["snapshot"],
            **raw_meta,
        }, parsed["events"])

    def _events_from_rows(self, rows: Iterable[Dict[str, Any]]) -> List[CanonicalEvent]:
        now = datetime.now(dt_timezone.utc)
        events = []
        for row in rows:
            train_number = str(row.get("train_number", row.get("trainNo", "")))
            station_code = str(row.get("station_code", row.get("station", "")))
            if not train_number or not station_code:
                continue
            payload = {"delay_minutes": row.get("delay_minutes", row.get("delay", 0)), "raw": row}
            events.append(CanonicalEvent(
                event_id=self._event_id("coa_arrival", {"train": train_number, "station": station_code, "time": row.get("event_time", now.isoformat())}),
                event_type="coa_arrival",
                source=self.source,
                event_time=_parse_time(row.get("event_time")) or now,
                received_at=now,
                train_number=train_number,
                station_code=station_code,
                sequence=row.get("sequence"),
                payload=payload,
            ).validate())
        return events

    def collect_railyatri(self) -> List[CanonicalEvent]:
        events: List[CanonicalEvent] = []
        template = getattr(settings, "PUBLIC_RAILYATRI_URL_TEMPLATE", "")
        for train_number in getattr(settings, "RAILETA_TRAIN_NUMBERS", ()): 
            if not template:
                break
            url = template.format(train_number=train_number)
            try:
                html = self.fetch_text(url)
                data = _extract_next_data(html)
                route = _find_route(data)
                page_props = data.get("props", {}).get("pageProps", {}) if isinstance(data, dict) else {}
                raw_meta = self.save_raw(train_number, {"url": url, "html": html, "next_data": data})
                self.snapshots.append({
                    "source": self.source,
                    "endpoint": url,
                    "http_status": 200,
                    "payload": _compact_snapshot(train_number, page_props, route),
                    **raw_meta,
                })
                events.extend(_route_events(train_number, route, self.source, url))
            except (requests.RequestException, ValueError, TypeError, json.JSONDecodeError) as exc:
                logger.warning("Public train page unavailable (%s): %s", train_number, exc)
                self.snapshots.append({"source": self.source, "endpoint": url, "http_status": 0, "payload": {"train_number": train_number}, "error": str(exc)})
        return events


class ImdWeatherAdapter(PublicFeedAdapter):
    source = "PUBLIC_IMD"

    def collect(self) -> List[CanonicalEvent]:
        try:
            data = self.fetch_json()
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            self.snapshots.append({
                "source": self.source,
                "endpoint": self.url,
                "http_status": getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                "parser_version": "imd-v1",
                "payload": {},
                "error": str(exc),
            })
            return []
        if not data:
            return []
        rows = data if isinstance(data, list) else data.get("stations", data.get("data", []))
        raw_meta = self.save_raw("weather", data)
        self.snapshots.append({
            "source": self.source,
            "endpoint": self.url,
            "http_status": 200,
            "parser_version": "imd-v1",
            "payload": {"row_count": len(rows) if isinstance(rows, list) else 0},
            **raw_meta,
        })
        now = datetime.now(dt_timezone.utc)
        events = []
        for row in rows:
            station_code = str(row.get("station_code", row.get("station", "")))
            if not station_code:
                continue
            payload = {"visibility_m": row.get("visibility_m"), "has_fog": row.get("has_fog", False), "rainfall_mm_per_hour": row.get("rainfall_mm_per_hour", 0), "raw": row}
            events.append(CanonicalEvent(
                event_id=self._event_id("weather_observation", {"station": station_code, "time": row.get("event_time", now.isoformat())}),
                event_type="weather_observation",
                source=self.source,
                event_time=_parse_time(row.get("event_time")) or now,
                received_at=now,
                station_code=station_code,
                payload=payload,
            ).validate())
        return events


class OpenMeteoWeatherAdapter(PublicFeedAdapter):
    """No-key weather-model adapter used when IMD access is unavailable."""

    source = "PUBLIC_WEATHER_MODEL"

    def collect(self, station_coordinates: Dict[str, Dict[str, Any]]) -> List[CanonicalEvent]:
        if not self.url or not station_coordinates:
            return []
        stations = list(station_coordinates.items())
        params = {
            "latitude": ",".join(str(item[1]["latitude"]) for item in stations),
            "longitude": ",".join(str(item[1]["longitude"]) for item in stations),
            "current": "temperature_2m,relative_humidity_2m,precipitation,visibility,weather_code,wind_speed_10m",
            "timezone": "Asia/Kolkata",
        }
        try:
            response = requests.get(self.url, params=params, timeout=self.timeout, headers={"User-Agent": "RailETA-SIH-Demo/1.0"})
            response.raise_for_status()
            data = response.json()
            locations = data if isinstance(data, list) else [data]
            raw_meta = self.save_raw("weather", {"request": params, "response": data})
            self.snapshots.append({
                "source": self.source,
                "endpoint": response.url,
                "http_status": response.status_code,
                "parser_version": "open-meteo-v1",
                "payload": {"request": params, "locations": len(locations)},
                **raw_meta,
            })
        except (requests.RequestException, ValueError, json.JSONDecodeError) as exc:
            self.snapshots.append({
                "source": self.source,
                "endpoint": self.url,
                "http_status": getattr(getattr(exc, "response", None), "status_code", 0) or 0,
                "parser_version": "open-meteo-v1",
                "payload": {"request": params},
                "error": str(exc),
            })
            return []

        now = datetime.now(dt_timezone.utc)
        events: List[CanonicalEvent] = []
        for (station_code, station), row in zip(stations, locations):
            current = row.get("current", {}) if isinstance(row, dict) else {}
            if not current:
                continue
            event_time = _parse_time(current.get("time"), ZoneInfo("Asia/Kolkata"))
            if event_time is None:
                logger.warning("Weather response for %s has no valid source timestamp", station_code)
                continue
            visibility = current.get("visibility")
            weather_code = current.get("weather_code")
            try:
                has_fog = int(weather_code) in {45, 48} or (visibility is not None and float(visibility) < 1000)
            except (TypeError, ValueError):
                has_fog = False
            payload = {
                "provider": "Open-Meteo",
                "observation_kind": "weather_model_current",
                "latitude": station["latitude"],
                "longitude": station["longitude"],
                "temperature_c": current.get("temperature_2m"),
                "relative_humidity_pct": current.get("relative_humidity_2m"),
                "precipitation_mm": current.get("precipitation"),
                "visibility_m": visibility,
                "wind_speed_kmh": current.get("wind_speed_10m"),
                "weather_code": weather_code,
                "has_fog": has_fog,
                "raw": current,
            }
            events.append(CanonicalEvent(
                event_id=self._event_id("weather_observation", {"station": station_code, "time": event_time.isoformat()}),
                event_type="weather_observation",
                source=self.source,
                event_time=event_time,
                received_at=now,
                station_code=station_code,
                payload=payload,
            ).validate())
        return events


def _parse_time(value: Any, default_tz=dt_timezone.utc):
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=dt_timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=default_tz)
    except (TypeError, ValueError):
        return None


def _extract_next_data(html: str) -> Any:
    """Extract Next.js page data without relying on a fragile DOM parser."""
    marker = '<script id="__NEXT_DATA__"'
    start = html.find(marker)
    if start < 0:
        raise ValueError("__NEXT_DATA__ was not found")
    start = html.find(">", start) + 1
    end = html.find("</script>", start)
    if start <= 0 or end < 0:
        raise ValueError("invalid __NEXT_DATA__ script")
    return json.loads(html[start:end])


def _find_route(value: Any) -> List[Dict[str, Any]]:
    """Find the route array in a public page's nested JSON payload."""
    if isinstance(value, dict):
        for key, candidate in value.items():
            if key == "route" and isinstance(candidate, list) and candidate and isinstance(candidate[0], dict):
                return candidate
            found = _find_route(candidate)
            if found:
                return found
    elif isinstance(value, list):
        for candidate in value:
            found = _find_route(candidate)
            if found:
                return found
    return []


def _ntes_clock_minutes(value: str):
    match = re.search(r"\b(\d{1,2}):(\d{2})\b", value or "")
    if not match:
        return None
    return int(match.group(1)) * 60 + int(match.group(2))


def _ntes_station_code(text: str):
    match = re.search(r"\b([A-Z][A-Z0-9]{0,5})\s+PF(?:\s|\d|\*)", text or "")
    if match:
        return match.group(1)
    match = re.search(r"\s-\s([A-Z][A-Z0-9]{0,5})\b", text or "")
    return match.group(1) if match else ""


def _ntes_station_name(text: str, code: str):
    if not text:
        return code
    cleaned = re.sub(r"\s+", " ", text).strip()
    if code:
        cleaned = re.sub(rf"\b{re.escape(code)}\s+PF(?:\s+\d+\*?)?", "", cleaned)
        cleaned = re.sub(rf"\s+-\s+{re.escape(code)}\b", "", cleaned)
    cleaned = re.sub(r"\b(?:Non-Stopping|SRC|DSTN|On Time|KMs?)\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b(?:\s+\d{1,2}-[A-Za-z]{3})?\*?", "", cleaned)
    cleaned = re.sub(r"\b\d+(?:\.\d+)?\s+KMs?\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\b\d+\b", "", cleaned)
    cleaned = re.sub(r"[⇓*]", "", cleaned)
    parts = [part.strip() for part in cleaned.split(" ") if part.strip()]
    # Prefer the longest contiguous station-name fragment after status words.
    return " ".join(parts[-8:]).strip() or code


def _parse_ntes_running_page(html: str, train_number: str, start_date: str):
    soup = BeautifulSoup(html, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else f"Train {train_number}"
    panel = soup.find("div", class_=lambda classes: classes and "panel" in classes)
    status_text = panel.get_text(" ", strip=True) if panel else ""
    rows = []
    current_code = ""
    for row in soup.find_all("div", class_=lambda classes: classes and ("stopRow" in classes or "nonStopRow" in classes)):
        classes = row.get("class", [])
        text = row.get_text(" ", strip=True)
        code = _ntes_station_code(text)
        if not code:
            continue
        is_stop = "nonStopRow" not in classes
        btexts = [item.get_text(" ", strip=True) for item in row.find_all("b")]
        station_name = _ntes_station_name(" ".join(btexts), code)
        times = re.findall(r"\b\d{1,2}:\d{2}\s+\d{1,2}-[A-Za-z]{3}\*?", text)
        arrival = _ntes_clock_minutes(times[0]) if times else None
        departure = _ntes_clock_minutes(times[-1]) if times else None
        if len(times) == 1:
            arrival = departure = _ntes_clock_minutes(times[0])
        distance_match = re.search(r"(\d+(?:\.\d+)?)\s+KMs?", text, flags=re.I)
        row_data = {
            "sequence": len(rows) + 1,
            "station_code": code,
            "station_name": station_name,
            "stop": is_stop,
            "sta_min": arrival,
            "std_min": departure,
            "scheduled_arrival": times[0] if times else None,
            "scheduled_departure": times[-1] if times else None,
            "distance_from_source": distance_match.group(1) if distance_match else None,
            "status": "current" if "currentStation" in classes else ("scheduled" if is_stop else "non_stopping"),
        }
        rows.append(row_data)
        if "currentStation" in classes:
            current_code = code

    if not rows:
        raise ValueError(f"No station rows found for NTES train {train_number}")
    source_match = re.search(r"([A-Z][A-Z .'-]+?)\s+-\s+([A-Z]{2,6})", title)
    next_code = ""
    if current_code:
        current_index = next((index for index, row in enumerate(rows) if row["station_code"] == current_code), -1)
        if current_index >= 0:
            next_code = next((row["station_code"] for row in rows[current_index + 1:] if row["stop"]), "")
    elif rows:
        current_code = rows[0]["station_code"]
        next_code = next((row["station_code"] for row in rows[1:] if row["stop"]), "")
    now = datetime.now(dt_timezone.utc)
    snapshot = {
        "train_number": train_number,
        "status": {
            "success": True,
            "source": rows[0]["station_code"],
            "destination": rows[-1]["station_code"],
            "title": status_text or title,
            "new_message": status_text or title,
            "current_station_code": current_code,
            "next_station_code": next_code,
            "position_mode": "station_event",
            "gps_unable": True,
            "source_checked_at": now.isoformat(),
        },
        "route": rows,
    }
    events = []
    if current_code and re.search(r"\b(departed|arrived|reached)\b", status_text, flags=re.I):
        event_type = "coa_arrival" if re.search(r"\b(arrived|reached)\b", status_text, flags=re.I) else "coa_departure"
        events.append(CanonicalEvent(
            event_id=f"public-ntes-{train_number}-{current_code}-{now.strftime('%Y%m%d%H%M')}-{event_type}",
            event_type=event_type,
            source="PUBLIC_NTES",
            event_time=now,
            received_at=now,
            train_number=train_number,
            station_code=current_code,
            payload={"status": status_text, "delay_minutes": _delay_from_text(status_text), "raw_source": "CRIS_NTES"},
        ).validate())
    return {"snapshot": snapshot, "events": events}


def _delay_from_text(text: str):
    match = re.search(r"(?:late|delay(?:ed)?)\s+(?:by\s+)?(\d+)\s*(?:minutes?|mins?)?", text or "", flags=re.I)
    return float(match.group(1)) if match else None


def _route_events(train_number: str, route: Iterable[Dict[str, Any]], source: str, url: str) -> List[CanonicalEvent]:
    now = datetime.now(dt_timezone.utc)
    events: List[CanonicalEvent] = []
    for stop in route:
        station = str(stop.get("stationCode", stop.get("station_code", ""))).upper()
        if station not in PILOT_STATIONS:
            continue
        status = str(stop.get("status", "")).lower()
        actual = stop.get("actualDeparture") or stop.get("actualArrival") or stop.get("actual_departure") or stop.get("actual_arrival")
        event_time = _parse_time(actual)
        if not event_time and status not in {"departed", "arrived"}:
            continue
        event_time = event_time or now
        delay = stop.get("delayDeparture", stop.get("delayArrival", stop.get("delay_minutes", stop.get("delay", 0))))
        payload = {
            "delay_minutes": delay or 0,
            "status": status or "observed",
            "scheduled_arrival": stop.get("scheduledArrival"),
            "scheduled_departure": stop.get("scheduledDeparture"),
            "platform": stop.get("platform", stop.get("platform_number")),
            "source_url": url,
            "raw": stop,
        }
        event_type = "coa_arrival" if status == "arrived" or stop.get("actualArrival") else "coa_departure"
        event_id = f"{source.lower()}-{train_number}-{station}-{event_time.isoformat()}-{event_type}"
        events.append(CanonicalEvent(
            event_id=event_id,
            event_type=event_type,
            source=source,
            event_time=event_time,
            received_at=now,
            train_number=str(train_number),
            station_code=station,
            sequence=stop.get("sequence"),
            payload=payload,
        ).validate())
    return events


def collect_public_events() -> Iterable[CanonicalEvent]:
    events, _ = collect_public_batch()
    yield from events


def get_train_adapter() -> DataSourceAdapter:
    """Build the configured structured train feed adapter."""
    adapter_name = getattr(settings, "RAILETA_DATA_ADAPTER", "simulated").strip().lower()
    if adapter_name in {"cris", "cris_rest", "rest"}:
        return CrisRestAdapter(getattr(settings, "CRIS_REST_URL", ""))
    if adapter_name in {"public", "public_scrape", "ntes", "railyatri"}:
        if not getattr(settings, "RAILETA_ENABLE_PUBLIC_SCRAPING", False):
            raise RuntimeError("Public scraping adapter requested but RAILETA_ENABLE_PUBLIC_SCRAPING is false")
        return PublicNtesAdapter(settings.PUBLIC_NTES_URL)
    if adapter_name in {"simulated", "demo", "fixture"}:
        return SimulatedFeedAdapter(settings.RAILETA_TRAIN_NUMBERS, settings.RAILETA_COLLECTOR_INTERVAL_SECONDS)
    raise ValueError(f"Unknown RAILETA_DATA_ADAPTER: {adapter_name}")


def _simulated_snapshots(events: Iterable[CanonicalEvent]) -> List[Dict[str, Any]]:
    rows = list(events)
    train_numbers = sorted({event.train_number for event in rows if event.train_number})
    snapshots = []
    for train_number in train_numbers:
        latest = next(event for event in reversed(rows) if event.train_number == train_number and event.event_type == "rtis_position")
        snapshots.append({
            "source": "SIMULATED_CRIS",
            "endpoint": "http://localhost/internal/simulated-cris",
            "http_status": 200,
            "parser_version": "simulated-cris-v1",
            "payload": {
                "adapter": "SimulatedFeedAdapter",
                "train_number": train_number,
                "run_id": latest.payload.get("run_id"),
                "status": {"position_mode": "station_event", "gps_unable": True, "title": "Time-compressed synthetic journey; not live railway data"},
                "event_count": sum(1 for event in rows if event.train_number == train_number),
                "event_types": sorted({event.event_type for event in rows if event.train_number == train_number}),
                "route": [
                    {"sequence": index + 1, "station_code": stop["station_code"], "station_name": stop["station_name"], "stop": True, "lat": stop["lat"], "lng": stop["lng"]}
                    for index, stop in enumerate(SIMULATED_ROUTE)
                ],
            },
        })
    return snapshots


def _structured_snapshot(adapter: DataSourceAdapter, events: Iterable[CanonicalEvent]) -> Dict[str, Any]:
    rows = list(events)
    source = getattr(adapter, "source", "CRIS_REST")
    return {
        "source": source,
        "endpoint": getattr(adapter, "url", "http://localhost/internal/events"),
        "http_status": 200,
        "parser_version": "structured-events-v1",
        "payload": {"adapter": adapter.__class__.__name__, "event_count": len(rows), "event_types": sorted({event.event_type for event in rows})},
    }


def collect_public_batch():
    """Poll the configured structured train adapter and weather providers."""
    if settings.RAILETA_DATA_ADAPTER == "historical_profiles":
        # Aggregate replay is handled by the ingestion task, not movement or
        # weather adapters. No external provider is contacted in this mode.
        return [], []
    adapter = get_train_adapter()
    events = adapter.poll()
    snapshots: List[Dict[str, Any]] = []
    if isinstance(adapter, PublicNtesAdapter):
        snapshots.extend(adapter.snapshots)
    elif isinstance(adapter, SimulatedFeedAdapter):
        snapshots.extend(_simulated_snapshots(events))
    else:
        # Keep a train-indexed snapshot, otherwise structured feeds disappear
        # from the same roster API that works for the simulated adapter.
        for number in sorted({event.train_number for event in events if event.train_number}):
            rows = [event for event in events if event.train_number == number]
            snapshot = _structured_snapshot(adapter, rows)
            route = next((event.payload["route"] for event in reversed(rows) if isinstance(event.payload.get("route"), list)), [])
            if not route:
                from .models import FeedSnapshot
                previous = FeedSnapshot.objects.filter(source="CRIS_REST", payload__train_number=number, error="").order_by("-fetched_at").first()
                route = (previous.payload or {}).get("route", []) if previous else []
            snapshot["payload"].update(train_number=number, route=route)
            snapshots.append(snapshot)
    coordinates = _pilot_coordinates_from_snapshots(snapshots)
    if not coordinates and isinstance(adapter, SimulatedFeedAdapter):
        coordinates = {row["station_code"]: {"latitude": row["lat"], "longitude": row["lng"], "name": row["station_name"]} for row in SIMULATED_ROUTE}
    weather_events: List[CanonicalEvent] = []
    weather_snapshots: List[Dict[str, Any]] = []
    from .models import FeedSnapshot
    cutoff = datetime.now(dt_timezone.utc) - timedelta(seconds=settings.RAILETA_WEATHER_INTERVAL_SECONDS)
    if FeedSnapshot.objects.filter(source__in=("PUBLIC_IMD", "PUBLIC_WEATHER_MODEL"), fetched_at__gte=cutoff).exists():
        # Weather model freshness is independent of the 30-second train feed.
        # Back off failed attempts too; never turn an outage into a retry flood.
        return events, snapshots
    if settings.IMD_WEATHER_URL:
        imd = ImdWeatherAdapter(settings.IMD_WEATHER_URL)
        weather_events = imd.collect()
        weather_snapshots.extend(imd.snapshots)
    if not weather_events and getattr(settings, "OPEN_METEO_ENABLED", True):
        weather = OpenMeteoWeatherAdapter(settings.OPEN_METEO_URL)
        weather_events = weather.collect(coordinates)
        weather_snapshots.extend(weather.snapshots)
    return events + weather_events, snapshots + weather_snapshots


def _pilot_coordinates_from_snapshots(snapshots: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Build station coordinates from the public route payload, avoiding hard-coded GPS."""
    coordinates: Dict[str, Dict[str, Any]] = {}
    for snapshot in snapshots:
        for stop in (snapshot.get("payload", {}).get("route", []) if isinstance(snapshot, dict) else []):
            code = str(stop.get("station_code", "")).upper()
            if code not in PILOT_STATIONS or code in coordinates:
                continue
            try:
                coordinates[code] = {"latitude": float(stop["lat"]), "longitude": float(stop["lng"]), "name": stop.get("station_name")}
            except (KeyError, TypeError, ValueError):
                continue
    return coordinates


def _compact_snapshot(train_number: str, page_props: Dict[str, Any], route: List[Dict[str, Any]]) -> Dict[str, Any]:
    lts = page_props.get("ltsData", {}) if isinstance(page_props, dict) else {}
    return {
        "train_number": train_number,
        "status": {key: lts.get(key) for key in ("success", "source", "destination", "source_stn_name", "dest_stn_name", "title", "new_message", "next_station_code", "next_station_name", "spent_time", "gps_unable") if key in lts},
        "route": [{key: stop.get(key) for key in ("sequence", "station_code", "station_name", "stop", "status", "std_min", "sta_min", "scheduled_arrival", "scheduled_departure", "scheduledArrival", "scheduledDeparture", "actual_arrival", "actual_departure", "actualArrival", "actualDeparture", "delay_arrival", "delay_departure", "delayArrival", "delayDeparture", "delay_minutes", "platform_number", "distance_from_source", "lat", "lng") if key in stop} for stop in route if isinstance(stop, dict)],
    }
