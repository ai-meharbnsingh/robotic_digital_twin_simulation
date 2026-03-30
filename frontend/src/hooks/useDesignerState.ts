import { useCallback, useRef, useState } from 'react'
import type {
  DesignerNode,
  DesignerEdge,
  DesignerZone,
  DesignerValidation,
  NodeType,
  WarehouseConfig,
} from '../types'

const API_BASE = window.location.origin
const MAX_UNDO = 10

// ── Snapshot (what gets pushed onto undo/redo stacks) ──────────────────────
interface Snapshot {
  nodes: DesignerNode[]
  edges: DesignerEdge[]
  zones: DesignerZone[]
}

// ── Tool selection ─────────────────────────────────────────────────────────
export type DesignerTool = NodeType | 'select' | 'edge' | 'zone'

// ── Public state shape ─────────────────────────────────────────────────────
export interface DesignerState {
  nodes: DesignerNode[]
  edges: DesignerEdge[]
  zones: DesignerZone[]
  selectedNodeId: string | null
  selectedTool: DesignerTool
  gridSpacing: number
  canUndo: boolean
  canRedo: boolean
}

// ── Helpers ────────────────────────────────────────────────────────────────
let _idCounter = 0
function nextId(prefix: string): string {
  _idCounter += 1
  return `${prefix}_${Date.now()}_${_idCounter}`
}

function snap(value: number, spacing: number): number {
  return Math.round(value / spacing) * spacing
}

function clone<T>(obj: T): T {
  return JSON.parse(JSON.stringify(obj)) as T
}

