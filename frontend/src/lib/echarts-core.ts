// Tree-shaken ECharts: register only the chart types and components we use, so the bundle
// carries a fraction of the full library. Import `echarts` from here, never from 'echarts'.
import { BarChart, EffectScatterChart, LinesChart, LineChart, MapChart } from 'echarts/charts'
import {
  GeoComponent,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TooltipComponent,
} from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import world from '../assets/world.geo.json'

echarts.use([
  LineChart,
  BarChart,
  MapChart,
  LinesChart,
  EffectScatterChart,
  GeoComponent,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  MarkLineComponent,
  CanvasRenderer,
])

// Register the vendored world map once (offline, CSP-safe — no external tiles).
echarts.registerMap('world', world as Parameters<typeof echarts.registerMap>[1])

export { echarts }
