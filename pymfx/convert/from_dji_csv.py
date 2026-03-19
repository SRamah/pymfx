"""
pymfx.convert.from_dji_csv - Import DJI flight CSV exports to MfxFile

Supports two common dialects:
- AirData UAV export  (column: datetime(utc), altitude(feet), speed(mph), ...)
- DJI Fly app export  (column: time(millisecond), altitude(feet), ...)

Unit conversions applied automatically:
- altitude : feet -> metres  (* 0.3048)
- speed    : mph  -> m/s     (* 0.44704)
- speed    : knots -> m/s    (* 0.514444)

Zero external dependencies (stdlib csv only).
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..models import (
    Event,
    Events,
    Meta,
    MfxFile,
    SchemaField,
    Trajectory,
    TrajectoryPoint,
)

_FEET_TO_M: float = 0.3048
_MPH_TO_MS: float = 0.44704
_KNOTS_TO_MS: float = 0.514444


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_datetime(s: str) -> datetime | None:
    """Parse a DJI datetime string to a UTC-aware datetime."""
    s = s.strip().rstrip("Z")
    for fmt in (
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _safe_float(val: str) -> float | None:
    """Parse a float, returning None for empty/null-like values."""
    v = val.strip() if val else ""
    if v in ("", "-", "N/A", "None", "nan", "NaN"):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _safe_bool(val: str) -> bool:
    """Parse a boolean-like CSV value."""
    return val.strip().lower() in ("true", "1", "yes")


def _detect_dialect(headers: list[str]) -> str:
    """Detect the DJI CSV dialect from column headers."""
    h = {c.lower().strip() for c in headers}
    if "time(millisecond)" in h:
        return "dji_fly"
    if "datetime(utc)" in h:
        return "airdata"
    return "unknown"


def _col_map(headers: list[str]) -> dict[str, str]:
    """Build a lowercased column name -> original header map."""
    return {h.lower().strip(): h for h in headers}


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def from_dji_csv(source: str | Path) -> MfxFile:
    """
    Import a DJI flight CSV export and convert it to MfxFile.

    Supports AirData UAV exports and DJI Fly app direct CSV exports.
    Unit conversions are applied automatically (feet to metres, mph to m/s).

    After import, fill in the required meta fields that DJI does not provide:
    ``pilot_id``, ``location``, ``license``, ``contact``, ``application``.

    Args:
        source: path to a .csv file (str or Path), or raw CSV string.

    Returns:
        MfxFile with ``meta.manufacturer="DJI"`` and ``meta.source_format="dji_csv"``.

    Example::

        mfx = from_dji_csv("DJIFlightRecord_2025-01-15.csv")
        mfx.meta.pilot_id = "pilot:john"
        mfx.meta.location = "Paris, FR"
        pymfx.write(mfx, "flight.mfx")
    """
    # --- Read source ---
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8-sig")  # handle BOM
    elif isinstance(source, str) and "\n" not in source and Path(source).exists():
        text = Path(source).read_text(encoding="utf-8-sig")
    else:
        text = source

    reader = csv.DictReader(io.StringIO(text))
    headers = list(reader.fieldnames or [])
    dialect = _detect_dialect(headers)
    col = _col_map(headers)

    points: list[TrajectoryPoint] = []
    raw_lines: list[str] = []
    events: list[Event] = []

    t0_dt: datetime | None = None
    prev_flycstate: str | None = None
    prev_video: bool = False

    for row_idx, row in enumerate(reader):

        # --- Compute t (seconds from start) ---
        t: float
        if "time(millisecond)" in col:
            ms = _safe_float(row.get(col["time(millisecond)"], ""))
            t = round(ms / 1000.0, 3) if ms is not None else float(row_idx)
        elif "datetime(utc)" in col:
            raw_dt = row.get(col["datetime(utc)"], "").strip()
            pt_dt = _parse_datetime(raw_dt) if raw_dt else None
            if pt_dt is not None:
                if t0_dt is None:
                    t0_dt = pt_dt
                t = round((pt_dt - t0_dt).total_seconds(), 3)
            else:
                t = float(row_idx)
        else:
            t = float(row_idx)

        # --- Coordinates ---
        lat = _safe_float(row.get(col.get("latitude", "___"), ""))
        lon = _safe_float(row.get(col.get("longitude", "___"), ""))
        if lat is None or lon is None:
            continue  # skip rows with no GPS fix

        # --- Altitude (feet -> metres) ---
        alt_m: float | None = None
        for alt_key in ("altitude(feet)", "height_above_takeoff(feet)", "rel_alt(feet)"):
            if alt_key in col:
                raw_alt = _safe_float(row.get(col[alt_key], ""))
                if raw_alt is not None:
                    alt_m = round(raw_alt * _FEET_TO_M, 3)
                    break
        if alt_m is None:
            for alt_key_m in ("altitude(m)", "altitude(meters)", "height_above_takeoff(m)"):
                if alt_key_m in col:
                    alt_m = _safe_float(row.get(col[alt_key_m], ""))
                    break

        # --- Speed ---
        speed_ms: float | None = None
        if "speed(mph)" in col:
            v = _safe_float(row.get(col["speed(mph)"], ""))
            if v is not None:
                speed_ms = round(v * _MPH_TO_MS, 3)
        elif "speed(m/s)" in col:
            speed_ms = _safe_float(row.get(col["speed(m/s)"], ""))
        elif "speed(knots)" in col:
            v = _safe_float(row.get(col["speed(knots)"], ""))
            if v is not None:
                speed_ms = round(v * _KNOTS_TO_MS, 3)

        # --- Orientation ---
        heading: float | None = None
        for h_key in ("compass_heading(degrees)", "heading(degrees)"):
            if h_key in col:
                heading = _safe_float(row.get(col[h_key], ""))
                break

        pitch: float | None = None
        if "pitch(degrees)" in col:
            pitch = _safe_float(row.get(col["pitch(degrees)"], ""))

        roll: float | None = None
        if "roll(degrees)" in col:
            roll = _safe_float(row.get(col["roll(degrees)"], ""))

        # --- Extra fields preserved as-is ---
        extra: dict = {}
        for xkey, xcol in (
            ("battery_percent",  "battery_percent"),
            ("satellites",       "satellites"),
            ("voltage_v",        "voltage(v)"),
            ("gimbal_pitch",     "gimbal_pitch(degrees)"),
            ("gimbal_roll",      "gimbal_roll(degrees)"),
            ("gimbal_heading",   "gimbal_heading(degrees)"),
            ("gpslevel",         "gpslevel"),
        ):
            if xcol in col:
                v2 = _safe_float(row.get(col[xcol], ""))
                if v2 is not None:
                    extra[xkey] = v2

        p = TrajectoryPoint(
            t=t, lat=lat, lon=lon,
            alt_m=alt_m, speed_ms=speed_ms,
            heading=heading, pitch=pitch, roll=roll,
            extra=extra,
        )
        points.append(p)

        # Raw line for checksum (standard fields only)
        vals = [f"{t:.3f}", str(lat), str(lon)]
        if alt_m is not None:
            vals.append(str(alt_m))
        if speed_ms is not None:
            vals.append(str(speed_ms))
        raw_lines.append(" | ".join(vals))

        # --- Events ---

        # Flight state change
        if "flycstate" in col:
            state = row.get(col["flycstate"], "").strip()
            if state and state != prev_flycstate and prev_flycstate is not None:
                sev = "warning" if state.lower() in ("critical", "failsafe", "noinputmode") else "info"
                events.append(Event(
                    t=t, type="state_change", severity=sev,
                    detail=f"{prev_flycstate} -> {state}",
                ))
            prev_flycstate = state

        # Photo trigger
        if "isphoto" in col:
            if _safe_bool(row.get(col["isphoto"], "")):
                events.append(Event(t=t, type="photo", severity="info", detail="photo captured"))

        # Video start / stop
        if "isvideo" in col:
            is_vid = _safe_bool(row.get(col["isvideo"], ""))
            if is_vid and not prev_video:
                events.append(Event(t=t, type="video_start", severity="info",
                                    detail="video recording started"))
            elif not is_vid and prev_video:
                events.append(Event(t=t, type="video_stop", severity="info",
                                    detail="video recording stopped"))
            prev_video = is_vid

        # Pilot message
        if "message" in col:
            msg = row.get(col["message"], "").strip()
            if msg:
                sev = "warning" if any(
                    w in msg.lower()
                    for w in ("warning", "error", "critical", "fail", "lost", "low battery")
                ) else "info"
                events.append(Event(t=t, type="message", severity=sev, detail=msg))

    # --- Auto-detect frequency ---
    frequency_hz: float | None = None
    if len(points) >= 2:
        total_t = points[-1].t - points[0].t
        if total_t > 0:
            frequency_hz = round((len(points) - 1) / total_t, 2)

    # --- date_start ---
    date_start = (
        t0_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if t0_dt is not None
        else "1970-01-01T00:00:00Z"
    )

    # --- Schema fields (only those present in data) ---
    schema_fields: list[SchemaField] = [
        SchemaField("t",   "float", ["no_null"]),
        SchemaField("lat", "float", ["no_null", "range=-90..90"]),
        SchemaField("lon", "float", ["no_null", "range=-180..180"]),
    ]
    if any(p.alt_m is not None for p in points):
        schema_fields.append(SchemaField("alt_m", "float"))
    if any(p.speed_ms is not None for p in points):
        schema_fields.append(SchemaField("speed_ms", "float"))
    if any(p.heading is not None for p in points):
        schema_fields.append(SchemaField("heading", "float", ["range=0..360"]))
    if any(p.pitch is not None for p in points):
        schema_fields.append(SchemaField("pitch", "float"))
    if any(p.roll is not None for p in points):
        schema_fields.append(SchemaField("roll", "float"))

    meta = Meta(
        id=f"uuid:{uuid.uuid4()}",
        drone_id="unknown",
        drone_type="unknown",
        pilot_id="unknown",
        date_start=date_start,
        status="complete",
        application="unknown",
        location="unknown",
        sensors=["camera"],
        data_level="raw",
        license="unknown",
        contact="unknown",
        manufacturer="DJI",
        source_format="dji_csv",
        source_format_detail=f"dialect:{dialect}",
    )

    trajectory = Trajectory(
        frequency_hz=frequency_hz,
        schema_fields=schema_fields,
        points=points,
        raw_lines=raw_lines,
    )

    events_obj: Events | None = None
    if events:
        ev_schema = [
            SchemaField("t",        "float", ["no_null"]),
            SchemaField("type",     "str"),
            SchemaField("severity", "str"),
            SchemaField("detail",   "str"),
        ]
        ev_raw = [
            f"{e.t:.3f} | {e.type or ''} | {e.severity or ''} | {e.detail or ''}"
            for e in events
        ]
        events_obj = Events(schema_fields=ev_schema, events=events, raw_lines=ev_raw)

    return MfxFile(
        version="1.0",
        encoding="UTF-8",
        meta=meta,
        trajectory=trajectory,
        events=events_obj,
    )
