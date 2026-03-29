import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html, Line } from '@react-three/drei'
import * as THREE from 'three'
import type { RobotPosition3D } from '../hooks/useRobotPositions'

// Match 2D dashboard color scheme
const TYPE_COLORS: Record<string, string> = {
  differential_drive: '#89dceb', // cyan — AMR
  unidirectional: '#fab387',     // orange — AGV
  omnidirectional: '#cba6f7',    // purple — OMNI
}

const STATUS_EMISSIVE: Record<string, string> = {
  error: '#f38ba8',
  offline: '#45475a',
  charging: '#a6e3a1',
}

function batteryColor(pct: number): string {
  if (pct > 60) return '#a6e3a1'  // green
  if (pct > 30) return '#f9e2af'  // yellow
  return '#f38ba8'                 // red
}

/** Shared geometry pool — created once in Scene, passed to all robot instances */
export interface RobotGeometryPool {
  amrBody: THREE.CylinderGeometry
  agvBody: THREE.BoxGeometry
  batteryBar: THREE.BoxGeometry
  directionCone: THREE.ConeGeometry
  destRing: THREE.RingGeometry
  selectRing: THREE.RingGeometry
}

interface Robot3DModelProps {
  rp: RobotPosition3D
  selected: boolean
  onSelect: (id: string) => void
  nodeMap: Map<string, { x: number; y: number }>
  geoPool: RobotGeometryPool
}

export function Robot3DModel({ rp, selected, onSelect, nodeMap, geoPool }: Robot3DModelProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const ringRef = useRef<THREE.Mesh>(null)

  const baseColor = TYPE_COLORS[rp.robot_type] ?? '#89dceb'
  const emissive = STATUS_EMISSIVE[rp.status] ?? (selected ? '#89b4fa' : '#000000')

  const pathPoints = useMemo((): [number, number, number][] | null => {
    if (!rp.path || rp.path.length < 2) return null
    const pts: [number, number, number][] = []
    for (const nodeName of rp.path) {
      const n = nodeMap.get(nodeName)
      if (n) pts.push([n.x, 0.02, n.y])
    }
    return pts.length >= 2 ? pts : null
  }, [rp.path, nodeMap])

  const destPos = useMemo((): [number, number, number] | null => {
    if (!rp.target_node) return null
    const n = nodeMap.get(rp.target_node)
    if (!n) return null
    return [n.x, 0.05, n.y]
  }, [rp.target_node, nodeMap])

  useFrame(() => {
    if (meshRef.current) {
      meshRef.current.position.copy(rp.current)
      meshRef.current.position.y = 0.2
      meshRef.current.rotation.y = -rp.theta
    }
    if (ringRef.current) {
      ringRef.current.position.set(rp.current.x, 0.02, rp.current.z)
    }
  })

  const isOffline = rp.status === 'offline'
  const opacity = isOffline ? 0.3 : 1.0
  const isAGV = rp.robot_type === 'unidirectional'

  return (
    <group>
      <mesh
        ref={meshRef}
        geometry={isAGV ? geoPool.agvBody : geoPool.amrBody}
        onClick={(e) => {
          e.stopPropagation()
          onSelect(rp.robot_id)
        }}
        castShadow
      >
        <meshStandardMaterial
          color={baseColor}
          emissive={emissive}
          emissiveIntensity={selected ? 0.4 : 0.15}
          transparent={isOffline}
          opacity={opacity}
        />

        {/* Battery indicator bar — shared geometry */}
        <mesh geometry={geoPool.batteryBar} position={[0, 0.2, 0]}>
          <meshStandardMaterial color={batteryColor(rp.battery_pct)} />
        </mesh>

        {/* Direction cone — shared geometry */}
        <mesh geometry={geoPool.directionCone} position={[0, 0.1, -0.35]} rotation={[Math.PI / 2, 0, 0]}>
          <meshStandardMaterial color="#cdd6f4" />
        </mesh>

        {/* Label — only for selected or low battery */}
        {(selected || rp.battery_pct < 30) && (
          <Html
            position={[0, 0.6, 0]}
            center
            distanceFactor={12}
            style={{ pointerEvents: 'none' }}
          >
            <div
              style={{
                background: selected ? 'rgba(137,180,250,0.9)' : 'rgba(30,30,46,0.85)',
                color: selected ? '#1e1e2e' : '#cdd6f4',
                padding: '2px 6px',
                borderRadius: 3,
                fontSize: 10,
                fontFamily: 'monospace',
                whiteSpace: 'nowrap',
                border: selected ? '1px solid #89b4fa' : '1px solid #313244',
              }}
            >
              {rp.name}
              {rp.battery_pct < 30 && ' ⚡'}
            </div>
          </Html>
        )}
      </mesh>

      {pathPoints && (
        <Line
          points={pathPoints}
          color={selected ? '#89b4fa' : '#585b70'}
          lineWidth={1}
          transparent
          opacity={selected ? 0.8 : 0.3}
        />
      )}

      {destPos && rp.current_task_id && (
        <mesh geometry={geoPool.destRing} position={destPos}>
          <meshBasicMaterial
            color={baseColor}
            transparent
            opacity={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {selected && (
        <mesh ref={ringRef} geometry={geoPool.selectRing} rotation={[-Math.PI / 2, 0, 0]}>
          <meshBasicMaterial color="#89b4fa" transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
      )}
    </group>
  )
}
