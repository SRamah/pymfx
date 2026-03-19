"""
pymfx.viz.trajectory_3d - 3-D trajectory visualization using matplotlib

Renders the flight path in three dimensions: longitude (X), latitude (Y)
and altitude (Z).  Optionally, each segment can be coloured by speed.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import MfxFile

if TYPE_CHECKING:
    from matplotlib.figure import Figure


def flight_3d(
    mfx: MfxFile,
    color_by: str | None = None,
    figsize: tuple[float, float] = (12, 7),
    dpi: int = 120,
    show_events: bool = True,
    azim: float = -60.0,
    elev: float = 25.0,
) -> Figure:
    """
    Render a 3-D trajectory plot (longitude / latitude / altitude).

    Args:
        mfx:         parsed :class:`~pymfx.MfxFile`
        color_by:    ``"speed"`` to colour each segment by speed value
                     (green = slow → red = fast); ``None`` for a uniform
                     blue line
        figsize:     figure size in inches ``(width, height)``
        dpi:         figure resolution
        show_events: mark events as orange triangles
        azim:        azimuth angle for the 3-D view (degrees)
        elev:        elevation angle for the 3-D view (degrees)

    Returns:
        :class:`matplotlib.figure.Figure`

    Example::

        fig = pymfx.viz.flight_3d(mfx)
        fig.savefig("3d.png", dpi=150)

        # colour by speed
        fig = pymfx.viz.flight_3d(mfx, color_by="speed")

    Raises:
        ValueError: if there are no trajectory points or no altitude data.
        ImportError: if matplotlib is not installed.
    """
    try:
        import matplotlib.pyplot as plt
        from mpl_toolkits.mplot3d import Axes3D  # noqa: F401 - registers projection
    except ImportError as exc:
        raise ImportError(
            "matplotlib is required for 3-D trajectory plots.\n"
            "Install it with: pip install pymfx[viz]  or  pip install matplotlib"
        ) from exc

    points = mfx.trajectory.points
    if not points:
        raise ValueError("No trajectory points to display.")

    alts = [p.alt_m for p in points]
    if all(a is None for a in alts):
        raise ValueError(
            "No altitude data (alt_m) found - flight_3d() requires altitude values."
        )

    lons = [p.lon for p in points]
    lats = [p.lat for p in points]
    alts_f = [a if a is not None else 0.0 for a in alts]

    plt.close("all")
    fig = plt.figure(figsize=figsize, dpi=dpi)
    ax = fig.add_subplot(111, projection="3d")

    # --- Trajectory line ---
    if color_by == "speed":
        speeds_raw = [p.speed_ms for p in points]
        valid_spd = [s for s in speeds_raw if s is not None]

        if valid_spd:
            import matplotlib
            import matplotlib.colors as mcolors

            cmap = matplotlib.colormaps["RdYlGn_r"]
            norm = mcolors.Normalize(vmin=min(valid_spd), vmax=max(valid_spd))
            speeds_f = [s if s is not None else min(valid_spd) for s in speeds_raw]

            for i in range(len(points) - 1):
                seg_color = cmap(norm(speeds_f[i]))
                ax.plot(
                    [lons[i], lons[i + 1]],
                    [lats[i], lats[i + 1]],
                    [alts_f[i], alts_f[i + 1]],
                    color=seg_color,
                    linewidth=1.8,
                )

            # Colour-bar
            sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
            sm.set_array([])
            fig.colorbar(sm, ax=ax, label="Speed (m/s)", shrink=0.45, pad=0.1)
        else:
            # Fall back to uniform colour when no speed data
            ax.plot(lons, lats, alts_f, color="#1a73e8", linewidth=1.8)
    else:
        ax.plot(lons, lats, alts_f, color="#1a73e8", linewidth=1.8)

    # --- Start / end scatter ---
    ax.scatter(
        [lons[0]], [lats[0]], [alts_f[0]],
        c="green", s=80, zorder=6, label="Start",
    )
    ax.scatter(
        [lons[-1]], [lats[-1]], [alts_f[-1]],
        c="red", s=80, zorder=6, label="End",
    )

    # --- Event markers ---
    if show_events and mfx.events:
        ev_lons, ev_lats, ev_alts = [], [], []
        for e in mfx.events.events:
            closest = min(points, key=lambda p: abs(p.t - e.t))
            ev_lons.append(closest.lon)
            ev_lats.append(closest.lat)
            ev_alts.append(closest.alt_m if closest.alt_m is not None else 0.0)
        if ev_lons:
            ax.scatter(
                ev_lons, ev_lats, ev_alts,
                c="orange", s=60, marker="^", zorder=6, label="Event",
            )

    # --- Labels & style ---
    ax.set_xlabel("Longitude", fontsize=9, labelpad=8)
    ax.set_ylabel("Latitude", fontsize=9, labelpad=8)
    ax.set_zlabel("Altitude (m)", fontsize=9, labelpad=8)  # type: ignore[attr-defined]
    ax.set_title(
        f"3-D Trajectory - {mfx.meta.drone_id}  ·  {mfx.meta.location}",
        fontsize=11,
        fontweight="bold",
        pad=12,
    )
    ax.view_init(elev=elev, azim=azim)
    ax.legend(fontsize=8, loc="upper left")

    # Annotate point count & duration
    duration = points[-1].t - points[0].t if len(points) >= 2 else 0.0
    fig.text(
        0.01, 0.01,
        f"{len(points)} points  ·  {duration:.1f}s  ·  {mfx.trajectory.frequency_hz or '?'} Hz",
        fontsize=7,
        color="#888",
    )

    fig.tight_layout()
    return fig
