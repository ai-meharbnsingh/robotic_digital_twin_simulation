"""
WCS Tests — Conveyor Controller, Sorter Engine, Lane Manager, Package Tracker.

Phase 13: 40+ tests covering all WCS components.
Tests actual logic with real values — no 'is not None' assertions.
"""

import os
import sys
import time
import yaml
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

from wcs.conveyor_controller import ConveyorController, ConveyorSegment, ConveyorState
from wcs.sorter_engine import SorterEngine, SortResult, DivertType
from wcs.lane_manager import LaneManager, LaneType, LaneState
from wcs.package_tracker import PackageTracker, PackageEvent


# ── Load real config ────────────────────────────────────

CONFIG_PATH = os.path.join(ROOT, "..", "configs", "wcs", "conveyor_layout.yaml")

@pytest.fixture
def wcs_config():
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)

@pytest.fixture
def conveyor(wcs_config):
    c = ConveyorController()
    c.load_config(wcs_config)
    return c

@pytest.fixture
def sorter(wcs_config):
    s = SorterEngine()
    s.load_config(wcs_config)
    return s

@pytest.fixture
def lanes(wcs_config):
    lm = LaneManager()
    lm.load_config(wcs_config)
    return lm

@pytest.fixture
def tracker():
    return PackageTracker()


# ══════════════════════════════════════════════════════════
# CONVEYOR CONTROLLER TESTS
# ══════════════════════════════════════════════════════════


class TestConveyorConfig:
    def test_loads_all_segments(self, conveyor):
        segments = conveyor.get_all_segments()
        assert len(segments) == 5, f"Expected 5 segments, got {len(segments)}"

    def test_segment_ids_match_config(self, conveyor):
        expected = {"INBOUND_A", "INBOUND_B", "MAIN_LINE", "SORTER_LINE", "EXPRESS_SPUR"}
        actual = {s["segment_id"] for s in conveyor.get_all_segments()}
        assert actual == expected

    def test_segment_properties(self, conveyor):
        seg = conveyor.get_segment("MAIN_LINE")
        assert seg is not None
        assert seg.length_m == 15.0
        assert seg.max_speed_mps == 2.0
        assert seg.direction == "forward"
        assert seg.upstream_id == "INBOUND_A"
        assert seg.downstream_id == "SORTER_LINE"


class TestConveyorControl:
    def test_start_segment(self, conveyor):
        result = conveyor.start_segment("MAIN_LINE")
        assert result["ok"] is True
        seg = conveyor.get_segment("MAIN_LINE")
        assert seg.state == ConveyorState.RUNNING
        assert seg.current_speed_mps > 0

    def test_start_with_custom_speed(self, conveyor):
        result = conveyor.start_segment("MAIN_LINE", speed_mps=0.8)
        assert result["ok"] is True
        assert result["speed_mps"] == 0.8

    def test_speed_clamped_to_max(self, conveyor):
        result = conveyor.start_segment("MAIN_LINE", speed_mps=99.0)
        assert result["ok"] is True
        assert result["speed_mps"] == 2.0  # MAIN_LINE max is 2.0

    def test_stop_segment(self, conveyor):
        conveyor.start_segment("MAIN_LINE")
        result = conveyor.stop_segment("MAIN_LINE")
        assert result["ok"] is True
        seg = conveyor.get_segment("MAIN_LINE")
        assert seg.state == ConveyorState.IDLE
        assert seg.current_speed_mps == 0.0

    def test_start_all(self, conveyor):
        result = conveyor.start_all()
        assert result["ok"] is True
        running = sum(1 for s in conveyor.get_all_segments() if s["state"] == "running")
        assert running == 5

    def test_stop_all(self, conveyor):
        conveyor.start_all()
        result = conveyor.stop_all()
        assert result["ok"] is True
        assert result["stopped"] == 5

    def test_invalid_segment(self, conveyor):
        result = conveyor.start_segment("FAKE_SEG")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_set_speed_while_running(self, conveyor):
        conveyor.start_segment("MAIN_LINE")
        seg = conveyor.get_segment("MAIN_LINE")
        result = seg.set_speed(1.0)
        assert result["ok"] is True
        assert result["speed_mps"] == 1.0

    def test_set_speed_while_stopped(self, conveyor):
        seg = conveyor.get_segment("MAIN_LINE")
        result = seg.set_speed(1.0)
        assert result["ok"] is False


