import { useApi } from './useApi'
import type { VDA5050GatewayStatus, VDA5050AgvState } from '../types'

export function useVDA5050Status(pollMs = 3000) {
  return useApi<VDA5050GatewayStatus>('/api/vda5050/status', pollMs)
}

export function useVDA5050Agvs(pollMs = 3000) {
  return useApi<VDA5050AgvState[]>('/api/vda5050/agvs', pollMs)
}
