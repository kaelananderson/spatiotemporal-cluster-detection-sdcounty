"""
extract_satscan_all.py
-----------------------
Extracts all SaTScan cluster data from an HTML cluster map output and writes
three output files that are all linked by cluster_id:

    1. <stem>_clusters.csv          -- full metadata table (stats/R/Excel)
    2. <stem>_polygons.geojson      -- circular cluster polygons (ArcGIS)
    3. <stem>_centroids.geojson     -- cluster center points   (ArcGIS)

Usage:
    python extract_satscan_all.py <input.html> [output_stem]

    output_stem is optional. If omitted, the stem is taken from the input
    filename (e.g. "lgbm_second_run_clustermap.html" → "lgbm_second_run_clustermap").

Examples:
    python extract_satscan_all.py lgbm_second_run_clustermap.html
    python extract_satscan_all.py lgbm_second_run_clustermap.html second_run

Or edit the CONFIG block below and run directly in VS Code.
"""

import re
import html
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
INPUT_HTML   = "notebooks/satscan/cluster_extract/lgbm_second_run.clustermap.html"   
OUTPUT_STEM  = ""          # ← optional: leave "" to auto-derive from filename
N_VERTICES   = 64          # vertices used to approximate each circle polygon

# Parse command-line args (override config if provided)
if len(sys.argv) >= 2:
    INPUT_HTML = sys.argv[1]
if len(sys.argv) >= 3:
    OUTPUT_STEM = sys.argv[2]

# Derive output stem from input filename if not set
if not OUTPUT_STEM:
    OUTPUT_STEM = Path(INPUT_HTML).stem

OUTPUT_CSV      = f"{OUTPUT_STEM}_clusters.csv"
OUTPUT_POLYGONS = f"{OUTPUT_STEM}_polygons.geojson"
OUTPUT_CENTROIDS = f"{OUTPUT_STEM}_centroids.geojson"

# ── COLUMN ORDER for CSV ──────────────────────────────────────────────────────
COLUMN_ORDER = [
    # Identifiers
    "cluster_id",
    # Spatial — cluster definition
    "center_lat", "center_lng",
    "radius_m", "radius_km",
    # Temporal
    "start_date", "end_date",
    "start_year", "start_month",
    "end_year", "end_month",
    "duration_days", "duration_weeks",
    # Statistical
    "observed_cases", "expected_cases", "excess_cases",
    "obs_exp_ratio", "llr", "p_value",
    # Cluster flags
    "is_high_rate", "is_hierarchical", "is_gini",
    "slider_value",
    # Case-point derived geometry
    "n_case_points",
    "cases_centroid_lat", "cases_centroid_lng",
    "center_to_case_centroid_km",
    "cases_bbox_lat_min", "cases_bbox_lat_max",
    "cases_bbox_lng_min", "cases_bbox_lng_max",
    "cases_bbox_lat_span_km", "cases_bbox_lng_span_km",
]

# ── HELPERS ───────────────────────────────────────────────────────────────────

def decode_html(s: str) -> str:
    """Unescape HTML entities used in SaTScan tooltip strings."""
    s = s.replace("&#32;", " ").replace("&#47;", "/")
    s = s.replace("&#46;", ".").replace("&#45;", "-")
    return html.unescape(s)


def parse_date(s: str):
    try:
        return datetime.strptime(s.strip(), "%Y/%m/%d")
    except Exception:
        return None


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in km between two lat/lng points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def centroid(points: list) -> tuple:
    """Return mean (lat, lng) of a list of (lng, lat) tuples."""
    if not points:
        return (None, None)
    lats = [p[1] for p in points]
    lngs = [p[0] for p in points]
    return (sum(lats) / len(lats), sum(lngs) / len(lngs))


def make_circle_polygon(center_lat: float, center_lng: float,
                        radius_m: float, n: int = 64) -> list:
    """
    Return a closed list of [lng, lat] pairs forming a geodetically accurate
    circle polygon. Uses the haversine bearing-offset method so the shape is
    correct on the curved surface of the earth.
    """
    R = 6_371_000.0  # Earth radius in metres
    coords = []
    for i in range(n):
        bearing = 2 * math.pi * i / n      # radians, clockwise from north
        lat1 = math.radians(center_lat)
        lng1 = math.radians(center_lng)
        d_r  = radius_m / R                # angular distance

        lat2 = math.asin(
            math.sin(lat1) * math.cos(d_r) +
            math.cos(lat1) * math.sin(d_r) * math.cos(bearing)
        )
        lng2 = lng1 + math.atan2(
            math.sin(bearing) * math.sin(d_r) * math.cos(lat1),
            math.cos(d_r) - math.sin(lat1) * math.sin(lat2)
        )
        coords.append([math.degrees(lng2), math.degrees(lat2)])

    coords.append(coords[0])   # close the ring
    return coords