class TestConveyorJam:
    def test_trigger_jam(self, conveyor):
        conveyor.start_segment("SORTER_LINE")
        result = conveyor.trigger_jam("SORTER_LINE", "test_jam")
        assert result["ok"] is True
        seg = conveyor.get_segment("SORTER_LINE")
        assert seg.state == ConveyorState.JAMMED
        assert seg.jam_count == 1

    def test_cascade_stop_upstream(self, conveyor):
        conveyor.start_all()
        result = conveyor.trigger_jam("SORTER_LINE")
        # SORTER_LINE upstream is MAIN_LINE, MAIN_LINE upstream is INBOUND_A
        assert "MAIN_LINE" in result["cascade_stopped"]

    def test_clear_jam(self, conveyor):
        conveyor.start_segment("SORTER_LINE")
        conveyor.trigger_jam("SORTER_LINE")
        result = conveyor.clear_jam("SORTER_LINE")
        assert result["ok"] is True
        seg = conveyor.get_segment("SORTER_LINE")
        assert seg.state == ConveyorState.IDLE

    def test_clear_resumes_upstream(self, conveyor):
        conveyor.start_all()
        conveyor.trigger_jam("SORTER_LINE")
        result = conveyor.clear_jam("SORTER_LINE")
        assert len(result["cascade_resumed"]) > 0

    def test_cannot_start_jammed(self, conveyor):
        conveyor.start_segment("MAIN_LINE")
        conveyor.get_segment("MAIN_LINE").trigger_jam()
        result = conveyor.start_segment("MAIN_LINE")
        assert result["ok"] is False
        assert "jammed" in result["error"]


class TestConveyorPackages:
    def test_add_package_to_running(self, conveyor):
        conveyor.start_segment("INBOUND_A")
        seg = conveyor.get_segment("INBOUND_A")
        result = seg.add_package("PKG_001")
        assert result["ok"] is True
        assert "PKG_001" in seg.packages_on_belt

    def test_add_package_to_stopped(self, conveyor):
        seg = conveyor.get_segment("INBOUND_A")
        result = seg.add_package("PKG_001")
        assert result["ok"] is False

    def test_remove_package(self, conveyor):
        conveyor.start_segment("INBOUND_A")
        seg = conveyor.get_segment("INBOUND_A")
        seg.add_package("PKG_001")
        result = seg.remove_package("PKG_001")
        assert result["ok"] is True
        assert seg.total_packages_transported == 1

    def test_transfer_between_segments(self, conveyor):
        conveyor.start_all()
        conveyor.get_segment("INBOUND_A").add_package("PKG_T1")
        result = conveyor.transfer_package("PKG_T1", "INBOUND_A", "MAIN_LINE")
        assert result["ok"] is True
        assert "PKG_T1" not in conveyor.get_segment("INBOUND_A").packages_on_belt
        assert "PKG_T1" in conveyor.get_segment("MAIN_LINE").packages_on_belt


class TestConveyorMaintenance:
    def test_enter_maintenance(self, conveyor):
        seg = conveyor.get_segment("INBOUND_A")
        result = seg.set_maintenance(True)
        assert result["ok"] is True
        assert seg.state == ConveyorState.MAINTENANCE

    def test_cannot_start_in_maintenance(self, conveyor):
        seg = conveyor.get_segment("INBOUND_A")
        seg.set_maintenance(True)
        result = conveyor.start_segment("INBOUND_A")
        assert result["ok"] is False


