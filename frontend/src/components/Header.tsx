import { useSpeedtest, useStatus } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { NetworkSelector } from './NetworkSelector'
import { RangeSelector } from './RangeSelector'

export function Header() {
  const speedtest = useSpeedtest()
  const result = speedtest.data
  const range = useUi((s) => s.range)
  const network = useUi((s) => s.network)
  const { data: status, isError } = useStatus(range)
  const healthy = !isError && status?.collector_healthy
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span
          className={`inline-block h-2.5 w-2.5 rounded-full ${healthy ? 'bg-ok' : 'bg-danger'}`}
          title={
            healthy ? 'Collector is running' : 'Collector is not reporting — data may be stale'
          }
        />
        <h1 className="text-lg font-semibold text-ink">netpulse</h1>
        <span className="text-xs text-muted">
          {healthy ? 'local network health' : 'collector offline — data may be stale'}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <NetworkSelector />
        <div className="flex flex-col items-end">
          <button
            onClick={() => speedtest.mutate()}
            disabled={speedtest.isPending}
            title="Runs a full download/upload test — consumes ~100–300 MB of data"
            className="rounded-lg border border-border bg-panel-2 px-3 py-1 text-sm text-ink transition hover:border-accent disabled:opacity-50"
          >
            {speedtest.isPending ? 'Testing…' : 'Run speedtest ⚠ data'}
          </button>
          {speedtest.isError && <span className="text-[11px] text-danger">Speedtest failed</span>}
          {result && !speedtest.isPending && (
            <span className="text-[11px] text-muted">
              ↓ {fmt.mbps(result.download_mbps)} · ↑ {fmt.mbps(result.upload_mbps)}
              {result.grade ? ` · bloat ${result.grade}` : ''}
            </span>
          )}
        </div>
        <a
          href={`/api/report?range=${range}&network=${network}`}
          target="_blank"
          rel="noopener"
          title="Open a printable evidence report (verdict, SLA, outages, route) — save as PDF"
          className="rounded-lg border border-border bg-panel-2 px-3 py-1 text-sm text-ink transition hover:border-accent"
        >
          Export report
        </a>
        <RangeSelector />
      </div>
    </header>
  )
}
