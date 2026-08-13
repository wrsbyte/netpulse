import type {
  ActivePoint,
  EventOut,
  FlowOut,
  NetworkInfo,
  Range,
  SeriesResponse,
  Status,
  Verdict,
} from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

// Every data call is scoped to a network ("current" | "all" | numeric id).
const q = (range: Range, network: string) => `range=${range}&network=${network}`

export const api = {
  networks: () => get<NetworkInfo[]>('/networks'),
  status: (range: Range, network: string) => get<Status>(`/status?${q(range, network)}`),
  verdict: (range: Range, network: string) => get<Verdict>(`/verdict?${q(range, network)}`),
  series: (metric: string, range: Range, network: string) =>
    get<SeriesResponse>(`/series?metric=${metric}&${q(range, network)}`),
  active: (range: Range, network: string) => get<ActivePoint[]>(`/active?${q(range, network)}`),
  events: (range: Range, network: string) => get<EventOut[]>(`/events?${q(range, network)}`),
  flows: (range: Range, network: string) => get<FlowOut[]>(`/flows?${q(range, network)}`),
  runSpeedtest: async (): Promise<ActivePoint> => {
    const res = await fetch('/api/actions/speedtest', { method: 'POST' })
    if (!res.ok) throw new Error(`speedtest failed (${res.status})`)
    return res.json() as Promise<ActivePoint>
  },
}
