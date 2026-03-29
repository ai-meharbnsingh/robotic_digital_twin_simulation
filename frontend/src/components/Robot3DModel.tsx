import { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'
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

interface Robot3DModelProps {
  rp: RobotPosition3D
  selected: boolean
  onSelect: (id: string) => void
  nodeMap: Map<string, { x: number; y: number }>
}

export function Robot3DModel({ rp, selected, onSelect, nodeMap }: Robot3DModelProps) {
  const meshRef = useRef<THREE.Mesh>(null)
  const batteryRef = useRef<THREE.Mesh>(null)

  const baseColor = TYPE_COLORS[rp.robot_type] ?? '#89dceb'
  const emissive = STATUS_EMISSIVE[rp.status] ?? (selected ? '#89b4fa' : '#000000')

  // Build path line points from node names
  const pathPoints = useMemo(() => {
    if (!rp.path || rp.path.length < 2) return null
    const pts: THREE.Vector3[] = []
    for (const nodeName of rp.path) {
      const n = nodeMap.get(nodeName)
      if (n) pts.push(new THREE.Vector3(n.x, 0.02, n.y))
    }
    return pts.length >= 2 ? pts : null
  }, [rp.path, nodeMap])

  const pathGeometry = useMemo(() => {
    if (!pathPoints) return null
    const geom = new THREE.BufferGeometry().setFromPoints(pathPoints)
    return geom
  }, [pathPoints])

  // Destination marker position
  const destPos = useMemo(() => {
    if (!rp.target_node) return null
    const n = nodeMap.get(rp.target_node)
    if (!n) return null
    return new THREE.Vector3(n.x, 0.05, n.y)
  }, [rp.target_node, nodeMap])

  // Animate mesh position + rotation each frame
  useFrame(() => {
    if (!meshRef.current) return
    meshRef.current.position.copy(rp.current)
    meshRef.current.position.y = 0.2 // lift above floor
    meshRef.current.rotation.y = -rp.theta
  })

  const isOffline = rp.status === 'offline'
  const opacity = isOffline ? 0.3 : 1.0
  const isAGV = rp.robot_type === 'unidirectional'

  return (
    <group>
      {/* Robot body */}
      <mesh
        ref={meshRef}
        onClick={(e) => {
          e.stopPropagation()
          onSelect(rp.robot_id)
        }}
        castShadow
      >
        {isAGV ? (
          <boxGeometry args={[0.6, 0.3, 0.8]} />
        ) : (
          <cylinderGeometry args={[0.3, 0.3, 0.3, 16]} />
        )}
        <meshStandardMaterial
          color={baseColor}
          emissive={emissive}
          emissiveIntensity={selected ? 0.4 : 0.15}
          transparent={isOffline}
          opacity={opacity}
        />

        {/* Battery indicator bar on top */}
        <mesh ref={batteryRef} position={[0, 0.2, 0]}>
          <boxGeometry args={[0.5, 0.05, 0.1]} />
          <meshStandardMaterial color={batteryColor(rp.battery_pct)} />
        </mesh>

        {/* Direction indicator (front arrow) */}
        <mesh position={[0, 0.1, -0.35]} rotation={[Math.PI / 2, 0, 0]}>
          <coneGeometry args={[0.08, 0.15, 4]} />
          <meshStandardMaterial color="#cdd6f4" />
        </mesh>

        {/* Label (HTML overlay) */}
        <Html
          position={[0, 0.6, 0]}
          center
          distanceFactor={15}
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
      </mesh>

      {/* Task path line on floor */}
      {pathGeometry && (
        <line>
          <bufferGeometry attach="geometry" {...pathGeometry} />
          <lineBasicMaterial
            attach="material"
            color={selected ? '#89b4fa' : '#585b70'}
            linewidth={1}
            transparent
            opacity={selected ? 0.8 : 0.3}
          />
        </line>
      )}

      {/* Destination marker */}
      {destPos && rp.current_task_id && (
        <mesh position={destPos}>
          <ringGeometry args={[0.2, 0.35, 16]} />
          <meshBasicMaterial
            color={baseColor}
            transparent
            opacity={0.5}
            side={THREE.DoubleSide}
          />
        </mesh>
      )}

      {/* Selection ring */}
      {selected && meshRef.current && (
        <mesh position={[rp.current.x, 0.02, rp.current.z]} rotation={[-Math.PI / 2, 0, 0]}>
          <ringGeometry args={[0.5, 0.6, 32]} />
          <meshBasicMaterial color="#89b4fa" transparent opacity={0.6} side={THREE.DoubleSide} />
        </mesh>
      )}
    </group>
  )
}
