import type { Robot } from '../types'

interface RobotStatusPanelProps {
  robots: Robot[]
  selectedRobotId?: string | null
  onSelectRobot?: (id: string | null) => void
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

const TYPE_BADGE: Record<string, { label: string; color: string }> = {
  differential_drive: { label: 'AMR', color: 'bg-sky-700 text-sky-200' },
  unidirectional:     { label: 'AGV', color: 'bg-orange-700 text-orange-200' },
  omnidirectional:    { label: 'OMNI', color: 'bg-purple-700 text-purple-200' },
}

const UNKNOWN_BADGE = { label: '???', color: 'bg-gray-700 text-gray-300' }

/**
 * List of robots with type badge, state, battery, and current position.
 */
export function RobotStatusPanel({ robots, selectedRobotId, onSelectRobot }: RobotStatusPanelProps) {
  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">Robot Status</h2>
      {robots.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No robots
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {robots.map((r) => {
            const badge = TYPE_BADGE[r.robot_type] || UNKNOWN_BADGE
            return (
              <div
                key={r.robot_id}
                className={`flex items-center gap-2 px-2 py-1.5 rounded text-xs cursor-pointer transition-colors ${
                  selectedRobotId === r.robot_id
                    ? 'bg-accent/20 border border-accent/40'
                    : 'bg-surface hover:bg-surface/80'
                }`}
                onClick={() => onSelectRobot?.(
                  selectedRobotId === r.robot_id ? null : r.robot_id
                )}
              >
                {/* Status dot */}
                <span
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[r.status] || 'bg-muted'}`}
                />

                {/* Type badge */}
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-bold flex-shrink-0 ${badge.color}`}
                >
                  {badge.label}
                </span>

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
            )
          })}
        </div>
      )}
    </div>
  )
}
