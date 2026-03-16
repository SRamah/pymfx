# pymfx

Python reference library for the **Mission Flight Exchange** (`.mfx`) v1.0 format.

> `.mfx` is an open, text-based, self-describing format for encapsulating UAV mission data in a single file.  
> It is to drone missions what GPX is to GPS tracks: a minimal, immediately adoptable, community-extensible standard.

---

## Installation

```bash
pip install pymfx
```

Or from source:

```bash
git clone https://github.com/pymfx/pymfx
cd pymfx
pip install -e .
```

**Requirements:** Python ≥ 3.10, no external dependencies.

---

## Quick start

```python
import pymfx

# Read a file
mfx = pymfx.parse("mission.mfx")

print(mfx.meta.drone_id)            # "Parrot-Anafi-SN987654"
print(mfx.meta.date_start)          # "2026-03-16T08:30:00Z"
print(len(mfx.trajectory.points))   # 3

for point in mfx.trajectory.points:
    print(point.t, point.lat, point.lon, point.alt_m)

# Validate
result = pymfx.validate(mfx)
if result.is_valid:
    print("✓ Valid file")
else:
    for issue in result.issues:
        print(issue)

# Write (checksums are auto-computed)
mfx.meta.contact = "new@lab.fr"
pymfx.write(mfx, "mission_v2.mfx")
```

---

## CLI

```bash
# Validate a file (rules V01–V21)
pymfx --validate mission.mfx

# Compute and verify SHA-256 checksums
pymfx --checksum mission.mfx

# Print a summary
pymfx --info mission.mfx
```

---

## Notebooks

Two Jupyter notebooks are included in `notebooks/`:

| Notebook | Description |
|---|---|
| `01_quickstart.ipynb` | Parse, inspect, validate and write a .mfx file step by step |
| `02_build_from_scratch.ipynb` | Build a complete .mfx file from raw Python data |

To run them:

```bash
pip install jupyter
jupyter notebook notebooks/
```

---

## Validation rules

The validator implements all 21 rules from the `.mfx` v1.0 spec:

| ID | Severity | Description |
|----|----------|-------------|
| V01 | Error | Valid @mfx version |
| V02 | Error | [trajectory] checksum correct |
| V03 | Error | [events] checksum correct |
| V04 | Error | [meta] present and in first position |
| V05 | Error | [trajectory] present |
| V06 | Error | date_end present and after date_start if status=complete |
| V07 | Error | t strictly increasing, max 3 decimal places |
| V08 | Error | Field types conform to the defined vocabulary |
| V09 | Error | Number of values per row equals number of schema fields |
| V10 | Error | [no_null] fields do not contain `-` |
| V11 | Warning | [range] constraints respected |
| V12 | Warning | [enum] constraints respected |
| V13 | Warning | Extension sections prefixed with `x_` |
| V14 | Warning | frequency_hz ≥ 1 |
| V15 | Warning | duration_s consistent with date_end − date_start (±5s) |
| V16 | Warning | id is a valid RFC 4122 UUID |
| V17 | Warning | bbox contains all [trajectory] points |
| V18 | Warning | Gap between declared and measured frequency_hz ≤ 20% |
| V19 | Warning | anomalies in [index] matches actual count |
| V20 | Warning | source_format_detail present if source_format=other |
| V21 | Warning | [index] is the last section |

---

## Package structure

```
pymfx/
├── pymfx/
│   ├── __init__.py      Public API
│   ├── models.py        Dataclasses (MfxFile, Meta, Trajectory, ...)
│   ├── parser.py        Read .mfx → Python objects
│   ├── writer.py        Python objects → .mfx
│   ├── validator.py     Rules V01–V21
│   ├── checksum.py      SHA-256 per spec
│   └── cli.py           CLI interface
├── notebooks/
│   ├── 01_quickstart.ipynb
│   └── 02_build_from_scratch.ipynb
└── tests/
    ├── example_minimal.mfx
    ├── test_parser.py
    ├── test_writer.py
    └── test_validator.py
```

---

## License

CC BY 4.0 — See the `.mfx` v1.0 specification for details.

**Format spec:** `mfx_spec_v1.0_final.md`  
**MIME type:** `application/x-mfx`  
**Reference implementation:** `pymfx` — `github.com/jabahm/pymfx`