def extract_tip_fields(tip_html: str) -> dict:
    """Pull all statistical fields out of a decoded SaTScan tooltip string."""
    decoded = decode_html(tip_html)
    fields  = {}

    # Dates and duration
    tf = re.search(r'Time frame.*?(\d{4}/\d+/\d+)\s*to\s*(\d{4}/\d+/\d+)', decoded)
    if tf:
        fields["start_date"] = tf.group(1)
        fields["end_date"]   = tf.group(2)
        d1 = parse_date(tf.group(1))
        d2 = parse_date(tf.group(2))
        if d1 and d2:
            fields["duration_days"]  = (d2 - d1).days
            fields["duration_weeks"] = round((d2 - d1).days / 7, 2)
            fields["start_year"]     = d1.year
            fields["start_month"]    = d1.month
            fields["end_year"]       = d2.year
            fields["end_month"]      = d2.month
    else:
        for k in ("start_date", "end_date", "duration_days", "duration_weeks",
                  "start_year", "start_month", "end_year", "end_month"):
            fields[k] = None

    def grab(pattern):
        m = re.search(pattern, decoded)
        return m.group(1) if m else None

    raw_cases    = grab(r'Number of cases.*?(\d+)')
    raw_expected = grab(r'Expected cases.*?([\d.]+)')
    raw_ratio    = grab(r'Observed / expected.*?([\d.]+)')
    raw_llr      = grab(r'Test statistic.*?([\d.]+)')
    raw_pval     = grab(r'P-value.*?([\d.]+)')

    fields["observed_cases"] = int(raw_cases)       if raw_cases    else None
    fields["expected_cases"] = float(raw_expected)  if raw_expected else None
    fields["obs_exp_ratio"]  = float(raw_ratio)     if raw_ratio    else None
    fields["llr"]            = float(raw_llr)       if raw_llr      else None
    fields["p_value"]        = float(raw_pval)      if raw_pval     else None

    if fields["observed_cases"] and fields["expected_cases"]:
        fields["excess_cases"] = round(
            fields["observed_cases"] - fields["expected_cases"], 2
        )
    else:
        fields["excess_cases"] = None

    return fields


# ── CORE EXTRACTION ───────────────────────────────────────────────────────────

def extract_all(html_path: str) -> list:
    """
    Parse the HTML and return a list of dicts, one per cluster,
    containing every available field including derived geometry.
    """
    print(f"\nReading {html_path} ...")
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # 1. Core metadata (id, lat, lng, radius, flags)
    meta_pattern = re.compile(
        r'\{ id: (\d+), slider_value : ([\d.]+), highrate : (\w+), '
        r'lat : ([\d.\-]+), lng : ([\d.\-]+), radius : ([\d.]+), '
        r'hierarchical : (\w+), gini : (\w+)'
    )
    meta_rows = meta_pattern.findall(content)
    print(f"  Found {len(meta_rows)} clusters.")

    # 2. Tooltip strings (statistical fields)
    tips = re.findall(r"tip : '(.*?)', edges", content, re.DOTALL)

    # 3. Individual case point blocks
    point_blocks = re.split(r"points : \[", content)

    records = []
    for i, meta in enumerate(meta_rows):
        cid, slider, highrate, lat, lng, radius, hierarchical, gini = meta
        lat_f    = float(lat)
        lng_f    = float(lng)
        radius_f = float(radius)

        row = {
            "cluster_id":      int(cid),
            "center_lat":      lat_f,
            "center_lng":      lng_f,
            "radius_m":        radius_f,
            "radius_km":       round(radius_f / 1000, 5),
            "is_high_rate":    highrate    == "true",
            "is_hierarchical": hierarchical == "true",
            "is_gini":         gini        == "true",
            "slider_value":    float(slider),
        }

        # Statistical fields from tooltip
        if i < len(tips):
            row.update(extract_tip_fields(tips[i]))

        # Case-point derived fields
        if i + 1 < len(point_blocks):
            block_text = point_blocks[i + 1].split("]}", 1)[0]
            pts = re.findall(r'\[([\d.\-]+),\s*([\d.\-]+)\]', block_text)
            pts = [(float(x), float(y)) for x, y in pts]   # (lng, lat)
            row["n_case_points"] = len(pts)

            if pts:
                c_lat, c_lng = centroid(pts)
                row["cases_centroid_lat"] = round(c_lat, 6)
                row["cases_centroid_lng"] = round(c_lng, 6)
                row["center_to_case_centroid_km"] = round(
                    haversine_km(lat_f, lng_f, c_lat, c_lng), 4
                )
                lats = [p[1] for p in pts]
                lngs = [p[0] for p in pts]
                row["cases_bbox_lat_min"]    = round(min(lats), 6)
                row["cases_bbox_lat_max"]    = round(max(lats), 6)
                row["cases_bbox_lng_min"]    = round(min(lngs), 6)
                row["cases_bbox_lng_max"]    = round(max(lngs), 6)
                row["cases_bbox_lat_span_km"] = round(
                    haversine_km(min(lats), lng_f, max(lats), lng_f), 4
                )
                row["cases_bbox_lng_span_km"] = round(
                    haversine_km(lat_f, min(lngs), lat_f, max(lngs)), 4
                )
            else:
                for k in ("cases_centroid_lat", "cases_centroid_lng",
                          "center_to_case_centroid_km", "cases_bbox_lat_min",
                          "cases_bbox_lat_max", "cases_bbox_lng_min",
                          "cases_bbox_lng_max", "cases_bbox_lat_span_km",
                          "cases_bbox_lng_span_km"):
                    row[k] = None
        else:
            row["n_case_points"] = None

        records.append(row)

    return records


