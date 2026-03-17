# pymfx

Python library for the **Mission Flight Exchange** (`.mfx`) v1.0 format.

---

## Installation

```bash
pip install pymfx
pip install pymfx[viz]        # folium + matplotlib
pip install pymfx[ds]         # pandas
pip install pymfx[notebooks]  # all extras + jupyter
```

---

## Usage

### Parse / Write / Validate

```python
import pymfx

mfx = pymfx.parse("flight.mfx")
result = pymfx.validate(mfx)
pymfx.write(mfx, "out.mfx")
```

### Convert

```python
pymfx.convert.to_geojson(mfx)
pymfx.convert.to_gpx(mfx)
pymfx.convert.to_kml(mfx)
pymfx.convert.to_csv(mfx)
```

### Flight statistics

```python
stats = pymfx.flight_stats(mfx)
print(stats.duration_s, stats.total_distance_km, stats.alt_max_m)
print(stats)  # formatted table
```

### Data science

```python
df = mfx.trajectory.to_dataframe()
df = mfx.trajectory.to_dataframe(events=mfx.events)  # nearest-time merge
d  = mfx.to_dict()
js = mfx.to_json(indent=2)
```

### Visualization

```python
import pymfx.viz as viz

viz.trajectory_map(mfx)                          # folium map
viz.speed_heatmap(mfx)                           # coloured by speed
viz.compare_map([mfx1, mfx2], labels=[...])      # multiple flights

viz.flight_profile(mfx)                          # alt / speed / heading
viz.events_timeline(mfx)                         # horizontal timeline
viz.flight_3d(mfx, color_by="speed")             # 3-D lon / lat / alt
```

### Utilities

```python
mfx.index = pymfx.generate_index(mfx)           # auto-compute bbox + anomalies
combined  = pymfx.merge(leg1, leg2, gap_s=5.0)  # concatenate flights
result    = pymfx.diff(flight_a, flight_b)       # structured comparison
```

---

## CLI

```bash
pymfx flight.mfx --validate
pymfx flight.mfx --checksum
pymfx flight.mfx --info
pymfx flight.mfx --stats
pymfx flight.mfx --diff other.mfx
pymfx flight.mfx --export geojson
pymfx flight.mfx --export gpx -o flight.gpx
```

---

## Notebooks

| Notebook | Description |
|---|---|
| `01_quickstart.ipynb` | Parse, validate, write |
| `02_build_from_scratch.ipynb` | Build a `.mfx` file from Python |
| `03_visualization.ipynb` | `trajectory_map` · `flight_profile` · `events_timeline` |
| `04_convert.ipynb` | GeoJSON · GPX · KML · CSV |
| `05_stats_datascience.ipynb` | `flight_stats` · DataFrame · JSON |
| `06_viz_advanced.ipynb` | `speed_heatmap` · `compare_map` · `flight_3d` |
| `07_utils.ipynb` | `generate_index` · `merge` · `diff` |

```bash
pip install pymfx[notebooks]
jupyter notebook notebooks/
```

---

## Validation rules

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
│   ├── __init__.py
│   ├── models.py
│   ├── parser.py
│   ├── writer.py
│   ├── validator.py
│   ├── checksum.py
│   ├── stats.py
│   ├── utils.py
│   ├── cli.py
│   ├── convert/
│   └── viz/
├── notebooks/
└── tests/
```

---

## License

CC BY 4.0 — **Format spec:** `mfx_spec_v1.0_final.md` · **MIME:** `application/x-mfx`
