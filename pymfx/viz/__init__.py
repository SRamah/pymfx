"""
pymfx.viz — Optional visualization module for .mfx files

Requires: folium, matplotlib
Install:  pip install pymfx[viz]

Functions:
    trajectory_map(mfx)          → folium.Map  — interactive GPS trace (green→red gradient)
    speed_heatmap(mfx)           → folium.Map  — trajectory coloured by speed
    compare_map([mfx1, mfx2])    → folium.Map  — multiple flights on the same map
    flight_profile(mfx)          → matplotlib Figure — altitude / speed / heading over time
    flight_3d(mfx)               → matplotlib Figure — 3-D lat/lon/alt trajectory
    events_timeline(mfx)         → matplotlib Figure — events on the flight timeline
"""

from .map import compare_map, speed_heatmap, trajectory_map
from .profile import flight_profile
from .timeline import events_timeline
from .trajectory_3d import flight_3d

__all__ = [
    "trajectory_map",
    "speed_heatmap",
    "compare_map",
    "flight_profile",
    "flight_3d",
    "events_timeline",
]
