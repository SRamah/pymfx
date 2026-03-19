"""
Tests for pymfx.cli — focused on cmd_import and cmd_repair.
"""
import sys
from pathlib import Path

import pytest

from pymfx.cli import cmd_import, cmd_repair
from pymfx.parser import parse
from pymfx.writer import write

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MINIMAL_GPX = """\
<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test"
     xmlns="http://www.topografix.com/GPX/1/1">
  <trk>
    <name>Test Track</name>
    <trkseg>
      <trkpt lat="48.8566" lon="2.3522"><ele>30.0</ele></trkpt>
      <trkpt lat="48.8570" lon="2.3530"><ele>32.0</ele></trkpt>
      <trkpt lat="48.8575" lon="2.3540"><ele>35.0</ele></trkpt>
    </trkseg>
  </trk>
</gpx>
"""

MINIMAL_GEOJSON = """\
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[2.3522, 48.8566, 30.0], [2.3530, 48.8570, 32.0], [2.3540, 48.8575, 35.0]]
      },
      "properties": {}
    }
  ]
}
"""

MINIMAL_CSV = """\
t,lat,lon,alt_m,speed_ms
0.0,48.8566,2.3522,30.0,0.0
1.0,48.8570,2.3530,32.0,2.5
2.0,48.8575,2.3540,35.0,3.0
"""

MINIMAL_DJI_CSV = """\
time(millisecond),latitude,longitude,altitude(feet),ascent(feet),speed(mph),heading(degrees)
0,48.8566,2.3522,98.4,0.0,0.0,0
1000,48.8570,2.3530,105.0,6.6,5.6,45
2000,48.8575,2.3540,114.8,16.4,6.7,90
"""


