import type { EChartsOption } from 'echarts'
import { useActive, useSeries } from '../hooks'
import { useUi } from '../store'
import { baseOption, lineSeries, thresholdSeries } from '../lib/echarts'
import { colorFor } from '../lib/format'
import { Chart } from './Chart'
import { Panel } from './ui'

export function LatencyChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useSeries('ping.rtt_avg', range)
  const option: EChartsOption = {
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: '{value} ms' } },
    series: [
      ...lineSeries(data?.series ?? [], true),
      ...thresholdSeries([{ y: 150, label: 'sluggish > 150 ms', color: '#f87171' }]),
    ],
  }
  return (
    <Panel
      title="Latency by target"
      subtitle="Round-trip time per target, in ms · lower is better · good < 30 · sluggish > 150. Band = min–max."
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
    series: [
      ...lineSeries(data?.series ?? []),
      ...thresholdSeries([{ y: 20, label: 'bad > 20%', color: '#f87171' }]),
    ],
  }
  return (
    <Panel
      title="Packet loss"
      subtitle="% of ping packets lost per target · 0 is perfect · > 2 hurts · 100 on all internet targets = outage"
    >
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
      ...thresholdSeries([{ y: -72, label: 'weak < -72 dBm', color: '#fbbf24' }]),
    ],
  }
  return (
    <Panel
      title="WiFi radio"
      subtitle="Signal in dBm (closer to 0 = stronger; strong > -60, weak < -72) vs TX link rate in Mbps"
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
    <Panel
      title="Interface throughput"
      subtitle="Live data rate on the WiFi uplink, in megabits/second (Mb/s) · download vs upload"
    >
      <Chart option={option} loading={rx.isLoading} height={200} />
    </Panel>
  )
}

export function DnsChart() {
  const range = useUi((s) => s.range)
  const { data, isLoading } = useSeries('dns.query_ms', range)
  const option: EChartsOption = {
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: '{value} ms' } },
    series: [
      ...lineSeries(data?.series ?? []),
      ...thresholdSeries([{ y: 300, label: 'slow > 300 ms', color: '#f87171' }]),
    ],
  }
  return (
    <Panel
      title="DNS resolution time"
      subtitle="Time to resolve a name, in ms, per resolver · good < 50 · slow > 300 · a failing resolver feels like 'no internet'"
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
      subtitle="Speedtest — download/upload in Mbps (bars); latency added under load in ms (line) · < 30 ms = grade A"
    >
      <Chart option={option} loading={isLoading} height={200} />
    </Panel>
  )
}
