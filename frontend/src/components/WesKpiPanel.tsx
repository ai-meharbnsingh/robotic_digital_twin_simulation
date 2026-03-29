import type { WesKpi } from '../types'

interface Props {
  kpi: WesKpi | null
}

export function WesKpiPanel({ kpi }: Props) {
  if (!kpi) {
    return (
      <div className="bg-panel border border-border rounded-lg p-3 flex items-center justify-center text-muted text-sm">
        Loading WES KPIs...
      </div>
    )
  }

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col gap-2 overflow-auto">
      <h2 className="text-sm font-semibold text-gray-300 tracking-wide uppercase">
        WES KPIs
      </h2>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Orders/hr" value={kpi.orders_per_hour.toFixed(1)} />
        <Stat label="Pick Accuracy" value={`${kpi.pick_accuracy_pct.toFixed(1)}%`} />
        <Stat label="Throughput" value={`${kpi.throughput_items_per_hour.toFixed(0)}/hr`} />
        <Stat label="Avg Cycle" value={`${kpi.avg_order_cycle_time_s.toFixed(1)}s`} />
        <Stat label="Pending" value={kpi.pending_orders} />
        <Stat label="Completed" value={kpi.completed_orders} />
      </div>
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
