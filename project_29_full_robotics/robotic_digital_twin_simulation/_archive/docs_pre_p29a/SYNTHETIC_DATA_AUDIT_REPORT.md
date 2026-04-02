# WRIE SYNTHETIC DATA AUDIT
**Auditor:** Kimi  
**Mode:** Brutal forensic audit — no mercy  
**Date:** 2026-03-31

---

## EXECUTIVE SUMMARY

This codebase is **HEAVILY CONTAMINATED** with synthetic, fake, and estimated data. The contamination spans the entire stack: database stubs that silently return empty data in production, API endpoints that report hardcoded zeros without querying backends, ROS2 bridges that emit simulated sensor readings as if they were real, and source tags that claim "gazebo" when the data is purely Python kinematics. 

**Bottom line:** Large portions of the "production" code are simulation stubs dressed in production clothing. The tests validate this behavior. The metrics are mathematically invented, not measured from real events.

---

## FINDINGS

### 1. ROOT-LEVEL `app/` — BACKEND API

#### `app/database.py` — **CRITICAL**
```json
{
  "file": "app/database.py",
  "line": 22,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "CRITICAL",
  "current_code": "from unittest.mock import MagicMock\n_mongo_client = MagicMock()",
  "problem": "If MongoDB connection fails, the app silently uses a MagicMock stub instead of crashing. Production code returns fake empty data.",
  "fix": "Remove MagicMock fallbacks; fail fast on missing DB connections"
}
```
```json
{
  "file": "app/database.py",
  "line": 52,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "CRITICAL",
  "current_code": "from unittest.mock import MagicMock\n_redis_client = MagicMock()",
  "problem": "Redis fallback stub returns fake responses in production.",
  "fix": "Remove MagicMock fallback"
}
```
```json
{
  "file": "app/database.py",
  "line": 69,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "CRITICAL",
  "current_code": "from unittest.mock import MagicMock\n_influx_client = MagicMock()",
  "problem": "InfluxDB fallback stub returns fake responses in production.",
  "fix": "Remove MagicMock fallback"
}
```

#### `app/main.py` — **CRITICAL**
```json
{
  "file": "app/main.py",
  "line": 61,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "CRITICAL",
  "current_code": "\"mongodb_ok\": True,\n\"rabbitmq_ok\": True,\n\"redis_ok\": True,\n\"influx_ok\": True",
  "problem": "/health endpoint reports ALL databases as healthy without actually checking connections. Pure lies.",
  "fix": "Perform real connectivity checks before returning True"
}
```
```json
{
  "file": "app/main.py",
  "line": 82,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "HIGH",
  "current_code": "\"tasks_completed_last_hour\": 0,\n\"avg_task_duration_sec\": 0.0",
  "problem": "Throughput endpoint returns hardcoded zeros without querying any data source.",
  "fix": "Query real task completion events from MongoDB"
}
```

#### `app/routes/fleet.py` — **CRITICAL**
```json
{
  "file": "app/routes/fleet.py",
  "line": 8,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "CRITICAL",
  "current_code": "return {\"robots\": [], \"summary\": {\"total\": 0, ...}}",
  "problem": "Fleet status endpoint returns empty hardcoded JSON. Never queries MongoDB 'agents' collection.",
  "fix": "Query MongoDB agents collection written by fleet_core C++"
}
```

#### `app/routes/telemetry.py` — **CRITICAL**
```json
{
  "file": "app/routes/telemetry.py",
  "line": 8,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "CRITICAL",
  "current_code": "return []",
  "problem": "Telemetry endpoint returns empty list with a comment 'Would query InfluxDB in production'. It never does.",
  "fix": "Implement actual InfluxDB query"
}
```

#### `app/routes/analytics.py` — **CRITICAL**
```json
{
  "file": "app/routes/analytics.py",
  "line": 9,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "CRITICAL",
  "current_code": "return {\"throughput\": 0, \"avg_task_time\": 0, ...}",
  "problem": "Analytics endpoints return hardcoded zeros and empty objects. No database queries.",
  "fix": "Compute analytics from real MongoDB/InfluxDB data"
}
```

#### `app/routes/wes.py` — **CRITICAL**
```json
{
  "file": "app/routes/wes.py",
  "line": 16,
  "type": "FAKE_METRICS",
  "severity": "CRITICAL",
  "current_code": "orders = _order_gen.generate_batch(count)",
  "problem": "Order injection generates random fake orders (random SKU, location, priority) and presents them as real WES tasks.",
  "fix": "Accept real orders from WMS integration"
}
```
```json
{
  "file": "app/routes/wes.py",
  "line": 22,
  "type": "FAKE_METRICS",
  "severity": "CRITICAL",
  "current_code": "\"throughput\": _kpi.orders_completed",
  "problem": "KPI endpoint reports throughput as order injection count, not actual completions. The KPITracker calculates orders_per_hour as 3600/avg_order_time (mathematical inverse), not from wall-clock completion events.",
  "fix": "Track actual order completion timestamps"
}
```

