"""
pymfx.viz.map — Interactive trajectory maps using folium

Functions
---------
trajectory_map   Standard GPS trace, green→red gradient per point.
speed_heatmap    Trajectory segments coloured by speed (green=slow → red=fast).
compare_map      Two or more flights overlaid on the same map.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..models import MfxFile

if TYPE_CHECKING:
    import folium

# Severity colors for event markers
_SEVERITY_COLOR = {
    "info":     "blue",
    "warning":  "orange",
    "critical": "red",
}

# Event type icons (Font Awesome subset supported by folium)
_EVENT_ICON = {
    "takeoff":  "plane",
    "landing":  "plane",
    "waypoint": "map-marker",
    "anomaly":  "exclamation-triangle",
    "rtl":      "undo",
    "abort":    "stop",
}

# Palette for compare_map — up to 8 distinct flights
_COMPARE_PALETTE = [
    "#1a73e8",  # Google blue
    "#e8341a",  # red
    "#0d9e3e",  # green
    "#f0a500",  # amber
    "#9c27b0",  # purple
    "#00acc1",  # cyan
    "#ff7043",  # deep orange
    "#78909c",  # blue-grey
]


def _gradient_color(i: int, total: int) -> str:
    """Return a hex color interpolated from green → yellow → red."""
    ratio = i / max(total - 1, 1)
    if ratio < 0.5:
        r = int(255 * ratio * 2)
        g = 200
    else:
        r = 200
        g = int(200 * (1 - (ratio - 0.5) * 2))
    return f"#{r:02x}{g:02x}40"


def _require_folium():
    try:
        import folium
        return folium
    except ImportError as exc:
        raise ImportError(
            "folium is required for interactive maps.\n"
            "Install it with: pip install pymfx[viz]  or  pip install folium"
        ) from exc


def _add_event_markers(m, mfx: MfxFile, points) -> None:  # type: ignore[no-untyped-def]
    """Add event markers to a folium Map (shared helper)."""
    import folium  # already verified available by caller
    if not mfx.events:
        return
    for e in mfx.events.events:
        if e.t is None:
            continue
        closest = min(
            (p for p in points if p.lat is not None and p.t is not None),
            key=lambda p: abs(p.t - e.t),  # type: ignore[operator]
            default=None,
        )
        if closest is None:
            continue
        color = _SEVERITY_COLOR.get(e.severity or "info", "blue")
        icon_name = _EVENT_ICON.get(e.type or "", "info-circle")
        popup_html = (
            f"<b>{e.type}</b><br>"
            f"t = {e.t:.3f}s<br>"
            f"severity = {e.severity}<br>"
            f"detail = {e.detail}"
        )
        folium.Marker(
            location=(closest.lat, closest.lon),
            popup=folium.Popup(popup_html, max_width=200),
            tooltip=f"{e.type} @ t={e.t:.1f}s",
            icon=folium.Icon(color=color, icon=icon_name, prefix="fa"),
        ).add_to(m)


# ---------------------------------------------------------------------------
# trajectory_map — existing function (unchanged API)
# ---------------------------------------------------------------------------

def trajectory_map(
    mfx: MfxFile,
    tile: str = "OpenStreetMap",
    line_weight: int = 3,
    show_points: bool = True,
    show_events: bool = True,
) -> folium.Map:
    """
    Build an interactive Leaflet map of the flight trajectory.

    Points are colour-graded green → yellow → red (start → end).

    Args:
        mfx:          parsed MfxFile
        tile:         map tile provider ("OpenStreetMap", "CartoDB positron", ...)
        line_weight:  width of the trajectory line in pixels
        show_points:  draw a small circle at each trajectory point
        show_events:  draw event markers with popups

    Returns:
        folium.Map — call ``.save("map.html")`` or display in Jupyter.
    """
    folium = _require_folium()

    points = mfx.trajectory.points
    if not points:
        raise ValueError("No trajectory points to display.")

    coords = [(p.lat, p.lon) for p in points if p.lat is not None and p.lon is not None]
    if not coords:
        raise ValueError("Trajectory points have no valid lat/lon values.")

    center_lat = sum(c[0] for c in coords) / len(coords)
    center_lon = sum(c[1] for c in coords) / len(coords)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles=tile)

    folium.PolyLine(
        locations=coords,
        color="#1a73e8",
        weight=line_weight,
        opacity=0.85,
        tooltip=f"{mfx.meta.drone_id} — {len(coords)} points",
    ).add_to(m)

    folium.Marker(
        location=coords[0],
        tooltip="Start — t=0s",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        location=coords[-1],
        tooltip=f"End — t={points[-1].t:.1f}s",
        icon=folium.Icon(color="red", icon="stop", prefix="fa"),
    ).add_to(m)

    if show_points:
        for i, p in enumerate(points):
            if p.lat is None or p.lon is None:
                continue
            parts = [f"t = {p.t:.3f}s", f"lat = {p.lat}", f"lon = {p.lon}"]
            if p.alt_m is not None:
                parts.append(f"alt = {p.alt_m}m")
            if p.speed_ms is not None:
                parts.append(f"speed = {p.speed_ms}m/s")
            folium.CircleMarker(
                location=(p.lat, p.lon),
                radius=3,
                color=_gradient_color(i, len(points)),
                fill=True,
                fill_opacity=0.7,
                tooltip="<br>".join(parts),
            ).add_to(m)

    if show_events:
        _add_event_markers(m, mfx, points)

    if mfx.index and mfx.index.bbox:
        lon_min, lat_min, lon_max, lat_max = mfx.index.bbox
        folium.Rectangle(
            bounds=[[lat_min, lon_min], [lat_max, lon_max]],
            color="#555",
            weight=1,
            dash_array="6",
            fill=False,
            tooltip="Bounding box",
        ).add_to(m)

    m.fit_bounds([[min(c[0] for c in coords), min(c[1] for c in coords)],
                  [max(c[0] for c in coords), max(c[1] for c in coords)]])
    return m


# ---------------------------------------------------------------------------
# speed_heatmap — segments coloured by speed
# ---------------------------------------------------------------------------

def speed_heatmap(
    mfx: MfxFile,
    tile: str = "OpenStreetMap",
    line_weight: int = 5,
    show_events: bool = True,
) -> folium.Map:
    """
    Build a speed heatmap: the trajectory is split into individual
    segments, each coloured by the speed measured at its starting point
    (green = slow → yellow → red = fast).

    A colour-scale legend is added to the map.

    Args:
        mfx:          parsed MfxFile
        tile:         map tile provider
        line_weight:  segment line width in pixels
        show_events:  draw event markers with popups

    Returns:
        folium.Map

    Example::

        m = pymfx.viz.speed_heatmap(mfx)
        m.save("speed.html")

    Raises:
        ValueError: if there are no trajectory points or no speed data.
    """
    folium = _require_folium()
    try:
        import branca.colormap as cm
    except ImportError as exc:
        raise ImportError(
            "branca is required for speed_heatmap. "
            "It ships with folium — install with: pip install pymfx[viz]"
        ) from exc

    points = mfx.trajectory.points
    if not points:
        raise ValueError("No trajectory points to display.")

    speeds = [p.speed_ms for p in points if p.speed_ms is not None]
    if not speeds:
        raise ValueError(
            "No speed data in trajectory. "
            "speed_heatmap() requires the 'speed_ms' field to be populated."
        )

    min_spd = min(speeds)
    max_spd = max(speeds)
    # Avoid divide-by-zero when all speeds are identical
    if max_spd == min_spd:
        max_spd = min_spd + 1.0

    colormap = cm.LinearColormap(
        colors=["green", "yellow", "red"],
        vmin=min_spd,
        vmax=max_spd,
        caption=f"Speed (m/s)  [{min_spd:.1f} – {max_spd:.1f}]",
    )

    coords = [(p.lat, p.lon) for p in points if p.lat is not None and p.lon is not None]
    center_lat = sum(c[0] for c in coords) / len(coords)
    center_lon = sum(c[1] for c in coords) / len(coords)

    m = folium.Map(location=[center_lat, center_lon], zoom_start=15, tiles=tile)

    # Draw coloured segments
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i + 1]
        if None in (p1.lat, p1.lon, p2.lat, p2.lon):
            continue
        spd = p1.speed_ms if p1.speed_ms is not None else min_spd
        color = colormap(spd)
        folium.PolyLine(
            locations=[(p1.lat, p1.lon), (p2.lat, p2.lon)],
            color=color,
            weight=line_weight,
            opacity=0.9,
            tooltip=f"t={p1.t:.1f}s  speed={spd:.2f} m/s",
        ).add_to(m)

    colormap.add_to(m)

    # Start / end markers
    folium.Marker(
        location=coords[0],
        tooltip=f"Start — {mfx.meta.drone_id}",
        icon=folium.Icon(color="green", icon="play", prefix="fa"),
    ).add_to(m)
    folium.Marker(
        location=coords[-1],
        tooltip=f"End — t={points[-1].t:.1f}s",
        icon=folium.Icon(color="red", icon="stop", prefix="fa"),
    ).add_to(m)

    if show_events:
        _add_event_markers(m, mfx, points)

    m.fit_bounds([[min(c[0] for c in coords), min(c[1] for c in coords)],
                  [max(c[0] for c in coords), max(c[1] for c in coords)]])
    return m


# ---------------------------------------------------------------------------
# compare_map — multiple flights on the same map
# ---------------------------------------------------------------------------

def compare_map(
    flights: list[MfxFile],
    labels: list[str] | None = None,
    tile: str = "OpenStreetMap",
    line_weight: int = 3,
    show_events: bool = True,
) -> folium.Map:
    """
    Overlay two or more flight trajectories on the same interactive map.

    Each flight receives a distinct colour.  Start and end markers are
    labelled with the flight's drone ID (or a custom *label*).  An HTML
    legend is added to the map.

    Args:
        flights:      list of two or more :class:`~pymfx.MfxFile` objects
        labels:       optional list of display names (same length as
                      *flights*); defaults to each flight's ``drone_id``
        tile:         map tile provider
        line_weight:  trajectory line width in pixels
        show_events:  draw event markers for every flight

    Returns:
        folium.Map

    Example::

        m = pymfx.viz.compare_map([mfx_morning, mfx_afternoon],
                                   labels=["Morning run", "Afternoon run"])
        m.save("compare.html")

    Raises:
        ValueError: if fewer than 2 flights are provided or any flight
                    has no trajectory points.
    """
    folium = _require_folium()

    if len(flights) < 2:
        raise ValueError("compare_map() requires at least 2 flights.")

    if labels is None:
        labels = [mfx.meta.drone_id for mfx in flights]
    if len(labels) != len(flights):
        raise ValueError("len(labels) must equal len(flights).")

    # Collect all valid coords across flights for centering / fitting
    all_coords: list[tuple[float, float]] = []
    for mfx in flights:
        if not mfx.trajectory.points:
            raise ValueError(
                f"Flight '{mfx.meta.drone_id}' has no trajectory points."
            )
        all_coords.extend(
            (p.lat, p.lon)
            for p in mfx.trajectory.points
            if p.lat is not None and p.lon is not None
        )

    center_lat = sum(c[0] for c in all_coords) / len(all_coords)
    center_lon = sum(c[1] for c in all_coords) / len(all_coords)
    m = folium.Map(location=[center_lat, center_lon], zoom_start=14, tiles=tile)

    for idx, (mfx, label) in enumerate(zip(flights, labels)):
        color = _COMPARE_PALETTE[idx % len(_COMPARE_PALETTE)]
        points = mfx.trajectory.points
        coords = [
            (p.lat, p.lon)
            for p in points
            if p.lat is not None and p.lon is not None
        ]
        if not coords:
            continue

        folium.PolyLine(
            locations=coords,
            color=color,
            weight=line_weight,
            opacity=0.85,
            tooltip=f"{label} — {len(coords)} points",
        ).add_to(m)

        # Start / end markers
        folium.Marker(
            location=coords[0],
            tooltip=f"[{label}] Start",
            icon=folium.Icon(color="green", icon="play", prefix="fa"),
        ).add_to(m)
        folium.Marker(
            location=coords[-1],
            tooltip=f"[{label}] End — t={points[-1].t:.1f}s",
            icon=folium.Icon(color="darkred", icon="stop", prefix="fa"),
        ).add_to(m)

        if show_events:
            _add_event_markers(m, mfx, points)

    # --- HTML legend ---
    legend_rows = "".join(
        f'<tr><td style="background:{_COMPARE_PALETTE[i % len(_COMPARE_PALETTE)]}; '
        f'width:16px; height:16px; border-radius:3px"></td>'
        f'<td style="padding-left:6px">{lbl}</td></tr>'
        for i, lbl in enumerate(labels)
    )
    legend_html = f"""
    <div style="position:fixed;bottom:30px;left:30px;z-index:9999;
                background:white;padding:10px 14px;border-radius:8px;
                box-shadow:2px 2px 6px rgba(0,0,0,.25);font-size:13px">
        <b>Flights</b><br>
        <table style="border-collapse:collapse;margin-top:4px">
        {legend_rows}
        </table>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    m.fit_bounds([[min(c[0] for c in all_coords), min(c[1] for c in all_coords)],
                  [max(c[0] for c in all_coords), max(c[1] for c in all_coords)]])
    return m
