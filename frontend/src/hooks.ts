import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './lib/api'
import type { Range } from './lib/types'
import { useUi } from './store'

const REFRESH_MS = 15_000

// Data hooks read the selected network from the store so every series is scoped consistently;
// callers pass only the metric/range they care about.
const useNetwork = () => useUi((s) => s.network)

export const useStatus = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['status', range, network],
    queryFn: () => api.status(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useVerdict = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['verdict', range, network],
    queryFn: () => api.verdict(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useSeries = (metric: string, range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['series', metric, range, network],
    queryFn: () => api.series(metric, range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useActive = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['active', range, network],
    queryFn: () => api.active(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useEvents = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['events', range, network],
    queryFn: () => api.events(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useFlows = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['flows', range, network],
    queryFn: () => api.flows(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useNetworks = () =>
  useQuery({ queryKey: ['networks'], queryFn: api.networks, refetchInterval: REFRESH_MS })

export function useSpeedtest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.runSpeedtest,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['active'] })
      qc.invalidateQueries({ queryKey: ['status'] })
      qc.invalidateQueries({ queryKey: ['verdict'] })
    },
  })
}
