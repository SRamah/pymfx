"""
pymfx.parser — Read a .mfx v1.0 file into Python objects
"""
from __future__ import annotations

import re
from pathlib import Path

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


class ParseError(Exception):
    pass


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove inline comments (# ...) except inside quoted strings.

    Handles escaped quotes (\") and both double-quote delimiters.
    """
    in_quote = False
    i = 0
    while i < len(line):
        ch = line[i]
        if ch == '\\' and in_quote:
            i += 2  # skip escaped character inside a string
            continue
        if ch == '"':
            in_quote = not in_quote
        if ch == '#' and not in_quote:
            return line[:i].rstrip()
        i += 1
    return line


def _parse_value(raw: str):
    """Convert a raw string value to a native Python type (best-effort)."""
    raw = raw.strip()
    if raw == '-':
        return None
    if raw.lower() == 'true':
        return True
    if raw.lower() == 'false':
        return False
    # list type [a, b, c]
    if raw.startswith('[') and raw.endswith(']'):
        inner = raw[1:-1]
        return [v.strip().strip('"') for v in inner.split(',')]
    # uuid
    if raw.startswith('uuid:'):
        return raw
    # bbox (lon_min, lat_min, lon_max, lat_max)
    if raw.startswith('(') and raw.endswith(')'):
        vals = [v.strip() for v in raw[1:-1].split(',')]
        try:
            return tuple(float(v) for v in vals)
        except ValueError:
            return raw
    # quoted string
    if raw.startswith('"') and raw.endswith('"'):
        return raw[1:-1]
    # int
    try:
        return int(raw)
    except ValueError:
        pass
    # float
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _parse_schema_line(schema_str: str) -> list[SchemaField]:
    """
    Parse a @schema line such as:
      point: {t:float [no_null], lat:float [range=-90..90, no_null], ...}
    Returns a list of SchemaField objects.

    Strategy: split the content inside {} into field tokens by advancing
    character by character and only splitting on ',' when outside any '[...]'.
    """
    m = re.search(r'\{(.+)\}', schema_str, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)

    # Token-aware split on commas outside brackets
    field_tokens = []
    depth = 0
    current = []
    for ch in inner:
        if ch == '[':
            depth += 1
            current.append(ch)
        elif ch == ']':
            depth -= 1
            current.append(ch)
        elif ch == ',' and depth == 0:
            field_tokens.append(''.join(current).strip())
            current = []
        else:
            current.append(ch)
    if current:
        field_tokens.append(''.join(current).strip())

    fields = []
    for token in field_tokens:
        token = token.strip()
        if not token:
            continue
        fm = re.match(r'(\w+)\s*:\s*(\w+)(.*)', token)
        if not fm:
            continue
        name = fm.group(1)
        dtype = fm.group(2)
        rest = fm.group(3).strip()
        constraints = []
        # Each [constraint] may contain commas (e.g. [range=-90..90, no_null])
        for cm in re.finditer(r'\[([^\]]+)\]', rest):
            cinner = cm.group(1)
            # Split individual constraints inside brackets
            parts = re.split(r',\s*(?=no_null|unique|enum=|range=|max_len=)', cinner)
            for c in parts:
                c = c.strip()
                if c:
                    # If it's an enum=[ without closing bracket, close it
                    if c.startswith('enum=[') and not c.endswith(']'):
                        c = c + ']'
                    constraints.append(c)
        fields.append(SchemaField(name=name, type=dtype, constraints=constraints))
    return fields


def _cast_field(value: str, field: SchemaField):
    """Cast a raw string value to the declared schema type."""
    if value.strip() == '-':
        return None
    v = value.strip()
    t = field.type.lower()
    if t in ('float', 'float32'):
        try:
            return float(v)
        except ValueError:
            raise ParseError(
                f"Cannot cast value {v!r} to float for field '{field.name}'"
            )
    if t == 'int':
        try:
            return int(v)
        except ValueError:
            raise ParseError(
                f"Cannot cast value {v!r} to int for field '{field.name}'"
            )
    if t == 'bool':
        return v.lower() == 'true'
    if v.startswith('"') and v.endswith('"'):
        return v[1:-1]
    return v


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

class MfxParser:
    def __init__(self, text: str):
        self._lines = text.splitlines()
        self._pos = 0

    def _current(self) -> str | None:
        while self._pos < len(self._lines):
            raw = self._lines[self._pos]
            stripped = _strip_comment(raw).rstrip()
            if stripped.strip():
                return stripped
            self._pos += 1
        return None

    def _advance(self):
        self._pos += 1

    def _consume(self) -> str:
        line = self._current()
        self._advance()
        return line

    def parse(self) -> MfxFile:
        version, encoding = self._parse_header()
        meta = None
        trajectory = None
        events = None
        index = None
        extensions = []

        while True:
            line = self._current()
            if line is None:
                break
            if line.startswith('['):
                section_name = line[1:line.index(']')]
                self._advance()
                if section_name == 'meta':
                    meta = self._parse_meta()
                elif section_name == 'trajectory':
                    trajectory = self._parse_trajectory()
                elif section_name == 'events':
                    events = self._parse_events()
                elif section_name == 'index':
                    index = self._parse_index()
                elif section_name.startswith('x_'):
                    extensions.append(self._parse_extension(section_name))
                else:
                    self._skip_until_next_section()
            else:
                self._advance()

        if meta is None:
            raise ParseError("Missing [meta] section")
        if trajectory is None:
            raise ParseError("Missing [trajectory] section")

        return MfxFile(
            version=version,
            encoding=encoding,
            meta=meta,
            trajectory=trajectory,
            events=events,
            index=index,
            extensions=extensions,
        )

    def _parse_header(self) -> tuple[str, str]:
        line = self._consume()
        if not line or not line.startswith('@mfx'):
            raise ParseError(f"File must start with '@mfx <version>', got: {line!r}")
        parts = line.split()
        version = parts[1] if len(parts) > 1 else ''
        encoding = 'UTF-8'
        nxt = self._current()
        if nxt and nxt.startswith('@encoding'):
            encoding = nxt.split()[-1]
            self._advance()
        return version, encoding

    def _parse_kv_block(self) -> dict:
        """Read key : value pairs until the next section or EOF."""
        kv = {}
        while True:
            line = self._current()
            if line is None or line.startswith('[') or line.startswith('@'):
                break
            if ':' in line:
                key, _, val = line.partition(':')
                kv[key.strip()] = _parse_value(val.strip())
            self._advance()
        return kv

    def _parse_meta(self) -> Meta:
        kv = self._parse_kv_block()

        # Check required fields before popping any key
        required = ['id', 'drone_id', 'drone_type', 'pilot_id',
                    'date_start', 'status', 'application', 'location',
                    'sensors', 'data_level', 'license', 'contact']
        for r in required:
            if r not in kv:
                raise ParseError(f"Missing required field in [meta]: {r}")

        sensors = kv.pop('sensors', [])
        if isinstance(sensors, str):
            sensors = [sensors]

        known = {
            'id', 'drone_id', 'drone_type', 'manufacturer', 'pilot_id',
            'date_start', 'date_end', 'duration_s', 'status', 'application',
            'location', 'crs', 'altitude_ref', 'sensors', 'data_level',
            'processing_tools', 'producer', 'producer_version',
            'source_format', 'source_format_detail', 'license', 'contact',
            'pid', 'keywords'
        }
        extra = {k: v for k, v in kv.items() if k not in known}

        return Meta(
            id=kv['id'],
            drone_id=kv['drone_id'],
            drone_type=kv['drone_type'],
            manufacturer=kv.get('manufacturer'),
            pilot_id=kv['pilot_id'],
            date_start=kv['date_start'],
            date_end=kv.get('date_end'),
            duration_s=kv.get('duration_s'),
            status=kv['status'],
            application=kv['application'],
            location=kv['location'],
            crs=kv.get('crs', 'WGS84'),
            altitude_ref=kv.get('altitude_ref', 'MSL'),
            sensors=sensors,
            data_level=kv['data_level'],
            processing_tools=kv.get('processing_tools'),
            producer=kv.get('producer'),
            producer_version=kv.get('producer_version'),
            source_format=kv.get('source_format'),
            source_format_detail=kv.get('source_format_detail'),
            pid=kv.get('pid'),
            keywords=kv.get('keywords') if isinstance(kv.get('keywords'), list) else ([kv['keywords']] if kv.get('keywords') else None),
            license=kv['license'],
            contact=kv['contact'],
            extra=extra,
        )

    def _parse_trajectory(self) -> Trajectory:
        frequency_hz = None
        checksum = None
        schema_fields: list[SchemaField] = []
        raw_data_lines: list[str] = []
        points: list[TrajectoryPoint] = []

        while True:
            line = self._current()
            if line is None or line.startswith('['):
                break
            if line.startswith('frequency_hz'):
                _, _, val = line.partition(':')
                frequency_hz = float(val.strip())
                self._advance()
            elif line.startswith('@checksum'):
                checksum = line.split(None, 1)[1].strip()
                self._advance()
            elif line.startswith('@schema'):
                schema_str = line
                self._advance()
                while self._current() and '}' not in schema_str:
                    schema_str += ' ' + self._current()
                    self._advance()
                schema_fields = _parse_schema_line(schema_str)
            elif line == 'data[]:':
                self._advance()
                while True:
                    dl = self._current()
                    if dl is None or dl.startswith('[') or dl.startswith('@schema'):
                        break
                    raw_data_lines.append(dl)
                    self._advance()
            else:
                self._advance()

        for raw in raw_data_lines:
            values = [v.strip() for v in raw.split('|')]
            point = self._build_trajectory_point(values, schema_fields)
            points.append(point)

        return Trajectory(
            frequency_hz=frequency_hz,
            schema_fields=schema_fields,
            points=points,
            checksum=checksum,
            raw_lines=raw_data_lines,
        )

    def _build_trajectory_point(self, values: list[str], fields: list[SchemaField]) -> TrajectoryPoint:
        field_map = {f.name: _cast_field(v, f) for f, v in zip(fields, values)}
        extra = {k: v for k, v in field_map.items()
                 if k not in ('t', 'lat', 'lon', 'alt_m', 'speed_ms', 'heading', 'roll', 'pitch')}
        return TrajectoryPoint(
            t=field_map.get('t'),
            lat=field_map.get('lat'),
            lon=field_map.get('lon'),
            alt_m=field_map.get('alt_m'),
            speed_ms=field_map.get('speed_ms'),
            heading=field_map.get('heading'),
            roll=field_map.get('roll'),
            pitch=field_map.get('pitch'),
            extra=extra,
        )

    def _parse_events(self) -> Events:
        checksum = None
        schema_fields: list[SchemaField] = []
        raw_data_lines: list[str] = []
        events: list[Event] = []

        while True:
            line = self._current()
            if line is None or line.startswith('['):
                break
            if line.startswith('@checksum'):
                checksum = line.split(None, 1)[1].strip()
                self._advance()
            elif line.startswith('@schema'):
                schema_str = line
                self._advance()
                while self._current() and '}' not in schema_str:
                    schema_str += ' ' + self._current()
                    self._advance()
                schema_fields = _parse_schema_line(schema_str)
            elif line == 'data[]:':
                self._advance()
                while True:
                    dl = self._current()
                    if dl is None or dl.startswith('[') or dl.startswith('@schema'):
                        break
                    raw_data_lines.append(dl)
                    self._advance()
            else:
                self._advance()

        for raw in raw_data_lines:
            values = [v.strip() for v in raw.split('|')]
            field_map = {f.name: _cast_field(v, f) for f, v in zip(schema_fields, values)}
            extra = {k: v for k, v in field_map.items()
                     if k not in ('t', 'type', 'severity', 'detail')}
            events.append(Event(
                t=field_map.get('t'),
                type=field_map.get('type'),
                severity=field_map.get('severity'),
                detail=field_map.get('detail'),
                extra=extra,
            ))

        return Events(
            schema_fields=schema_fields,
            events=events,
            checksum=checksum,
            raw_lines=raw_data_lines,
        )

    def _parse_index(self) -> Index:
        kv = self._parse_kv_block()
        return Index(bbox=kv.get('bbox'), anomalies=kv.get('anomalies'))

    def _parse_extension(self, name: str) -> Extension:
        kv = self._parse_kv_block()
        return Extension(name=name, fields=kv)

    def _skip_until_next_section(self):
        while True:
            line = self._current()
            if line is None or line.startswith('['):
                break
            self._advance()


def parse(source: str | Path) -> MfxFile:
    """
    Parse a .mfx file from a file path or raw string.

    Args:
        source: path to the file (str or Path), or raw .mfx text content

    Returns:
        MfxFile — complete object representation of the file

    Raises:
        ParseError: if the file cannot be decoded as UTF-8 or has invalid content
    """
    if isinstance(source, Path):
        try:
            text = source.read_text(encoding='utf-8')
        except UnicodeDecodeError as exc:
            raise ParseError(f"File is not valid UTF-8: {source}") from exc
    elif isinstance(source, str):
        # Treat as a file path only when there are no newlines AND the path exists.
        # This avoids the fragile len<500 heuristic that could misinterpret long
        # paths as raw content or short raw content as a path.
        candidate = Path(source)
        if '\n' not in source and candidate.exists():
            try:
                text = candidate.read_text(encoding='utf-8')
            except UnicodeDecodeError as exc:
                raise ParseError(f"File is not valid UTF-8: {candidate}") from exc
        else:
            text = source
    else:
        raise TypeError(f"parse() expects str or Path, got {type(source).__name__!r}")
    return MfxParser(text).parse()
