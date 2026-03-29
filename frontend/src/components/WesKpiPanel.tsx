import { useState, useCallback } from 'react'
import type { WesKpi } from '../types'

const API_BASE = window.location.origin

interface Props {
  kpi: WesKpi | null
}

interface ImportResult {
  imported: number
  tasks_created: number
  errors: Array<{ row: number; error: string }>
}

export function WesKpiPanel({ kpi }: Props) {
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<ImportResult | null>(null)
  const [dragOver, setDragOver] = useState(false)

  const handleUpload = useCallback(async (file: File) => {
    setImporting(true)
    setResult(null)
    try {
      const formData = new FormData()
      formData.append('file', file)
      const resp = await fetch(`${API_BASE}/api/wes/orders/import`, {
        method: 'POST',
        body: formData,
      })
      const data = await resp.json()
      if (!resp.ok) {
        setResult({ imported: 0, tasks_created: 0, errors: [{ row: 0, error: data.detail || 'Upload failed' }] })
      } else {
        setResult(data)
      }
    } catch {
      setResult({ imported: 0, tasks_created: 0, errors: [{ row: 0, error: 'Upload failed' }] })
    } finally {
      setImporting(false)
    }
  }, [])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files[0]
    if (file) handleUpload(file)
  }, [handleUpload])

  const onFileSelect = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleUpload(file)
    e.target.value = '' // Reset so same file can be re-uploaded
  }, [handleUpload])

  return (
    <div className="bg-panel border border-border rounded-lg p-3 flex flex-col gap-2 overflow-auto">
      <h2 className="text-sm font-semibold text-gray-300 tracking-wide uppercase">
        WES KPIs
      </h2>

      {/* KPI metrics */}
      {kpi && (
        <div className="grid grid-cols-2 gap-2 text-xs">
          <Stat label="Orders/hr" value={kpi.orders_per_hour.toFixed(1)} />
          <Stat label="Pick Accuracy" value={`${kpi.pick_accuracy_pct.toFixed(1)}%`} />
          <Stat label="Throughput" value={`${kpi.throughput_items_per_hour.toFixed(0)}/hr`} />
          <Stat label="Avg Cycle" value={`${kpi.avg_order_cycle_time_s.toFixed(1)}s`} />
          <Stat label="Pending" value={kpi.pending_orders} />
          <Stat label="Completed" value={kpi.completed_orders} />
        </div>
      )}

      {/* CSV Upload zone */}
      <div
        className={`mt-1 border-2 border-dashed rounded-lg p-2 text-center text-xs cursor-pointer transition-colors ${
          dragOver
            ? 'border-blue-400 bg-blue-400/10'
            : 'border-border hover:border-gray-500'
        }`}
        onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        onClick={() => document.getElementById('csv-upload')?.click()}
      >
        <input
          id="csv-upload"
          type="file"
          accept=".csv,.txt"
          className="hidden"
          onChange={onFileSelect}
        />
        {importing ? (
          <span className="text-muted">Importing...</span>
        ) : (
          <span className="text-muted">
            Drop CSV or <span className="text-blue-400 underline">browse</span>
          </span>
        )}
      </div>

      {/* Upload result */}
      {result && (
        <div className={`text-xs rounded px-2 py-1 ${
          result.errors.length === 0
            ? 'bg-green-900/30 text-green-400'
            : result.imported > 0
              ? 'bg-yellow-900/30 text-yellow-400'
              : 'bg-red-900/30 text-red-400'
        }`}>
          {result.imported > 0 && (
            <div>{result.imported} orders imported, {result.tasks_created} tasks created</div>
          )}
          {result.errors.length > 0 && (
            <div>{result.errors.length} errors (row {result.errors.map(e => e.row).join(', ')})</div>
          )}
          {result.imported === 0 && result.errors.length === 0 && (
            <div>No orders imported</div>
          )}
        </div>
      )}
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
