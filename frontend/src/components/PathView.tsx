import { useHops } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import type { HopSeries } from '../lib/types'
import { Panel } from './ui'

// Loss % -> heat colour (green ok -> amber -> red).
function heat(loss: number | null): string {
  if (loss == null) return 'transparent'
  if (loss <= 0) return '#1a3a2a'
  if (loss < 5) return '#2f6b3f'
  if (loss < 20) return '#b58a1b'
  if (loss < 50) return '#c25a2a'
  return '#c23a3a'
}

function firstLossHop(hops: HopSeries[]): number | null {
  const end = hops[hops.length - 1]
  if (!end || end.avg_loss < 5) return null // clean destination -> mid-hop loss is ICMP artifact
  return hops.find((h) => h.avg_loss >= 5)?.hop ?? null
}

export function PathView() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useHops(range)
  const hops = data?.hops ?? []
  const culprit = firstLossHop(hops)

  return (
    <Panel
      title={`Path to ${data?.target ?? '…'}`}
      subtitle="Per-hop loss over time (mtr). Loss that starts at a hop AND reaches the destination is real; a single mid-hop spike is ICMP rate-limiting."
    >
      {isLoading && hops.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">Collecting path samples…</p>
      ) : hops.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted">
          No traceroute data yet (mtr runs every few minutes).
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                <th className="pb-1 pr-2 font-medium">Hop</th>
                <th className="pb-1 pr-2 font-medium">Host</th>
                <th className="pb-1 pr-3 text-right font-medium">Avg loss</th>
                <th className="pb-1 font-medium">Loss over time →</th>
              </tr>
            </thead>
            <tbody>
              {hops.map((h) => (
                <tr key={h.hop} className="border-b border-border/40 last:border-0">
                  <td className="py-1 pr-2 tabular-nums text-muted">{h.hop}</td>
                  <td className="py-1 pr-2 text-ink">
                    {h.host ?? '*'}
                    {culprit === h.hop && (
                      <span className="ml-2 rounded bg-danger/15 px-1.5 py-0.5 text-[11px] text-danger">
                        loss starts here
                      </span>
                    )}
                  </td>
                  <td
                    className={`py-1 pr-3 text-right tabular-nums ${
                      h.avg_loss >= 5 && (culprit == null || h.hop >= culprit)
                        ? 'text-danger'
                        : 'text-muted'
                    }`}
                  >
                    {fmt.pct(h.avg_loss)}
                  </td>
                  <td className="py-1">
                    <div className="flex gap-[2px]">
                      {h.points.map((p, i) => (
                        <span
                          key={i}
                          title={`${fmt.time(p.ts)} · ${fmt.pct(p.loss_pct)}`}
                          className="h-4 w-1.5 rounded-[1px]"
                          style={{ background: heat(p.loss_pct) }}
                        />
                      ))}
                    </div>
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
