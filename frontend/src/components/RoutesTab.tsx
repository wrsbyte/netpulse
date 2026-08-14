import { useAnycast, useFlowQuality } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { DiurnalPanel } from './DiurnalPanel'
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
  const { data } = useFlowQuality(range)
  const flows = data ?? []
  return (
    <Panel
      title="Live transport quality (passive)"
      subtitle="Per-endpoint RTT/loss/goodput the kernel measures on your real traffic (ss -ti). Excess = current − base RTT = queuing/congestion right now; lower is better."
    >
      {flows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">No active flows sampled yet.</p>
      ) : (
        <div className="max-h-[28rem] overflow-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="sticky top-0 bg-panel text-left text-[11px] uppercase tracking-wide text-muted">
                <th scope="col" className="pb-1 pr-3 font-medium">
                  App / endpoint
                </th>
                <th scope="col" className="pb-1 pr-3 font-medium">
                  ASN
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Base RTT (ms)
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Now (ms)
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Excess (ms)
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
              {flows.map((f) => (
                <tr key={f.remote_ip} className="border-b border-border/40 last:border-0">
                  <td className="py-1 pr-3 text-ink">{f.app ?? f.remote_ip}</td>
                  <td className="py-1 pr-3 text-muted tabular-nums">
                    {f.asn ? `AS${f.asn}` : '—'}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums text-muted">
                    {fmt.msFine(f.min_rtt_ms)}
                  </td>
                  <td className="py-1 pr-3 text-right tabular-nums text-ink">
                    {fmt.msFine(f.srtt_ms)}
                  </td>
                  <td className="py-1 pr-3 text-right">
                    <Badge tone={excessTone(f.excess_ms)}>{fmt.msFine(f.excess_ms)}</Badge>
                  </td>
                  <td
                    className={`py-1 pr-3 text-right tabular-nums ${
                      f.retrans_total ? 'text-warn' : 'text-muted'
                    }`}
                  >
                    {f.retrans_total ?? 0}
                  </td>
                  <td className="py-1 text-right tabular-nums text-muted">
                    {fmt.mbps(f.delivery_mbps)}
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
      <DiurnalPanel />
      <FlowQualityPanel />
    </div>
  )
}