// ── Hook ───────────────────────────────────────────────────────────────────
export function useDesignerState() {
  const [nodes, setNodes] = useState<DesignerNode[]>([])
  const [edges, setEdges] = useState<DesignerEdge[]>([])
  const [zones, setZones] = useState<DesignerZone[]>([])
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null)
  const [selectedTool, setSelectedTool] = useState<DesignerTool>('select')
  const [gridSpacing, setGridSpacing] = useState(2)

  // Loaded config metadata — per-hook instance (not module global)
  const configNameRef = useRef('')
  const configDescRef = useRef('')

  // Undo / redo stacks (kept in refs to avoid bloating React state)
  const undoStack = useRef<Snapshot[]>([])
  const redoStack = useRef<Snapshot[]>([])
  const [canUndo, setCanUndo] = useState(false)
  const [canRedo, setCanRedo] = useState(false)

  // ── Snapshot helpers ───────────────────────────────────────────────────
  const takeSnapshot = useCallback(() => {
    // We read from latest state via functional updates' closures aren't fresh
    // enough, so we read the values synchronously via a batching trick:
    // the caller should call takeSnapshot() BEFORE mutating state.
    setNodes((prev) => {
      setEdges((prevE) => {
        setZones((prevZ) => {
          const s: Snapshot = { nodes: clone(prev), edges: clone(prevE), zones: clone(prevZ) }
          undoStack.current = [...undoStack.current.slice(-(MAX_UNDO - 1)), s]
          redoStack.current = []
          setCanUndo(true)
          setCanRedo(false)
          return prevZ // no change
        })
        return prevE
      })
      return prev
    })
  }, [])

  const undo = useCallback(() => {
    const stack = undoStack.current
    if (stack.length === 0) return
    const snap = stack[stack.length - 1]!
    undoStack.current = stack.slice(0, -1)

    // Push current state onto redo
    setNodes((prev) => {
      setEdges((prevE) => {
        setZones((prevZ) => {
          redoStack.current = [...redoStack.current, { nodes: clone(prev), edges: clone(prevE), zones: clone(prevZ) }]
          setCanRedo(true)
          return clone(snap.zones)
        })
        return clone(snap.edges)
      })
      return clone(snap.nodes)
    })
    setCanUndo(undoStack.current.length > 0)
    setSelectedNodeId(null)
  }, [])

  const redo = useCallback(() => {
    const stack = redoStack.current
    if (stack.length === 0) return
    const snap = stack[stack.length - 1]!
    redoStack.current = stack.slice(0, -1)

    setNodes((prev) => {
      setEdges((prevE) => {
        setZones((prevZ) => {
          undoStack.current = [...undoStack.current, { nodes: clone(prev), edges: clone(prevE), zones: clone(prevZ) }]
          setCanUndo(true)
          return clone(snap.zones)
        })
        return clone(snap.edges)
      })
      return clone(snap.nodes)
    })
    setCanRedo(redoStack.current.length > 0)
    setSelectedNodeId(null)
  }, [])

  // ── Node operations ────────────────────────────────────────────────────
  const addNode = useCallback(
    (x: number, y: number, type: NodeType) => {
      takeSnapshot()
      const sx = snap(x, gridSpacing)
      const sy = snap(y, gridSpacing)
      const id = nextId('N')
      const prefix = type === 'shelf' ? 'S' : type === 'charge' ? 'DOCK' : type === 'pick' ? 'PICK' : type === 'drop' ? 'DROP' : type === 'hub' ? 'HUB' : 'N'
      const name = `${prefix}_${id.slice(-4)}`
      const node: DesignerNode = { id, name, x: sx, y: sy, type }
      setNodes((prev) => [...prev, node])
      setSelectedNodeId(id)
      return id
    },
    [gridSpacing, takeSnapshot],
  )

  const moveNode = useCallback(
    (nodeId: string, x: number, y: number) => {
      const sx = snap(x, gridSpacing)
      const sy = snap(y, gridSpacing)
      setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, x: sx, y: sy } : n)))
    },
    [gridSpacing],
  )

  const moveNodeStart = useCallback(() => {
    takeSnapshot()
  }, [takeSnapshot])

  const removeNode = useCallback(
    (nodeId: string) => {
      takeSnapshot()
      setNodes((prev) => prev.filter((n) => n.id !== nodeId))
      setEdges((prev) => prev.filter((e) => e.from !== nodeId && e.to !== nodeId))
      setZones((prev) =>
        prev.map((z) => ({ ...z, nodeIds: z.nodeIds.filter((id) => id !== nodeId) })),
      )
      if (selectedNodeId === nodeId) setSelectedNodeId(null)
    },
    [selectedNodeId, takeSnapshot],
  )

  const updateNodeName = useCallback(
    (nodeId: string, name: string) => {
      takeSnapshot()
      setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, name } : n)))
    },
    [takeSnapshot],
  )

  const updateNodeType = useCallback(
    (nodeId: string, type: NodeType) => {
      takeSnapshot()
      setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, type } : n)))
    },
    [takeSnapshot],
  )

  // ── Edge operations ────────────────────────────────────────────────────
  const addEdge = useCallback(
    (fromId: string, toId: string) => {
      if (fromId === toId) return
      takeSnapshot()
      setEdges((prev) => {
        const exists = prev.some(
          (e) => (e.from === fromId && e.to === toId) || (e.from === toId && e.to === fromId),
        )
        if (exists) return prev
        return [...prev, { id: nextId('E'), from: fromId, to: toId }]
      })
    },
    [takeSnapshot],
  )

  const removeEdge = useCallback(
    (edgeId: string) => {
      takeSnapshot()
      setEdges((prev) => prev.filter((e) => e.id !== edgeId))
    },
    [takeSnapshot],
  )

  // ── Zone operations ────────────────────────────────────────────────────
  const setNodeZone = useCallback(
    (nodeId: string, zoneName: string | undefined) => {
      takeSnapshot()
      setNodes((prev) => prev.map((n) => (n.id === nodeId ? { ...n, zone: zoneName } : n)))
    },
    [takeSnapshot],
  )

  const addZone = useCallback(
    (name: string, type: DesignerZone['type']) => {
      takeSnapshot()
      setZones((prev) => {
        if (prev.some((z) => z.name === name)) return prev
        return [...prev, { name, type, nodeIds: [] }]
      })
    },
    [takeSnapshot],
  )

  // ── Auto-edge: connect nodes within gridSpacing distance ───────────────
  const autoEdges = useCallback(() => {
    takeSnapshot()
    setNodes((currentNodes) => {
      setEdges((currentEdges) => {
        const newEdges = [...currentEdges]
        for (let i = 0; i < currentNodes.length; i++) {
          for (let j = i + 1; j < currentNodes.length; j++) {
            const a = currentNodes[i]!
            const b = currentNodes[j]!
            const dx = a.x - b.x
            const dy = a.y - b.y
            const dist = Math.sqrt(dx * dx + dy * dy)
            if (dist <= gridSpacing * 1.1) {
              const exists = newEdges.some(
                (e) =>
                  (e.from === a.id && e.to === b.id) ||
                  (e.from === b.id && e.to === a.id),
              )
              if (!exists) {
                newEdges.push({ id: nextId('E'), from: a.id, to: b.id })
              }
            }
          }
        }
        return newEdges
      })
      return currentNodes
    })
  }, [gridSpacing, takeSnapshot])

  // ── Import / Export / Validate ─────────────────────────────────────────
  const loadConfig = useCallback(
    (config: WarehouseConfig) => {
      configNameRef.current = config.name || ''
      configDescRef.current = config.description || ''
      takeSnapshot()
      const newNodes: DesignerNode[] = config.nodes.map((n) => ({
        id: nextId('N'),
        name: n.name,
        x: n.x,
        y: n.y,
        type: n.type,
      }))
      // Build name→id map for edges
      const nameToId = new Map<string, string>()
      for (const n of newNodes) nameToId.set(n.name, n.id)

      const newEdges: DesignerEdge[] = config.edges
        .map((e) => {
          const fromId = nameToId.get(e.from)
          const toId = nameToId.get(e.to)
          if (!fromId || !toId) return null
          return { id: nextId('E'), from: fromId, to: toId } as DesignerEdge
        })
        .filter((e): e is DesignerEdge => e !== null)

      const newZones: DesignerZone[] = (config.zones ?? []).map((z) => ({
        name: z.name,
        type: z.type,
        nodeIds: z.nodes.map((name) => nameToId.get(name)).filter((id): id is string => !!id),
      }))

      // Assign zones to nodes
      for (const zone of newZones) {
        for (const nid of zone.nodeIds) {
          const node = newNodes.find((n) => n.id === nid)
          if (node) node.zone = zone.name
        }
      }

      setNodes(newNodes)
      setEdges(newEdges)
      setZones(newZones)
      setSelectedNodeId(null)
      setGridSpacing(config.grid_spacing_m || 2)

      // Reset stacks after load
      undoStack.current = []
      redoStack.current = []
      setCanUndo(false)
      setCanRedo(false)
    },
    [takeSnapshot],
  )

  const exportConfig = useCallback((): WarehouseConfig => {
    // Build zones from node assignments
    const zoneMap = new Map<string, { type: DesignerZone['type']; nodeNames: string[] }>()
    for (const z of zones) {
      zoneMap.set(z.name, { type: z.type, nodeNames: [] })
    }
    for (const n of nodes) {
      if (n.zone) {
        const entry = zoneMap.get(n.zone)
        if (entry) entry.nodeNames.push(n.name)
      }
    }

    const idToName = new Map<string, string>()
    for (const n of nodes) idToName.set(n.id, n.name)

    return {
      name: configNameRef.current || 'Custom Layout',
      description: configDescRef.current || 'Designed in Warehouse Designer',
      grid_spacing_m: gridSpacing,
      nodes: nodes.map((n) => ({ name: n.name, x: n.x, y: n.y, type: n.type })),
      edges: edges
        .map((e) => {
          const from = idToName.get(e.from)
          const to = idToName.get(e.to)
          if (!from || !to) return null
          return { from, to }
        })
        .filter((e): e is { from: string; to: string } => e !== null),
      zones: Array.from(zoneMap.entries()).map(([name, v]) => ({
        name,
        type: v.type,
        nodes: v.nodeNames,
      })),
    }
  }, [nodes, edges, zones, gridSpacing])

  const validate = useCallback(async (): Promise<DesignerValidation> => {
    const config = exportConfig()
    try {
      const res = await fetch(`${API_BASE}/api/designer/validate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return (await res.json()) as DesignerValidation
    } catch {
      // Fallback client-side validation
      const errors: string[] = []
      const warnings: string[] = []
      if (nodes.length === 0) errors.push('No nodes placed')
      if (edges.length === 0) errors.push('No edges defined')
      const names = nodes.map((n) => n.name)
      const dupes = names.filter((n, i) => names.indexOf(n) !== i)
      if (dupes.length > 0) errors.push(`Duplicate node names: ${dupes.join(', ')}`)
      // Check for isolated nodes (no edges)
      const connectedIds = new Set<string>()
      for (const e of edges) {
        connectedIds.add(e.from)
        connectedIds.add(e.to)
      }
      const isolated = nodes.filter((n) => !connectedIds.has(n.id))
      if (isolated.length > 0) warnings.push(`Isolated nodes: ${isolated.map((n) => n.name).join(', ')}`)
      if (!nodes.some((n) => n.type === 'charge')) warnings.push('No charging station')
      return { valid: errors.length === 0, errors, warnings }
    }
  }, [nodes, edges, exportConfig])

  const exportToServer = useCallback(async (): Promise<{ saved: boolean; path?: string; error?: string }> => {
    const config = exportConfig()
    const exportName = (config.name || 'custom_layout').replace(/[^a-zA-Z0-9_-]/g, '_').toLowerCase()
    try {
      const res = await fetch(`${API_BASE}/api/designer/export`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: exportName, config }),
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      return (await res.json()) as { saved: boolean; path?: string }
    } catch (err) {
      return { saved: false, error: err instanceof Error ? err.message : String(err) }
    }
  }, [exportConfig])

  // ── Return ─────────────────────────────────────────────────────────────
  const state: DesignerState = {
    nodes,
    edges,
    zones,
    selectedNodeId,
    selectedTool,
    gridSpacing,
    canUndo,
    canRedo,
  }

  return {
    state,
    // Selection
    setSelectedNodeId,
    setSelectedTool,
    setGridSpacing,
    // Node ops
    addNode,
    moveNode,
    moveNodeStart,
    removeNode,
    updateNodeName,
    updateNodeType,
    // Edge ops
    addEdge,
    removeEdge,
    // Zone ops
    setNodeZone,
    addZone,
    // Bulk ops
    autoEdges,
    // Undo / redo
    undo,
    redo,
    // Import / Export
    loadConfig,
    exportConfig,
    validate,
    exportToServer,
  }
}
