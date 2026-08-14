import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from './lib/api'
import type { Range, RawQuery } from './lib/types'
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

export const useHops = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['hops', range, network],
    queryFn: () => api.hops(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useAnycast = () => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['anycast', network],
    queryFn: () => api.anycast(network),
    refetchInterval: REFRESH_MS,
  })
}

export const useFlowQuality = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['flowQuality', range, network],
    queryFn: () => api.flowQuality(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useFlowServices = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['flowServices', range, network],
    queryFn: () => api.flowServices(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useGeo = () => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['geo', network],
    queryFn: () => api.geo(network),
    refetchInterval: REFRESH_MS,
  })
}

export const useSla = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['sla', range, network],
    queryFn: () => api.sla(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useExperience = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['experience', range, network],
    queryFn: () => api.experience(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useDnsCompare = (range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['dnsCompare', range, network],
    queryFn: () => api.dnsCompare(range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useDiurnal = (metric: string, range: Range) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['diurnal', metric, range, network],
    queryFn: () => api.diurnal(metric, range, network),
    refetchInterval: REFRESH_MS,
  })
}

export const useRawTables = () => useQuery({ queryKey: ['rawTables'], queryFn: api.rawTables })

export const useRaw = (name: string, range: Range, query: RawQuery) => {
  const network = useNetwork()
  return useQuery({
    queryKey: ['raw', name, range, network, query],
    queryFn: () => api.raw(name, range, network, query),
    refetchInterval: REFRESH_MS,
    placeholderData: (prev) => prev, // keep the table visible while re-querying on filter/sort
  })
}

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
