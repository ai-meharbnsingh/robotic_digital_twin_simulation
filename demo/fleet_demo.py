#!/usr/bin/env python3
"""
fleet_demo.py — 10-minute narrated demo using REST API calls.

Demonstrates the full Robotic Digital Twin capability:
  Act 1: Normal fleet operations (inject 10 orders)
  Act 2: Fault injection and recovery
  Act 3: Surge handling (inject 50 orders)
  Act 4: Fleet analytics

Requirements:
  - API running at localhost:8029 (docker compose up, or uvicorn)
  - OR run standalone (uses direct Python imports as fallback)

Run:
    python3 demo/fleet_demo.py
    python3 demo/fleet_demo.py --standalone   # No API server needed
"""

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "python"))

# Try httpx for API mode
try:
    import httpx
    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False


# ── Helpers ──────────────────────────────────────────────────────────

BASE_URL = "http://localhost:8029"


def narrate(text: str):
    """Print narration with timestamp."""
    ts = time.strftime("%H:%M:%S")
    print(f"\n  [{ts}] {text}")


def pause(seconds: float = 1.0):
    """Visible pause between demo steps."""
    time.sleep(seconds)


def api_get(path: str) -> dict:
    """GET request to the API."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(f"{BASE_URL}{path}")
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


def api_post(path: str, data: dict = None) -> dict:
    """POST request to the API."""
    try:
        with httpx.Client(timeout=5.0) as client:
            resp = client.post(f"{BASE_URL}{path}", json=data or {})
            return resp.json()
    except Exception as e:
        return {"error": str(e)}


def print_json(data: dict, indent: int = 4):
    """Pretty-print JSON response."""
    print(f"    {json.dumps(data, indent=indent, default=str)}")


# ── Standalone Mode (no API server) ──────────────────────────────────

def run_standalone():
    """Run the demo using direct Python imports (no API server needed)."""
    from wes.order_generator import OrderGenerator
    from wes.kpi_tracker import KPITracker
    from app.config import load_warehouse_config, load_robot_config

    print("=" * 70)
    print("  Robotic Digital Twin — Fleet Demo (Standalone Mode)")
    print("=" * 70)

    # Load configs
    warehouse = load_warehouse_config("simple_grid")
    robot_config = load_robot_config("differential_drive")
    nodes = warehouse["nodes"]
    zones = warehouse["zones"]
    pick_nodes = [n["name"] for n in nodes if n.get("type") == "pick"]
    drop_nodes = [n["name"] for n in nodes if n.get("type") == "drop"]

    narrate(f"Loaded warehouse: {warehouse['name']} ({len(nodes)} nodes)")
    narrate(f"Loaded robot config: {robot_config['name']}")

    # Initialize WES
    order_gen = OrderGenerator(pick_nodes=pick_nodes, drop_nodes=drop_nodes, seed=42)
    kpi = KPITracker()

    narrate("WES layer ready")
    pause(0.5)

    # ── ACT 1: Normal Fleet Operations ──
    print("\n" + "=" * 70)
    print("  ACT 1: Normal Fleet Operations")
    print("=" * 70)

    narrate("Generating 10 simulated robots across the warehouse...")
    robots = []
    for i, node in enumerate(nodes[:10]):
        robot = {
            "robot_id": f"robot_{i+1:02d}",
            "pose": {"x": node["x"], "y": node["y"], "theta": 0.0},
            "velocity": {"linear": 0.5 if i % 3 != 0 else 0.0},
            "battery": {"charge_pct": 80 - i * 5},
            "status": "moving" if i % 3 != 0 else "idle",
            "current_node": node["name"],
        }
        robots.append(robot)
        narrate(f"  {robot['robot_id']} at {node['name']} "
                f"(battery: {robot['battery']['charge_pct']}%)")
    pause(0.5)

    narrate("Injecting 10 orders...")
    orders = order_gen.generate_batch(10)
    for o in orders[:3]:
        narrate(f"  Order {o['order_id'][:8]}... "
                f"{o['source_node']} -> {o['destination_node']} "
                f"(priority: {o['priority']}, {o['payload_kg']}kg)")
    narrate(f"  ... and {len(orders) - 3} more orders")
    pause(0.5)

    # ── ACT 2: Fault Injection ──
    print("\n" + "=" * 70)
    print("  ACT 2: Fault Injection — Motor Failure")
    print("=" * 70)

    crash_robot = robots[0]
    narrate(f"FAULT INJECTED: {crash_robot['robot_id']} motor failure at {crash_robot['current_node']}!")
    pause(0.5)

    narrate(f"  Robot {crash_robot['robot_id']} stopped. Awaiting recovery via fleet manager.")
    narrate(f"  Fleet manager will reassign tasks and route robot to dock.")
    pause(0.5)

    # ── ACT 3: Surge Handling ──
    print("\n" + "=" * 70)
    print("  ACT 3: Order Surge — 50 Orders")
    print("=" * 70)

    narrate("Injecting 50 orders (5x normal load)...")
    surge_orders = order_gen.generate_batch(50)
    narrate(f"  Generated {len(surge_orders)} orders (total: {order_gen.order_count})")
    pause(0.5)

    narrate("Fleet under load — task queue growing:")
    narrate(f"  Active robots: {sum(1 for r in robots if r['status'] == 'moving')}")
    narrate(f"  Idle robots: {sum(1 for r in robots if r['status'] == 'idle')}")
    narrate(f"  Total pending orders: {len(orders) + len(surge_orders)}")
    pause(0.5)

    # ── ACT 4: Analytics ──
    print("\n" + "=" * 70)
    print("  ACT 4: Fleet Analytics")
    print("=" * 70)

    narrate("Computing WES KPIs...")
    kpi_result = kpi.compute(orders + surge_orders, [])
    narrate(f"  Orders per hour:  {kpi_result['orders_per_hour']:.0f}")
    narrate(f"  Total orders:     {len(orders) + len(surge_orders)}")
    pause(0.5)

    # ── Summary ──
    print("\n" + "=" * 70)
    print("  DEMO COMPLETE — Summary")
    print("=" * 70)

    narrate(f"Total orders generated: {len(orders) + len(surge_orders)}")
    narrate(f"Orders per hour:        {kpi_result['orders_per_hour']:.0f}")
    narrate(f"Robots simulated:       {len(robots)}")
    print()
    print("  Demo complete.")
    print("=" * 70)


# ── API Mode (requires running server) ───────────────────────────────

def run_api_mode():
    """Run the demo via REST API calls to localhost:8029."""
    if not _HTTPX_AVAILABLE:
        print("ERROR: httpx is required for API mode. Install with: pip install httpx")
        print("       Or run with --standalone flag to skip the API.")
        sys.exit(1)

    print("=" * 70)
    print("  Robotic Digital Twin — Fleet Demo (API Mode)")
    print(f"  Target: {BASE_URL}")
    print("=" * 70)

    # Check health
    narrate("Checking API health...")
    health = api_get("/health")
    if "error" in health:
        narrate(f"  ERROR: Cannot reach API at {BASE_URL}")
        narrate(f"  {health['error']}")
        narrate("  Start the API with: docker compose up")
        narrate("  Or run with: python3 demo/fleet_demo.py --standalone")
        sys.exit(1)

    print_json(health)
    pause(0.5)

    # ACT 1: Normal ops
    print("\n" + "=" * 70)
    print("  ACT 1: Normal Fleet Operations")
    print("=" * 70)

    narrate("Checking fleet status...")
    fleet = api_get("/api/fleet/status")
    print_json(fleet)
    pause(0.5)

    narrate("Loading warehouse map...")
    map_data = api_get("/api/map")
    narrate(f"  Map: {map_data.get('name', 'unknown')}")
    narrate(f"  Nodes: {len(map_data.get('nodes', []))}")
    narrate(f"  Edges: {len(map_data.get('edges', []))}")
    pause(0.5)

    narrate("Computing path: DOCK_1 -> DROP_1...")
    path = api_get("/api/map/path?start=DOCK_1&end=DROP_1")
    narrate(f"  Path: {' -> '.join(path.get('path', []))}")
    narrate(f"  Hops: {path.get('hops', 0)}, Distance: {path.get('distance', 0)}m")
    pause(0.5)

    narrate("Injecting 10 orders...")
    result = api_post("/api/wes/inject-orders", {"num_orders": 10})
    narrate(f"  Injected: {result.get('injected', 0)} orders")
    pause(0.5)

    # ACT 2: Fault injection
    print("\n" + "=" * 70)
    print("  ACT 2: Fault Injection — Motor Failure")
    print("=" * 70)

    narrate("Injecting motor failure fault on robot_01...")
    fault = api_post("/api/simulation/inject-fault", {
        "fault_type": "motor_failure",
        "robot_id": "robot_01",
        "duration_s": 30.0,
    })
    print_json(fault)
    pause(0.5)

    # ACT 3: Surge
    print("\n" + "=" * 70)
    print("  ACT 3: Order Surge — 50 Orders")
    print("=" * 70)

    narrate("Injecting 50 orders (surge)...")
    surge = api_post("/api/wes/inject-orders", {"num_orders": 50})
    narrate(f"  Injected: {surge.get('injected', 0)} orders")
    pause(0.5)

    narrate("WES KPIs:")
    kpi = api_get("/api/wes/kpi")
    print_json(kpi)
    pause(0.5)

    # ACT 4: Analytics
    print("\n" + "=" * 70)
    print("  ACT 4: Fleet Analytics")
    print("=" * 70)

    narrate("Fleet-wide analytics:")
    analytics = api_get("/api/analytics/fleet")
    print_json(analytics)
    pause(0.5)

    narrate("Throughput stats:")
    throughput = api_get("/api/stats/throughput")
    print_json(throughput)

    # Summary
    print("\n" + "=" * 70)
    print("  DEMO COMPLETE")
    print("=" * 70)
    narrate("All 4 acts completed successfully.")
    narrate(f"API endpoint: {BASE_URL}")
    narrate("Dashboard:    http://localhost:5199")
    narrate("Grafana:      http://localhost:3000")
    print("=" * 70)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Robotic Digital Twin — Fleet Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 demo/fleet_demo.py --standalone   # No API server needed
  python3 demo/fleet_demo.py                # Requires API at localhost:8029
        """,
    )
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Run without API server (uses direct Python imports)",
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8029",
        help="API base URL (default: http://localhost:8029)",
    )
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    if args.standalone:
        run_standalone()
    else:
        run_api_mode()


if __name__ == "__main__":
    main()