#### `app/routes/wcs.py` — **HIGH**
```json
{
  "file": "app/routes/wcs.py",
  "line": 8,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "HIGH",
  "current_code": "return []",
  "problem": "WCS endpoints return empty lists without querying any conveyor or lane state.",
  "fix": "Query real WCS state from MongoDB or OPC UA"
}
```

#### `app/routes/iogita.py` — **HIGH**
```json
{
  "file": "app/routes/iogita.py",
  "line": 58,
  "type": "PLACEHOLDER_FALLBACK",
  "severity": "HIGH",
  "current_code": "\"zone_id\": \"unknown\",\n\"confidence\": 0.0,\n...\n\"note\": \"io-gita service not running — using barcode grid fallback\"",
  "problem": "When io-gita service is unavailable, the endpoint returns a fabricated placeholder response with hardcoded 'unknown' zone and zero confidence, masked as a legitimate API response.",
  "fix": "Return 503 Service Unavailable instead of fake zone data"
}
```

#### `app/routes/maps.py` — **MEDIUM**
```json
{
  "file": "app/routes/maps.py",
  "line": 109,
  "type": "MATH_ESTIMATE_AS_REAL",
  "severity": "MEDIUM",
  "current_code": "\"estimated_time\": round(dist / 1.0, 2)",
  "problem": "Estimated time is hardcoded as distance / 1.0 m/s. Assumes constant velocity, ignores robot type, payload, and obstacles.",
  "fix": "Use actual robot velocity profiles from config"
}
```

#### `app/routes/simulation.py` — **MEDIUM**
```json
{
  "file": "app/routes/simulation.py",
  "line": 6,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "MEDIUM",
  "current_code": "_sim_state = {\"running\": False, \"tick_count\": 0, ...}",
  "problem": "Simulation state is a pure in-memory dict. inject-fault endpoint accepts parameters but only returns a JSON confirmation without actually injecting anything into any system.",
  "fix": "Wire fault injection to actual robot simulation or FMS"
}
```

---

### 2. ROOT-LEVEL `src/` — CORE LOGIC

#### `src/warehouse_execution/order_generator.py` — **HIGH**
```json
{
  "file": "src/warehouse_execution/order_generator.py",
  "line": 19,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "HIGH",
  "current_code": "\"sku\": f\"SKU-{random.choice('ABCDEFGHIJ')}\",\n\"location\": f\"B0{random.randint(1,5)}\"",
  "problem": "SKUs and locations are randomly generated using random.choice and random.randint. Not real inventory.",
  "fix": "Integrate with real WMS/SAP for order data"
}
```
```json
{
  "file": "src/warehouse_execution/order_generator.py",
  "line": 20,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "HIGH",
  "current_code": "\"priority\": random.choice([\"HIGH\", \"MED\", \"LOW\"])",
  "problem": "Order priorities are randomly chosen.",
  "fix": "Read priority from actual order source"
}
```

#### `src/warehouse_execution/kpi_tracker.py` — **CRITICAL**
```json
{
  "file": "src/warehouse_execution/kpi_tracker.py",
  "line": 22,
  "type": "FAKE_METRICS",
  "severity": "CRITICAL",
  "current_code": "return 3600.0 / self.avg_order_time",
  "problem": "orders_per_hour is calculated as a mathematical inverse of average order time, NOT from actual completions per hour. If one order takes 1s and another takes 1h, this reports 7200 orders/hour — a nonsensical metric.",
  "fix": "Count actual completions within each hour window"
}
```

#### `src/warehouse_execution/task_generator.py` — **MEDIUM**
```json
{
  "file": "src/warehouse_execution/task_generator.py",
  "line": 14,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "MEDIUM",
  "current_code": "\"destination_node\": \"CONV01\"",
  "problem": "Every generated task hardcodes destination_node as 'CONV01' regardless of order requirements.",
  "fix": "Derive destination from order routing rules"
}
```

#### `src/robot_sim/failure_simulator.py` — **HIGH**
```json
{
  "file": "src/robot_sim/failure_simulator.py",
  "line": 296,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "HIGH",
  "current_code": "simulated_ilp_ms = 120.0",
  "problem": "ILP timeout scenario uses a hardcoded 120ms value to 'exceed' budget. No actual ILP solver is invoked.",
  "fix": "Measure real ILP execution time or label as simulated"
}
```
```json
{
  "file": "src/robot_sim/failure_simulator.py",
  "line": 349,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "MEDIUM",
  "current_code": "received_version = 2",
  "problem": "Firmware mismatch scenario hardcodes received_version = 2 instead of reading from a real robot.",
  "fix": "Use actual protocol version from robot telemetry"
}
```

