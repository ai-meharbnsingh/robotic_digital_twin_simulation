import { useApi } from './useApi'
import type { WMSStatus, WMSOrdersResponse, WMSDlqResponse } from '../types'

export function useWMSStatus(pollMs = 5000) {
  return useApi<WMSStatus>('/api/wms/status', pollMs)
}

export function useWMSOrders(pollMs = 5000) {
  return useApi<WMSOrdersResponse>('/api/wms/orders', pollMs)
}

export function useWMSDlq(pollMs = 10000) {
  return useApi<WMSDlqResponse>('/api/wms/dlq', pollMs)
}
