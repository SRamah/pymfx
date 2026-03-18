"""
pymfx.writer — Serialize a MfxFile object to .mfx v1.0 text format
"""
from __future__ import annotations

from pathlib import Path

from .checksum import compute_checksum
from .models import Events, Extension, MfxFile, SchemaField, Trajectory

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_value(v) -> str:
    """Format a Python value as a .mfx string."""
    if v is None:
        return '-'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, list):
        return '[' + ', '.join(str(x) for x in v) + ']'
    if isinstance(v, tuple):
        return '(' + ','.join(str(x) for x in v) + ')'
    if isinstance(v, str) and ('|' in v or ' ' in v):
        return f'"{v}"'
    return str(v)


def _fmt_schema_field(f: SchemaField) -> str:
    """Format a SchemaField as a declaration string."""
    s = f"{f.name}:{f.type}"
    if f.constraints:
        for c in f.constraints:
            s += f" [{c}]"
    return s


# ---------------------------------------------------------------------------
# Writer
# ---------------------------------------------------------------------------

class MfxWriter:
    def __init__(self, mfx: MfxFile, compute_checksums: bool = True):
        self.mfx = mfx
        self.compute_checksums = compute_checksums

    def write(self) -> str:
        parts = []
        parts.append(self._write_header())
        parts.append(self._write_meta())
        parts.append(self._write_trajectory())
        if self.mfx.events:
            parts.append(self._write_events())
        for ext in self.mfx.extensions:
            parts.append(self._write_extension(ext))
        if self.mfx.index:
            parts.append(self._write_index())
        return "\n".join(parts) + "\n"

    def _write_header(self) -> str:
        return f"@mfx {self.mfx.version}\n@encoding {self.mfx.encoding}"

    def _write_meta(self) -> str:
        m = self.mfx.meta
        lines = ["", "[meta]"]

        def kv(key: str, val, pad=20):
            if val is None:
                return
            lines.append(f"{key:<{pad}} : {_fmt_value(val)}")

        kv("id", m.id)
        kv("drone_id", m.drone_id)
        kv("drone_type", m.drone_type)
        if m.manufacturer:
            kv("manufacturer", m.manufacturer)
        kv("pilot_id", m.pilot_id)
        kv("date_start", m.date_start)
        if m.date_end:
            kv("date_end", m.date_end)
        if m.duration_s is not None:
            kv("duration_s", m.duration_s)
        kv("status", m.status)
        kv("application", m.application)
        kv("location", m.location)
        kv("crs", m.crs)
        kv("altitude_ref", m.altitude_ref)
        kv("sensors", m.sensors)
        kv("data_level", m.data_level)
        if m.processing_tools:
            kv("processing_tools", m.processing_tools)
        if m.producer:
            kv("producer", m.producer)
        if m.producer_version:
            kv("producer_version", m.producer_version)
        if m.source_format:
            kv("source_format", m.source_format)
        if m.source_format_detail:
            kv("source_format_detail", m.source_format_detail)
        if m.pid:
            kv("pid", m.pid)
        if m.keywords:
            kv("keywords", m.keywords)
        kv("license", m.license)
        kv("contact", m.contact)
        for k, v in m.extra.items():
            kv(k, v)

        return "\n".join(lines)

    def _write_trajectory(self) -> str:
        t = self.mfx.trajectory
        lines = ["", "[trajectory]"]
        if t.frequency_hz is not None:
            lines.append(f"frequency_hz : {t.frequency_hz}")

        data_lines = self._build_trajectory_data_lines(t)

        if self.compute_checksums:
            lines.append(f"@checksum {compute_checksum(data_lines)}")

        if t.schema_fields:
            field_strs = ", ".join(_fmt_schema_field(f) for f in t.schema_fields)
            lines.append(f"@schema point: {{{field_strs}}}")
        lines.append("")
        lines.append("data[]:")
        lines.extend(data_lines)

        return "\n".join(lines)

    def _build_trajectory_data_lines(self, t: Trajectory) -> list[str]:
        if t.raw_lines:
            return list(t.raw_lines)
        field_names = [f.name for f in t.schema_fields]
        rows = []
        for p in t.points:
            vals = []
            for fn in field_names:
                if fn == 't':
                    vals.append(f"{p.t:.3f}" if p.t is not None else '-')
                elif fn == 'lat':
                    vals.append(str(p.lat) if p.lat is not None else '-')
                elif fn == 'lon':
                    vals.append(str(p.lon) if p.lon is not None else '-')
                elif fn == 'alt_m':
                    vals.append(str(p.alt_m) if p.alt_m is not None else '-')
                elif fn == 'speed_ms':
                    vals.append(str(p.speed_ms) if p.speed_ms is not None else '-')
                elif fn == 'heading':
                    vals.append(str(p.heading) if p.heading is not None else '-')
                elif fn == 'roll':
                    vals.append(str(p.roll) if p.roll is not None else '-')
                elif fn == 'pitch':
                    vals.append(str(p.pitch) if p.pitch is not None else '-')
                else:
                    vals.append(str(p.extra.get(fn, '-')))
            rows.append(" | ".join(vals))
        return rows

    def _write_events(self) -> str:
        ev = self.mfx.events
        lines = ["", "[events]"]

        data_lines = self._build_events_data_lines(ev)

        if self.compute_checksums:
            lines.append(f"@checksum {compute_checksum(data_lines)}")

        if ev.schema_fields:
            field_strs = ", ".join(_fmt_schema_field(f) for f in ev.schema_fields)
            lines.append(f"@schema event: {{{field_strs}}}")
        lines.append("")
        lines.append("data[]:")
        lines.extend(data_lines)

        return "\n".join(lines)

    def _build_events_data_lines(self, ev: Events) -> list[str]:
        if ev.raw_lines:
            return list(ev.raw_lines)
        field_names = [f.name for f in ev.schema_fields]
        rows = []
        for e in ev.events:
            vals = []
            for fn in field_names:
                if fn == 't':
                    vals.append(f"{e.t:.3f}" if e.t is not None else '-')
                elif fn == 'type':
                    vals.append(e.type if e.type is not None else '-')
                elif fn == 'severity':
                    vals.append(e.severity if e.severity is not None else '-')
                elif fn == 'detail':
                    v = e.detail if e.detail is not None else '-'
                    vals.append(f'"{v}"' if ' ' in str(v) else str(v))
                else:
                    vals.append(str(e.extra.get(fn, '-')))
            rows.append(" | ".join(vals))
        return rows

    def _write_index(self) -> str:
        idx = self.mfx.index
        lines = ["", "[index]"]
        if idx.bbox is not None:
            bbox_str = "(" + ",".join(str(v) for v in idx.bbox) + ")"
            lines.append(f"bbox      : {bbox_str}")
        if idx.anomalies is not None:
            lines.append(f"anomalies : {idx.anomalies}")
        return "\n".join(lines)

    def _write_extension(self, ext: Extension) -> str:
        lines = ["", f"[{ext.name}]"]
        for k, v in ext.fields.items():
            lines.append(f"{k:<20} : {_fmt_value(v)}")
        return "\n".join(lines)


def write(mfx: MfxFile, dest: str | Path | None = None,
          compute_checksums: bool = True) -> str:
    """
    Serialize a MfxFile to .mfx text format.

    Args:
        mfx: the MfxFile object to serialize
        dest: optional output path (if provided, writes the file)
        compute_checksums: recompute SHA-256 checksums (recommended)

    Returns:
        The .mfx file content as a string
    """
    text = MfxWriter(mfx, compute_checksums=compute_checksums).write()
    if dest:
        Path(dest).write_text(text, encoding='utf-8')
    return text
