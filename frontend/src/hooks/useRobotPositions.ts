import { useRef, useCallback } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'
import type { Robot, FleetWSEvent } from '../types'

export interface RobotPosition3D {
  robot_id: string
  current: THREE.Vector3
  target: THREE.Vector3
  theta: number
  targetTheta: number
  status: Robot['status']
  robot_type: Robot['robot_type']
  battery_pct: number
  current_node: string
  target_node: string
  path: string[]
  name: string
  current_task_id: string | null
  lastUpdated: number // timestamp of last REST or WS update
}

const LERP_SPEED = 6 // units per second — smooth but responsive
const STALE_TIMEOUT_MS = 15_000 // prune robots with no update for 15s

/**
 * Maintains a map of robot positions with smooth interpolation.
 * Fed by REST (robots[]) for full state and WebSocket events for low-latency updates.
 * Call updateFromRest() when REST data arrives.
 * Call handleWSEvent() on each WebSocket event.
 * useFrame drives the interpolation every render frame.
 */
export function useRobotPositions() {
  const positionsRef = useRef<Map<string, RobotPosition3D>>(new Map())

  const updateFromRest = useCallback(
    (robots: Robot[]) => {
      const map = positionsRef.current
      const seen = new Set<string>()

      for (const r of robots) {
        seen.add(r.robot_id)
        const existing = map.get(r.robot_id)

        // Use pose coordinates (meters, matching warehouse config)
        const tx = r.pose.x
        const tz = r.pose.y // warehouse Y maps to 3D Z

        const now = Date.now()
        if (existing) {
          existing.target.set(tx, 0, tz)
          existing.targetTheta = r.pose.theta
          existing.status = r.status
          existing.robot_type = r.robot_type
          existing.battery_pct = r.battery.charge_pct
          existing.current_node = r.current_node
          existing.target_node = r.target_node
          existing.path = r.path
          existing.name = r.name
          existing.current_task_id = r.current_task_id
          existing.lastUpdated = now
        } else {
          map.set(r.robot_id, {
            robot_id: r.robot_id,
            current: new THREE.Vector3(tx, 0, tz),
            target: new THREE.Vector3(tx, 0, tz),
            theta: r.pose.theta,
            targetTheta: r.pose.theta,
            status: r.status,
            robot_type: r.robot_type,
            battery_pct: r.battery.charge_pct,
            current_node: r.current_node,
            target_node: r.target_node,
            path: r.path,
            name: r.name,
            current_task_id: r.current_task_id,
            lastUpdated: now,
          })
        }
      }

      // Prune robots: remove if absent from REST AND stale (no update for 15s)
      // This handles both genuine fleet removal and ghost robots from transient failures
      const now2 = Date.now()
      for (const [key, rp] of map.entries()) {
        if (!seen.has(key) && (now2 - rp.lastUpdated) > STALE_TIMEOUT_MS) {
          map.delete(key)
        }
      }
    },
    [],
  )

  const handleWSEvent = useCallback(
    (event: FleetWSEvent) => {
      if (event.event !== 'robot_position') return
      const d = event.data as Record<string, unknown>
      // Runtime validation — guard against malformed WS events
      if (
        typeof d?.robot_id !== 'string' ||
        !d.pose ||
        typeof (d.pose as Record<string, unknown>).x !== 'number' ||
        typeof (d.pose as Record<string, unknown>).y !== 'number'
      ) return

      const pose = d.pose as { x: number; y: number; theta: number }
      const robotId = d.robot_id as string
      const existing = positionsRef.current.get(robotId)

      const now = Date.now()
      if (existing) {
        existing.target.set(pose.x, 0, pose.y)
        if (typeof pose.theta === 'number') existing.targetTheta = pose.theta
        if (typeof d.status === 'string') existing.status = d.status as Robot['status']
        if (typeof d.current_node === 'string') existing.current_node = d.current_node
        existing.lastUpdated = now
      } else {
        // WS arrived before REST — create provisional entry so robot appears immediately
        positionsRef.current.set(robotId, {
          robot_id: robotId,
          current: new THREE.Vector3(pose.x, 0, pose.y),
          target: new THREE.Vector3(pose.x, 0, pose.y),
          theta: pose.theta ?? 0,
          targetTheta: pose.theta ?? 0,
          status: (d.status as Robot['status']) ?? 'idle',
          robot_type: 'differential_drive',
          battery_pct: 100,
          current_node: (d.current_node as string) ?? '',
          target_node: '',
          path: [],
          name: robotId,
          current_task_id: null,
          lastUpdated: now,
        })
      }
    },
    [],
  )

  // Interpolate positions every frame
  useFrame((_, delta) => {
    const t = Math.min(1, delta * LERP_SPEED)
    for (const rp of positionsRef.current.values()) {
      rp.current.lerp(rp.target, t)
      // Shortest-arc angle interpolation
      let dTheta = rp.targetTheta - rp.theta
      if (dTheta > Math.PI) dTheta -= 2 * Math.PI
      if (dTheta < -Math.PI) dTheta += 2 * Math.PI
      rp.theta += dTheta * t
    }
  })

  return { positionsRef, updateFromRest, handleWSEvent }
}
