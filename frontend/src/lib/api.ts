import type { ActivePoint, EventOut, FlowOut, Range, SeriesResponse, Status } from './types'

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`/api${path}`)
  if (!res.ok) throw new Error(`${res.status} ${path}`)
  return res.json() as Promise<T>
}

export const api = {
  status: (range: Range) => get<Status>(`/status?range=${range}`),
  series: (metric: string, range: Range) =>
    get<SeriesResponse>(`/series?metric=${metric}&range=${range}`),
  active: (range: Range) => get<ActivePoint[]>(`/active?range=${range}`),
  events: (range: Range) => get<EventOut[]>(`/events?range=${range}`),
  flows: (range: Range) => get<FlowOut[]>(`/flows?range=${range}`),
  runSpeedtest: async (): Promise<ActivePoint> => {
    const res = await fetch('/api/actions/speedtest', { method: 'POST' })
    if (!res.ok) throw new Error(`speedtest failed (${res.status})`)
    return res.json() as Promise<ActivePoint>
  },
}
