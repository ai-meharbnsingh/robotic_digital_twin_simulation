import { useCallback, useEffect, useRef, useState } from 'react'
import type { NodeType, WarehouseConfig, ZoneType } from '../types'
import { useDesignerState } from '../hooks/useDesignerState'
import type { DesignerTool } from '../hooks/useDesignerState'
import { DesignerNodePalette } from './DesignerNodePalette'
import { DesignerToolbar } from './DesignerToolbar'

// ── Color constants (match WarehouseGrid) ──────────────────────────────────
const NODE_COLORS: Record<string, string> = {
  aisle: '#6c7086',
  shelf: '#89b4fa',
  charge: '#a6e3a1',
  pick: '#f9e2af',
  drop: '#fab387',
  hub: '#cba6f7',
}

const ZONE_COLORS: Record<string, string> = {
  dock: '#a6e3a120',
  shelf: '#89b4fa20',
  ops: '#cba6f720',
  aisle: '#6c708620',
  lane: '#89dceb20',
  pick: '#f9e2af20',
}

const CANVAS_BG = '#11111b'
const GRID_COLOR = '#313244'
const EDGE_COLOR = '#45475a'
const EDGE_HOVER_COLOR = '#89b4fa'
const SELECTED_RING = '#89b4fa'
const TEXT_COLOR = '#cdd6f4'
const EDGE_PENDING_COLOR = '#f9e2af'

const API_BASE = window.location.origin

const NODE_RADIUS = 12
const HOVER_RADIUS = 16
const MIN_ZOOM = 0.2
const MAX_ZOOM = 5

// ── Helper: world ↔ screen transforms ──────────────────────────────────────
interface Camera {
  x: number
  y: number
  zoom: number
}

function worldToScreen(wx: number, wy: number, cam: Camera): [number, number] {
  return [(wx - cam.x) * cam.zoom, (wy - cam.y) * cam.zoom]
}

function screenToWorld(sx: number, sy: number, cam: Camera): [number, number] {
  return [sx / cam.zoom + cam.x, sy / cam.zoom + cam.y]
}

// ── Main component ─────────────────────────────────────────────────────────
interface WarehouseDesignerProps {
  onConfigExported?: (config: WarehouseConfig) => void
}

