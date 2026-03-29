import { useEffect, useMemo, useRef } from 'react'
import { Canvas, useThree, useFrame } from '@react-three/fiber'
import { OrbitControls, Grid } from '@react-three/drei'
import * as THREE from 'three'
import { useRobotPositions } from '../hooks/useRobotPositions'
import { Robot3DModel } from './Robot3DModel'
import type { Robot, MapNode, MapEdge, HeatMapCell, FleetWSEvent } from '../types'

// --- Node type colors (matching 2D WarehouseGrid) ---
const NODE_COLORS: Record<string, string> = {
  aisle: '#6c7086',
  shelf: '#89b4fa',
  charge: '#a6e3a1',
  pick: '#f9e2af',
  drop: '#fab387',
  hub: '#cba6f7',
}

const SHELF_HEIGHT = 1.2
const CHARGE_HEIGHT = 0.6
const STATION_HEIGHT = 0.4

// --- Sub-components rendered inside the Canvas ---

function FloorEdges({ edges, nodeMap }: { edges: MapEdge[]; nodeMap: Map<string, { x: number; y: number }> }) {
  const geometry = useMemo(() => {
    const pts: number[] = []
    for (const e of edges) {
      const a = nodeMap.get(e.from)
      const b = nodeMap.get(e.to)
      if (!a || !b) continue
      pts.push(a.x, 0.01, a.y, b.x, 0.01, b.y)
    }
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    return geom
  }, [edges, nodeMap])

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#45475a" transparent opacity={0.4} />
    </lineSegments>
  )
}

function NodeMarkers({ nodes }: { nodes: MapNode[] }) {
  return (
    <group>
      {nodes.map((n) => {
        const color = NODE_COLORS[n.type] ?? '#6c7086'

        if (n.type === 'shelf') {
          return (
            <mesh key={n.name} position={[n.x, SHELF_HEIGHT / 2, n.y]} castShadow receiveShadow>
              <boxGeometry args={[0.7, SHELF_HEIGHT, 0.7]} />
              <meshStandardMaterial color={color} transparent opacity={0.6} />
            </mesh>
          )
        }

        if (n.type === 'charge') {
          return (
            <group key={n.name}>
              <mesh position={[n.x, CHARGE_HEIGHT / 2, n.y]}>
                <cylinderGeometry args={[0.25, 0.3, CHARGE_HEIGHT, 8]} />
                <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.2} />
              </mesh>
              <mesh position={[n.x, CHARGE_HEIGHT + 0.1, n.y]} rotation={[-Math.PI / 2, 0, 0]}>
                <circleGeometry args={[0.15, 6]} />
                <meshBasicMaterial color="#f9e2af" />
              </mesh>
            </group>
          )
        }

        if (n.type === 'pick' || n.type === 'drop') {
          return (
            <mesh key={n.name} position={[n.x, STATION_HEIGHT / 2, n.y]}>
              <boxGeometry args={[0.5, STATION_HEIGHT, 0.5]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.15} />
            </mesh>
          )
        }

        if (n.type === 'hub') {
          return (
            <mesh key={n.name} position={[n.x, 0.3, n.y]}>
              <octahedronGeometry args={[0.35]} />
              <meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.3} />
            </mesh>
          )
        }

        // Aisle: flat disc
        return (
          <mesh key={n.name} position={[n.x, 0.01, n.y]} rotation={[-Math.PI / 2, 0, 0]}>
            <circleGeometry args={[0.12, 12]} />
            <meshBasicMaterial color={color} transparent opacity={0.5} />
          </mesh>
        )
      })}
    </group>
  )
}

function HeatMapOverlay({ cells, resolution }: { cells: HeatMapCell[]; resolution: number }) {
  return (
    <group>
      {cells.map((c, i) => {
        const color = heatColor(c.intensity)
        return (
          <mesh
            key={i}
            position={[c.x + resolution / 2, 0.005, c.y + resolution / 2]}
            rotation={[-Math.PI / 2, 0, 0]}
          >
            <planeGeometry args={[resolution, resolution]} />
            <meshBasicMaterial color={color} transparent opacity={0.35} />
          </mesh>
        )
      })}
    </group>
  )
}

