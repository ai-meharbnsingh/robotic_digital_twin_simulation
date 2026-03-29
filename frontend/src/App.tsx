import { useCallback, useState } from 'react'
import { useApi } from './hooks/useApi'
import { useFleetWebSocket } from './hooks/useFleetWebSocket'
import { WarehouseGrid } from './components/WarehouseGrid'
import { RobotStatusPanel } from './components/RobotStatusPanel'
import { TaskQueue } from './components/TaskQueue'
import { BatteryLevels } from './components/BatteryLevels'
import { FleetAnalyticsPanel } from './components/FleetAnalyticsPanel'
import { WesKpiPanel } from './components/WesKpiPanel'
import { HeatMapControls } from './components/HeatMapControls'
import type {
  Robot,
  Task,
  MapNode,
  MapEdge,
  Health,
  FleetAnalytics,
  WesKpi,
  HeatMapData,
  FleetWSEvent,
} from './types'

const POLL_MS = 3000

interface MapData {
  nodes: MapNode[]
  edges: MapEdge[]
}

export default function App() {
  // REST polling for core data
  const { data: robots, error: robotsErr } = useApi<Robot[]>('/api/robots', POLL_MS)
  const { data: tasks, error: tasksErr } = useApi<Task[]>('/api/tasks', POLL_MS)
  const { data: mapData } = useApi<MapData>('/api/map', 0) // Fetch once
  const { data: health } = useApi<Health>('/health', 5000)
  const { data: fleetAnalytics } = useApi<FleetAnalytics>('/api/analytics/fleet', POLL_MS)
  const { data: wesKpi } = useApi<WesKpi>('/api/wes/kpi', POLL_MS)

  // Heat map state
  const [heatmapEnabled, setHeatmapEnabled] = useState(false)
  const [heatmapDuration, setHeatmapDuration] = useState('1h')
  const { data: heatmap } = useApi<HeatMapData>(
    heatmapEnabled ? `/api/analytics/heatmap?duration=${heatmapDuration}&resolution=0.5` : null,
    heatmapEnabled ? 5000 : 0,
  )

  const handleWSEvent = useCallback((_event: FleetWSEvent) => {
    // Future: merge real-time updates into state for lower-latency display
  }, [])

  const { connected: wsConnected } = useFleetWebSocket(handleWSEvent)

  // Aggregate errors
  const apiErrors = [robotsErr, tasksErr].filter(Boolean)

  return (
    <div className="min-h-screen bg-surface text-gray-200 flex flex-col">
      {/* Header */}
      <header className="bg-panel border-b border-border px-4 py-2 flex items-center gap-4">
        <h1 className="text-lg font-bold text-gray-100 tracking-tight">
          RDT Fleet Dashboard
        </h1>

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

      {/* 7-panel grid: 4 columns, 2 rows */}
      <main className="flex-1 p-3 grid grid-cols-4 grid-rows-2 gap-3 min-h-0">
        {/* Row 1 */}
        <WarehouseGrid
          nodes={mapData?.nodes ?? []}
          edges={mapData?.edges ?? []}
          robots={robots ?? []}
          heatmapCells={heatmap?.cells}
          heatmapResolution={heatmap?.resolution_m}
          heatmapEnabled={heatmapEnabled}
        />
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
      </main>
    </div>
  )
}
