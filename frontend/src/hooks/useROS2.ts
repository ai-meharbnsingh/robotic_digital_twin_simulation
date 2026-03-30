import { useApi } from './useApi'
import type { ROS2BridgeStatus } from '../types'

export function useROS2Status(pollMs = 5000) {
  return useApi<ROS2BridgeStatus>('/api/ros2/status', pollMs)
}