function heatColor(intensity: number): string {
  if (intensity <= 0.5) {
    const t = intensity * 2
    const r = Math.round(166 + (249 - 166) * t)
    const g = Math.round(227 + (226 - 227) * t)
    const b = Math.round(161 + (175 - 161) * t)
    return `rgb(${r},${g},${b})`
  }
  const t = (intensity - 0.5) * 2
  const r = Math.round(249 + (243 - 249) * t)
  const g = Math.round(226 + (139 - 226) * t)
  const b = Math.round(175 + (168 - 175) * t)
  return `rgb(${r},${g},${b})`
}

function CameraFollow({ target, enabled }: { target: THREE.Vector3 | null; enabled: boolean }) {
  const { camera } = useThree()
  const offsetRef = useRef(new THREE.Vector3(3, 6, 3))

  useFrame(() => {
    if (!enabled || !target) return
    const dest = target.clone().add(offsetRef.current)
    camera.position.lerp(dest, 0.03)
    camera.lookAt(target)
  })

  return null
}

// --- Main scene (rendered inside Canvas) ---

interface SceneProps {
  nodes: MapNode[]
  edges: MapEdge[]
  robots: Robot[]
  heatmapCells?: HeatMapCell[]
  heatmapResolution?: number
  heatmapEnabled?: boolean
  selectedRobotId: string | null
  onSelectRobot: (id: string | null) => void
  followMode: boolean
  lastWSEvent: FleetWSEvent | null
}

function Scene({
  nodes,
  edges,
  robots,
  heatmapCells,
  heatmapResolution,
  heatmapEnabled,
  selectedRobotId,
  onSelectRobot,
  followMode,
  lastWSEvent,
}: SceneProps) {
  const nodeMap = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>()
    for (const n of nodes) m.set(n.name, { x: n.x, y: n.y })
    return m
  }, [nodes])

  const { positionsRef, updateFromRest, handleWSEvent } = useRobotPositions()

  // Sync REST data into position system
  useEffect(() => {
    if (robots.length > 0) updateFromRest(robots)
  }, [robots, updateFromRest])

  // Forward WS events to position system
  useEffect(() => {
    if (lastWSEvent) handleWSEvent(lastWSEvent)
  }, [lastWSEvent, handleWSEvent])

  const bounds = useMemo(() => {
    if (nodes.length === 0) return { cx: 0, cz: 0, size: 20 }
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (const n of nodes) {
      if (n.x < minX) minX = n.x
      if (n.x > maxX) maxX = n.x
      if (n.y < minZ) minZ = n.y
      if (n.y > maxZ) maxZ = n.y
    }
    const cx = (minX + maxX) / 2
    const cz = (minZ + maxZ) / 2
    const size = Math.max(maxX - minX, maxZ - minZ) + 4
    return { cx, cz, size }
  }, [nodes])

  // Follow target
  const followTarget = useMemo(() => {
    if (!selectedRobotId) return null
    const rp = positionsRef.current.get(selectedRobotId)
    return rp?.current ?? null
  }, [selectedRobotId, positionsRef])

  // Robot ID list (re-derive when REST data changes)
  const robotIds = useMemo(() => {
    return Array.from(positionsRef.current.keys())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [robots])

  return (
    <>
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[bounds.cx + bounds.size, bounds.size, bounds.cz + bounds.size]}
        intensity={0.8}
        castShadow
        shadow-mapSize-width={1024}
        shadow-mapSize-height={1024}
      />
      <directionalLight
        position={[bounds.cx - bounds.size / 2, bounds.size / 2, bounds.cz - bounds.size / 2]}
        intensity={0.3}
      />

      <Grid
        position={[bounds.cx, 0, bounds.cz]}
        args={[bounds.size * 1.5, bounds.size * 1.5]}
        cellSize={1}
        cellColor="#313244"
        sectionSize={5}
        sectionColor="#45475a"
        fadeDistance={bounds.size * 2}
        infiniteGrid={false}
      />

      <mesh
        rotation={[-Math.PI / 2, 0, 0]}
        position={[bounds.cx, -0.01, bounds.cz]}
        receiveShadow
        onClick={() => onSelectRobot(null)}
      >
        <planeGeometry args={[bounds.size * 2, bounds.size * 2]} />
        <meshStandardMaterial color="#11111b" transparent opacity={0.8} />
      </mesh>

      <FloorEdges edges={edges} nodeMap={nodeMap} />
      <NodeMarkers nodes={nodes} />

      {heatmapEnabled && heatmapCells && heatmapResolution && (
        <HeatMapOverlay cells={heatmapCells} resolution={heatmapResolution} />
      )}

      {robotIds.map((id) => {
        const rp = positionsRef.current.get(id)
        if (!rp) return null
        return (
          <Robot3DModel
            key={id}
            rp={rp}
            selected={id === selectedRobotId}
            onSelect={onSelectRobot}
            nodeMap={nodeMap}
          />
        )
      })}

      <OrbitControls
        makeDefault
        target={[bounds.cx, 0, bounds.cz]}
        maxPolarAngle={Math.PI / 2.1}
        minDistance={2}
        maxDistance={bounds.size * 3}
        enableDamping
        dampingFactor={0.1}
      />

      <CameraFollow target={followTarget} enabled={followMode} />
    </>
  )
}

