# pymfx

[![CI](https://github.com/jabahm/pymfx/actions/workflows/ci.yml/badge.svg)](https://github.com/jabahm/pymfx/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/pymfx)](https://pypi.org/project/pymfx/)
[![Coverage](https://codecov.io/gh/jabahm/pymfx/branch/main/graph/badge.svg)](https://codecov.io/gh/jabahm/pymfx)
[![Docs](https://img.shields.io/badge/docs-jabahm.github.io/pymfx-blue)](https://jabahm.github.io/pymfx)
[![mfx-ready](https://img.shields.io/badge/format-.mfx%201.0-blue)](https://github.com/jabahm/pymfx)

Python library for the **Mission Flight Exchange** (`.mfx`) format — an open plain-text format for UAV mission data built for [FAIR](https://www.go-fair.org/fair-principles/) compliance.

```bash
pip install pymfx          # core (zero dependencies)
pip install pymfx[viz]     # + folium maps & matplotlib plots
pip install pymfx[ds]      # + pandas DataFrame integration
```

---

## What it does

```python
import pymfx

# Parse
mfx = pymfx.parse("flight.mfx")

# Validate — 22 rules (V01-V22)
result = pymfx.validate(mfx)
print(result)
# ✓ Valid file - no issues found.

# Stats
print(pymfx.flight_stats(mfx))
# ┌──────────────────────────────────────────┐
# │  Flight Statistics                       │
# ├──────────────────────────────────────────┤
# │  Points        : 1024                   │
# │  Duration      : 312.5 s               │
# │  Distance      : 4821.33 m             │
# ├──────────────────────────────────────────┤
# │  Alt max       : 87.3 m               │
# │  Speed mean    : 8.7 m/s              │
# └──────────────────────────────────────────┘

# FAIR score
score = pymfx.fair_score(mfx)
print(f"S = {score.S:.2f}  (F={score.F:.2f} A={score.A:.2f} I={score.interop:.2f} R={score.R:.2f})")
# S = 0.88  (F=0.88 A=1.00 I=0.75 R=0.88)
print(score.breakdown())

# Write (auto-computes SHA-256 checksums)
pymfx.write(mfx, "out.mfx")
```

---

## Convert

```python
# Import from drone manufacturer formats
mfx = pymfx.convert.from_dji_csv("DJIFlightRecord.csv")   # AirData or DJI Fly
mfx = pymfx.convert.from_gpx("track.gpx")
mfx = pymfx.convert.from_geojson("route.geojson")

# Export to standard formats
pymfx.convert.to_geojson(mfx)   # → GeoJSON FeatureCollection
pymfx.convert.to_gpx(mfx)       # → GPX 1.1
pymfx.convert.to_kml(mfx)       # → KML (Google Earth)
pymfx.convert.to_csv(mfx)       # → CSV
```

---

## Visualize

```python
import pymfx.viz as viz

viz.trajectory_map(mfx)          # interactive folium map (green → red gradient)
viz.speed_heatmap(mfx)           # map coloured by speed
viz.compare_map([mfx1, mfx2])   # multi-flight overlay
viz.flight_profile(mfx)          # altitude / speed / heading over time
viz.flight_3d(mfx)               # 3-D lat/lon/alt trajectory
viz.events_timeline(mfx)         # events on the flight timeline
```

---

## DataFrame

```python
df = mfx.trajectory.to_dataframe(events=mfx.events)
# t      lat       lon       alt_m   speed_ms  event_type
# 0.000  48.8566   2.3522    52.1    3.2       NaN
# 1.000  48.8567   2.3523    54.3    4.1       NaN
# 2.000  48.8568   2.3524    57.0    5.3       photo
```

---

## CLI

```bash
pymfx flight.mfx --validate        # check V01-V22
pymfx flight.mfx --info            # summary
pymfx flight.mfx --stats           # flight statistics
pymfx flight.mfx --checksum        # verify SHA-256
pymfx flight.mfx --diff other.mfx  # compare two flights
pymfx flight.mfx --export geojson -o out.geojson
```

---

## The .mfx format

Plain text, structured sections, human-readable:

```
@mfx 1.0
@encoding UTF-8

[meta]
id            : uuid:f47ac10b-58cc-4372-a567-0e02b2c3d479
drone_id      : drone:DJI-Mini3-SN8273
drone_type    : multirotor
pilot_id      : pilot:ahmed-jabrane
date_start    : 2024-06-15T08:30:00Z
date_end      : 2024-06-15T08:35:12Z
status        : complete
application   : environmental-monitoring
location      : Parc de Sceaux, FR
sensors       : [rgb-camera, thermal]
data_level    : raw
license       : CC-BY-4.0
contact       : ahmed@example.org

[trajectory]
frequency_hz  : 1.0
@checksum sha256:a3f2...
@schema point: t:float[no_null] lat:float[no_null,range=-90..90] lon:float[no_null,range=-180..180] alt_m:float speed_ms:float heading:float
data[]:
0.000 | 48.7733 | 2.2858 | 52.1 | 3.2 | 182.0
1.000 | 48.7734 | 2.2859 | 54.3 | 4.1 | 183.0
...

[index]
bbox      : (2.2858, 48.7733, 2.2901, 48.7751)
anomalies : 0
```

---

## License

MIT · Format spec: CC BY 4.0
