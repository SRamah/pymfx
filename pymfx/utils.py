"""
pymfx.utils - High-level utilities for MfxFile manipulation

Functions
---------
generate_index   Compute an :class:`~pymfx.Index` from trajectory/events data.
merge            Concatenate two flights in temporal order.
diff             Compare two MfxFile objects and return a :class:`DiffResult`.
"""
from __future__ import annotations

import copy
import uuid
from dataclasses import dataclass
from typing import Any

from .models import Event, Events, Index, MfxFile, SchemaField, Trajectory, TrajectoryPoint
from .stats import flight_stats

# ---------------------------------------------------------------------------
# generate_index
# ---------------------------------------------------------------------------

def generate_index(mfx: MfxFile) -> Index:
    """Compute a :class:`~pymfx.Index` from the trajectory and events.

    Calculates:

    * **bbox** - (lon_min, lat_min, lon_max, lat_max) bounding box of all
      trajectory points (``None`` if no valid coordinates).
    * **anomalies** - count of events whose ``severity`` is ``"warning"``
      or ``"critical"`` (0 if there are no events).

    Args:
        mfx: a parsed :class:`~pymfx.MfxFile`.

    Returns:
        :class:`~pymfx.Index` that can be assigned to ``mfx.index``.

    Example::

        mfx.index = pymfx.generate_index(mfx)
        pymfx.write(mfx, "flight_with_index.mfx")
    """
    pts = mfx.trajectory.points

    lons = [p.lon for p in pts if p.lon is not None]
    lats = [p.lat for p in pts if p.lat is not None]

    if lons and lats:
        bbox: tuple[float, float, float, float] | None = (
            round(min(lons), 8),
            round(min(lats), 8),
            round(max(lons), 8),
            round(max(lats), 8),
        )
    else:
        bbox = None

    anomalies = 0
    if mfx.events:
        anomalies = sum(
            1 for e in mfx.events.events
            if e.severity in ("warning", "critical")
        )

    return Index(bbox=bbox, anomalies=anomalies)


# ---------------------------------------------------------------------------
# merge
# ---------------------------------------------------------------------------

def merge(
    mfx1: MfxFile,
    mfx2: MfxFile,
    gap_s: float = 0.0,
) -> MfxFile:
    """Merge two flights into a single :class:`~pymfx.MfxFile`.

    ``mfx2``'s trajectory is appended after ``mfx1``'s with a time offset
    so the concatenated ``t`` axis remains strictly increasing.

    * **Trajectory** - all points of ``mfx1`` followed by all points of
      ``mfx2`` (``t`` values of ``mfx2`` are shifted by
      ``mfx1.last_t + gap_s``).
    * **Schema** - union of both schemas (fields from ``mfx1`` first, new
      fields from ``mfx2`` appended).
    * **Events** - all events from both flights (``mfx2`` events are also
      time-shifted).
    * **Meta** - copied from ``mfx1``; a new UUID is assigned.

    Args:
        mfx1:  base flight (meta is taken from here)
        mfx2:  flight to append
        gap_s: extra gap in seconds inserted between the two flights
               (default 0)

    Returns:
        A new :class:`~pymfx.MfxFile`.

    Example::

        combined = pymfx.merge(leg1, leg2, gap_s=5.0)
        pymfx.write(combined, "combined.mfx")
    """
    # Time offset for mfx2
    t_offset: float = 0.0
    if mfx1.trajectory.points:
        t_offset = mfx1.trajectory.points[-1].t + gap_s

    # --- Trajectory points ---
    pts1 = mfx1.trajectory.points
    pts2 = [
        TrajectoryPoint(
            t=round(p.t + t_offset, 3),
            lat=p.lat,
            lon=p.lon,
            alt_m=p.alt_m,
            speed_ms=p.speed_ms,
            heading=p.heading,
            roll=p.roll,
            pitch=p.pitch,
            extra=dict(p.extra),
        )
        for p in mfx2.trajectory.points
    ]
    all_points = pts1 + pts2

    # --- Schema (union, mfx1 order preserved) ---
    schema1_names = {f.name for f in mfx1.trajectory.schema_fields}
    merged_schema: list[SchemaField] = list(mfx1.trajectory.schema_fields)
    for sf in mfx2.trajectory.schema_fields:
        if sf.name not in schema1_names:
            merged_schema.append(SchemaField(sf.name, sf.type, list(sf.constraints)))

    # --- Events ---
    merged_events: Events | None = None
    if mfx1.events or mfx2.events:
        ev1 = list(mfx1.events.events) if mfx1.events else []
        ev2 = [
            Event(
                t=round(e.t + t_offset, 3),
                type=e.type,
                severity=e.severity,
                detail=e.detail,
                extra=dict(e.extra),
            )
            for e in (mfx2.events.events if mfx2.events else [])
        ]
        ev_schema = (
            mfx1.events.schema_fields
            if mfx1.events
            else (mfx2.events.schema_fields if mfx2.events else [])
        )
        merged_events = Events(schema_fields=ev_schema, events=ev1 + ev2)

    # --- Frequency ---
    freq = mfx1.trajectory.frequency_hz
    if freq is None and len(all_points) >= 2:
        total_t = all_points[-1].t - all_points[0].t
        if total_t > 0:
            freq = round((len(all_points) - 1) / total_t, 2)

    # --- Meta (deep copy from mfx1, new UUID) ---
    merged_meta = copy.deepcopy(mfx1.meta)
    merged_meta.id = f"uuid:{uuid.uuid4()}"

    return MfxFile(
        version="1.0",
        encoding="UTF-8",
        meta=merged_meta,
        trajectory=Trajectory(
            frequency_hz=freq,
            schema_fields=merged_schema,
            points=all_points,
        ),
        events=merged_events,
    )


