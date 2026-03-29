import { useCallback, useState, lazy, Suspense } from 'react'
import { useApi } from './hooks/useApi'
import { useFleetWebSocket } from './hooks/useFleetWebSocket'
import { WarehouseGrid } from './components/WarehouseGrid'

// Lazy-load 3D scene (Three.js is ~1MB — only load when user clicks 3D tab)
const Warehouse3D = lazy(() =>
  import('./components/Warehouse3D').then((m) => ({ default: m.Warehouse3D }))
)
import { RobotStatusPanel } from './components/RobotStatusPanel'
import { TaskQueue } from './components/TaskQueue'
import { BatteryLevels } from './components/BatteryLevels'
import { FleetAnalyticsPanel } from './components/FleetAnalyticsPanel'
import { WesKpiPanel } from './components/WesKpiPanel'
import { HeatMapControls } from './components/HeatMapControls'
import { WaveStatusPanel } from './components/WaveStatusPanel'
import type {
  Robot,
  Task,
  MapNode,
  MapEdge,
  Health,
  FleetAnalytics,
  WesKpi,
  HeatMapData,
  WavesResponse,
  FleetWSEvent,
} from './types'

const POLL_MS = 3000

type ViewMode = '2d' | '3d'

interface MapData {
  nodes: MapNode[]
  edges: MapEdge[]
}

