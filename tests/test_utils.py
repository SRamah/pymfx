"""
Tests for pymfx.utils — generate_index, merge, diff, DiffResult
"""
from __future__ import annotations

import uuid

import pytest

import pymfx
from pymfx.models import (
    Event,
    Events,
    Index,
    Meta,
    MfxFile,
    SchemaField,
    Trajectory,
    TrajectoryPoint,
)
from pymfx.utils import DiffResult, diff, generate_index, merge

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_mfx(
    n: int = 5,
    drone_id: str = "TEST-01",
    t_offset: float = 0.0,
    with_events: bool = False,
    alt: float = 100.0,
    speed: float = 5.0,
) -> MfxFile:
    pts = [
        TrajectoryPoint(
            t=round(t_offset + float(i), 3),
            lat=48.858 + i * 0.001,
            lon=2.295 + i * 0.001,
            alt_m=alt + i,
            speed_ms=speed,
        )
        for i in range(n)
    ]
    schema = [
        SchemaField("t",        "float", ["no_null"]),
        SchemaField("lat",      "float", ["no_null"]),
        SchemaField("lon",      "float", ["no_null"]),
        SchemaField("alt_m",    "float"),
        SchemaField("speed_ms", "float"),
    ]
    traj = Trajectory(frequency_hz=1.0, schema_fields=schema, points=pts)
    meta = Meta(
        id=f"uuid:{uuid.uuid4()}",
        drone_id=drone_id,
        drone_type="quadcopter",
        pilot_id="pilot01",
        date_start="2024-06-01T10:00:00Z",
        status="complete",
        application="survey",
        location="Paris",
        sensors=["GPS"],
        data_level="raw",
        license="CC-BY-4.0",
        contact="test@example.com",
    )
    ev_schema = [
        SchemaField("t",        "float", ["no_null"]),
        SchemaField("type",     "str"),
        SchemaField("severity", "str"),
        SchemaField("detail",   "str"),
    ]
    events = Events(
        schema_fields=ev_schema,
        events=[
            Event(t=t_offset + 1.0, type="takeoff", severity="info",    detail="ok"),
            Event(t=t_offset + 3.0, type="warning", severity="warning", detail="wind"),
        ],
    ) if with_events else None
    return MfxFile(version="1.0", encoding="UTF-8", meta=meta,
                   trajectory=traj, events=events)


# ---------------------------------------------------------------------------
# TestGenerateIndex
# ---------------------------------------------------------------------------

class TestGenerateIndex:

    def test_returns_index(self):
        mfx = _make_mfx()
        idx = generate_index(mfx)
        assert isinstance(idx, Index)

    def test_bbox_not_none(self):
        mfx = _make_mfx()
        idx = generate_index(mfx)
        assert idx.bbox is not None

    def test_bbox_length(self):
        mfx = _make_mfx()
        idx = generate_index(mfx)
        assert len(idx.bbox) == 4

    def test_bbox_lon_min_lt_max(self):
        mfx = _make_mfx()
        idx = generate_index(mfx)
        lon_min, lat_min, lon_max, lat_max = idx.bbox
        assert lon_min <= lon_max
        assert lat_min <= lat_max

    def test_bbox_contains_all_points(self):
        mfx = _make_mfx(n=10)
        idx = generate_index(mfx)
        lon_min, lat_min, lon_max, lat_max = idx.bbox
        for p in mfx.trajectory.points:
            assert lon_min <= p.lon <= lon_max
            assert lat_min <= p.lat <= lat_max

    def test_anomalies_zero_no_events(self):
        mfx = _make_mfx(with_events=False)
        idx = generate_index(mfx)
        assert idx.anomalies == 0

    def test_anomalies_counts_warnings(self):
        mfx = _make_mfx(with_events=True)  # 1 warning event
        idx = generate_index(mfx)
        assert idx.anomalies == 1

    def test_anomalies_counts_criticals(self):
        mfx = _make_mfx(with_events=True)
        mfx.events.events.append(
            Event(t=4.0, type="abort", severity="critical", detail="motor")
        )
        idx = generate_index(mfx)
        assert idx.anomalies == 2  # 1 warning + 1 critical

    def test_info_events_not_counted(self):
        mfx = _make_mfx(with_events=True)  # has 1 info + 1 warning
        idx = generate_index(mfx)
        assert idx.anomalies == 1  # only the warning counts

    def test_empty_trajectory_bbox_none(self):
        mfx = _make_mfx()
        mfx.trajectory.points = []
        idx = generate_index(mfx)
        assert idx.bbox is None

    def test_public_api(self):
        mfx = _make_mfx()
        idx = pymfx.generate_index(mfx)
        assert isinstance(idx, Index)

    def test_mutate_mfx_index(self):
        """Typical usage: assign result back to mfx.index."""
        mfx = _make_mfx(with_events=True)
        mfx.index = generate_index(mfx)
        assert mfx.index is not None
        assert mfx.index.bbox is not None


