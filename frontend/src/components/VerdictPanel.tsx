import { useVerdict } from '../hooks'
import { useUi } from '../store'
import type { Finding } from '../lib/types'

function gradeTone(grade: string): string {
  if (grade.startsWith('A')) return 'text-ok border-ok/40 bg-ok/10'
  if (grade === 'B') return 'text-accent border-accent/40 bg-accent/10'
  if (grade === 'C') return 'text-warn border-warn/40 bg-warn/10'
  return 'text-danger border-danger/40 bg-danger/10'
}

// Severity conveyed by label + colour + icon (never colour alone — WCAG).
const SEVERITY: Record<Finding['severity'], { text: string; icon: string; label: string }> = {
  error: { text: 'text-danger', icon: '✕', label: 'Critical' },
  warning: { text: 'text-warn', icon: '!', label: 'Warning' },
  info: { text: 'text-accent', icon: 'i', label: 'Info' },
  ok: { text: 'text-ok', icon: '✓', label: 'OK' },
}

// What each sub-score measures + the direction that's better. Score itself is always 0–100.
const BREAKDOWN_LABEL: Record<string, string> = {
  loss: 'Packet loss',
  latency: 'Latency',
  jitter: 'Jitter',
  bufferbloat: 'Bufferbloat',
  availability: 'Uptime',
}
const BREAKDOWN_ORDER = ['loss', 'latency', 'jitter', 'bufferbloat', 'availability']

function subTone(v: number): string {
  if (v >= 80) return 'bg-ok'
  if (v >= 60) return 'bg-warn'
  return 'bg-danger'
}

function Finding({ f, prominent = false }: { f: Finding; prominent?: boolean }) {
  const sev = SEVERITY[f.severity]
  if (prominent) {
    return (
      <div className="flex items-start gap-2">
        <span
          className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${sev.text}`}
          aria-label={sev.label}
          title={sev.label}
        >
          {sev.icon}
        </span>
        <div className="min-w-0">
          <div className={`text-sm font-semibold ${sev.text}`}>{f.title}</div>
          <div className="text-sm text-muted">{f.detail}</div>
        </div>
      </div>
    )
  }
  return (
    <div className="flex items-start gap-2 text-xs">
      <span className={`shrink-0 font-bold ${sev.text}`} aria-label={sev.label} title={sev.label}>
        {sev.icon}
      </span>
      <span className="text-ink">{f.title}.</span>
      <span className="text-muted">{f.detail}</span>
    </div>
  )
}

export function VerdictPanel() {
  const range = useUi((s) => s.range)
  const { data, isLoading, isError } = useVerdict(range)
  const breakdown = data?.score.breakdown ?? {}
  const headline = isError
    ? 'Cannot reach the collector — is netpulse running?'
    : isLoading
      ? 'Analyzing…'
      : (data?.headline ?? 'No data yet')

  return (
    <section className="rounded-xl border border-border bg-panel p-4">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="flex items-start gap-4 lg:flex-1">
          <div
            className={`flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-xl border font-bold tabular-nums ${
              data ? gradeTone(data.score.grade) : 'border-border text-muted'
            }`}
            title="Overall health grade A+ (best) to F (worst), from the weighted score below"
          >
            <span className="text-3xl leading-none">{data ? data.score.grade : '—'}</span>
            <span className="mt-0.5 text-[10px] font-normal">
              {data ? `${Math.round(data.score.score)}/100` : ''}
            </span>
          </div>
          <div className="min-w-0 flex-1">
            <h2 className={`text-base font-semibold ${isError ? 'text-danger' : 'text-ink'}`}>
              {headline}
            </h2>
            {(() => {
              const findings = data?.findings ?? []
              const primary = findings.filter(
                (f) => f.severity === 'error' || f.severity === 'warning',
              )
              const secondary = findings.filter((f) => f.severity === 'info' || f.severity === 'ok')
              return (
                <>
                  <div className="mt-2 space-y-2">
                    {primary.map((f, i) => (
                      <Finding key={i} f={f} prominent />
                    ))}
                  </div>
                  {secondary.length > 0 && (
                    <details className="mt-2 group">
                      <summary className="cursor-pointer text-xs text-muted hover:text-ink">
                        {primary.length > 0 ? `${secondary.length} more observations` : 'Details'} ▸
                      </summary>
                      <div className="mt-2 space-y-1">
                        {secondary.map((f, i) => (
                          <Finding key={i} f={f} />
                        ))}
                      </div>
                    </details>
                  )}
                </>
              )
            })()}
          </div>
        </div>

        {Object.keys(breakdown).length > 0 && (
          <div className="lg:w-72 lg:shrink-0">
            <div className="mb-1 text-[11px] uppercase tracking-wide text-muted">
              Score breakdown · higher is better (0–100)
            </div>
            <div className="space-y-1">
              {BREAKDOWN_ORDER.filter((k) => k in breakdown).map((k) => (
                <div key={k} className="flex items-center gap-2 text-xs">
                  <span className="w-20 shrink-0 text-muted">{BREAKDOWN_LABEL[k]}</span>
                  <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-panel-2">
                    <div
                      className={`h-full rounded-full ${subTone(breakdown[k])}`}
                      style={{ width: `${breakdown[k]}%` }}
                    />
                  </div>
                  <span className="w-7 shrink-0 text-right tabular-nums text-ink">
                    {Math.round(breakdown[k])}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </section>
  )
}
