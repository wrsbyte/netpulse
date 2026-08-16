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

## Data versioning (provenance & trust)

netpulse is a **measurement instrument**: its real public contract is the *dataset*, not an API.
So the package **semver in `backend/pyproject.toml`** (surfaced as `netpulse.__version__`) is
governed by **data impact, not code-API impact**, and **every collected sample stores the version
that produced it** (`code_version`). This is how we know which rows to trust and never silently pool
data measured two different ways. (This convention exists because a probe once changed `ping -c`
without a version bump: stored loss quantized as 1/5 while the code said 1/4 — the data was no longer
reproducible from the method. Full design & process: [DATA_VERSIONING.md](DATA_VERSIONING.md).)

**Bump the version in the SAME commit as the change**, by data impact:

- **MAJOR** (`X.0.0`) — a metric's **meaning/unit/schema breaks**; old and new rows are
  *incomparable*. Never pool the affected metric across a major boundary.
- **MINOR** (`0.X.0`) — the **measurement method changed so values step**, but the metric still
  means the same thing (e.g. `ping -c 4→10`, loss now count-based, grade on TCP not ICMP); **or** a
  new metric/probe is added. Compare across a minor boundary only with the step in mind.
- **PATCH** (`0.0.X`) — **no effect on collected values**: refactor, crash fix, docs, or a fix that
  only stops *garbage* rows (fabricated outages) without shifting valid ones.

**Maintenance, every time you bump:**
1. Edit `__version__` in `backend/src/netpulse/__init__.py` (the single source; `pyproject.toml`
   reads it dynamically).
2. Add an entry to [DATA_VERSIONS.md](DATA_VERSIONS.md): version, date, what changed, and the
   **trust note** (what not to compare across the boundary, and why).
3. If it adds/changes a column, extend `db/migrate.py` (idempotent, backfilled) — see TDD below.
4. Stamping is automatic (the `code_version` column defaults to `__version__`); the collector also
   records the version + git SHA in the `data_version` registry at startup. Nothing else to wire.

## TDD — the working rule

**Every fix starts with a failing test.** Reproduce the bug as a red test, then make it green.
The two `ss`/status regressions in `tests/test_flows.py` and `tests/test_status.py` exist
because they were written red-first against the exact bug (state-filtered `ss` output; empty
rollup right after boot). Don't fix-then-cover; cover-then-fix.

## Commits

Conventional, imperative, English: `type(scope): summary` (e.g. `feat(probes): add wifi
channel scan`). Keep diffs minimal and on-topic; run `make check` before committing.
