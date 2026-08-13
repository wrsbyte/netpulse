import type { EChartsOption, SeriesOption } from 'echarts'
import type { Point, Series } from './types'
import { colorAt } from './format'

const reduceMotion =
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches

// Shared dark base every chart spreads over. Kept minimal; charts add axes/series.
export const baseOption: EChartsOption = {
  animation: !reduceMotion,
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

// A dashed horizontal reference line (e.g. "sluggish > 150 ms") so good/bad is visible.
export interface Threshold {
  y: number
  label: string
  color: string
  yAxisIndex?: number
}

export function thresholdSeries(thresholds: Threshold[]): SeriesOption[] {
  return [
    {
      type: 'line',
      data: [],
      silent: true,
      markLine: {
        symbol: 'none',
        lineStyle: { type: 'dashed', width: 1 },
        data: thresholds.map((t) => ({
          yAxis: t.y,
          yAxisIndex: t.yAxisIndex ?? 0,
          lineStyle: { color: t.color },
          label: {
            formatter: t.label,
            color: t.color,
            position: 'insideEndTop',
            fontSize: 10,
          },
        })),
      },
    },
  ]
}

type Pair = [number, number | null]

const toPairs = (points: Point[], key: keyof Point = 'avg'): Pair[] =>
  points.map((p) => [p.ts * 1000, p[key] as number | null])

// A line per series tag; if points carry mn/mx, draw a translucent band behind it.
// Colour is assigned by position so lines within one chart are always visually distinct
// (hashing the tag collided several targets onto the same yellow).
export function lineSeries(series: Series[], withBand = false): SeriesOption[] {
  const out: SeriesOption[] = []
  series.forEach((s, idx) => {
    const color = colorAt(idx)
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
  })
  return out
}
