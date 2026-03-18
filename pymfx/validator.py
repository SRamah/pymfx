"""
pymfx.validator — Validate a .mfx v1.0 file

Implements rules V01–V21 from the spec.
"""
from __future__ import annotations

import re
import uuid as _uuid_mod
from dataclasses import dataclass
from datetime import datetime

from .checksum import verify_checksum
from .models import MfxFile

# ---------------------------------------------------------------------------
# Validation result types
# ---------------------------------------------------------------------------

@dataclass
class ValidationIssue:
    rule: str        # e.g. "V01"
    severity: str    # "error" | "warning"
    message: str

    def __str__(self):
        return f"[{self.severity.upper()}] {self.rule}: {self.message}"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error"]

    @property
    def warnings(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "warning"]

    def __str__(self):
        if not self.issues:
            return "✓ Valid file — no issues found."
        lines = [str(i) for i in self.issues]
        status = "✓ Valid" if self.is_valid else "✗ Invalid"
        lines.append(f"\n{status} — {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

class MfxValidator:
    def __init__(self, mfx: MfxFile, raw_text: str | None = None):
        self.mfx = mfx
        self.raw_text = raw_text
        self.issues: list[ValidationIssue] = []

    def _err(self, rule: str, msg: str):
        self.issues.append(ValidationIssue(rule=rule, severity="error", message=msg))

    def _warn(self, rule: str, msg: str):
        self.issues.append(ValidationIssue(rule=rule, severity="warning", message=msg))

    def validate(self) -> ValidationResult:
        self._v01()
        self._v02()
        self._v03()
        self._v04()
        self._v05()
        self._v06()
        self._v07()
        self._v08()
        self._v09()
        self._v10()
        self._v11()
        self._v12()
        self._v13()
        self._v14()
        self._v15()
        self._v16()
        self._v17()
        self._v18()
        self._v19()
        self._v20()
        self._v21()
        self._v22()
        return ValidationResult(issues=self.issues)

    # V01 — File starts with @mfx + valid version
    def _v01(self):
        if not self.mfx.version:
            self._err("V01", "Missing or invalid @mfx version")
        elif not re.match(r'^\d+\.\d+$', self.mfx.version):
            self._err("V01", f"Invalid @mfx version: {self.mfx.version!r} (expected e.g. '1.0')")

    # V02 — [trajectory] checksum is correct
    def _v02(self):
        traj = self.mfx.trajectory
        if traj.checksum:
            if not verify_checksum(traj.raw_lines, traj.checksum):
                self._err("V02", f"[trajectory] checksum mismatch. Declared: {traj.checksum}")

    # V03 — [events] checksum is correct
    def _v03(self):
        ev = self.mfx.events
        if ev and ev.checksum:
            if not verify_checksum(ev.raw_lines, ev.checksum):
                self._err("V03", f"[events] checksum mismatch. Declared: {ev.checksum}")

    # V04 — [meta] present and required fields are non-empty
    def _v04(self):
        # Note: parser raises ParseError before MfxFile is built if [meta] is absent,
        # so mfx.meta is never None here. We use V04 to catch empty required fields.
        required_fields = [
            'id', 'drone_id', 'drone_type', 'pilot_id', 'date_start',
            'status', 'application', 'location', 'sensors', 'data_level', 'license', 'contact',
        ]
        meta = self.mfx.meta
        for fname in required_fields:
            val = getattr(meta, fname, None)
            if val is None or (isinstance(val, str) and not val.strip()) or (isinstance(val, list) and len(val) == 0):
                self._err("V04", f"Required [meta] field '{fname}' is empty or missing")

    # V05 — [trajectory] present
    def _v05(self):
        if self.mfx.trajectory is None:
            self._err("V05", "Missing [trajectory] section")

    # V06 — date_end present and after date_start if status=complete
    def _v06(self):
        meta = self.mfx.meta
        if meta.status == 'complete':
            if not meta.date_end:
                self._err("V06", "date_end is required when status=complete")
            else:
                try:
                    ds = datetime.fromisoformat(meta.date_start.replace('Z', '+00:00'))
                    de = datetime.fromisoformat(meta.date_end.replace('Z', '+00:00'))
                    if de <= ds:
                        self._err("V06", f"date_end ({meta.date_end}) must be after date_start ({meta.date_start})")
                except Exception as e:
                    self._err("V06", f"Cannot parse dates: {e}")

    # V07 — t is strictly increasing, max 3 decimal places
    def _v07(self):
        points = self.mfx.trajectory.points
        prev_t = None
        for i, p in enumerate(points):
            if p.t is None:
                self._err("V07", f"Point {i}: t is None (no_null)")
                continue
            t_str = str(p.t)
            if '.' in t_str:
                decimals = len(t_str.split('.')[1])
                if decimals > 3:
                    self._err("V07", f"Point {i}: t={p.t} has more than 3 decimal places")
            if prev_t is not None and p.t <= prev_t:
                self._err("V07", f"Point {i}: t={p.t} is not strictly increasing (previous: {prev_t})")
            prev_t = p.t

    # V08 — Field types conform to the defined vocabulary
    def _v08(self):
        valid_types = {'int', 'float', 'float32', 'bool', 'str', 'date',
                       'datetime', 'geo', 'uuid', 'bbox', 'list'}
        for f in self.mfx.trajectory.schema_fields:
            if f.type.lower() not in valid_types:
                self._err("V08", f"[trajectory] unknown type for field '{f.name}': {f.type!r}")
        if self.mfx.events:
            for f in self.mfx.events.schema_fields:
                if f.type.lower() not in valid_types:
                    self._err("V08", f"[events] unknown type for field '{f.name}': {f.type!r}")

    # V09 — Each data[] row has exactly as many values as schema fields
    def _v09(self):
        traj = self.mfx.trajectory
        n_fields = len(traj.schema_fields)
        for i, raw in enumerate(traj.raw_lines):
            n_vals = len(raw.split('|'))
            if n_vals != n_fields:
                self._err("V09", f"[trajectory] row {i+1}: {n_vals} values for {n_fields} fields")
        if self.mfx.events:
            ev = self.mfx.events
            n_fields = len(ev.schema_fields)
            for i, raw in enumerate(ev.raw_lines):
                n_vals = len(raw.split('|'))
                if n_vals != n_fields:
                    self._err("V09", f"[events] row {i+1}: {n_vals} values for {n_fields} fields")

    # V10 — [no_null] fields must not contain -
    def _v10(self):
        traj = self.mfx.trajectory
        no_null_fields = {f.name for f in traj.schema_fields if 'no_null' in f.constraints}
        field_names = [f.name for f in traj.schema_fields]
        for i, raw in enumerate(traj.raw_lines):
            values = [v.strip() for v in raw.split('|')]
            for fn in no_null_fields:
                if fn in field_names:
                    idx = field_names.index(fn)
                    if idx < len(values) and values[idx] == '-':
                        self._err("V10", f"[trajectory] row {i+1}: no_null field '{fn}' contains '-'")
        if self.mfx.events:
            ev = self.mfx.events
            no_null_fields = {f.name for f in ev.schema_fields if 'no_null' in f.constraints}
            field_names = [f.name for f in ev.schema_fields]
            for i, raw in enumerate(ev.raw_lines):
                values = [v.strip() for v in raw.split('|')]
                for fn in no_null_fields:
                    if fn in field_names:
                        idx = field_names.index(fn)
                        if idx < len(values) and values[idx] == '-':
                            self._err("V10", f"[events] row {i+1}: no_null field '{fn}' contains '-'")

    # V11 — [range] constraints respected
    def _v11(self):
        self._check_range_section(self.mfx.trajectory.schema_fields,
                                   self.mfx.trajectory.raw_lines, "[trajectory]")
        if self.mfx.events:
            self._check_range_section(self.mfx.events.schema_fields,
                                       self.mfx.events.raw_lines, "[events]")

    def _check_range_section(self, schema_fields, raw_lines, section_label):
        for f in schema_fields:
            range_c = next((c for c in f.constraints if c.startswith('range=')), None)
            if not range_c:
                continue
            m = re.match(r'range=(-?[\d.]+)\.\.(-?[\d.]+)', range_c)
            if not m:
                continue
            lo, hi = float(m.group(1)), float(m.group(2))
            field_names = [ff.name for ff in schema_fields]
            if f.name not in field_names:
                continue
            idx = field_names.index(f.name)
            for i, raw in enumerate(raw_lines):
                values = [v.strip() for v in raw.split('|')]
                if idx >= len(values) or values[idx] == '-':
                    continue
                try:
                    val = float(values[idx])
                    if not (lo <= val <= hi):
                        self._warn("V11", f"{section_label} row {i+1}: '{f.name}'={val} out of range [{lo}..{hi}]")
                except ValueError:
                    pass

    # V12 — [enum] constraints respected
    def _v12(self):
        self._check_enum_section(self.mfx.trajectory.schema_fields,
                                  self.mfx.trajectory.raw_lines, "[trajectory]")
        if self.mfx.events:
            self._check_enum_section(self.mfx.events.schema_fields,
                                      self.mfx.events.raw_lines, "[events]")

    def _check_enum_section(self, schema_fields, raw_lines, section_label):
        for f in schema_fields:
            enum_c = next((c for c in f.constraints if c.startswith('enum=')), None)
            if not enum_c:
                continue
            m = re.match(r'enum=\[([^\]]+)\]', enum_c)
            if not m:
                continue
            allowed = [v.strip() for v in m.group(1).split(',')]
            field_names = [ff.name for ff in schema_fields]
            if f.name not in field_names:
                continue
            idx = field_names.index(f.name)
            for i, raw in enumerate(raw_lines):
                values = [v.strip() for v in raw.split('|')]
                if idx >= len(values) or values[idx] == '-':
                    continue
                val = values[idx].strip('"')
                if val not in allowed:
                    self._warn("V12", f"{section_label} row {i+1}: '{f.name}'={val!r} not in {allowed}")

    # V13 — Extension sections are prefixed with x_
    def _v13(self):
        for ext in self.mfx.extensions:
            if not ext.name.startswith('x_'):
                self._warn("V13", f"Extension section not prefixed with 'x_': [{ext.name}]")

    # V14 — frequency_hz >= 1
    def _v14(self):
        hz = self.mfx.trajectory.frequency_hz
        if hz is not None and hz < 1:
            self._warn("V14", f"frequency_hz={hz} < 1 Hz (recommended >= 1)")

    # V15 — duration_s consistent with date_end - date_start (±5s)
    def _v15(self):
        meta = self.mfx.meta
        if meta.status != 'complete':
            return
        if meta.duration_s is None or not meta.date_end:
            return
        try:
            ds = datetime.fromisoformat(meta.date_start.replace('Z', '+00:00'))
            de = datetime.fromisoformat(meta.date_end.replace('Z', '+00:00'))
            computed = (de - ds).total_seconds()
            if abs(computed - meta.duration_s) > 5:
                self._warn("V15", f"duration_s={meta.duration_s} inconsistent with date_end - date_start = {computed:.0f}s (diff > 5s)")
        except Exception:
            pass

    # V16 — id is a valid RFC 4122 UUID
    def _v16(self):
        id_val = self.mfx.meta.id
        if isinstance(id_val, str) and id_val.startswith('uuid:'):
            id_str = id_val[5:]
            try:
                _uuid_mod.UUID(id_str, version=4)
            except ValueError:
                try:
                    _uuid_mod.UUID(id_str)
                except ValueError:
                    self._warn("V16", f"id is not a valid RFC 4122 UUID: {id_str!r}")
        else:
            self._warn("V16", f"id does not start with 'uuid:': {id_val!r}")

    # V17 — bbox contains all [trajectory] points
    def _v17(self):
        if self.mfx.index is None or self.mfx.index.bbox is None:
            return
        bbox = self.mfx.index.bbox
        if len(bbox) != 4:
            self._warn("V17", f"Malformed bbox: {bbox}")
            return
        lon_min, lat_min, lon_max, lat_max = bbox
        for i, p in enumerate(self.mfx.trajectory.points):
            if p.lat is None or p.lon is None:
                continue
            if not (lat_min <= p.lat <= lat_max and lon_min <= p.lon <= lon_max):
                self._warn("V17", f"Point {i} ({p.lat},{p.lon}) outside bbox {bbox}")

    # V18 — Gap between declared and measured frequency_hz <= 20%
    def _v18(self):
        traj = self.mfx.trajectory
        if traj.frequency_hz is None or len(traj.points) < 2:
            return
        if traj.frequency_hz <= 0:
            self._warn("V18", f"frequency_hz={traj.frequency_hz} is not positive (must be > 0)")
            return
        ts = [p.t for p in traj.points if p.t is not None]
        if len(ts) < 2:
            return
        total_time = ts[-1] - ts[0]
        if total_time <= 0:
            return
        measured_hz = (len(ts) - 1) / total_time
        declared_hz = traj.frequency_hz
        ratio = abs(measured_hz - declared_hz) / declared_hz
        if ratio > 0.20:
            self._warn("V18", f"frequency_hz declared={declared_hz} Hz, measured≈{measured_hz:.2f} Hz (gap {ratio*100:.0f}% > 20%)")

    # V19 — anomalies in [index] matches the actual count
    def _v19(self):
        if self.mfx.index is None or self.mfx.events is None:
            return
        if self.mfx.index.anomalies is None:
            return
        real_count = sum(
            1 for e in self.mfx.events.events
            if e.severity in ('warning', 'critical')
        )
        if self.mfx.index.anomalies != real_count:
            self._warn("V19", f"[index] anomalies={self.mfx.index.anomalies}, actual={real_count}")

    # V20 — source_format_detail present if source_format=other
    def _v20(self):
        meta = self.mfx.meta
        if meta.source_format == 'other' and not meta.source_format_detail:
            self._warn("V20", "source_format=other but source_format_detail is missing")

    # V22 — pid is a valid URI if present
    def _v22(self):
        pid = self.mfx.meta.pid
        if pid is None:
            return
        if not (pid.startswith('http://') or pid.startswith('https://')
                or pid.startswith('doi:') or pid.startswith('hdl:')
                or pid.startswith('ark:')):
            self._warn("V22", f"pid '{pid}' does not look like a valid URI (expected http/https/doi/hdl/ark)")

    # V21 — [index] is the last section if present
    def _v21(self):
        if self.raw_text and self.mfx.index:
            idx_pos = self.raw_text.rfind('[index]')
            after = self.raw_text[idx_pos + len('[index]'):]
            m = re.search(r'^\[(?!index\])\w', after, re.MULTILINE)
            if m:
                self._warn("V21", "[index] is not the last section of the file")


def validate(mfx: MfxFile, raw_text: str | None = None) -> ValidationResult:
    """
    Validate a MfxFile against rules V01–V21.

    Args:
        mfx: parsed MfxFile object
        raw_text: original raw text (optional, needed for V21)

    Returns:
        ValidationResult with the list of issues found
    """
    return MfxValidator(mfx, raw_text=raw_text).validate()