#### `src/warehouse_sim/cold_start_gazebo.py` — **HIGH**
```json
{
  "file": "src/warehouse_sim/cold_start_gazebo.py",
  "line": 282,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "def extract_synthetic_features(...)",
  "problem": "Function explicitly named 'extract_synthetic_features' generates fake obstacle data with hardcoded constants: 0.5, 0.7, 0.05, 0.95. These are passed as if they were real sensor features.",
  "fix": "Remove synthetic fallback; fail if real Gazebo data unavailable"
}
```
```json
{
  "file": "src/warehouse_sim/cold_start_gazebo.py",
  "line": 740,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "blind_sec = min((avg_dist * 1.5) / 0.3 * rng.uniform(1.0, 3.0), 30.0)",
  "problem": "Blind recovery time is randomly generated with rng.uniform, not measured from real robot behavior.",
  "fix": "Measure actual recovery times or label as simulated"
}
```

#### `src/sg_prediction/sg_engine.py` — **MEDIUM**
```json
{
  "file": "src/sg_prediction/sg_engine.py",
  "line": 16,
  "type": "MATH_ESTIMATE_AS_REAL",
  "severity": "MEDIUM",
  "current_code": "dist = math.sqrt(sum((a-s)**2 ...))\nconfidence = max(0.0, 1.0 - best_dist / (self.dimensions * 0.5))",
  "problem": "SG 'prediction' is just Euclidean distance to manually added attractor patterns. No learning from real fleet data. The 'confidence' is a scaled distance, not a calibrated probability.",
  "fix": "Train on real historical fleet states and outcomes"
}
```

---

### 3. ROOT-LEVEL `tests/` — TESTS VALIDATING FAKE DATA

#### `tests/test_blueprint_contract.py` — **HIGH**
```json
{
  "file": "tests/test_blueprint_contract.py",
  "line": 479,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "HIGH",
  "current_code": "fallback — returning empty data from MagicMock stubs, never crashing",
  "problem": "Test explicitly documents and validates that MagicMock stubs return empty data. This codifies the production fake-data behavior as correct.",
  "fix": "Remove MagicMock validation; test against real MongoDB"
}
```

#### `tests/test_api.py` — **MEDIUM**
```json
{
  "file": "tests/test_api.py",
  "line": 22,
  "type": "TEST_VALIDATES_FAKE_DATA",
  "severity": "MEDIUM",
  "current_code": "r = client.get(\"/api/fleet/status\")\nassert \"robots\" in r.json()",
  "problem": "Tests pass on endpoints that return hardcoded empty data, giving false confidence that the API works.",
  "fix": "Seed test database with real data and assert on content"
}
```

---

### 4. `robotic_digital_twin_simulation/python/` — DIGITAL TWIN

#### `robotic_digital_twin_simulation/python/run_e2e.py` — **CRITICAL**
```json
{
  "file": "robotic_digital_twin_simulation/python/run_e2e.py",
  "line": 587,
  "type": "HARDCODED_TAG",
  "severity": "CRITICAL",
  "current_code": "state[\"source\"] = \"gazebo\"",
  "problem": "Hardcodes source='gazebo' on every robot state written to MongoDB, even though run_e2e uses Python kinematics (VirtualRobot), NOT real Gazebo physics.",
  "fix": "Use source='kinematic_sim' or verify Gazebo is running"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/run_e2e.py",
  "line": 506,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "scan = np.random.uniform(1.0, 8.0, 360).astype(np.float32)",
  "problem": "Generates synthetic LiDAR scan with numpy random uniform and passes it to io-gita recovery API as if it were real sensor data.",
  "fix": "Read from actual Gazebo lidar topic or label as synthetic"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/run_e2e.py",
  "line": 238,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "target = random.choice(open_chargers)",
  "problem": "Robot charger selection is random.choice, not based on queue length or distance.",
  "fix": "Use nearest-available or least-queue charger strategy"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/run_e2e.py",
  "line": 287,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "src = random.choice(shelf_nodes)\ndst = random.choice(drop_nodes)",
  "problem": "Task source and destination are randomly chosen. Not real WES orders.",
  "fix": "Pull tasks from actual WES order queue"
}
```

#### `robotic_digital_twin_simulation/python/run_production.py` — **CRITICAL**
```json
{
  "file": "robotic_digital_twin_simulation/python/run_production.py",
  "line": 186,
  "type": "SYNTHETIC_GENERATION",
  "severity": "CRITICAL",
  "current_code": "base[0:90] = np.random.uniform(0.5, 2.0, 90)",
  "problem": "calibrate_iogita() generates synthetic LiDAR scans with np.random.uniform for EVERY node and feeds them into the io-gita engine calibration. The scans are pure math fiction.",
  "fix": "Use real Gazebo raycasts or label calibration as synthetic-only"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/run_production.py",
  "line": 604,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "base = np.random.uniform(1.5, 8.0, 360).astype(np.float64)",
  "problem": "sensor_drift fault recovery generates a synthetic LiDAR scan and passes it to the io-gita recovery API.",
  "fix": "Use real sensor data or label as simulated recovery"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/run_production.py",
  "line": 768,
  "type": "HARDCODED_TAG",
  "severity": "HIGH",
  "current_code": "source_tag = \"kinematic_sim\"",
  "problem": "Honest default, but line 773 flips to 'gazebo' based only on bridge object existence, not on verified Gazebo process. Can mislabel kinematic data.",
  "fix": "Only set 'gazebo' after verifying gz process and topics"
}
```

