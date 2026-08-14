import { useStatus } from '../hooks'
import { useUi } from '../store'
import { fmt } from '../lib/format'
import { Kpi } from './ui'

function signalTone(dbm: number | null): 'ok' | 'warn' | 'danger' | 'default' {
  if (dbm == null) return 'default'
  if (dbm >= -60) return 'ok'
  if (dbm >= -72) return 'warn'
  return 'danger'
}

function lossTone(loss: number | null): 'ok' | 'warn' | 'danger' | 'default' {
  if (loss == null) return 'default'
  if (loss >= 100) return 'danger'
  if (loss > 2) return 'warn'
  return 'ok'
}

export function StatusBar() {
  const range = useUi((s) => s.range)
  const { data } = useStatus(range)

  const speedHint = data
    ? `↑ ${fmt.mbps(data.latest_upload_mbps)}` +
      (data.current_rx_mbps != null ? ` · now ↓ ${fmt.mbps(data.current_rx_mbps)}` : '')
    : undefined

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7">
      <Kpi
        label="Status"
        value={
          data ? (!data.collector_healthy ? 'Stale' : data.online ? 'Online' : 'Offline') : '—'
        }
        tone={data ? (!data.collector_healthy ? 'warn' : data.online ? 'ok' : 'danger') : 'default'}
        hint={
          data && !data.collector_healthy ? 'collector offline' : (data?.wifi_ssid ?? undefined)
        }
        title="Whether any internet target is reachable right now. 'Stale' = the sampling collector stopped reporting, so these numbers may be outdated."
      />
      <Kpi
        label="Speed (down)"
        value={fmt.mbps(data?.latest_download_mbps)}
        hint={speedHint}
        title="Last speedtest download capacity (Mbps); hint shows upload capacity and the live throughput actually in use right now"
      />
      <Kpi
        label="Latency"
        value={fmt.ms(data?.current_rtt)}
        hint={`iface ${data?.interface ?? '—'}`}
        title="Current best round-trip time to the internet (ms) · good < 30 · sluggish > 150 · lower is better"
      />
      <Kpi
        label="Loss"
        value={fmt.pct(data?.current_loss)}
        tone={lossTone(data?.current_loss ?? null)}
        title="Ping packets lost right now (%) · 0 is perfect · > 2 hurts · 100 = down"
      />
      <Kpi
        label="WiFi signal"
        value={fmt.dbm(data?.wifi_signal_dbm)}
        tone={signalTone(data?.wifi_signal_dbm ?? null)}
        hint={data?.wifi_bitrate ? `${fmt.bitrate(data.wifi_bitrate)} link` : undefined}
        title="Radio signal strength (dBm; closer to 0 is stronger) · strong > -60 · weak < -72"
      />
      <Kpi
        label="Quality (MOS)"
        value={fmt.mos(data?.latest_mos)}
        hint={data?.latest_grade ? `bufferbloat ${data.latest_grade}` : undefined}
        title="Mean Opinion Score, call quality 1 (bad) to 5 (excellent); ≥ 4 is good"
      />
      <Kpi
        label="Outages"
        value={data ? String(data.outages_in_range) : '—'}
        tone={data && data.outages_in_range > 0 ? 'warn' : 'default'}
        hint={data ? 'in range' : undefined}
        title="Count of full outages in the selected range (all internet targets down at once)"
      />
    </div>
  )
}
