import { useDnsCompare } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { Badge, Panel } from './ui'

const NAME: Record<string, string> = {
  '9.9.9.9': 'Quad9',
  '8.8.8.8': 'Google',
  '1.1.1.1': 'Cloudflare',
  system: 'Router',
}

export function DnsComparePanel() {
  const range = useUi((s) => s.range)
  const { data } = useDnsCompare(range)
  const rows = (data ?? []).filter((r) => r.resolver !== 'system')
  const best = rows.reduce<string | null>(
    (b, r) =>
      b === null || r.fail_pct < (rows.find((x) => x.resolver === b)?.fail_pct ?? 99)
        ? r.resolver
        : b,
    null,
  )
  return (
    <Panel
      title="DNS resolvers compared"
      subtitle="Which resolver to use, measured over the range. Lower jitter + lower failures matter more than median (all cached lookups are instant)."
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
              <th scope="col" className="pb-1 pr-3 font-medium">
                Resolver
              </th>
              <th scope="col" className="pb-1 pr-3 text-right font-medium">
                Median
              </th>
              <th scope="col" className="pb-1 pr-3 text-right font-medium">
                p95
              </th>
              <th scope="col" className="pb-1 pr-3 text-right font-medium">
                Jitter
              </th>
              <th scope="col" className="pb-1 pr-3 text-right font-medium">
                Fail %
              </th>
              <th scope="col" className="pb-1 text-right font-medium">
                n
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.resolver} className="border-b border-border/40 last:border-0">
                <td className="py-1.5 pr-3 text-ink">
                  {NAME[r.resolver] ?? r.resolver}{' '}
                  <span className="text-xs text-muted">{r.resolver}</span>
                  {r.resolver === best && (
                    <span className="ml-2">
                      <Badge tone="ok">best</Badge>
                    </span>
                  )}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-ink">
                  {fmt.ms(r.median_ms)}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-muted">
                  {fmt.ms(r.p95_ms)}
                </td>
                <td className="py-1.5 pr-3 text-right tabular-nums text-muted">
                  {fmt.ms(r.jitter_ms)}
                </td>
                <td
                  className={`py-1.5 pr-3 text-right tabular-nums ${
                    r.fail_pct >= 5 ? 'text-danger' : r.fail_pct >= 2 ? 'text-warn' : 'text-ok'
                  }`}
                >
                  {r.fail_pct >= 2 && <span aria-hidden>▲ </span>}
                  {r.fail_pct.toFixed(1)}%
                </td>
                <td className="py-1.5 text-right tabular-nums text-muted">
                  {r.n.toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}
