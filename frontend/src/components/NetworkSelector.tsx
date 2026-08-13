import { useNetworks } from '../hooks'
import { useUi } from '../store'

export function NetworkSelector() {
  const { network, setNetwork } = useUi()
  const { data } = useNetworks()
  const networks = data ?? []

  return (
    <label className="flex items-center gap-1.5 text-sm">
      <span className="text-muted">Network</span>
      <select
        value={network}
        onChange={(e) => setNetwork(e.target.value)}
        className="rounded-lg border border-border bg-panel-2 px-2 py-1 text-ink outline-none transition hover:border-accent focus:border-accent"
      >
        <option value="current">Current</option>
        <option value="all">All networks</option>
        {networks.map((n) => (
          <option key={n.id} value={String(n.id)}>
            {n.label ?? n.ssid ?? `Network ${n.id}`}
            {n.is_current ? ' • now' : ''}
          </option>
        ))}
      </select>
    </label>
  )
}
