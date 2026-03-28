import type { Robot } from '../types'

interface BatteryLevelsProps {
  robots: Robot[]
}

function barColor(pct: number): string {
  if (pct < 20) return 'bg-danger'
  if (pct < 50) return 'bg-warning'
  return 'bg-success'
}

/**
 * Horizontal bar chart showing battery level per robot.
 */
export function BatteryLevels({ robots }: BatteryLevelsProps) {
  const sorted = [...robots].sort(
    (a, b) => a.battery.charge_pct - b.battery.charge_pct
  )

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">Battery Levels</h2>
      {sorted.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No robots
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {sorted.map((r) => {
            const pct = r.battery.charge_pct
            return (
              <div key={r.robot_id} className="flex items-center gap-2 text-xs">
                {/* Robot name */}
                <span className="w-20 truncate text-gray-300">
                  {r.name || r.robot_id}
                </span>

                {/* Bar background */}
                <div className="flex-1 h-3 bg-surface rounded overflow-hidden">
                  <div
                    className={`h-full rounded transition-all duration-500 ${barColor(pct)}`}
                    style={{ width: `${Math.max(pct, 1)}%` }}
                  />
                </div>

                {/* Percentage */}
                <span
                  className={`w-10 text-right font-mono ${
                    pct < 20 ? 'text-danger' : pct < 50 ? 'text-warning' : 'text-success'
                  }`}
                >
                  {pct.toFixed(0)}%
                </span>

                {/* Charging indicator */}
                {r.battery.is_charging && (
                  <span className="text-success text-[10px]">CHG</span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