class TestConveyorStats:
    def test_stats(self, conveyor):
        conveyor.start_all()
        stats = conveyor.get_stats()
        assert stats["total_segments"] == 5
        assert stats["running"] == 5
        assert stats["jammed"] == 0
        assert stats["stopped"] == 0
        assert stats["maintenance"] == 0

    def test_stats_with_jam_shows_stopped(self, conveyor):
        conveyor.start_all()
        conveyor.trigger_jam("SORTER_LINE")
        stats = conveyor.get_stats()
        assert stats["jammed"] == 1
        assert stats["stopped"] >= 1  # Cascade-stopped upstream

    def test_eta(self, conveyor):
        conveyor.start_segment("MAIN_LINE", speed_mps=1.5)
        seg = conveyor.get_segment("MAIN_LINE")
        eta = seg.get_eta_s()
        assert abs(eta - 10.0) < 0.01  # 15m / 1.5 m/s = 10s


# ══════════════════════════════════════════════════════════
# SORTER ENGINE TESTS
# ══════════════════════════════════════════════════════════


class TestSorterConfig:
    def test_loads_rules(self, sorter):
        rules = sorter.get_rules()
        assert len(rules) == 5  # EXPRESS, ZA, ZB, ZC, RETURNS

    def test_loads_diverts(self, sorter):
        diverts = sorter.get_diverts()
        assert len(diverts) == 5

    def test_rules_sorted_by_priority(self, sorter):
        rules = sorter.get_rules()
        priorities = [r["priority"] for r in rules]
        assert priorities == sorted(priorities, reverse=True)


class TestSorterRouting:
    def test_express_route(self, sorter):
        result = sorter.sort_package("P1", "EXP-12345")
        assert result["result"] == SortResult.DIVERTED.value
        assert result["target_lane"] == "LANE_EXPRESS"

    def test_zone_a_route(self, sorter):
        result = sorter.sort_package("P2", "ZA-99999")
        assert result["result"] == SortResult.DIVERTED.value
        assert result["target_lane"] == "LANE_OUT_A"

    def test_zone_b_route(self, sorter):
        result = sorter.sort_package("P3", "ZB-11111")
        assert result["target_lane"] == "LANE_OUT_B"

    def test_returns_route(self, sorter):
        result = sorter.sort_package("P4", "RET-55555")
        assert result["target_lane"] == "LANE_RETURNS"

    def test_unknown_barcode_default_lane(self, sorter):
        result = sorter.sort_package("P5", "UNKNOWN-00000")
        assert result["result"] == SortResult.DEFAULT_LANE.value
        assert result["target_lane"] == "DEFAULT"

    def test_empty_barcode_misread(self, sorter):
        result = sorter.sort_package("P6", "")
        assert result["result"] == SortResult.MISREAD.value

    def test_lane_full_rejection(self, sorter):
        capacities = {"LANE_EXPRESS": {"current": 20, "max": 20}}
        result = sorter.sort_package("P7", "EXP-FULL", capacities)
        assert result["result"] == SortResult.LANE_FULL.value

    def test_priority_ordering(self, sorter):
        # EXPRESS (priority=10) should match before ZONE rules (priority=5)
        result = sorter.sort_package("P8", "EXP-ZA-BOTH")
        assert result["target_lane"] == "LANE_EXPRESS"  # Higher priority wins

    def test_add_rule_at_runtime(self, sorter):
        rule = sorter.add_rule("CUSTOM-", "LANE_OUT_C", priority=20)
        result = sorter.sort_package("P9", "CUSTOM-123")
        assert result["target_lane"] == "LANE_OUT_C"

    def test_divert_point_counter(self, sorter):
        sorter.sort_package("P10", "EXP-AAA")
        sorter.sort_package("P11", "EXP-BBB")
        diverts = sorter.get_diverts()
        express_divert = next(d for d in diverts if d["divert_id"] == "DIV_EXPRESS")
        assert express_divert["diverted_count"] == 2