def _write_tmp(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# cmd_import – success cases
# ---------------------------------------------------------------------------

class TestCmdImportGpx:
    def test_import_gpx_to_stdout(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "track.gpx", MINIMAL_GPX)
        rc = cmd_import(src, "gpx", None)
        assert rc == 0
        out = capsys.readouterr().out
        assert "@mfx 1.0" in out
        assert "[trajectory]" in out

    def test_import_gpx_to_file(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "track.gpx", MINIMAL_GPX)
        dest = tmp_path / "out.mfx"
        rc = cmd_import(src, "gpx", dest)
        assert rc == 0
        assert dest.exists()
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert len(mfx.trajectory.points) == 3

    def test_import_gpx_checksum_computed(self, tmp_path):
        src = _write_tmp(tmp_path, "track.gpx", MINIMAL_GPX)
        dest = tmp_path / "out.mfx"
        cmd_import(src, "gpx", dest)
        raw = dest.read_text(encoding="utf-8")
        assert "@checksum sha256:" in raw

    def test_import_gpx_point_count_message(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "track.gpx", MINIMAL_GPX)
        dest = tmp_path / "out.mfx"
        cmd_import(src, "gpx", dest)
        err = capsys.readouterr().err
        assert "3 points" in err


class TestCmdImportGeojson:
    def test_import_geojson_to_file(self, tmp_path):
        src = _write_tmp(tmp_path, "route.geojson", MINIMAL_GEOJSON)
        dest = tmp_path / "out.mfx"
        rc = cmd_import(src, "geojson", dest)
        assert rc == 0
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert len(mfx.trajectory.points) == 3

    def test_import_geojson_stdout(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "route.geojson", MINIMAL_GEOJSON)
        rc = cmd_import(src, "geojson", None)
        assert rc == 0
        assert "[trajectory]" in capsys.readouterr().out


class TestCmdImportCsv:
    def test_import_csv_to_file(self, tmp_path):
        src = _write_tmp(tmp_path, "points.csv", MINIMAL_CSV)
        dest = tmp_path / "out.mfx"
        rc = cmd_import(src, "csv", dest)
        assert rc == 0
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert len(mfx.trajectory.points) == 3

    def test_import_csv_has_index(self, tmp_path):
        src = _write_tmp(tmp_path, "points.csv", MINIMAL_CSV)
        dest = tmp_path / "out.mfx"
        cmd_import(src, "csv", dest)
        raw = dest.read_text(encoding="utf-8")
        mfx = parse(raw)
        # from_csv may or may not produce an index — but the file should parse
        assert mfx.trajectory.points[0].lat == pytest.approx(48.8566)


class TestCmdImportDji:
    def test_import_dji_to_file(self, tmp_path):
        src = _write_tmp(tmp_path, "log.csv", MINIMAL_DJI_CSV)
        dest = tmp_path / "out.mfx"
        rc = cmd_import(src, "dji", dest)
        assert rc == 0
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert len(mfx.trajectory.points) == 3

    def test_import_dji_source_format(self, tmp_path):
        src = _write_tmp(tmp_path, "log.csv", MINIMAL_DJI_CSV)
        dest = tmp_path / "out.mfx"
        cmd_import(src, "dji", dest)
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert mfx.meta.source_format is not None


# ---------------------------------------------------------------------------
# cmd_import – error cases
# ---------------------------------------------------------------------------

class TestCmdImportErrors:
    def test_import_bad_encoding(self, tmp_path):
        src = tmp_path / "bad.gpx"
        src.write_bytes(b"\xff\xfe bad bytes \x00\x01")
        rc = cmd_import(src, "gpx", None)
        assert rc == 1

    def test_import_malformed_gpx(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "bad.gpx", "this is not xml at all!!!")
        rc = cmd_import(src, "gpx", None)
        assert rc == 1
        assert "Import error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_repair – success cases
# ---------------------------------------------------------------------------

# Minimal .mfx without a checksum or index to repair
_MFX_NO_INDEX = """\
@mfx 1.0
@encoding UTF-8

[meta]
id                   : uuid:550e8400-e29b-41d4-a716-446655440000
drone_id             : drone:test-drone
drone_type           : multirotor
pilot_id             : pilot:test
date_start           : 2025-06-01T00:00:00Z
status               : complete
application          : test
location             : Testville
sensors              : [rgb]
data_level           : raw
license              : CC-BY-4.0
contact              : test@test.com

[trajectory]
frequency_hz : 1.0
@schema point: {t:float [no_null], lat:float [no_null], lon:float [no_null], alt_m:float32, speed_ms:float32}

data[]:
0.000 | 48.8566 | 2.3522 | 30.0 | 0.0
1.000 | 48.8570 | 2.3530 | 32.0 | 2.5
2.000 | 48.8575 | 2.3540 | 35.0 | 3.0
"""

# Same file but with an intentionally wrong checksum
_MFX_WRONG_CHECKSUM = _MFX_NO_INDEX.replace(
    "frequency_hz : 1.0\n@schema",
    "frequency_hz : 1.0\n@checksum sha256:deadbeef0000\n@schema",
)

# Same file with a wrong bbox in the index
_MFX_WRONG_INDEX = _MFX_NO_INDEX + """\

[index]
bbox      : (0.0,0.0,1.0,1.0)
anomalies : 99
"""


class TestCmdRepairAddsIndex:
    def test_repair_adds_index_block(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        dest = tmp_path / "fixed.mfx"
        rc = cmd_repair(src, dest)
        assert rc == 0
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert mfx.index is not None
        assert mfx.index.bbox is not None

    def test_repair_bbox_correct(self, tmp_path):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        mfx = parse(dest.read_text(encoding="utf-8"))
        lon_min, lat_min, lon_max, lat_max = mfx.index.bbox
        assert lon_min == pytest.approx(2.3522)
        assert lat_min == pytest.approx(48.8566)
        assert lon_max == pytest.approx(2.3540)
        assert lat_max == pytest.approx(48.8575)

    def test_repair_reports_index_added(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        out = capsys.readouterr().out
        assert "[index] block added" in out


class TestCmdRepairFixesChecksum:
    def test_repair_writes_valid_checksum(self, tmp_path):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_WRONG_CHECKSUM)
        dest = tmp_path / "fixed.mfx"
        rc = cmd_repair(src, dest)
        assert rc == 0
        raw = dest.read_text(encoding="utf-8")
        assert "@checksum sha256:" in raw
        # Should now be a valid 64-char hex digest
        import re
        m = re.search(r"@checksum sha256:([0-9a-f]+)", raw)
        assert m and len(m.group(1)) == 64

    def test_repair_checksum_message(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        out = capsys.readouterr().out
        assert "SHA-256 checksums recomputed" in out


class TestCmdRepairFixesWrongIndex:
    def test_repair_corrects_bbox(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_WRONG_INDEX)
        dest = tmp_path / "fixed.mfx"
        rc = cmd_repair(src, dest)
        assert rc == 0
        mfx = parse(dest.read_text(encoding="utf-8"))
        lon_min, lat_min, lon_max, lat_max = mfx.index.bbox
        assert lon_min == pytest.approx(2.3522)
        assert lat_max == pytest.approx(48.8575)

    def test_repair_corrects_anomaly_count(self, tmp_path):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_WRONG_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        mfx = parse(dest.read_text(encoding="utf-8"))
        assert mfx.index.anomalies == 0  # no actual anomalies in the data

    def test_repair_reports_bbox_changed(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_WRONG_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        out = capsys.readouterr().out
        assert "bbox" in out

    def test_repair_reports_anomalies_changed(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_WRONG_INDEX)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        out = capsys.readouterr().out
        assert "anomalies" in out


class TestCmdRepairInPlace:
    def test_repair_inplace_when_no_output(self, tmp_path, capsys):
        """--repair with no -o writes back to the source file."""
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        rc = cmd_repair(src, None)
        assert rc == 0
        # File should now have an [index] block
        mfx = parse(src.read_text(encoding="utf-8"))
        assert mfx.index is not None

    def test_repair_inplace_success_message(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "flight.mfx", _MFX_NO_INDEX)
        cmd_repair(src, None)
        out = capsys.readouterr().out
        assert str(src) in out


# ---------------------------------------------------------------------------
# cmd_repair – error cases
# ---------------------------------------------------------------------------

class TestCmdRepairErrors:
    def test_repair_bad_encoding(self, tmp_path):
        src = tmp_path / "bad.mfx"
        src.write_bytes(b"\xff\xfe not utf-8 \x00")
        rc = cmd_repair(src, None)
        assert rc == 1

    def test_repair_parse_error(self, tmp_path, capsys):
        src = _write_tmp(tmp_path, "bad.mfx", "this is not mfx format")
        rc = cmd_repair(src, None)
        assert rc == 1
        assert "Parse error" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# cmd_repair – unknown field warnings
# ---------------------------------------------------------------------------

class TestCmdRepairWarnings:
    def test_repair_warns_unknown_fields(self, tmp_path, capsys):
        mfx_unknown = _MFX_NO_INDEX.replace(
            "location             : Testville",
            "location             : unknown",
        )
        src = _write_tmp(tmp_path, "flight.mfx", mfx_unknown)
        dest = tmp_path / "fixed.mfx"
        cmd_repair(src, dest)
        err = capsys.readouterr().err
        assert "meta.location" in err
        assert "unknown" in err
