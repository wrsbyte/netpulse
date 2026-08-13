import { Header } from './components/Header'
import { StatusBar } from './components/StatusBar'
import {
  ActiveChart,
  DnsChart,
  LatencyChart,
  LossChart,
  ThroughputChart,
  WifiChart,
} from './components/charts'
import { EventsTable, FlowsTable } from './components/tables'

export default function App() {
  return (
    <div className="mx-auto max-w-7xl space-y-4 p-4 lg:p-6">
      <Header />
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
      <footer className="pt-2 text-center text-xs text-muted">
        Sampling on the host · refreshes every 15 s · localhost only
      </footer>
    </div>
  )
}
