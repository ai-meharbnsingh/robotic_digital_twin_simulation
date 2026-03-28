import type { Robot } from '../types'

interface RobotStatusPanelProps {
  robots: Robot[]
}

const STATUS_DOT: Record<string, string> = {
  idle: 'bg-muted',
  moving: 'bg-accent',
  charging: 'bg-success',
  loading: 'bg-warning',
  unloading: 'bg-warning',
  error: 'bg-danger',
  offline: 'bg-gray-600',
  docking: 'bg-purple-400',
  undocking: 'bg-purple-400',
  waiting: 'bg-yellow-300',
}

/**
 * List of robots with state, battery, and current position.
 */
export function RobotStatusPanel({ robots }: RobotStatusPanelProps) {
  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">Robot Status</h2>
      {robots.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No robots
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {robots.map((r) => (
            <div
              key={r.robot_id}
              className="flex items-center gap-2 px-2 py-1.5 bg-surface rounded text-xs"
            >
              {/* Status dot */}
              <span
                className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[r.status] || 'bg-muted'}`}
              />

              {/* Name */}
              <span className="font-medium text-gray-200 w-20 truncate">
                {r.name || r.robot_id}
              </span>

              {/* Status */}
              <span className="text-muted w-16 truncate">{r.status}</span>

              {/* Battery */}
              <span
                className={`w-10 text-right ${
                  r.battery.charge_pct < 20
                    ? 'text-danger'
                    : r.battery.charge_pct < 50
                      ? 'text-warning'
                      : 'text-success'
                }`}
              >
                {r.battery.charge_pct.toFixed(0)}%
              </span>

              {/* Node */}
              <span className="text-muted ml-auto truncate">
                {r.current_node || '---'}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