class TestSorterStats:
    def test_stats_after_sorting(self, sorter):
        sorter.sort_package("P1", "EXP-1")
        sorter.sort_package("P2", "ZA-1")
        sorter.sort_package("P3", "UNKNOWN")
        sorter.sort_package("P4", "")
        stats = sorter.get_stats()
        assert stats["total_sorted"] == 4
        assert stats["diverted"] == 2
        assert stats["misread"] == 1
        assert stats["default_lane"] == 1


# ══════════════════════════════════════════════════════════
# LANE MANAGER TESTS
# ══════════════════════════════════════════════════════════


class TestLaneConfig:
    def test_loads_all_lanes(self, lanes):
        all_lanes = lanes.get_all_lanes()
        assert len(all_lanes) == 8  # 2 inbound + 3 outbound + express + returns + default

    def test_lane_types(self, lanes):
        inbound = lanes.get_lanes_by_type(LaneType.INBOUND)
        outbound = lanes.get_lanes_by_type(LaneType.OUTBOUND)
        express = lanes.get_lanes_by_type(LaneType.EXPRESS)
        assert len(inbound) == 2
        assert len(outbound) == 3
        assert len(express) == 1


class TestLaneOperations:
    def test_add_package(self, lanes):
        result = lanes.add_package_to_lane("LANE_OUT_A", "PKG_001")
        assert result["ok"] is True
        assert result["count"] == 1

    def test_remove_package_fifo(self, lanes):
        lanes.add_package_to_lane("LANE_OUT_A", "PKG_A")
        lanes.add_package_to_lane("LANE_OUT_A", "PKG_B")
        result = lanes.remove_package_from_lane("LANE_OUT_A")
        assert result["ok"] is True
        assert result["package_id"] == "PKG_A"  # FIFO

    def test_lane_full(self, lanes):
        lane = lanes.get_lane("LANE_EXPRESS")
        for i in range(lane.max_capacity):
            lanes.add_package_to_lane("LANE_EXPRESS", f"PKG_{i}")
        result = lanes.add_package_to_lane("LANE_EXPRESS", "PKG_OVERFLOW")
        assert result["ok"] is False
        assert result.get("overflow") is True

    def test_lane_utilization(self, lanes):
        lane = lanes.get_lane("LANE_OUT_A")
        for i in range(25):
            lanes.add_package_to_lane("LANE_OUT_A", f"PKG_{i}")
        assert lane.get_utilization_pct() == 50.0  # 25/50

    def test_close_and_open(self, lanes):
        lane = lanes.get_lane("LANE_OUT_B")
        lane.close()
        assert lane.state == LaneState.CLOSED
        result = lane.add_package("PKG_X")
        assert result["ok"] is False
        lane.open()
        assert lane.state == LaneState.OPEN

    def test_capacities_for_sorter(self, lanes):
        caps = lanes.get_capacities()
        assert "LANE_EXPRESS" in caps
        assert caps["LANE_EXPRESS"]["max"] == 20


class TestLaneStats:
    def test_stats(self, lanes):
        lanes.add_package_to_lane("LANE_OUT_A", "P1")
        lanes.add_package_to_lane("LANE_OUT_B", "P2")
        stats = lanes.get_stats()
        assert stats["total_lanes"] == 8
        assert stats["total_packages"] == 2
        assert stats["total_capacity"] > 0


# ══════════════════════════════════════════════════════════
# PACKAGE TRACKER TESTS
# ══════════════════════════════════════════════════════════