# ── WRITERS ───────────────────────────────────────────────────────────────────

def write_csv(records: list, out_path: str):
    """Write full metadata table to CSV."""
    for r in records:
        for col in COLUMN_ORDER:
            r.setdefault(col, None)

    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMN_ORDER, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

    print(f"  ✓ CSV        → {out_path}  ({len(records)} rows, {len(COLUMN_ORDER)} columns)")


def build_properties(row: dict) -> dict:
    """
    Shared property block for both GeoJSON outputs.
    Keeps every field except the raw case-point bbox details
    (those are spatial metadata more useful in the CSV).
    """
    keep = [
        "cluster_id",
        "center_lat", "center_lng",
        "radius_m", "radius_km",
        "start_date", "end_date",
        "start_year", "start_month",
        "end_year", "end_month",
        "duration_days", "duration_weeks",
        "observed_cases", "expected_cases", "excess_cases",
        "obs_exp_ratio", "llr", "p_value",
        "is_high_rate", "is_hierarchical", "is_gini",
        "slider_value",
        "n_case_points",
        "cases_centroid_lat", "cases_centroid_lng",
        "center_to_case_centroid_km",
    ]
    return {k: row.get(k) for k in keep}


def write_polygons_geojson(records: list, out_path: str, n_vertices: int = 64):
    """Write cluster circles as GeoJSON Polygon features."""
    features = []
    for row in records:
        ring = make_circle_polygon(
            row["center_lat"], row["center_lng"],
            row["radius_m"], n=n_vertices
        )
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [ring]
            },
            "properties": build_properties(row)
        })

    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    print(f"  ✓ Polygons   → {out_path}  ({len(features)} features, {n_vertices} vertices/circle)")


def write_centroids_geojson(records: list, out_path: str):
    """Write cluster centers as GeoJSON Point features."""
    features = []
    for row in records:
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [row["center_lng"], row["center_lat"]]
            },
            "properties": build_properties(row)
        })

    geojson = {"type": "FeatureCollection", "features": features}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(geojson, f, indent=2)

    print(f"  ✓ Centroids  → {out_path}  ({len(features)} features)")


# ── ENTRY POINT ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    records = extract_all(INPUT_HTML)

    print(f"\nWriting output files (stem: '{OUTPUT_STEM}') ...")
    write_csv(records,              OUTPUT_CSV)
    write_polygons_geojson(records, OUTPUT_POLYGONS, n_vertices=N_VERTICES)
    write_centroids_geojson(records, OUTPUT_CENTROIDS)

    print(f"""
All done. Three files written:
  {OUTPUT_CSV}
  {OUTPUT_POLYGONS}
  {OUTPUT_CENTROIDS}

All files share 'cluster_id' as the common key.
""")