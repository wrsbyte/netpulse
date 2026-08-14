// Mirrors backend/src/netpulse/api/schemas.py. Keep in sync.

export type Range = '6h' | '24h' | '7d'

export interface Point {
  ts: number
  avg: number | null
  mn?: number | null
  mx?: number | null
  p95?: number | null
}

export interface Series {
  tag: string
  points: Point[]
}

export interface SeriesResponse {
  metric: string
  range: Range
  resolution: string
  series: Series[]
}

export interface ActivePoint {
  ts: number
  download_mbps: number | null
  upload_mbps: number | null
  idle_latency: number | null
  bufferbloat_ms: number | null
  grade: string | null
  mos: number | null
}

export interface EventOut {
  ts: number
  end_ts: number | null
  kind: string
  severity: string
  detail: string
  duration: number | null
}

export interface FlowOut {
  remote_ip: string
  rdns: string | null
  asn: string | null
  app: string | null
  conns: number
}

export interface NetworkInfo {
  id: number
  label: string | null
  ssid: string | null
  gateway_ip: string | null
  gateway_mac: string | null
  interface: string | null
  first_seen: number
  last_seen: number
  is_current: boolean
}

export interface Score {
  score: number
  grade: string
  breakdown: Record<string, number>
}

export interface Finding {
  severity: 'error' | 'warning' | 'info' | 'ok'
  title: string
  detail: string
}

export interface Verdict {
  score: Score
  headline: string
  findings: Finding[]
}

export interface RawColumn {
  name: string
  type: 'number' | 'string' | 'bool' | 'time'
  unit: string | null
  values: string[] | null
}

export interface RawAgg {
  column: string
  count: number
  min: number | null
  max: number | null
  avg: number | null
  p95: number | null
}

export interface RawPage {
  columns: RawColumn[]
  rows: Record<string, unknown>[]
  total: number
  agg: RawAgg[]
}

export interface RawQuery {
  q?: string
  sort?: string
  dir?: 'asc' | 'desc'
  filters?: Record<string, string>
  limit: number
  offset: number
}

export interface HopPoint {
  ts: number
  loss_pct: number | null
  rtt_ms: number | null
}

export interface HopSeries {
  hop: number
  host: string | null
  avg_loss: number
  points: HopPoint[]
}

export interface HopTimeline {
  target: string
  hops: HopSeries[]
}

export interface AnycastInfo {
  provider: string
  target: string
  colo: string | null
  colo_country: string | null
  client_country: string | null
  out_of_country: boolean
  ts: number
}

export interface FlowQuality {
  remote_ip: string
  asn: string | null
  app: string | null
  srtt_ms: number | null
  min_rtt_ms: number | null
  excess_ms: number | null
  retrans_total: number | null
  delivery_mbps: number | null
  sockets: number
}

export interface Status {
  online: boolean
  current_rtt: number | null
  current_loss: number | null
  wifi_signal_dbm: number | null
  wifi_bitrate: number | null
  wifi_ssid: string | null
  public_ipv4: string | null
  public_ipv6: string | null
  outages_in_range: number
  latest_download_mbps: number | null
  latest_upload_mbps: number | null
  latest_grade: string | null
  latest_mos: number | null
  interface: string
}
