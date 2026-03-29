import type { HeatMapData, ZoneCongestion } from '../types'

interface HeatMapControlsProps {
  enabled: boolean
  onToggle: (enabled: boolean) => void
  duration: string
  onDurationChange: (duration: string) => void
  heatmap: HeatMapData | null
}

const DURATIONS = ['1h', '4h', '8h', '24h']

const CONGESTION_COLOR: Record<string, string> = {
  low: 'text-success',
  medium: 'text-yellow-400',
  high: 'text-orange-400',
  critical: 'text-danger',
}

function getCongestionLevel(score: number): string {
  if (score < 0.5) return 'low'
  if (score < 2.0) return 'medium'
  if (score < 5.0) return 'high'
  return 'critical'
}

/**
 * Heat map controls: toggle, time window selector, zone congestion scores.
 */
export function HeatMapControls({
  enabled,
  onToggle,
  duration,
  onDurationChange,
  heatmap,
}: HeatMapControlsProps) {
  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-sm font-semibold text-accent">Heat Map</h2>

        {/* Toggle */}
        <button
          onClick={() => onToggle(!enabled)}
          className={`px-2 py-0.5 rounded text-[10px] font-bold ${
            enabled
              ? 'bg-accent text-gray-900'
              : 'bg-surface text-muted border border-border'
          }`}
        >
          {enabled ? 'ON' : 'OFF'}
        </button>
      </div>

      {/* Duration selector */}
      <div className="flex gap-1 mb-3">
        {DURATIONS.map((d) => (
          <button
            key={d}
            onClick={() => onDurationChange(d)}
            className={`flex-1 px-1 py-1 rounded text-[10px] font-medium ${
              duration === d
                ? 'bg-accent text-gray-900'
                : 'bg-surface text-muted hover:text-gray-200'
            }`}
          >
            {d}
          </button>
        ))}
      </div>

      {/* Stats */}
      {heatmap && enabled && (
        <div className="text-[10px] text-muted mb-2 flex gap-3">
          <span>Source: {heatmap.data_source}</span>
          <span>{heatmap.cell_count} cells</span>
          <span>{heatmap.query_ms}ms</span>
        </div>
      )}

      {/* Zone congestion scores */}
      {heatmap && enabled && heatmap.zones.length > 0 && (
        <div className="flex-1 overflow-y-auto space-y-1">
          <div className="text-[10px] text-muted font-semibold mb-1">
            Zone Congestion
          </div>
          {heatmap.zones.map((z: ZoneCongestion) => {
            const level = getCongestionLevel(z.congestion_score)
            return (
              <div
                key={z.zone_name}
                className="flex items-center gap-2 px-2 py-1 bg-surface rounded text-[10px]"
              >
                <span className="font-medium text-gray-300 w-24 truncate">
                  {z.zone_name}
                </span>
                <span className="text-muted w-10">{z.zone_type}</span>
                <span className={`ml-auto font-bold ${CONGESTION_COLOR[level]}`}>
                  {z.congestion_score.toFixed(1)}
                </span>
              </div>
            )
          })}
        </div>
      )}

      {/* Empty state */}
      {(!heatmap || !enabled) && (
        <div className="flex-1 flex items-center justify-center text-muted text-[10px]">
          {enabled ? 'Loading...' : 'Enable to view traffic density'}
        </div>
      )}
    </div>
  )
}
