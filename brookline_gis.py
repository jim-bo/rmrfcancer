#!/usr/bin/env python3
"""
Fetch property and street characteristics from Brookline, MA public GIS data.

Data sources:
  - Brookline ArcGIS Server (gisweb.brooklinema.gov) for parcel and street data
  - Brookline Assessor's property lookup for detailed building info

Usage:
  python brookline_gis.py "White Place"
  python brookline_gis.py --street "White Pl"
  python brookline_gis.py --address "10 White Pl"
  python brookline_gis.py --parcel-id "123-45-67"
"""

import argparse
import json
import sys
from urllib.parse import urlencode

import requests

# Brookline ArcGIS REST endpoints
BASE_URL = "https://gisweb.brooklinema.gov/arcgis/rest/services"

# GPV Default MapServer - has parcels with assessor data
PARCELS_URL = f"{BASE_URL}/GPV/gpvdefault/MapServer"

# Accela MapServer - has parcels (3), buildings (4), street edges (7)
ACCELA_URL = f"{BASE_URL}/Accela/MapServer"

# Layer IDs within the Accela service
ACCELA_PARCELS_LAYER = 3
ACCELA_BUILDINGS_LAYER = 4
ACCELA_STREET_EDGES_LAYER = 7

# Common request timeout
TIMEOUT = 30


def query_layer(service_url, layer_id, where_clause, out_fields="*", return_geometry=False):
    """Query an ArcGIS MapServer layer and return features."""
    url = f"{service_url}/{layer_id}/query"
    params = {
        "where": where_clause,
        "outFields": out_fields,
        "returnGeometry": "true" if return_geometry else "false",
        "f": "json",
    }
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()

    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error'].get('message', data['error'])}")

    return data.get("features", [])


def get_layer_fields(service_url, layer_id):
    """Fetch field definitions for a layer (useful for discovery)."""
    url = f"{service_url}/{layer_id}"
    params = {"f": "json"}
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    return data.get("fields", [])


def find_parcels_by_street(street_name):
    """Search parcels whose street address contains the given name."""
    # PAR_ADD_ST_1 is the primary street name field
    where = f"UPPER(PAR_ADD_ST_1) LIKE '%{street_name.upper()}%'"
    return query_layer(PARCELS_URL, 2, where)


def find_parcels_by_address(street_number, street_name):
    """Search parcels by street number and name."""
    where = (
        f"PAR_ADD_NO_1 = {street_number} AND "
        f"UPPER(PAR_ADD_ST_1) LIKE '%{street_name.upper()}%'"
    )
    return query_layer(PARCELS_URL, 2, where)


def find_parcels_by_id(parcel_id):
    """Search parcels by parcel ID."""
    where = f"PARCEL_ID = '{parcel_id}'"
    return query_layer(PARCELS_URL, 2, where)


def find_street_edges(street_name):
    """Search street edge features by street name."""
    where = f"UPPER(STREETNAME) LIKE '%{street_name.upper()}%'"
    return query_layer(ACCELA_URL, ACCELA_STREET_EDGES_LAYER, where)


def find_buildings_by_street(street_name):
    """Search building features by street name."""
    where = f"UPPER(STREETNAME) LIKE '%{street_name.upper()}%'"
    return query_layer(ACCELA_URL, ACCELA_BUILDINGS_LAYER, where)


def format_parcel(feature):
    """Format a parcel feature for display."""
    attrs = feature.get("attributes", {})
    lines = []

    address_num = attrs.get("PAR_ADD_NO_1", "")
    address_st = attrs.get("PAR_ADD_ST_1", "")
    address = f"{address_num} {address_st}".strip()
    if address:
        lines.append(f"  Address:       {address}")

    parcel_id = attrs.get("PARCEL_ID", "")
    if parcel_id:
        lines.append(f"  Parcel ID:     {parcel_id}")

    owner = attrs.get("OWNER_NAME", "")
    if owner:
        lines.append(f"  Owner:         {owner}")

    co_owner = attrs.get("CO_OWNER_NAME", "")
    if co_owner:
        lines.append(f"  Co-Owner:      {co_owner}")

    land_area = attrs.get("TOT_LND_AREA") or attrs.get("TOT_LND_ARE")
    if land_area is not None:
        lines.append(f"  Land Area:     {land_area:,.0f} sq ft")

    gross_area = attrs.get("GROSS_AREA")
    if gross_area is not None:
        lines.append(f"  Gross Area:    {gross_area:,.0f} sq ft")

    living_area = attrs.get("LIVING_AREA")
    if living_area is not None:
        lines.append(f"  Living Area:   {living_area:,.0f} sq ft")

    bldg_val = attrs.get("BLDG_VAL") or attrs.get("BLDG_VALUE")
    if bldg_val is not None:
        lines.append(f"  Building Val:  ${bldg_val:,.0f}")

    land_val = attrs.get("LAND_VAL") or attrs.get("LAND_VALUE")
    if land_val is not None:
        lines.append(f"  Land Value:    ${land_val:,.0f}")

    total_val = attrs.get("TOTAL_VAL") or attrs.get("TOTAL_VALUE")
    if total_val is not None:
        lines.append(f"  Total Value:   ${total_val:,.0f}")

    class_code = attrs.get("CLASS_CODE", "")
    if class_code:
        lines.append(f"  Class Code:    {class_code}")

    year_built = attrs.get("YEAR_BUILT")
    if year_built is not None:
        lines.append(f"  Year Built:    {year_built}")

    return "\n".join(lines)


