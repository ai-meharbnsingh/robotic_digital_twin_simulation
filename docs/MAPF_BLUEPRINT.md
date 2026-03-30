# MAPF Scaling Blueprint — Phase 11

Multi-Agent Path Finding (MAPF) for 100+ robot fleets. This document describes the architecture, algorithms, scaling limits, and integration patterns.

---

## Overview

The system provides two complementary MAPF algorithms:

| Algorithm | Type | Complexity | Use Case | Limit |
|-----------|------|------------|----------|-------|
| **CBS** | Optimal | Exponential | Offline batch planning | ≤50 agents (hard: 200) |
| **PIBT** | Suboptimal | Linear | Real-time 15Hz FMS loop | ≤500 agents |

---

## Algorithms

### CBS (Conflict-Based Search)

Two-level search algorithm:

1. **High level**: Search over conflicts (constraint tree)
   - Each node represents a set of constraints
   - Branch on conflicts: create child nodes with additional constraints
2. **Low level**: Single-agent A* with time-space constraints
   - Vertex constraints: cannot be at node at time t
   - Edge constraints: cannot traverse edge at time t

**Heuristic**: 0 if at goal, 1 if neighbor, else 2+. Admissible for unweighted graphs.

**Time limit**: Configurable (default 5s). Returns best-effort solution on timeout.

### PIBT (Priority Inheritance with Backtracking)

Single-pass greedy algorithm:

1. Sort agents by priority (highest first)
2. For each agent, try to move toward goal
3. If blocked by lower-priority agent, that agent inherits priority and moves first
4. If backtracking fails, agent waits

**Cycle detection**: Call stack tracking prevents infinite recursion.

**Performance**: ~32ms for 100 agents (meets 15Hz requirement).

---

## Scaling Limits

### CBS Scaling

| Agents | Typical Time | Success Rate | Notes |
|--------|--------------|--------------|-------|
| 2-10 | <100ms | 100% | Reliable for corridor conflicts |
| 10-20 | 1-3s | 95%+ | Dense scenarios may timeout |
| 20-50 | 3-10s | 70% | Best-effort on timeout |
| 50-200 | 5s (timeout) | <50% | Not recommended |

**Recommendation**: Use CBS for ≤20 agents or sparse scenarios. Use PIBT for dense/large fleets.

### PIBT Scaling

| Agents | Step Time | 15Hz Compatible | Notes |
|--------|-----------|-----------------|-------|
| 10 | <5ms | Yes | Negligible overhead |
| 50 | <15ms | Yes | Smooth real-time |
| 100 | ~32ms | Yes | Meets 67ms deadline |
| 200 | ~60ms | Yes | Near limit |
| 500 | ~150ms | No | API limit enforced |

---

## Resource Limits

Enforced at API layer:

```python
MAX_AGENTS_CBS = 200      # Hard limit for CBS
MAX_AGENTS_PIBT = 500     # Hard limit for PIBT
MAX_BENCHMARK_HISTORY = 1000  # Memory cap for metrics
```

**Time limits**: 0.001s – 30s per solve request.

---

## Congestion Tracker

Tracks hotspot metrics for bottleneck detection:

- **Occupancy**: Total robot-ticks at node
- **Wait time avg**: Average consecutive ticks a robot stays
- **Throughput**: Unique robots passing through

Use `get_bottlenecks(top_n=5)` to identify congestion points for dynamic rerouting.

---

## Integration Patterns

### Pattern 1: Offline Batch Planning (CBS)

```python
# Pre-plan routes for a wave of orders
response = requests.post("/api/mapf/solve", json={
    "solver": "cbs",
    "agents": [{"agent_id": r.id, "start": r.position, "goal": r.target} for r in robots],
    "time_limit_s": 10.0
})
paths = response.json()["paths"]
# Assign paths to robots for execution
```

### Pattern 2: Real-time FMS Loop (PIBT)

```python
# In 15Hz FMS control loop
while running:
    state = get_robot_states()
    response = requests.post("/api/mapf/step", json={
        "agents": [{
            "agent_id": r.id,
            "position": r.position,
            "goal": r.target,
            "priority": r.task_priority,
            "wait_time": r.stuck_ticks
        } for r in robots]
    })
    moves = response.json()["moves"]
    apply_moves(moves)
    time.sleep(1/15)
```

### Pattern 3: Hybrid (CBS + PIBT Fallback)

```python
# Try CBS first, fall back to PIBT on timeout
result = cbs_solve(agents, time_limit=2.0)
if not result["success"]:
    result = pibt_step(agents)  # Guaranteed to return
```

---

## API Endpoints

| Endpoint | Method | Auth | Description |
|----------|--------|------|-------------|
| `/api/mapf/solve` | POST | Yes | CBS or PIBT solve |
| `/api/mapf/step` | POST | Yes | Single PIBT step (15Hz) |
| `/api/mapf/status` | GET | No | Solver metrics |
| `/api/mapf/benchmarks` | GET | No | Performance history |

---

## Testing

28 tests cover:

- CBS: 2-100 agents, head-on conflicts, time limits, edge cases
- PIBT: Single step, 10-100 agents, priority inheritance, no collisions
- Graph building: Grid conversion, bidirectional edges
- Congestion: Occupancy tracking, bottleneck detection
- Endpoints: All 4 endpoints, auth, validation

Run: `pytest tests/test_mapf.py -v`

---

## Future Work

1. **Parallel CBS**: Multi-thread constraint tree expansion
2. **Weighted PIBT**: Add lookahead for better suboptimality bounds
3. **Dynamic obstacles**: Integrate with congestion tracker for hotspot avoidance
4. **Lifelong MAPF**: Continuous replanning for persistent goals
5. **ECBS**: Suboptimal variant of CBS for better 20-50 agent scaling

---

## References

- Sharon, G., et al. "Conflict-based search for optimal multi-agent pathfinding." AAAI 2012.
- Okumura, K., et al. "Priority Inheritance with Backtracking for Iterative Multi-agent Path Finding." IJCAI 2019.
