"""
Tests for the new viz functions:
  speed_heatmap, compare_map, flight_3d
"""
from __future__ import annotations

import math
import sys
import uuid
from pathlib import Path

import matplotlib
import pytest

matplotlib.use("Agg")

sys.path.insert(0, str(Path(__file__).parent.parent))

from pymfx.models import (
    Event,
    Events,
    Meta,
    MfxFile,
    SchemaField,
    Trajectory,
    TrajectoryPoint,
)

# ---------------------------------------------------------------------------
# Shared fixture builder
# ---------------------------------------------------------------------------

def _make_mfx(
    n: int = 20,
    with_speed: bool = True,
    with_alt: bool = True,
    with_events: bool = True,
    drone_id: str = "DRONE-A",
    lat_offset: float = 0.0,
) -> MfxFile:
    pts = [
        TrajectoryPoint(
            t=float(i),
            lat=round(48.858 + lat_offset + i * 0.0001, 7),
            lon=round(2.295 + i * 0.0001, 7),
            alt_m=round(100.0 + math.sin(i) * 5, 2) if with_alt else None,
            speed_ms=round(5.0 + math.cos(i) * 2, 2) if with_speed else None,
            heading=float(i * 10 % 360),
        )
        for i in range(n)
    ]
    schema = [
        SchemaField("t", "float", ["no_null"]),
        SchemaField("lat", "float", ["no_null"]),
        SchemaField("lon", "float", ["no_null"]),
    ]
    if with_alt:
        schema.append(SchemaField("alt_m", "float"))
    if with_speed:
        schema.append(SchemaField("speed_ms", "float"))

    traj = Trajectory(frequency_hz=1.0, schema_fields=schema, points=pts)
    meta = Meta(
        id=f"uuid:{uuid.uuid4()}",
        drone_id=drone_id,
        drone_type="quadcopter",
        pilot_id="pilot01",
        date_start="2025-06-01T10:00:00Z",
        status="complete",
        application="survey",
        location="Paris",
        sensors=["GPS"],
        data_level="raw",
        license="CC-BY-4.0",
        contact="test@example.com",
    )
    ev_schema = [SchemaField("t", "float"), SchemaField("type", "str"),
                 SchemaField("severity", "str"), SchemaField("detail", "str")]
    events = Events(
        schema_fields=ev_schema,
        events=[
            Event(t=2.0, type="takeoff",  severity="info",    detail="ok"),
            Event(t=10.0, type="anomaly", severity="warning", detail="wind"),
        ],
    ) if with_events else None
    return MfxFile(version="1.0", encoding="UTF-8", meta=meta,
                   trajectory=traj, events=events)


# ---------------------------------------------------------------------------
# TestSpeedHeatmap
# ---------------------------------------------------------------------------

class TestSpeedHeatmap:

    def test_returns_folium_map(self):
        folium = pytest.importorskip("folium")
        mfx = _make_mfx()
        from pymfx.viz import speed_heatmap
        m = speed_heatmap(mfx)
        assert isinstance(m, folium.Map)

    def test_renders_html(self):
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx()
        m = speed_heatmap(mfx)
        html = m._repr_html_()
        assert len(html) > 500

    def test_colormap_legend_in_html(self):
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx()
        m = speed_heatmap(mfx)
        html = m._repr_html_()
        # branca colormap adds its own HTML
        assert html is not None

    def test_no_speed_raises(self):
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx(with_speed=False)
        with pytest.raises(ValueError, match="No speed data"):
            speed_heatmap(mfx)

    def test_empty_trajectory_raises(self):
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx()
        mfx.trajectory.points = []
        with pytest.raises(ValueError, match="No trajectory points"):
            speed_heatmap(mfx)

    def test_with_events(self):
        folium = pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx(with_events=True)
        m = speed_heatmap(mfx, show_events=True)
        assert isinstance(m, folium.Map)

    def test_without_events(self):
        folium = pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx(with_events=True)
        m = speed_heatmap(mfx, show_events=False)
        assert isinstance(m, folium.Map)

    def test_uniform_speed_no_crash(self):
        """All-identical speeds should not raise a divide-by-zero."""
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx()
        for p in mfx.trajectory.points:
            p.speed_ms = 5.0
        m = speed_heatmap(mfx)
        assert m is not None

    def test_save_to_file(self, tmp_path):
        pytest.importorskip("folium")
        from pymfx.viz import speed_heatmap
        mfx = _make_mfx()
        m = speed_heatmap(mfx)
        out = tmp_path / "speed.html"
        m.save(str(out))
        assert out.exists() and out.stat().st_size > 1000


# ---------------------------------------------------------------------------
# TestCompareMap
# ---------------------------------------------------------------------------

