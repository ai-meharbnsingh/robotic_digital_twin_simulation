import type { SGPrediction } from '../types'

interface SGPredictionsProps {
  predictions: SGPrediction[]
}

const SEVERITY_STYLE: Record<string, string> = {
  info: 'border-l-accent bg-accent/5',
  warning: 'border-l-warning bg-warning/5',
  error: 'border-l-danger bg-danger/5',
  critical: 'border-l-danger bg-danger/10',
}

const TYPE_LABEL: Record<string, string> = {
  bottleneck: 'BOTTLENECK',
  deadlock: 'DEADLOCK',
  congestion: 'CONGESTION',
  battery_critical: 'BATTERY',
}

/**
 * SG (Semantic Gravity) prediction alerts.
 * Shows bottleneck, deadlock, congestion, and battery warnings.
 */
export function SGPredictions({ predictions }: SGPredictionsProps) {
  const sorted = [...predictions].sort((a, b) => {
    const sev = { critical: 0, error: 1, warning: 2, info: 3 }
    return (sev[a.severity] ?? 4) - (sev[b.severity] ?? 4)
  })

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">
        SG Predictions
        {predictions.length > 0 && (
          <span className="ml-2 text-danger font-normal">
            ({predictions.length} active)
          </span>
        )}
      </h2>
      {sorted.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-success text-sm">
          No active alerts
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1.5">
          {sorted.map((p) => (
            <div
              key={p.prediction_id}
              className={`border-l-2 rounded px-2 py-1.5 text-xs ${SEVERITY_STYLE[p.severity] || ''}`}
            >
              <div className="flex items-center gap-2 mb-0.5">
                <span className="font-semibold text-gray-200">
                  {TYPE_LABEL[p.prediction_type] || p.prediction_type}
                </span>
                <span className="text-muted">
                  {(p.confidence * 100).toFixed(0)}% conf
                </span>
                <span className="ml-auto text-muted text-[10px]">
                  {p.severity.toUpperCase()}
                </span>
              </div>
              <div className="text-gray-400">{p.message}</div>
              {p.affected_robots.length > 0 && (
                <div className="text-muted mt-0.5">
                  Robots: {p.affected_robots.join(', ')}
                </div>
              )}
              {p.affected_nodes.length > 0 && (
                <div className="text-muted">
                  Nodes: {p.affected_nodes.join(', ')}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