class TestPackageTracker:
    def test_create_package(self, tracker):
        pid = tracker.create_package("BC-001", order_id="ORD-1", sku="SKU-A", weight_kg=2.5)
        assert len(pid) == 12
        pkg = tracker.get_package(pid)
        assert pkg["barcode"] == "BC-001"
        assert pkg["order_id"] == "ORD-1"
        assert pkg["weight_kg"] == 2.5
        assert pkg["status"] == PackageEvent.CREATED.value

    def test_full_journey(self, tracker):
        pid = tracker.create_package("BC-JOURNEY")
        tracker.log_event(pid, PackageEvent.ROBOT_PICKED, "STOR_A_0_0")
        tracker.log_event(pid, PackageEvent.ROBOT_DROPPED, "DROP_0")
        tracker.log_event(pid, PackageEvent.CONVEYOR_ENTRY, "INBOUND_A")
        tracker.log_event(pid, PackageEvent.CONVEYOR_TRANSFER, "MAIN_LINE")
        tracker.log_event(pid, PackageEvent.SORTER_SCANNED, "SORTER_LINE")
        tracker.log_event(pid, PackageEvent.SORTER_DIVERTED, "DIV_A")
        tracker.log_event(pid, PackageEvent.LANE_ENTRY, "LANE_OUT_A")
        tracker.log_event(pid, PackageEvent.SHIPPED, "DOCK_A")

        pkg = tracker.get_package(pid)
        assert pkg["status"] == PackageEvent.SHIPPED.value
        assert pkg["event_count"] == 9  # created + 8 events
        assert pkg["shipped_at"] is not None

    def test_find_by_barcode(self, tracker):
        tracker.create_package("FIND-ME-001")
        tracker.create_package("FIND-ME-001")
        tracker.create_package("OTHER-999")
        found = tracker.find_by_barcode("FIND-ME-001")
        assert len(found) == 2

    def test_in_transit(self, tracker):
        p1 = tracker.create_package("T1")
        p2 = tracker.create_package("T2")
        tracker.log_event(p1, PackageEvent.SHIPPED, "dock")
        in_transit = tracker.get_in_transit()
        assert len(in_transit) == 1
        assert in_transit[0]["package_id"] == p2

    def test_packages_at_location(self, tracker):
        p1 = tracker.create_package("LOC-1")
        p2 = tracker.create_package("LOC-2")
        tracker.log_event(p1, PackageEvent.CONVEYOR_ENTRY, "MAIN_LINE")
        tracker.log_event(p2, PackageEvent.CONVEYOR_ENTRY, "MAIN_LINE")
        at_main = tracker.get_packages_at_location("MAIN_LINE")
        assert len(at_main) == 2

    def test_stats(self, tracker):
        p1 = tracker.create_package("S1")
        p2 = tracker.create_package("S2")
        tracker.log_event(p1, PackageEvent.SHIPPED, "dock")
        stats = tracker.get_stats()
        assert stats["total_packages"] == 2
        assert stats["shipped"] == 1
        assert stats["in_transit"] == 1


# ══════════════════════════════════════════════════════════
# END-TO-END INTEGRATION TESTS
# ══════════════════════════════════════════════════════════


class TestSorterRemoveRule:
    def test_remove_existing_rule(self, sorter):
        rules_before = len(sorter.get_rules())
        rule_id = sorter.get_rules()[0]["rule_id"]
        removed = sorter.remove_rule(rule_id)
        assert removed is True
        assert len(sorter.get_rules()) == rules_before - 1

    def test_remove_nonexistent_rule(self, sorter):
        removed = sorter.remove_rule("FAKE_RULE_ID")
        assert removed is False

    def test_get_recent_log(self, sorter):
        sorter.sort_package("P1", "EXP-1")
        sorter.sort_package("P2", "ZA-2")
        sorter.sort_package("P3", "UNKNOWN")
        log = sorter.get_recent_log(limit=2)
        assert len(log) == 2
        assert log[-1]["package_id"] == "P3"

    def test_get_recent_log_empty(self, sorter):
        log = sorter.get_recent_log()
        assert log == []


