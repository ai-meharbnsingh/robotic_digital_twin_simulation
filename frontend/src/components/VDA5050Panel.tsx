import { useState, useCallback } from 'react'
import { useVDA5050Status, useVDA5050Agvs } from '../hooks/useVDA5050'
import type { VDA5050AgvState } from '../types'

const API_BASE = window.location.origin
const API_KEY = (import.meta.env?.VITE_API_KEY as string | undefined) ?? ''

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['X-API-Key'] = API_KEY
  return headers
}

function batteryColor(pct: number): string {
  if (pct >= 60) return 'bg-success'
  if (pct >= 30) return 'bg-warning'
  return 'bg-danger'
}

function AgvRow({ agv }: { agv: VDA5050AgvState }) {
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const serialNumber = agv.serial_number
  const state = agv.last_state
  const batteryCharge = state?.batteryState?.batteryCharge ?? 0
  const orderId = state?.orderId || null
  const position = state?.agvPosition ?? null
  const operatingMode = state?.operatingMode ?? 'UNKNOWN'
  const driving = state?.driving ?? false
  const errors = state?.errors ?? []
  const errorCount = errors.length

  const handleEStop = useCallback(async () => {
    setSending(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/vda5050/instant-actions`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify({
          agv_id: serialNumber,
          action_type: 'stopPause',
          action_id: `estop-${serialNumber}-${Date.now()}`,
        }),
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`HTTP ${res.status}: ${body}`)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setSending(false)
    }
  }, [serialNumber])

  return (
    <div className="bg-surface rounded px-2 py-1.5 space-y-1">
      {/* Row 1: ID + driving status + mode */}
      <div className="flex items-center gap-2 text-[10px]">
        <span className="text-gray-200 font-semibold truncate">
          {serialNumber}
        </span>
        <span
          className={`ml-auto px-1.5 py-0.5 rounded font-bold text-[9px] ${
            driving ? 'bg-green-700 text-green-200' : 'bg-gray-700 text-gray-400'
          }`}
        >
          {driving ? 'DRIVING' : 'IDLE'}
        </span>
        <span className="px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 text-[9px]">
          {operatingMode}
        </span>
      </div>

      {/* Row 2: battery + order + position + errors + e-stop */}
      <div className="flex items-center gap-2 text-[10px]">
        {/* Battery bar */}
        <div className="flex items-center gap-1 min-w-[80px]">
          <div className="w-12 h-2 rounded bg-gray-700 overflow-hidden">
            <div
              className={`h-full rounded ${batteryColor(batteryCharge)}`}
              style={{ width: `${Math.min(batteryCharge, 100)}%` }}
            />
          </div>
          <span className="text-muted">{batteryCharge.toFixed(0)}%</span>
        </div>

        {/* Current order or idle */}
        <span className="text-muted truncate">
          {orderId ? (
            <>
              Order:{' '}
              <span className="text-gray-300">{orderId}</span>
            </>
          ) : (
            <span className="text-gray-500">idle</span>
          )}
        </span>

        {/* Position */}
        {position && (
          <span className="text-muted ml-auto">
            ({position.x.toFixed(1)}, {position.y.toFixed(1)})
          </span>
        )}

        {/* Error badge */}
        {errorCount > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-red-700 text-red-200 text-[9px] font-bold">
            {errorCount} err
          </span>
        )}

        {/* E-Stop button */}
        <button
          onClick={handleEStop}
          disabled={sending}
          className="px-1.5 py-0.5 rounded bg-danger/80 text-gray-100 text-[9px] font-bold hover:bg-danger disabled:opacity-40 transition-colors flex-shrink-0"
        >
          {sending ? '...' : 'E-Stop'}
        </button>
      </div>

      {/* Error details (only if present) */}
      {errorCount > 0 && (
        <div className="text-[9px] text-danger space-y-0.5 pl-1">
          {errors.slice(0, 3).map((e, i) => (
            <div key={i}>
              [{e.errorLevel}] {e.errorType}: {e.errorDescription}
            </div>
          ))}
          {errorCount > 3 && (
            <div className="text-muted">+{errorCount - 3} more</div>
          )}
        </div>
      )}

      {/* Per-AGV mutation error */}
      {error && (
        <div className="text-[9px] text-danger">{error}</div>
      )}
    </div>
  )
}

export function VDA5050Panel() {
  const { data: status } = useVDA5050Status()
  const { data: agvs } = useVDA5050Agvs()

  const brokerConnected = status?.broker_connected ?? false
  const agvList = agvs ?? []

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <h2 className="text-sm font-semibold text-accent">VDA5050 Gateway</h2>
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            brokerConnected ? 'bg-success' : 'bg-danger'
          }`}
        />
        <span className="text-[10px] text-muted">
          {brokerConnected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {/* Stats row */}
      {status && (
        <div className="grid grid-cols-2 gap-1.5 mb-2 text-[10px]">
          <div className="bg-surface rounded px-2 py-1">
            <div className="text-muted">AGVs Online</div>
            <div className="text-gray-200 font-bold">
              {status.agvs_online}/{status.agvs_total}
            </div>
          </div>
          <div className="bg-surface rounded px-2 py-1">
            <div className="text-muted">Gateway</div>
            <div className="text-gray-200 font-bold">
              {status.gateway_initialized ? 'Active' : 'Inactive'}
            </div>
          </div>
        </div>
      )}

      {/* AGV list */}
      {agvList.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-muted text-[10px]">
          No AGVs reported
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto space-y-1">
          {agvList.map((agv: VDA5050AgvState) => (
            <AgvRow key={agv.serial_number} agv={agv} />
          ))}
        </div>
      )}

    </div>
  )
}
