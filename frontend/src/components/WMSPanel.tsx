import { useState, useCallback } from 'react'
import { useWMSStatus, useWMSOrders, useWMSDlq } from '../hooks/useWMS'
import type { WMSOrder, WMSDlqEntry } from '../types'

const API_BASE = window.location.origin
const API_KEY = (import.meta.env?.VITE_API_KEY as string | undefined) ?? ''

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['X-API-Key'] = API_KEY
  return headers
}

export function WMSPanel() {
  const { data: status } = useWMSStatus()
  const { data: ordersResp } = useWMSOrders()
  const { data: dlqResp } = useWMSDlq()

  const [syncing, setSyncing] = useState(false)
  const [syncResult, setSyncResult] = useState<string | null>(null)

  const connectorType = status?.type ?? 'unknown'
  const connected = status?.connected ?? false
  const initialized = status?.connector_initialized ?? false
  const dlqTotal = status?.dlq?.total ?? 0

  const orders = ordersResp?.orders ?? []
  const dlqEntries = dlqResp?.dead_letters ?? []

  const handleSync = useCallback(async () => {
    setSyncing(true)
    setSyncResult(null)
    try {
      const res = await fetch(`${API_BASE}/api/wms/sync`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`HTTP ${res.status}: ${body}`)
      }
      const data = await res.json()
      setSyncResult(`Synced ${data.synced} orders (${data.errors} errors)`)
    } catch (err) {
      setSyncResult(err instanceof Error ? err.message : String(err))
    } finally {
      setSyncing(false)
    }
  }, [])

  return (
    <div className="bg-panel border border-border rounded-lg p-3 h-full flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <h2 className="text-sm font-semibold text-accent">WMS Connector</h2>
        <span
          className={`w-2 h-2 rounded-full flex-shrink-0 ${
            connected ? 'bg-success' : 'bg-danger'
          }`}
        />
        <span className="text-[10px] text-muted">
          {initialized ? `${connectorType.toUpperCase()} ${connected ? 'Connected' : 'Disconnected'}` : 'Not Initialized'}
        </span>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-1.5 mb-2 text-[10px]">
        <div className="bg-surface rounded px-2 py-1">
          <div className="text-muted">Connector</div>
          <div className="text-gray-200 font-bold">{connectorType.toUpperCase()}</div>
        </div>
        <div className="bg-surface rounded px-2 py-1">
          <div className="text-muted">Orders</div>
          <div className="text-gray-200 font-bold">{orders.length}</div>
        </div>
        <div className="bg-surface rounded px-2 py-1">
          <div className="text-muted">DLQ</div>
          <div className={`font-bold ${dlqTotal > 0 ? 'text-danger' : 'text-gray-200'}`}>
            {dlqTotal}
          </div>
        </div>
      </div>

      {/* Sync button */}
      <div className="mb-2">
        <button
          onClick={handleSync}
          disabled={syncing || !initialized}
          className="w-full px-2 py-1 rounded bg-accent/80 text-panel text-[10px] font-bold hover:bg-accent disabled:opacity-40 transition-colors"
        >
          {syncing ? 'Syncing...' : 'Sync Orders'}
        </button>
        {syncResult && (
          <div className="text-[9px] text-muted mt-1">{syncResult}</div>
        )}
      </div>

      {/* Recent orders */}
      <div className="flex-1 overflow-y-auto space-y-1">
        {orders.length === 0 ? (
          <div className="flex items-center justify-center text-muted text-[10px] py-2">
            No orders synced
          </div>
        ) : (
          orders.slice(-5).reverse().map((order: WMSOrder, i: number) => (
            <div key={order.order_id || i} className="bg-surface rounded px-2 py-1 text-[10px]">
              <div className="flex items-center gap-2">
                <span className="text-gray-200 font-semibold truncate">
                  {order.order_id || 'N/A'}
                </span>
                <span className="ml-auto px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 text-[9px]">
                  {order.source}
                </span>
              </div>
              <div className="text-muted">
                {order.items?.length ?? 0} items | P{order.priority} | {order.customer || 'N/A'}
              </div>
            </div>
          ))
        )}
      </div>

      {/* DLQ entries (if any) */}
      {dlqEntries.length > 0 && (
        <div className="mt-2 border-t border-border pt-1">
          <div className="text-[10px] text-danger font-semibold mb-1">Dead Letters</div>
          {dlqEntries.slice(0, 3).map((entry: WMSDlqEntry, i: number) => (
            <div key={entry.message_id || i} className="bg-surface rounded px-2 py-0.5 text-[9px] text-danger mb-0.5">
              {entry.message_id}: {entry.error}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
