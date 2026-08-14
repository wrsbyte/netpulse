"""Coarse geolocation for the route map.

Airport (IATA) coordinates for the CDN POPs we detect, and country centroids as a fallback.
Deliberately coarse: the map renders *approximate* positions with honest uncertainty (POP =
airport-precise; country-only = centroid), never a false-precision pin for an unlocatable hop.
Pure lookups, unit-tested.
"""

from __future__ import annotations

# IATA airport -> (lat, lon) for the POPs in the anycast table.
IATA_LATLON: dict[str, tuple[float, float]] = {
    "QRO": (20.62, -100.19), "MEX": (19.44, -99.07), "GDL": (20.52, -103.31),
    "DFW": (32.90, -97.04), "MIA": (25.79, -80.29), "IAH": (29.98, -95.34),
    "LAX": (33.94, -118.41), "ATL": (33.64, -84.43), "IAD": (38.94, -77.46),
    "EWR": (40.69, -74.17), "SJC": (37.36, -121.93), "ORD": (41.98, -87.90),
    "DEN": (39.86, -104.67), "SEA": (47.45, -122.31), "PHX": (33.43, -112.01),
    "BOG": (4.70, -74.15), "GRU": (-23.43, -46.47), "GIG": (-22.81, -43.25),
    "EZE": (-34.82, -58.54), "SCL": (-33.39, -70.79), "LIM": (-12.02, -77.11),
    "PTY": (9.07, -79.38), "UIO": (-0.13, -78.36), "SJO": (9.99, -84.20),
    "GUA": (14.58, -90.53), "MDE": (6.16, -75.42), "LHR": (51.47, -0.45),
    "CDG": (49.01, 2.55), "FRA": (50.03, 8.57), "AMS": (52.31, 4.76), "MAD": (40.47, -3.56),
}

COUNTRY_CENTROID: dict[str, tuple[float, float]] = {
    "MX": (23.63, -102.55), "US": (39.83, -98.58), "CO": (4.57, -74.30), "BR": (-14.24, -51.93),
    "AR": (-38.42, -63.62), "CL": (-35.68, -71.54), "PE": (-9.19, -75.02), "GB": (55.38, -3.44),
    "FR": (46.23, 2.21), "DE": (51.17, 10.45), "ES": (40.46, -3.75), "NL": (52.13, 5.29),
}


def locate_colo(colo: str | None) -> tuple[float, float] | None:
    return IATA_LATLON.get(colo) if colo else None


def locate_country(cc: str | None) -> tuple[float, float] | None:
    return COUNTRY_CENTROID.get(cc) if cc else None
