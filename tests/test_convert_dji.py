"""
Tests for pymfx.convert.from_dji_csv
Covers: AirData dialect, DJI Fly dialect, unit conversions,
        event extraction, edge cases.
"""
import textwrap

import pytest

from pymfx.convert.from_dji_csv import from_dji_csv
from pymfx.models import MfxFile

# ---------------------------------------------------------------------------
# Fixtures — synthetic CSV data
# ---------------------------------------------------------------------------

AIRDATA_CSV = textwrap.dedent("""\
    datetime(utc),latitude,longitude,altitude(feet),speed(mph),compass_heading(degrees),pitch(degrees),roll(degrees),isPhoto,isVideo,flycstate,battery_percent,satellites,message
    2025-01-15 10:00:00.000,48.8566,2.3522,164.042,6.711,90.0,-2.5,1.2,False,False,AutoTakeoff,95,12,
    2025-01-15 10:00:01.000,48.8567,2.3523,196.850,11.185,91.0,-3.0,1.5,False,True,P-GPS,94,12,
    2025-01-15 10:00:02.000,48.8568,2.3524,229.659,13.422,92.0,-3.2,1.8,True,True,P-GPS,93,12,
    2025-01-15 10:00:03.000,48.8569,2.3525,262.467,11.185,93.0,-2.8,1.6,False,True,P-GPS,92,12,
    2025-01-15 10:00:04.000,48.8570,2.3526,262.467,0.000,94.0,-1.0,0.5,False,False,AutoLanding,91,12,Low battery warning
""")

DJIFLY_CSV = textwrap.dedent("""\
    time(millisecond),latitude,longitude,altitude(feet),speed(mph),compass_heading(degrees)
    0,48.8566,2.3522,98.425,0.000,180.0
    1000,48.8567,2.3523,131.234,6.711,181.0
    2000,48.8568,2.3524,164.042,8.948,182.0
    3000,48.8569,2.3525,164.042,4.474,183.0
""")

MINIMAL_CSV = textwrap.dedent("""\
    datetime(utc),latitude,longitude
    2025-06-01 08:00:00,51.5074,-0.1278
    2025-06-01 08:00:01,51.5075,-0.1277
    2025-06-01 08:00:02,51.5076,-0.1276
""")

NO_GPS_ROWS_CSV = textwrap.dedent("""\
    datetime(utc),latitude,longitude,altitude(feet)
    2025-01-01 00:00:00,,,0.0
    2025-01-01 00:00:01,48.0,2.0,32.808
    2025-01-01 00:00:02,48.001,2.001,65.617
""")


# ---------------------------------------------------------------------------
# Basic parsing
# ---------------------------------------------------------------------------

