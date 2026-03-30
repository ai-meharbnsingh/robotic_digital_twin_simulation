import { useState, useCallback } from 'react'
import { useApi } from './useApi'
import type { Scenario, ScenarioComparison, ScenarioConfig, ScenarioRunResult } from '../types'

const API_BASE = window.location.origin

// API key for write endpoints — read from Vite env or fallback to empty (auth disabled)
const API_KEY = (import.meta.env?.VITE_API_KEY as string | undefined) ?? ''

function authHeaders(): Record<string, string> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  if (API_KEY) headers['X-API-Key'] = API_KEY
  return headers
}

// ---- Polling hooks (reuse useApi pattern) ----

export function useScenarios(pollMs: number = 3000) {
  return useApi<Scenario[]>('/api/scenarios', pollMs)
}

// ---- Mutation hooks ----

interface MutationResult<T> {
  data: T | null
  loading: boolean
  error: string | null
  execute: (...args: never[]) => Promise<T | null>
}

export function useCreateScenario(): MutationResult<Scenario> & {
  execute: (config: Partial<ScenarioConfig>) => Promise<Scenario | null>
} {
  const [data, setData] = useState<Scenario | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const execute = useCallback(async (config: Partial<ScenarioConfig>): Promise<Scenario | null> => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/scenarios`, {
        method: 'POST',
        headers: authHeaders(),
        body: JSON.stringify(config),
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`HTTP ${res.status}: ${body}`)
      }
      const json = (await res.json()) as Scenario
      setData(json)
      return json
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, execute }
}

export function useRunScenario(): MutationResult<ScenarioRunResult> & {
  execute: (scenarioId: string) => Promise<ScenarioRunResult | null>
} {
  const [data, setData] = useState<ScenarioRunResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const execute = useCallback(async (scenarioId: string): Promise<ScenarioRunResult | null> => {
    setLoading(true)
    setError(null)
    try {
      const res = await fetch(`${API_BASE}/api/scenarios/${scenarioId}/run`, {
        method: 'POST',
        headers: authHeaders(),
      })
      if (!res.ok) {
        const body = await res.text()
        throw new Error(`HTTP ${res.status}: ${body}`)
      }
      const json = (await res.json()) as ScenarioRunResult
      setData(json)
      return json
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  return { data, loading, error, execute }
}

export function useScenarioComparison(ids: string[]) {
  const query = ids.length >= 2 ? `/api/scenarios/compare?ids=${ids.join(',')}` : null
  return useApi<ScenarioComparison>(query, 0)
}
