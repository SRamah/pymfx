"""
Tests for pymfx.convert - import/export round-trips and format validation.
"""
import json
import xml.etree.ElementTree as ET

import pytest

import pymfx
from pymfx.convert import (
    from_csv,
    from_geojson,
    from_gpx,
    to_csv,
    to_geojson,
    to_gpx,
    to_kml,
)
from pymfx.models import MfxFile, Meta, SchemaField, Trajectory, TrajectoryPoint

# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def simple_mfx() -> MfxFile:
    """A minimal MfxFile with 5 trajectory points."""
    points = [
        TrajectoryPoint(t=float(i), lat=48.858 + i * 0.001, lon=2.295 + i * 0.001,
                        alt_m=100.0 + i * 5, speed_ms=5.0, heading=90.0)
        for i in range(5)
    ]
    schema = [
        SchemaField("t",   "float", ["no_null"]),
        SchemaField("lat", "float", ["no_null"]),
        SchemaField("lon", "float", ["no_null"]),
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


# ---------------------------------------------------------------------------
# to_geojson
# ---------------------------------------------------------------------------

class TestToGeoJSON:
    def test_valid_json(self, simple_mfx):
        out = to_geojson(simple_mfx)
        data = json.loads(out)
        assert data["type"] == "FeatureCollection"

    def test_linestring_present(self, simple_mfx):
        data = json.loads(to_geojson(simple_mfx))
        geom_types = [f["geometry"]["type"] for f in data["features"]]
        assert "LineString" in geom_types

    def test_coordinate_count(self, simple_mfx):
        data = json.loads(to_geojson(simple_mfx))
        ls = next(f for f in data["features"] if f["geometry"]["type"] == "LineString")
        assert len(ls["geometry"]["coordinates"]) == 5

    def test_include_points(self, simple_mfx):
        data = json.loads(to_geojson(simple_mfx, include_points=True))
        point_features = [f for f in data["features"]
                          if f["geometry"]["type"] == "Point"]
        assert len(point_features) == 5

    def test_compact_output(self, simple_mfx):
        out = to_geojson(simple_mfx, indent=None)
        assert "\n" not in out


# ---------------------------------------------------------------------------
# to_gpx
# ---------------------------------------------------------------------------

class TestToGPX:
    def test_valid_xml(self, simple_mfx):
        out = to_gpx(simple_mfx)
        root = ET.fromstring(out)
        assert root.tag.endswith("gpx") or "gpx" in root.tag.lower()

    def test_trkpt_count(self, simple_mfx):
        out = to_gpx(simple_mfx)
        root = ET.fromstring(out)
        ns = {"g": "http://www.topografix.com/GPX/1/1"}
        trkpts = root.findall(".//g:trkpt", ns)
        assert len(trkpts) == 5

    def test_ele_present(self, simple_mfx):
        out = to_gpx(simple_mfx)
        root = ET.fromstring(out)
        ns = {"g": "http://www.topografix.com/GPX/1/1"}
        eles = root.findall(".//g:ele", ns)
        assert len(eles) == 5


# ---------------------------------------------------------------------------
# to_kml
# ---------------------------------------------------------------------------

class TestToKML:
    def test_valid_xml(self, simple_mfx):
        out = to_kml(simple_mfx)
        root = ET.fromstring(out)
        assert "kml" in root.tag.lower()

    def test_linestring_present(self, simple_mfx):
        out = to_kml(simple_mfx)
        root = ET.fromstring(out)
        ls = root.findall(".//{http://www.opengis.net/kml/2.2}LineString")
        assert len(ls) == 1

    def test_coordinates_count(self, simple_mfx):
        out = to_kml(simple_mfx)
        root = ET.fromstring(out)
        coords_el = root.find(".//{http://www.opengis.net/kml/2.2}coordinates")
        assert coords_el is not None
        coords = coords_el.text.strip().split()
        assert len(coords) == 5


# ---------------------------------------------------------------------------
# to_csv
# ---------------------------------------------------------------------------

class TestToCSV:
    def test_header_and_rows(self, simple_mfx):
        out = to_csv(simple_mfx)
        lines = [l for l in out.strip().splitlines() if l]
        assert lines[0].startswith("t,")
        assert len(lines) == 6  # header + 5 data rows

    def test_lat_lon_values(self, simple_mfx):
        import csv, io
        out = to_csv(simple_mfx)
        rows = list(csv.DictReader(io.StringIO(out)))
        assert float(rows[0]["lat"]) == pytest.approx(48.858)
        assert float(rows[0]["lon"]) == pytest.approx(2.295)

    def test_include_events_no_events(self, simple_mfx):
        out = to_csv(simple_mfx, include_events=True)
        assert "type" not in out  # no events section added


# ---------------------------------------------------------------------------
# from_geojson round-trip
# ---------------------------------------------------------------------------

class TestFromGeoJSON:
    def test_round_trip_point_count(self, simple_mfx):
        geojson_str = to_geojson(simple_mfx)
        mfx2 = from_geojson(geojson_str)
        assert len(mfx2.trajectory.points) == 5

    def test_round_trip_coords(self, simple_mfx):
        mfx2 = from_geojson(to_geojson(simple_mfx))
        p0 = mfx2.trajectory.points[0]
        assert p0.lat == pytest.approx(48.858, abs=1e-5)
        assert p0.lon == pytest.approx(2.295, abs=1e-5)

    def test_meta_drone_id_preserved(self, simple_mfx):
        mfx2 = from_geojson(to_geojson(simple_mfx))
        assert mfx2.meta.drone_id == "TEST-01"

    def test_no_linestring_raises(self):
        bad = json.dumps({"type": "FeatureCollection", "features": []})
        with pytest.raises(ValueError, match="No LineString"):
            from_geojson(bad)


# ---------------------------------------------------------------------------
# from_csv round-trip
# ---------------------------------------------------------------------------

class TestFromCSV:
    def test_round_trip_point_count(self, simple_mfx):
        csv_str = to_csv(simple_mfx)
        mfx2 = from_csv(csv_str)
        assert len(mfx2.trajectory.points) == 5

    def test_round_trip_coords(self, simple_mfx):
        mfx2 = from_csv(to_csv(simple_mfx))
        p0 = mfx2.trajectory.points[0]
        assert p0.lat == pytest.approx(48.858, abs=1e-5)

    def test_empty_csv_raises(self):
        with pytest.raises(ValueError):
            from_csv("lat,lon\n")

    def test_custom_col_names(self):
        csv_data = "latitude,longitude,altitude\n48.85,2.29,100\n48.86,2.30,101\n"
        mfx = from_csv(csv_data, lat_col="latitude", lon_col="longitude", alt_col="altitude")
        assert len(mfx.trajectory.points) == 2
        assert mfx.trajectory.points[0].alt_m == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# from_gpx
# ---------------------------------------------------------------------------

class TestFromGPX:
    GPX_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">
  <metadata>
    <name>TestFlight</name>
    <time>2025-06-01T10:00:00Z</time>
  </metadata>
  <trk>
    <trkseg>
      <trkpt lat="48.858" lon="2.295"><ele>100</ele><time>2025-06-01T10:00:00Z</time></trkpt>
      <trkpt lat="48.859" lon="2.296"><ele>105</ele><time>2025-06-01T10:00:01Z</time></trkpt>
      <trkpt lat="48.860" lon="2.297"><ele>110</ele><time>2025-06-01T10:00:02Z</time></trkpt>
    </trkseg>
  </trk>
</gpx>"""

    def test_point_count(self):
        mfx = from_gpx(self.GPX_SAMPLE)
        assert len(mfx.trajectory.points) == 3

    def test_time_axis(self):
        mfx = from_gpx(self.GPX_SAMPLE)
        pts = mfx.trajectory.points
        assert pts[0].t == pytest.approx(0.0)
        assert pts[1].t == pytest.approx(1.0)
        assert pts[2].t == pytest.approx(2.0)

    def test_altitude(self):
        mfx = from_gpx(self.GPX_SAMPLE)
        assert mfx.trajectory.points[0].alt_m == pytest.approx(100.0)

    def test_frequency_detected(self):
        mfx = from_gpx(self.GPX_SAMPLE)
        assert mfx.trajectory.frequency_hz == pytest.approx(1.0)

    def test_meta_date_start(self):
        mfx = from_gpx(self.GPX_SAMPLE)
        assert mfx.meta.date_start == "2025-06-01T10:00:00Z"
