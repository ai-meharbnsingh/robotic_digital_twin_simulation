import { useMemo } from 'react'
import type { MapNode, MapEdge, Robot, HeatMapCell } from '../types'

interface WarehouseGridProps {
  nodes: MapNode[]
  edges: MapEdge[]
  robots: Robot[]
  heatmapCells?: HeatMapCell[]
  heatmapResolution?: number
  heatmapEnabled?: boolean
}

const NODE_COLORS: Record<string, string> = {
  aisle: '#6c7086',
  shelf: '#89b4fa',
  charge: '#a6e3a1',
  pick: '#f9e2af',
  drop: '#fab387',
  hub: '#cba6f7',
}

const ROBOT_TYPE_COLORS: Record<string, string> = {
  differential_drive: '#89dceb',  // cyan — AMR
  unidirectional:     '#fab387',  // orange — AGV
  omnidirectional:    '#cba6f7',  // purple — OMNI
}

const ROBOT_UNKNOWN_COLOR = '#6c7086'  // gray — unknown type
const ROBOT_ERROR_COLOR = '#f38ba8'

/**
 * Interpolate from green (low) → yellow (mid) → red (high) based on 0-1 intensity.
 */
function heatColor(intensity: number): string {
  const t = Math.max(0, Math.min(1, intensity))
  let r: number, g: number, b: number

  if (t < 0.5) {
    // Green → Yellow (0.0 → 0.5)
    const s = t / 0.5
    r = Math.round(166 + (249 - 166) * s)  // #a6 → #f9
    g = Math.round(227 + (226 - 227) * s)  // #e3 → #e2
    b = Math.round(161 + (175 - 161) * s)  // #a1 → #af (greenish-yellow)
  } else {
    // Yellow → Red (0.5 → 1.0)
    const s = (t - 0.5) / 0.5
    r = Math.round(249 + (243 - 249) * s)  // #f9 → #f3
    g = Math.round(226 + (139 - 226) * s)  // #e2 → #8b
    b = Math.round(175 + (168 - 175) * s)  // #af → #a8
  }

  return `rgb(${r}, ${g}, ${b})`
}

/**
 * Top-down warehouse map with optional heat map overlay.
 * Layers (bottom to top): heat map → edges → nodes → robots.
 */
export function WarehouseGrid({
  nodes,
  edges,
  robots,
  heatmapCells,
  heatmapResolution = 0.5,
  heatmapEnabled = false,
}: WarehouseGridProps) {
  // Compute SVG viewBox from node extents
  const { viewBox, scale } = useMemo(() => {
    if (nodes.length === 0) {
      return { viewBox: '0 0 100 100', scale: 1 }
    }
    const xs = nodes.map((n) => n.x)
    const ys = nodes.map((n) => n.y)
    const minX = Math.min(...xs)
    const maxX = Math.max(...xs)
    const minY = Math.min(...ys)
    const maxY = Math.max(...ys)
    const pad = 2
    const w = Math.max(maxX - minX + pad * 2, 10)
    const h = Math.max(maxY - minY + pad * 2, 10)
    const s = Math.max(w, h) / 100
    return {
      viewBox: `${minX - pad} ${minY - pad} ${w} ${h}`,
      scale: s,
    }
  }, [nodes])

  // Build a quick lookup: node name -> {x, y}
  const nodeMap = useMemo(() => {
    const m = new Map<string, { x: number; y: number }>()
    for (const n of nodes) {
      m.set(n.name, { x: n.x, y: n.y })
    }
    return m
  }, [nodes])

  // Build robot positions with type info for color-coding
  const robotPositions = useMemo(() => {
    return robots.map((r) => ({
      id: r.robot_id,
      x: r.pose.x,
      y: r.pose.y,
      status: r.status,
      name: r.name || r.robot_id,
      robot_type: r.robot_type,
    }))
  }, [robots])

  const nodeRadius = Math.max(0.3, scale * 0.5)
  const robotSize = Math.max(0.5, scale * 0.7)
  const cellSize = heatmapResolution

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">Warehouse Map</h2>
      {nodes.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No map data
        </div>
      ) : (
        <svg
          viewBox={viewBox}
          className="flex-1 w-full"
          style={{ minHeight: 0 }}
          preserveAspectRatio="xMidYMid meet"
        >
          {/* Heat map overlay — rendered first (bottom layer) */}
          {heatmapEnabled && heatmapCells && heatmapCells.map((cell) => (
            <rect
              key={`hm-${cell.col}-${cell.row}`}
              x={cell.x - cellSize / 2}
              y={cell.y - cellSize / 2}
              width={cellSize}
              height={cellSize}
              fill={heatColor(cell.intensity)}
              opacity={0.35 + cell.intensity * 0.35}
              rx={cellSize * 0.05}
            >
              <title>{`Visits: ${cell.visit_count} | Dwell: ${cell.avg_dwell_time_s.toFixed(1)}s`}</title>
            </rect>
          ))}

          {/* Edges */}
          {edges.map((e, i) => {
            const from = nodeMap.get(e.from)
            const to = nodeMap.get(e.to)
            if (!from || !to) return null
            return (
              <line
                key={`edge-${i}`}
                x1={from.x}
                y1={from.y}
                x2={to.x}
                y2={to.y}
                stroke="#313244"
                strokeWidth={scale * 0.15}
              />
            )
          })}

          {/* Nodes */}
          {nodes.map((n) => (
            <circle
              key={n.name}
              cx={n.x}
              cy={n.y}
              r={nodeRadius}
              fill={NODE_COLORS[n.type] || '#6c7086'}
              opacity={0.8}
            >
              <title>{`${n.name} (${n.type})`}</title>
            </circle>
          ))}

          {/* Robots — color-coded by type */}
          {robotPositions.map((r) => {
            const typeColor = ROBOT_TYPE_COLORS[r.robot_type] || ROBOT_UNKNOWN_COLOR
            const fillColor = r.status === 'error' ? ROBOT_ERROR_COLOR : typeColor
            return (
              <g key={r.id}>
                <rect
                  x={r.x - robotSize / 2}
                  y={r.y - robotSize / 2}
                  width={robotSize}
                  height={robotSize}
                  fill={fillColor}
                  rx={robotSize * 0.15}
                  transform={`rotate(45 ${r.x} ${r.y})`}
                  opacity={r.status === 'offline' ? 0.3 : 0.9}
                >
                  <title>{`${r.name} [${r.robot_type}] [${r.status}]`}</title>
                </rect>
                <text
                  x={r.x}
                  y={r.y + robotSize + scale * 0.4}
                  textAnchor="middle"
                  fill="#cdd6f4"
                  fontSize={scale * 0.8}
                >
                  {r.name}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}
