"""
pymfx.models — Dataclasses representing the structure of a .mfx v1.0 file
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pandas as pd


@dataclass
class Meta:
    id: str
    drone_id: str
    drone_type: str
    pilot_id: str
    date_start: str
    status: str
    application: str
    location: str
    sensors: list[str]
    data_level: str
    license: str
    contact: str

    manufacturer: str | None = None
    date_end: str | None = None
    duration_s: int | None = None
    crs: str = "WGS84"
    altitude_ref: str = "MSL"
    processing_tools: str | None = None
    producer: str | None = None
    producer_version: str | None = None
    source_format: str | None = None
    source_format_detail: str | None = None
    pid: str | None = None          # Persistent identifier (DOI, Handle, ARK, URI)
    keywords: list[str] | None = None  # Scientific keywords

    # Extra fields not defined in the official schema
    extra: dict = field(default_factory=dict)


@dataclass
class SchemaField:
    name: str
    type: str
    constraints: list[str] = field(default_factory=list)


@dataclass
class TrajectoryPoint:
    t: float
    lat: float
    lon: float
    alt_m: float | None = None
    speed_ms: float | None = None
    heading: float | None = None
    roll: float | None = None
    pitch: float | None = None
    extra: dict = field(default_factory=dict)  # additional schema fields


@dataclass
class Trajectory:
    frequency_hz: float | None
    schema_fields: list[SchemaField]
    points: list[TrajectoryPoint]
    checksum: str | None = None  # sha256:<hex>
    raw_lines: list[str] = field(default_factory=list)  # raw data lines for checksum

    # ------------------------------------------------------------------
    # Data-science helpers
    # ------------------------------------------------------------------

    def to_dataframe(self, events: Events | None = None) -> pd.DataFrame:
        """Convert trajectory points to a :class:`pandas.DataFrame`.

        Each trajectory point becomes one row.  All standard fields
        (``t``, ``lat``, ``lon``, ``alt_m``, ``speed_ms``, ``heading``,
        ``roll``, ``pitch``) plus any extra schema fields are included as
        columns.

        If *events* is provided the event table is merged into the
        trajectory frame with a **nearest-time** join, adding columns
        ``event_type``, ``event_severity``, and ``event_detail``
        (``NaN`` for points that have no nearby event).

        Usage::

            df = mfx.trajectory.to_dataframe()
            df_with_events = mfx.trajectory.to_dataframe(events=mfx.events)

        Requires ``pandas``::

            pip install pandas
            # or: pip install "pymfx[ds]"

        Args:
            events: optional :class:`Events` container to merge into the
                result.

        Returns:
            :class:`pandas.DataFrame`
        """
        try:
            import pandas as pd  # noqa: F811
        except ImportError as exc:
            raise ImportError(
                "pandas is required for to_dataframe(). "
                "Install it with: pip install pandas  (or: pip install 'pymfx[ds]')"
            ) from exc

        records: list[dict] = []
        for p in self.points:
            row: dict = {
                "t": p.t,
                "lat": p.lat,
                "lon": p.lon,
                "alt_m": p.alt_m,
                "speed_ms": p.speed_ms,
                "heading": p.heading,
                "roll": p.roll,
                "pitch": p.pitch,
            }
            row.update(p.extra)
            records.append(row)

        df = pd.DataFrame(records)

        if events is not None and events.events:
            ev_records = [
                {
                    "t": e.t,
                    "event_type": e.type,
                    "event_severity": e.severity,
                    "event_detail": e.detail,
                }
                for e in events.events
            ]
            ev_df = pd.DataFrame(ev_records)
            df = pd.merge_asof(
                df.sort_values("t").reset_index(drop=True),
                ev_df.sort_values("t").reset_index(drop=True),
                on="t",
                direction="nearest",
            )

        return df


@dataclass
class Event:
    t: float
    type: str | None = None
    severity: str | None = None
    detail: str | None = None
    extra: dict = field(default_factory=dict)


@dataclass
class Events:
    schema_fields: list[SchemaField]
    events: list[Event]
    checksum: str | None = None
    raw_lines: list[str] = field(default_factory=list)


@dataclass
class Index:
    bbox: tuple[float, float, float, float] | None = None  # lon_min, lat_min, lon_max, lat_max
    anomalies: int | None = None


@dataclass
class Extension:
    name: str  # e.g. "x_weather"
    fields: dict = field(default_factory=dict)


@dataclass
class MfxFile:
    version: str
    encoding: str
    meta: Meta
    trajectory: Trajectory
    events: Events | None = None
    index: Index | None = None
    extensions: list[Extension] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialize this :class:`MfxFile` to a plain Python :class:`dict`.

        All nested dataclasses are recursively converted.  Tuples (e.g.
        ``Index.bbox``) become lists for JSON compatibility.  Use
        :meth:`to_json` to obtain a JSON string directly.

        Returns:
            A plain :class:`dict` suitable for :func:`json.dumps`,
            :mod:`pprint`, or passing to data-processing libraries.
        """
        return asdict(self)

    def to_json(self, indent: int | None = 2) -> str:
        """Serialize this :class:`MfxFile` to a JSON string.

        Equivalent to ``json.dumps(mfx.to_dict(), indent=indent)``.

        Usage::

            print(mfx.to_json())            # pretty-printed
            compact = mfx.to_json(indent=None)  # single line

        Args:
            indent: indentation level passed to :func:`json.dumps`
                (``None`` for compact, ``2`` for pretty).

        Returns:
            A JSON :class:`str`.
        """
        return json.dumps(self.to_dict(), indent=indent)
