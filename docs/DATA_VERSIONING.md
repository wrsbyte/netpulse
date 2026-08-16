# Data versioning — provenance & trust

## Why this exists

netpulse is a long-running instrument whose value is a **comparable time series**. That only holds
if we know *how* each row was measured. The triggering incident: the ping probe shipped with
`-c 4`, was later changed, and the stored loss quantized as **1/5 (20%)** while the committed code
said `-c 4` (1/4 = 25%). The data was no longer reproducible from the method, and there was no way,
from a row alone, to know which measurement produced it — so no way to know whether a "5% loss to
Cloudflare" was real or an artifact of a since-fixed probe. (It was an artifact.)

The fix: **every sample carries the code version that produced it**, and that version is a semver
bumped by **data impact** (see [CONVENTIONS.md](CONVENTIONS.md#data-versioning-provenance--trust)).
A query can then say "only rows from `code_version >= 0.2.0`" and mean it.

## The version

- **Single source of truth:** `__version__` in `backend/src/netpulse/__init__.py` (a literal).
  `pyproject.toml` reads it **dynamically** (`[tool.hatch.version]`), so packaging can't drift from
  it. Runtime reads the literal directly (`from netpulse import __version__`) — **not**
  `importlib.metadata`, which for an editable install serves the stale `.dist-info` until the next
  `uv sync`; the literal takes effect on a plain collector restart.
- **Governed by the dataset, not an API.** netpulse has no external API consumers; the dataset *is*
  the contract, so MAJOR/MINOR/PATCH are defined by what a change does to the *data* (the three
  rules in CONVENTIONS). A pure code refactor is PATCH; a probe method change that shifts values is
  MINOR even though it "feels" like a bug fix.

## Architecture

Two complementary records — a per-row stamp for filtering, and a registry for reproducibility.

### 1. Per-sample stamp: `code_version`

`code_version: str` lives on the **`NetworkScoped` mixin** (`db/models.py`) with
`default=__version__`, so all 14 sample tables (`ping_raw`, `dns_raw`, `tcp_connect`, `wifi_raw`, …)
inherit it in one place — the same pattern as `network_id` — and **every row created by the running
process is stamped with that process's version automatically** (the SQLAlchemy insert default), no
per-call wiring. A row is self-describing: which network, which code measured it.

Backfill: existing pre-versioning rows get `code_version = "0.0.0"` — the sentinel for **"provenance
unknown, do not trust for cross-version comparison"**.

### 2. Provenance registry: `data_version` table

One row per version ever run: `(version PK, first_seen_ts, git_sha, note)`. The collector
**upserts** its own version at startup, capturing the **git SHA** (`git rev-parse --short HEAD`,
best-effort — `null` in a non-git deploy). This maps a version to *when it began collecting* and the
*exact commit*, so any window of data is reproducible to a source tree. `first_seen_ts` also gives
the boundary timestamps where the method changed, for annotating charts.

### Querying by trust

```sql
-- Loss you can trust (measured the count-based, deterministic-sample way):
SELECT * FROM ping_raw WHERE code_version >= '0.2.0';

-- When did each measurement regime start? (chart boundary lines)
SELECT version, datetime(first_seen_ts,'unixepoch','localtime'), git_sha, note FROM data_version;
```

> Note: string comparison works for zero-padded single-digit semver; once any component reaches 10,
> compare with a parsed tuple (a helper in `analysis/` when we get there). Documented so it isn't a
> silent trap.

## The process (every measurement-affecting change)

1. **Make the change** (with its red→green test, per TDD).
2. **Bump `version`** in `backend/pyproject.toml` by data impact (MAJOR/MINOR/PATCH — CONVENTIONS).
3. **Log it** in [DATA_VERSIONS.md](DATA_VERSIONS.md): version, date, what changed, and the **trust
   note** — explicitly what must *not* be compared across the boundary.
4. **Migrate** if a column/table changed: extend `db/migrate.py` (`_ADDED_COLUMNS`), idempotent and
   backfilled. Migrations run on collector startup.
5. **Commit** everything together (`type(scope): …` + the version bump), so the SHA in the registry
   points at exactly the tree that produced that version's data.

`code_version` stamping and the `data_version` upsert are automatic — steps 4–5 are the only manual
wiring, and only when the schema changes.

## What is *not* versioned here (and why)

- **External data vintages** (GeoLite2, Team-Cymru ASN snapshot, destination list) — tracked
  separately per the route-peering plan; they change independently of the code semver.
- **Config** (`config.toml` targets/intervals) — a config edit changes *what* is measured, not
  *how*; if a target set change would make a metric incomparable, note it in DATA_VERSIONS.md.
