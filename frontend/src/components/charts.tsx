import type { EChartsOption } from 'echarts'
import { useActive, useSeries } from '../hooks'
import { useUi } from '../store'
import { baseOption, lineSeries } from '../lib/echarts'
import { colorFor } from '../lib/format'
import { Chart } from './Chart'
import { Panel } from './ui'

export function LatencyChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useSeries('ping.rtt_avg', range)
  const option: EChartsOption = {
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: '{value} ms' } },
    series: lineSeries(data?.series ?? [], true),
  }
  return (
    <Panel
      title="Latency by target"
      subtitle="RTT per hop — shaded band = min–max spread (aggregated ranges)"
    >
      <Chart option={option} loading={isLoading} height={240} />
    </Panel>
  )
}

export function LossChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useSeries('ping.loss_pct', range)
  const option: EChartsOption = {
    yAxis: { ...baseOption.yAxis, max: 100, axisLabel: { formatter: '{value}%' } },
    series: lineSeries(data?.series ?? []),
  }
  return (
    <Panel title="Packet loss" subtitle="% lost per target — 100% on all internet targets = outage">
      <Chart option={option} loading={isLoading} height={200} />
    </Panel>
  )
}

export function WifiChart() {
  const range = useUi((s) => s.range)
  const signal = useSeries('wifi.signal_dbm', range)
  const bitrate = useSeries('wifi.tx_bitrate', range)
  const sig = signal.data?.series[0]?.points ?? []
  const rate = bitrate.data?.series[0]?.points ?? []
  const option: EChartsOption = {
    legend: { ...baseOption.legend, data: ['signal (dBm)', 'TX bitrate (Mbps)'] },
    yAxis: [
      {
        type: 'value',
        name: 'dBm',
        axisLabel: { formatter: '{value}' },
        splitLine: { lineStyle: { color: '#1a2432' } },
      },
      { type: 'value', name: 'Mbps', position: 'right', splitLine: { show: false } },
    ],
    series: [
      {
        name: 'signal (dBm)',
        type: 'line',
        showSymbol: false,
        smooth: true,
        data: sig.map((p) => [p.ts * 1000, p.avg]),
        lineStyle: { color: '#38bdf8', width: 1.5 },
        itemStyle: { color: '#38bdf8' },
      },
      {
        name: 'TX bitrate (Mbps)',
        type: 'line',
        yAxisIndex: 1,
        showSymbol: false,
        smooth: true,
        data: rate.map((p) => [p.ts * 1000, p.avg]),
        lineStyle: { color: '#34d399', width: 1.5 },
        itemStyle: { color: '#34d399' },
      },
    ],
  }
  return (
    <Panel
      title="WiFi radio"
      subtitle="Signal vs link rate — signal dropping while retries climb = radio, not ISP"
    >
      <Chart option={option} loading={signal.isLoading} height={200} />
    </Panel>
  )
}

export function ThroughputChart() {
  const range = useUi((s) => s.range)
  const rx = useSeries('throughput.rx_bps', range)
  const tx = useSeries('throughput.tx_bps', range)
  const toMbps = (pts: { ts: number; avg: number | null }[]) =>
    pts.map((p) => [p.ts * 1000, p.avg == null ? null : p.avg / 1e6])
  const option: EChartsOption = {
    legend: { ...baseOption.legend, data: ['download', 'upload'] },
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: '{value} Mb/s' } },
    series: [
      {
        name: 'download',
        type: 'line',
        areaStyle: { color: '#38bdf8', opacity: 0.12 },
        showSymbol: false,
        data: toMbps(rx.data?.series[0]?.points ?? []),
        lineStyle: { color: '#38bdf8', width: 1.2 },
        itemStyle: { color: '#38bdf8' },
      },
      {
        name: 'upload',
        type: 'line',
        areaStyle: { color: '#a78bfa', opacity: 0.12 },
        showSymbol: false,
        data: toMbps(tx.data?.series[0]?.points ?? []),
        lineStyle: { color: '#a78bfa', width: 1.2 },
        itemStyle: { color: '#a78bfa' },
      },
    ],
  }
  return (
    <Panel title="Interface throughput" subtitle="Live RX/TX on the uplink (Mb/s)">
      <Chart option={option} loading={rx.isLoading} height={200} />
    </Panel>
  )
}

export function DnsChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useSeries('dns.query_ms', range)
  const option: EChartsOption = {
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: '{value} ms' } },
    series: lineSeries(data?.series ?? []),
  }
  return (
    <Panel
      title="DNS resolution time"
      subtitle="Per resolver — a slow/failing resolver feels like 'no internet'"
    >
      <Chart option={option} loading={isLoading} height={200} />
    </Panel>
  )
}

export function ActiveChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useActive(range)
  const rows = data ?? []
  const option: EChartsOption = {
    legend: { ...baseOption.legend, data: ['download', 'upload', 'bufferbloat (ms)'] },
    yAxis: [
      { type: 'value', name: 'Mbps', splitLine: { lineStyle: { color: '#1a2432' } } },
      { type: 'value', name: 'ms', position: 'right', splitLine: { show: false } },
    ],
    series: [
      {
        name: 'download',
        type: 'bar',
        data: rows.map((r) => [r.ts * 1000, r.download_mbps]),
        itemStyle: { color: colorFor('download') },
      },
      {
        name: 'upload',
        type: 'bar',
        data: rows.map((r) => [r.ts * 1000, r.upload_mbps]),
        itemStyle: { color: colorFor('upload') },
      },
      {
        name: 'bufferbloat (ms)',
        type: 'line',
        yAxisIndex: 1,
        symbolSize: 6,
        data: rows.map((r) => [r.ts * 1000, r.bufferbloat_ms]),
        lineStyle: { color: '#fbbf24', width: 1.5 },
        itemStyle: { color: '#fbbf24' },
      },
    ],
  }
  return (
    <Panel
      title="Active bandwidth & bufferbloat"
      subtitle="Speedtest history — added latency under load is the meeting/gaming killer"
    >
      <Chart option={option} loading={isLoading} height={200} />
    </Panel>
  )
}