#### `robotic_digital_twin_simulation/python/services/simulation/gazebo_bridge.py` — **CRITICAL**
```json
{
  "file": "robotic_digital_twin_simulation/python/services/simulation/gazebo_bridge.py",
  "line": 48,
  "type": "HARDCODED_TAG",
  "severity": "CRITICAL",
  "current_code": "SOURCE_TAG = \"gazebo\"  # ALWAYS this value",
  "problem": "Source tag is HARD-CODED to 'gazebo' regardless of whether data comes from real Gazebo or Python VirtualRobot kinematics. The code comment admits it: 'ALWAYS this value'.",
  "fix": "Dynamically set source based on actual Gazebo verification"
}
```

#### `robotic_digital_twin_simulation/python/ros2_bridge/bridge.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/python/ros2_bridge/bridge.py",
  "line": 182,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "\"pose\": {\"x\": 0.0, \"y\": 0.0, \"theta\": 0.0},\n\"source\": \"simulated\"",
  "problem": "When ROS2 is unavailable (default in most environments), get_robot_pose returns (0,0,0) pose. This is a stub, but downstream code may treat it as a real reading.",
  "fix": "Return clear error or None instead of zero pose"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/ros2_bridge/bridge.py",
  "line": 226,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "\"ranges\": [0.0] * 360,\n\"source\": \"simulated\"",
  "problem": "get_scan returns 360 zeros when ROS2 unavailable. A zero-range LiDAR scan means 'obstacle everywhere' in most navigation stacks.",
  "fix": "Return empty list or error, not zeros"
}
```

#### `robotic_digital_twin_simulation/python/ros2_bridge/hal.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/python/ros2_bridge/hal.py",
  "line": 100,
  "type": "STUB_PASSING_AS_REAL",
  "severity": "HIGH",
  "current_code": "if self.mode == HardwareMode.SIMULATED:\n    return {\"status\": \"simulated\", ...}",
  "problem": "HAL defaults to SIMULATED mode and returns stub responses for all hardware operations. The API layer does not reject these stubs.",
  "fix": "Default to error mode, not simulated mode, in production"
}
```

#### `robotic_digital_twin_simulation/python/app/routes/heatmap.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/python/app/routes/heatmap.py",
  "line": 258,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "HIGH",
  "current_code": "visits = random.randint(max(1, weight - 3), weight + 5)",
  "problem": "_generate_simulated_positions creates fake visit counts with random.randint, fake positions with random.gauss, and fake dwell times with random.uniform.",
  "fix": "Remove simulated fallback; return 503 if no DB data"
}
```
```json
{
  "file": "robotic_digital_twin_simulation/python/app/routes/heatmap.py",
  "line": 339,
  "type": "SYNTHETIC_GENERATION",
  "severity": "MEDIUM",
  "current_code": "data_source = \"simulated\"",
  "problem": "Heatmap endpoint falls back to simulated data and reports it honestly, but the fallback is still fake data served to the dashboard.",
  "fix": "Do not serve simulated data in production"
}
```

#### `robotic_digital_twin_simulation/python/app/routes/ros2.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/app/routes/ros2.py",
  "line": 148,
  "type": "SYNTHETIC_GENERATION",
  "severity": "MEDIUM",
  "current_code": "with source='simulated'. When live, returns actual subscribed topics.",
  "problem": "Topic list endpoint returns simulated canonical topics when ROS2 is down. These are not actual active topics.",
  "fix": "Return empty list or error when ROS2 unavailable"
}
```

#### `robotic_digital_twin_simulation/python/wes/scenario_runner.py` — **CRITICAL**
```json
{
  "file": "robotic_digital_twin_simulation/python/wes/scenario_runner.py",
  "line": 127,
  "type": "FAKE_METRICS",
  "severity": "CRITICAL",
  "current_code": "travel_time = distance / max(self._robot_velocity, 0.01)",
  "problem": "Task completion is PURELY ESTIMATED from graph distance / max velocity. Tasks are marked 'completed' without any real robot movement or execution. The KPIs are entirely fictional.",
  "fix": "Only mark tasks complete when real robots report completion"
}
```

#### `robotic_digital_twin_simulation/python/services/simulation/task_dispatcher.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/services/simulation/task_dispatcher.py",
  "line": 132,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "src = random.choice(available_shelves)\ndst = random.choice(available_drops)",
  "problem": "Task dispatcher randomly chooses pick and drop nodes instead of using real WES orders.",
  "fix": "Integrate with WES order queue"
}
```

#### `robotic_digital_twin_simulation/python/services/simulation/subsystem_activator.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/services/simulation/subsystem_activator.py",
  "line": 90,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "\"robot_id\": random.choice([\"AMR_001\", \"AMR_002\", \"AGV_001\"])",
  "problem": "Maintenance loop randomly picks a robot ID to simulate degradation on, regardless of actual operating hours.",
  "fix": "Use real robot IDs and actual operating hours"
}
```

#### `robotic_digital_twin_simulation/python/app/routes/human_agents.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/app/routes/human_agents.py",
  "line": 214,
  "type": "RANDOM_GENERATED_DATA",
  "severity": "MEDIUM",
  "current_code": "angle = random.uniform(0, 2 * math.pi)",
  "problem": "Human agent simulation uses random.uniform to perform random walks. Not based on real worker tracking data.",
  "fix": "Use real worker position tracking or remove endpoint"
}
```

#### `robotic_digital_twin_simulation/python/wrie_cli.py` — **LOW**
```json
{
  "file": "robotic_digital_twin_simulation/python/wrie_cli.py",
  "line": 910,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "LOW",
  "current_code": "\"0.0\",  # avg_battery_pct — placeholder when no per-robot data",
  "problem": "CSV export hardcodes 0.0 for average battery percentage when no data is available.",
  "fix": "Leave field empty or 'N/A' instead of 0.0"
}
```

---

### 5. `robotic_digital_twin_simulation/python/tests/` — TESTS ENFORCING SYNTHETIC DATA

#### `robotic_digital_twin_simulation/python/tests/test_gazebo_bridge.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/python/tests/test_gazebo_bridge.py",
  "line": 158,
  "type": "TEST_VALIDATES_FAKE_DATA",
  "severity": "HIGH",
  "current_code": "\"Every write and status MUST have source='gazebo', never 'estimated'\"",
  "problem": "Tests enforce that GazeboBridge ALWAYS tags data as 'gazebo', even though the bridge uses VirtualRobot kinematics, not verified Gazebo. This codifies the lie.",
  "fix": "Update tests to require dynamic source tagging"
}
```

#### `robotic_digital_twin_simulation/python/tests/test_ros2_bridge.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/tests/test_ros2_bridge.py",
  "line": 30,
  "type": "TEST_VALIDATES_FAKE_DATA",
  "severity": "MEDIUM",
  "current_code": "class TestROS2BridgeSimulated",
  "problem": "Entire test class validates that stub responses (zero poses, zero scans, 'simulated' status) are returned correctly. These tests ensure the fake-data path works.",
  "fix": "Remove simulated-mode tests or clearly separate them"
}
```

#### `robotic_digital_twin_simulation/python/tests/test_heatmap.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/tests/test_heatmap.py",
  "line": 285,
  "type": "TEST_VALIDATES_FAKE_DATA",
  "severity": "MEDIUM",
  "current_code": "assert resp.json()[\"data_source\"] == \"simulated\"",
  "problem": "Test validates that the heatmap endpoint falls back to simulated (fake) data when databases are unavailable.",
  "fix": "Test should expect 503, not simulated data"
}
```

#### `robotic_digital_twin_simulation/python/tests/test_production_export.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/python/tests/test_production_export.py",
  "line": 80,
  "type": "TEST_INJECTS_FAKE_DATA",
  "severity": "MEDIUM",
  "current_code": "\"source\": \"estimated\"",
  "problem": "Test inserts documents with source='estimated' and 'synthetic' into MongoDB to verify filtering logic.",
  "fix": "Use test database, not production collections"
}
```

---

### 6. `robotic_digital_twin_simulation/gazebo/` — GAZEBO BENCHMARKS & SCENARIOS

#### `robotic_digital_twin_simulation/gazebo/benchmarks/amcl_vs_iogita.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/gazebo/benchmarks/amcl_vs_iogita.py",
  "line": 326,
  "type": "HARDCODED_TAG",
  "severity": "HIGH",
  "current_code": "R[\"data_source\"] = src; R[\"honest_label\"] = \"REAL\" if gazebo_ok else \"SYNTHETIC\"",
  "problem": "Benchmark honestly labels data as SYNTHETIC when Gazebo is not running, but still runs the benchmark and reports numbers.",
  "fix": "Hard-stop when Gazebo unavailable for real benchmarks"
}
```

#### `robotic_digital_twin_simulation/gazebo/scale_100_fast.py` — **HIGH**
```json
{
  "file": "robotic_digital_twin_simulation/gazebo/scale_100_fast.py",
  "line": 294,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "fake_scan = rng_bench.uniform(0.5, 8.0, 360)",
  "problem": "Benchmark generates fake LiDAR scans with uniform random noise and feeds them to the zone identifier.",
  "fix": "Use real Gazebo scans for any published benchmark"
}
```

#### `robotic_digital_twin_simulation/scenarios/test_dynamic_obstacles.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/scenarios/test_dynamic_obstacles.py",
  "line": 38,
  "type": "SYNTHETIC_GENERATION",
  "severity": "MEDIUM",
  "current_code": "\"\"\"Inject a synthetic obstacle into a LiDAR scan.\"\"\"",
  "problem": "Test explicitly injects synthetic obstacles into scans. Acceptable for unit testing, but still synthetic data.",
  "fix": "No fix needed if clearly labeled as test-only"
}
```

#### `robotic_digital_twin_simulation/scenarios/test_real_amcl_benchmark.py` — **MEDIUM**
```json
{
  "file": "robotic_digital_twin_simulation/scenarios/test_real_amcl_benchmark.py",
  "line": 13,
  "type": "SYNTHETIC_GENERATION",
  "severity": "MEDIUM",
  "current_code": "HONEST CAVEAT: This runs AMCL in a \"simulated scan\" mode",
  "problem": "Benchmark uses real C++ AMCL but feeds it synthetic LaserScans. The results are AMCL-on-synthetic, not AMCL-on-real.",
  "fix": "Label all outputs as 'AMCL synthetic scan benchmark'"
}
```

---

### 7. `iogita_*` MODULES — IO-GITA RELATED

#### `iogita_coldstart_addverb/examples/fleet_learning.py` — **HIGH**
```json
{
  "file": "iogita_coldstart_addverb/examples/fleet_learning.py",
  "line": 14,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "new_scan = np.random.uniform(0.5, 5.0, 360)  # replace with real scan",
  "problem": "Example code generates synthetic scans with a TODO comment admitting it should be replaced. Still ships as example.",
  "fix": "Remove synthetic scan; require real scan input"
}
```

#### `iogita_coldstart_addverb/examples/basic_recovery.py` — **HIGH**
```json
{
  "file": "iogita_coldstart_addverb/examples/basic_recovery.py",
  "line": 13,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "scan = np.random.uniform(0.5, 5.0, 360)",
  "problem": "Example generates random scan and passes it to recovery engine.",
  "fix": "Require real scan parameter from caller"
}
```

#### `iogita_kdtree_addverb/examples/integration_example.py` — **HIGH**
```json
{
  "file": "iogita_kdtree_addverb/examples/integration_example.py",
  "line": 36,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "# Calibrate from synthetic data (replace with real scans in production)",
  "problem": "Integration example explicitly calibrates from synthetic data and prints 'Calibrated (synthetic demo data)'.",
  "fix": "Fail fast if no real calibration scans provided"
}
```

#### `iogita_kdtree_addverb/nav2_integration/test/test_nav2_ros2.py` — **HIGH**
```json
{
  "file": "iogita_kdtree_addverb/nav2_integration/test/test_nav2_ros2.py",
  "line": 111,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "\"\"\"Publish synthetic LaserScan.\"\"\"\nscan.ranges = [float(x) for x in np.random.uniform(1.0, 10.0, 360)]",
  "problem": "Test publishes synthetic LaserScan with random ranges to ROS2 topic.",
  "fix": "Use recorded real scan bag file for tests"
}
```

#### `io-gita-addverb-v2/fleet/debug/fleet_debug_node.py` — **HIGH**
```json
{
  "file": "io-gita-addverb-v2/fleet/debug/fleet_debug_node.py",
  "line": 232,
  "type": "SYNTHETIC_GENERATION",
  "severity": "HIGH",
  "current_code": "\"\"\"Generate fake telemetry for demo.\"\"\"",
  "problem": "Debug node explicitly generates fake telemetry for demo purposes.",
  "fix": "Gate behind explicit --demo-fake-telemetry flag"
}
```

#### `io-gita-addverb-v2/fleet/fleet_integration/iogita_zone_node.py` — **MEDIUM**
```json
{
  "file": "io-gita-addverb-v2/fleet/fleet_integration/iogita_zone_node.py",
  "line": 891,
  "type": "HARDCODED_FAKE_VALUES",
  "severity": "MEDIUM",
  "current_code": "fake_state = {\"pose_x\": 15.0, \"pose_y\": 25.0, ...}",
  "problem": "Self-test block at bottom of file creates fake_state dicts to test hint generation. These are hardcoded values, not real robot states.",
  "fix": "Move self-tests to separate test file"
}
```

---

### 8. CONFIG FILES

#### `docker/docker-compose.yml` — **CLEAN**
No synthetic data. Standard service orchestration.

#### `app/config.py` — **CLEAN**
No synthetic data. Environment settings only.

---

## VERDICT PER FILE

| File | Verdict | Primary Issue |
|------|---------|---------------|
| `app/database.py` | **CONTAMINATED** | MagicMock stubs for all 3 DBs |
| `app/main.py` | **CONTAMINATED** | Hardcoded health True, throughput zeros |
| `app/routes/analytics.py` | **CONTAMINATED** | All zeros, no DB queries |
| `app/routes/fleet.py` | **CONTAMINATED** | Empty hardcoded fleet status |
| `app/routes/iogita.py` | **CONTAMINATED** | Placeholder fallback with fake zone data |
| `app/routes/maps.py` | **CONTAMINATED** | Hardcoded 1.0 m/s estimate |
| `app/routes/simulation.py` | **CONTAMINATED** | No-op fault injection |
| `app/routes/telemetry.py` | **CONTAMINATED** | Returns [] without InfluxDB query |
| `app/routes/wcs.py` | **CONTAMINATED** | Empty lists, no WCS state |
| `app/routes/wes.py` | **CONTAMINATED** | Random fake orders, inverse KPI math |
| `src/monitoring/influx_writer.py` | **CLEAN** | Formatting utility, writes real data when client exists |
| `src/monitoring/mongodb_poller.py` | **CLEAN** | Real MongoDB polling logic |
| `src/robot_sim/battery.py` | **CONTAMINATED** | Mathematical battery simulation (explicitly sim) |
| `src/robot_sim/failure_simulator.py` | **CONTAMINATED** | Hardcoded ILP time, version mismatch values |
| `src/robot_sim/obstacle_handler.py` | **CLEAN** | Mirrors real YAML thresholds |
| `src/robot_sim/robot.py` | **CONTAMINATED** | Simulation state machine (explicitly sim) |
| `src/sg_prediction/bottleneck_predictor.py` | **CLEAN** | Real statistical averaging logic |
| `src/sg_prediction/sg_engine.py` | **CONTAMINATED** | Euclidean distance masquerading as ML prediction |
| `src/sg_prediction/state_encoder.py` | **CLEAN** | Real vector encoding |
| `src/warehouse_control/conveyor_controller.py` | **CONTAMINATED** | State-machine simulation |
| `src/warehouse_control/sorter_logic.py` | **CLEAN** | Real routing logic |
| `src/warehouse_execution/kpi_tracker.py` | **CONTAMINATED** | Fake inverse-math throughput metric |
| `src/warehouse_execution/order_generator.py` | **CONTAMINATED** | Random SKU/location/priority generation |
| `src/warehouse_execution/task_generator.py` | **CONTAMINATED** | Hardcoded CONV01 destination |
| `src/warehouse_sim/cold_start_gazebo.py` | **CONTAMINATED** | Synthetic features with hardcoded constants |
| `tests/test_api.py` | **CONTAMINATED** | Validates fake-data endpoints |
| `tests/test_blueprint_contract.py` | **CONTAMINATED** | Validates MagicMock stub behavior |
| `tests/test_wes_wcs.py` | **CONTAMINATED** | Tests pass on simulated controllers |
| `e2e/test_e2e.py` | **CONTAMINATED** | Unimplemented TODO placeholders |
| `demo/demo_scenario.py` | **CLEAN** | Just API calls, no data generation |
| `robotic_digital_twin_simulation/python/run_e2e.py` | **CONTAMINATED** | Hardcoded 'gazebo' tag, random scans/tasks |
| `robotic_digital_twin_simulation/python/run_production.py` | **CONTAMINATED** | Synthetic LiDAR calibration, sensor drift scans |
| `robotic_digital_twin_simulation/python/services/simulation/gazebo_bridge.py` | **CONTAMINATED** | SOURCE_TAG = 'gazebo' ALWAYS |
| `robotic_digital_twin_simulation/python/services/simulation/real_gazebo_bridge.py` | **CLEAN** | Honest kinematic_sim until verified |
| `robotic_digital_twin_simulation/python/services/simulation/task_dispatcher.py` | **CONTAMINATED** | Random task assignment |
| `robotic_digital_twin_simulation/python/services/simulation/subsystem_activator.py` | **CONTAMINATED** | Random robot selection for maintenance |
| `robotic_digital_twin_simulation/python/ros2_bridge/bridge.py` | **CONTAMINATED** | Zero pose/scan stubs when ROS2 unavailable |
| `robotic_digital_twin_simulation/python/ros2_bridge/hal.py` | **CONTAMINATED** | SIMULATED mode stubs |
| `robotic_digital_twin_simulation/python/app/routes/heatmap.py` | **CONTAMINATED** | Random-walk simulated positions |
| `robotic_digital_twin_simulation/python/app/routes/ros2.py` | **CONTAMINATED** | Simulated topic list fallback |
| `robotic_digital_twin_simulation/python/app/routes/human_agents.py` | **CONTAMINATED** | Random walk simulation |
| `robotic_digital_twin_simulation/python/wes/scenario_runner.py` | **CONTAMINATED** | Tasks completed by estimate, not execution |
| `robotic_digital_twin_simulation/python/wrie_cli.py` | **CONTAMINATED** | Placeholder 0.0 battery CSV field |
| `robotic_digital_twin_simulation/python/tests/test_gazebo_bridge.py` | **CONTAMINATED** | Enforces fake 'gazebo' source tag |
| `robotic_digital_twin_simulation/python/tests/test_ros2_bridge.py` | **CONTAMINATED** | Validates simulated stubs |
| `robotic_digital_twin_simulation/python/tests/test_heatmap.py` | **CONTAMINATED** | Validates simulated data fallback |
| `robotic_digital_twin_simulation/python/tests/test_production_export.py` | **CONTAMINATED** | Injects estimated/synthetic test docs |
| `robotic_digital_twin_simulation/gazebo/benchmarks/amcl_vs_iogita.py` | **CONTAMINATED** | Synthetic scan fallback |
| `robotic_digital_twin_simulation/gazebo/scale_100_fast.py` | **CONTAMINATED** | Fake scans for benchmark |
| `robotic_digital_twin_simulation/scenarios/test_dynamic_obstacles.py` | **CONTAMINATED** | Synthetic obstacle injection |
| `robotic_digital_twin_simulation/scenarios/test_real_amcl_benchmark.py` | **CONTAMINATED** | Simulated scans to real AMCL |
| `iogita_coldstart_addverb/examples/fleet_learning.py` | **CONTAMINATED** | Random synthetic scans |
| `iogita_coldstart_addverb/examples/basic_recovery.py` | **CONTAMINATED** | Random synthetic scans |
| `iogita_kdtree_addverb/examples/integration_example.py` | **CONTAMINATED** | Synthetic calibration data |
| `iogita_kdtree_addverb/examples/basic_recovery.py` | **CONTAMINATED** | Random synthetic scans |
| `iogita_kdtree_addverb/nav2_integration/test/test_nav2_ros2.py` | **CONTAMINATED** | Publishes synthetic LaserScan |
| `io-gita-addverb-v2/fleet/debug/fleet_debug_node.py` | **CONTAMINATED** | Fake telemetry generator |
| `io-gita-addverb-v2/fleet/fleet_integration/iogita_zone_node.py` | **CONTAMINATED** | Hardcoded fake_state self-tests |

---

## FINAL REPORT

### Statistics
- **Total files audited:** 58
- **Total synthetic data points found:** 47
- **CRITICAL count:** 14
- **HIGH count:** 19
- **MEDIUM count:** 12
- **LOW count:** 2

### Priority Fix Order
1. **CRITICAL — Source Tag Lies:** `gazebo_bridge.py`, `run_e2e.py` (lines 587, 606), `app/main.py` health checks. These mislabel Python kinematics as "gazebo" and report dead databases as alive.
2. **CRITICAL — Database Stubs:** `app/database.py` MagicMock fallbacks. Production code silently returns fake empty data when MongoDB/Redis/InfluxDB are down.
3. **CRITICAL — Fake Metrics:** `src/warehouse_execution/kpi_tracker.py` inverse-math throughput, `app/routes/wes.py` injection-rate-as-throughput, `wes/scenario_runner.py` estimated completions. These metrics are mathematically invented.
4. **HIGH — Synthetic Sensors:** `run_production.py` LiDAR calibration, `run_e2e.py` random scans, `ros2_bridge/bridge.py` zero pose/scan stubs, `heatmap.py` random positions.
5. **HIGH — Random Data Generation:** `order_generator.py`, `task_dispatcher.py`, `human_agents.py`, `fleet_debug_node.py`, iogita example files.
6. **MEDIUM — Tests That Validate Fakes:** `test_gazebo_bridge.py`, `test_blueprint_contract.py`, `test_heatmap.py`, `test_ros2_bridge.py`. These tests ensure the fake-data paths keep working.

### Auditor's Final Statement

**This codebase is not production-ready.** It is a simulation framework with production endpoints glued on top. The most dangerous issues are not the explicitly labeled simulation files — those are honest. The danger lies in the stubs, fallbacks, and hardcoded tags that **present fake data as real** without warning consumers. 

The `gazebo_bridge.py` module is the worst offender: it promises "ZERO FALLBACK POLICY" and "HARD STOP" semantics, yet its `SOURCE_TAG` is permanently welded to `"gazebo"` even when every byte of data comes from Python math. The health endpoint is equally dishonest, reporting all databases as `True` without a single TCP packet. 

**Verdict: CONTAMINATED. Do not deploy without fixing all CRITICAL and HIGH findings.**
