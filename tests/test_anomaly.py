"""
Tests for pymfx.anomaly — detect_anomalies(), AnomalyReport, Anomaly
"""
import copy

import pytest

from pymfx.anomaly import AnomalyReport, detect_anomalies, _haversine, _mean_std
from pymfx.models import (
    Event, Events, Index, MfxFile, Meta, SchemaField, Trajectory, TrajectoryPoint,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_meta(**kwargs):
    defaults = dict(
        id="uuid:00000000-0000-0000-0000-000000000001",
        drone_id="drone:test", drone_type="multirotor", pilot_id="pilot:test",
        date_start="2025-06-01T00:00:00Z", status="complete",
        application="test", location="Testville",
        sensors=["rgb"], data_level="raw",
        license="CC-BY-4.0", contact="t@t.com",
    )
    defaults.update(kwargs)
    return Meta(**defaults)


def _make_mfx(points: list[TrajectoryPoint], index=None) -> MfxFile:
    schema = [
        SchemaField("t",        "float",   ["no_null"]),
        SchemaField("lat",      "float",   ["no_null"]),
        SchemaField("lon",      "float",   ["no_null"]),
        SchemaField("alt_m",    "float32", []),
        SchemaField("speed_ms", "float32", []),
    ]
    return MfxFile(
        version="1.0",
        encoding="UTF-8",
        meta=_make_meta(),
        trajectory=Trajectory(frequency_hz=1.0, schema_fields=schema, points=points),
        index=index,
    )


def _pt(t, lat, lon, alt=50.0, speed=8.0):
    return TrajectoryPoint(t=t, lat=lat, lon=lon, alt_m=alt, speed_ms=speed)


# A clean 10-point trajectory with no anomalies
CLEAN_PTS = [
    _pt(float(i), 48.8566 + i * 0.0001, 2.3522 + i * 0.0001, 50.0, 8.0)
    for i in range(10)
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_haversine_same_point(self):
        assert _haversine(48.0, 2.0, 48.0, 2.0) == pytest.approx(0.0)

    def test_haversine_known(self):
        # Paris → Lyon ~392 km
        d = _haversine(48.8566, 2.3522, 45.7640, 4.8357)
        assert 390_000 < d < 394_000

    def test_mean_std_uniform(self):
        mu, sigma = _mean_std([5.0, 5.0, 5.0])
        assert mu == pytest.approx(5.0)
        assert sigma == pytest.approx(0.0)

    def test_mean_std_values(self):
        mu, sigma = _mean_std([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
        assert mu == pytest.approx(5.0)
        assert sigma == pytest.approx(2.0)

    def test_mean_std_single(self):
        mu, sigma = _mean_std([3.0])
        assert mu == pytest.approx(3.0)
        assert sigma == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# No anomalies
# ---------------------------------------------------------------------------

class TestNoAnomalies:
    def test_clean_flight_returns_empty(self):
        mfx = _make_mfx(CLEAN_PTS)
        report = detect_anomalies(mfx)
        assert report.count == 0

    def test_clean_flight_str(self):
        mfx = _make_mfx(CLEAN_PTS)
        report = detect_anomalies(mfx)
        assert "No anomalies" in str(report)

    def test_single_point_returns_empty(self):
        mfx = _make_mfx([_pt(0.0, 48.0, 2.0)])
        report = detect_anomalies(mfx)
        assert report.count == 0

    def test_empty_trajectory_returns_empty(self):
        mfx = _make_mfx([])
        report = detect_anomalies(mfx)
        assert report.count == 0

    def test_returns_anomaly_report_type(self):
        mfx = _make_mfx(CLEAN_PTS)
        assert isinstance(detect_anomalies(mfx), AnomalyReport)


# ---------------------------------------------------------------------------
# Speed spike detection
# ---------------------------------------------------------------------------

class TestSpeedSpike:
    # Mathematical note: with k identical normal speeds + 1 spike, Z = sqrt(k).
    # Need k >= 15 to get Z = sqrt(15) ≈ 3.87 > 3.0 threshold.
    def _mfx_with_spike(self, spike_speed=42.0):
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(15)]
        pts.append(_pt(15.0, 48.8581, 2.3522, 50.0, spike_speed))
        return _make_mfx(pts)

    def test_detects_speed_spike(self):
        mfx = self._mfx_with_spike(42.0)
        report = detect_anomalies(mfx)
        kinds = [a.kind for a in report.anomalies]
        assert "speed_spike" in kinds

    def test_spike_at_correct_time(self):
        mfx = self._mfx_with_spike(42.0)
        report = detect_anomalies(mfx)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert spikes[0].t == pytest.approx(15.0)

    def test_spike_severity_warning(self):
        # Z = sqrt(15) ≈ 3.87, which is > 3 but < 10 → warning
        mfx = self._mfx_with_spike(42.0)
        report = detect_anomalies(mfx)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert len(spikes) >= 1
        assert spikes[0].severity == "warning"

    def test_extreme_spike_severity_critical(self):
        # With 101 normal + 1 spike: Z = sqrt(101) ≈ 10.05 > 10 → critical
        pts = [_pt(float(i), 48.8566 + i * 0.00001, 2.3522, 50.0, 8.0) for i in range(101)]
        pts.append(_pt(101.0, 48.8676, 2.3522, 50.0, 200.0))
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert len(spikes) >= 1
        assert spikes[0].severity == "critical"

    def test_detail_contains_speed_value(self):
        mfx = self._mfx_with_spike(42.0)
        report = detect_anomalies(mfx)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert "42" in spikes[0].detail

    def test_custom_z_threshold_higher_no_detection(self):
        mfx = self._mfx_with_spike(42.0)
        # Z ≈ 3.87 → raising threshold to 5 should suppress it
        report = detect_anomalies(mfx, speed_z_threshold=5.0)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert len(spikes) == 0

    def test_all_same_speed_no_spike(self):
        pts = [_pt(float(i), 48.0 + i * 0.0001, 2.0, 50.0, 8.0) for i in range(10)]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)
        spikes = [a for a in report.anomalies if a.kind == "speed_spike"]
        assert len(spikes) == 0

    def test_null_speed_skipped(self):
        pts = [_pt(float(i), 48.0 + i * 0.0001, 2.0, 50.0, 8.0) for i in range(8)]
        pts.append(TrajectoryPoint(t=8.0, lat=48.0008, lon=2.0, alt_m=50.0, speed_ms=None))
        pts.append(_pt(9.0, 48.0009, 2.0, 50.0, 8.0))
        mfx = _make_mfx(pts)
        # Should not raise, and the null-speed point should not cause false positive
        report = detect_anomalies(mfx)
        assert isinstance(report, AnomalyReport)


# ---------------------------------------------------------------------------
# GPS jump detection
# ---------------------------------------------------------------------------

class TestGpsJump:
    def _mfx_with_jump(self):
        pts = [
            _pt(0.0, 48.8566, 2.3522, 50.0, 8.0),
            _pt(1.0, 48.8567, 2.3523, 50.0, 8.0),
            _pt(2.0, 48.9100, 2.4500, 50.0, 8.0),  # GPS jump ~7km in 1s
            _pt(3.0, 48.8569, 2.3525, 50.0, 8.0),
        ]
        return _make_mfx(pts)

    def test_detects_gps_jump(self):
        mfx = self._mfx_with_jump()
        report = detect_anomalies(mfx)
        kinds = [a.kind for a in report.anomalies]
        assert "gps_jump" in kinds

    def test_gps_jump_always_critical(self):
        mfx = self._mfx_with_jump()
        report = detect_anomalies(mfx)
        jumps = [a for a in report.anomalies if a.kind == "gps_jump"]
        assert all(j.severity == "critical" for j in jumps)

    def test_gps_jump_at_correct_time(self):
        mfx = self._mfx_with_jump()
        report = detect_anomalies(mfx)
        jumps = [a for a in report.anomalies if a.kind == "gps_jump"]
        assert jumps[0].t == pytest.approx(2.0)

    def test_gps_jump_detail_contains_distance(self):
        mfx = self._mfx_with_jump()
        report = detect_anomalies(mfx)
        jumps = [a for a in report.anomalies if a.kind == "gps_jump"]
        assert "m" in jumps[0].detail

    def test_small_movement_no_jump(self):
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(5)]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)
        jumps = [a for a in report.anomalies if a.kind == "gps_jump"]
        assert len(jumps) == 0

    def test_custom_cap_lower_triggers_detection(self):
        # Very small cap should flag even normal movement
        pts = [_pt(float(i), 48.8566 + i * 0.001, 2.3522, 50.0, 8.0) for i in range(5)]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx, gps_speed_cap_ms=1.0)
        jumps = [a for a in report.anomalies if a.kind == "gps_jump"]
        assert len(jumps) > 0

    def test_null_coords_skipped(self):
        pts = [
            _pt(0.0, 48.8566, 2.3522),
            TrajectoryPoint(t=1.0, lat=None, lon=None, alt_m=50.0, speed_ms=8.0),
            _pt(2.0, 48.8568, 2.3524),
        ]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)  # should not raise
        assert isinstance(report, AnomalyReport)


