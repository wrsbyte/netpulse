import { useStatus } from '../hooks'
import { useUi } from '../store'

// A dashboard that keeps showing numbers while the collector is dead is worse than no dashboard —
// make "these numbers may be stale" impossible to miss, not just a 2 px dot in the header.
export function StaleBanner() {
  const range = useUi((s) => s.range)
  const { data, isError } = useStatus(range)
  const down = isError || (data && !data.collector_healthy)
  if (!down) return null
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded-lg border border-danger/50 bg-danger/10 px-3 py-2 text-sm text-danger"
    >
      <span aria-hidden>⚠</span>
      <span>
        <b>Data may be stale.</b> The sampling collector isn't reporting — restart it with{' '}
        <code className="rounded bg-panel-2 px-1">systemctl --user restart netpulse-collector</code>
        .
      </span>
    </div>
  )
}
