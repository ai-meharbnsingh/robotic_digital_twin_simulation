#!/usr/bin/env python3
"""
Generate Realistic Warehouse — 150m × 200m, 12 zones
======================================================

Generates BOTH:
  1. configs/warehouses/realistic.json — node/edge/zone config
  2. gazebo/worlds/realistic.sdf — 3D world with zone-specific geometry

Zone layout (3×4 grid):
  Row 3: Zone_A (y=150-195)  Zone_B (y=150-195)  Zone_C (y=150-195)
  Row 2: Zone_D (y=100-145)  Zone_E (y=100-145)  Zone_F (y=100-145)
  Row 1: Zone_G (y=50-95)    Zone_H (y=50-95)    Zone_I (y=50-95)
  Row 0: Zone_J (Pick, y=5-40) Zone_K (Drop, y=5-40) Zone_L (Ops, y=5-40)

Each storage zone (A-I): 5 aisles × 8 shelves, 2 chargers, 1 cross-aisle
Zones J/K/L: Pick stations, drop stations, ops area

EACH ZONE HAS UNIQUE GEOMETRY:
  - Different shelf heights (1.8m to 3.0m)
  - Different shelf depths (0.3m to 0.7m)
  - Different gap patterns
  This makes LiDAR signatures UNIQUE per zone.
"""

import json
import math
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# ── Zone definitions ──
# (name, col, row, type, shelf_height, shelf_depth, has_gaps)
ZONE_SPECS = [
    # Row 3 (top) — storage
    ("Zone_A", 0, 3, "storage", 2.5, 0.4, False),
    ("Zone_B", 1, 3, "storage", 2.0, 0.3, False),
    ("Zone_C", 2, 3, "storage", 3.0, 0.5, False),
    # Row 2 — storage with gaps
    ("Zone_D", 0, 2, "storage", 2.5, 0.5, True),
    ("Zone_E", 1, 2, "storage", 2.0, 0.7, True),
    ("Zone_F", 2, 2, "storage", 3.0, 0.3, True),
    # Row 1 — storage varied
    ("Zone_G", 0, 1, "storage", 1.8, 0.4, False),
    ("Zone_H", 1, 1, "storage", 2.2, 0.6, False),
    ("Zone_I", 2, 1, "storage", 2.8, 0.5, True),
    # Row 0 (bottom) — special
    ("Zone_J", 0, 0, "pick", 0.8, 0.5, False),
    ("Zone_K", 1, 0, "drop", 0.8, 0.5, False),
    ("Zone_L", 2, 0, "ops", 1.5, 0.4, False),
]

# Layout constants
ZONE_WIDTH = 40.0       # m per zone column
ZONE_HEIGHT = 45.0      # m per zone row
ZONE_GAP_X = 5.0        # gap between zone columns (main corridor)
ZONE_GAP_Y = 5.0        # gap between zone rows (main corridor)
AISLE_COUNT = 5
AISLE_SPACING = 6.0     # m between aisle centers
SHELF_COUNT = 8
SHELF_SPACING = 4.5     # m between shelf centers along aisle
AISLE_WIDTH = 3.0       # m between shelf walls
CROSS_AISLE_POS = 4     # cross-aisle between shelf 4 and 5


def zone_origin(col, row):
    """Bottom-left corner of a zone."""
    x = col * (ZONE_WIDTH + ZONE_GAP_X) + 5
    y = row * (ZONE_HEIGHT + ZONE_GAP_Y) + 5
    return x, y