# ---------------------------------------------------------------------------
# Altitude cliff detection
# ---------------------------------------------------------------------------

class TestAltitudeCliff:
    def _mfx_with_cliff(self, delta=-45.0):
        pts = [
            _pt(0.0, 48.8566, 2.3522, 50.0, 8.0),
            _pt(1.0, 48.8567, 2.3523, 50.0, 8.0),
            _pt(2.0, 48.8568, 2.3524, 50.0 + delta, 8.0),  # cliff
            _pt(3.0, 48.8569, 2.3525, 50.0 + delta, 8.0),
        ]
        return _make_mfx(pts)

    def test_detects_drop_cliff(self):
        mfx = self._mfx_with_cliff(-45.0)
        report = detect_anomalies(mfx)
        kinds = [a.kind for a in report.anomalies]
        assert "altitude_cliff" in kinds

    def test_detects_rise_cliff(self):
        mfx = self._mfx_with_cliff(+45.0)
        report = detect_anomalies(mfx)
        kinds = [a.kind for a in report.anomalies]
        assert "altitude_cliff" in kinds

    def test_cliff_at_correct_time(self):
        mfx = self._mfx_with_cliff(-45.0)
        report = detect_anomalies(mfx)
        cliffs = [a for a in report.anomalies if a.kind == "altitude_cliff"]
        assert cliffs[0].t == pytest.approx(2.0)

    def test_moderate_cliff_warning(self):
        mfx = self._mfx_with_cliff(-35.0)
        report = detect_anomalies(mfx)
        cliffs = [a for a in report.anomalies if a.kind == "altitude_cliff"]
        assert len(cliffs) >= 1
        assert cliffs[0].severity == "warning"

    def test_extreme_cliff_critical(self):
        mfx = self._mfx_with_cliff(-80.0)
        report = detect_anomalies(mfx)
        cliffs = [a for a in report.anomalies if a.kind == "altitude_cliff"]
        assert len(cliffs) >= 1
        assert cliffs[0].severity == "critical"

    def test_gradual_descent_no_cliff(self):
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0 - i * 0.5, 8.0)
               for i in range(10)]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)
        cliffs = [a for a in report.anomalies if a.kind == "altitude_cliff"]
        assert len(cliffs) == 0

    def test_null_alt_skipped(self):
        pts = [
            _pt(0.0, 48.8566, 2.3522, 50.0),
            TrajectoryPoint(t=1.0, lat=48.8567, lon=2.3523, alt_m=None),
            _pt(2.0, 48.8568, 2.3524, 50.0),
        ]
        mfx = _make_mfx(pts)
        report = detect_anomalies(mfx)  # should not raise
        assert isinstance(report, AnomalyReport)