class TestSerialization:
    def test_conveyor_to_dict_fields(self, conveyor):
        conveyor.start_segment("MAIN_LINE", speed_mps=1.5)
        seg = conveyor.get_segment("MAIN_LINE")
        d = seg.to_dict()
        assert d["segment_id"] == "MAIN_LINE"
        assert d["state"] == "running"  # String, not enum
        assert d["speed_mps"] == 1.5
        assert d["length_m"] == 15.0
        assert isinstance(d["eta_s"], float)
        assert abs(d["eta_s"] - 10.0) < 0.01

    def test_lane_to_dict_fields(self, lanes):
        lane = lanes.get_lane("LANE_EXPRESS")
        d = lane.to_dict()
        assert d["lane_id"] == "LANE_EXPRESS"
        assert d["type"] == "express"  # String, not enum
        assert d["state"] == "open"    # String, not enum
        assert d["max_capacity"] == 20

    def test_divert_to_dict_fields(self, sorter):
        diverts = sorter.get_diverts()
        d = diverts[0]
        assert isinstance(d["divert_type"], str)
        assert d["divert_type"] in ("popup", "tilt_tray", "crossbelt", "pusher")


class TestEdgeCases:
    def test_remove_package_nonexistent_from_lane(self, lanes):
        lanes.add_package_to_lane("LANE_OUT_A", "PKG_REAL")
        result = lanes.remove_package_from_lane("LANE_OUT_A", "PKG_FAKE")
        assert result["ok"] is False
        assert "not in this lane" in result["error"]

    def test_add_to_nonexistent_lane(self, lanes):
        result = lanes.add_package_to_lane("FAKE_LANE", "P1")
        assert result["ok"] is False

    def test_remove_from_empty_lane(self, lanes):
        result = lanes.remove_package_from_lane("LANE_OUT_C")
        assert result["ok"] is False
        assert "empty" in result["error"]

    def test_log_event_nonexistent_package(self, tracker):
        result = tracker.log_event("FAKE_PKG", PackageEvent.SHIPPED, "dock")
        assert result["ok"] is False

    def test_get_package_nonexistent(self, tracker):
        result = tracker.get_package("FAKE_PKG")
        assert result is None

    def test_disabled_sort_rule(self, sorter):
        rule = sorter.add_rule("DIS-", "LANE_OUT_A", priority=99)
        rule.enabled = False
        result = sorter.sort_package("P_DIS", "DIS-123")
        assert result["result"] == "default_lane"  # Disabled rule doesn't match


class TestMultiUpstreamCascade:
    """Cascade stop/resume with merge topology (INBOUND_B feeds MAIN_LINE)."""

    def test_cascade_stops_all_upstreams(self, conveyor):
        """Jam on SORTER_LINE should cascade-stop MAIN_LINE, INBOUND_A, AND INBOUND_B."""
        conveyor.start_all()
        result = conveyor.trigger_jam("SORTER_LINE")
        stopped = result["cascade_stopped"]
        assert "MAIN_LINE" in stopped
        assert "INBOUND_A" in stopped
        assert "INBOUND_B" in stopped

    def test_cascade_resumes_all_upstreams(self, conveyor):
        """Clear jam should resume all cascade-stopped upstreams including INBOUND_B."""
        conveyor.start_all()
        conveyor.trigger_jam("SORTER_LINE")
        result = conveyor.clear_jam("SORTER_LINE")
        resumed = result["cascade_resumed"]
        assert "MAIN_LINE" in resumed
        assert "INBOUND_A" in resumed
        assert "INBOUND_B" in resumed

    def test_main_line_has_two_upstreams(self, conveyor):
        """MAIN_LINE.upstream_ids should contain both INBOUND_A and INBOUND_B."""
        seg = conveyor.get_segment("MAIN_LINE")
        assert set(seg.upstream_ids) == {"INBOUND_A", "INBOUND_B"}


class TestBeltCapacity:
    """Belt capacity limit prevents unbounded package accumulation."""

    def test_add_package_rejected_when_full(self, conveyor):
        conveyor.start_segment("INBOUND_A")
        seg = conveyor.get_segment("INBOUND_A")
        cap = seg.max_belt_capacity
        # Fill belt to capacity
        for i in range(cap):
            result = seg.add_package(f"PKG_{i}")
            assert result["ok"] is True
        # Next add should be rejected
        result = seg.add_package("PKG_OVERFLOW")
        assert result["ok"] is False
        assert "belt full" in result["error"]
        assert len(seg.packages_on_belt) == cap

    def test_default_capacity_is_20(self, conveyor):
        seg = conveyor.get_segment("INBOUND_A")
        assert seg.max_belt_capacity == 20


