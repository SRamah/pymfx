"""
pymfx.stats — Aggregated flight statistics from an MfxFile.

Zero external dependencies (stdlib math only).

Example usage::

    from pymfx.stats import flight_stats

    stats = flight_stats(mfx)
    print(stats)
    print(f"Total distance: {stats.total_distance_m:.1f} m")
    print(f"Max altitude  : {stats.alt_max_m} m")
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import MfxFile

_EARTH_RADIUS_M: float = 6_371_000.0  # mean radius, metres


# ---------------------------------------------------------------------------
# Haversine helper
# ---------------------------------------------------------------------------

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in **metres** between two WGS-84 points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * _EARTH_RADIUS_M * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# FlightStats dataclass
# ---------------------------------------------------------------------------

@dataclass
class FlightStats:
    """Aggregated statistics for a single drone flight.

    All fields that cannot be computed (e.g. altitude not recorded in the
    trajectory schema) are ``None``.
    """

    # --- Time -----------------------------------------------------------------
    duration_s: float | None
    """Effective flight duration in seconds (``t_last − t_first``)."""

    point_count: int
    """Total number of trajectory points."""

    # --- Distance -------------------------------------------------------------
    total_distance_m: float | None
    """Sum of haversine distances between consecutive points, in metres."""

    # --- Altitude -------------------------------------------------------------
    alt_max_m: float | None
    """Maximum altitude recorded, in metres."""

    alt_min_m: float | None
    """Minimum altitude recorded, in metres."""

    alt_mean_m: float | None
    """Mean altitude across all points, in metres."""

    # --- Speed ----------------------------------------------------------------
    speed_max_ms: float | None
    """Maximum recorded speed, in m/s."""

    speed_mean_ms: float | None
    """Mean speed across all points that have a speed value, in m/s."""

    # --- Convenience ----------------------------------------------------------

    @property
    def total_distance_km(self) -> float | None:
        """Total distance in kilometres (``None`` if unavailable)."""
        return self.total_distance_m / 1000.0 if self.total_distance_m is not None else None

    def __str__(self) -> str:  # noqa: D105
        sep = "─" * 42

        def _v(val: float | None, unit: str, decimals: int = 1) -> str:
            return f"{val:.{decimals}f} {unit}" if val is not None else "n/a"

        lines = [
            f"┌{sep}┐",
            "│  Flight Statistics" + " " * (len(sep) - 18) + "│",
            f"├{sep}┤",
            f"│  Points        : {self.point_count:<23}│",
            f"│  Duration      : {_v(self.duration_s, 's'):<23}│",
            f"│  Distance      : {_v(self.total_distance_m, 'm', 2):<23}│",
        ]
        if self.total_distance_km is not None:
            lines.append(f"│  Distance (km) : {self.total_distance_km:<23.3f}│")
        lines += [
            f"├{sep}┤",
            f"│  Alt max       : {_v(self.alt_max_m, 'm'):<23}│",
            f"│  Alt min       : {_v(self.alt_min_m, 'm'):<23}│",
            f"│  Alt mean      : {_v(self.alt_mean_m, 'm'):<23}│",
            f"├{sep}┤",
            f"│  Speed max     : {_v(self.speed_max_ms, 'm/s'):<23}│",
            f"│  Speed mean    : {_v(self.speed_mean_ms, 'm/s'):<23}│",
            f"└{sep}┘",
        ]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# flight_stats()
# ---------------------------------------------------------------------------

def flight_stats(mfx: MfxFile) -> FlightStats:
    """Compute aggregated flight statistics from an :class:`~pymfx.MfxFile`.

    The computation is purely positional — it uses trajectory ``lat`` / ``lon``
    for distance (Haversine formula), ``alt_m`` for altitude stats, ``speed_ms``
    for speed stats, and ``t`` for duration.  Fields not present in the
    trajectory schema return ``None``.

    Args:
        mfx: a parsed :class:`~pymfx.MfxFile` object.

    Returns:
        :class:`FlightStats` with all available metrics filled in.
    """
    pts = mfx.trajectory.points

    if not pts:
        return FlightStats(
            duration_s=None,
            point_count=0,
            total_distance_m=None,
            alt_max_m=None,
            alt_min_m=None,
            alt_mean_m=None,
            speed_max_ms=None,
            speed_mean_ms=None,
        )

    # --- Duration -------------------------------------------------------------
    duration_s: float | None = pts[-1].t - pts[0].t if len(pts) >= 2 else 0.0

    # --- Total distance (Haversine) -------------------------------------------
    total_distance_m: float | None = None
    if len(pts) >= 2:
        total_distance_m = sum(
            _haversine(pts[i].lat, pts[i].lon, pts[i + 1].lat, pts[i + 1].lon)
            for i in range(len(pts) - 1)
        )

    # --- Altitude -------------------------------------------------------------
    alts = [p.alt_m for p in pts if p.alt_m is not None]
    alt_max_m = max(alts) if alts else None
    alt_min_m = min(alts) if alts else None
    alt_mean_m = sum(alts) / len(alts) if alts else None

    # --- Speed ----------------------------------------------------------------
    speeds = [p.speed_ms for p in pts if p.speed_ms is not None]
    speed_max_ms = max(speeds) if speeds else None
    speed_mean_ms = sum(speeds) / len(speeds) if speeds else None

    return FlightStats(
        duration_s=duration_s,
        point_count=len(pts),
        total_distance_m=total_distance_m,
        alt_max_m=alt_max_m,
        alt_min_m=alt_min_m,
        alt_mean_m=alt_mean_m,
        speed_max_ms=speed_max_ms,
        speed_mean_ms=speed_mean_ms,
    )
