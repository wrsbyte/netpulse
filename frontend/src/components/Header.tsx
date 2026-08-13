import { useSpeedtest } from '../hooks'
import { NetworkSelector } from './NetworkSelector'
import { RangeSelector } from './RangeSelector'

export function Header() {
  const speedtest = useSpeedtest()
  return (
    <header className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex items-center gap-2">
        <span className="inline-block h-2.5 w-2.5 rounded-full bg-accent" />
        <h1 className="text-lg font-semibold text-ink">netpulse</h1>
        <span className="text-xs text-muted">local network health</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <NetworkSelector />
        <button
          onClick={() => speedtest.mutate()}
          disabled={speedtest.isPending}
          className="rounded-lg border border-border bg-panel-2 px-3 py-1 text-sm text-ink transition hover:border-accent disabled:opacity-50"
        >
          {speedtest.isPending ? 'Testing…' : 'Run speedtest'}
        </button>
        <RangeSelector />
      </div>
    </header>
  )
}
