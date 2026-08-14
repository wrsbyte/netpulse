import type { EChartsOption } from 'echarts'
import { useState } from 'react'
import { useDiurnal } from '../hooks'
import { useUi } from '../store'
import { baseOption } from '../lib/echarts'
import { Chart } from './Chart'
import { Panel } from './ui'

type Metric = 'loss' | 'latency'

export function DiurnalPanel() {
  const range = useUi((s) => s.range)
  const [metric, setMetric] = useState<Metric>('loss')
  const { data, isLoading } = useDiurnal(metric, range)
  const cells = data?.cells ?? []
  const unit = metric === 'loss' ? '%' : 'ms'

  const option: EChartsOption = {
    grid: { ...baseOption.grid, top: 16 },
    tooltip: {
      ...baseOption.tooltip,
      formatter: (p: unknown) => {
        const d = p as { name: string; value: number; dataIndex: number }
        const c = cells[d.dataIndex]
        return `${d.name} · ${d.value.toFixed(1)}${unit} (CI ${c.ci_lo.toFixed(1)}–${c.ci_hi.toFixed(1)}, n=${c.n})`
      },
    },
    xAxis: {
      type: 'category',
      data: cells.map((c) => `${String(c.hour).padStart(2, '0')}h`),
      axisLine: { lineStyle: { color: '#243044' } },
    },
    yAxis: { ...baseOption.yAxis, axisLabel: { formatter: `{value} ${unit}` } },
    series: [
      {
        type: 'bar',
        data: cells.map((c) => ({
          value: Number(c.mean.toFixed(2)),
          itemStyle: {
            color:
              metric === 'loss'
                ? c.mean < 1
                  ? '#34d399'
                  : c.mean < 3
                    ? '#fbbf24'
                    : '#f87171'
                : '#38bdf8',
          },
        })),
      },
    ],
  }

  return (
    <Panel
      title="By hour of day"
      subtitle="Does it get worse at peak hours? Bars = mean per local hour; tooltip shows the block-bootstrap 95% CI."
      actions={
        <div className="inline-flex rounded-lg border border-border bg-panel-2 p-0.5 text-sm">
          {(['loss', 'latency'] as Metric[]).map((m) => (
            <button
              key={m}
              onClick={() => setMetric(m)}
              className={`rounded-md px-2.5 py-0.5 transition ${
                metric === m ? 'bg-accent font-semibold text-bg' : 'text-muted hover:text-ink'
              }`}
            >
              {m}
            </button>
          ))}
        </div>
      }
    >
      {data && !data.sufficient && (
        <p className="mb-2 rounded-md bg-warn/10 px-2 py-1 text-xs text-warn">
          Only {data.days_observed} day{data.days_observed === 1 ? '' : 's'} observed — a peak-hour
          claim needs ≥ 3 days of repeating pattern. This is indicative, not proven.
        </p>
      )}
      <Chart option={option} loading={isLoading} height={200} />
    </Panel>
  )
}
