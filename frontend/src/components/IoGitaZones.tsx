import type { IoGitaZoneStatus } from '../types'

interface IoGitaZonesProps {
  zones: IoGitaZoneStatus[]
}

const ZONE_COLORS: Record<string, string> = {
  dock: 'text-purple-400',
  shelf: 'text-accent',
  ops: 'text-warning',
  aisle: 'text-muted',
}

/**
 * io-gita zone identification status per robot.
 * Shows zone, confidence, and fallback indicator.
 */
export function IoGitaZones({ zones }: IoGitaZonesProps) {
  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">
        io-gita Zones
      </h2>
      {zones.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-sm">
          No zone data
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {zones.map((z) => (
            <div
              key={z.robot_id}
              className="flex items-center gap-2 px-2 py-1.5 bg-surface rounded text-xs"
            >
              {/* Robot ID */}
              <span className="text-gray-300 w-20 truncate font-medium">
                {z.robot_id}
              </span>

              {/* Zone */}
              <span className={`w-12 ${ZONE_COLORS[z.zone] || 'text-muted'}`}>
                {z.zone}
              </span>

              {/* Confidence bar */}
              <div className="flex-1 h-2 bg-surface rounded overflow-hidden border border-border">
                <div
                  className="h-full bg-accent/60 rounded transition-all duration-300"
                  style={{ width: `${z.confidence * 100}%` }}
                />
              </div>
              <span className="text-muted w-10 text-right">
                {(z.confidence * 100).toFixed(0)}%
              </span>

              {/* Fallback indicator */}
              {z.fallback_active && (
                <span className="px-1 py-0.5 bg-warning/20 text-warning rounded text-[10px] font-medium">
                  FALLBACK
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
