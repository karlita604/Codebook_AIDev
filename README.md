# Codebook_AIDev

Measuring how repository structural health (design/implementation smells,
OO metrics) and PR-level process behavior change when AI coding agents
start contributing to a project — using an interrupted time series (not a
naive before/after), so ordinary codebase drift doesn't get mistaken for
an agent effect.

This README documents the pipeline end to end: how to set it up, how to
run it, how to scale the corpus, and how to reproduce the analysis from
scratch. For the actual findings, methodology rationale, and current
status, start with `Writing/ProjectStatus.md` and `Writing/Results.md`
instead — this file is about *running the code*, not the conclusions.

---

## Table of contents

1. [What this project does](#what-this-project-does)
2. [Repository layout](#repository-layout)
3. [Prerequisites](#prerequisites)
4. [Setup](#setup)
5. [Quick start — running the pipeline](#quick-start--running-the-pipeline)
6. [The pipeline, stage by stage](#the-pipeline-stage-by-stage)
7. [Scaling the corpus](#scaling-the-corpus)
8. [Replicating the analysis from scratch](#replicating-the-analysis-from-scratch)
9. [Output data reference](#output-data-reference)
10. [Configuration and registries](#configuration-and-registries)
11. [Storage lifecycle](#storage-lifecycle)
12. [Known limitations and troubleshooting](#known-limitations-and-troubleshooting)
13. [Where to find the findings](#where-to-find-the-findings)

---

## What this project does

**Research question**: when an AI coding agent (Claude Code, GitHub
Copilot, Cursor, Devin, OpenAI Codex, …) starts contributing pull
requests to a repository, does the repository's internal code quality
and its PR/review process measurably change — and if so, in a consistent
direction across repos?

**Design**: for each repository in the corpus, its *intervention point*
is the date of its first AI-agent-authored PR (drawn from the `hao-li/AIDev`
dataset on Hugging Face). Two independent tracks are then sampled:

- **Track A** (source tree): the repo's source code is snapshotted at a
  grid of commits — either a fixed monthly calendar grid (`A1`,
  2022‑01‑01 → 2026‑03‑31) or a grid centered on the repo's own
  intervention date (`A2`, weekly ±3 months, monthly out to ±12 months) —
  and OO metrics / code smells are computed at each snapshot.
- **Track B** (PR events): pull request metadata is sampled the same two
  ways (`B1` fixed monthly window, `B2` centered on the intervention PR)
  to track process-level signals (PR size, merge latency, review
  activity) independent of the source-tree snapshots.

A third analysis (**RQ3**, the "entity tracker") follows individual
classes/methods across their full git history to measure churn rate
before vs. after the intervention point, independent of the fixed
snapshot grid.

Three parallel measurement paths exist for the source-tree track:

1. **DPy/Designite** (licensed trial tools) — the original pilot's
   ground truth, kept for cross-validation, but LOC-capped and slow (see
   [Known limitations](#known-limitations-and-troubleshooting)).
2. **In-house Python** (`src/inhouse/py_metrics.py`, `py_smells.py`) —
   a from-scratch `ast`-based engine, no LOC cap, validated against #1
   (r = 0.997–0.999 for OO metrics).
3. **In-house C#** (`src/inhouse/roslyn_tool/`) — a syntax-only Roslyn
   port (no `.sln`/`MSBuildWorkspace` project load), validated the same
   way.

---

## Repository layout

```
src/
  phase0/          Corpus selection & data collection (repo candidates,
                    PR sampling, git cloning, snapshot materialization,
                    the legacy DPy/Designite driver)
  inhouse/          In-house Python + C# analysis engines: OO metrics,
                    code smells, entity-history (RQ3) tracking,
                    consolidation, validation against the licensed tools
  inhouse/roslyn_tool/   The compiled C# analyzer (.NET 8) the Python
                    side shells out to for C# repos
  analysis/         Statistical analysis (segmented regression)
  viz/              Figure/table generation
  pipeline/         The orchestrator (run_pipeline.py)
  common/           Shared infrastructure: resumability, repo-exclusion
                    registry, parallel dispatch, storage lifecycle
  repos/            Candidate-repo dedup utility (Phase 0)

data/               Gitignored. repo_cache/ (full-history clones),
                    snapshots/ (extracted per-commit source trees, the
                    input to stages 4-6 below), tool_output/ (raw
                    per-chunk output from the legacy DPy driver, auto-
                    deleted once pooled unless you pass --keep-tool-output
                    to long_analysis.py).

results/
  repos/            Candidate pools, repo summaries, the exclusion/
                    keep-cache registries
  snapshots/        The Track A snapshot manifest (which commit
                    represents which repo × track × date)
  pr_samples/       Track B PR-event samples
  analysis/         Every pooled metrics/smells/entity-history/
                    regression output — the actual analysis results
  phase0/           Early candidate-pool iterations (historical)

Writing/            All research documentation: methodology
                    (Longitudinal.md), current status (ProjectStatus.md),
                    findings (Results.md), the raw chronological build
                    log (ProjectUpdate.md), and per-subsystem design docs
                    (InHouseTooling.md, PySmellDetection.md,
                    RQ3_CodeTracking.md). Writing/figures/ holds the
                    current Track A/churn figure set generated by stages
                    10-11 below.

figures/            A separate, earlier committed figure set
                    (rq3_visual_report/) from before RQ3's figures moved
                    under Writing/figures/ — kept for history, not
                    regenerated by the current pipeline.

.gitignore excludes: data/repo_cache/, data/tool_output/,
data/snapshots/, data/archive/, .venv/, __pycache__/, logs/,
src/inhouse/roslyn_tool/{bin,obj}/, and any github_tokens* file.
```

---

## Prerequisites

- **Python 3.10+** (developed against 3.14; nothing version-specific is
  known, but not tested below 3.10)
- **.NET 8 SDK** (`dotnet --version` should print `8.x`) — needed to
  build/run the C# analyzer in `src/inhouse/roslyn_tool/`
- **git** on `PATH`, with `git cat-file --batch` support (any
  reasonably recent git — this is a long-standing plumbing command)
- **A GitHub personal access token** — needed for Track B (PR sampling)
  and for the Hugging Face-free portions of Phase 0. Unauthenticated
  GitHub API access is capped at 60 requests/hour, which this pipeline
  needs far more than.
- (Optional) **DPy** and **Designite** trial licenses, only if you want
  to re-run the legacy pilot-recalibration path (`long_analysis.py`) —
  not needed for the in-house tools, which are the default path for
  anything beyond the original 4-repo pilot.

---

## Setup

```bash
# 1. Python dependencies
pip install -r requirements.txt
# (pandas, pyarrow, huggingface_hub, requests, pydriller, lizard)

# 2. Build the C# analyzer once (subsequent runs auto-rebuild if stale)
cd src/inhouse/roslyn_tool
dotnet build -c Release
cd ../../..

# 3. Set your GitHub token (needed for Track B / PR sampling)
# PowerShell:
$env:GITHUB_TOKEN = "ghp_..."
# persisted across terminals:
setx GITHUB_TOKEN "ghp_..."
```

**Optional — multiple GitHub tokens for faster Track B sampling.** If you
have more than one personal access token, drop the extra ones (one per
line, `#`-comments allowed) into a local file and point
`GITHUB_TOKENS_FILE` at it:

```powershell
$env:GITHUB_TOKENS_FILE = "C:\path\to\your\extra_tokens.txt"
```

Requests round-robin across every token found (`GITHUB_TOKEN` plus
whatever's in the file), and each additional token roughly divides the
wall-clock cost of Track B sampling — 2 tokens ≈ half the time. Never
commit a tokens file; keep it outside the repo if you can (the
`.gitignore` patterns `github_tokens*`/`.github_tokens` are a backstop,
not a substitute for keeping it elsewhere).

---

## Quick start — running the pipeline

Everything runs through one orchestrator,
`src/pipeline/run_pipeline.py`, which sequences the 13-stage pipeline
(previously run stage-by-stage by hand). It's a thin subprocess
sequencer — it doesn't reimplement any stage, just runs each one's own
script with the right flags and stops on the first failure.

```bash
# Run everything, sequentially, against whatever corpus size the last
# `select` run produced:
python -m src.pipeline.run_pipeline run

# Run just a subset of stages:
python -m src.pipeline.run_pipeline run --stages metrics,smells

# Smoke-test without doing real work:
python -m src.pipeline.run_pipeline run --dry-run --limit 3

# Scope to one repo:
python -m src.pipeline.run_pipeline run --repo crewAIInc/crewAI

# Grow the corpus and parallelize:
python -m src.pipeline.run_pipeline run --target-total 100 --workers 4

# See what the last run did:
python -m src.pipeline.run_pipeline status
```

Every run writes a rolled-up log to
`results/pipeline-run-<timestamp>.json` (stage names, exit codes, wall
time) — check `status` after a run to see it summarized.

**You do not have to use the orchestrator.** Every stage is also a
normal, independently runnable script with its own `--help`; the
orchestrator is a convenience, not a requirement. This matters if you
want to inspect one stage's output before moving to the next, or if you
need flags the orchestrator doesn't forward (each script's own
`--help` is authoritative for what it accepts).

---

## The pipeline, stage by stage

Run in this order (the orchestrator's default). Each stage's own file
has a full design-rationale docstring at the top — this is a summary of
what it does and its key flags, not a replacement for reading it.

### 1. `select` — `src/phase0/repo_pr_selection.py`

Picks the repo corpus. Reads the candidate pool
(`results/phase0/repos_*.csv`, ≥500-star Python/C# repos), joins each
candidate against the `hao-li/AIDev` PR dataset (Hugging Face, no auth
needed) to find each repo's *intervention date* (its earliest
agent-authored PR), then stratifies a `--target-total`-sized pick across
languages, preferring repos with more agent-PR signal.

```bash
python src/phase0/repo_pr_selection.py --target-total 100
```

Writes `results/repos/<date>-aidev-agent-prs-<n>.csv` (PR-level rows) and
`results/repos/<date>-repo-summary-<n>.csv` (one row per candidate repo,
with `intervention_date` — this is what every later stage reads to
rebuild the same N-repo pick deterministically).

Draws from a fixed candidate pool file — it cannot return more repos
than that file has. Re-run the underlying `≥500-star Python/C#` GitHub
search with wider parameters first if you need a bigger pool (this repo
ships with 235 candidates, enough for 100 but not 1000 — see
[Scaling the corpus](#scaling-the-corpus)).

`--verify-monotonic-growth` is a diagnostic, not part of the normal
flow: it checks that `suggest_pilot(n)`'s pick is a superset of
`suggest_pilot(n-1)`'s for every n against the current candidate pool —
re-run it whenever the candidate pool changes shape (e.g. after widening
it for a 1000-repo run) before relying on that property.

### 2. `snapshot-manifest` — `src/phase0/repo_snapshot_pipeline.py`

For each repo in the `--target-total`-sized pick, clones it (partial
clone — full commit history, blobs fetched lazily) into
`data/repo_cache/<owner>__<repo>/`, then resolves the A1 (fixed
calendar) and A2 (intervention-centered) grids against it — for each
grid point, the nearest commit at-or-before that date. This is a
*manifest* (which commit represents which repo×track×date), not the
metrics themselves.

```bash
python src/phase0/repo_snapshot_pipeline.py --target-total 100
```

Writes `results/snapshots/<date>-repo-snapshot-manifest-<n>.csv`. This
is the file every downstream analysis stage reads as its input. No
`--workers` flag on this stage yet — cloning runs one repo at a time.

### 3. `materialize` — `src/phase0/materialize_snapshots.py`

Extracts the actual source-language files (not a full checkout — just
`*.py` or `*.cs`/`*.sln`/etc., language-filtered) for every unique commit
in the manifest, into `data/snapshots/<owner>__<repo>/<sha>/`. Dedupes by
`(repo, commit_sha)`, since several grid points can resolve to the same
commit.

```bash
python src/phase0/materialize_snapshots.py                      # all repos
python src/phase0/materialize_snapshots.py --repo crewAIInc/crewAI
python src/phase0/materialize_snapshots.py --workers 4           # parallel
```

Idempotent/resumable — reruns skip already-materialized commits.
`EXCLUDED_REPOS` (permanently unmaterializable repos, e.g. ones whose
project graph can't be loaded) is read from the exclusion registry, not
hardcoded — see [Configuration and registries](#configuration-and-registries).

### 4–6. `metrics` / `smells` / `entity-history`

The actual analysis, one stage per output type:

```bash
# OO metrics (LOC, WMC, LCOM, DIT, fan-in/out, cyclomatic complexity, …)
python src/inhouse/pool_inhouse_metrics.py

# Code smells (God Class, Data Class, Feature Envy, Brain Method —
# Lanza & Marinescu 2006 Detection Strategies)
python src/inhouse/pool_inhouse_smells.py

# RQ3 entity-history: per-class/method lineage tracking across renames
python src/inhouse/pool_entity_history.py
```

All three share the same conventions:

- `--manifest <path>` (default: latest in `results/snapshots/`)
- `--dry-run` — bookkeeping only, no real analysis (fast smoke test)
- `--limit N` / `--repo <substring>` — scope to a subset
- `--stale-check` — report done-row bookkeeping and exit, without
  running anything (sanity-check before a real run — see
  [Known limitations](#known-limitations-and-troubleshooting) for the
  footgun this guards against)
- `--workers N` — repos to process in parallel (default 1 = sequential).
  Each repo's analysis is fully independent, so this is the main lever
  for wall-clock time at scale; `>1` writes one output fragment file per
  repo instead of one shared file (both shapes are handled transparently
  by the consolidation step and the resumability check)

`pool_inhouse_metrics.py`/`pool_inhouse_smells.py` also auto-apply any
`scope=per-run` exclusion from the registry (see
[Configuration and registries](#configuration-and-registries)) — e.g. a
repo whose size makes a particular computation impractically slow.

Every row includes a `status` column (`"ok"` or an error string);
failures are also written to a sibling `<output>-errors.csv` rather than
crashing the run.

### 7–8. `consolidate-metrics` / `consolidate-smells`

```bash
python src/inhouse/consolidate_inhouse_metrics.py
python src/inhouse/consolidate_inhouse_smells.py
```

Concatenates every fragment file from stages 4–5 (there can be several,
if you ran with `--workers` or `--repo`-scoped invocations) into one
canonical pooled table, deduped on `(repo_id, track, target_date,
commit_sha)`, keep-last. No CLI flags — always operates on everything it
finds in `results/analysis/`.

### 9. `regression` — `src/analysis/segmented_regression.py`

Fits the interrupted-time-series model (`metric ~ time + post +
time_since_intervention × post`) per (repo, metric), closed-form OLS, for
every repo with enough pre/post data (default: ≥5 points each side).

```bash
python src/analysis/segmented_regression.py
```

Writes `results/analysis/<date>-segmented-regression-full-<n>.csv`
(fitted rows) and a matching `-skipped.csv` (repos excluded for
insufficient data — reported, not silently dropped).

### 10–11. `viz-track-a` / `viz-churn`

```bash
python src/viz/generate_track_a_figures.py     # Figs 1-6, Tables 1-2
python src/viz/generate_churn_figures.py --entity-history <path>  # Figs 7-9, Table 3
```

Reads the consolidated/regression outputs above and writes PNGs/CSVs to
`Writing/figures/`. `generate_churn_figures.py` needs an explicit
`--entity-history` path (the orchestrator resolves this to the latest
real pooled entity-history file automatically).

### 12–13. `validate-metrics` / `validate-smells`

```bash
python src/inhouse/validate_against_pilot.py
python src/inhouse/validate_smells_against_pilot.py
```

Cross-checks the in-house engines' output against the original pilot's
DPy/Designite ground truth (correlation for metrics, pre/post-direction
agreement for smells, since the smell *definitions* are independently
sourced, not a reproduction of DPy/Designite's closed catalogs). Useful
to re-run after any change to the analysis engines themselves, not
something that needs re-running just because the corpus grew.

### Not in the default sequence: `legacy-dpy-designite`

`src/phase0/long_analysis.py` — the original licensed DPy/Designite
driver. Hard-gated: refuses to run against more than 25 eligible rows
without `--force`, since one large snapshot can take ~29 hours under its
LOC-cap chunking. Only needed for pilot recalibration against the
licensed baseline; run it by name explicitly
(`--stages legacy-dpy-designite`) if you actually need it.

---

## Scaling the corpus

The pipeline is designed so that going from ~20 repos to 100, then 1000,
is a config change, not a rewrite:

```bash
python -m src.pipeline.run_pipeline run --target-total 100 --workers 4
```

**What actually happens when you grow `--target-total`:**

1. `select` re-derives the N-repo pick from the (fixed-size) candidate
   pool — this is fast and network-light (one Hugging Face parquet
   read).
2. `snapshot-manifest` clones every *new* repo (already-cloned ones are
   skipped) and resolves its grid. **This is the expensive step** — real
   bandwidth and disk, no `--workers` support yet, so it's currently
   sequential. At ~430MB/repo average, budget disk accordingly (100
   repos ≈ 43GB, 1000 ≈ 430GB).
3. `materialize`, `metrics`, `smells`, `entity-history` all support
   `--workers N` — this is the main lever for wall-clock time. Start low
   (4–6) on a single workstation; `git`/`dotnet` subprocess calls have
   real per-call startup cost, so more workers than that tends to fight
   over disk/CPU rather than help.

**Before pushing past 100**, two real preconditions:

- **The candidate pool.** `select` draws from a fixed 235-row file
  (`results/phase0/repos_07-21-500-pycsharp-1398_235.csv`). That's
  enough for 100 repos, not 1000 — you'll need to re-run the underlying
  candidate search (`src/phase0/PRfilter.py` → `src/repos/repo.py`) with
  wider parameters (lower star threshold, more languages) first.
- **`check_monotonic_growth()`.** `suggest_pilot()`'s stratification
  currently only iterates `["Python", "C#"]`; its "bigger n is a
  superset of smaller n" property (which the whole "grow painlessly"
  design leans on) was verified empirically against the current 235-row
  pool but isn't proven in general — re-run
  `python src/phase0/repo_pr_selection.py --verify-monotonic-growth`
  against whatever candidate pool you're about to scale with before
  trusting it, especially if you add a third language.

**Known bottlenecks that are already fixed, not open risks:**

- The `_tcc`/`_lcom` O(n²) cohesion computation (both Python and C#) is
  capped at 300 methods via seeded sampling
  (`ast_common.sample_field_sets()`) — previously confirmed to stall
  ~20 minutes on a single pathological class.
- Entity-history's per-touch git fetch is batched (`git cat-file
  --batch`, one process per file instead of one per commit) —
  previously confirmed to take 68 minutes on one high-touch entity,
  measured at a 38.7x speedup after the fix.

---

## Replicating the analysis from scratch

A full run from an empty `data/`/`results/` state:

```bash
# 0. Setup (see "Setup" above): pip install, dotnet build, GITHUB_TOKEN

# 1. Pick the corpus
python src/phase0/repo_pr_selection.py --target-total 100

# 2. Clone + resolve the Track A snapshot grid (slow, network-bound)
python src/phase0/repo_snapshot_pipeline.py --target-total 100

# 3. Sample Track B PR events (needs GITHUB_TOKEN; --dry-run first to
#    see the query-count estimate before spending real API quota)
python src/phase0/pr_sampling_pipeline.py --target-total 100 --dry-run
python src/phase0/pr_sampling_pipeline.py --target-total 100

# 4. Extract source trees for every resolved commit
python src/phase0/materialize_snapshots.py --workers 4

# 5. Run the analysis engines
python src/inhouse/pool_inhouse_metrics.py --workers 4
python src/inhouse/pool_inhouse_smells.py --workers 4
python src/inhouse/pool_entity_history.py --workers 4

# 6. Consolidate fragments into canonical pooled tables
python src/inhouse/consolidate_inhouse_metrics.py
python src/inhouse/consolidate_inhouse_smells.py

# 7. Fit the interrupted-time-series model
python src/analysis/segmented_regression.py

# 8. Generate figures/tables
python src/viz/generate_track_a_figures.py
python src/viz/generate_churn_figures.py --entity-history results/analysis/<latest-entity-history-file>.csv

# 9. (Optional) validate the in-house engines against the licensed
#    pilot baseline
python src/inhouse/validate_against_pilot.py
python src/inhouse/validate_smells_against_pilot.py
```

Or, equivalently, via the orchestrator:

```bash
python -m src.pipeline.run_pipeline run --target-total 100 --workers 4
```

(Track B / `pr_sampling_pipeline.py` isn't in the orchestrator's default
stage list yet — run it separately as step 3 above if you need it.)

Every stage is resumable — if a run is interrupted, rerunning the same
command picks up from where it left off (each stage's `--stale-check`
flag, where available, reports what it thinks is already done before you
commit to a real run).

---

## Output data reference

All real analysis output lives under `results/analysis/`, in a
consistent naming convention:

```
<MM-DD>-<tag>-<scope>.csv           the pooled/fragment output itself
<MM-DD>-<tag>-<scope>-errors.csv    per-row failures (key columns + error message)
<MM-DD>-<tag>-<scope>-progress.json live progress while a run is in flight
<MM-DD>-<tag>-<scope>.runinfo.json  schema_version bookkeeping (see below)
```

`<scope>` is a bare row/repo count for an unscoped run, or
`<repo-slug>-<count>` for a `--repo`-scoped or `--workers`-parallel
fragment. `<tag>` is one of `inhouse-metrics`, `inhouse-smells`,
`entity-history` (or `dryrun-` prefixed variants), plus
`inhouse-metrics-pooled`/`inhouse-smells-pooled` for the consolidated
tables and `segmented-regression-full-<n>` for the regression output.

**Row keys**: `(repo_id, track, target_date, commit_sha)` for
metrics/smells (one row per snapshot grid point); `(repo_id, full_name)`
for entity-history (one row per lineage, many rows per repo).

**Key columns worth knowing about**:
- `status`: `"ok"` or an error string — always check this before trusting
  a row's other values
- `tcc_sampled` / `lcom_sampled` (class-level), `n_tcc_sampled` /
  `n_lcom_sampled` (snapshot-level summary): whether the cohesion metric
  for a given class was estimated from a sample (>300 methods) rather
  than computed exactly — near-always 0/false; if you see a nonzero
  count, that snapshot has an unusually large class worth a second look

---

## Configuration and registries

Two CSV registries under `results/repos/`, both with the shape
`full_name, <reason column>, ...` — read them directly, or through
`src/common/exclusions.py` / `src/common/storage_lifecycle.py`.

**`excluded_repos.csv`** (`full_name, excluded_at, reason, scope`) — repos
excluded from analysis. `scope=permanent` means a tool can *never*
handle this repo (e.g. a project-graph load failure); `scope=per-run`
means a scale workaround expected to be retired once the underlying fix
lands. `materialize_snapshots.py` reads the permanent rows;
`pool_inhouse_metrics.py`/`pool_inhouse_smells.py` auto-apply the
per-run rows. To add one:

```python
from src.common.exclusions import record_exclusion
record_exclusion("owner/repo", "reason here", scope="per-run")
```

**`keep_cache.csv`** (`full_name` only) — repos whose
`data/repo_cache/` clone should never be pruned by
`storage_lifecycle.py`, regardless of entity-history status (e.g. a repo
you're actively debugging). See [Storage lifecycle](#storage-lifecycle).

---

## Storage lifecycle

`data/repo_cache/` (full git-history clones) grows with the corpus — at
~430MB/repo average, that's ~43GB at 100 repos. `src/common/storage_lifecycle.py`
identifies which repos are safe to reclaim (entity-history done for that
repo, not on `keep_cache.csv`) and reports or deletes them:

```bash
# Report only — never deletes anything by default
python src/common/storage_lifecycle.py

# Scope to one repo
python src/common/storage_lifecycle.py --repo crewAIInc/crewAI

# Actually delete (only after reviewing the dry-run report above)
python src/common/storage_lifecycle.py --confirm
```

This is **deliberately not wired into the automatic pipeline**. A repo's
clone may be needed again even after entity-history is "done" for it
today — the manifest could later be regenerated with a wider date grid,
or `--max-files-per-repo` raised for a fuller entity-history pass.
Pruning is a manual, deliberate action you take when *you* decide a repo
is truly done, not something that happens as a side effect of running
the pipeline.

---

## Known limitations and troubleshooting

**The resumability "instant resume" footgun.** Every batch stage treats
*any* prior output file matching its tag as already-done (this is
intentional — it's what lets parallel `--repo`-scoped runs share
progress). A `schema_version` check (`src/common/resumable_run.py`)
guards against a bug-fix silently being masked by stale pre-fix output,
but only for files produced after that tracking existed. If a run seems
to finish suspiciously fast with "0 rows processed," run `--stale-check`
first — it reports exactly how many done-keys it's trusting, from how
many files, oldest/newest.

**Windows path limitations.** A small number of repos have historical
commits containing filenames Windows can't materialize (quote characters,
paths exceeding `MAX_PATH`) — `materialize_snapshots.py` reports these as
`[archive] ... failed or timed out` per-commit and continues; they're
environmental, not pipeline bugs, and don't block the rest of the run.

**GitHub API rate limits.** Track B (`pr_sampling_pipeline.py`) needs
`GITHUB_TOKEN` — unauthenticated access is 60 req/hour. The Search API
specifically caps at 30 req/min per token regardless of your core-API
limit; see `GITHUB_TOKENS_FILE` above for spreading load across multiple
tokens. Some GitHub orgs (e.g. `dotnet`) block fine-grained PATs from
their repos entirely at the org level — this shows up as a 401 even with
a valid token, and is why `dotnet/aspire` is in the permanent exclusion
registry.

**The legacy DPy/Designite path is intentionally hard to invoke at
scale.** If you need it for pilot recalibration, pass `--force` and
expect multi-hour-to-multi-day runtimes for anything beyond a handful of
repos — this is not a bug, it's the reason the in-house engines exist.

**No formal test suite.** Correctness is established by hand-validation
against known-good numbers (see each tool's own build-log entry in
`Writing/ProjectUpdate.md`) and direct comparison against the licensed
pilot baseline (`validate_against_pilot.py`/`validate_smells_against_pilot.py`),
not pytest. If you're modifying an analysis engine, follow that same
pattern — construct a small case with a hand-computable expected answer
before trusting it on real data.

---

## Where to find the findings

This README is about running the pipeline. For the actual research:

- **`Writing/ProjectStatus.md`** — current status, start here
- **`Writing/Results.md`** — findings, tables, figures, dashboard link
- **`Writing/Longitudinal.md`** — full methodology (the four sampling
  tracks, staleness handling, intervention-date derivation)
- **`Writing/ProjectUpdate.md`** — the raw, append-only chronological
  build log (every methodology decision, bug, and blocker, kept verbatim
  even where it turned out to be a dead end — the methodology record)
- **`Writing/InHouseTooling.md`** — design rationale for the in-house
  metrics/smells engines and the pipeline-scaling infrastructure
  (concurrency, cohesion sampling, git batching, storage lifecycle)
- **`Writing/PySmellDetection.md`** / **`Writing/RQ3_CodeTracking.md`** —
  deep design docs for the smell-detection and entity-tracking
  subsystems specifically
