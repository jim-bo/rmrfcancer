#!/usr/bin/env python3
"""
Fetch property and street characteristics from Brookline, MA public GIS data.

Data sources:
  - MassGIS L3 Parcel+Assessor FeatureServer (primary, richest assessor data)
  - Brookline ArcGIS Server (gisweb.brooklinema.gov) for street edges & buildings
  - Brookline local parcel data (fallback / supplemental owner info)

Usage:
  python brookline_gis.py "White Place"
  python brookline_gis.py --street "White Pl"
  python brookline_gis.py --address "10 White Pl"
  python brookline_gis.py --parcel-id "217-02-00"
  python brookline_gis.py --discover
"""

import argparse
import json
import sys

import requests

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# MassGIS Level 3 Parcels + Assessor data (statewide, best assessor fields)
MASSGIS_PARCELS_URL = (
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services"
    "/L3_TAXPAR_POLY_ASSESS_gdb/FeatureServer"
)
MASSGIS_PARCELS_LAYER = 0
BROOKLINE_TOWN_ID = 46

# Brookline local ArcGIS server
BROOKLINE_BASE = "https://gisweb.brooklinema.gov/arcgis/rest/services"
BROOKLINE_PARCELS_URL = f"{BROOKLINE_BASE}/GPV/gpvdefault/MapServer"
BROOKLINE_PARCELS_LAYER = 3
ACCELA_URL = f"{BROOKLINE_BASE}/Accela/MapServer"
ACCELA_STREET_EDGES_LAYER = 7
ACCELA_BUILDINGS_LAYER = 4

# MassGIS/MassDOT Roads (statewide road centerlines)
MASSDOT_ROADS_URL = (
    "https://services1.arcgis.com/hGdibHYSPO59RG1h/arcgis/rest/services"
    "/MassGIS-MassDOT_Roads/FeatureServer"
)
MASSDOT_ROADS_LAYER = 0

# Approximate bounding box for Brookline, MA (WGS84)
BROOKLINE_BBOX = "-71.18,42.31,-71.10,42.35"

TIMEOUT = 30


# ---------------------------------------------------------------------------
# Generic ArcGIS query helpers
# ---------------------------------------------------------------------------

def query_layer(service_url, layer_id, where_clause, out_fields="*",
                return_geometry=False, extra_params=None):
    """Query an ArcGIS REST layer and return features."""
    url = f"{service_url}/{layer_id}/query"
    params = {
        "where": where_clause,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "f": "json",
    }
    if extra_params:
        params.update(extra_params)

    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        msg = data["error"].get("message", data["error"])
        raise RuntimeError(f"ArcGIS error: {msg}")

    return data.get("features", [])


