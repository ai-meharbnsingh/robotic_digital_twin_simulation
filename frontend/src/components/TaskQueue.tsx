import { useMemo } from 'react'
import type { Task } from '../types'

interface TaskQueueProps {
  tasks: Task[]
}

const STATUS_BADGE: Record<string, string> = {
  pending: 'bg-muted/30 text-muted',
  assigned: 'bg-accent/20 text-accent',
  in_progress: 'bg-warning/20 text-warning',
  completed: 'bg-success/20 text-success',
  failed: 'bg-danger/20 text-danger',
  cancelled: 'bg-gray-600/20 text-gray-500',
}

/**
 * Task queue showing pending, active, and completed tasks.
 */
export function TaskQueue({ tasks }: TaskQueueProps) {
  const { pending, active, completed } = useMemo(() => {
    const p: Task[] = []
    const a: Task[] = []
    const c: Task[] = []
    for (const t of tasks) {
      if (t.status === 'pending' || t.status === 'assigned') p.push(t)
      else if (t.status === 'in_progress') a.push(t)
      else c.push(t)
    }
    // Sort pending by priority descending
    p.sort((x, y) => y.priority - x.priority)
    // Sort completed by completed_at descending
    c.sort((x, y) => {
      const ta = x.completed_at || x.created_at
      const tb = y.completed_at || y.created_at
      return tb.localeCompare(ta)
    })
    return { pending: p, active: a, completed: c.slice(0, 10) }
  }, [tasks])

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      <h2 className="text-sm font-semibold text-accent mb-2">
        Task Queue
        <span className="text-muted font-normal ml-2">
          ({pending.length} pending / {active.length} active / {completed.length} done)
        </span>
      </h2>
      <div className="flex-1 overflow-y-auto space-y-1">
        {[...active, ...pending, ...completed].map((t) => (
          <div
            key={t.task_id}
            className="flex items-center gap-2 px-2 py-1 bg-surface rounded text-xs"
          >
            {/* Status badge */}
            <span
              className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_BADGE[t.status] || ''}`}
            >
              {t.status}
            </span>

            {/* Type */}
            <span className="text-gray-300 w-14 truncate">{t.task_type}</span>

            {/* Route */}
            <span className="text-muted truncate">
              {t.source_node} → {t.destination_node}
            </span>

            {/* Priority */}
            <span className="ml-auto text-muted">P{t.priority}</span>

            {/* Robot */}
            {t.assigned_robot_id && (
              <span className="text-accent text-[10px]">{t.assigned_robot_id}</span>
            )}
          </div>
        ))}
        {tasks.length === 0 && (
          <div className="flex-1 flex items-center justify-center text-muted text-sm py-4">
            No tasks
          </div>
        )}
      </div>
    </div>
  )
}