# ---------------------------------------------------------------------------
# Multiple anomalies + sorting
# ---------------------------------------------------------------------------

class TestMultipleAnomalies:
    def _mfx_multi(self):
        # 20 normal background points so Z = sqrt(20) ≈ 4.47 > 3 for speed spike
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(20)]
        pts.append(_pt(20.0, 48.8586, 2.3522, 50.0, 80.0))  # speed spike
        pts.append(_pt(21.0, 48.9500, 2.5000, 50.0,  8.0))  # GPS jump
        pts.append(_pt(22.0, 48.8588, 2.3524, 50.0,  8.0))  # normal after jump
        pts.append(_pt(23.0, 48.8589, 2.3525,  2.0,  8.0))  # altitude cliff
        pts.append(_pt(24.0, 48.8590, 2.3526,  2.0,  8.0))
        return _make_mfx(pts)

    def test_detects_all_three_kinds(self):
        mfx = self._mfx_multi()
        report = detect_anomalies(mfx)
        kinds = {a.kind for a in report.anomalies}
        assert "speed_spike" in kinds
        assert "gps_jump" in kinds
        assert "altitude_cliff" in kinds

    def test_sorted_by_time(self):
        mfx = self._mfx_multi()
        report = detect_anomalies(mfx)
        times = [a.t for a in report.anomalies]
        assert times == sorted(times)

    def test_report_str_contains_all_kinds(self):
        mfx = self._mfx_multi()
        report = detect_anomalies(mfx)
        s = str(report)
        assert "speed_spike" in s
        assert "gps_jump" in s
        assert "altitude_cliff" in s

    def test_count_matches_anomalies_length(self):
        mfx = self._mfx_multi()
        report = detect_anomalies(mfx)
        assert report.count == len(report.anomalies)


