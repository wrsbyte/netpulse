import { useVerdict } from '../hooks'
import { useUi } from '../store'
import type { Finding } from '../lib/types'

function gradeTone(grade: string): string {
  if (grade.startsWith('A')) return 'text-ok border-ok/40 bg-ok/10'
  if (grade === 'B') return 'text-accent border-accent/40 bg-accent/10'
  if (grade === 'C') return 'text-warn border-warn/40 bg-warn/10'
  return 'text-danger border-danger/40 bg-danger/10'
}

const SEV_DOT: Record<Finding['severity'], string> = {
  error: 'bg-danger',
  warning: 'bg-warn',
  info: 'bg-accent',
  ok: 'bg-ok',
}

export function VerdictPanel() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useVerdict(range)

  return (
    <section className="rounded-xl border border-border bg-panel p-4">
      <div className="flex items-start gap-4">
        <div
          className={`flex h-16 w-16 shrink-0 items-center justify-center rounded-xl border text-3xl font-bold tabular-nums ${
            data ? gradeTone(data.score.grade) : 'border-border text-muted'
          }`}
          title={data ? `Health score ${data.score.score}/100` : undefined}
        >
          {data ? data.score.grade : '—'}
        </div>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold text-ink">
            {isLoading ? 'Analyzing…' : (data?.headline ?? 'No data yet')}
          </h2>
          <ul className="mt-2 space-y-1">
            {data?.findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm">
                <span
                  className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${SEV_DOT[f.severity]}`}
                />
                <span className="text-ink">{f.title}.</span>
                <span className="text-muted">{f.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
