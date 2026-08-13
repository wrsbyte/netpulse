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

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      <Kpi
        label="Status"
        value={data ? (data.online ? 'Online' : 'Offline') : '—'}
        tone={data ? (data.online ? 'ok' : 'danger') : 'default'}
        hint={data?.wifi_ssid ?? undefined}
      />
      <Kpi
        label="Latency"
        value={fmt.ms(data?.current_rtt)}
        hint={`iface ${data?.interface ?? '—'}`}
      />
      <Kpi
        label="Loss"
        value={fmt.pct(data?.current_loss)}
        tone={lossTone(data?.current_loss ?? null)}
      />
      <Kpi
        label="WiFi signal"
        value={fmt.dbm(data?.wifi_signal_dbm)}
        tone={signalTone(data?.wifi_signal_dbm ?? null)}
        hint={data?.wifi_bitrate ? `${fmt.bitrate(data.wifi_bitrate)} link` : undefined}
      />
      <Kpi
        label="Quality (MOS)"
        value={fmt.mos(data?.latest_mos)}
        hint={data?.latest_grade ? `bufferbloat ${data.latest_grade}` : undefined}
      />
      <Kpi
        label="Outages"
        value={data ? String(data.outages_in_range) : '—'}
        tone={data && data.outages_in_range > 0 ? 'warn' : 'default'}
        hint={data?.public_ipv4 ?? undefined}
      />
    </div>
  )
}