def format_street_edge(feature):
    """Format a street edge feature for display."""
    attrs = feature.get("attributes", {})
    lines = []

    name = attrs.get("STREETNAME") or attrs.get("FULLNAME") or attrs.get("NAME")
    if name:
        lines.append(f"  Street Name:   {name}")

    length = attrs.get("SHAPE.STLen()") or attrs.get("Shape.STLength()") or attrs.get("LENGTH")
    if length is not None:
        lines.append(f"  Length:        {length:,.1f} ft")

    street_type = attrs.get("STREETTYPE") or attrs.get("TYPE")
    if street_type:
        lines.append(f"  Type:          {street_type}")

    return "\n".join(lines)


def discover_fields(service_url, layer_id, layer_name=""):
    """Print all fields for a layer (for development/debugging)."""
    fields = get_layer_fields(service_url, layer_id)
    print(f"\n--- Fields for {layer_name} (layer {layer_id}) ---")
    for f in fields:
        print(f"  {f['name']:30s}  {f['type']:30s}  {f.get('alias', '')}")


def parse_street_query(query):
    """Parse a freeform query into optional street number + street name.

    Examples:
      "White Pl"      -> (None, "White Pl")
      "10 White Pl"   -> (10, "White Pl")
      "White Place"   -> (None, "White Place")
    """
    parts = query.strip().split(None, 1)
    if len(parts) >= 2:
        try:
            num = int(parts[0])
            return num, parts[1]
        except ValueError:
            pass
    return None, query


def main():
    parser = argparse.ArgumentParser(
        description="Fetch property and street data from Brookline, MA public GIS.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s "White Pl"              Search parcels on White Place
  %(prog)s "10 White Pl"           Search for 10 White Place
  %(prog)s --street "White Pl"     Search parcels + street edges
  %(prog)s --address "10 White Pl" Search by specific address
  %(prog)s --parcel-id "217-02-00" Search by parcel ID
  %(prog)s --discover              List available fields in each layer
  %(prog)s --raw "White Pl"        Show raw JSON attributes
        """,
    )
    parser.add_argument("query", nargs="?", help="Street name or address to search")
    parser.add_argument("--street", help="Search by street name")
    parser.add_argument("--address", help="Search by full address (number + street)")
    parser.add_argument("--parcel-id", help="Search by parcel ID")
    parser.add_argument("--discover", action="store_true", help="Show available fields")
    parser.add_argument("--raw", action="store_true", help="Show raw JSON attributes")

    args = parser.parse_args()

    if args.discover:
        print("Discovering available GIS layers and fields...\n")
        try:
            discover_fields(PARCELS_URL, 2, "Parcels (GPV Default)")
        except Exception as e:
            print(f"  Error querying GPV Parcels: {e}")
        try:
            discover_fields(ACCELA_URL, ACCELA_PARCELS_LAYER, "Parcels (Accela)")
        except Exception as e:
            print(f"  Error querying Accela Parcels: {e}")
        try:
            discover_fields(ACCELA_URL, ACCELA_BUILDINGS_LAYER, "Buildings (Accela)")
        except Exception as e:
            print(f"  Error querying Accela Buildings: {e}")
        try:
            discover_fields(ACCELA_URL, ACCELA_STREET_EDGES_LAYER, "Street Edges (Accela)")
        except Exception as e:
            print(f"  Error querying Accela Street Edges: {e}")
        return

    if not any([args.query, args.street, args.address, args.parcel_id]):
        parser.print_help()
        sys.exit(1)

    # Determine search mode
    if args.parcel_id:
        print(f"Searching for parcel ID: {args.parcel_id}\n")
        parcels = find_parcels_by_id(args.parcel_id)
        if parcels:
            print(f"Found {len(parcels)} parcel(s):\n")
            for i, p in enumerate(parcels, 1):
                print(f"Parcel {i}:")
                if args.raw:
                    print(json.dumps(p["attributes"], indent=2))
                else:
                    print(format_parcel(p))
                print()
        else:
            print("No parcels found.")

    elif args.address:
        num, street = parse_street_query(args.address)
        if num is None:
            print("Error: --address requires a street number (e.g., '10 White Pl')")
            sys.exit(1)
        print(f"Searching for address: {num} {street}\n")
        parcels = find_parcels_by_address(num, street)
        if parcels:
            print(f"Found {len(parcels)} parcel(s):\n")
            for i, p in enumerate(parcels, 1):
                print(f"Parcel {i}:")
                if args.raw:
                    print(json.dumps(p["attributes"], indent=2))
                else:
                    print(format_parcel(p))
                print()
        else:
            print("No parcels found at that address.")

    else:
        street_name = args.street or args.query
        num, street = parse_street_query(street_name)

        if num is not None:
            # If they gave a number, search by address first
            print(f"Searching for address: {num} {street}\n")
            parcels = find_parcels_by_address(num, street)
        else:
            print(f"Searching for parcels on: {street}\n")
            parcels = find_parcels_by_street(street)

        if parcels:
            print(f"Found {len(parcels)} parcel(s):\n")
            for i, p in enumerate(parcels, 1):
                print(f"Parcel {i}:")
                if args.raw:
                    print(json.dumps(p["attributes"], indent=2))
                else:
                    print(format_parcel(p))
                print()
        else:
            print("No parcels found.")

        # Also search street edges if --street was used
        if args.street:
            print(f"\nSearching street edges for: {street}\n")
            edges = find_street_edges(street)
            if edges:
                print(f"Found {len(edges)} street segment(s):\n")
                for i, e in enumerate(edges, 1):
                    print(f"Segment {i}:")
                    if args.raw:
                        print(json.dumps(e["attributes"], indent=2))
                    else:
                        print(format_street_edge(e))
                    print()
            else:
                print("No street edge data found.")


if __name__ == "__main__":
    main()