def get_layer_fields(service_url, layer_id):
    """Fetch field definitions for a layer."""
    url = f"{service_url}/{layer_id}"
    resp = requests.get(url, params={"f": "json"}, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("fields", [])


# ---------------------------------------------------------------------------
# MassGIS parcel queries (primary – richest assessor data)
# ---------------------------------------------------------------------------

def massgis_parcels_by_street(street_name):
    """All Brookline parcels whose FULL_STR contains the given name."""
    where = f"TOWN_ID={BROOKLINE_TOWN_ID} AND UPPER(FULL_STR) LIKE '%{street_name.upper()}%'"
    return query_layer(MASSGIS_PARCELS_URL, MASSGIS_PARCELS_LAYER, where)


def massgis_parcels_by_address(street_number, street_name):
    """Brookline parcel at a specific address."""
    where = (
        f"TOWN_ID={BROOKLINE_TOWN_ID} AND "
        f"ADDR_NUM='{street_number}' AND "
        f"UPPER(FULL_STR) LIKE '%{street_name.upper()}%'"
    )
    return query_layer(MASSGIS_PARCELS_URL, MASSGIS_PARCELS_LAYER, where)


def massgis_parcels_by_loc_id(loc_id):
    """Brookline parcel by LOC_ID (MassGIS unique parcel identifier)."""
    where = f"LOC_ID='{loc_id}'"
    return query_layer(MASSGIS_PARCELS_URL, MASSGIS_PARCELS_LAYER, where)


# ---------------------------------------------------------------------------
# Brookline local parcel queries (fallback / supplemental)
# ---------------------------------------------------------------------------

def brookline_parcels_by_street(street_name):
    where = f"UPPER(PAR_ADD_ST_1) LIKE '%{street_name.upper()}%'"
    return query_layer(BROOKLINE_PARCELS_URL, BROOKLINE_PARCELS_LAYER, where)


def brookline_parcels_by_address(street_number, street_name):
    where = (
        f"PAR_ADD_NO_1={street_number} AND "
        f"UPPER(PAR_ADD_ST_1) LIKE '%{street_name.upper()}%'"
    )
    return query_layer(BROOKLINE_PARCELS_URL, BROOKLINE_PARCELS_LAYER, where)


def brookline_parcels_by_id(parcel_id):
    where = f"PARCEL_ID='{parcel_id}'"
    return query_layer(BROOKLINE_PARCELS_URL, BROOKLINE_PARCELS_LAYER, where)


# ---------------------------------------------------------------------------
# Street / road queries
# ---------------------------------------------------------------------------

def brookline_street_edges(street_name):
    """Street edge segments from the local Brookline Accela service."""
    where = f"UPPER(STREETNAME) LIKE '%{street_name.upper()}%'"
    return query_layer(ACCELA_URL, ACCELA_STREET_EDGES_LAYER, where)


def massdot_roads_in_brookline(street_name):
    """MassDOT road centerlines within Brookline's bounding box."""
    where = f"UPPER(STREETNAME) LIKE '%{street_name.upper()}%'"
    extra = {
        "geometry": BROOKLINE_BBOX,
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }
    return query_layer(MASSDOT_ROADS_URL, MASSDOT_ROADS_LAYER, where,
                       extra_params=extra)


# ---------------------------------------------------------------------------
# Display formatting
# ---------------------------------------------------------------------------

def format_massgis_parcel(feature):
    """Format a MassGIS L3 parcel feature for display."""
    a = feature.get("attributes", {})
    lines = []

    site_addr = a.get("SITE_ADDR", "")
    if site_addr:
        lines.append(f"  Address:       {site_addr}")

    loc_id = a.get("LOC_ID", "")
    if loc_id:
        lines.append(f"  LOC_ID:        {loc_id}")

    owner = a.get("OWNER1", "")
    if owner:
        lines.append(f"  Owner:         {owner}")

    use_code = a.get("USE_CODE", "")
    if use_code:
        lines.append(f"  Use Code:      {use_code}")

    style = a.get("STYLE", "")
    if style:
        lines.append(f"  Style:         {style}")

    yr = a.get("YR_BUILT")
    if yr:
        lines.append(f"  Year Built:    {yr}")

    floors = a.get("RES_FLR")
    if floors:
        lines.append(f"  Floors:        {floors}")

    rooms = a.get("NUM_ROOMS")
    if rooms:
        lines.append(f"  Rooms:         {rooms}")

    bldg_area = a.get("BLDG_AREA")
    if bldg_area:
        lines.append(f"  Building Area: {bldg_area:,.0f} sq ft")

    lot_size = a.get("LOT_SIZE")
    lot_units = a.get("LOT_UNITS", "S")
    if lot_size:
        unit_label = "acres" if lot_units == "A" else "sq ft"
        lines.append(f"  Lot Size:      {lot_size:,.0f} {unit_label}")

    bldg_val = a.get("BLDG_VAL")
    if bldg_val:
        lines.append(f"  Building Val:  ${bldg_val:,.0f}")

    land_val = a.get("LAND_VAL")
    if land_val:
        lines.append(f"  Land Value:    ${land_val:,.0f}")

    other_val = a.get("OTHER_VAL")
    if other_val:
        lines.append(f"  Other Value:   ${other_val:,.0f}")

    total_val = a.get("TOTAL_VAL")
    if total_val:
        lines.append(f"  Total Value:   ${total_val:,.0f}")

    fy = a.get("FY")
    if fy:
        lines.append(f"  Fiscal Year:   {fy}")

    return "\n".join(lines)


def format_brookline_parcel(feature):
    """Format a local Brookline parcel feature for display."""
    a = feature.get("attributes", {})
    lines = []

    addr = f"{a.get('PAR_ADD_NO_1', '')} {a.get('PAR_ADD_ST_1', '')}".strip()
    if addr:
        lines.append(f"  Address:       {addr}")

    pid = a.get("PARCEL_ID", "")
    if pid:
        lines.append(f"  Parcel ID:     {pid}")

    owner = a.get("OWNER_NAME", "")
    if owner:
        lines.append(f"  Owner:         {owner}")

    land_area = a.get("TOT_LND_AREA") or a.get("TOT_LND_ARE")
    if land_area is not None:
        lines.append(f"  Land Area:     {land_area:,.0f} sq ft")

    for field, label in [("BLDG_VALUE", "Building Val"), ("LAND_VALUE", "Land Value"),
                         ("TOTAL_VALUE", "Total Value"), ("RES_VALUE", "Res Value"),
                         ("COM_VALUE", "Com Value")]:
        val = a.get(field)
        if val is not None:
            lines.append(f"  {label + ':':14s} ${val:,.0f}")

    cc = a.get("CLASS_CODE", "")
    if cc:
        lines.append(f"  Class Code:    {cc}")

    return "\n".join(lines)


def format_street(feature):
    """Format a street edge / road feature for display."""
    a = feature.get("attributes", {})
    lines = []
    name = a.get("STREETNAME") or a.get("FULLNAME") or a.get("NAME", "")
    if name:
        lines.append(f"  Street:        {name}")
    length = (a.get("SHAPE.STLen()") or a.get("Shape.STLength()")
              or a.get("Shape__Length") or a.get("LENGTH"))
    if length is not None:
        lines.append(f"  Length:        {length:,.1f} ft")
    stype = a.get("STREETTYPE") or a.get("TYPE") or a.get("CLASS")
    if stype is not None:
        lines.append(f"  Type/Class:    {stype}")
    rdtype = a.get("RDTYPE")
    if rdtype is not None:
        lines.append(f"  Road Type:     {rdtype}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------

def discover_fields(service_url, layer_id, label):
    """Print all fields for a layer."""
    try:
        fields = get_layer_fields(service_url, layer_id)
        print(f"\n--- {label} (layer {layer_id}) ---")
        for f in fields:
            print(f"  {f['name']:30s}  {f['type']:30s}  {f.get('alias', '')}")
    except Exception as e:
        print(f"\n--- {label} ---\n  Error: {e}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_street_query(query):
    """Parse freeform query into (number|None, street_name).

    '10 White Pl' -> (10, 'White Pl')
    'White Place' -> (None, 'White Place')
    """
    parts = query.strip().split(None, 1)
    if len(parts) >= 2:
        try:
            return int(parts[0]), parts[1]
        except ValueError:
            pass
    return None, query


def print_features(features, formatter, label="parcel", raw=False):
    """Print a list of features using the given formatter."""
    if not features:
        print(f"No {label}s found.")
        return
    print(f"Found {len(features)} {label}(s):\n")
    for i, feat in enumerate(features, 1):
        print(f"{label.capitalize()} {i}:")
        if raw:
            print(json.dumps(feat["attributes"], indent=2, default=str))
        else:
            print(formatter(feat))
        print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Fetch property and street data from Brookline, MA public GIS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "White Pl"               Search parcels on White Place
  %(prog)s "10 White Pl"            Search for 10 White Place
  %(prog)s --street "White Pl"      Search parcels + street data
  %(prog)s --address "10 White Pl"  Search by specific address
  %(prog)s --parcel-id "217-02-00"  Search by Brookline parcel ID
  %(prog)s --loc-id "F_46_123"      Search by MassGIS LOC_ID
  %(prog)s --source local "Beacon"  Use Brookline server instead of MassGIS
  %(prog)s --discover               List available fields in each layer
  %(prog)s --raw "White Pl"         Show raw JSON attributes
        """,
    )
    parser.add_argument("query", nargs="?", help="Street name or 'number street' to search")
    parser.add_argument("--street", help="Search by street name (also fetches street data)")
    parser.add_argument("--address", help="Search by full address (number + street)")
    parser.add_argument("--parcel-id", help="Search by Brookline parcel ID")
    parser.add_argument("--loc-id", help="Search by MassGIS LOC_ID")
    parser.add_argument("--source", choices=["massgis", "local"], default="massgis",
                        help="Data source: massgis (default, richer) or local (Brookline server)")
    parser.add_argument("--discover", action="store_true", help="Show available fields")
    parser.add_argument("--raw", action="store_true", help="Show raw JSON attributes")

    args = parser.parse_args()

    # ---- Discovery mode ----
    if args.discover:
        print("Discovering available GIS layers and fields...")
        discover_fields(MASSGIS_PARCELS_URL, MASSGIS_PARCELS_LAYER,
                        "MassGIS L3 Parcels+Assessor")
        discover_fields(BROOKLINE_PARCELS_URL, BROOKLINE_PARCELS_LAYER,
                        "Brookline Local Parcels")
        discover_fields(ACCELA_URL, ACCELA_STREET_EDGES_LAYER,
                        "Brookline Street Edges (Accela)")
        discover_fields(ACCELA_URL, ACCELA_BUILDINGS_LAYER,
                        "Brookline Buildings (Accela)")
        discover_fields(MASSDOT_ROADS_URL, MASSDOT_ROADS_LAYER,
                        "MassDOT Roads (statewide)")
        return

    if not any([args.query, args.street, args.address, args.parcel_id, args.loc_id]):
        parser.print_help()
        sys.exit(1)

    use_massgis = args.source == "massgis"

    # ---- LOC_ID search (MassGIS only) ----
    if args.loc_id:
        print(f"Searching MassGIS for LOC_ID: {args.loc_id}\n")
        features = massgis_parcels_by_loc_id(args.loc_id)
        print_features(features, format_massgis_parcel, "parcel", args.raw)
        return

    # ---- Parcel ID search (local Brookline only) ----
    if args.parcel_id:
        print(f"Searching Brookline for parcel ID: {args.parcel_id}\n")
        features = brookline_parcels_by_id(args.parcel_id)
        print_features(features, format_brookline_parcel, "parcel", args.raw)
        return

    # ---- Address search ----
    if args.address:
        num, street = parse_street_query(args.address)
        if num is None:
            print("Error: --address requires a street number (e.g., '10 White Pl')")
            sys.exit(1)
        print(f"Searching for: {num} {street}\n")
        if use_massgis:
            features = massgis_parcels_by_address(num, street)
            print_features(features, format_massgis_parcel, "parcel", args.raw)
        else:
            features = brookline_parcels_by_address(num, street)
            print_features(features, format_brookline_parcel, "parcel", args.raw)
        return

    # ---- Street / freeform search ----
    street_name = args.street or args.query
    num, street = parse_street_query(street_name)

    if num is not None:
        print(f"Searching for: {num} {street}\n")
        if use_massgis:
            features = massgis_parcels_by_address(num, street)
            fmt = format_massgis_parcel
        else:
            features = brookline_parcels_by_address(num, street)
            fmt = format_brookline_parcel
    else:
        print(f"Searching parcels on: {street}\n")
        if use_massgis:
            features = massgis_parcels_by_street(street)
            fmt = format_massgis_parcel
        else:
            features = brookline_parcels_by_street(street)
            fmt = format_brookline_parcel

    print_features(features, fmt, "parcel", args.raw)

    # Also fetch street data when --street is used
    if args.street:
        print(f"Searching street segments for: {street}\n")
        edges = []
        # Try local Brookline street edges first, fall back to MassDOT
        try:
            edges = brookline_street_edges(street)
        except Exception:
            pass
        if not edges:
            try:
                edges = massdot_roads_in_brookline(street)
            except Exception:
                pass
        print_features(edges, format_street, "segment", args.raw)


if __name__ == "__main__":
    main()
