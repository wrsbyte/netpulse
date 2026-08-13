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

// Where real loss begins: start of the contiguous lossy run reaching the destination (mirrors
// the backend attribution). A clean destination means any mid-hop loss is an ICMP artifact.
function firstLossHop(hops: HopSeries[]): number | null {
  const end = hops[hops.length - 1]
  if (!end || end.avg_loss < 5) return null
  let start = hops.length - 1
  while (start - 1 >= 0 && hops[start - 1].avg_loss >= 5) start--
  return hops[start].hop
}

function avgRtt(h: HopSeries): number | null {
  const vals = h.points.map((p) => p.rtt_ms).filter((v): v is number => v != null)
  return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null
}

const HEAT_LEGEND = [
  { c: '#1a3a2a', t: '0%' },
  { c: '#2f6b3f', t: '<5%' },
  { c: '#b58a1b', t: '<20%' },
  { c: '#c25a2a', t: '<50%' },
  { c: '#c23a3a', t: '≥50%' },
]

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
          <div className="mb-2 flex items-center gap-2 text-[11px] text-muted">
            <span className="uppercase tracking-wide">Loss legend:</span>
            {HEAT_LEGEND.map((h) => (
              <span key={h.t} className="inline-flex items-center gap-1">
                <span className="h-3 w-3 rounded-[2px]" style={{ background: h.c }} />
                {h.t}
              </span>
            ))}
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                <th scope="col" className="pb-1 pr-2 font-medium">
                  Hop
                </th>
                <th scope="col" className="pb-1 pr-2 font-medium">
                  Host
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Avg RTT (ms)
                </th>
                <th scope="col" className="pb-1 pr-3 text-right font-medium">
                  Avg loss (%)
                </th>
                <th scope="col" className="pb-1 font-medium">
                  Loss over time →
                </th>
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
                  <td className="py-1 pr-3 text-right tabular-nums text-muted">
                    {fmt.msFine(avgRtt(h))}
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