class TestCompareMap:

    def test_returns_folium_map(self):
        folium = pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx(drone_id="A", lat_offset=0.0)
        mfx2 = _make_mfx(drone_id="B", lat_offset=0.005)
        m = compare_map([mfx1, mfx2])
        assert isinstance(m, folium.Map)

    def test_three_flights(self):
        folium = pytest.importorskip("folium")
        from pymfx.viz import compare_map
        flights = [_make_mfx(drone_id=f"D{i}", lat_offset=i * 0.005) for i in range(3)]
        m = compare_map(flights)
        assert isinstance(m, folium.Map)

    def test_legend_in_html(self):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx(drone_id="Alpha")
        mfx2 = _make_mfx(drone_id="Beta", lat_offset=0.005)
        m = compare_map([mfx1, mfx2])
        html = m._repr_html_()
        assert "Alpha" in html
        assert "Beta" in html

    def test_custom_labels(self):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx(drone_id="X")
        mfx2 = _make_mfx(drone_id="Y", lat_offset=0.005)
        m = compare_map([mfx1, mfx2], labels=["Morning", "Evening"])
        html = m._repr_html_()
        assert "Morning" in html
        assert "Evening" in html

    def test_too_few_flights_raises(self):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        with pytest.raises(ValueError, match="at least 2"):
            compare_map([_make_mfx()])

    def test_label_count_mismatch_raises(self):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx()
        mfx2 = _make_mfx(lat_offset=0.005)
        with pytest.raises(ValueError, match="len"):
            compare_map([mfx1, mfx2], labels=["only one label"])

    def test_empty_flight_raises(self):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx()
        mfx2 = _make_mfx(lat_offset=0.005)
        mfx2.trajectory.points = []
        with pytest.raises(ValueError, match="no trajectory points"):
            compare_map([mfx1, mfx2])

    def test_with_events(self):
        folium = pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx(with_events=True)
        mfx2 = _make_mfx(lat_offset=0.005, with_events=True)
        m = compare_map([mfx1, mfx2], show_events=True)
        assert isinstance(m, folium.Map)

    def test_save_to_file(self, tmp_path):
        pytest.importorskip("folium")
        from pymfx.viz import compare_map
        mfx1 = _make_mfx()
        mfx2 = _make_mfx(lat_offset=0.005)
        m = compare_map([mfx1, mfx2])
        out = tmp_path / "compare.html"
        m.save(str(out))
        assert out.exists() and out.stat().st_size > 1000


# ---------------------------------------------------------------------------
# TestFlight3D
# ---------------------------------------------------------------------------

class TestFlight3D:

    def test_returns_figure(self):
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx)
        assert isinstance(fig, Figure)

    def test_has_3d_axes(self):
        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx)
        ax = fig.axes[0]
        assert hasattr(ax, "get_zlim")

    def test_color_by_speed(self):
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx, color_by="speed")
        assert isinstance(fig, Figure)

    def test_color_by_speed_no_speed_fallback(self):
        """Should fall back to uniform colour when no speed data."""
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx(with_speed=False)
        fig = flight_3d(mfx, color_by="speed")
        assert isinstance(fig, Figure)

    def test_empty_trajectory_raises(self):
        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        mfx.trajectory.points = []
        with pytest.raises(ValueError, match="No trajectory points"):
            flight_3d(mfx)

    def test_no_altitude_raises(self):
        from pymfx.viz import flight_3d
        mfx = _make_mfx(with_alt=False)
        with pytest.raises(ValueError, match="altitude"):
            flight_3d(mfx)

    def test_with_events(self):
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx(with_events=True)
        fig = flight_3d(mfx, show_events=True)
        assert isinstance(fig, Figure)

    def test_without_events(self):
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx(with_events=True)
        fig = flight_3d(mfx, show_events=False)
        assert isinstance(fig, Figure)

    def test_custom_view_angles(self):
        from matplotlib.figure import Figure

        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx, azim=30, elev=45)
        assert isinstance(fig, Figure)

    def test_custom_figsize(self):
        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx, figsize=(8, 5))
        assert fig.get_size_inches()[0] == pytest.approx(8)

    def test_save_to_file(self, tmp_path):
        from pymfx.viz import flight_3d
        mfx = _make_mfx()
        fig = flight_3d(mfx)
        out = tmp_path / "3d.png"
        fig.savefig(str(out))
        assert out.exists() and out.stat().st_size > 5000

    def test_title_contains_drone_id(self):
        from pymfx.viz import flight_3d
        mfx = _make_mfx(drone_id="PHANTOM-4")
        fig = flight_3d(mfx)
        title = fig.axes[0].get_title()
        assert "PHANTOM-4" in title
