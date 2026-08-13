import { useEvents, useFlows } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { Badge, Panel } from './ui'

const SEVERITY_TONE: Record<string, 'ok' | 'warn' | 'danger' | 'info'> = {
  error: 'danger',
  warning: 'warn',
  info: 'info',
}

// Distinguish loading (undefined) / error / empty so an empty table never asserts "healthy".
function StateRow({
  isLoading,
  isError,
  empty,
  emptyText,
}: {
  isLoading: boolean
  isError: boolean
  empty: boolean
  emptyText: string
}) {
  if (isError)
    return <p className="py-6 text-center text-sm text-danger">Couldn’t load — retrying…</p>
  if (isLoading && empty) return <p className="py-6 text-center text-sm text-muted">Loading…</p>
  if (empty) return <p className="py-6 text-center text-sm text-muted">{emptyText}</p>
  return null
}

export function EventsTable() {
  const range = useUi((s) => s.range)
  const { data, isLoading, isError } = useEvents(range)
  const events = data ?? []
  return (
    <Panel title="Events" subtitle="Outages, roaming, DNS failures, IP/network changes, alerts">
      {events.length === 0 ? (
        <StateRow isLoading={isLoading} isError={isError} empty emptyText="No events in range." />
      ) : (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                <th scope="col" className="pb-1 pr-2 font-medium">
                  Time
                </th>
                <th scope="col" className="pb-1 pr-2 font-medium">
                  Kind
                </th>
                <th scope="col" className="pb-1 pr-2 font-medium">
                  Detail
                </th>
                <th scope="col" className="pb-1 text-right font-medium">
                  Duration
                </th>
              </tr>
            </thead>
            <tbody>
              {events.map((e, i) => (
                <tr key={i} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 pr-2 whitespace-nowrap text-muted tabular-nums">
                    {fmt.datetime(e.ts)}
                  </td>
                  <td className="py-1.5 pr-2">
                    <Badge tone={SEVERITY_TONE[e.severity] ?? 'info'}>{e.kind}</Badge>
                  </td>
                  <td className="py-1.5 pr-2 text-ink">{e.detail}</td>
                  <td className="py-1.5 text-right whitespace-nowrap text-muted tabular-nums">
                    {e.kind === 'outage' ? fmt.duration(e.duration) : ''}
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

export function FlowsTable() {
  const range = useUi((s) => s.range)
  const { data, isLoading, isError } = useFlows(range)
  const flows = data ?? []
  return (
    <Panel
      title="Top destinations"
      subtitle="Who this machine talks to, classified by app / CDN + ASN"
    >
      {flows.length === 0 ? (
        <StateRow
          isLoading={isLoading}
          isError={isError}
          empty
          emptyText="No connections sampled yet."
        />
      ) : (
        <div className="max-h-72 overflow-y-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                <th scope="col" className="pb-1 font-medium">
                  App / host
                </th>
                <th scope="col" className="pb-1 font-medium">
                  ASN
                </th>
                <th scope="col" className="pb-1 text-right font-medium">
                  Conns
                </th>
              </tr>
            </thead>
            <tbody>
              {flows.map((f) => (
                <tr key={f.remote_ip} className="border-b border-border/50 last:border-0">
                  <td className="py-1.5 pr-2">
                    <span className="text-ink">{f.app ?? f.rdns ?? f.remote_ip}</span>
                    {f.app && f.rdns && <span className="ml-1 text-xs text-muted">{f.rdns}</span>}
                  </td>
                  <td className="py-1.5 pr-2 text-muted tabular-nums">
                    {f.asn ? `AS${f.asn}` : '—'}
                  </td>
                  <td className="py-1.5 text-right text-ink tabular-nums">{f.conns}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  )
}