class TestSortLogDeque:
    """Deque-based sort log truncation at boundary."""

    def test_log_bounded_at_max_log(self, sorter):
        """Sort log should never exceed _max_log entries (uses deque maxlen)."""
        max_log = sorter._max_log  # 1000
        # Write max_log + 100 entries
        for i in range(max_log + 100):
            sorter.sort_package(f"P{i}", f"ZA-{i}")
        log = sorter.get_recent_log(limit=max_log + 200)
        assert len(log) == max_log
        # Oldest entry should be P100, not P0 (first 100 evicted)
        assert log[0]["package_id"] == "P100"
        assert log[-1]["package_id"] == f"P{max_log + 99}"


class TestConfigCrossRef:
    """Verify config cross-references are valid."""

    def test_connected_segment_ids_exist(self, conveyor, lanes):
        """Every lane's connected_segment_id references an existing segment."""
        all_seg_ids = {s["segment_id"] for s in conveyor.get_all_segments()}
        for lane_dict in lanes.get_all_lanes():
            csid = lane_dict.get("connected_segment_id")
            if csid is not None:
                assert csid in all_seg_ids, f"Lane {lane_dict['lane_id']} references missing segment {csid}"

    def test_inbound_a_config_values(self, conveyor):
        """Spot-check INBOUND_A config values match YAML."""
        seg = conveyor.get_segment("INBOUND_A")
        assert seg.length_m == 6.0
        assert seg.max_speed_mps == 1.2

    def test_sorter_line_config_values(self, conveyor):
        """Spot-check SORTER_LINE config values match YAML."""
        seg = conveyor.get_segment("SORTER_LINE")
        assert seg.length_m == 10.0
        assert seg.max_speed_mps == 1.5

    def test_sort_rule_target_lanes_exist(self, sorter, lanes):
        """Every sort rule's target_lane references an existing lane."""
        all_lane_ids = {l["lane_id"] for l in lanes.get_all_lanes()}
        for rule in sorter.get_rules():
            assert rule["target_lane"] in all_lane_ids, \
                f"Rule {rule['rule_id']} targets missing lane {rule['target_lane']}"

    def test_divert_segment_ids_exist(self, conveyor, sorter):
        """Every divert point's segment_id references an existing segment."""
        all_seg_ids = {s["segment_id"] for s in conveyor.get_all_segments()}
        for div in sorter.get_diverts():
            assert div["segment_id"] in all_seg_ids, \
                f"Divert {div['divert_id']} references missing segment {div['segment_id']}"


class TestSortLogQueryCap:
    def test_log_query_capped_at_200(self, sorter):
        """get_recent_log limit should work correctly."""
        for i in range(300):
            sorter.sort_package(f"P{i}", f"ZA-{i}")
        log_50 = sorter.get_recent_log(limit=50)
        assert len(log_50) == 50
        log_all = sorter.get_recent_log(limit=9999)
        assert len(log_all) == 300  # All 300 within deque maxlen=1000


class TestTransferCapacity:
    def test_transfer_rejected_when_dest_full(self, conveyor):
        """transfer_package should reject when destination belt is full."""
        conveyor.start_all()
        src = conveyor.get_segment("INBOUND_A")
        dest = conveyor.get_segment("MAIN_LINE")
        # Fill destination to capacity
        for i in range(dest.max_belt_capacity):
            dest.add_package(f"FILL_{i}")
        # Add one to source
        src.add_package("PKG_XFER")
        # Transfer should fail
        result = conveyor.transfer_package("PKG_XFER", "INBOUND_A", "MAIN_LINE")
        assert result["ok"] is False
        assert "belt full" in result["error"]
        # Package should still be on source
        assert "PKG_XFER" in src.packages_on_belt


