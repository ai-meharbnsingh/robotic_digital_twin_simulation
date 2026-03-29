import type { WavesResponse, Wave } from '../types'

interface WaveStatusPanelProps {
  waves: WavesResponse | null
}

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-700 text-yellow-200',
  active: 'bg-sky-700 text-sky-200',
  completed: 'bg-green-700 text-green-200',
}

function formatTime(unix: number | null): string {
  if (!unix) return '—'
  return new Date(unix * 1000).toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
  })
}

/**
 * Wave status panel — shows active/pending/completed waves with order counts.
 */
export function WaveStatusPanel({ waves }: WaveStatusPanelProps) {
  const summary = waves?.summary
  const waveList = waves?.waves ?? []

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">Wave Planner</h2>

      {/* Summary counters */}
      {summary && (
        <div className="flex gap-2 mb-2 text-[10px]">
          <span className="px-2 py-0.5 rounded bg-yellow-700/30 text-yellow-300">
            {summary.pending} pending
          </span>
          <span className="px-2 py-0.5 rounded bg-sky-700/30 text-sky-300">
            {summary.active} active
          </span>
          <span className="px-2 py-0.5 rounded bg-green-700/30 text-green-300">
            {summary.completed} done
          </span>
        </div>
      )}

      {/* Wave list */}
      {waveList.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-[10px]">
          No waves — create rules or inject orders
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {waveList.map((w: Wave) => (
            <div
              key={w.wave_id}
              className="px-2 py-1.5 bg-surface rounded text-[10px] space-y-0.5"
            >
              <div className="flex items-center gap-2">
                <span
                  className={`px-1.5 py-0.5 rounded font-bold ${STATUS_COLORS[w.status] || 'bg-gray-700 text-gray-300'}`}
                >
                  {w.status.toUpperCase()}
                </span>
                <span className="text-gray-300 font-medium truncate">
                  {w.wave_id.slice(0, 8)}
                </span>
                {w.zone_affinity && (
                  <span className="text-muted ml-auto">{w.zone_affinity}</span>
                )}
              </div>
              <div className="flex gap-3 text-muted">
                <span>{w.order_ids.length} orders</span>
                <span>{w.task_ids.length} tasks</span>
                <span>max {w.max_robots} robots</span>
                <span className="ml-auto">{formatTime(w.created_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