# ---------------------------------------------------------------------------
# DiffResult dataclass
# ---------------------------------------------------------------------------

@dataclass
class DiffResult:
    """Structured comparison between two :class:`~pymfx.MfxFile` objects.

    Produced by :func:`diff`.  Every field that can be computed is
    populated; fields that are unavailable remain ``None``.
    """

    # --- Meta -----------------------------------------------------------------
    meta_diffs: list[tuple[str, Any, Any]]
    """List of ``(field_name, value_in_mfx1, value_in_mfx2)`` for every
    meta field whose values differ."""

    # --- Trajectory -----------------------------------------------------------
    point_count_1: int
    point_count_2: int
    duration_s_1: float | None
    duration_s_2: float | None
    total_distance_m_1: float | None
    total_distance_m_2: float | None
    frequency_hz_1: float | None
    frequency_hz_2: float | None

    # --- Events ---------------------------------------------------------------
    event_count_1: int
    event_count_2: int

    # --- Convenience ----------------------------------------------------------

    @property
    def has_differences(self) -> bool:
        """``True`` if *any* compared field differs between the two files."""
        return bool(self.meta_diffs) or (
            self.point_count_1 != self.point_count_2
            or self.event_count_1 != self.event_count_2
        )

    def __str__(self) -> str:  # noqa: D105
        sep = "─" * 50
        W = 22  # column width for value pairs

        def _pair(v1: Any, v2: Any, unit: str = "", decimals: int = 1) -> str:
            def _fmt(v: Any) -> str:
                if v is None:
                    return "n/a"
                if isinstance(v, float):
                    return f"{v:.{decimals}f}{(' ' + unit) if unit else ''}"
                return str(v)

            s1, s2 = _fmt(v1), _fmt(v2)
            eq = "=" if s1 == s2 else "≠"
            return f"{s1:<{W}}  {eq}  {s2}"

        lines = [
            f"┌{sep}┐",
            "│  MfxFile diff" + " " * (len(sep) - 13) + "│",
            f"├{sep}┤",
        ]

        # Meta diffs
        if self.meta_diffs:
            lines.append(f"│  Meta differences ({len(self.meta_diffs)} field(s))" +
                         " " * (len(sep) - 27 - len(str(len(self.meta_diffs)))) + "│")
            for fname, v1, v2 in self.meta_diffs:
                tag = f"  ≠ {fname:<16}: {str(v1)[:18]:<18} → {str(v2)[:18]}"
                lines.append(f"│{tag:<{len(sep)}}│")
        else:
            lines.append("│  Meta             : identical" +
                         " " * (len(sep) - 29) + "│")

        lines.append(f"├{sep}┤")

        # Trajectory
        lines.append("│  Trajectory" + " " * (len(sep) - 11) + "│")
        lines.append(f"│    Points   : {_pair(self.point_count_1, self.point_count_2):<{len(sep)-15}}│")
        lines.append(f"│    Duration : {_pair(self.duration_s_1, self.duration_s_2, 's'):<{len(sep)-15}}│")
        lines.append(f"│    Distance : {_pair(self.total_distance_m_1, self.total_distance_m_2, 'm', 1):<{len(sep)-15}}│")
        lines.append(f"│    Freq Hz  : {_pair(self.frequency_hz_1, self.frequency_hz_2, 'Hz', 2):<{len(sep)-15}}│")

        lines.append(f"├{sep}┤")

        # Events
        lines.append("│  Events" + " " * (len(sep) - 7) + "│")
        lines.append(f"│    Count    : {_pair(self.event_count_1, self.event_count_2):<{len(sep)-15}}│")

        lines.append(f"└{sep}┘")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# diff
# ---------------------------------------------------------------------------

_META_COMPARE_FIELDS = (
    "drone_id", "drone_type", "pilot_id", "date_start", "date_end",
    "status", "application", "location", "license",
)


def diff(mfx1: MfxFile, mfx2: MfxFile) -> DiffResult:
    """Compare two :class:`~pymfx.MfxFile` objects.

    Compares:

    * **Meta** - selected human-relevant fields (drone_id, pilot_id, …)
    * **Trajectory** - point count, duration, total distance, frequency
    * **Events** - event count

    Args:
        mfx1: first flight
        mfx2: second flight

    Returns:
        :class:`DiffResult`

    Example::

        result = pymfx.diff(ref_flight, new_flight)
        print(result)
        if result.has_differences:
            print("Flights differ!")
    """
    # --- Meta diffs ---
    meta_diffs: list[tuple[str, Any, Any]] = []
    for fname in _META_COMPARE_FIELDS:
        v1 = getattr(mfx1.meta, fname, None)
        v2 = getattr(mfx2.meta, fname, None)
        if v1 != v2:
            meta_diffs.append((fname, v1, v2))

    # --- Trajectory stats ---
    s1 = flight_stats(mfx1)
    s2 = flight_stats(mfx2)

    # --- Events ---
    ev1 = len(mfx1.events.events) if mfx1.events else 0
    ev2 = len(mfx2.events.events) if mfx2.events else 0

    return DiffResult(
        meta_diffs=meta_diffs,
        point_count_1=s1.point_count,
        point_count_2=s2.point_count,
        duration_s_1=s1.duration_s,
        duration_s_2=s2.duration_s,
        total_distance_m_1=s1.total_distance_m,
        total_distance_m_2=s2.total_distance_m,
        frequency_hz_1=mfx1.trajectory.frequency_hz,
        frequency_hz_2=mfx2.trajectory.frequency_hz,
        event_count_1=ev1,
        event_count_2=ev2,
    )