# ---------------------------------------------------------------------------
# inject_events=True
# ---------------------------------------------------------------------------

class TestInjectEvents:
    def _mfx_with_spike(self):
        # 15 normal + 1 spike → Z = sqrt(15) ≈ 3.87 > 3 threshold
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(15)]
        pts.append(_pt(15.0, 48.8581, 2.3522, 50.0, 80.0))
        return _make_mfx(pts)

    def test_inject_creates_events_block(self):
        mfx = self._mfx_with_spike()
        assert mfx.events is None
        detect_anomalies(mfx, inject_events=True)
        assert mfx.events is not None

    def test_inject_adds_event_with_correct_type(self):
        mfx = self._mfx_with_spike()
        detect_anomalies(mfx, inject_events=True)
        types = [e.type for e in mfx.events.events]
        assert "anomaly" in types

    def test_inject_event_at_correct_time(self):
        mfx = self._mfx_with_spike()
        detect_anomalies(mfx, inject_events=True)
        anomaly_events = [e for e in mfx.events.events if e.type == "anomaly"]
        assert anomaly_events[0].t == pytest.approx(15.0)

    def test_inject_event_severity_propagated(self):
        mfx = self._mfx_with_spike()
        report = detect_anomalies(mfx, inject_events=True)
        event = mfx.events.events[0]
        spike = next(a for a in report.anomalies if a.kind == "speed_spike")
        assert event.severity == spike.severity

    def test_inject_clears_raw_lines(self):
        mfx = self._mfx_with_spike()
        detect_anomalies(mfx, inject_events=True)
        assert mfx.events.raw_lines == []

    def test_inject_updates_index_anomalies(self):
        mfx = self._mfx_with_spike()
        mfx.index = Index(bbox=(2.3522, 48.8566, 2.3522, 48.8575), anomalies=0)
        report = detect_anomalies(mfx, inject_events=True)
        assert mfx.index.anomalies == report.count

    def test_inject_appends_to_existing_events(self):
        mfx = self._mfx_with_spike()
        schema = [
            SchemaField("t", "float", ["no_null"]),
            SchemaField("type", "str", []),
            SchemaField("severity", "str", []),
            SchemaField("detail", "str", []),
        ]
        mfx.events = Events(
            schema_fields=schema,
            events=[Event(t=0.0, type="takeoff", severity="info", detail="nominal")],
            raw_lines=[],
        )
        detect_anomalies(mfx, inject_events=True)
        types = [e.type for e in mfx.events.events]
        assert "takeoff" in types
        assert "anomaly" in types

    def test_no_inject_when_no_anomalies(self):
        mfx = _make_mfx(CLEAN_PTS)
        report = detect_anomalies(mfx, inject_events=True)
        assert report.count == 0
        assert mfx.events is None  # should not have created an empty block

    def test_inject_false_does_not_modify_mfx(self):
        mfx = self._mfx_with_spike()
        detect_anomalies(mfx, inject_events=False)
        assert mfx.events is None


# ---------------------------------------------------------------------------
# Round-trip: inject → write → parse → validate events
# ---------------------------------------------------------------------------

class TestRoundTrip:
    def test_inject_write_parse(self, tmp_path):
        import pymfx
        # 15 normal + 1 spike → Z = sqrt(15) ≈ 3.87 > 3
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(15)]
        pts.append(_pt(15.0, 48.8581, 2.3522, 50.0, 80.0))
        mfx = _make_mfx(pts)

        detect_anomalies(mfx, inject_events=True)
        out = tmp_path / "out.mfx"
        pymfx.write(mfx, out)

        mfx2 = pymfx.parse(out.read_text(encoding="utf-8"))
        assert mfx2.events is not None
        anomaly_events = [e for e in mfx2.events.events if e.type == "anomaly"]
        assert len(anomaly_events) >= 1


