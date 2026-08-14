import { useExperience } from '../hooks'
import { useUi } from '../store'
import type { Activity } from '../lib/types'
import { Panel } from './ui'

const ICON: Record<string, string> = {
  'Video calls': '📞',
  Browsing: '🌐',
  Streaming: '🎬',
  Gaming: '🎮',
}

const RATING = {
  good: { label: 'Good', color: '#34d399', bg: 'rgba(52,211,153,0.12)' },
  fair: { label: 'Fair', color: '#fbbf24', bg: 'rgba(251,191,36,0.12)' },
  poor: { label: 'Poor', color: '#f87171', bg: 'rgba(248,113,113,0.12)' },
  unknown: { label: '—', color: '#8a97ab', bg: 'rgba(138,151,171,0.10)' },
} as const

function num(v: number | null, unit: string): string {
  if (v == null) return '—'
  const rounded = unit === '%' ? v.toFixed(1) : Math.round(v).toString()
  return `${rounded}${unit === '%' ? '' : ' '}${unit}`
}

function Card({ a }: { a: Activity }) {
  const r = RATING[a.rating]
  return (
    <div
      className="rounded-xl border p-3"
      style={{ borderColor: `${r.color}44`, background: r.bg }}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{ICON[a.activity] ?? '•'}</span>
        <span className="text-sm font-semibold text-ink">{a.activity}</span>
        <span
          className="ml-auto rounded-full px-2 py-0.5 text-[11px] font-bold"
          style={{ color: r.color, background: `${r.color}22` }}
        >
          {r.label}
        </span>
      </div>
      <p className="mt-1.5 text-xs text-muted">{a.summary}</p>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-0.5">
        {a.metrics
          .filter((m) => m.value != null)
          .map((m) => (
            <span key={m.label} className="text-xs tabular-nums">
              <span className="text-muted">{m.label} </span>
              <span style={{ color: m.ok ? '#34d399' : '#f87171' }}>
                {m.ok ? '' : '▲ '}
                {num(m.value, m.unit)}
              </span>
            </span>
          ))}
      </div>
    </div>
  )
}

export function ExperiencePanel() {
  const range = useUi((s) => s.range)
  const { data } = useExperience(range)
  const activities = data?.activities ?? []
  return (
    <Panel
      title="What you'll experience"
      subtitle="Plain-language rating per activity, from the metrics measured over the range. Green metric = within the good range for that use; red = the one dragging it down."
    >
      {activities.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted">Gathering data…</p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {activities.map((a) => (
            <Card key={a.activity} a={a} />
          ))}
        </div>
      )}
    </Panel>
  )
}
