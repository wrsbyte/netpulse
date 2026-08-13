import { useEffect, useMemo, useState } from 'react'
import { useRaw, useRawTables } from '../hooks'
import { useUi } from '../store'
import { api } from '../lib/api'
import { fmt } from '../lib/format'
import type { RawAgg, RawColumn } from '../lib/types'
import { Panel } from './ui'

const PAGE_SIZES = [50, 100, 250, 500]

function cell(col: RawColumn, value: unknown): string {
  if (value == null) return '—'
  if (col.type === 'time') return fmt.datetime(value as number)
  if (col.type === 'bool') return value ? 'ok' : 'fail'
  if (col.type === 'number') {
    const n = value as number
    return Number.isInteger(n) ? String(n) : n.toFixed(2)
  }
  return String(value)
}

function num(v: number | null, unit: string | null): string {
  if (v == null) return '—'
  const s = Number.isInteger(v) ? String(v) : v.toFixed(2)
  return unit ? `${s} ${unit}` : s
}

export function DataTab() {
  const range = useUi((s) => s.range)
  const network = useUi((s) => s.network)
  const { data: tables } = useRawTables()

  const [table, setTable] = useState('ping')
  const [page, setPage] = useState(0)
  const [pageSize, setPageSize] = useState(100)
  const [sort, setSort] = useState<{ col: string; dir: 'asc' | 'desc' } | null>(null)
  const [filters, setFilters] = useState<Record<string, string>>({})
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')

  // Debounce the free-text search so we don't query on every keystroke.
  useEffect(() => {
    const id = setTimeout(() => setQ(search.trim()), 300)
    return () => clearTimeout(id)
  }, [search])

  // Any filter/sort/table change resets to the first page.
  useEffect(() => setPage(0), [table, pageSize, sort, filters, q])

  const query = useMemo(
    () => ({
      q: q || undefined,
      sort: sort?.col,
      dir: sort?.dir,
      filters,
      limit: pageSize,
      offset: page * pageSize,
    }),
    [q, sort, filters, pageSize, page],
  )
  const { data, isFetching } = useRaw(table, range, query)

  const columns = data?.columns ?? []
  const aggByCol = useMemo(
    () => Object.fromEntries((data?.agg ?? []).map((a: RawAgg) => [a.column, a])),
    [data],
  )
  const total = data?.total ?? 0
  const pages = Math.max(1, Math.ceil(total / pageSize))
  const from = total === 0 ? 0 : page * pageSize + 1
  const to = Math.min(total, (page + 1) * pageSize)
  const activeFilters = Object.keys(filters).length + (q ? 1 : 0)

  const toggleSort = (col: string) =>
    setSort((s) =>
      s?.col !== col ? { col, dir: 'desc' } : s.dir === 'desc' ? { col, dir: 'asc' } : null,
    )

  const setFilter = (col: string, val: string) =>
    setFilters((f) => {
      const next = { ...f }
      if (val) next[col] = val
      else delete next[col]
      return next
    })

  const reset = () => {
    setFilters({})
    setSearch('')
    setSort(null)
  }

  return (
    <Panel
      title="Raw samples"
      subtitle={`${from.toLocaleString()}–${to.toLocaleString()} of ${total.toLocaleString()} rows · aggregates below reflect the current filter`}
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="w-36 rounded-lg border border-border bg-panel-2 px-2 py-1 text-sm text-ink outline-none placeholder:text-muted focus:border-accent"
          />
          <select
            value={table}
            onChange={(e) => {
              setTable(e.target.value)
              reset()
            }}
            className="rounded-lg border border-border bg-panel-2 px-2 py-1 text-sm text-ink outline-none hover:border-accent focus:border-accent"
          >
            {(tables ?? [table]).map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          {activeFilters > 0 && (
            <button
              onClick={reset}
              className="rounded-lg border border-border bg-panel-2 px-2 py-1 text-sm text-muted transition hover:border-accent hover:text-ink"
            >
              Clear ({activeFilters})
            </button>
          )}
          <a
            href={api.rawCsvUrl(table, range, network, query)}
            className="rounded-lg border border-border bg-panel-2 px-3 py-1 text-sm text-ink transition hover:border-accent"
          >
            Export CSV
          </a>
        </div>
      }
    >
      {/* Per-column enum filters */}
      {columns.some((c) => c.values && c.values.length > 0) && (
        <div className="mb-3 flex flex-wrap gap-2">
          {columns
            .filter((c) => c.values && c.values.length > 0)
            .map((c) => (
              <select
                key={c.name}
                value={filters[c.name] ?? ''}
                onChange={(e) => setFilter(c.name, e.target.value)}
                className={`rounded-lg border px-2 py-1 text-xs outline-none focus:border-accent ${
                  filters[c.name]
                    ? 'border-accent bg-accent/10 text-ink'
                    : 'border-border bg-panel-2 text-muted'
                }`}
              >
                <option value="">{c.name}: all</option>
                {c.values!.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            ))}
        </div>
      )}

      <div className={`overflow-x-auto transition-opacity ${isFetching ? 'opacity-60' : ''}`}>
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
              {columns.map((c) => (
                <th
                  key={c.name}
                  scope="col"
                  aria-sort={
                    sort?.col === c.name
                      ? sort.dir === 'desc'
                        ? 'descending'
                        : 'ascending'
                      : 'none'
                  }
                  className="sticky top-0 whitespace-nowrap border-b border-border bg-panel pb-1 pr-3 font-medium"
                >
                  <button
                    onClick={() => toggleSort(c.name)}
                    className="inline-flex items-center gap-1 hover:text-ink"
                    title={`Sort by ${c.name}`}
                  >
                    {c.name}
                    {c.unit && <span className="normal-case text-muted">({c.unit})</span>}
                    <span className="text-accent">
                      {sort?.col === c.name ? (sort.dir === 'desc' ? '↓' : '↑') : '↕'}
                    </span>
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data?.rows.map((row, i) => (
              <tr key={i} className="border-b border-border/40 last:border-0 hover:bg-panel-2/50">
                {columns.map((c) => (
                  <td
                    key={c.name}
                    className={`whitespace-nowrap py-1 pr-3 tabular-nums ${
                      c.type === 'number' ? 'text-right' : 'text-ink'
                    } ${c.type === 'number' ? 'text-ink' : ''}`}
                  >
                    {cell(c, row[c.name])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          {data && data.agg.length > 0 && (
            <tfoot>
              <tr className="border-t border-border text-xs text-muted">
                {columns.map((c, i) => {
                  const a = aggByCol[c.name]
                  return (
                    <td key={c.name} className="whitespace-nowrap py-1.5 pr-3 text-right">
                      {i === 0 ? (
                        <span className="text-[11px] uppercase tracking-wide">avg · p95</span>
                      ) : a ? (
                        <span
                          className="tabular-nums"
                          title={`min ${num(a.min, c.unit)} · avg ${num(a.avg, c.unit)} · p95 ${num(a.p95, c.unit)} · max ${num(a.max, c.unit)} · n ${a.count}`}
                        >
                          {num(a.avg, c.unit)} · {num(a.p95, null)}
                        </span>
                      ) : (
                        ''
                      )}
                    </td>
                  )
                })}
              </tr>
            </tfoot>
          )}
        </table>
        {!data && <p className="py-6 text-center text-sm text-muted">Loading…</p>}
        {data && data.rows.length === 0 && (
          <p className="py-6 text-center text-sm text-muted">
            No rows match {activeFilters > 0 ? 'these filters' : 'this range'}.
          </p>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted">
        <label className="flex items-center gap-1.5">
          <span>Rows per page</span>
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="rounded-lg border border-border bg-panel-2 px-2 py-1 text-ink outline-none focus:border-accent"
          >
            {PAGE_SIZES.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-2">
          <span className="tabular-nums">
            Page {page + 1} of {pages}
          </span>
          {[
            { label: '« First', to: 0, disabled: page === 0 },
            { label: '‹ Prev', to: page - 1, disabled: page === 0 },
            { label: 'Next ›', to: page + 1, disabled: page + 1 >= pages },
            { label: 'Last »', to: pages - 1, disabled: page + 1 >= pages },
          ].map((b) => (
            <button
              key={b.label}
              onClick={() => setPage(b.to)}
              disabled={b.disabled}
              className="rounded-lg border border-border bg-panel-2 px-2.5 py-1 text-ink transition hover:border-accent disabled:opacity-40"
            >
              {b.label}
            </button>
          ))}
        </div>
      </div>
    </Panel>
  )
}