# ---------------------------------------------------------------------------
# CLI  cmd_anomalies
# ---------------------------------------------------------------------------

class TestCmdAnomalies:
    def _mfx_text_with_spike(self):
        # 15 normal rows + 1 spike → Z = sqrt(15) ≈ 3.87 > 3
        return """\
@mfx 1.0
@encoding UTF-8

[meta]
id            : uuid:00000000-0000-0000-0000-000000000001
drone_id      : drone:test
drone_type    : multirotor
pilot_id      : pilot:test
date_start    : 2025-06-01T00:00:00Z
status        : complete
application   : test
location      : Testville
sensors       : [rgb]
data_level    : raw
license       : CC-BY-4.0
contact       : t@t.com

[trajectory]
frequency_hz : 1.0
@schema point: {t:float [no_null], lat:float [no_null], lon:float [no_null], alt_m:float32, speed_ms:float32}

data[]:
0.000  | 48.8566 | 2.3522 | 50.0 | 8.0
1.000  | 48.8567 | 2.3523 | 50.0 | 8.0
2.000  | 48.8568 | 2.3524 | 50.0 | 8.0
3.000  | 48.8569 | 2.3525 | 50.0 | 8.0
4.000  | 48.8570 | 2.3526 | 50.0 | 8.0
5.000  | 48.8571 | 2.3527 | 50.0 | 8.0
6.000  | 48.8572 | 2.3528 | 50.0 | 8.0
7.000  | 48.8573 | 2.3529 | 50.0 | 8.0
8.000  | 48.8574 | 2.3530 | 50.0 | 8.0
9.000  | 48.8575 | 2.3531 | 50.0 | 8.0
10.000 | 48.8576 | 2.3532 | 50.0 | 8.0
11.000 | 48.8577 | 2.3533 | 50.0 | 8.0
12.000 | 48.8578 | 2.3534 | 50.0 | 8.0
13.000 | 48.8579 | 2.3535 | 50.0 | 8.0
14.000 | 48.8580 | 2.3536 | 50.0 | 8.0
15.000 | 48.8581 | 2.3537 | 50.0 | 80.0
"""

    def test_cmd_anomalies_returns_1_when_found(self, tmp_path):
        from pymfx.cli import cmd_anomalies
        src = tmp_path / "flight.mfx"
        src.write_text(self._mfx_text_with_spike(), encoding="utf-8")
        rc = cmd_anomalies(src, None)
        assert rc == 1

    def test_cmd_anomalies_prints_report(self, tmp_path, capsys):
        from pymfx.cli import cmd_anomalies
        src = tmp_path / "flight.mfx"
        src.write_text(self._mfx_text_with_spike(), encoding="utf-8")
        cmd_anomalies(src, None)
        out = capsys.readouterr().out
        assert "speed_spike" in out

    def test_cmd_anomalies_inject_and_save(self, tmp_path):
        from pymfx.cli import cmd_anomalies
        import pymfx
        src = tmp_path / "flight.mfx"
        src.write_text(self._mfx_text_with_spike(), encoding="utf-8")
        dest = tmp_path / "fixed.mfx"
        rc = cmd_anomalies(src, dest)
        assert rc == 1
        assert dest.exists()
        mfx2 = pymfx.parse(dest.read_text(encoding="utf-8"))
        assert mfx2.events is not None
        anomaly_events = [e for e in mfx2.events.events if e.type == "anomaly"]
        assert len(anomaly_events) >= 1

    def test_cmd_anomalies_clean_returns_0(self, tmp_path):
        from pymfx.cli import cmd_anomalies
        import pymfx
        pts = [_pt(float(i), 48.8566 + i * 0.0001, 2.3522, 50.0, 8.0) for i in range(10)]
        mfx = _make_mfx(pts)
        src = tmp_path / "clean.mfx"
        src.write_text(pymfx.write(mfx), encoding="utf-8")
        rc = cmd_anomalies(src, None)
        assert rc == 0