class TestFromDjiCsvBasic:

    def test_returns_mfxfile(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert isinstance(mfx, MfxFile)

    def test_version(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.version == "1.0"

    def test_manufacturer(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.meta.manufacturer == "DJI"

    def test_source_format(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.meta.source_format == "dji_csv"

    def test_dialect_detected_airdata(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert "airdata" in (mfx.meta.source_format_detail or "")

    def test_dialect_detected_djifly(self):
        mfx = from_dji_csv(DJIFLY_CSV)
        assert "dji_fly" in (mfx.meta.source_format_detail or "")

    def test_point_count_airdata(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert len(mfx.trajectory.points) == 5

    def test_point_count_djifly(self):
        mfx = from_dji_csv(DJIFLY_CSV)
        assert len(mfx.trajectory.points) == 4

    def test_meta_uuid_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.meta.id.startswith("uuid:")

    def test_date_start_extracted(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.meta.date_start == "2025-01-15T10:00:00Z"


# ---------------------------------------------------------------------------
# Coordinates
# ---------------------------------------------------------------------------

class TestCoordinates:

    def test_lat_lon_correct(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        p0 = mfx.trajectory.points[0]
        assert p0.lat == pytest.approx(48.8566)
        assert p0.lon == pytest.approx(2.3522)

    def test_all_points_have_lat_lon(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        for p in mfx.trajectory.points:
            assert p.lat is not None
            assert p.lon is not None


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

class TestUnitConversions:

    def test_altitude_feet_to_metres(self):
        """164.042 feet == 50.0 m (within 1 mm)."""
        mfx = from_dji_csv(AIRDATA_CSV)
        p0 = mfx.trajectory.points[0]
        assert p0.alt_m == pytest.approx(164.042 * 0.3048, abs=0.001)

    def test_speed_mph_to_ms(self):
        """6.711 mph == 3.0 m/s (within 1 mm/s)."""
        mfx = from_dji_csv(AIRDATA_CSV)
        p0 = mfx.trajectory.points[0]
        assert p0.speed_ms == pytest.approx(6.711 * 0.44704, abs=0.001)

    def test_zero_speed_is_zero(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        last = mfx.trajectory.points[-1]
        assert last.speed_ms == pytest.approx(0.0, abs=0.001)

    def test_djifly_altitude_conversion(self):
        mfx = from_dji_csv(DJIFLY_CSV)
        p0 = mfx.trajectory.points[0]
        assert p0.alt_m == pytest.approx(98.425 * 0.3048, abs=0.001)


# ---------------------------------------------------------------------------
# Timestamps / t axis
# ---------------------------------------------------------------------------

class TestTimestamps:

    def test_t_starts_at_zero_airdata(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.trajectory.points[0].t == pytest.approx(0.0)

    def test_t_increments_by_one_second(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        pts = mfx.trajectory.points
        for i in range(1, len(pts)):
            assert pts[i].t == pytest.approx(pts[i - 1].t + 1.0, abs=0.001)

    def test_t_starts_at_zero_djifly(self):
        mfx = from_dji_csv(DJIFLY_CSV)
        assert mfx.trajectory.points[0].t == pytest.approx(0.0)

    def test_t_djifly_in_seconds(self):
        """DJI Fly uses milliseconds; 1000 ms should become t=1.000."""
        mfx = from_dji_csv(DJIFLY_CSV)
        assert mfx.trajectory.points[1].t == pytest.approx(1.0)

    def test_t_strictly_increasing(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        pts = mfx.trajectory.points
        for i in range(1, len(pts)):
            assert pts[i].t > pts[i - 1].t


# ---------------------------------------------------------------------------
# Orientation fields
# ---------------------------------------------------------------------------

class TestOrientation:

    def test_heading_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.trajectory.points[0].heading == pytest.approx(90.0)

    def test_pitch_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.trajectory.points[0].pitch == pytest.approx(-2.5)

    def test_roll_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.trajectory.points[0].roll == pytest.approx(1.2)


# ---------------------------------------------------------------------------
# Schema fields
# ---------------------------------------------------------------------------

class TestSchema:

    def test_required_fields_in_schema(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        names = [f.name for f in mfx.trajectory.schema_fields]
        assert "t" in names
        assert "lat" in names
        assert "lon" in names

    def test_alt_in_schema_when_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        names = [f.name for f in mfx.trajectory.schema_fields]
        assert "alt_m" in names

    def test_no_alt_in_schema_when_absent(self):
        mfx = from_dji_csv(MINIMAL_CSV)
        names = [f.name for f in mfx.trajectory.schema_fields]
        assert "alt_m" not in names

    def test_no_null_on_t_lat_lon(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        nn = {f.name for f in mfx.trajectory.schema_fields if "no_null" in f.constraints}
        assert {"t", "lat", "lon"}.issubset(nn)


# ---------------------------------------------------------------------------
# Frequency
# ---------------------------------------------------------------------------

class TestFrequency:

    def test_frequency_detected_1hz(self):
        """5 points over 4 seconds = 1 Hz."""
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.trajectory.frequency_hz == pytest.approx(1.0)

    def test_frequency_detected_djifly(self):
        """4 points over 3 seconds = 1 Hz."""
        mfx = from_dji_csv(DJIFLY_CSV)
        assert mfx.trajectory.frequency_hz == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------

class TestEvents:

    def test_events_present(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert mfx.events is not None
        assert len(mfx.events.events) > 0

    def test_state_change_event(self):
        """AutoTakeoff -> P-GPS at t=1 should generate a state_change event."""
        mfx = from_dji_csv(AIRDATA_CSV)
        types = [e.type for e in mfx.events.events]
        assert "state_change" in types

    def test_photo_event(self):
        """isPhoto=True at t=2 should generate a photo event."""
        mfx = from_dji_csv(AIRDATA_CSV)
        photo_events = [e for e in mfx.events.events if e.type == "photo"]
        assert len(photo_events) == 1
        assert photo_events[0].t == pytest.approx(2.0)

    def test_video_start_event(self):
        """Video starts at t=1 (False->True)."""
        mfx = from_dji_csv(AIRDATA_CSV)
        starts = [e for e in mfx.events.events if e.type == "video_start"]
        assert len(starts) == 1
        assert starts[0].t == pytest.approx(1.0)

    def test_video_stop_event(self):
        """Video stops at t=4 (True->False)."""
        mfx = from_dji_csv(AIRDATA_CSV)
        stops = [e for e in mfx.events.events if e.type == "video_stop"]
        assert len(stops) == 1
        assert stops[0].t == pytest.approx(4.0)

    def test_message_event_warning_severity(self):
        """'Low battery warning' should be severity=warning."""
        mfx = from_dji_csv(AIRDATA_CSV)
        msg_events = [e for e in mfx.events.events if e.type == "message"]
        assert len(msg_events) == 1
        assert msg_events[0].severity == "warning"
        assert "battery" in msg_events[0].detail.lower()

    def test_events_schema_has_four_fields(self):
        mfx = from_dji_csv(AIRDATA_CSV)
        assert len(mfx.events.schema_fields) == 4

    def test_no_events_when_no_event_columns(self):
        mfx = from_dji_csv(MINIMAL_CSV)
        assert mfx.events is None


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_rows_without_gps_are_skipped(self):
        """Rows with empty lat/lon should be skipped silently."""
        mfx = from_dji_csv(NO_GPS_ROWS_CSV)
        assert len(mfx.trajectory.points) == 2
        assert mfx.trajectory.points[0].lat == pytest.approx(48.0)

    def test_minimal_csv_no_crash(self):
        """CSV with only lat/lon/datetime should parse without error."""
        mfx = from_dji_csv(MINIMAL_CSV)
        assert len(mfx.trajectory.points) == 3

    def test_unknown_dialect(self):
        """CSV with unrecognised headers still parses (dialect=unknown)."""
        csv_data = "latitude,longitude\n48.0,2.0\n48.1,2.1\n"
        mfx = from_dji_csv(csv_data)
        assert len(mfx.trajectory.points) == 2
        assert "unknown" in (mfx.meta.source_format_detail or "")

    def test_result_is_writable(self):
        """from_dji_csv output can be serialised back to .mfx text."""
        import pymfx
        mfx = from_dji_csv(AIRDATA_CSV)
        text = pymfx.write(mfx)
        assert "[meta]" in text
        assert "[trajectory]" in text

    def test_result_roundtrip_parseable(self):
        """Written .mfx can be re-parsed without errors."""
        import pymfx
        mfx = from_dji_csv(AIRDATA_CSV)
        text = pymfx.write(mfx)
        mfx2 = pymfx.parse(text)
        assert len(mfx2.trajectory.points) == len(mfx.trajectory.points)
