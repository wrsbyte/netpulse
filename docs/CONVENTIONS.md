# Conventions

Standards this repo follows so it stays consistent and reviewable. `make check` enforces the
automated ones.

## Language & tooling

- **Backend** — Python 3.13, typed throughout. Managed by **uv**. Lint/format **ruff**, types
  **mypy `strict`**, tests **pytest**. Async I/O (probes shell out concurrently).
- **Frontend** — TypeScript (strict), **pnpm**, Vite. Lint **oxlint**, format **Prettier**
  (single quotes, no semicolons, width 100), styling **Tailwind**.
- Everything user-facing and in-code is **English**.

## Backend

- **One responsibility per module.** A probe measures and parses; it does not schedule, store,
  or notify — the collector orchestrates, the API reads. Keep them decoupled.
- **Pure logic is extracted and tested.** Anything derivable without I/O (parsing, MOS,
  percentile, IP extraction) is a pure function with a unit test. Probes stay thin.
- **Typed data crosses boundaries.** Config is Pydantic; the store is typed SQLAlchemy 2.0
  models; API responses are Pydantic schemas that mirror `frontend/src/lib/types.ts`.
- **Graceful degradation, not defensive noise.** A missing tool or unreachable host is an
  expected outcome the probe returns cleanly — no blanket try/except swallowing real bugs. The
  one broad guard is per-scheduled-job, so a crash can't stop the daemon.
- **No secrets, no root by default.** Core probes are unprivileged; the single optional
  privilege (raw-socket `mtr`) is a scoped, reviewed sudoers rule.
- Comments explain **why**, never what. Names carry the meaning.

## Frontend

- **Server state via TanStack Query; UI state via Zustand.** Don't mix them; never hand-roll
  fetch-in-effect for data that Query should own.
- **One ECharts lifecycle owner** (`components/Chart.tsx`). Panels produce a typed
  `EChartsOption` and nothing else — no direct `echarts.init` elsewhere.
- **Import ECharts from `lib/echarts-core.ts`** (tree-shaken registry), never from `'echarts'`
  directly, so the bundle stays small.
- Theme colors come from Tailwind `@theme` tokens (`text-ink`, `bg-panel`, …); avoid ad-hoc
  hex except inside chart option builders.

## TDD — the working rule

**Every fix starts with a failing test.** Reproduce the bug as a red test, then make it green.
The two `ss`/status regressions in `tests/test_flows.py` and `tests/test_status.py` exist
because they were written red-first against the exact bug (state-filtered `ss` output; empty
rollup right after boot). Don't fix-then-cover; cover-then-fix.

## Commits

Conventional, imperative, English: `type(scope): summary` (e.g. `feat(probes): add wifi
channel scan`). Keep diffs minimal and on-topic; run `make check` before committing.