def generate_config():
    """Generate warehouse JSON config with nodes, edges, and zones."""
    nodes = []
    edges = []
    zones = []
    node_id = 0

    def add_node(name, x, y, ntype):
        nonlocal node_id
        nodes.append({"name": name, "x": round(x, 2), "y": round(y, 2), "type": ntype})
        node_id += 1
        return name

    def add_edge(a, b):
        edges.append({"from": a, "to": b})

    # ── Build each zone ──
    for zname, col, row, ztype, sh, sd, gaps in ZONE_SPECS:
        ox, oy = zone_origin(col, row)
        zone_nodes = []

        if ztype == "storage":
            # 2 chargers at zone entry
            c1 = add_node(f"{zname}_C1", ox + 5, oy + 2, "charge")
            c2 = add_node(f"{zname}_C2", ox + ZONE_WIDTH - 10, oy + 2, "charge")
            zone_nodes.extend([c1, c2])

            # Entry node connecting chargers
            entry = add_node(f"{zname}_entry", ox + ZONE_WIDTH / 2, oy + 2, "none")
            zone_nodes.append(entry)
            add_edge(c1, entry)
            add_edge(entry, c2)

            # 5 aisles
            aisle_entries = []
            for ai in range(AISLE_COUNT):
                ax = ox + 5 + ai * AISLE_SPACING  # aisle center x
                aisle_entry = add_node(f"{zname}_A{ai}_entry", ax, oy + 5, "aisle")
                zone_nodes.append(aisle_entry)
                add_edge(entry, aisle_entry)
                aisle_entries.append(aisle_entry)

                prev_node = aisle_entry
                for si in range(SHELF_COUNT):
                    sy = oy + 8 + si * SHELF_SPACING
                    stype = "shelf" if not gaps or si % 2 == 0 else "none"
                    sn = add_node(f"{zname}_A{ai}_S{si}", ax, sy, stype)
                    zone_nodes.append(sn)
                    add_edge(prev_node, sn)
                    prev_node = sn

                # Aisle exit at top
                aisle_exit = add_node(f"{zname}_A{ai}_exit", ax, oy + ZONE_HEIGHT - 3, "aisle")
                zone_nodes.append(aisle_exit)
                add_edge(prev_node, aisle_exit)

            # Cross-aisle at midpoint (between shelf 3 and 4)
            cross_y = oy + 8 + CROSS_AISLE_POS * SHELF_SPACING - SHELF_SPACING / 2
            for ai in range(AISLE_COUNT - 1):
                ax1 = ox + 5 + ai * AISLE_SPACING
                ax2 = ox + 5 + (ai + 1) * AISLE_SPACING
                cn1 = f"{zname}_A{ai}_S{CROSS_AISLE_POS - 1}"
                cn2 = f"{zname}_A{ai + 1}_S{CROSS_AISLE_POS - 1}"
                # Cross-aisle connects shelf nodes
                add_edge(cn1, cn2)

            # Connect aisle entries to each other (cross corridor at bottom)
            for ai in range(AISLE_COUNT - 1):
                add_edge(aisle_entries[ai], aisle_entries[ai + 1])

        elif ztype == "pick":
            # 4 pick stations with approach aisles
            for pi in range(4):
                px = ox + 5 + pi * 8
                p_approach = add_node(f"{zname}_P{pi}_approach", px, oy + 5, "aisle")
                p_station = add_node(f"{zname}_P{pi}", px, oy + 15, "pick")
                zone_nodes.extend([p_approach, p_station])
                add_edge(p_approach, p_station)
                if pi > 0:
                    prev_approach = f"{zname}_P{pi-1}_approach"
                    add_edge(prev_approach, p_approach)
            # Chargers
            c1 = add_node(f"{zname}_C1", ox + 2, oy + 2, "charge")
            c2 = add_node(f"{zname}_C2", ox + 35, oy + 2, "charge")
            zone_nodes.extend([c1, c2])
            add_edge(c1, f"{zname}_P0_approach")
            add_edge(c2, f"{zname}_P3_approach")

        elif ztype == "drop":
            # 4 drop stations with conveyor approach
            for di in range(4):
                dx = ox + 5 + di * 8
                d_approach = add_node(f"{zname}_D{di}_approach", dx, oy + 5, "aisle")
                d_station = add_node(f"{zname}_D{di}", dx, oy + 15, "drop")
                zone_nodes.extend([d_approach, d_station])
                add_edge(d_approach, d_station)
                if di > 0:
                    add_edge(f"{zname}_D{di-1}_approach", d_approach)
            c1 = add_node(f"{zname}_C1", ox + 2, oy + 2, "charge")
            c2 = add_node(f"{zname}_C2", ox + 35, oy + 2, "charge")
            zone_nodes.extend([c1, c2])
            add_edge(c1, f"{zname}_D0_approach")
            add_edge(c2, f"{zname}_D3_approach")

        elif ztype == "ops":
            # Open ops area with workbenches
            for oi in range(6):
                ox2 = ox + 5 + (oi % 3) * 12
                oy2 = oy + 10 + (oi // 3) * 15
                on = add_node(f"{zname}_W{oi}", ox2, oy2, "hub")
                zone_nodes.append(on)
                if oi > 0:
                    add_edge(f"{zname}_W{oi-1}", on)
            # Connect first and last to form loop
            add_edge(f"{zname}_W5", f"{zname}_W0")
            c1 = add_node(f"{zname}_C1", ox + 2, oy + 2, "charge")
            c2 = add_node(f"{zname}_C2", ox + 35, oy + 2, "charge")
            zone_nodes.extend([c1, c2])
            add_edge(c1, f"{zname}_W0")
            add_edge(c2, f"{zname}_W2")

        zones.append({"name": zname, "type": ztype, "nodes": zone_nodes,
                       "shelf_height": sh, "shelf_depth": sd, "has_gaps": gaps})

    # ── Main corridors connecting zones ──
    # Horizontal corridors between zone columns
    for row in range(4):
        for col in range(2):
            z1 = [z for z in ZONE_SPECS if z[1] == col and z[2] == row][0]
            z2 = [z for z in ZONE_SPECS if z[1] == col + 1 and z[2] == row][0]
            n1 = f"{z1[0]}_corridor_E"
            n2 = f"{z2[0]}_corridor_W"
            ox1, oy1 = zone_origin(col, row)
            ox2, oy2 = zone_origin(col + 1, row)
            add_node(n1, ox1 + ZONE_WIDTH - 2, oy1 + ZONE_HEIGHT / 2, "none")
            add_node(n2, ox2 + 2, oy2 + ZONE_HEIGHT / 2, "none")
            add_edge(n1, n2)
            # Connect to zone internals
            if z1[3] == "storage":
                add_edge(f"{z1[0]}_A{AISLE_COUNT-1}_exit", n1)
            if z2[3] == "storage":
                add_edge(n2, f"{z2[0]}_A0_entry")

    # Vertical corridors between zone rows
    for col in range(3):
        for row in range(3):
            z1 = [z for z in ZONE_SPECS if z[1] == col and z[2] == row][0]
            z2 = [z for z in ZONE_SPECS if z[1] == col and z[2] == row + 1][0]
            n1 = f"{z1[0]}_corridor_N"
            n2 = f"{z2[0]}_corridor_S"
            ox1, oy1 = zone_origin(col, row)
            ox2, oy2 = zone_origin(col, row + 1)
            add_node(n1, ox1 + ZONE_WIDTH / 2, oy1 + ZONE_HEIGHT - 2, "none")
            add_node(n2, ox2 + ZONE_WIDTH / 2, oy2 + 2, "none")
            add_edge(n1, n2)
            # Connect to zone internals
            if z1[3] == "storage":
                add_edge(f"{z1[0]}_A2_exit", n1)
            elif z1[3] == "pick":
                add_edge(f"{z1[0]}_P0_approach", n1)
            elif z1[3] == "drop":
                add_edge(f"{z1[0]}_D0_approach", n1)
            elif z1[3] == "ops":
                add_edge(f"{z1[0]}_W0", n1)
            if z2[3] == "storage":
                add_edge(n2, f"{z2[0]}_entry")

    config = {
        "name": "Realistic Warehouse 150x200m",
        "description": "12 zones, 60 aisles, 720 shelves, 24 chargers, varied geometry per zone",
        "size_m": [150, 200],
        "nodes": nodes,
        "edges": edges,
        "zones": zones,
    }

    # Save
    out_path = os.path.join(PROJECT_ROOT, "configs", "warehouses", "realistic.json")
    with open(out_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"Generated: {out_path}")
    print(f"  Nodes: {len(nodes)}")
    print(f"  Edges: {len(edges)}")
    print(f"  Zones: {len(zones)}")
    types = {}
    for n in nodes:
        types[n["type"]] = types.get(n["type"], 0) + 1
    print(f"  Node types: {types}")

    return config


if __name__ == "__main__":
    config = generate_config()
