# Product conventions

The quality bar every feature must clear before it ships. A feature that fails any applicable
rule here is unfinished — not "good enough". These are product rules; engineering rules live in
`CONVENTIONS.md`. Reviews (and the audit agents) check against this document, not opinion.

## First principle: self-explanatory

A competent user with no manual must understand any screen on sight. That means, for every
value shown:

- **Unit** always visible (ms, dBm, Mbps, %, count). Never a bare number.
- **What it measures** — a one-line plain-language description reachable without leaving the view
  (subtitle or tooltip).
- **Direction & reference range** — is higher or lower better, and what counts as good / bad
  (e.g. "latency: lower is better · good < 30 ms · sluggish > 150 ms"). Show the threshold on the
  chart itself (reference line), not only in prose.
- **Type / enumeration** — for coded values (grade A+…F, severity, event kind, boolean ok/fail),
  the possible values and their meaning are discoverable (legend or tooltip).
- **Aggregation stated** — if a number is an average / p95 / max, say so.

## Data views (tables) — the non-negotiable set

A table is not shippable with pagination alone. Every data table provides, **server-side** (over
the full filtered set, not just the visible page):

1. **Sorting** — click any column header; asc/desc/none; a visible sort indicator.
2. **Filtering** — a global text search plus per-column filters appropriate to the column
   (enum → dropdown, number → min/max, boolean → toggle, time → range).
3. **Aggregation** — a summary row/panel for numeric columns: count, min, max, mean, p95.
   Aggregates reflect the filter, not the page.
4. **Pagination** — page size selector, total row count, current range ("1–100 of 9,282"),
   first/prev/next/last. Never load an unbounded set.
5. **Export** — CSV of the current filtered/sorted set (not just the page).
6. **Column metadata** — header shows the unit; a tooltip explains the column.
7. **Density & overflow** — horizontal scroll contained; numeric columns right-aligned and
   `tabular-nums`; timestamps localized.

## Metrics & charts

- Y-axis labelled with the unit; series legend names carry units where mixed.
- Threshold **reference lines** for the good/bad boundaries relevant to that metric.
- Percentile band (min–max or p25–p95) shown where variance matters, not a bare mean.
- Empty range renders an explanatory empty state, never a blank canvas.
- Colours are semantic and consistent project-wide: ok = green, warning = amber, danger = red,
  info = blue. Colour is never the only signal (pair with icon/text/position — WCAG).

## States (every async view)

Loading, empty, error, and populated are all designed — no dead blank. Loading shows a skeleton
or spinner; empty explains what will appear and when; error states are actionable.

## Interaction & motion

- Every interactive element has visible hover, focus (keyboard), active and disabled states.
- Focus is keyboard-reachable and visibly ringed; tab order follows reading order.
- Transitions are ≤ 200 ms and purposeful (state change, reveal) — never decorative jitter.
- Primary action per context is singular and obvious; destructive/data-cost actions
  (speedtest consumes data) are labelled as such.

## Verdict / conclusions

- The system states a conclusion and its **evidence** (numbers, timestamps, hops), plus a
  **confidence**. It never shows raw metrics and leaves the user to guess.
- Grades and severities always carry their scale/legend.

## Accessibility (WCAG 2.1 AA)

- Text contrast ≥ 4.5:1, non-text ≥ 3:1. State conveyed by ≥ 2 channels.
- Full keyboard operation; visible focus; semantic HTML (`th/scope`, `label`, `button`).
- Respect `prefers-reduced-motion`.

## Definition of done (per feature)

Self-explanatory ✓ · states ✓ · (tables) filter+sort+aggregate+paginate+export ✓ · units &
ranges ✓ · keyboard + focus ✓ · `make check` green ✓ · reviewed against this doc ✓.
