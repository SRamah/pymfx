"""
pymfx.anomaly - Trajectory anomaly detection

Three detectors (all stdlib, no dependencies):

    speed_spike    : speed_ms Z-score exceeds threshold (default 3σ)
    gps_jump       : implied horizontal speed between consecutive points
                     exceeds a physical cap (default 100 m/s)
    altitude_cliff : vertical rate between consecutive points exceeds
                     a physical cap (default 30 m/s)

Usage::

    report = pymfx.detect_anomalies(mfx)
    print(report)                          # summary table
    print(report.count)                    # number of anomalies

    # Inject anomaly events directly into the MfxFile (in-place):
    report = pymfx.detect_anomalies(mfx, inject_events=True)
    pymfx.write(mfx, "fixed.mfx")

    # Custom thresholds:
    report = pymfx.detect_anomalies(
        mfx,
        speed_z_threshold=5.0,
        gps_speed_cap_ms=80.0,
        altitude_rate_cap_ms=20.0,
    )
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from .models import Event, Events, MfxFile, SchemaField

# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class Anomaly:
    """A single detected anomaly."""
    t: float
    kind: str        # "speed_spike" | "gps_jump" | "altitude_cliff"
    severity: str    # "warning" | "critical"
    detail: str
    point_index: int  # index into trajectory.points


@dataclass
class AnomalyReport:
    """Result of :func:`detect_anomalies`."""
    anomalies: list[Anomaly] = field(default_factory=list)

    @property
    def count(self) -> int:
        return len(self.anomalies)

    def __str__(self) -> str:
        if not self.anomalies:
            return "✓ No anomalies detected."
        lines = [f"Anomalies detected: {self.count}", ""]
        col = f"{'t(s)':>9}  {'type':<20}  {'severity':<10}  detail"
        lines.append(col)
        lines.append("─" * 72)
        for a in self.anomalies:
            sev_tag = "⚠" if a.severity == "warning" else "✗"
            lines.append(
                f"{a.t:>9.3f}  {a.kind:<20}  {sev_tag} {a.severity:<8}  {a.detail}"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two WGS-84 coordinates."""
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Return (mean, population std-dev) of a list of floats."""
    n = len(values)
    if n == 0:
        return 0.0, 0.0
    mu = sum(values) / n
    if n < 2:
        return mu, 0.0
    variance = sum((x - mu) ** 2 for x in values) / n
    return mu, math.sqrt(variance)


# ---------------------------------------------------------------------------
# Detectors
# ---------------------------------------------------------------------------

def _detect_speed_spikes(
    pts,
    z_threshold: float,
    found: list[Anomaly],
) -> None:
    speeds = [(i, p) for i, p in enumerate(pts) if p.speed_ms is not None]
    if len(speeds) < 3:
        return
    vals = [p.speed_ms for _, p in speeds]
    mu, sigma = _mean_std(vals)
    if sigma == 0:
        return
    for i, p in speeds:
        z = abs(p.speed_ms - mu) / sigma
        if z > z_threshold:
            sev = "critical" if z > 10 else "warning"
            found.append(Anomaly(
                t=p.t,
                kind="speed_spike",
                severity=sev,
                detail=f"{p.speed_ms:.2f} m/s (z={z:.1f}, mean={mu:.2f}, σ={sigma:.2f})",
                point_index=i,
            ))


def _detect_gps_jumps(
    pts,
    speed_cap_ms: float,
    found: list[Anomaly],
) -> None:
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if None in (p1.lat, p1.lon, p2.lat, p2.lon, p1.t, p2.t):
            continue
        dt = p2.t - p1.t
        if dt <= 0:
            continue
        dist = _haversine(p1.lat, p1.lon, p2.lat, p2.lon)
        implied = dist / dt
        if implied > speed_cap_ms:
            found.append(Anomaly(
                t=p2.t,
                kind="gps_jump",
                severity="critical",
                detail=f"{dist:.0f}m in {dt:.3f}s (implied {implied:.0f} m/s, cap {speed_cap_ms:.0f})",
                point_index=i + 1,
            ))


def _detect_altitude_cliffs(
    pts,
    rate_cap_ms: float,
    found: list[Anomaly],
) -> None:
    for i in range(len(pts) - 1):
        p1, p2 = pts[i], pts[i + 1]
        if None in (p1.alt_m, p2.alt_m, p1.t, p2.t):
            continue
        dt = p2.t - p1.t
        if dt <= 0:
            continue
        rate = abs(p2.alt_m - p1.alt_m) / dt
        if rate > rate_cap_ms:
            delta = p2.alt_m - p1.alt_m
            sev = "critical" if rate > 50 else "warning"
            found.append(Anomaly(
                t=p2.t,
                kind="altitude_cliff",
                severity=sev,
                detail=f"{delta:+.1f}m in {dt:.3f}s ({rate:.1f} m/s vertical, cap {rate_cap_ms:.0f})",
                point_index=i + 1,
            ))


# ---------------------------------------------------------------------------
# Event injection
# ---------------------------------------------------------------------------

_DEFAULT_EVENTS_SCHEMA = [
    SchemaField("t",        "float", ["no_null"]),
    SchemaField("type",     "str",   ["enum=[takeoff,landing,waypoint,anomaly,rtl,abort]"]),
    SchemaField("severity", "str",   ["enum=[info,warning,critical]"]),
    SchemaField("detail",   "str",   []),
]


def _inject_events(mfx: MfxFile, anomalies: list[Anomaly]) -> None:
    """Append anomaly :class:`Event` objects to *mfx.events* in-place.

    Creates the ``[events]`` block if it does not exist yet.  Clears
    ``raw_lines`` so the writer re-serialises from the event objects.
    Updates ``mfx.index.anomalies`` if an index block is present.
    """
    if mfx.events is None:
        mfx.events = Events(
            schema_fields=list(_DEFAULT_EVENTS_SCHEMA),
            events=[],
            raw_lines=[],
        )

    for a in anomalies:
        mfx.events.events.append(Event(
            t=a.t,
            type="anomaly",
            severity=a.severity,
            detail=a.detail,
        ))

    # Force writer to re-serialise (raw_lines would override events list)
    mfx.events.raw_lines = []

    # Keep index.anomalies in sync
    if mfx.index is not None:
        mfx.index.anomalies = sum(
            1 for e in mfx.events.events if e.type == "anomaly"
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_anomalies(
    mfx: MfxFile,
    *,
    speed_z_threshold: float = 3.0,
    gps_speed_cap_ms: float = 100.0,
    altitude_rate_cap_ms: float = 30.0,
    inject_events: bool = False,
) -> AnomalyReport:
    """Detect trajectory anomalies in a :class:`~pymfx.MfxFile`.

    Runs three independent checks on the trajectory points:

    * **speed_spike** — any point whose ``speed_ms`` Z-score exceeds
      *speed_z_threshold* (default 3σ).  Severity is ``critical`` when
      Z > 10, ``warning`` otherwise.
    * **gps_jump** — consecutive-point pair where the implied horizontal
      speed (haversine distance ÷ Δt) exceeds *gps_speed_cap_ms*
      (default 100 m/s — physically impossible for any civilian UAV).
      Always ``critical``.
    * **altitude_cliff** — consecutive-point pair where the vertical rate
      |Δalt| ÷ Δt exceeds *altitude_rate_cap_ms* (default 30 m/s).
      Severity is ``critical`` when rate > 50 m/s, ``warning`` otherwise.

    Args:
        mfx: the flight to analyse.
        speed_z_threshold: Z-score cut-off for speed spike detection.
        gps_speed_cap_ms: horizontal speed cap (m/s) for GPS jump detection.
        altitude_rate_cap_ms: vertical rate cap (m/s) for altitude cliff
            detection.
        inject_events: if ``True``, detected anomalies are appended to
            ``mfx.events`` **in-place** (creates the block if absent) and
            ``mfx.index.anomalies`` is updated.

    Returns:
        :class:`AnomalyReport` with the list of detected anomalies.

    Example::

        report = pymfx.detect_anomalies(mfx)
        print(report)

        # Inject and re-save:
        report = pymfx.detect_anomalies(mfx, inject_events=True)
        pymfx.write(mfx, "repaired.mfx")
    """
    pts = mfx.trajectory.points
    found: list[Anomaly] = []

    if len(pts) < 2:
        return AnomalyReport(anomalies=found)

    _detect_speed_spikes(pts, speed_z_threshold, found)
    _detect_gps_jumps(pts, gps_speed_cap_ms, found)
    _detect_altitude_cliffs(pts, altitude_rate_cap_ms, found)

    # Sort by timestamp for a clean report
    found.sort(key=lambda a: (a.t, a.kind))

    if inject_events and found:
        _inject_events(mfx, found)

    return AnomalyReport(anomalies=found)
