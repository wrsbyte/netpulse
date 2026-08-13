import { useUi, type Tab } from '../store'

const TABS: { key: Tab; label: string }[] = [
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'path', label: 'Path' },
  { key: 'data', label: 'Raw data' },
]

export function Tabs() {
  const { tab, setTab } = useUi()
  return (
    <nav className="flex gap-1 border-b border-border">
      {TABS.map((t) => (
        <button
          key={t.key}
          onClick={() => setTab(t.key)}
          className={`-mb-px border-b-2 px-3 py-2 text-sm transition ${
            tab === t.key
              ? 'border-accent text-ink'
              : 'border-transparent text-muted hover:text-ink'
          }`}
        >
          {t.label}
        </button>
      ))}
    </nav>
  )
}
