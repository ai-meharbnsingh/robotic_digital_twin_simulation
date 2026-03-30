"""
ScenarioRunner — executes a single scenario in isolated DB namespace.

Time-stepped simulation: estimates travel time from graph distance / robot velocity.
Completes tasks after estimated time. Runs in milliseconds of wall-clock, not real-time.

Phase 6: Parallel Scenario Comparison.
"""

import math
import time
from collections import deque
from typing import Any

from wes.order_generator import OrderGenerator
from wes.task_generator import TaskGenerator
from wes.kpi_tracker import KPITracker


class ScenarioRunner:
    """
    Executes a single scenario in isolated DB namespace.

    Steps:
    1. Create robot docs in namespace
    2. Generate orders via OrderGenerator (seeded for reproducibility)
    3. Generate tasks via TaskGenerator
    4. Simulate task completion (time-stepped, not real-time)
    5. Compute KPIs via KPITracker
    """

    def __init__(
        self,
        db,
        scenario_id: str,
        config: dict,
        warehouse_config: dict,
        robot_config: dict,
    ):
        """
        Args:
            db: Motor database instance.
            scenario_id: UUID for namespace isolation.
            config: Scenario config (fleet_size, order_count, etc.).
            warehouse_config: Parsed warehouse JSON.
            robot_config: Parsed robot YAML.
        """
        self._db = db
        self._scenario_id = scenario_id
        self._config = config
        self._warehouse_config = warehouse_config
        self._robot_config = robot_config

        # Build graph for distance computation
        self._node_positions = self._build_node_positions(warehouse_config)
        self._adjacency = self._build_adjacency(warehouse_config)

        # Robot velocity from config (m/s)
        motion = robot_config.get("motion", {})
        self._robot_velocity = motion.get("max_linear_velocity", 2.0)

        # Pick/drop times from attachment config
        attachment = robot_config.get("attachment", {})
        self._load_time_s = attachment.get("load_time_s", 3.0)
        self._unload_time_s = attachment.get("unload_time_s", 3.0)

    @staticmethod
    def _build_node_positions(warehouse_config: dict) -> dict[str, tuple[float, float]]:
        """Map node names to (x, y) positions."""
        positions = {}
        for node in warehouse_config.get("nodes", []):
            positions[node["name"]] = (float(node["x"]), float(node["y"]))
        return positions

    @staticmethod
    def _build_adjacency(warehouse_config: dict) -> dict[str, list[str]]:
        """Build bidirectional adjacency list from edges."""
        adj: dict[str, list[str]] = {}
        for edge in warehouse_config.get("edges", []):
            a, b = edge["from"], edge["to"]
            adj.setdefault(a, []).append(b)
            adj.setdefault(b, []).append(a)
        return adj

    def _graph_distance(self, start: str, end: str) -> float:
        """
        BFS shortest path distance through the warehouse graph.

        Returns Euclidean distance along the path (sum of edge lengths).
        Falls back to direct Euclidean if nodes not in graph.
        """
        if start == end:
            return 0.0

        if start not in self._adjacency or end not in self._adjacency:
            # Fallback: direct Euclidean
            return self._euclidean(start, end)

        # BFS for shortest path (unweighted hop count, then compute distance)
        visited = {start}
        queue = deque([(start, [start])])

        while queue:
            current, path = queue.popleft()
            if current == end:
                # Compute path distance
                total = 0.0
                for i in range(len(path) - 1):
                    total += self._euclidean(path[i], path[i + 1])
                return total
            for neighbor in self._adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))

        # No path found — fallback to direct Euclidean
        return self._euclidean(start, end)

    def _euclidean(self, a: str, b: str) -> float:
        """Euclidean distance between two nodes."""
        pos_a = self._node_positions.get(a, (0.0, 0.0))
        pos_b = self._node_positions.get(b, (0.0, 0.0))
        dx = pos_a[0] - pos_b[0]
        dy = pos_a[1] - pos_b[1]
        return math.sqrt(dx * dx + dy * dy)

    def _estimate_task_time(self, task: dict) -> float:
        """
        Estimate wall-clock seconds for a task.

        travel_time = graph_distance / robot_velocity
        total = travel_time + load_time + unload_time
        """
        source = task.get("source_node", "")
        dest = task.get("destination_node", "")
        distance = self._graph_distance(source, dest)
        travel_time = distance / max(self._robot_velocity, 0.01)
        return travel_time + self._load_time_s + self._unload_time_s

    async def execute(self, duration_s: float) -> dict:
        """
        Execute the scenario simulation.

        1. Create robot docs in namespace
        2. Generate orders via OrderGenerator (seeded)
        3. Generate tasks via TaskGenerator
        4. Simulate task completion (time-stepped)
        5. Compute KPIs via KPITracker

        Args:
            duration_s: Simulation duration in seconds.

        Returns:
            KPI dict from KPITracker.
        """
        config = self._config
        fleet_size = config.get("fleet_size", 5)
        order_count = config.get("order_count", 50)
        seed = config.get("order_seed")
        strategy = config.get("allocation_strategy", "fifo")

        # 1. Create robot docs
        robots = self._create_robots(fleet_size)

        # 2. Generate orders (seeded for reproducibility)
        nodes = self._warehouse_config.get("nodes", [])
        pick_nodes = [n["name"] for n in nodes if n.get("type") == "pick"]
        drop_nodes = [n["name"] for n in nodes if n.get("type") == "drop"]

        order_gen = OrderGenerator(
            pick_nodes=pick_nodes,
            drop_nodes=drop_nodes,
            seed=seed,
        )
        orders = order_gen.generate_batch(order_count)

        # 3. Generate tasks
        task_gen = TaskGenerator()
        tasks = task_gen.from_orders(orders)

        # 4. Time-stepped simulation
        sim_time = 0.0
        base_time = time.time()

        # Set order created_at to simulation start
        for order in orders:
            order["created_at"] = base_time

        # Assign tasks to robots and simulate completion
        task_queue = list(tasks)  # copy to consume
        robot_busy_until = {r["robot_id"]: 0.0 for r in robots}
        # Track each robot's current node for nearest-strategy distance calc
        robot_current_node = {r["robot_id"]: r.get("current_node", "DOCK_1") for r in robots}

        # Sort tasks by priority (descending) for priority_weighted
        if strategy == "priority_weighted":
            task_queue.sort(key=lambda t: t.get("priority", 0), reverse=True)

        completed_tasks = []
        failed_tasks = []

        while task_queue and sim_time < duration_s:
            # Find the next available robot
            if strategy == "nearest":
                # For nearest: pick the robot closest (by graph distance) to the task source
                task = task_queue[0]
                task_source = task.get("source_node", "")
                best_robot = None
                best_score = float("inf")
                for rid, busy_until in robot_busy_until.items():
                    available_at = max(busy_until, sim_time)
                    # Graph distance from robot's current node to task source
                    travel_dist = self._graph_distance(robot_current_node[rid], task_source)
                    # Score: available_at + travel_time (distance / velocity)
                    travel_time = travel_dist / max(self._robot_velocity, 0.01)
                    score = available_at + travel_time
                    if score < best_score:
                        best_score = score
                        best_robot = rid
                if best_robot is None:
                    break
                available_time = max(robot_busy_until[best_robot], sim_time)
                task_queue.pop(0)
            else:
                # FIFO or priority_weighted: assign to first available robot
                # Find earliest-available robot
                best_robot = min(robot_busy_until, key=robot_busy_until.get)
                available_time = max(robot_busy_until[best_robot], sim_time)
                task = task_queue.pop(0)

            # Estimate task duration (includes travel from source to destination + load/unload)
            task_duration = self._estimate_task_time(task)

            # For nearest strategy, add travel from robot's current node to task source
            if strategy == "nearest":
                approach_dist = self._graph_distance(
                    robot_current_node[best_robot], task.get("source_node", "")
                )
                approach_time = approach_dist / max(self._robot_velocity, 0.01)
                task_duration += approach_time

            # Task starts when robot is available
            task_start = available_time
            task_end = task_start + task_duration

            if task_end > duration_s:
                # Task won't complete within duration — mark as pending
                break

            # Mark task as completed
            task["status"] = "completed"
            task["assigned_robot_id"] = best_robot
            task["assigned_at"] = base_time + task_start
            task["started_at"] = base_time + task_start
            task["completed_at"] = base_time + task_end
            completed_tasks.append(task)

            # Update robot availability and current node (robot ends at task destination)
            robot_busy_until[best_robot] = task_end
            robot_current_node[best_robot] = task.get("destination_node", robot_current_node[best_robot])

            # Advance simulation time
            sim_time = task_end

        # Mark remaining tasks as pending (not completed in time)
        for task in task_queue:
            task["status"] = "pending"

        # Mark orders as completed if all their tasks are completed
        task_status_by_order: dict[str, list[str]] = {}
        for task in tasks:
            oid = task.get("order_id", "")
            task_status_by_order.setdefault(oid, []).append(task["status"])

        for order in orders:
            oid = order["order_id"]
            statuses = task_status_by_order.get(oid, [])
            if statuses and all(s == "completed" for s in statuses):
                order["status"] = "completed"
                # Set completed_at to the latest task completion
                max_completed = max(
                    t["completed_at"] for t in tasks
                    if t.get("order_id") == oid and t.get("completed_at")
                )
                order["completed_at"] = max_completed
            else:
                order["status"] = "pending"

        # 5. Compute KPIs
        kpi_tracker = KPITracker()
        kpis = kpi_tracker.compute(orders, tasks)

        # Store in namespace collections (graceful)
        if self._db is not None:
            try:
                orders_coll = self._db[_collection_name(self._scenario_id, "orders")]
                tasks_coll = self._db[_collection_name(self._scenario_id, "tasks")]
                robots_coll = self._db[_collection_name(self._scenario_id, "robots")]

                if orders:
                    await orders_coll.insert_many([o.copy() for o in orders])
                if tasks:
                    await tasks_coll.insert_many([t.copy() for t in tasks])
                if robots:
                    await robots_coll.insert_many([r.copy() for r in robots])
            except Exception:
                pass

        return kpis

    def _create_robots(self, fleet_size: int) -> list[dict]:
        """Create robot docs for the scenario."""
        robots = []
        for i in range(fleet_size):
            robots.append({
                "robot_id": f"scenario_{self._scenario_id}_robot_{i:03d}",
                "name": f"Robot {i:03d}",
                "status": "idle",
                "battery_pct": self._robot_config.get("battery", {}).get("initial_charge_pct", 100),
                "position": {"x": 0, "y": 0},
                "current_node": "DOCK_1",
            })
        return robots


def _collection_name(scenario_id: str, base: str) -> str:
    """Generate namespaced collection name for scenario isolation."""
    return f"scenario_{scenario_id}_{base}"
