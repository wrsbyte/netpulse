import { useAnycast, useFlowServices } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { DiurnalPanel } from './DiurnalPanel'
import { DnsComparePanel } from './DnsComparePanel'
import { Badge, Panel } from './ui'

function excessTone(ms: number | null): 'ok' | 'warn' | 'danger' | 'info' {
  if (ms == null) return 'info'
  if (ms < 20) return 'ok'
  if (ms < 80) return 'warn'
  return 'danger'
}

function AnycastPanel() {
  const { data } = useAnycast()
  const pops = data ?? []
  return (
    <Panel
      title="CDN serving POP (anycast)"
      subtitle="Which datacentre a CDN actually serves you from. An out-of-country POP means the ISP routes that CDN abroad — international latency and loss you didn't choose."
    >
      {pops.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted">No anycast POP data yet.</p>
      ) : (
        <div className="flex flex-wrap gap-3">
          {pops.map((p) => (
            <div
              key={`${p.provider}:${p.target}`}
              className="rounded-lg border border-border bg-panel-2 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold text-ink capitalize">{p.provider}</span>
                <span className="text-xs text-muted">{p.target}</span>
              </div>
              <div className="mt-1 flex items-center gap-2">
                <span className="text-lg font-bold tabular-nums text-ink">{p.colo ?? '—'}</span>
                <span className="text-xs text-muted">
                  {p.colo_country} · you: {p.client_country}
                </span>
                {p.out_of_country ? (
                  <Badge tone="danger">out of country</Badge>
                ) : (
                  <Badge tone="ok">in country</Badge>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}

function FlowQualityPanel() {
  const range = useUi((s) => s.range)
  const { data } = useFlowServices(range)
  const services = data ?? []
  return (
    <Panel
      title="Who you talk to & how it performs"
      subtitle="Your real traffic (ss -ti) grouped by service, most-used first. Excess = extra RTT over the path's floor = queuing/congestion; lower is better. Endpoints = how many IPs collapsed into that service."
    >
      {services.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">No active flows sampled yet.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                <th scope="col" className="pb-1 pr-3 font-medium">
                  Service
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Endpoints
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Base RTT
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Worst excess
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Retrans
                </th>
                <th scope="col" className="pb-1 text-right font-medium">
                  Goodput
                </th>
              </tr>
            </thead>
            <tbody>
              {services.map((s) => (
                <tr key={s.service} className="border-b border-border/40 last:border-0">
                  <td className="py-1.5 pr-3 text-ink">
                    {s.service} {s.asn && <span className="text-[11px] text-muted">AS{s.asn}</span>}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-muted">{s.endpoints}</td>
                  <td className="py-1.5 pr-3 text-right tabular-nums text-muted">
                    {fmt.msFine(s.rtt_ms)}
                  </td>
                  <td className="py-1.5 pr-3 text-right">
                    <Badge tone={excessTone(s.worst_excess_ms)}>
                      {fmt.msFine(s.worst_excess_ms)}
                    </Badge>
                  </td>
                  <td
                    className={`py-1.5 pr-3 text-right tabular-nums ${
                      s.retrans_total ? 'text-warn' : 'text-muted'
                    }`}
                  >
                    {s.retrans_total}
                  </td>
                  <td className="py-1.5 text-right tabular-nums text-muted">
                    {fmt.mbps(s.delivery_mbps)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}

export function RoutesTab() {
  return (
    <div className="space-y-4">
      <AnycastPanel />
      <DnsComparePanel />
      <DiurnalPanel />
      <FlowQualityPanel />
    </div>
  )
}
