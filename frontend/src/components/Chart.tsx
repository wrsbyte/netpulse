import type { EChartsOption } from 'echarts'
import { useEffect, useRef } from 'react'
import { baseOption } from '../lib/echarts'
import { echarts } from '../lib/echarts-core'

interface ChartProps {
  option: EChartsOption
  height?: number
  loading?: boolean
  error?: boolean
}

// Thin ECharts wrapper: init once, update option on change, resize with the container.
export function Chart({ option, height = 220, loading, error }: ChartProps) {
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
    chart.current?.setOption({ ...baseOption, ...option }, { notMerge: true })
  }, [option])

  useEffect(() => {
    if (loading)
      chart.current?.showLoading('default', { maskColor: 'transparent', textColor: '#8a97ab' })
    else chart.current?.hideLoading()
  }, [loading])

  return (
    <div className="relative">
      <div ref={ref} style={{ height }} className="w-full" />
      {error && (
        <div className="absolute inset-0 flex items-center justify-center text-sm text-danger">
          Cannot reach the collector — is netpulse running?
        </div>
      )}
    </div>
  )
}
