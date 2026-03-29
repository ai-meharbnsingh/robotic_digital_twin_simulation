import { useState, useEffect, useRef, useCallback } from 'react'

const API_BASE = window.location.origin

interface UseApiResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  refetch: () => void
}

/**
 * Generic REST fetcher with polling interval.
 * @param path - API path (e.g., "/api/robots")
 * @param intervalMs - Polling interval in ms. 0 = no polling (fetch once).
 */
export function useApi<T>(path: string, intervalMs: number = 0): UseApiResult<T> {
  const [data, setData] = useState<T | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const mountedRef = useRef(true)

  const fetchData = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}${path}`)
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const json = await res.json() as T
      if (mountedRef.current) {
        setData(json)
        setError(null)
        setLoading(false)
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err instanceof Error ? err.message : String(err))
        setLoading(false)
      }
    }
  }, [path])

  useEffect(() => {
    mountedRef.current = true
    setLoading(true)
    fetchData()

    if (intervalMs > 0) {
      intervalRef.current = setInterval(fetchData, intervalMs)
    }

    return () => {
      mountedRef.current = false
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }
  }, [fetchData, intervalMs])

  return { data, loading, error, refetch: fetchData }
}
