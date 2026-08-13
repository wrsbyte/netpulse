export const fmt = {
  ms: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(0)} ms`),
  msFine: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)} ms`),
  pct: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(0)}%`),
  dbm: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(0)} dBm`),
  mbps: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)} Mbps`),
  bitrate: (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(0)} Mbps`),
  mos: (v: number | null | undefined) => (v == null ? '—' : v.toFixed(2)),
  bps: (v: number | null | undefined) => {
    if (v == null) return '—'
    const bits = v
    if (bits >= 1e9) return `${(bits / 1e9).toFixed(1)} Gbps`
    if (bits >= 1e6) return `${(bits / 1e6).toFixed(1)} Mbps`
    if (bits >= 1e3) return `${(bits / 1e3).toFixed(0)} kbps`
    return `${bits.toFixed(0)} bps`
  },
  time: (ts: number) =>
    new Date(ts * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  datetime: (ts: number) =>
    new Date(ts * 1000).toLocaleString([], {
      month: 'short',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    }),
  duration: (s: number | null | undefined) => {
    if (s == null) return 'ongoing'
    if (s < 60) return `${s.toFixed(0)}s`
    if (s < 3600) return `${(s / 60).toFixed(1)}m`
    return `${(s / 3600).toFixed(1)}h`
  },
}

// A stable color per series tag (targets, resolvers).
const PALETTE = [
  '#38bdf8',
  '#34d399',
  '#fbbf24',
  '#f87171',
  '#a78bfa',
  '#f472b6',
  '#22d3ee',
  '#facc15',
]

export function colorFor(tag: string): string {
  let hash = 0
  for (let i = 0; i < tag.length; i++) hash = (hash * 31 + tag.charCodeAt(i)) & 0xffff
  return PALETTE[hash % PALETTE.length]
}

// Distinct colour by position — use within a single chart so lines never collide.
export function colorAt(index: number): string {
  return PALETTE[index % PALETTE.length]
}
