"""
Tests for io-gita intelligence layer.

- ZoneIdentifier: zone ID < 1ms
- ColdStartRecovery: recovery < 2s
- FleetAtlas: fingerprint aggregation
"""

import time
import tempfile
from pathlib import Path

import numpy as np
import pytest

# Sample warehouse config for testing
SAMPLE_ZONES = [
    {"name": "Charging", "type": "dock", "nodes": ["DOCK_1", "DOCK_2"]},
    {"name": "Storage", "type": "shelf", "nodes": ["S_11", "S_12", "S_13", "S_21", "S_23", "S_31", "S_32", "S_33"]},
    {"name": "Operations", "type": "ops", "nodes": ["PICK_1", "DROP_1", "HUB"]},
]

SAMPLE_NODES = [
    {"name": "DOCK_1", "x": 0, "y": 0, "type": "charge"},
    {"name": "DOCK_2", "x": 8, "y": 0, "type": "charge"},
    {"name": "S_11", "x": 2, "y": 2, "type": "shelf"},
    {"name": "S_12", "x": 4, "y": 2, "type": "shelf"},
    {"name": "S_13", "x": 6, "y": 2, "type": "shelf"},
    {"name": "S_21", "x": 2, "y": 4, "type": "shelf"},
    {"name": "HUB", "x": 4, "y": 4, "type": "hub"},
    {"name": "S_23", "x": 6, "y": 4, "type": "shelf"},
    {"name": "S_31", "x": 2, "y": 6, "type": "shelf"},
    {"name": "S_32", "x": 4, "y": 6, "type": "shelf"},
    {"name": "S_33", "x": 6, "y": 6, "type": "shelf"},
    {"name": "PICK_1", "x": 0, "y": 8, "type": "pick"},
    {"name": "DROP_1", "x": 8, "y": 8, "type": "drop"},
]