export function WarehouseDesigner({ onConfigExported }: WarehouseDesignerProps) {
  const designer = useDesignerState()
  const { state } = designer

  const canvasRef = useRef<HTMLCanvasElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Camera state
  const [camera, setCamera] = useState<Camera>({ x: -5, y: -5, zoom: 40 })

  // Interaction state
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null)
  const [dragNodeId, setDragNodeId] = useState<string | null>(null)
  const [isPanning, setIsPanning] = useState(false)
  const [panStart, setPanStart] = useState<{ mx: number; my: number; cx: number; cy: number } | null>(null)
  const [edgeFromId, setEdgeFromId] = useState<string | null>(null)
  const [mouseWorld, setMouseWorld] = useState<[number, number]>([0, 0])

  // Node properties panel
  const selectedNode = state.nodes.find((n) => n.id === state.selectedNodeId) ?? null

  // ── Canvas resize ──────────────────────────────────────────────────────
  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current
    const container = containerRef.current
    if (!canvas || !container) return
    const rect = container.getBoundingClientRect()
    const dpr = window.devicePixelRatio || 1
    canvas.width = rect.width * dpr
    canvas.height = rect.height * dpr
    canvas.style.width = `${rect.width}px`
    canvas.style.height = `${rect.height}px`
  }, [])

  useEffect(() => {
    resizeCanvas()
    window.addEventListener('resize', resizeCanvas)
    return () => window.removeEventListener('resize', resizeCanvas)
  }, [resizeCanvas])

  // ── Drawing ────────────────────────────────────────────────────────────
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const dpr = window.devicePixelRatio || 1
    const w = canvas.width
    const h = canvas.height

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    const cw = w / dpr
    const ch = h / dpr

    // Clear
    ctx.fillStyle = CANVAS_BG
    ctx.fillRect(0, 0, cw, ch)

    // Grid lines
    const spacing = state.gridSpacing
    const [tlx, tly] = screenToWorld(0, 0, camera)
    const [brx, bry] = screenToWorld(cw, ch, camera)
    const startX = Math.floor(tlx / spacing) * spacing
    const startY = Math.floor(tly / spacing) * spacing

    ctx.strokeStyle = GRID_COLOR
    ctx.lineWidth = 0.5

    for (let gx = startX; gx <= brx; gx += spacing) {
      const [sx] = worldToScreen(gx, 0, camera)
      ctx.beginPath()
      ctx.moveTo(sx, 0)
      ctx.lineTo(sx, ch)
      ctx.stroke()
    }
    for (let gy = startY; gy <= bry; gy += spacing) {
      const [, sy] = worldToScreen(0, gy, camera)
      ctx.beginPath()
      ctx.moveTo(0, sy)
      ctx.lineTo(cw, sy)
      ctx.stroke()
    }

    // Origin crosshair
    const [ox, oy] = worldToScreen(0, 0, camera)
    ctx.strokeStyle = '#45475a'
    ctx.lineWidth = 1
    ctx.beginPath()
    ctx.moveTo(ox - 8, oy)
    ctx.lineTo(ox + 8, oy)
    ctx.moveTo(ox, oy - 8)
    ctx.lineTo(ox, oy + 8)
    ctx.stroke()

    // Zone backgrounds
    for (const zone of state.zones) {
      const zoneNodes = state.nodes.filter((n) => zone.nodeIds.includes(n.id))
      if (zoneNodes.length < 2) continue
      const xs = zoneNodes.map((n) => n.x)
      const ys = zoneNodes.map((n) => n.y)
      const pad = spacing * 0.4
      const minX = Math.min(...xs) - pad
      const minY = Math.min(...ys) - pad
      const maxX = Math.max(...xs) + pad
      const maxY = Math.max(...ys) + pad
      const [sx1, sy1] = worldToScreen(minX, minY, camera)
      const [sx2, sy2] = worldToScreen(maxX, maxY, camera)
      ctx.fillStyle = ZONE_COLORS[zone.type] || '#ffffff10'
      ctx.fillRect(sx1, sy1, sx2 - sx1, sy2 - sy1)
      ctx.strokeStyle = (ZONE_COLORS[zone.type] || '#ffffff10').replace('20', '60')
      ctx.lineWidth = 1
      ctx.strokeRect(sx1, sy1, sx2 - sx1, sy2 - sy1)
      // Zone label
      ctx.fillStyle = '#6c7086'
      ctx.font = '9px sans-serif'
      ctx.fillText(zone.name, sx1 + 3, sy1 + 11)
    }

    // Edges
    const nodeById = new Map(state.nodes.map((n) => [n.id, n]))
    for (const edge of state.edges) {
      const from = nodeById.get(edge.from)
      const to = nodeById.get(edge.to)
      if (!from || !to) continue
      const [x1, y1] = worldToScreen(from.x, from.y, camera)
      const [x2, y2] = worldToScreen(to.x, to.y, camera)
      const isHovered = hoveredNodeId === edge.from || hoveredNodeId === edge.to
      ctx.strokeStyle = isHovered ? EDGE_HOVER_COLOR : EDGE_COLOR
      ctx.lineWidth = isHovered ? 2 : 1.5
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }

    // Pending edge line (while creating edge)
    if (edgeFromId) {
      const fromNode = nodeById.get(edgeFromId)
      if (fromNode) {
        const [fx, fy] = worldToScreen(fromNode.x, fromNode.y, camera)
        const [mx, my] = worldToScreen(mouseWorld[0], mouseWorld[1], camera)
        ctx.strokeStyle = EDGE_PENDING_COLOR
        ctx.lineWidth = 1.5
        ctx.setLineDash([5, 5])
        ctx.beginPath()
        ctx.moveTo(fx, fy)
        ctx.lineTo(mx, my)
        ctx.stroke()
        ctx.setLineDash([])
      }
    }

    // Nodes
    for (const node of state.nodes) {
      const [sx, sy] = worldToScreen(node.x, node.y, camera)
      const isSelected = node.id === state.selectedNodeId
      const isHovered = node.id === hoveredNodeId
      const r = isHovered ? HOVER_RADIUS : NODE_RADIUS
      const color = NODE_COLORS[node.type] || '#6c7086'

      // Selection ring
      if (isSelected) {
        ctx.strokeStyle = SELECTED_RING
        ctx.lineWidth = 2.5
        ctx.beginPath()
        ctx.arc(sx, sy, r + 4, 0, Math.PI * 2)
        ctx.stroke()
      }

      // Node body
      if (node.type === 'shelf') {
        // Square for shelves
        ctx.fillStyle = color
        ctx.globalAlpha = 0.85
        ctx.fillRect(sx - r * 0.7, sy - r * 0.7, r * 1.4, r * 1.4)
        ctx.globalAlpha = 1
      } else {
        // Circle for others
        ctx.fillStyle = color
        ctx.globalAlpha = 0.85
        ctx.beginPath()
        ctx.arc(sx, sy, r, 0, Math.PI * 2)
        ctx.fill()
        ctx.globalAlpha = 1
      }

      // Node label
      ctx.fillStyle = TEXT_COLOR
      ctx.font = '10px sans-serif'
      ctx.textAlign = 'center'
      ctx.fillText(node.name, sx, sy + r + 13)
    }

    // Coordinates display
    ctx.fillStyle = '#6c7086'
    ctx.font = '10px monospace'
    ctx.textAlign = 'left'
    ctx.fillText(
      `(${mouseWorld[0].toFixed(1)}, ${mouseWorld[1].toFixed(1)}) zoom: ${camera.zoom.toFixed(0)}`,
      8,
      ch - 8,
    )
  }, [state, camera, hoveredNodeId, edgeFromId, mouseWorld])

  // ── Hit test ───────────────────────────────────────────────────────────
  const hitTestNode = useCallback(
    (sx: number, sy: number): string | null => {
      // Iterate in reverse so top-drawn nodes are hit first
      for (let i = state.nodes.length - 1; i >= 0; i--) {
        const node = state.nodes[i]!
        const [nx, ny] = worldToScreen(node.x, node.y, camera)
        const dx = sx - nx
        const dy = sy - ny
        if (dx * dx + dy * dy <= HOVER_RADIUS * HOVER_RADIUS) {
          return node.id
        }
      }
      return null
    },
    [state.nodes, camera],
  )

  // ── Mouse handlers ─────────────────────────────────────────────────────
  const getCanvasPos = useCallback((e: React.MouseEvent): [number, number] => {
    const canvas = canvasRef.current
    if (!canvas) return [0, 0]
    const rect = canvas.getBoundingClientRect()
    return [e.clientX - rect.left, e.clientY - rect.top]
  }, [])

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      const [sx, sy] = getCanvasPos(e)
      const [wx, wy] = screenToWorld(sx, sy, camera)

      // Middle mouse button → pan
      if (e.button === 1) {
        e.preventDefault()
        setIsPanning(true)
        setPanStart({ mx: sx, my: sy, cx: camera.x, cy: camera.y })
        return
      }

      // Right click → remove node
      if (e.button === 2) {
        const nodeId = hitTestNode(sx, sy)
        if (nodeId) {
          e.preventDefault()
          designer.removeNode(nodeId)
        }
        return
      }

      // Left click
      const nodeId = hitTestNode(sx, sy)

      if (state.selectedTool === 'select') {
        if (nodeId) {
          designer.setSelectedNodeId(nodeId)
          setDragNodeId(nodeId)
          designer.moveNodeStart()
        } else {
          designer.setSelectedNodeId(null)
          // Start panning on empty space with left click
          setIsPanning(true)
          setPanStart({ mx: sx, my: sy, cx: camera.x, cy: camera.y })
        }
        return
      }

      if (state.selectedTool === 'edge') {
        if (nodeId) {
          if (edgeFromId) {
            // Complete edge
            designer.addEdge(edgeFromId, nodeId)
            setEdgeFromId(null)
          } else {
            // Start edge
            setEdgeFromId(nodeId)
          }
        } else {
          setEdgeFromId(null)
        }
        return
      }

      // Zone tool: click a node to select it for zone assignment via properties panel
      if (state.selectedTool === 'zone') {
        if (nodeId) {
          designer.setSelectedNodeId(nodeId)
          // If zones exist, auto-assign first available zone to the node (toggle)
          const node = state.nodes.find((n) => n.id === nodeId)
          if (node && state.zones.length > 0) {
            // If node already has a zone, remove it; otherwise assign first zone
            if (node.zone) {
              designer.setNodeZone(nodeId, undefined)
            } else {
              designer.setNodeZone(nodeId, state.zones[0]!.name)
            }
          }
        }
        return
      }

      // Node placement tools
      const nodeTypes: string[] = ['shelf', 'aisle', 'charge', 'pick', 'drop', 'hub']
      if (nodeTypes.includes(state.selectedTool)) {
        if (!nodeId) {
          designer.addNode(wx, wy, state.selectedTool as NodeType)
        } else {
          designer.setSelectedNodeId(nodeId)
        }
        return
      }
    },
    [camera, state.selectedTool, state.nodes, state.zones, edgeFromId, hitTestNode, designer, getCanvasPos],
  )

  const handleMouseMove = useCallback(
    (e: React.MouseEvent) => {
      const [sx, sy] = getCanvasPos(e)
      const [wx, wy] = screenToWorld(sx, sy, camera)
      setMouseWorld([wx, wy])

      // Panning
      if (isPanning && panStart) {
        const dx = (sx - panStart.mx) / camera.zoom
        const dy = (sy - panStart.my) / camera.zoom
        setCamera((prev) => ({ ...prev, x: panStart.cx - dx, y: panStart.cy - dy }))
        return
      }

      // Dragging node
      if (dragNodeId) {
        designer.moveNode(dragNodeId, wx, wy)
        return
      }

      // Hover detection
      const nodeId = hitTestNode(sx, sy)
      setHoveredNodeId(nodeId)
    },
    [camera, isPanning, panStart, dragNodeId, hitTestNode, designer, getCanvasPos],
  )

  const handleMouseUp = useCallback(() => {
    setDragNodeId(null)
    setIsPanning(false)
    setPanStart(null)
  }, [])

  const handleWheel = useCallback(
    (e: React.WheelEvent) => {
      e.preventDefault()
      const [sx, sy] = getCanvasPos(e)
      const [wx, wy] = screenToWorld(sx, sy, camera)
      const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
      const newZoom = Math.max(MIN_ZOOM, Math.min(MAX_ZOOM, camera.zoom * factor))
      // Adjust camera so the world point under the cursor stays fixed
      const newCamX = wx - sx / newZoom
      const newCamY = wy - sy / newZoom
      setCamera({ x: newCamX, y: newCamY, zoom: newZoom })
    },
    [camera, getCanvasPos],
  )

  const handleContextMenu = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
  }, [])

  // ── Keyboard shortcuts ─────────────────────────────────────────────────
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Undo/Redo
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault()
        designer.undo()
        return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && e.shiftKey) {
        e.preventDefault()
        designer.redo()
        return
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'y') {
        e.preventDefault()
        designer.redo()
        return
      }

      // Don't intercept if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement) return

      // Delete selected node
      if ((e.key === 'Delete' || e.key === 'Backspace') && state.selectedNodeId) {
        e.preventDefault()
        designer.removeNode(state.selectedNodeId)
        return
      }

      // Tool shortcuts
      const toolMap: Record<string, DesignerTool> = {
        v: 'select',
        e: 'edge',
        z: 'zone',
        s: 'shelf',
        a: 'aisle',
        c: 'charge',
        p: 'pick',
        d: 'drop',
        h: 'hub',
      }
      const tool = toolMap[e.key.toLowerCase()]
      if (tool) {
        designer.setSelectedTool(tool)
        setEdgeFromId(null)
      }

      // Escape clears edge mode and selection
      if (e.key === 'Escape') {
        setEdgeFromId(null)
        designer.setSelectedNodeId(null)
      }
    }

    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [designer, state.selectedNodeId])

  // ── Template loading ───────────────────────────────────────────────────
  const handleLoadTemplate = useCallback(
    async (templateName: string) => {
      try {
        const res = await fetch(`${API_BASE}/api/designer/templates/${templateName}`)
        if (res.ok) {
          const config = (await res.json()) as WarehouseConfig
          designer.loadConfig(config)
          // Center camera on loaded content
          if (config.nodes.length > 0) {
            const xs = config.nodes.map((n) => n.x)
            const ys = config.nodes.map((n) => n.y)
            const cx = (Math.min(...xs) + Math.max(...xs)) / 2
            const cy = (Math.min(...ys) + Math.max(...ys)) / 2
            const rangeX = Math.max(...xs) - Math.min(...xs) + 4
            const rangeY = Math.max(...ys) - Math.min(...ys) + 4
            const canvas = canvasRef.current
            const cw = canvas ? canvas.clientWidth : 800
            const ch = canvas ? canvas.clientHeight : 600
            const zoom = Math.min(cw / rangeX, ch / rangeY) * 0.8
            setCamera({ x: cx - cw / (2 * zoom), y: cy - ch / (2 * zoom), zoom })
          }
          return
        }
      } catch {
        // API unavailable — try static file
      }

      // Fallback: try fetching from configs directory
      try {
        const res = await fetch(`/configs/warehouses/${templateName}.json`)
        if (res.ok) {
          const config = (await res.json()) as WarehouseConfig
          designer.loadConfig(config)
          return
        }
      } catch {
        // ignore
      }
    },
    [designer],
  )

  // ── Export with callback ───────────────────────────────────────────────
  const handleExportServer = useCallback(async () => {
    const result = await designer.exportToServer()
    if (result.saved && onConfigExported) {
      onConfigExported(designer.exportConfig())
    }
    return result
  }, [designer, onConfigExported])

  // ── Properties panel (selected node) ───────────────────────────────────
  const renderProperties = () => {
    if (!selectedNode) {
      return (
        <div className="text-xs text-muted p-3">
          <p className="mb-2 text-[10px] uppercase tracking-wider font-semibold">Properties</p>
          <p>Click a node to see its properties</p>
          <div className="mt-4 text-[10px] leading-relaxed opacity-70">
            <p className="font-semibold mb-1">Shortcuts:</p>
            <p>V — Select &nbsp; E — Edge &nbsp; Del — Remove</p>
            <p>S — Shelf &nbsp; A — Aisle &nbsp; C — Charge</p>
            <p>P — Pick &nbsp; D — Drop &nbsp; H — Hub</p>
            <p>Scroll — Zoom &nbsp; Mid/LClick empty — Pan</p>
            <p>Right-click node — Remove</p>
            <p>Ctrl+Z / Ctrl+Shift+Z — Undo/Redo</p>
          </div>
          <div className="mt-4 text-[10px] leading-relaxed opacity-70">
            <p className="font-semibold mb-1">Stats:</p>
            <p>Nodes: {state.nodes.length}</p>
            <p>Edges: {state.edges.length}</p>
            <p>Zones: {state.zones.length}</p>
          </div>
        </div>
      )
    }

    return (
      <div className="text-xs p-3 flex flex-col gap-2">
        <p className="text-[10px] uppercase tracking-wider font-semibold text-muted mb-1">Node Properties</p>
        <label className="flex flex-col gap-0.5">
          <span className="text-muted text-[10px]">Name</span>
          <input
            type="text"
            value={selectedNode.name}
            onChange={(e) => designer.updateNodeName(selectedNode.id, e.target.value)}
            className="bg-surface border border-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-accent"
          />
        </label>
        <label className="flex flex-col gap-0.5">
          <span className="text-muted text-[10px]">Type</span>
          <select
            value={selectedNode.type}
            onChange={(e) => designer.updateNodeType(selectedNode.id, e.target.value as NodeType)}
            className="bg-surface border border-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-accent"
          >
            <option value="aisle">Aisle</option>
            <option value="shelf">Shelf</option>
            <option value="charge">Charge</option>
            <option value="pick">Pick</option>
            <option value="drop">Drop</option>
            <option value="hub">Hub</option>
          </select>
        </label>
        <div className="flex gap-2">
          <label className="flex flex-col gap-0.5 flex-1">
            <span className="text-muted text-[10px]">X</span>
            <input
              type="number"
              value={selectedNode.x}
              readOnly
              className="bg-surface border border-border rounded px-2 py-1 text-xs text-muted"
            />
          </label>
          <label className="flex flex-col gap-0.5 flex-1">
            <span className="text-muted text-[10px]">Y</span>
            <input
              type="number"
              value={selectedNode.y}
              readOnly
              className="bg-surface border border-border rounded px-2 py-1 text-xs text-muted"
            />
          </label>
        </div>
        <label className="flex flex-col gap-0.5">
          <span className="text-muted text-[10px]">Zone</span>
          <div className="flex gap-1">
            <select
              value={selectedNode.zone ?? ''}
              onChange={(e) =>
                designer.setNodeZone(selectedNode.id, e.target.value || undefined)
              }
              className="bg-surface border border-border rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-accent flex-1"
            >
              <option value="">None</option>
              {state.zones.map((z) => (
                <option key={z.name} value={z.name}>
                  {z.name}
                </option>
              ))}
            </select>
          </div>
        </label>
        {/* New zone creator */}
        <NewZoneInline onAdd={designer.addZone} />
        <button
          className="mt-2 px-2 py-1 text-xs rounded border border-danger/40 text-danger hover:bg-danger/10 transition-colors"
          onClick={() => designer.removeNode(selectedNode.id)}
        >
          Delete Node
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full w-full bg-surface">
      {/* Toolbar */}
      <DesignerToolbar
        gridSpacing={state.gridSpacing}
        onGridSpacingChange={designer.setGridSpacing}
        canUndo={state.canUndo}
        canRedo={state.canRedo}
        onUndo={designer.undo}
        onRedo={designer.redo}
        onAutoEdges={designer.autoEdges}
        onValidate={designer.validate}
        onExport={handleExportServer}
        onExportJson={designer.exportConfig}
        onImportJson={designer.loadConfig}
        onLoadTemplate={handleLoadTemplate}
      />

      {/* Main area: palette + canvas + properties */}
      <div className="flex-1 flex min-h-0">
        {/* Left: palette */}
        <div className="w-32 flex-shrink-0">
          <DesignerNodePalette
            selectedTool={state.selectedTool}
            onSelectTool={(tool) => {
              designer.setSelectedTool(tool)
              setEdgeFromId(null)
            }}
          />
        </div>

        {/* Center: canvas */}
        <div ref={containerRef} className="flex-1 relative min-w-0 min-h-0">
          <canvas
            ref={canvasRef}
            className="absolute inset-0 w-full h-full"
            style={{ cursor: getCursor(state.selectedTool, hoveredNodeId, isPanning, dragNodeId) }}
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onMouseLeave={handleMouseUp}
            onWheel={handleWheel}
            onContextMenu={handleContextMenu}
          />
          {/* Tool indicator overlay */}
          <div className="absolute top-2 left-2 bg-panel/80 border border-border rounded px-2 py-1 text-[10px] text-muted pointer-events-none">
            Tool: <span className="text-gray-200 font-semibold">{state.selectedTool.toUpperCase()}</span>
            {edgeFromId && <span className="text-warning ml-2">Click target node...</span>}
          </div>
        </div>

        {/* Right: properties */}
        <div className="w-48 flex-shrink-0 bg-panel border-l border-border overflow-y-auto">
          {renderProperties()}
        </div>
      </div>
    </div>
  )
}

