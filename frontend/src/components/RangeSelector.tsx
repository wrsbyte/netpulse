import { useUi } from '../store'
import type { Range } from '../lib/types'

const RANGES: { key: Range; label: string }[] = [
  { key: '6h', label: '6 h' },
  { key: '24h', label: '24 h' },
  { key: '7d', label: '7 d' },
]

export function RangeSelector() {
  const { range, setRange } = useUi()
  return (
    <div className="inline-flex rounded-lg border border-border bg-panel-2 p-0.5">
      {RANGES.map((r) => (
        <button
          key={r.key}
          onClick={() => setRange(r.key)}
          className={`rounded-md px-3 py-1 text-sm transition ${
            range === r.key ? 'bg-accent text-bg font-semibold' : 'text-muted hover:text-ink'
          }`}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}
