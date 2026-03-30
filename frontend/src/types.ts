/**
 * TypeScript interfaces matching Python backend response shapes.
 * Contracts verified by python/tests/test_3d_contracts.py.
 */

// --- Enums ---

export type RobotStatus =
  | 'idle'
  | 'moving'
  | 'charging'
  | 'loading'
  | 'unloading'
  | 'error'
  | 'offline'
  | 'docking'
  | 'undocking'
  | 'waiting'

export type TaskStatus =
  | 'pending'
  | 'assigned'
  | 'in_progress'
  | 'completed'
  | 'failed'
  | 'cancelled'

export type TaskType = 'pick' | 'drop' | 'charge' | 'move' | 'pick_and_drop'

export type EventSeverity = 'info' | 'warning' | 'error' | 'critical'

export type NodeType = 'aisle' | 'shelf' | 'charge' | 'pick' | 'drop' | 'hub'

export type ZoneType = 'dock' | 'shelf' | 'ops' | 'aisle' | 'lane' | 'pick'

export type RobotType = 'differential_drive' | 'unidirectional' | 'omnidirectional'

// --- Core Models ---

export interface Pose {
  x: number
  y: number
  theta: number
}

export interface Velocity {
  linear: number
  angular: number
}

export interface BatteryState {
  charge_pct: number
  is_charging: boolean
  voltage: number
  current: number
  temperature_c: number
}

export interface Robot {
  robot_id: string
  name: string
  robot_type: RobotType
  status: RobotStatus
  pose: Pose
  velocity: Velocity
  battery: BatteryState
  current_node: string
  target_node: string
  current_task_id: string | null
  path: string[]
  path_index: number
  errors: string[]
  last_seen: string
  action_code: number
  response_code: number
}

export interface Task {
  task_id: string
  task_type: TaskType
  status: TaskStatus
  assigned_robot_id: string | null
  source_node: string
  destination_node: string
  priority: number
  created_at: string
  assigned_at: string | null
  started_at: string | null
  completed_at: string | null
  payload_kg: number
  error_message: string | null
}

export interface MapNode {
  name: string
  x: number
  y: number
  type: NodeType
}

export interface MapEdge {
  from: string
  to: string
  weight?: number
  bidirectional?: boolean
}

export interface Zone {
  name: string
  type: ZoneType
  nodes: string[]
}

export interface Health {
  status: string
  mongodb_ok: boolean
  redis_ok: boolean
  influxdb_ok: boolean
  rabbitmq_ok: boolean
  warehouse_loaded: boolean
  robot_loaded: boolean
  wes_loaded: boolean
  check_duration_ms: number
}

export interface FleetAnalytics {
  total_tasks: number
  completed_tasks: number
  failed_tasks: number
  avg_task_time_s: number
  total_robots: number
  avg_battery_pct: number
  throughput_tasks_per_hour: number
}

export interface WesKpi {
  orders_per_hour: number
  pick_accuracy_pct: number
  throughput_items_per_hour: number
  avg_order_cycle_time_s: number
  pending_orders: number
  completed_orders: number
  total_orders: number
  completed_tasks: number
  failed_tasks: number
}

// --- Heat Map ---

export interface HeatMapCell {
  x: number
  y: number
  col: number
  row: number
  visit_count: number
  avg_dwell_time_s: number
  intensity: number // 0.0 - 1.0
}

export interface ZoneCongestion {
  zone_name: string
  zone_type: string
  node_count: number
  total_visits: number
  avg_visits_per_node: number
  avg_dwell_time_s: number
  congestion_score: number
}

export interface HeatMapGrid {
  min_x: number
  min_y: number
  max_x: number
  max_y: number
  cols: number
  rows: number
}

export interface HeatMapData {
  duration: string
  resolution_m: number
  data_source: string
  grid: HeatMapGrid
  cells: HeatMapCell[]
  total_positions: number
  cell_count: number
  zones: ZoneCongestion[]
  query_ms: number
}