export default function App() {
  // View mode toggle
  const [viewMode, setViewMode] = useState<ViewMode>('2d')
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null)
  const [followMode, setFollowMode] = useState(false)

  // REST polling for core data
  const { data: robots, error: robotsErr } = useApi<Robot[]>('/api/robots', POLL_MS)
  const { data: tasks, error: tasksErr } = useApi<Task[]>('/api/tasks', POLL_MS)
  const { data: mapData } = useApi<MapData>('/api/map', 0) // Fetch once
  const { data: health } = useApi<Health>('/health', 5000)
  const { data: fleetAnalytics } = useApi<FleetAnalytics>('/api/analytics/fleet', POLL_MS)
  const { data: wesKpi } = useApi<WesKpi>('/api/wes/kpi', POLL_MS)
  const { data: waves, error: wavesErr } = useApi<WavesResponse>('/api/wes/waves', POLL_MS)

  // Heat map state
  const [heatmapEnabled, setHeatmapEnabled] = useState(false)
  const [heatmapDuration, setHeatmapDuration] = useState('1h')
  const { data: heatmap } = useApi<HeatMapData>(
    heatmapEnabled ? `/api/analytics/heatmap?duration=${heatmapDuration}&resolution=0.5` : null,
    heatmapEnabled ? 5000 : 0,
  )

  const handleWSEvent = useCallback((_event: FleetWSEvent) => {
    // WS events forwarded to 3D scene via lastEvent from useFleetWebSocket
  }, [])

  const { connected: wsConnected, lastEvent: lastWSEvent } = useFleetWebSocket(handleWSEvent)

  // Aggregate errors
  const apiErrors = [robotsErr, tasksErr, wavesErr].filter(Boolean)

  const handleSelectRobot = useCallback((id: string | null) => {
    setSelectedRobotId(id)
    if (!id) setFollowMode(false)
  }, [])

  return (
    <div className="min-h-screen bg-surface text-gray-200 flex flex-col">
      {/* Header */}
      <header className="bg-panel border-b border-border px-4 py-2 flex items-center gap-4">
        <h1 className="text-lg font-bold text-gray-100 tracking-tight">
          RDT Fleet Dashboard
        </h1>

        {/* 2D / 3D toggle */}
        <div className="flex items-center gap-0 border border-border rounded overflow-hidden text-xs">
          <button
            className={`px-3 py-1 transition-colors ${
              viewMode === '2d'
                ? 'bg-accent text-panel font-semibold'
                : 'bg-panel text-muted hover:text-gray-200'
            }`}
            onClick={() => setViewMode('2d')}
          >
            2D
          </button>
          <button
            className={`px-3 py-1 transition-colors ${
              viewMode === '3d'
                ? 'bg-accent text-panel font-semibold'
                : 'bg-panel text-muted hover:text-gray-200'
            }`}
            onClick={() => setViewMode('3d')}
          >
            3D
          </button>
        </div>

        {/* Follow mode toggle (3D only) */}
        {viewMode === '3d' && selectedRobotId && (
          <button
            className={`text-xs px-2 py-1 rounded border transition-colors ${
              followMode
                ? 'border-accent bg-accent/20 text-accent'
                : 'border-border text-muted hover:text-gray-200'
            }`}
            onClick={() => setFollowMode((f) => !f)}
          >
            {followMode ? 'Following' : 'Follow'} {selectedRobotId}
          </button>
        )}

        {/* Health indicator */}
        <div className="flex items-center gap-1.5 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              health?.status === 'healthy' || health?.status === 'degraded' ? 'bg-success' : 'bg-danger'
            }`}
          />
          <span className="text-muted">
            {health ? health.status.toUpperCase() : 'CONNECTING'}
          </span>
        </div>

        {/* WS status */}
        <div className="flex items-center gap-1.5 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              wsConnected ? 'bg-success' : 'bg-warning'
            }`}
          />
          <span className="text-muted">
            WS {wsConnected ? 'LIVE' : 'RECONNECTING'}
          </span>
        </div>

        {/* Service status (from health) */}
        {health && (
          <div className="ml-auto flex items-center gap-3 text-[10px] text-muted">
            <span>
              MongoDB{' '}
              <span className={health.mongodb_ok ? 'text-success' : 'text-danger'}>
                {health.mongodb_ok ? 'OK' : 'DOWN'}
              </span>
            </span>
            <span>
              Redis{' '}
              <span className={health.redis_ok ? 'text-success' : 'text-danger'}>
                {health.redis_ok ? 'OK' : 'DOWN'}
              </span>
            </span>
            <span>
              RabbitMQ{' '}
              <span className={health.rabbitmq_ok ? 'text-success' : 'text-danger'}>
                {health.rabbitmq_ok ? 'OK' : 'DOWN'}
              </span>
            </span>
          </div>
        )}
      </header>

      {/* Error banner */}
      {apiErrors.length > 0 && (
        <div className="bg-danger/10 border-b border-danger/30 px-4 py-1.5 text-xs text-danger">
          API Error: {apiErrors.join(' | ')}
        </div>
      )}

      {/* 7-panel grid: 4 columns, 2 rows — col 1 row 1 switches between 2D and 3D */}
      <main className="flex-1 p-3 grid grid-cols-4 grid-rows-2 gap-3 min-h-0">
        {/* Row 1 */}
        {viewMode === '2d' ? (
          <WarehouseGrid
            nodes={mapData?.nodes ?? []}
            edges={mapData?.edges ?? []}
            robots={robots ?? []}
            heatmapCells={heatmap?.cells}
            heatmapResolution={heatmap?.resolution_m}
            heatmapEnabled={heatmapEnabled}
          />
        ) : (
          <Suspense fallback={
            <div className="bg-panel rounded border border-border flex items-center justify-center text-muted text-sm">
              Loading 3D scene...
            </div>
          }>
            <Warehouse3D
              nodes={mapData?.nodes ?? []}
              edges={mapData?.edges ?? []}
              robots={robots ?? []}
              heatmapCells={heatmap?.cells}
              heatmapResolution={heatmap?.resolution_m}
              heatmapEnabled={heatmapEnabled}
              selectedRobotId={selectedRobotId}
              onSelectRobot={handleSelectRobot}
              followMode={followMode}
              lastWSEvent={lastWSEvent ?? null}
            />
          </Suspense>
        )}
        <RobotStatusPanel robots={robots ?? []} />
        <TaskQueue tasks={tasks ?? []} />
        <HeatMapControls
          enabled={heatmapEnabled}
          onToggle={setHeatmapEnabled}
          duration={heatmapDuration}
          onDurationChange={setHeatmapDuration}
          heatmap={heatmap ?? null}
        />

        {/* Row 2 */}
        <BatteryLevels robots={robots ?? []} />
        <FleetAnalyticsPanel analytics={fleetAnalytics} />
        <WesKpiPanel kpi={wesKpi} />
        <WaveStatusPanel waves={waves ?? null} />
      </main>
    </div>
  )
}
