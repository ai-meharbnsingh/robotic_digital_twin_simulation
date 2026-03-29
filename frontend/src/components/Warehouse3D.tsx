import { useEffect, useMemo, useRef, type RefObject } from 'react'
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
  const geometryRef = useRef<THREE.BufferGeometry | null>(null)

  const geometry = useMemo(() => {
    // Dispose previous geometry to prevent GPU memory leak
    geometryRef.current?.dispose()
    const pts: number[] = []
    for (const e of edges) {
      const a = nodeMap.get(e.from)
      const b = nodeMap.get(e.to)
      if (!a || !b) continue
      pts.push(a.x, 0.01, a.y, b.x, 0.01, b.y)
    }
    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.Float32BufferAttribute(pts, 3))
    geometryRef.current = geom
    return geom
  }, [edges, nodeMap])

  // Cleanup on unmount
  useEffect(() => {
    return () => { geometryRef.current?.dispose() }
  }, [])

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
  const geometryRef = useRef<THREE.BufferGeometry | null>(null)

  // Merge all heatmap cells into a single geometry with per-vertex colors (1 draw call)
  const { geometry } = useMemo(() => {
    geometryRef.current?.dispose()

    const positions: number[] = []
    const colors: number[] = []
    const half = resolution / 2
    const y = 0.005

    for (const c of cells) {
      const cx = c.x + half
      const cz = c.y + half
      const [r, g, b] = heatColorRGB(c.intensity)

      // Two triangles forming a quad (6 vertices)
      positions.push(
        cx - half, y, cz - half,  cx + half, y, cz - half,  cx + half, y, cz + half,
        cx - half, y, cz - half,  cx + half, y, cz + half,  cx - half, y, cz + half,
      )
      for (let i = 0; i < 6; i++) colors.push(r, g, b)
    }

    const geom = new THREE.BufferGeometry()
    geom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3))
    geom.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3))
    geometryRef.current = geom
    return { geometry: geom }
  }, [cells, resolution])

  useEffect(() => {
    return () => { geometryRef.current?.dispose() }
  }, [])

  if (cells.length === 0) return null

  return (
    <mesh geometry={geometry}>
      <meshBasicMaterial vertexColors transparent opacity={0.35} />
    </mesh>
  )
}

function heatColorRGB(intensity: number): [number, number, number] {
  // green → yellow → red, returns normalized [0-1] values
  if (intensity <= 0.5) {
    const t = intensity * 2
    return [
      (166 + (249 - 166) * t) / 255,
      (227 + (226 - 227) * t) / 255,
      (161 + (175 - 161) * t) / 255,
    ]
  }
  const t = (intensity - 0.5) * 2
  return [
    (249 + (243 - 249) * t) / 255,
    (226 + (139 - 226) * t) / 255,
    (175 + (168 - 175) * t) / 255,
  ]
}

function CameraFollow({
  positionsRef,
  selectedRobotId,
  enabled,
}: {
  positionsRef: RefObject<Map<string, { current: THREE.Vector3 }>>
  selectedRobotId: string | null
  enabled: boolean
}) {
  const { camera } = useThree()
  const offsetRef = useRef(new THREE.Vector3(3, 6, 3))

  useFrame((_, delta) => {
    if (!enabled || !selectedRobotId) return
    const rp = positionsRef.current?.get(selectedRobotId)
    if (!rp) return
    // Frame-rate independent lerp: ~5 units/sec convergence
    const t = Math.min(1, delta * 5)
    const dest = rp.current.clone().add(offsetRef.current)
    camera.position.lerp(dest, t)
    camera.lookAt(rp.current)
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
  wsHandlerRef: React.MutableRefObject<((event: FleetWSEvent) => void) | null>
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
  wsHandlerRef,
}: SceneProps) {
  const nodeMap = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>()
    for (const n of nodes) m.set(n.name, { x: n.x, y: n.y })
    return m
  }, [nodes])

  const { positionsRef, updateFromRest, handleWSEvent } = useRobotPositions()

  // Register WS handler ref — events flow directly to position system (no React re-render)
  useEffect(() => {
    wsHandlerRef.current = handleWSEvent
    return () => { wsHandlerRef.current = null }
  }, [wsHandlerRef, handleWSEvent])

  // Sync REST data into position system
  useEffect(() => {
    if (robots.length > 0) updateFromRest(robots)
  }, [robots, updateFromRest])

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

  // Robot ID list — union of REST robots + WS-provisional entries in positionsRef
  const robotIds = useMemo(() => {
    const ids = new Set(robots.map((r) => r.robot_id))
    for (const key of positionsRef.current.keys()) ids.add(key)
    return Array.from(ids)
  }, [robots, positionsRef])

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
        enabled={!followMode}
        target={[bounds.cx, 0, bounds.cz]}
        maxPolarAngle={Math.PI / 2.1}
        minDistance={2}
        maxDistance={bounds.size * 3}
        enableDamping
        dampingFactor={0.1}
      />

      <CameraFollow positionsRef={positionsRef} selectedRobotId={selectedRobotId} enabled={followMode} />
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
  wsHandlerRef: React.MutableRefObject<((event: FleetWSEvent) => void) | null>
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
  wsHandlerRef,
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
          wsHandlerRef={wsHandlerRef}
        />
      </Canvas>

      <div className="absolute bottom-2 left-2 text-[10px] text-muted bg-panel/80 px-2 py-1 rounded border border-border">
        {robots.length} robots | 3D View
      </div>
    </div>
  )
}
