"""
ScenarioManager — manages scenario lifecycle for parallel comparison.

Create, run, fetch results, compare, and cleanup scenarios.
Each scenario runs in an isolated DB namespace (scenario_{id}_{collection}).

Phase 6: Parallel Scenario Comparison.
"""

import logging
import time
import uuid
from typing import Any, Optional

from app.config import load_warehouse_config, load_robot_config

logger = logging.getLogger(__name__)


class ScenarioNotFoundError(KeyError):
    """Raised when a scenario ID does not exist in the database."""
    pass


class ScenarioNotCompletedError(ValueError):
    """Raised when a scenario is accessed for results but is not yet completed."""
    pass


class ScenarioPersistenceError(RuntimeError):
    """Raised when a MongoDB write (insert/update/drop) fails."""
    pass


class ScenarioManager:
    """
    Manages scenario lifecycle: create, run, results, compare, cleanup.

    Usage:
        manager = ScenarioManager(db, warehouse_config_loader, robot_config_loader)
        scenario = await manager.create_scenario(config)
        result = await manager.run_scenario(scenario["scenario_id"])
        comparison = await manager.compare_scenarios([id_a, id_b])
    """

    def __init__(self, db, warehouse_config_loader=None, robot_config_loader=None):
        """
        Args:
            db: Motor database instance.
            warehouse_config_loader: Callable that loads warehouse config by name.
            robot_config_loader: Callable that loads robot config by name.
        """
        self._db = db
        self._load_warehouse = warehouse_config_loader or load_warehouse_config
        self._load_robot = robot_config_loader or load_robot_config

    def _validate_warehouse_config(self, name: str) -> bool:
        """Check if warehouse config exists."""
        try:
            self._load_warehouse(name)
            return True
        except (FileNotFoundError, Exception):
            return False

    def _validate_robot_config(self, name: str) -> bool:
        """Check if robot config exists."""
        try:
            self._load_robot(name)
            return True
        except (FileNotFoundError, Exception):
            return False

    async def create_scenario(self, config: dict) -> dict:
        """
        Create scenario doc in 'scenarios' collection.

        Args:
            config: Scenario configuration with name, fleet_size, etc.

        Returns:
            Scenario doc with scenario_id, name, status='created', config, created_at.

        Raises:
            ValueError: If warehouse or robot config doesn't exist.
        """
        warehouse_name = config.get("warehouse_config", "simple_grid")
        robot_name = config.get("robot_config", "differential_drive")

        if not self._validate_warehouse_config(warehouse_name):
            raise ValueError(f"Warehouse config not found: {warehouse_name}")
        if not self._validate_robot_config(robot_name):
            raise ValueError(f"Robot config not found: {robot_name}")

        scenario_id = str(uuid.uuid4())
        scenario = {
            "scenario_id": scenario_id,
            "name": config["name"],
            "description": config.get("description", ""),
            "status": "created",
            "config": {
                "fleet_size": config.get("fleet_size", 5),
                "robot_config": robot_name,
                "allocation_strategy": config.get("allocation_strategy", "fifo"),
                "warehouse_config": warehouse_name,
                "order_count": config.get("order_count", 50),
                "order_seed": config.get("order_seed"),
                "duration_s": config.get("duration_s", 60),
            },
            "created_at": time.time(),
            "completed_at": None,
            "kpis": None,
        }

        if self._db is not None:
            try:
                await self._db["scenarios"].insert_one(scenario.copy())
            except Exception as exc:
                logger.error("Failed to persist scenario %s: %s", scenario_id, exc)
                raise ScenarioPersistenceError(
                    f"Failed to persist scenario {scenario_id}: {exc}"
                ) from exc

        return _strip_id(scenario)

    async def list_scenarios(self) -> list[dict]:
        """List all scenarios.

        Raises:
            ScenarioPersistenceError: If MongoDB query fails.
        """
        if self._db is None:
            return []
        try:
            scenarios = await self._db["scenarios"].find(
                {}, {"_id": 0}
            ).to_list(length=10000)
            return scenarios
        except Exception as exc:
            logger.error("Failed to list scenarios: %s", exc)
            raise ScenarioPersistenceError(
                f"Failed to list scenarios: {exc}"
            ) from exc

    async def count_active_scenarios(self) -> int:
        """Count non-archived scenarios (for limit enforcement).

        Raises:
            ScenarioPersistenceError: If MongoDB query fails.
        """
        if self._db is None:
            return 0
        try:
            return await self._db["scenarios"].count_documents(
                {"status": {"$ne": "archived"}}
            )
        except Exception as exc:
            logger.error("Failed to count active scenarios: %s", exc)
            raise ScenarioPersistenceError(
                f"Failed to count active scenarios: {exc}"
            ) from exc

    async def run_scenario(self, scenario_id: str, duration_override: Optional[float] = None) -> dict:
        """
        Execute scenario: generate orders, simulate tasks, compute KPIs.

        Args:
            scenario_id: UUID of the scenario to run.
            duration_override: Optional override for simulation duration in seconds.

        Returns:
            Dict with status='completed' and kpis.

        Raises:
            KeyError: If scenario not found.
            ValueError: If scenario status is invalid for running.
        """
        # Atomic conditional update: set status='running' only if currently 'created' or 'completed'
        # This prevents concurrent double-run (two callers cannot both pass the filter)
        try:
            scenario = await self._db["scenarios"].find_one_and_update(
                {
                    "scenario_id": scenario_id,
                    "status": {"$in": ["created", "completed"]},
                },
                {"$set": {"status": "running", "started_at": time.time()}},
                return_document=True,
                projection={"_id": 0},
            )
        except Exception as exc:
            logger.error("Failed to acquire run lock: %s", exc)
            raise ScenarioPersistenceError("Failed to update scenario status") from exc

        if scenario is None:
            # Either not found or status was not runnable
            existing = await self._get_scenario(scenario_id)
            if existing is None:
                raise ScenarioNotFoundError(f"Scenario not found: {scenario_id}")
            raise ScenarioNotCompletedError(
                f"Scenario {scenario_id} has status '{existing.get('status')}', cannot run"
            )

        config = scenario["config"]
        duration = duration_override or config["duration_s"]

        # Load configs
        warehouse_config = self._load_warehouse(config["warehouse_config"])
        robot_config = self._load_robot(config["robot_config"])

        # Run via ScenarioRunner
        from wes.scenario_runner import ScenarioRunner

        runner = ScenarioRunner(
            db=self._db,
            scenario_id=scenario_id,
            config=config,
            warehouse_config=warehouse_config,
            robot_config=robot_config,
        )
        kpis = await runner.execute(duration_s=duration)

        # Update scenario in DB
        now = time.time()
        if self._db is not None:
            try:
                await self._db["scenarios"].update_one(
                    {"scenario_id": scenario_id},
                    {"$set": {
                        "status": "completed",
                        "completed_at": now,
                        "kpis": kpis,
                    }},
                )
            except Exception as exc:
                logger.error("Failed to update scenario %s after run: %s", scenario_id, exc)
                raise ScenarioPersistenceError(
                    f"Failed to update scenario {scenario_id} after run: {exc}"
                ) from exc

        return {
            "scenario_id": scenario_id,
            "status": "completed",
            "kpis": kpis,
            "completed_at": now,
        }

    async def get_results(self, scenario_id: str) -> dict:
        """
        Get KPIs for a completed scenario.

        Args:
            scenario_id: UUID of the scenario.

        Returns:
            Dict with scenario_id, status, kpis.

        Raises:
            KeyError: If scenario not found.
            ValueError: If scenario not completed.
        """
        scenario = await self._get_scenario(scenario_id)
        if scenario is None:
            raise ScenarioNotFoundError(f"Scenario not found: {scenario_id}")
        if scenario["status"] != "completed":
            raise ScenarioNotCompletedError(
                f"Scenario {scenario_id} is '{scenario['status']}', not completed"
            )
        return {
            "scenario_id": scenario_id,
            "name": scenario["name"],
            "status": "completed",
            "config": scenario["config"],
            "kpis": scenario["kpis"],
            "completed_at": scenario.get("completed_at"),
        }

    async def compare_scenarios(self, scenario_ids: list[str]) -> dict:
        """
        Compare 2+ completed scenarios.

        Args:
            scenario_ids: List of scenario UUIDs to compare.

        Returns:
            Dict with scenarios, deltas (vs first as baseline), and rankings.

        Raises:
            ValueError: If fewer than 2 IDs provided.
            KeyError: If any scenario not found or not completed.
        """
        if len(scenario_ids) < 2:
            raise ValueError("Need at least 2 scenario IDs to compare")

        results = []
        for sid in scenario_ids:
            res = await self.get_results(sid)
            results.append(res)

        # Baseline is the first scenario
        baseline_kpis = results[0]["kpis"]

        # Compute deltas relative to baseline
        deltas = []
        for res in results[1:]:
            delta = {}
            for key in baseline_kpis:
                baseline_val = baseline_kpis.get(key, 0)
                compare_val = res["kpis"].get(key, 0)
                if isinstance(baseline_val, (int, float)) and isinstance(compare_val, (int, float)):
                    delta[key] = round(compare_val - baseline_val, 4)
            deltas.append({
                "scenario_id": res["scenario_id"],
                "name": res["name"],
                "vs_baseline": delta,
            })

        # Rankings: rank by throughput (higher = better), then by cycle time (lower = better)
        ranked = sorted(
            results,
            key=lambda r: (
                r["kpis"].get("throughput_items_per_hour", 0),
                -r["kpis"].get("avg_order_cycle_time_s", float("inf")),
            ),
            reverse=True,
        )
        rankings = []
        for rank, res in enumerate(ranked, 1):
            rankings.append({
                "rank": rank,
                "scenario_id": res["scenario_id"],
                "name": res["name"],
                "throughput_items_per_hour": res["kpis"].get("throughput_items_per_hour", 0),
                "avg_order_cycle_time_s": res["kpis"].get("avg_order_cycle_time_s", 0),
            })

        return {
            "scenarios": [
                {
                    "scenario_id": r["scenario_id"],
                    "name": r["name"],
                    "config": r["config"],
                    "kpis": r["kpis"],
                }
                for r in results
            ],
            "deltas": deltas,
            "rankings": rankings,
            "baseline_scenario_id": scenario_ids[0],
        }

    async def cleanup_scenario(self, scenario_id: str) -> dict:
        """
        Drop scenario namespace collections. Set status='archived'.

        Args:
            scenario_id: UUID of the scenario to archive.

        Returns:
            Dict with archived status.
        """
        scenario = await self._get_scenario(scenario_id)
        if scenario is None:
            raise ScenarioNotFoundError(f"Scenario not found: {scenario_id}")

        # Drop namespace collections
        if self._db is not None:
            for base in ("orders", "tasks", "robots"):
                coll_name = self._collection_name(scenario_id, base)
                try:
                    await self._db[coll_name].drop()
                except Exception as exc:
                    logger.error(
                        "Failed to drop collection %s for scenario %s: %s",
                        coll_name, scenario_id, exc,
                    )
                    raise ScenarioPersistenceError(
                        f"Failed to drop collection {coll_name}: {exc}"
                    ) from exc

            # Update status
            try:
                await self._db["scenarios"].update_one(
                    {"scenario_id": scenario_id},
                    {"$set": {"status": "archived"}},
                )
            except Exception as exc:
                logger.error(
                    "Failed to archive scenario %s: %s", scenario_id, exc,
                )
                raise ScenarioPersistenceError(
                    f"Failed to archive scenario {scenario_id}: {exc}"
                ) from exc

        return {"scenario_id": scenario_id, "status": "archived"}

    async def _get_scenario(self, scenario_id: str) -> Optional[dict]:
        """Load a scenario from DB by ID.

        Raises:
            ScenarioPersistenceError: If MongoDB query fails.
        """
        if self._db is None:
            return None
        try:
            return await self._db["scenarios"].find_one(
                {"scenario_id": scenario_id}, {"_id": 0}
            )
        except Exception as exc:
            logger.error("Failed to fetch scenario %s: %s", scenario_id, exc)
            raise ScenarioPersistenceError(
                f"Failed to fetch scenario {scenario_id}: {exc}"
            ) from exc

    @staticmethod
    def _collection_name(scenario_id: str, base: str) -> str:
        """Generate namespaced collection name for scenario isolation."""
        return f"scenario_{scenario_id}_{base}"


def _strip_id(doc: dict) -> dict:
    """Remove MongoDB _id field if present."""
    return {k: v for k, v in doc.items() if k != "_id"}
