/**
 * TypeScript interfaces matching python/app/models.py
 * Used by all dashboard components and hooks.
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

export type ZoneType = 'dock' | 'shelf' | 'ops' | 'aisle'

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
  weight: number
  bidirectional: boolean
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
}

// --- WebSocket Events ---

export interface WSEvent {
  event: string
  data: unknown
}

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

export type FleetWSEvent = RobotPositionEvent | TaskUpdateEvent | WSEvent
