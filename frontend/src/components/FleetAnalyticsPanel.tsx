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

  // Handle both old API format (flat) and new format (detailed)
  const a = analytics as any
  const totalTasks = a.total_tasks ?? 0
  const completed = a.completed_tasks ?? 0
  const failed = a.failed_tasks ?? 0
  const avgTime = a.avg_task_time_s ?? a.avg_task_time ?? 0
  const robots = a.total_robots ?? 0
  const avgBat = a.avg_battery_pct ?? 0
  const throughput = a.throughput_tasks_per_hour ?? a.throughput ?? 0

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col gap-2 overflow-auto">
      <h2 className="text-sm font-semibold text-gray-300 tracking-wide uppercase">
        Fleet Analytics
      </h2>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <Stat label="Total Tasks" value={totalTasks} />
        <Stat label="Completed" value={completed} />
        <Stat label="Failed" value={failed} />
        <Stat label="Avg Time" value={`${Number(avgTime).toFixed(1)}s`} />
        <Stat label="Robots" value={robots} />
        <Stat label="Avg Battery" value={`${Number(avgBat).toFixed(0)}%`} />
        <Stat label="Throughput" value={`${Number(throughput).toFixed(0)}/hr`} className="col-span-2" />
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
