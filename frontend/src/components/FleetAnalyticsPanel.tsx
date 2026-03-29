import type { FleetAnalytics } from '../types'

interface Props {
  analytics: FleetAnalytics | null
}

export function FleetAnalyticsPanel({ analytics }: Props) {
  if (!analytics) {
    return (
      <div className="bg-panel border border-border rounded-lg p-3 flex items-center justify-center text-muted text-sm">
        Loading fleet analytics...
      </div>
    )
  }

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col gap-2 overflow-auto">
      <h2 className="text-sm font-semibold text-gray-300 tracking-wide uppercase">
        Fleet Analytics
      </h2>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Total Tasks" value={analytics.total_tasks} />
        <Stat label="Completed" value={analytics.completed_tasks} />
        <Stat label="Failed" value={analytics.failed_tasks} />
        <Stat label="Avg Time" value={`${analytics.avg_task_time_s.toFixed(1)}s`} />
        <Stat label="Robots" value={analytics.total_robots} />
        <Stat label="Avg Battery" value={`${analytics.avg_battery_pct.toFixed(0)}%`} />
        <Stat label="Throughput" value={`${analytics.throughput_tasks_per_hour.toFixed(0)}/hr`} className="col-span-2" />
      </div>
    </div>
  )
}

function Stat({ label, value, className = '' }: { label: string; value: string | number; className?: string }) {
  return (
    <div className={`bg-surface rounded px-2 py-1.5 ${className}`}>
      <div className="text-muted text-[10px]">{label}</div>
      <div className="text-gray-200 font-mono">{value}</div>
    </div>
  )
}