// --- Waves ---

export type WaveStatus = 'pending' | 'active' | 'completed'

export interface Wave {
  wave_id: string
  status: WaveStatus
  order_ids: string[]
  zone_affinity: string | null
  max_robots: number
  deadline: number | null
  created_at: number
  released_at: number | null
  completed_at: number | null
  task_ids: string[]
}

export interface WaveSummary {
  pending: number
  active: number
  completed: number
}

export interface WavesResponse {
  waves: Wave[]
  count: number
  summary: WaveSummary
}

// --- WebSocket Events ---

export interface RobotPositionEvent {
  event: 'robot_position'
  data: {
    robot_id: string
    pose: Pose
    status: RobotStatus
    current_node: string
  }
}

export interface TaskUpdateEvent {
  event: 'task_update'
  data: {
    task_id: string
    status: TaskStatus
    assigned_robot_id: string | null
  }
}

export interface OtherBroadcastEvent {
  event: 'robot_state_change' | 'collision_alert' | 'deadlock_event' | 'fleet_metrics' | 'wcs_event'
  data: Record<string, unknown>
}

export interface WSControlMessage {
  type: 'connected' | 'pong'
  [key: string]: unknown
}

export type FleetWSEvent = RobotPositionEvent | TaskUpdateEvent | OtherBroadcastEvent | WSControlMessage

// --- Scenarios ---

export type ScenarioStatus = 'created' | 'running' | 'completed' | 'failed' | 'archived'
export type AllocationStrategy = 'fifo' | 'nearest' | 'priority_weighted'

export interface ScenarioConfig {
  name: string
  description: string
  fleet_size: number
  robot_config: string
  allocation_strategy: AllocationStrategy
  warehouse_config: string
  order_count: number
  order_seed: number | null
  duration_s: number
}

export interface Scenario {
  scenario_id: string
  name: string
  status: ScenarioStatus
  config: ScenarioConfig
  created_at: number
  started_at: number | null
  completed_at: number | null
  kpis: WesKpi | null
}

/** Partial response from POST /api/scenarios/{id}/run — not a full Scenario. */
export interface ScenarioRunResult {
  scenario_id: string
  status: 'completed'
  kpis: WesKpi
  completed_at: number
}

export interface ScenarioDelta {
  scenario_id: string
  name: string
  vs_baseline: Record<string, number>
}

export interface ScenarioRanking {
  rank: number
  scenario_id: string
  name: string
  throughput_items_per_hour: number
  avg_order_cycle_time_s: number
}

/** Partial scenario object returned inside a comparison response (no status/timestamps). */
export interface ScenarioComparisonEntry {
  scenario_id: string
  name: string
  config: ScenarioConfig
  kpis: WesKpi
}

export interface ScenarioComparison {
  scenarios: ScenarioComparisonEntry[]
  deltas: ScenarioDelta[]
  rankings: ScenarioRanking[]
  baseline_scenario_id: string
}

// --- Warehouse Designer ---

export interface DesignerNode {
  id: string
  name: string
  x: number
  y: number
  type: NodeType
  zone?: string
}

export interface DesignerEdge {
  id: string
  from: string
  to: string
}

export interface DesignerZone {
  name: string
  type: ZoneType
  nodeIds: string[]
}

export interface DesignerValidation {
  valid: boolean
  errors: string[]
  warnings: string[]
}

/** JSON export format matching configs/warehouses/*.json */
export interface WarehouseConfig {
  name: string
  description: string
  grid_spacing_m: number
  nodes: { name: string; x: number; y: number; type: NodeType }[]
  edges: { from: string; to: string }[]
  zones: { name: string; type: ZoneType; nodes: string[] }[]
}

// --- VDA5050 ---

export interface VDA5050GatewayStatus {
  broker_connected: boolean
  agvs_online: number
  agvs_total: number
  gateway_initialized: boolean
}

export type VDA5050ConnectionState = 'ONLINE' | 'OFFLINE' | 'CONNECTIONBROKEN'