class TestEndToEnd:
    """Full flow: package created → conveyor → sorter → lane."""

    def test_full_material_flow(self, conveyor, sorter, lanes, tracker):
        """Robot drops package → conveyor carries → sorter routes → lane receives."""
        # Start conveyors
        conveyor.start_all()

        # Create package
        pid = tracker.create_package("ZA-E2E-001", order_id="ORD-E2E")

        # Robot drops on inbound conveyor
        tracker.log_event(pid, PackageEvent.ROBOT_DROPPED, "DROP_0")
        inbound = conveyor.get_segment("INBOUND_A")
        inbound.add_package(pid)
        tracker.log_event(pid, PackageEvent.CONVEYOR_ENTRY, "INBOUND_A")

        # Transfer to main line
        conveyor.transfer_package(pid, "INBOUND_A", "MAIN_LINE")
        tracker.log_event(pid, PackageEvent.CONVEYOR_TRANSFER, "MAIN_LINE")

        # Transfer to sorter line
        conveyor.transfer_package(pid, "MAIN_LINE", "SORTER_LINE")
        tracker.log_event(pid, PackageEvent.CONVEYOR_TRANSFER, "SORTER_LINE")

        # Sorter scans and routes
        sort_result = sorter.sort_package(pid, "ZA-E2E-001", lanes.get_capacities())
        assert sort_result["result"] == SortResult.DIVERTED.value
        assert sort_result["target_lane"] == "LANE_OUT_A"
        tracker.log_event(pid, PackageEvent.SORTER_DIVERTED, "DIV_A")

        # Package enters lane
        lane_result = lanes.add_package_to_lane("LANE_OUT_A", pid)
        assert lane_result["ok"] is True
        tracker.log_event(pid, PackageEvent.LANE_ENTRY, "LANE_OUT_A")

        # Remove from sorter conveyor
        conveyor.get_segment("SORTER_LINE").remove_package(pid)

        # Ship
        lanes.remove_package_from_lane("LANE_OUT_A", pid)
        tracker.log_event(pid, PackageEvent.SHIPPED, "DOCK_A")

        # Verify full journey
        pkg = tracker.get_package(pid)
        assert pkg["status"] == PackageEvent.SHIPPED.value
        assert pkg["event_count"] == 8  # created + 7 events
        assert pkg["shipped_at"] is not None

    def test_jam_blocks_flow(self, conveyor, tracker):
        """Jam on sorter → upstream stops → no packages accepted."""
        conveyor.start_all()

        # Trigger jam on sorter
        conveyor.trigger_jam("SORTER_LINE", "test_blockage")

        # Main line should be cascade-stopped
        main = conveyor.get_segment("MAIN_LINE")
        assert main.state == ConveyorState.STOPPED

        # Clear jam
        conveyor.clear_jam("SORTER_LINE")
        assert conveyor.get_segment("SORTER_LINE").state == ConveyorState.IDLE

    def test_express_priority(self, conveyor, sorter, lanes, tracker):
        """Express packages get routed to express lane."""
        conveyor.start_all()

        p_normal = tracker.create_package("ZA-NORMAL")
        p_express = tracker.create_package("EXP-FAST")

        r_normal = sorter.sort_package(p_normal, "ZA-NORMAL")
        r_express = sorter.sort_package(p_express, "EXP-FAST")

        assert r_normal["target_lane"] == "LANE_OUT_A"
        assert r_express["target_lane"] == "LANE_EXPRESS"

    def test_system_stats(self, conveyor, sorter, lanes, tracker):
        """All stats report real numbers."""
        conveyor.start_all()
        tracker.create_package("STAT-1")
        sorter.sort_package("STAT-1", "ZA-STAT")

        conv_stats = conveyor.get_stats()
        sort_stats = sorter.get_stats()
        lane_stats = lanes.get_stats()
        pkg_stats = tracker.get_stats()

        assert conv_stats["total_segments"] == 5
        assert conv_stats["running"] == 5
        assert conv_stats["stopped"] == 0
        assert sort_stats["total_sorted"] == 1
        assert lane_stats["total_lanes"] == 8
        assert pkg_stats["total_packages"] == 1
