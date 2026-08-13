import { DataTab } from './components/DataTab'
import { Header } from './components/Header'
import { PathView } from './components/PathView'
import { StatusBar } from './components/StatusBar'
import { Tabs } from './components/Tabs'
import { VerdictPanel } from './components/VerdictPanel'
import {
  ActiveChart,
  DnsChart,
  LatencyChart,
  LossChart,
  ThroughputChart,
  WifiChart,
} from './components/charts'
import { EventsTable, FlowsTable } from './components/tables'
import { useUi } from './store'

function Dashboard() {
  return (
    <>
      <StatusBar />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="lg:col-span-2">
          <LatencyChart />
        </div>
        <LossChart />
        <WifiChart />
        <ThroughputChart />
        <DnsChart />
        <ActiveChart />
        <EventsTable />
        <FlowsTable />
      </div>
    </>
  )
}

export default function App() {
  const tab = useUi((s) => s.tab)
  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
      <Header />
      <VerdictPanel />
      <Tabs />
      {tab === 'dashboard' && <Dashboard />}
      {tab === 'path' && <PathView />}
      {tab === 'data' && <DataTab />}
      <footer className="pt-2 text-center text-xs text-muted">
        Sampling on the host · refreshes every 15 s · localhost only
      </footer>
    </div>
  )
}
