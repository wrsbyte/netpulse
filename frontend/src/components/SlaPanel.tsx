import { useSla } from '../hooks'
import { useUi } from '../store'
import { Badge, Panel } from './ui'

function unit(metric: string): string {
  if (metric === 'Uptime') return '%'
  if (metric === 'Latency') return ' ms'
  return ' Mbps'
}

function fmt(v: number | null, metric: string): string {
  if (v == null) return '—'
  return `${metric === 'Uptime' ? v.toFixed(2) : Math.round(v)}${unit(metric)}`
}

export function SlaPanel() {
  const range = useUi((s) => s.range)
  const { data, isError } = useSla(range)
  if (isError || !data || !data.configured) return null // no contract set → don't show the card
  return (
    <Panel
      title="Contract vs delivered (SLA)"
      subtitle={`What your ISP promised vs what you actually received ${data.window_label}. Capacity passes at ≥90% of the headline rate; uptime/latency are hard thresholds.`}
    >
      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {data.lines.map((l) => {
          const tone = l.meets == null ? 'info' : l.meets ? 'ok' : 'danger'
          return (
            <div key={l.metric} className="rounded-xl border border-border bg-panel-2 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-ink">{l.metric}</span>
                <Badge tone={tone}>
                  {l.meets == null ? 'pending' : l.meets ? 'met' : 'breach'}
                </Badge>
              </div>
              <div className="mt-1 text-lg font-bold tabular-nums text-ink">
                {fmt(l.measured, l.metric)}
              </div>
              <div className="text-xs text-muted">
                {l.metric === 'Latency' ? 'ceiling' : 'contracted'} {fmt(l.contracted, l.metric)}
                {l.delivered_pct != null && l.metric !== 'Uptime' && l.metric !== 'Latency' && (
                  <> · {l.delivered_pct.toFixed(0)}% delivered</>
                )}
              </div>
            </div>
          )
        })}
      </div>
      {data.breaches > 0 && (
        <p className="mt-2 text-xs text-danger">
          {data.breaches} contract {data.breaches === 1 ? 'metric is' : 'metrics are'} below what
          you pay for — this is the evidence to take to your ISP.
        </p>
      )}
    </Panel>
  )
}
