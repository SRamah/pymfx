"""
Tests for pymfx.stats (flight_stats) and the data-science helpers
added to pymfx.models (to_dataframe, to_dict, to_json).
"""
from __future__ import annotations

import json
import math

import pytest

import pymfx
from pymfx.models import (
    Event,
    Events,
    Meta,
    MfxFile,
    SchemaField,
    Trajectory,
    TrajectoryPoint,
)
from pymfx.stats import flight_stats

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_mfx() -> MfxFile:
    """Minimal MfxFile with 5 trajectory points, 1 Hz, known geometry."""
    points = [
        TrajectoryPoint(
            t=float(i),
            lat=48.858 + i * 0.001,
            lon=2.295 + i * 0.001,
            alt_m=100.0 + i * 5,
            speed_ms=10.0 + i,
            heading=90.0,
        )
        for i in range(5)
    ]
    schema = [
        SchemaField("t",        "float", ["no_null"]),
        SchemaField("lat",      "float", ["no_null"]),
        SchemaField("lon",      "float", ["no_null"]),
        SchemaField("alt_m",    "float"),
        SchemaField("speed_ms", "float"),
        SchemaField("heading",  "float"),
    ]
    traj = Trajectory(frequency_hz=1.0, schema_fields=schema, points=points)
    meta = Meta(
        id="uuid:00000000-0000-0000-0000-000000000001",
        drone_id="TEST-01", drone_type="quadcopter", pilot_id="pilot01",
        date_start="2025-06-01T10:00:00Z", status="complete",
        application="survey", location="Paris", sensors=["GPS"],
        data_level="raw", license="CC-BY-4.0", contact="test@example.com",
    )
    return MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)


@pytest.fixture()
def mfx_with_events(simple_mfx: MfxFile) -> MfxFile:
    """MfxFile that also has an events section."""
    ev_schema = [
        SchemaField("t",        "float", ["no_null"]),
        SchemaField("type",     "str"),
        SchemaField("severity", "str"),
        SchemaField("detail",   "str"),
    ]
    events = Events(
        schema_fields=ev_schema,
        events=[
            Event(t=1.0, type="takeoff",  severity="info",     detail="Motors armed"),
            Event(t=3.0, type="waypoint", severity="info",     detail="WP 1 reached"),
            Event(t=4.0, type="warning",  severity="warning",  detail="Low battery"),
        ],
    )
    simple_mfx.events = events
    return simple_mfx


@pytest.fixture()
def empty_mfx() -> MfxFile:
    """MfxFile with zero trajectory points."""
    traj = Trajectory(frequency_hz=None, schema_fields=[], points=[])
    meta = Meta(
        id="uuid:00000000-0000-0000-0000-000000000000",
        drone_id="EMPTY", drone_type="unknown", pilot_id="n/a",
        date_start="2025-01-01T00:00:00Z", status="incomplete",
        application="test", location="test", sensors=[],
        data_level="raw", license="MIT", contact="n/a",
    )
    return MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)


# ---------------------------------------------------------------------------
# TestFlightStats - core statistics
# ---------------------------------------------------------------------------