export interface VDA5050AgvError {
  errorType: string
  errorLevel: string
  errorDescription: string
}

export interface VDA5050AgvPosition {
  x: number
  y: number
  theta: number
  mapId: string
}

export interface VDA5050AgvLastState {
  orderId: string
  lastNodeId: string
  agvPosition: VDA5050AgvPosition
  batteryState: { batteryCharge: number; batteryVoltage: number; charging: boolean }
  operatingMode: string
  driving: boolean
  errors: VDA5050AgvError[]
  safetyState: { eStop: string; fieldViolation: boolean }
}

export interface VDA5050AgvState {
  serial_number: string
  last_state: VDA5050AgvLastState
}

// --- ROS2 Bridge ---

export type HardwareMode = 'simulated' | 'ros2_sim' | 'ros2_real'

export interface ROS2BridgeStatus {
  ros2_available: boolean
  bridge_mode: string
  fms_url: string
  subscribed_topics: number
  discovered_nodes: number
  bridge_initialized: boolean
}

export interface ROS2Topic {
  topic_type: string
  template: string
  msg_type: string
  source: 'live' | 'simulated'
}

/** Response from POST /api/ros2/nav-goal (matches python/app/routes/ros2.py + HAL) */
export interface ROS2NavGoalResponse {
  status: 'simulated' | 'sent' | 'error'
  robot_id: string
  goal: { x: number; y: number; theta: number }
  mode: HardwareMode
  timestamp: number
  topic?: string          // present when ROS2 is live
  error?: string          // present when status='error'
}

// --- MAPF / Congestion (Phase 11) ---

export interface CongestionMap {
  [node_id: string]: {
    occupancy: number
    wait_time_avg: number
    throughput: number
  }
}

export interface Bottleneck {
  node_id: string
  occupancy: number
  wait_time_avg: number
  throughput: number
}

export interface MAPFSolveResult {
  paths?: Record<string, string[]>
  moves?: Record<string, string>
  cost?: number
  conflicts_resolved?: number
  solve_time_ms: number
  success: boolean
}

export interface MAPFStatus {
  last_solve_time_ms: number
  last_conflicts_resolved: number
  total_solves: number
}

export interface MAPFBenchmarkEntry {
  solver: string
  agent_count: number
  solve_time_ms: number
  conflicts_resolved?: number
  success: boolean
}

/** Response from GET /api/ros2/pose/{robot_id} (matches python/app/routes/ros2.py + HAL) */
export interface ROS2PoseResponse {
  robot_id: string
  pose: Pose
  source: 'simulated' | 'ros2' | 'error'
  mode: HardwareMode
  topic?: string          // present when ROS2 is live
  error?: string          // present when source='error'
}

// --- WMS/ERP Connector (Phase 12) ---

export interface WMSDlqStatus {
  total: number
  dead: number
  retrying: number
  rabbitmq_connected: boolean
}

export interface WMSStatus {
  connector_initialized: boolean
  type: string | null
  connected: boolean
  dlq: WMSDlqStatus
  // Webhook-specific
  pending_orders?: number
  processed_orders?: number
  callback_url?: string
  // SAP-specific
  base_url?: string
  // Odoo-specific
  url?: string
  database?: string
  authenticated?: boolean
}

export interface WMSOrder {
  order_id: string
  source: 'sap' | 'odoo' | 'webhook'
  items: { sku: string; quantity: number; location: string }[]
  priority: number
  customer: string
  created_at: string
  raw: Record<string, unknown>
}

export interface WMSOrdersResponse {
  orders: WMSOrder[]
  total: number
}

export interface WMSDlqEntry {
  message_id: string
  order: Record<string, unknown>
  error: string
  enqueued_at: number
  retry_count: number
  status: 'dead' | 'retrying'
}

export interface WMSDlqResponse {
  dead_letters: WMSDlqEntry[]
  total: number
  rabbitmq_connected: boolean
}