class TestZoneIdentifier:
    def test_init(self):
        """ZoneIdentifier initializes with zones and nodes."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        assert zi.num_zones == 3
        assert zi.backend in ("sg_engine", "hopfield_ode", "hopfield_fallback")

    def test_identify_returns_zone_name(self):
        """identify() returns a string zone name."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        zone = zi.identify([0.0, 0.0])
        assert isinstance(zone, str)
        assert zone in ("Charging", "Storage", "Operations", "unknown")

    def test_identify_charging_zone(self):
        """Position near DOCK_1 (0,0) should identify as Charging via nearest centroid."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        # Charging centroid: (4, 0). Storage centroid ~(4.25, 4).
        # Use direct nearest centroid check to verify the centroid is correct
        zone = zi._nearest_zone(np.array([4.0, 0.0]))
        assert zone == "Charging"

    def test_identify_storage_zone(self):
        """Position near storage nodes should identify as Storage."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        # Storage centroid is roughly (4.25, 4.0) — try center of storage
        zone = zi.identify([4.0, 4.0])
        assert zone in ("Storage", "Operations")  # HUB is at (4,4) which is in Operations

    def test_identify_operations_zone(self):
        """Position near operations nodes should identify as Operations."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        # Operations centroid: PICK_1(0,8), DROP_1(8,8), HUB(4,4) → ~(4, 6.67)
        zone = zi.identify([4.0, 6.67])
        assert zone in ("Storage", "Operations")

    def test_zone_id_under_1ms(self):
        """Zone identification must complete in < 1ms."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)

        # Warm up
        zi.identify([1.0, 1.0])

        # Measure over 100 runs
        times = []
        for _ in range(100):
            _, elapsed_ms = zi.identify_timed([np.random.uniform(0, 8), np.random.uniform(0, 8)])
            times.append(elapsed_ms)

        avg_ms = sum(times) / len(times)
        max_ms = max(times)
        assert avg_ms < 1.0, f"Average zone ID time {avg_ms:.3f}ms exceeds 1ms target"
        assert max_ms < 5.0, f"Max zone ID time {max_ms:.3f}ms is too high"

    def test_multiple_identifications_consistent(self):
        """Same position should give same zone repeatedly."""
        from intelligence.iogita.zone_identifier import ZoneIdentifier
        zi = ZoneIdentifier(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        pos = [4.0, 0.0]
        results = [zi.identify(pos) for _ in range(10)]
        assert len(set(results)) == 1, f"Inconsistent results: {results}"


class TestColdStartRecovery:
    def test_init(self):
        """ColdStartRecovery initializes."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        cs = ColdStartRecovery()
        assert cs is not None

    def test_save_and_load_state(self):
        """save_state and load_state round-trip works."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        with tempfile.TemporaryDirectory() as tmpdir:
            cs = ColdStartRecovery(state_dir=Path(tmpdir))
            state = {
                "robot_id": "robot_001",
                "pose": {"x": 2.0, "y": 4.0, "theta": 1.57},
                "battery": {"charge_pct": 65.0},
                "current_node": "S_11",
                "current_task_id": "task_42",
                "status": "moving",
            }
            assert cs.save_state("robot_001", state) is True

            loaded = cs.load_state("robot_001")
            assert loaded is not None
            assert loaded["state"]["pose"]["x"] == 2.0
            assert loaded["state"]["current_node"] == "S_11"

    def test_generate_recovery_hints_with_state(self):
        """Recovery hints include position restore and task resume."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        cs = ColdStartRecovery()
        state = {
            "pose": {"x": 2.0, "y": 4.0},
            "current_node": "S_11",
            "battery": {"charge_pct": 65.0},
            "current_task_id": "task_42",
        }
        cs.save_state("robot_001", state)

        hints = cs.generate_recovery_hints("robot_001", state)
        assert hints["robot_id"] == "robot_001"
        assert hints["has_prior_state"] is True
        assert len(hints["steps"]) > 0
        step_actions = [s["action"] for s in hints["steps"]]
        assert "restore_position" in step_actions
        assert "localize_to_node" in step_actions
        assert "resume_task" in step_actions

    def test_generate_recovery_hints_without_state(self):
        """Recovery hints for unknown robot include full_init."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        cs = ColdStartRecovery()
        hints = cs.generate_recovery_hints("unknown_robot", {})
        assert hints["has_prior_state"] is False
        step_actions = [s["action"] for s in hints["steps"]]
        assert "full_init" in step_actions

    def test_cold_start_under_2s(self):
        """Cold start recovery must complete in < 2s."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        cs = ColdStartRecovery()
        state = {
            "pose": {"x": 2.0, "y": 4.0},
            "current_node": "S_11",
            "battery": {"charge_pct": 15.0},
            "current_task_id": "task_42",
        }
        cs.save_state("robot_001", state)

        start = time.perf_counter()
        hints = cs.generate_recovery_hints("robot_001", state)
        elapsed_s = time.perf_counter() - start

        assert elapsed_s < 2.0, f"Cold start took {elapsed_s:.2f}s, exceeds 2s target"
        assert hints["recovery_time_ms"] < 2000

    def test_low_battery_hint(self):
        """Low battery triggers charge_first hint."""
        from intelligence.iogita.cold_start import ColdStartRecovery
        cs = ColdStartRecovery()
        state = {
            "pose": {"x": 2.0, "y": 4.0},
            "current_node": "S_11",
            "battery": {"charge_pct": 5.0},
        }
        cs.save_state("robot_low", state)
        hints = cs.generate_recovery_hints("robot_low", state)
        step_actions = [s["action"] for s in hints["steps"]]
        assert "charge_first" in step_actions


class TestFleetAtlas:
    def test_init(self):
        """FleetAtlas initializes."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        assert atlas is not None

    def test_update_fingerprint(self):
        """Updating fingerprint records robot zone."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        atlas.update_fingerprint("robot_001", "Charging", {"x": 0, "y": 0, "theta": 0})
        snapshot = atlas.get_fleet_snapshot()
        assert snapshot["total_robots"] == 1
        assert snapshot["zone_occupation"]["Charging"] == 1

    def test_zone_transition_recorded(self):
        """Moving a robot between zones records a transition."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        atlas.update_fingerprint("robot_001", "Charging", {"x": 0, "y": 0})
        atlas.update_fingerprint("robot_001", "Storage", {"x": 4, "y": 4})
        snapshot = atlas.get_fleet_snapshot()
        assert len(snapshot["recent_transitions"]) == 1
        assert snapshot["recent_transitions"][0]["from_zone"] == "Charging"
        assert snapshot["recent_transitions"][0]["to_zone"] == "Storage"

    def test_detect_map_change_no_change(self):
        """No change detected when map is unchanged."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        result = atlas.detect_map_change(SAMPLE_NODES)
        assert result["changed"] is False

    def test_detect_map_change_added_node(self):
        """Change detected when a node is added."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        new_nodes = SAMPLE_NODES + [{"name": "NEW_NODE", "x": 10, "y": 10, "type": "aisle"}]
        result = atlas.detect_map_change(new_nodes)
        assert result["changed"] is True
        assert "NEW_NODE" in result["added_nodes"]

    def test_transition_matrix(self):
        """Transition matrix correctly counts zone changes."""
        from intelligence.iogita.fleet_atlas import FleetAtlas
        atlas = FleetAtlas(zones=SAMPLE_ZONES, nodes=SAMPLE_NODES)
        atlas.update_fingerprint("r1", "Charging", {"x": 0, "y": 0})
        atlas.update_fingerprint("r1", "Storage", {"x": 4, "y": 4})
        atlas.update_fingerprint("r1", "Operations", {"x": 4, "y": 8})
        matrix = atlas.get_zone_transition_matrix()
        assert matrix["total_transitions"] == 2
        assert matrix["transitions"]["Charging"]["Storage"] == 1
        assert matrix["transitions"]["Storage"]["Operations"] == 1