# ---------------------------------------------------------------------------
# TestMerge
# ---------------------------------------------------------------------------

class TestMerge:

    def test_returns_mfxfile(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        result = merge(mfx1, mfx2)
        assert isinstance(result, MfxFile)

    def test_point_count(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        result = merge(mfx1, mfx2)
        assert len(result.trajectory.points) == 8

    def test_t_strictly_increasing(self):
        """With gap_s > 0 the full t axis must be strictly increasing."""
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        result = merge(mfx1, mfx2, gap_s=1.0)
        ts = [p.t for p in result.trajectory.points]
        for i in range(len(ts) - 1):
            assert ts[i + 1] > ts[i], f"t not increasing at index {i}: {ts[i]} >= {ts[i+1]}"

    def test_t_offset_applied(self):
        """mfx2 points must start after mfx1's last t."""
        mfx1 = _make_mfx(n=5)   # t: 0 … 4
        mfx2 = _make_mfx(n=3)   # t: 0, 1, 2 → after merge: 4+gap, 5+gap, 6+gap
        result = merge(mfx1, mfx2, gap_s=0.0)
        last_t1 = mfx1.trajectory.points[-1].t
        first_t2_merged = result.trajectory.points[5].t
        assert first_t2_merged >= last_t1

    def test_gap_applied(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        result = merge(mfx1, mfx2, gap_s=10.0)
        last_t1 = mfx1.trajectory.points[-1].t
        first_t2_merged = result.trajectory.points[5].t
        assert first_t2_merged == pytest.approx(last_t1 + 10.0)

    def test_meta_from_mfx1(self):
        mfx1 = _make_mfx(drone_id="ALPHA")
        mfx2 = _make_mfx(drone_id="BETA")
        result = merge(mfx1, mfx2)
        assert result.meta.drone_id == "ALPHA"

    def test_new_uuid_assigned(self):
        mfx1 = _make_mfx()
        mfx2 = _make_mfx()
        result = merge(mfx1, mfx2)
        assert result.meta.id != mfx1.meta.id
        assert result.meta.id != mfx2.meta.id

    def test_events_merged(self):
        mfx1 = _make_mfx(n=5, with_events=True)   # 2 events
        mfx2 = _make_mfx(n=3, with_events=True)   # 2 events
        result = merge(mfx1, mfx2)
        assert result.events is not None
        assert len(result.events.events) == 4

    def test_events_time_shifted(self):
        mfx1 = _make_mfx(n=5, with_events=True)
        mfx2 = _make_mfx(n=3, with_events=True)
        last_t1 = mfx1.trajectory.points[-1].t
        result = merge(mfx1, mfx2)
        # mfx2 events should be time-shifted
        mfx2_ev_ts = [e.t for e in result.events.events[2:]]  # last 2 are from mfx2
        for et in mfx2_ev_ts:
            assert et >= last_t1

    def test_no_events_if_both_empty(self):
        mfx1 = _make_mfx(n=5, with_events=False)
        mfx2 = _make_mfx(n=3, with_events=False)
        result = merge(mfx1, mfx2)
        assert result.events is None

    def test_schema_union(self):
        """Extra fields from mfx2 should appear in merged schema."""
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        mfx2.trajectory.schema_fields.append(SchemaField("custom_field", "float"))
        result = merge(mfx1, mfx2)
        names = [f.name for f in result.trajectory.schema_fields]
        assert "custom_field" in names

    def test_public_api(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=3)
        result = pymfx.merge(mfx1, mfx2)
        assert isinstance(result, MfxFile)


# ---------------------------------------------------------------------------
# TestDiff
# ---------------------------------------------------------------------------

class TestDiff:

    def test_returns_diff_result(self):
        mfx1 = _make_mfx()
        mfx2 = _make_mfx()
        result = diff(mfx1, mfx2)
        assert isinstance(result, DiffResult)

    def test_identical_files_no_meta_diffs(self):
        mfx1 = _make_mfx(drone_id="X")
        mfx2 = _make_mfx(drone_id="X")
        result = diff(mfx1, mfx2)
        assert result.meta_diffs == []

    def test_different_drone_id_detected(self):
        mfx1 = _make_mfx(drone_id="ALPHA")
        mfx2 = _make_mfx(drone_id="BETA")
        result = diff(mfx1, mfx2)
        fields = [d[0] for d in result.meta_diffs]
        assert "drone_id" in fields

    def test_meta_diff_values(self):
        mfx1 = _make_mfx(drone_id="ALPHA")
        mfx2 = _make_mfx(drone_id="BETA")
        result = diff(mfx1, mfx2)
        d = next(d for d in result.meta_diffs if d[0] == "drone_id")
        assert d[1] == "ALPHA"
        assert d[2] == "BETA"

    def test_point_counts(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=8)
        result = diff(mfx1, mfx2)
        assert result.point_count_1 == 5
        assert result.point_count_2 == 8

    def test_duration(self):
        mfx1 = _make_mfx(n=5)   # duration = 4.0 s
        mfx2 = _make_mfx(n=9)   # duration = 8.0 s
        result = diff(mfx1, mfx2)
        assert result.duration_s_1 == pytest.approx(4.0)
        assert result.duration_s_2 == pytest.approx(8.0)

    def test_frequency_hz(self):
        mfx1 = _make_mfx()
        mfx2 = _make_mfx()
        mfx2.trajectory.frequency_hz = 10.0
        result = diff(mfx1, mfx2)
        assert result.frequency_hz_1 == pytest.approx(1.0)
        assert result.frequency_hz_2 == pytest.approx(10.0)

    def test_event_counts(self):
        mfx1 = _make_mfx(with_events=True)    # 2 events
        mfx2 = _make_mfx(with_events=False)   # 0 events
        result = diff(mfx1, mfx2)
        assert result.event_count_1 == 2
        assert result.event_count_2 == 0

    def test_has_differences_true(self):
        mfx1 = _make_mfx(drone_id="A")
        mfx2 = _make_mfx(drone_id="B")
        assert diff(mfx1, mfx2).has_differences is True

    def test_has_differences_false_same_point_count(self):
        mfx1 = _make_mfx(n=5, drone_id="X")
        mfx2 = _make_mfx(n=5, drone_id="X")
        result = diff(mfx1, mfx2)
        assert result.has_differences is False

    def test_has_differences_different_event_count(self):
        mfx1 = _make_mfx(with_events=True)
        mfx2 = _make_mfx(with_events=False)
        assert diff(mfx1, mfx2).has_differences is True

    def test_distance_populated(self):
        mfx1 = _make_mfx(n=5)
        mfx2 = _make_mfx(n=10)
        result = diff(mfx1, mfx2)
        assert result.total_distance_m_1 is not None
        assert result.total_distance_m_2 is not None
        assert result.total_distance_m_2 > result.total_distance_m_1

    def test_public_api(self):
        mfx1 = _make_mfx(drone_id="A")
        mfx2 = _make_mfx(drone_id="B")
        result = pymfx.diff(mfx1, mfx2)
        assert isinstance(result, pymfx.DiffResult)


# ---------------------------------------------------------------------------
# TestDiffStr
# ---------------------------------------------------------------------------

class TestDiffStr:

    def test_returns_string(self):
        result = diff(_make_mfx(), _make_mfx())
        assert isinstance(str(result), str)

    def test_contains_points(self):
        s = str(diff(_make_mfx(n=5), _make_mfx(n=8)))
        assert "Points" in s

    def test_contains_distance(self):
        s = str(diff(_make_mfx(), _make_mfx()))
        assert "Distance" in s

    def test_contains_events(self):
        s = str(diff(_make_mfx(), _make_mfx()))
        assert "Event" in s

    def test_meta_diff_shown(self):
        s = str(diff(_make_mfx(drone_id="ALPHA"), _make_mfx(drone_id="BETA")))
        assert "ALPHA" in s
        assert "BETA" in s
