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
