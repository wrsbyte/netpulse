import type {
  ActivePoint,
  AnycastInfo,
  DiurnalResponse,
  DnsCompareRow,
  EventOut,
  ExperienceResponse,
  FlowOut,
  FlowQuality,
  GeoResponse,
  HopTimeline,
  NetworkInfo,
  Range,
  RawPage,
  RawQuery,
  SeriesResponse,
  ServiceQuality,
  SlaReport,
  Status,
  Verdict,
} from './types'

// Serialize a RawQuery to query-string params; `paged` adds limit/offset (omitted for export).
function rawParams(query: RawQuery, paged = true): string {
  const p = new URLSearchParams()
  if (query.q) p.set('q', query.q)
  if (query.sort) p.set('sort', query.sort)
  if (query.dir) p.set('dir', query.dir)
  for (const [col, val] of Object.entries(query.filters ?? {})) p.append('f', `${col}:${val}`)
  if (paged) {
    p.set('limit', String(query.limit))
    p.set('offset', String(query.offset))
  }
  return p.toString()
}

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
  hops: (range: Range, network: string) =>
    get<HopTimeline>(`/traceroute/hops?${q(range, network)}`),
  anycast: (network: string) => get<AnycastInfo[]>(`/anycast?network=${network}`),
  geo: (network: string) => get<GeoResponse>(`/geo?network=${network}`),
  flowQuality: (range: Range, network: string) =>
    get<FlowQuality[]>(`/flow-quality?${q(range, network)}`),
  flowServices: (range: Range, network: string) =>
    get<ServiceQuality[]>(`/flow-services?${q(range, network)}`),
  diurnal: (metric: string, range: Range, network: string) =>
    get<DiurnalResponse>(`/diurnal?metric=${metric}&${q(range, network)}`),
  dnsCompare: (range: Range, network: string) =>
    get<DnsCompareRow[]>(`/dns-compare?${q(range, network)}`),
  experience: (range: Range, network: string) =>
    get<ExperienceResponse>(`/experience?${q(range, network)}`),
  sla: (range: Range, network: string) => get<SlaReport>(`/sla?${q(range, network)}`),
  rawTables: () => get<string[]>('/raw/tables'),
  raw: (name: string, range: Range, network: string, query: RawQuery) =>
    get<RawPage>(`/raw/${name}?${q(range, network)}&${rawParams(query)}`),
  rawCsvUrl: (name: string, range: Range, network: string, query: RawQuery) =>
    `/api/raw/${name}/export.csv?${q(range, network)}&${rawParams(query, false)}`,
  runSpeedtest: async (): Promise<ActivePoint> => {
    const res = await fetch('/api/actions/speedtest', { method: 'POST' })
    if (!res.ok) throw new Error(`speedtest failed (${res.status})`)
    return res.json() as Promise<ActivePoint>
  },
}
