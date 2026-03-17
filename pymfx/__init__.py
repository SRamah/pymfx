"""
pymfx — Python library for the Mission Flight Exchange (.mfx) v1.0 format

Quick start:

    import pymfx

    # Read a file
    mfx = pymfx.parse("mission.mfx")

    # Validate
    result = pymfx.validate(mfx)
    print(result)

    # Write
    pymfx.write(mfx, "out.mfx")

    # Convert
    geojson = pymfx.convert.to_geojson(mfx)
    mfx2    = pymfx.convert.from_gpx("flight.gpx")

    # Flight statistics
    stats = pymfx.flight_stats(mfx)
    print(stats)

    # Data science
    df = mfx.trajectory.to_dataframe()   # pandas DataFrame
    d  = mfx.to_dict()                   # plain dict
    js = mfx.to_json()                   # JSON string
"""

from . import convert
from .checksum import compute_checksum, verify_checksum
from .models import (
    Event,
    Events,
    Extension,
    Index,
    Meta,
    MfxFile,
    SchemaField,
    Trajectory,
    TrajectoryPoint,
)
from .parser import ParseError, parse
from .stats import FlightStats, flight_stats
from .validator import ValidationIssue, ValidationResult, validate
from .writer import write

__version__ = "1.0.0"
__all__ = [
    "parse", "ParseError",
    "write",
    "validate", "ValidationResult", "ValidationIssue",
    "compute_checksum", "verify_checksum",
    "convert",
    "flight_stats", "FlightStats",
    "MfxFile", "Meta", "Trajectory", "TrajectoryPoint",
    "Events", "Event", "Index", "Extension", "SchemaField",
]
