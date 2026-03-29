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
}

const LERP_SPEED = 6 // units per second — smooth but responsive

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
          })
        }
      }

      // Remove robots that no longer appear in REST — but only if REST
      // returned a non-empty list (empty = transient API failure, not fleet deletion)
      if (robots.length > 0) {
        for (const key of map.keys()) {
          if (!seen.has(key)) map.delete(key)
        }
      }
    },
    [],
  )

  const handleWSEvent = useCallback(
    (event: FleetWSEvent) => {
      if (event.event !== 'robot_position') return
      const d = event.data as {
        robot_id: string
        pose: { x: number; y: number; theta: number }
        status: string
        current_node: string
      }
      const existing = positionsRef.current.get(d.robot_id)
      if (!existing) return

      existing.target.set(d.pose.x, 0, d.pose.y)
      existing.targetTheta = d.pose.theta
      existing.status = d.status as Robot['status']
      existing.current_node = d.current_node
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