// --- Public component (wraps Canvas) ---

interface Warehouse3DProps {
  nodes: MapNode[]
  edges: MapEdge[]
  robots: Robot[]
  heatmapCells?: HeatMapCell[]
  heatmapResolution?: number
  heatmapEnabled?: boolean
  selectedRobotId: string | null
  onSelectRobot: (id: string | null) => void
  followMode: boolean
  lastWSEvent: FleetWSEvent | null
}

export function Warehouse3D({
  nodes,
  edges,
  robots,
  heatmapCells,
  heatmapResolution,
  heatmapEnabled,
  selectedRobotId,
  onSelectRobot,
  followMode,
  lastWSEvent,
}: Warehouse3DProps) {
  const camPos = useMemo((): [number, number, number] => {
    if (nodes.length === 0) return [10, 12, 10]
    let maxX = -Infinity, maxZ = -Infinity
    let minX = Infinity, minZ = Infinity
    for (const n of nodes) {
      if (n.x > maxX) maxX = n.x
      if (n.x < minX) minX = n.x
      if (n.y > maxZ) maxZ = n.y
      if (n.y < minZ) minZ = n.y
    }
    const cx = (minX + maxX) / 2
    const cz = (minZ + maxZ) / 2
    const span = Math.max(maxX - minX, maxZ - minZ)
    return [cx + span * 0.6, span * 0.8, cz + span * 0.6]
  }, [nodes])

  return (
    <div className="bg-panel rounded border border-border overflow-hidden relative" style={{ minHeight: 0 }}>
      <Canvas
        camera={{ position: camPos, fov: 50, near: 0.1, far: 500 }}
        shadows
        gl={{ antialias: true, alpha: false }}
        style={{ background: '#11111b' }}
        onCreated={({ gl }) => {
          gl.setClearColor('#11111b')
          gl.toneMapping = THREE.ACESFilmicToneMapping
          gl.toneMappingExposure = 1.2
        }}
      >
        <Scene
          nodes={nodes}
          edges={edges}
          robots={robots}
          heatmapCells={heatmapCells}
          heatmapResolution={heatmapResolution}
          heatmapEnabled={heatmapEnabled}
          selectedRobotId={selectedRobotId}
          onSelectRobot={onSelectRobot}
          followMode={followMode}
          lastWSEvent={lastWSEvent}
        />
      </Canvas>

      <div className="absolute bottom-2 left-2 text-[10px] text-muted bg-panel/80 px-2 py-1 rounded border border-border">
        {robots.length} robots | 3D View
      </div>
    </div>
  )
}
