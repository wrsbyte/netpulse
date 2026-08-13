import type { EChartsOption } from 'echarts'
import type { Point, Series } from './types'
import { colorFor } from './format'

// Shared dark base every chart spreads over. Kept minimal; charts add axes/series.
export const baseOption: EChartsOption = {
  backgroundColor: 'transparent',
  textStyle: { color: '#8a97ab', fontSize: 11 },
  grid: { left: 48, right: 16, top: 24, bottom: 28 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: '#1a2432',
    borderColor: '#243044',
    textStyle: { color: '#e6edf7' },
  },
  legend: { top: 0, right: 8, textStyle: { color: '#8a97ab' }, icon: 'roundRect' },
  xAxis: {
    type: 'time',
    axisLine: { lineStyle: { color: '#243044' } },
    splitLine: { show: false },
  },
  yAxis: {
    type: 'value',
    axisLine: { show: false },
    splitLine: { lineStyle: { color: '#1a2432' } },
  },
}

type Pair = [number, number | null]

const toPairs = (points: Point[], key: keyof Point = 'avg'): Pair[] =>
  points.map((p) => [p.ts * 1000, p[key] as number | null])

// A line per series tag; if points carry mn/mx, draw a translucent band behind it.
export function lineSeries(series: Series[], withBand = false): EChartsOption['series'] {
  const out: NonNullable<EChartsOption['series']> = []
  for (const s of series) {
    const color = colorFor(s.tag)
    if (withBand && s.points.some((p) => p.mn != null && p.mx != null)) {
      out.push(
        {
          name: s.tag,
          type: 'line',
          data: toPairs(s.points, 'mn'),
          lineStyle: { opacity: 0 },
          stack: `band-${s.tag}`,
          symbol: 'none',
          silent: true,
          legendHoverLink: false,
        },
        {
          name: s.tag,
          type: 'line',
          data: s.points.map((p) => [
            p.ts * 1000,
            p.mx != null && p.mn != null ? p.mx - p.mn : null,
          ]),
          lineStyle: { opacity: 0 },
          areaStyle: { color, opacity: 0.1 },
          stack: `band-${s.tag}`,
          symbol: 'none',
          silent: true,
          legendHoverLink: false,
        },
      )
    }
    out.push({
      name: s.tag,
      type: 'line',
      data: toPairs(s.points),
      showSymbol: false,
      smooth: true,
      connectNulls: false,
      lineStyle: { color, width: 1.5 },
      itemStyle: { color },
    })
  }
  return out
}
