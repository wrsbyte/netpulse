import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './lib/api'
import type { Range } from './lib/types'

const REFRESH_MS = 15_000

export const useStatus = (range: Range) =>
  useQuery({
    queryKey: ['status', range],
    queryFn: () => api.status(range),
    refetchInterval: REFRESH_MS,
  })

export const useSeries = (metric: string, range: Range) =>
  useQuery({
    queryKey: ['series', metric, range],
    queryFn: () => api.series(metric, range),
    refetchInterval: REFRESH_MS,
  })

export const useActive = (range: Range) =>
  useQuery({
    queryKey: ['active', range],
    queryFn: () => api.active(range),
    refetchInterval: REFRESH_MS,
  })

export const useEvents = (range: Range) =>
  useQuery({
    queryKey: ['events', range],
    queryFn: () => api.events(range),
    refetchInterval: REFRESH_MS,
  })

export const useFlows = (range: Range) =>
  useQuery({
    queryKey: ['flows', range],
    queryFn: () => api.flows(range),
    refetchInterval: REFRESH_MS,
  })

export function useSpeedtest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.runSpeedtest,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['active'] })
      qc.invalidateQueries({ queryKey: ['status'] })
    },
  })
}