// ── Cursor helper ──────────────────────────────────────────────────────────
function getCursor(
  tool: DesignerTool,
  hoveredNodeId: string | null,
  isPanning: boolean,
  dragNodeId: string | null,
): string {
  if (isPanning) return 'grabbing'
  if (dragNodeId) return 'grabbing'
  if (hoveredNodeId) {
    if (tool === 'select') return 'grab'
    if (tool === 'edge') return 'pointer'
    return 'pointer'
  }
  if (tool === 'select') return 'default'
  if (tool === 'edge') return 'crosshair'
  return 'crosshair'
}

// ── Inline zone creator ────────────────────────────────────────────────────
function NewZoneInline({ onAdd }: { onAdd: (name: string, type: ZoneType) => void }) {
  const [name, setName] = useState('')
  const [type, setType] = useState<ZoneType>('aisle')
  const [open, setOpen] = useState(false)

  if (!open) {
    return (
      <button
        className="text-[10px] text-accent hover:underline text-left"
        onClick={() => setOpen(true)}
      >
        + New zone
      </button>
    )
  }

  return (
    <div className="flex flex-col gap-1 border border-border rounded p-1.5 bg-surface">
      <input
        type="text"
        placeholder="Zone name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        className="bg-surface border border-border rounded px-1 py-0.5 text-[10px] text-gray-200 focus:outline-none focus:border-accent"
      />
      <select
        value={type}
        onChange={(e) => setType(e.target.value as ZoneType)}
        className="bg-surface border border-border rounded px-1 py-0.5 text-[10px] text-gray-200 focus:outline-none focus:border-accent"
      >
        <option value="dock">Dock</option>
        <option value="shelf">Shelf</option>
        <option value="ops">Ops</option>
        <option value="aisle">Aisle</option>
        <option value="lane">Lane</option>
        <option value="pick">Pick</option>
      </select>
      <div className="flex gap-1">
        <button
          className="text-[10px] px-1.5 py-0.5 rounded border border-accent/50 text-accent hover:bg-accent/10"
          onClick={() => {
            if (name.trim()) {
              onAdd(name.trim(), type)
              setName('')
              setOpen(false)
            }
          }}
        >
          Add
        </button>
        <button
          className="text-[10px] px-1.5 py-0.5 rounded border border-border text-muted hover:text-gray-200"
          onClick={() => {
            setName('')
            setOpen(false)
          }}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}
