import { useApi } from '../hooks/useApi'
import type { MAPFStatus, Bottleneck, MAPFBenchmarkEntry } from '../types'

const POLL_MS = 3000

interface CongestionResponse {
  congestion_map: Record<string, { occupancy: number; wait_time_avg: number; throughput: number }>
  bottlenecks: Bottleneck[]
  total_nodes_tracked: number
}

export function CongestionPanel() {
  const { data: statusData, error: statusError } = useApi<MAPFStatus>('/api/mapf/status', POLL_MS)
  const { data: congestionData } = useApi<CongestionResponse>('/api/mapf/congestion', POLL_MS)

  const error = statusError

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col gap-2 overflow-auto">
      <h2 className="text-sm font-semibold text-gray-300 tracking-wide uppercase">
        MAPF Congestion
      </h2>

      {error && (
        <div className="text-xs text-danger">API error: {error}</div>
      )}

      {statusData && (
        <div className="flex flex-col gap-2">
          {/* Solver stats */}
          <div className="grid grid-cols-3 gap-2 text-xs">
            <Stat label="Total Solves" value={statusData.total_solves ?? 0} />
            <Stat
              label="Last Solve"
              value={`${(statusData.last_solve_time_ms ?? 0).toFixed(1)}ms`}
            />
            <Stat
              label="Conflicts"
              value={statusData.last_conflicts_resolved ?? 0}
            />
          </div>

          {/* Congestion bottlenecks (if available) */}
          {congestionData && congestionData.bottlenecks.length > 0 && (
            <div className="flex flex-col gap-1">
              <div className="text-xs text-muted font-medium">Top Bottlenecks</div>
              {congestionData.bottlenecks.slice(0, 5).map((b) => (
                <div key={b.node_id} className="flex items-center gap-2 text-xs">
                  <span className="text-gray-400 font-mono w-16 truncate">{b.node_id}</span>
                  <div className="flex-1 bg-surface rounded-full h-2 overflow-hidden">
                    <div
                      className="h-full bg-accent rounded-full transition-all"
                      style={{ width: `${Math.min(100, (b.occupancy / Math.max(congestionData.bottlenecks[0].occupancy, 1)) * 100)}%` }}
                    />
                  </div>
                  <span className="text-muted w-12 text-right">{b.occupancy}</span>
                </div>
              ))}
            </div>
          )}

          {/* Benchmark list */}
          <BottleneckList />
        </div>
      )}

      {!statusData && !error && (
        <div className="text-xs text-muted">Loading MAPF status...</div>
      )}
    </div>
  )
}

/** Fetches and displays recent solve benchmarks */
function BottleneckList() {
  const { data } = useApi<{ solves: MAPFBenchmarkEntry[] }>('/api/mapf/benchmarks', 5000)

  if (!data || !data.solves || data.solves.length === 0) {
    return (
      <div className="text-xs text-muted">No benchmark data yet. Run a MAPF solve to see metrics.</div>
    )
  }

  const recent = data.solves.slice(-5).reverse()

  return (
    <div className="flex flex-col gap-1">
      <div className="text-xs text-muted font-medium">Recent Solves</div>
      {recent.map((s, i) => (
        <div key={i} className="flex items-center gap-2 text-xs">
          <span className="text-gray-400 font-mono w-8">{s.solver.toUpperCase()}</span>
          <div className="flex-1 bg-surface rounded-full h-2 overflow-hidden">
            <div
              className="h-full bg-accent rounded-full transition-all"
              style={{ width: `${Math.min(100, (s.solve_time_ms / 100) * 100)}%` }}
            />
          </div>
          <span className="text-muted w-16 text-right">
            {s.solve_time_ms.toFixed(1)}ms
          </span>
          <span className="text-gray-400 w-12 text-right">
            {s.agent_count} bots
          </span>
        </div>
      ))}
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-surface rounded px-2 py-1.5">
      <div className="text-muted text-[10px]">{label}</div>
      <div className="text-gray-200 font-mono">{value}</div>
    </div>
  )
}
