import { useCallback, useEffect, useRef, useState } from 'react'
import type { FleetWSEvent } from '../types'

const WS_URL = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/fleet`
const MAX_BACKOFF_MS = 30_000
const INITIAL_BACKOFF_MS = 1_000

interface UseFleetWebSocketResult {
  connected: boolean
  error: string | null
}

/**
 * WebSocket hook for fleet real-time updates.
 * Auto-reconnects with exponential backoff.
 */
export function useFleetWebSocket(
  onEvent?: (event: FleetWSEvent) => void
): UseFleetWebSocketResult {
  const [connected, setConnected] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const wsRef = useRef<WebSocket | null>(null)
  const backoffRef = useRef(INITIAL_BACKOFF_MS)
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)
  const onEventRef = useRef(onEvent)
  onEventRef.current = onEvent

  const connect = useCallback(() => {
    if (!mountedRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    try {
      const ws = new WebSocket(WS_URL)
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnected(true)
        setError(null)
        backoffRef.current = INITIAL_BACKOFF_MS
      }

      ws.onmessage = (msgEvent) => {
        if (!mountedRef.current) return
        try {
          const parsed = JSON.parse(msgEvent.data) as FleetWSEvent
          onEventRef.current?.(parsed)
        } catch {
          // Ignore malformed messages
        }
      }

      ws.onerror = () => {
        if (!mountedRef.current) return
        setError('WebSocket error')
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        // Exponential backoff reconnect
        const delay = backoffRef.current
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
        reconnectTimerRef.current = setTimeout(connect, delay)
      }
    } catch {
      if (mountedRef.current) {
        setError('Failed to create WebSocket')
        const delay = backoffRef.current
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS)
        reconnectTimerRef.current = setTimeout(connect, delay)
      }
    }
  }, [])

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current)
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return { connected, error }
}
