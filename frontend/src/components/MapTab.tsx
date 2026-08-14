import type { EChartsOption } from 'echarts'
import { useEffect, useRef } from 'react'
import { useGeo } from '../hooks'
import type { GeoArc, GeoHop, GeoPoint } from '../lib/types'
import { echarts } from '../lib/echarts-core'
import { Panel } from './ui'

// Loss drives colour (green/amber/red); it's what actually degrades a path. Unknown = neutral.
function lossColor(loss: number | null): string {
  if (loss == null) return '#8a97ab'
  if (loss < 2) return '#34d399'
  if (loss < 5) return '#fbbf24'
  return '#f87171'
}

// RTT drives size — farther/slower destinations read bigger. Clamped so the map stays legible.
function rttSize(rtt: number | null, base: number): number {
  if (rtt == null) return base
  return Math.min(base + rtt / 6, base + 22)
}

function pointTooltip(p: GeoPoint): string {
  const rows: string[] = [`<b>${p.label}</b>`]
  if (p.target) rows.push(`target ${p.target}`)
  if (p.rtt_ms != null) rows.push(`RTT ${p.rtt_ms.toFixed(0)} ms`)
  if (p.loss_pct != null) rows.push(`loss ${p.loss_pct.toFixed(1)}%`)
  if (p.kind === 'pop') rows.push(p.out_of_country ? 'routed abroad' : 'in-country POP')
  return rows.join('<br/>')
}

function hopTooltip(h: GeoHop): string {
  const where = [h.city, h.country].filter(Boolean).join(', ')
  const rows = [`<b>Hop ${h.hop}${where ? ` — ${where}` : ''}</b>`, h.ip]
  if (h.rtt_ms != null) rows.push(`RTT ${h.rtt_ms.toFixed(0)} ms`)
  if (h.loss_pct != null) rows.push(`loss ${h.loss_pct.toFixed(1)}%`)
  return rows.join('<br/>')
}

export function MapTab() {
  const { data } = useGeo()
  const ref = useRef<HTMLDivElement>(null)
  const chart = useRef<ReturnType<typeof echarts.init> | null>(null)

  useEffect(() => {
    if (!ref.current) return
    chart.current = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    const observer = new ResizeObserver(() => chart.current?.resize())
    observer.observe(ref.current)
    return () => {
      observer.disconnect()
      chart.current?.dispose()
      chart.current = null
    }
  }, [])

  useEffect(() => {
    if (!chart.current || !data) return
    const points = data.points.map((p) => ({
      name: p.label,
      value: [p.lon, p.lat, p.rtt_ms ?? 0],
      symbolSize: rttSize(p.rtt_ms, p.kind === 'you' ? 14 : 8),
      itemStyle: {
        color: p.kind === 'you' ? '#38bdf8' : lossColor(p.loss_pct),
        borderColor: p.out_of_country ? '#f87171' : 'transparent',
        borderWidth: p.out_of_country ? 2 : 0,
      },
      tooltip: { formatter: pointTooltip(p) },
    }))
    const arcs = data.arcs.map((a: GeoArc) => ({
      coords: [
        [a.from_lon, a.from_lat],
        [a.to_lon, a.to_lat],
      ],
      lineStyle: {
        color: lossColor(a.loss_pct),
        width: a.rtt_ms != null ? Math.min(1 + a.rtt_ms / 40, 4) : 1.2,
      },
    }))
    const you = data.points.find((p) => p.kind === 'you')
    const pathCoords = [
      ...(you ? [[you.lon, you.lat]] : []),
      ...data.path.map((h) => [h.lon, h.lat]),
    ]
    const pathLine = pathCoords.length >= 2 ? [{ coords: pathCoords }] : []
    const hopPoints = data.path.map((h) => ({
      name: h.city ?? h.ip,
      value: [h.lon, h.lat],
      symbolSize: 6,
      itemStyle: { color: lossColor(h.loss_pct), borderColor: '#0b1017', borderWidth: 1 },
      tooltip: { formatter: hopTooltip(h) },
    }))
    const option: EChartsOption = {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item', backgroundColor: '#1a2432', textStyle: { color: '#e6edf7' } },
      geo: {
        map: 'world',
        roam: true,
        itemStyle: { areaColor: '#131a26', borderColor: '#243044' },
        emphasis: { itemStyle: { areaColor: '#1a2432' }, label: { show: false } },
      },
      series: [
        {
          type: 'lines',
          coordinateSystem: 'geo',
          data: arcs,
          effect: { show: true, period: 4, trailLength: 0.2, symbol: 'arrow', symbolSize: 5 },
          lineStyle: { opacity: 0.75, curveness: 0.3 },
        },
        {
          type: 'lines',
          coordinateSystem: 'geo',
          data: pathLine,
          effect: { show: true, period: 5, trailLength: 0.4, symbol: 'circle', symbolSize: 3 },
          lineStyle: { color: '#7dd3fc', width: 1.6, opacity: 0.9, type: 'dashed', curveness: 0 },
          z: 3,
        },
        {
          type: 'scatter',
          coordinateSystem: 'geo',
          data: hopPoints,
          symbol: 'circle',
          z: 4,
        },
        {
          type: 'effectScatter',
          coordinateSystem: 'geo',
          data: points,
          rippleEffect: { scale: 2.5 },
          label: {
            show: true,
            formatter: '{b}',
            position: 'right',
            color: '#8a97ab',
            fontSize: 10,
          },
        },
      ],
    }
    chart.current.setOption(option, { notMerge: true })
  }, [data])

  return (
    <Panel
      title="Route map"
      subtitle="Your real route (dashed line = geolocated traceroute hops) and the CDN POPs serving you. Node size ∝ measured RTT; colour = loss (green <2%, amber <5%, red ≥5%); a red ring = a POP routed out of country."
    >
      <div ref={ref} style={{ height: 460 }} className="w-full" />
      <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted">
        <span>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#38bdf8' }} />{' '}
          You
        </span>
        <span>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#34d399' }} />{' '}
          loss &lt;2%
        </span>
        <span>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#fbbf24' }} />{' '}
          &lt;5%
        </span>
        <span>
          <span className="inline-block h-2 w-2 rounded-full" style={{ background: '#f87171' }} />{' '}
          ≥5%
        </span>
        <span>
          ┈ dashed = your traceroute route (hops) · ◯ red ring = routed abroad · bigger = higher RTT
        </span>
      </div>
    </Panel>
  )
}
