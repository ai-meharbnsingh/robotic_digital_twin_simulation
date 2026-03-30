import { Component, useCallback, useRef, useState, lazy, Suspense, type ReactNode } from 'react'
import { useApi } from './hooks/useApi'
import { useFleetWebSocket } from './hooks/useFleetWebSocket'
import type { FleetWSEvent } from './types'
import { WarehouseGrid } from './components/WarehouseGrid'
import { WarehouseDesigner } from './components/WarehouseDesigner'

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
import { ScenarioPanel } from './components/ScenarioPanel'
import { ScenarioComparisonDashboard } from './components/ScenarioComparisonDashboard'
import { VDA5050Panel } from './components/VDA5050Panel'
import { CongestionPanel } from './components/CongestionPanel'
import { useROS2Status } from './hooks/useROS2'
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
} from './types'

/** ErrorBoundary — catches R3F crashes so the 2D dashboard survives */
class Scene3DErrorBoundary extends Component<
  { children: ReactNode; onError: () => void },
  { hasError: boolean; error: string }
> {
  state = { hasError: false, error: '' }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }

  componentDidCatch() {
    this.props.onError()
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="bg-panel rounded border border-danger/30 flex flex-col items-center justify-center text-sm p-4 gap-2">
          <span className="text-danger font-semibold">3D scene crashed</span>
          <span className="text-muted text-xs">{this.state.error}</span>
          <button
            className="text-xs px-3 py-1 rounded border border-border text-muted hover:text-gray-200"
            onClick={() => this.setState({ hasError: false, error: '' })}
          >
            Retry 3D
          </button>
        </div>
      )
    }
    return this.props.children
  }
}

const POLL_MS = 3000

type ViewMode = '2d' | '3d' | 'designer'

interface MapData {
  nodes: MapNode[]
  edges: MapEdge[]
}

export default function App() {
  // View mode toggle — 3D stays mounted once loaded to preserve camera/state
  const [viewMode, setViewMode] = useState<ViewMode>('2d')
  const [has3DLoaded, setHas3DLoaded] = useState(false)
  const [selectedRobotId, setSelectedRobotId] = useState<string | null>(null)
  const [followMode, setFollowMode] = useState(false)

  // Scenario comparison view
  const [compareIds, setCompareIds] = useState<string[] | null>(null)

  const handleSetViewMode = useCallback((mode: ViewMode) => {
    setViewMode(mode)
    if (mode === '3d') setHas3DLoaded(true)
  }, [])

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

  // WS events go to 3D scene via ref callback — avoids React re-render storm
  const wsHandlerRef = useRef<((event: FleetWSEvent) => void) | null>(null)
  const handleWSEvent = useCallback((event: FleetWSEvent) => {
    wsHandlerRef.current?.(event)
  }, [])
  const { connected: wsConnected } = useFleetWebSocket(handleWSEvent)

  // ROS2 bridge status
  const { data: ros2Status } = useROS2Status(5000)

  // Aggregate errors
  const apiErrors = [robotsErr, tasksErr, wavesErr].filter(Boolean)

  const handleSelectRobot = useCallback((id: string | null) => {
    setSelectedRobotId(id)
    if (!id) setFollowMode(false)
  }, [])

  const handleCompareScenarios = useCallback((ids: string[]) => {
    setCompareIds(ids)
  }, [])

  const handleCloseComparison = useCallback(() => {
    setCompareIds(null)
  }, [])

  // Scenario comparison view — full-screen overlay replaces dashboard
  if (compareIds && compareIds.length >= 2) {
    return (
      <ScenarioComparisonDashboard
        scenarioIds={compareIds}
        onClose={handleCloseComparison}
      />
    )
  }

  return (
    <div className="min-h-screen bg-surface text-gray-200 flex flex-col">
      {/* Header */}
      <header className="bg-panel border-b border-border px-4 py-2 flex items-center gap-4">
        <h1 className="text-lg font-bold text-gray-100 tracking-tight">
          RDT Fleet Dashboard
        </h1>

        {/* 2D / 3D / Designer toggle */}
        <div className="flex items-center gap-0 border border-border rounded overflow-hidden text-xs">
          <button
            className={`px-3 py-1 transition-colors ${
              viewMode === '2d'
                ? 'bg-accent text-panel font-semibold'
                : 'bg-panel text-muted hover:text-gray-200'
            }`}
            onClick={() => handleSetViewMode('2d')}
          >
            2D
          </button>
          <button
            className={`px-3 py-1 transition-colors ${
              viewMode === '3d'
                ? 'bg-accent text-panel font-semibold'
                : 'bg-panel text-muted hover:text-gray-200'
            }`}
            onClick={() => handleSetViewMode('3d')}
          >
            3D
          </button>
          <button
            className={`px-3 py-1 transition-colors ${
              viewMode === 'designer'
                ? 'bg-accent text-panel font-semibold'
                : 'bg-panel text-muted hover:text-gray-200'
            }`}
            onClick={() => handleSetViewMode('designer')}
          >
            Designer
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

        {/* ROS2 bridge status */}
        <div className="flex items-center gap-1.5 text-xs">
          <span
            className={`w-2 h-2 rounded-full ${
              ros2Status?.ros2_available ? 'bg-success' : 'bg-gray-500'
            }`}
          />
          <span className="text-muted">
            ROS2 {ros2Status ? (ros2Status.ros2_available ? 'LIVE' : 'SIM') : '...'}
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

      {/* Designer mode — full-width, replaces dashboard grid */}
      {viewMode === 'designer' && (
        <main className="flex-1 min-h-0">
          <WarehouseDesigner />
        </main>
      )}

      {/* Dashboard grid (2D / 3D modes) */}
      {viewMode !== 'designer' && (
        <main className="flex-1 p-3 grid grid-cols-4 auto-rows-fr gap-3 min-h-0">
          {/* Row 1: 2D and 3D views — 3D stays mounted (hidden) to preserve camera/state */}
          <div className={viewMode === '2d' ? '' : 'hidden'}>
            <WarehouseGrid
              nodes={mapData?.nodes ?? []}
              edges={mapData?.edges ?? []}
              robots={robots ?? []}
              heatmapCells={heatmap?.cells}
              heatmapResolution={heatmap?.resolution_m}
              heatmapEnabled={heatmapEnabled}
            />
          </div>
          {has3DLoaded && (
            <div className={viewMode === '3d' ? '' : 'hidden'}>
              <Scene3DErrorBoundary onError={() => handleSetViewMode('2d')}>
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
                    wsHandlerRef={wsHandlerRef}
                  />
                </Suspense>
              </Scene3DErrorBoundary>
            </div>
          )}
          <RobotStatusPanel
            robots={robots ?? []}
            selectedRobotId={viewMode === '3d' ? selectedRobotId : undefined}
            onSelectRobot={viewMode === '3d' ? handleSelectRobot : undefined}
          />
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

          {/* Row 3: Scenarios + VDA5050 */}
          <div className="col-span-2">
            <ScenarioPanel onCompare={handleCompareScenarios} />
          </div>
          <div className="col-span-2">
            <VDA5050Panel />
          </div>

          {/* Row 4: MAPF Congestion (Phase 11) */}
          <div className="col-span-2">
            <CongestionPanel />
          </div>
        </main>
      )}
    </div>
  )
}
