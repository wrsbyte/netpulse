import type { EChartsOption } from 'echarts'
import { useEffect, useRef } from 'react'
import { useGeo } from '../hooks'
import { echarts } from '../lib/echarts-core'
import { Panel } from './ui'

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
      value: [p.lon, p.lat],
      itemStyle: {
        color: p.kind === 'you' ? '#38bdf8' : p.out_of_country ? '#f87171' : '#34d399',
      },
    }))
    const arcs = data.arcs.map((a) => ({
      coords: [
        [a.from_lon, a.from_lat],
        [a.to_lon, a.to_lat],
      ],
      lineStyle: { color: a.out_of_country ? '#f87171' : '#34d399' },
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
          lineStyle: { width: 1.2, opacity: 0.7, curveness: 0.3 },
        },
        {
          type: 'effectScatter',
          coordinateSystem: 'geo',
          data: points,
          symbolSize: 10,
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
      subtitle="You and the CDN POPs serving you (coarse: airport-level for POPs). A red arc = an out-of-country POP — your traffic to that CDN is routed abroad."
    >
      <div ref={ref} style={{ height: 460 }} className="w-full" />
    </Panel>
  )
}
