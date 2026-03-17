"""
pymfx.cli — Command-line interface

Usage:
    pymfx flight.mfx --validate
    pymfx flight.mfx --checksum
    pymfx flight.mfx --info
    pymfx flight.mfx --stats
    pymfx flight.mfx --export geojson
    pymfx flight.mfx --export gpx -o flight.gpx
    pymfx flight.mfx --export kml  -o flight.kml
    pymfx flight.mfx --export csv  -o flight.csv
"""
import argparse
import sys
from pathlib import Path

from .checksum import compute_checksum
from .convert import to_csv, to_geojson, to_gpx, to_kml
from .parser import ParseError, parse
from .stats import flight_stats
from .utils import diff
from .validator import validate

_EXPORT_FORMATS = ("geojson", "gpx", "kml", "csv")


def cmd_validate(path: Path) -> int:
    """Validate a .mfx file and print issues."""
    try:
        raw_text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        print(f"✗ File encoding error (expected UTF-8): {e}", file=sys.stderr)
        return 1
    try:
        mfx = parse(raw_text)
    except ParseError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    result = validate(mfx, raw_text=raw_text)
    print(str(result))
    return 0 if result.is_valid else 1


def cmd_checksum(path: Path) -> int:
    """Compute and display SHA-256 checksums for all data[] blocks in a .mfx file."""
    try:
        raw_text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        print(f"✗ File encoding error (expected UTF-8): {e}", file=sys.stderr)
        return 1
    try:
        mfx = parse(raw_text)
    except ParseError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    print(f"File: {path}")
    traj = mfx.trajectory
    checksum = compute_checksum(traj.raw_lines)
    declared = traj.checksum or "(not declared)"
    match = "✓" if traj.checksum and traj.checksum == checksum else ("✗" if traj.checksum else "—")
    print(f"  [trajectory] data[] : {checksum}")
    print(f"    declared          : {declared} {match}")

    if mfx.events:
        ev_checksum = compute_checksum(mfx.events.raw_lines)
        ev_declared = mfx.events.checksum or "(not declared)"
        ev_match = "✓" if mfx.events.checksum and mfx.events.checksum == ev_checksum else ("✗" if mfx.events.checksum else "—")
        print(f"  [events] data[]    : {ev_checksum}")
        print(f"    declared         : {ev_declared} {ev_match}")

    return 0


def cmd_info(path: Path) -> int:
    """Print a summary of a .mfx file."""
    try:
        raw_text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        print(f"✗ File encoding error (expected UTF-8): {e}", file=sys.stderr)
        return 1
    try:
        mfx = parse(raw_text)
    except ParseError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    m = mfx.meta
    print(f"File     : {path}")
    print(f"Version  : {mfx.version}")
    print(f"ID       : {m.id}")
    print(f"Drone    : {m.drone_id} ({m.drone_type})")
    print(f"Pilot    : {m.pilot_id}")
    print(f"Start    : {m.date_start}")
    if m.date_end:
        print(f"End      : {m.date_end}")
    print(f"Status   : {m.status}")
    print(f"App      : {m.application}")
    print(f"Location : {m.location}")
    print(f"Sensors  : {m.sensors}")
    t = mfx.trajectory
    print("\n[trajectory]")
    print(f"  Points       : {len(t.points)}")
    print(f"  frequency_hz : {t.frequency_hz}")
    if t.points:
        print(f"  t range      : {t.points[0].t:.3f}s — {t.points[-1].t:.3f}s")
    if mfx.events:
        print(f"\n[events]  : {len(mfx.events.events)} event(s)")
    if mfx.index:
        print("\n[index]")
        if mfx.index.bbox:
            print(f"  bbox      : {mfx.index.bbox}")
        if mfx.index.anomalies is not None:
            print(f"  anomalies : {mfx.index.anomalies}")
    if mfx.extensions:
        print(f"\nExtensions : {[e.name for e in mfx.extensions]}")

    return 0


def cmd_stats(path: Path) -> int:
    """Print aggregated flight statistics for a .mfx file."""
    try:
        raw_text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        print(f"✗ File encoding error (expected UTF-8): {e}", file=sys.stderr)
        return 1
    try:
        mfx = parse(raw_text)
    except ParseError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    print(str(flight_stats(mfx)))
    return 0


def cmd_diff(path1: Path, path2: Path) -> int:
    """Compare two .mfx files and print a structured diff."""
    results = []
    for path in (path1, path2):
        try:
            raw = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as e:
            print(f"✗ Encoding error in {path}: {e}", file=sys.stderr)
            return 1
        try:
            results.append(parse(raw))
        except ParseError as e:
            print(f"✗ Parse error in {path}: {e}", file=sys.stderr)
            return 1

    mfx1, mfx2 = results
    result = diff(mfx1, mfx2)
    print(f"File A : {path1}")
    print(f"File B : {path2}")
    print()
    print(str(result))
    return 0 if not result.has_differences else 1


def cmd_export(path: Path, fmt: str, output: Path | None) -> int:
    """Export a .mfx file to another format."""
    try:
        raw_text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError as e:
        print(f"✗ File encoding error (expected UTF-8): {e}", file=sys.stderr)
        return 1
    try:
        mfx = parse(raw_text)
    except ParseError as e:
        print(f"✗ Parse error: {e}", file=sys.stderr)
        return 1

    converters = {
        "geojson": to_geojson,
        "gpx":     to_gpx,
        "kml":     to_kml,
        "csv":     to_csv,
    }
    result = converters[fmt](mfx)

    if output:
        output.write_text(result, encoding='utf-8')
        print(f"✓ Exported to {output}", file=sys.stderr)
    else:
        print(result)
    return 0


def main():
    parser = argparse.ArgumentParser(
        prog='pymfx',
        description='Read, validate and manage .mfx v1.0 mission files',
        epilog=(
            'Examples:\n'
            '  pymfx flight.mfx --validate\n'
            '  pymfx flight.mfx --info\n'
            '  pymfx flight.mfx --stats\n'
            '  pymfx flight.mfx --checksum\n'
            '  pymfx flight.mfx --diff other.mfx\n'
            '  pymfx flight.mfx --export geojson\n'
            '  pymfx flight.mfx --export gpx -o flight.gpx'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('file', type=Path, help='.mfx file to process')
    parser.add_argument('-o', '--output', type=Path, default=None,
                        help='Output file path (default: stdout)')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--validate', action='store_true',
                       help='Validate the file (rules V01–V21)')
    group.add_argument('--checksum', action='store_true',
                       help='Compute and verify SHA-256 checksums')
    group.add_argument('--info', action='store_true',
                       help='Print a summary of the file')
    group.add_argument('--stats', action='store_true',
                       help='Print aggregated flight statistics')
    group.add_argument('--diff', type=Path, metavar='FILE2',
                       help='Compare with FILE2 and print structured differences')
    group.add_argument('--export', choices=_EXPORT_FORMATS, metavar='FORMAT',
                       help=f'Export to another format: {", ".join(_EXPORT_FORMATS)}')

    args = parser.parse_args()

    if not args.file.exists():
        print(f"✗ File not found: {args.file}", file=sys.stderr)
        sys.exit(1)

    if args.validate:
        sys.exit(cmd_validate(args.file))
    elif args.checksum:
        sys.exit(cmd_checksum(args.file))
    elif args.info:
        sys.exit(cmd_info(args.file))
    elif args.stats:
        sys.exit(cmd_stats(args.file))
    elif args.diff:
        sys.exit(cmd_diff(args.file, args.diff))
    elif args.export:
        sys.exit(cmd_export(args.file, args.export, args.output))


if __name__ == '__main__':
    main()