class TestFlightStats:

    def test_point_count(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        assert stats.point_count == 5

    def test_duration(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        # t runs 0.0 → 4.0 → duration = 4.0 s
        assert stats.duration_s == pytest.approx(4.0)

    def test_distance_positive(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        assert stats.total_distance_m is not None
        assert stats.total_distance_m > 0

    def test_distance_km_property(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        assert stats.total_distance_km == pytest.approx(
            stats.total_distance_m / 1000.0, rel=1e-9
        )

    def test_distance_known_value(self):
        """One step of ~111 m per 0.001° latitude at 48.858°."""
        pts = [
            TrajectoryPoint(t=0.0, lat=0.0, lon=0.0),
            TrajectoryPoint(t=1.0, lat=1.0, lon=0.0),
        ]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        stats = flight_stats(mfx)
        # 1° latitude ≈ 111 195 m
        assert stats.total_distance_m == pytest.approx(111_195.0, rel=0.001)

    def test_alt_max(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        # alt_m = 100 + i*5 for i in [0,1,2,3,4] → max = 120
        assert stats.alt_max_m == pytest.approx(120.0)

    def test_alt_min(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        assert stats.alt_min_m == pytest.approx(100.0)

    def test_alt_mean(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        # mean of [100, 105, 110, 115, 120] = 110
        assert stats.alt_mean_m == pytest.approx(110.0)

    def test_speed_max(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        # speed_ms = 10 + i → max = 14
        assert stats.speed_max_ms == pytest.approx(14.0)

    def test_speed_mean(self, simple_mfx):
        stats = flight_stats(simple_mfx)
        # mean of [10, 11, 12, 13, 14] = 12
        assert stats.speed_mean_ms == pytest.approx(12.0)

    def test_no_altitude(self):
        """When alt_m is absent, altitude stats should be None."""
        pts = [
            TrajectoryPoint(t=float(i), lat=float(i), lon=float(i))
            for i in range(3)
        ]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        s = flight_stats(mfx)
        assert s.alt_max_m is None
        assert s.alt_min_m is None
        assert s.alt_mean_m is None

    def test_no_speed(self):
        """When speed_ms is absent, speed stats should be None."""
        pts = [TrajectoryPoint(t=0.0, lat=0.0, lon=0.0)]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        s = flight_stats(mfx)
        assert s.speed_max_ms is None
        assert s.speed_mean_ms is None

    def test_empty_trajectory(self, empty_mfx):
        stats = flight_stats(empty_mfx)
        assert stats.point_count == 0
        assert stats.duration_s is None
        assert stats.total_distance_m is None
        assert stats.alt_max_m is None
        assert stats.speed_max_ms is None

    def test_single_point(self):
        """A single point has duration 0 and no distance."""
        pts = [TrajectoryPoint(t=0.0, lat=48.858, lon=2.295, alt_m=100.0)]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        s = flight_stats(mfx)
        assert s.point_count == 1
        assert s.duration_s == pytest.approx(0.0)
        assert s.total_distance_m is None


# ---------------------------------------------------------------------------
# TestFlightStatsStr - __str__ output
# ---------------------------------------------------------------------------

class TestFlightStatsStr:

    def test_contains_keywords(self, simple_mfx):
        s = str(flight_stats(simple_mfx))
        assert "Distance" in s
        assert "Duration" in s
        assert "Speed" in s
        assert "Alt" in s

    def test_returns_string(self, simple_mfx):
        assert isinstance(str(flight_stats(simple_mfx)), str)

    def test_na_when_none(self, empty_mfx):
        s = str(flight_stats(empty_mfx))
        assert "n/a" in s

    def test_km_line_present(self, simple_mfx):
        s = str(flight_stats(simple_mfx))
        assert "km" in s


# ---------------------------------------------------------------------------
# TestHaversine - internal distance function
# ---------------------------------------------------------------------------

class TestHaversine:
    """Validate the haversine implementation via flight_stats."""

    def test_zero_distance(self):
        pts = [
            TrajectoryPoint(t=0.0, lat=48.858, lon=2.295),
            TrajectoryPoint(t=1.0, lat=48.858, lon=2.295),
        ]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        assert flight_stats(mfx).total_distance_m == pytest.approx(0.0)

    def test_antipodal_points(self):
        """Antipodal points should be exactly π × R ≈ 20 015 km."""
        pts = [
            TrajectoryPoint(t=0.0, lat=0.0,   lon=0.0),
            TrajectoryPoint(t=1.0, lat=0.0,   lon=180.0),
        ]
        traj = Trajectory(frequency_hz=1.0, schema_fields=[], points=pts)
        meta = Meta(
            id="uuid:test", drone_id="X", drone_type="X", pilot_id="X",
            date_start="2025-01-01T00:00:00Z", status="complete",
            application="X", location="X", sensors=[], data_level="raw",
            license="MIT", contact="X",
        )
        mfx = MfxFile(version="1.0", encoding="UTF-8", meta=meta, trajectory=traj)
        expected = math.pi * 6_371_000.0  # half circumference
        assert flight_stats(mfx).total_distance_m == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# TestToDataFrame - Trajectory.to_dataframe()
# ---------------------------------------------------------------------------

class TestToDataFrame:

    def test_shape(self, simple_mfx):
        pytest.importorskip("pandas")
        df = simple_mfx.trajectory.to_dataframe()
        assert df.shape[0] == 5  # 5 points

    def test_required_columns(self, simple_mfx):
        pytest.importorskip("pandas")
        df = simple_mfx.trajectory.to_dataframe()
        for col in ("t", "lat", "lon"):
            assert col in df.columns

    def test_standard_columns(self, simple_mfx):
        pytest.importorskip("pandas")
        df = simple_mfx.trajectory.to_dataframe()
        for col in ("alt_m", "speed_ms", "heading"):
            assert col in df.columns

    def test_lat_lon_values(self, simple_mfx):
        pytest.importorskip("pandas")
        df = simple_mfx.trajectory.to_dataframe()
        assert float(df["lat"].iloc[0]) == pytest.approx(48.858)
        assert float(df["lon"].iloc[0]) == pytest.approx(2.295)

    def test_t_values(self, simple_mfx):
        pytest.importorskip("pandas")
        df = simple_mfx.trajectory.to_dataframe()
        assert list(df["t"]) == pytest.approx([0.0, 1.0, 2.0, 3.0, 4.0])

    def test_events_merge_adds_columns(self, mfx_with_events):
        pytest.importorskip("pandas")
        df = mfx_with_events.trajectory.to_dataframe(events=mfx_with_events.events)
        assert "event_type" in df.columns
        assert "event_severity" in df.columns
        assert "event_detail" in df.columns

    def test_events_merge_row_count_unchanged(self, mfx_with_events):
        """Events merge must NOT add extra rows - one row per trajectory point."""
        pytest.importorskip("pandas")
        df = mfx_with_events.trajectory.to_dataframe(events=mfx_with_events.events)
        assert df.shape[0] == 5

    def test_no_pandas_raises(self, simple_mfx, monkeypatch):
        """ImportError raised with a helpful message when pandas is missing."""
        import builtins
        real_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pandas":
                raise ImportError("No module named 'pandas'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", mock_import)
        with pytest.raises(ImportError, match="pandas"):
            simple_mfx.trajectory.to_dataframe()


# ---------------------------------------------------------------------------
# TestToDict - MfxFile.to_dict()
# ---------------------------------------------------------------------------

class TestToDict:

    def test_returns_dict(self, simple_mfx):
        assert isinstance(simple_mfx.to_dict(), dict)

    def test_top_level_keys(self, simple_mfx):
        d = simple_mfx.to_dict()
        assert "version" in d
        assert "encoding" in d
        assert "meta" in d
        assert "trajectory" in d

    def test_version_value(self, simple_mfx):
        assert simple_mfx.to_dict()["version"] == "1.0"

    def test_meta_drone_id(self, simple_mfx):
        assert simple_mfx.to_dict()["meta"]["drone_id"] == "TEST-01"

    def test_points_count(self, simple_mfx):
        d = simple_mfx.to_dict()
        assert len(d["trajectory"]["points"]) == 5

    def test_first_point_lat(self, simple_mfx):
        pts = simple_mfx.to_dict()["trajectory"]["points"]
        assert pts[0]["lat"] == pytest.approx(48.858)

    def test_nested_dicts_not_dataclasses(self, simple_mfx):
        """All nested objects must be plain dicts/lists, not dataclasses."""
        import dataclasses
        d = simple_mfx.to_dict()
        for pt in d["trajectory"]["points"]:
            assert not dataclasses.is_dataclass(pt)

    def test_sensors_list(self, simple_mfx):
        d = simple_mfx.to_dict()
        assert d["meta"]["sensors"] == ["GPS"]


# ---------------------------------------------------------------------------
# TestToJson - MfxFile.to_json()
# ---------------------------------------------------------------------------

class TestToJson:

    def test_returns_str(self, simple_mfx):
        assert isinstance(simple_mfx.to_json(), str)

    def test_valid_json(self, simple_mfx):
        out = simple_mfx.to_json()
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_version_field(self, simple_mfx):
        data = json.loads(simple_mfx.to_json())
        assert data["version"] == "1.0"

    def test_compact_output(self, simple_mfx):
        out = simple_mfx.to_json(indent=None)
        assert "\n" not in out

    def test_pretty_output(self, simple_mfx):
        out = simple_mfx.to_json(indent=2)
        assert "\n" in out

    def test_round_trip_drone_id(self, simple_mfx):
        data = json.loads(simple_mfx.to_json())
        assert data["meta"]["drone_id"] == "TEST-01"

    def test_round_trip_points(self, simple_mfx):
        data = json.loads(simple_mfx.to_json())
        assert len(data["trajectory"]["points"]) == 5

    def test_public_api(self, simple_mfx):
        """flight_stats and FlightStats must be importable from pymfx directly."""
        assert hasattr(pymfx, "flight_stats")
        assert hasattr(pymfx, "FlightStats")
        stats = pymfx.flight_stats(simple_mfx)
        assert isinstance(stats, pymfx.FlightStats)
