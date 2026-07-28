# Project Update — 2026-07-21

## Where things stand

The goal: measure repository structural health before vs. after AI coding
agents start contributing, using DPy/Designite smells and OO metrics as the
outcome, on a small set of pilot repos before scaling up. Phase 0 (data
filtering) is iterating in parallel; the longitudinal methodology is designed
and its data-collection pipeline is built and has run end-to-end for 5 pilot
repos. Nothing has been analyzed yet — this update is about the pipeline, not
results.

## Phase 0 — data filtering (`src/phase0/`, `src/repos/`)

- **`PRfilter.py`** filters the AIDev PR dataset by stars, language, rejection
  state, English titles, non-empty bodies, and (newest addition)
  `require_live_url` — drops PRs whose GitHub page now 404s (repo deleted,
  made private, or renamed since AIDev was scraped), checked via concurrent
  HTTP HEAD requests. 
- **`repo.py`** dedupes a PR-id list down to its unique repos. **`phase1.py`** joins a PR-id list back to AIDev for PR
metadata (title, body, agent, dates). Both scripts' default inputs were
  reconciled today to point at the same PR-id list after they'd drifted apart.
- **`metrics.py`** is still a stub (Phase 1.5) — column names and descriptions
  are sketched but not implemented.

## Longitudinal study methodology (`Writing/Longitudinal.md`)

Designed as an **interrupted time series**, not a naive before/after
snapshot, so ordinary codebase drift doesn't get mistaken for an agent effect.

- the AIDev dataset (`all_pull_request.parquet`)
  contains only agent-authored PRs and only spans 2024-12-24 to 2025-07-30 —
  it can't supply a pre-agent baseline or anything outside that ~7-month
  window. It's used only to find each repo's *intervention point* (its
  earliest agent-authored PR); everything else needs a fresh git/GitHub pull.
- **Four sampling tracks**, split by what's sampled (repo source tree vs. PR
  events) × how it's anchored (fixed calendar window vs. centered on each
  repo's own intervention point):
  - **A1** — monthly repo snapshot, fixed 2022-01-01–2026-03-31 grid (51 pts)
  - **A2** — repo snapshot centered on intervention date (weekly ±3mo, monthly
    to ±12mo — 45 pts), for a precise read on the discontinuity itself
  - **B1** — PR sampling, monthly 2-day window, fixed grid (up to 510 PRs/repo)
  - **B2** — PR sampling, ±10 PRs immediately around the intervention PR
- Every A1/A2 snapshot carries a **staleness** flag (`commit_date`,
  `staleness_days`, `is_stale` at >45 days, `no_prior_commit`) so a quiet
  repo-month doesn't silently masquerade as fresh data.
- Full decision log, open questions, and rationale live in the doc itself.

## Phase 1a — repo & PR picking (built, done)

`src/phase0/repo_pr_selection.py` takes the candidate repo list, pulls AIDev's
agent PRs for those repos, flags each repo's intervention PR, and builds a
per-repo summary (agent PR count, dosage by agent, intervention date). Output:
`results/repos/07-21-aidev-agent-prs-3332.csv` and
`07-21-repo-summary-235.csv`. From this, suggested (and proceeded with) a
5-repo pilot, stratified by language:

| repo | language | agent PRs | intervention date |
|---|---|---|---|
| crewAIInc/crewAI | Python | 327 | 2024-12-27 |
| airbytehq/airbyte | Python | 218 | 2025-01-21 |
| mlflow/mlflow | Python | 91 | 2025-05-21 |
| wieslawsoltes/Dock | C# | 309 | 2025-06-25 |
| dotnet/aspire | C# | 169 | 2025-05-19 |

## Phase 1c — repo-snapshot pipeline (built, done)

`src/phase0/repo_snapshot_pipeline.py` resolves Tracks A1/A2 into an actual
manifest for the 5 pilot repos: partial (`--filter=blob:none`) git clones into
`data/repo_cache/` (gitignored), then `git log --until` per grid point to find
the nearest commit and its staleness. Hit and fixed a Windows-specific
`Filename too long` failure on `airbyte`/`aspire` (deep test-fixture paths past
the 260-char path limit) with `-c core.longpaths=true`, scoped to the clone
command rather than a persisted config change.

**Result:** all 5 repos cloned (2.8 GB total), 480 snapshot rows in
`results/snapshots/07-21-repo-snapshot-manifest-480.csv` — 4 stale points (all
Dock, Track A1, far from its intervention date), 43 `no_prior_commit` points
(crewAI + aspire, both young enough that early-2022 grid points predate their
first commit — expected, not a bug).

## Phase 1e — snapshot materialization (built, done)

`src/phase0/materialize_snapshots.py` turns the Phase 1c manifest's commit
resolutions into actual source trees DPy/Designite can run against: for every
*unique* `(repo, commit_sha)` (401 of them across the 5 repos, not 480 — many
grid points share a commit), it does a one-time per-repo blob backfill
(`git sparse-checkout` + `git backfill --sparse`, HTTP/1.1 forced — HTTP/2
was resetting mid-transfer in this environment) and then a language-filtered
`git archive` (just `*.py` or `*.cs`, matching the repo) into
`data/snapshots/<owner>__<repo>/<commit_sha>/`. Resumable by design.

**Result:** 399 of 401 unique commits materialized. The 2 that never
materialize (both crewAI) hit a permanent Windows filesystem incompatibility
— a test fixture path containing a `"` character, illegal in NTFS filenames
— not a transient failure; would need a Linux/WSL environment to fill in.

## Phase 1d — DPy/Designite orchestration (built, blocked on tool install)

`src/phase0/long_analysis.py` reads the Phase 1c manifest, drops
`no_prior_commit` rows, and for each remaining row looks up its
already-materialized source tree from Phase 1e
(`data/snapshots/<owner>__<repo>/<commit_sha>/`), routes to DPy (Python) or
Designite (C#) by the row's `language`, and writes a consolidated
smell/metric CSV plus a separate errors CSV so one bad row can't abort the
run. Neither tool is actually installed (no `dpy`/`designite`/even `java` on
this machine, and both are commercial products from designite-tools.com
whose real CLI and output schema aren't verified) — `run_dpy()` /
`run_designite()` / `parse_tool_output()` are stubs marked `TODO`, gated
behind `DPY_EXECUTABLE`/`DESIGNITE_EXECUTABLE` env vars, ready to fill in
once the tools are installed. Added `--dry-run` (snapshot lookup +
bookkeeping only, no tool call) and `--repo`/`--limit` filters so the
orchestration itself can be smoke-tested without the tools.

First version of this script did its own `git checkout` per row directly in
the Phase 1c clone cache instead of reading Phase 1e's output — built before
noticing Phase 1e already existed and already solved exactly the problem
that approach then hit (a slow lazy blob-fetch on `airbyte`'s partial clone
timed out and left that cached clone in a half-updated state). Rewritten to
consume `data/snapshots/` directly, per the design already recorded in
`Longitudinal.md` §7–§8.

**Result:** full `--dry-run` across all 5 repos resolves 435/437 eligible
rows instantly (no network, no checkout — just a directory lookup), with the
2 failures being exactly the 2 known-unmaterialized crewAI commits, cleanly
logged to the errors CSV rather than crashing.

**Update 2026-07-27 — tools installed, two new concrete blockers found.**
Both `DPy.exe` and `DesigniteConsole.exe` are now installed
(`C:\Users\kvrlv\Downloads\`), so `run_dpy()`'s CLI is confirmed for real
(`DPy.exe analyze -i <dir> -o <dir> -f csv`) and wired in. Testing against
real data surfaced two separate problems, neither of them code bugs:
- **DPy**: the installed license is Trial, capped at <10,000 LOC for CSV
  export. Every pilot snapshot is far over that (smallest is ~60K LOC), so
  DPy currently only writes a log file, not data, against any of them —
  confirmed by running it against a real `mlflow` snapshot (271K LOC) and a
  tiny synthetic file (which *did* export real CSVs, confirming the schema
  — see `parse_tool_output()`'s docstring). Needs a Professional license.
- **Designite**: `-i`/`--input` requires an actual `.sln` (it's a Roslyn
  `MSBuildWorkspace` tool, not a plain file scanner) — confirmed by pointing
  it directly at a materialized Dock snapshot and getting `Argument error!!
  The specified file doesn't exists`. Phase 1e's snapshots only contain
  `*.cs` files (see `materialize_snapshots.py`'s language pathspec), no
  project/solution files, so there's currently nothing to point it at. Also:
  no .NET SDK is installed, only runtimes, which `MSBuildWorkspace` may need
  even once a `.sln` exists. `run_designite()` now raises a clear
  `NotImplementedError` explaining this rather than attempting a call known
  to fail.

**Update 2026-07-27 (continued) — DPy chunking wrapper.** Decompiled
`DesigniteConsole.dll`'s strings first (`InterpretBatchFile`,
`GetAllSolutionPaths`, `IsSolutionFile`, `OpenSolutionAsync`) to check
whether its `--help`-mentioned "batch file" input mode was a way around the
`.sln` requirement — it isn't; a batch file is just a text file listing
multiple `.sln` paths, so every code path still needs a real solution file.
Designite stays parked (per decision — focus on DPy/Python first).

For DPy, tested whether the Trial LOC cap is per-repo or per-invocation by
pointing it at a small (~3K LOC) `mlflow` subdirectory: it exported full,
real CSVs, confirming the cap is per-invocation — and along the way gave the
confirmed schema for 2 more DPy output files (`_arch_smells.csv`,
`_design_smells.csv`) that hadn't shown up in the earlier near-empty test.
Built `plan_dpy_chunks()`/`run_dpy_chunked()` in `long_analysis.py`: splits
a snapshot into sub-cap chunks along real directory boundaries (falling back
to bin-packing loose files by LOC when a directory is flat with no
subdirectories left to split by — needed for real, e.g. `mlflow/utils` has
57 loose files with no children), runs DPy once per chunk, and pools results
in `parse_tool_output()`. Per the decision above: class/method-level metrics
and design/implementation smells are pooled across chunks since they're
local regardless of scope; architecture-level smells and Fan-In/Fan-Out are
collected but kept explicitly chunk-scoped (not folded into the primary
metric row), since a chunk never sees the whole repo and computing "God
component"/coupling from an arbitrary slice would misrepresent the real
codebase.

Validated the chunker in isolation against the real `mlflow` snapshot
(465K raw lines by my count, 1,902 files) before spending any DPy runtime:
first pass produced 291 chunks with 10 still over cap (flat directories with
many loose files, e.g. `mlflow/utils`'s 57 files/17K LOC) — traced to the
bin-packing step calling the wrong LOC-counting function (a directory-recursive
counter given a single file, silently returning 0, so every file landed in
one batch); fixed, re-validated: 304 chunks, zero overlaps, all 1,902 files
covered exactly once, only 1 residual oversized chunk (a single file whose
own LOC exceeds the cap — expected, nothing left to split it by).

**Real-world cost, measured, not estimated:** timed one DPy invocation at
~3.4s. 304 chunks/snapshot × 96 materialized `mlflow` snapshots ≈ **29 hours**
of DPy runtime for that one repo alone — a full run across all 3 Python
pilot repos is realistically multi-day as currently scoped.

**Result — real end-to-end test:** ran the full pipeline (not `--dry-run`)
against one real `mlflow` snapshot (2022-01-01, an early/smaller commit —
70,274 LOC, 81 chunks). Produced a single, well-formed pooled output row:
318 classes, 5,160 methods, class LOC p50/p90 = 23/113, method LOC p50/p90 =
9/27, cyclomatic complexity p50/p90 = 1/3, 1,339 design smells (19.1/KLOC),
6,465 implementation smells (92.0/KLOC), and 25 architecture smells correctly
kept in a separate `arch_smell_count_chunk_scoped` column rather than pooled
into the primary row. Confirms the chunking/pooling design works correctly
on real data. Test row and raw per-chunk CSVs deleted afterward (proof of
correctness, not meant as a kept deliverable).

**Decision 2026-07-27:** accept the multi-day cost — run the full manifest
now as a long background job rather than tuning scope first.

Before launching, made the pipeline crash-resilient (a multi-day unattended
run needs this regardless of background/foreground):
- **Incremental writes.** `main()` previously only wrote output once, at the
  very end — a crash at hour 20 would have lost everything. Now appends
  each row's result to the output CSV immediately as it completes.
- **Resumable.** On start, reads whatever's already in that run's output CSV
  and skips those `(repo_id, track, target_date, commit_sha)` keys — a
  restart after a crash picks up where it left off instead of redoing
  potentially hours of already-done DPy work. Errored rows are retried, not
  skipped, since some failures (a timeout, a transient lock) aren't
  guaranteed to repeat.
- **Chunk-output cleanup.** A full run touches hundreds of chunks per row
  across hundreds of rows — left alone, raw per-chunk CSVs in
  `data/tool_output/` would reach into the hundreds of thousands of small
  files. Each row's raw output is now deleted once pooled into the result
  (`--keep-tool-output` to disable, for debugging a specific row).

### 🔴 RUN IN PROGRESS — started 2026-07-27, now running as 3 parallel workers

**History (chronological):**
1. **Silent death + a date-rollover resume bug (2026-07-28 AM).** Original
   process (PID 32412) died after 48/437 rows with no exception logged
   (most likely killed externally — sleep/reboot/logout). Restarting it
   exposed a real bug: `main()` stamped the output filename with
   `date.today()`, so restarting on a new calendar day couldn't find
   yesterday's file and was about to silently redo all 48 rows. Caught
   before any rows were reprocessed; fixed by having `main()` find its
   output file by scope (tag + total/repo) regardless of date prefix.
2. **Verbosity added.** A row is 100-390+ DPy chunks at ~2-3s each — could
   run 15-20+ min with zero output. Added `--verbose`: per-chunk
   index/total/LOC/timing/ETA, a `[row] starting ...` marker, and DPy
   subprocess failures now surface their real stdout/stderr instead of a
   generic "exited 1".
3. **Parallelized across 3 workers, then a Smart App Control incident.**
   32 logical cores, ~9% utilization — an obvious candidate to speed up.
   Made resume/dedup **global** (`_load_done_keys` now scans *every*
   `results/analysis/*-smell-metrics-*.csv`, not just the current process's
   own file) and gave each `--repo`-scoped process its own output filename,
   so concurrent workers can never race on the same file or redo each
   other's work. Verified with a real concurrent test (two scoped dry-runs
   launched at the same instant) before trusting it. Partitioned the 437
   rows 3 ways with zero overlap (verified against the manifest):
   `--repo "airbyte|Dock"` (192), `--repo crewAI` (74),
   `--repo "mlflow|aspire"` (171). **First launch failed almost
   immediately** — every row errored with `[WinError 4551] An Application
   Control policy has blocked this file`. Root cause (confirmed via
   `Microsoft-Windows-CodeIntegrity/Operational` event log, IDs
   3118/3077/3033): **Windows Smart App Control**, not a code bug — 3
   concurrent launches of an unsigned executable (`DPy.exe`) in rapid
   succession read as malicious to its reputation heuristics, and it
   escalated from occasionally flagging the file (2 sporadic failures
   during the sequential run) to blocking it outright, confirmed by a
   direct manual invocation returning `Permission denied` completely
   outside my script. Reducing back to a single process didn't help — the
   block was on the file, not on concurrency. Stopped everything rather
   than keep guessing; user turned Smart App Control off directly (an
   OS-level setting I did not and would not touch myself — per Microsoft,
   once it's on it's only reversible by resetting/reinstalling Windows).
4. **Resumed, with error-cleanup added.** `DPy.exe version` confirmed
   working again post-fix. Added `_clear_stale_errors()`: when a row
   succeeds, it now removes any matching stale error record from *every*
   errors CSV for that tag (not just the current process's own), so a
   resolved failure (like the ~194 `WinError 4551` rows from the SAC
   incident) doesn't linger looking unresolved once retried successfully.
   Verified in isolation before trusting it on real data, then confirmed on
   the real retry: the crewAI errors file dropped from 60 → 51 entries as
   retried rows succeeded, while the 2 permanent crewAI filename-gap errors
   (§8, won't ever succeed) correctly stayed put.

**Currently running**, 3 parallel processes, `--verbose` on, `DPY_EXECUTABLE`
set to `DPy.exe`:

- `--repo "airbyte|Dock"` → `results/analysis/07-28-smell-metrics-airbyteDock-192*`
- `--repo crewAI` → `results/analysis/07-28-smell-metrics-crewAI-74*`
- `--repo "mlflow|aspire"` → `results/analysis/07-28-smell-metrics-mlflowaspire-171*`

Plus the original unscoped file (`07-27-smell-metrics-437*`, 52/437 done)
which is no longer being added to but still counts toward the global
done-set.

- **PIDs:** `logs/phase0/long_analysis.pid` (comma-separated, one per
  worker).
- **Live logs:** `logs/phase0/long_analysis_{airbyte,crewai,mlflow}.log`
  (+ matching `.err.log`, should stay empty) — one per worker, each showing
  its own per-chunk verbose progress.
- **Progress:** each output's own `*-progress.json`.
- **If a worker crashes:** rerun that exact same command (e.g.
  `python long_analysis.py --verbose --repo crewAI`) — resumes automatically,
  same as the single-process case.
- **Known non-blocking errors:** ~75 `dotnet/aspire` rows fail fast with
  `DESIGNITE_EXECUTABLE not set` (expected — Designite work is deliberately
  deferred to the `designite-sln-support` branch) and 2 `crewAI` rows will
  never succeed (permanent Windows filename incompatibility, §8).

## Visualization

Built an interactive timeline (published as a Claude artifact) showing every
A1/A2 sample point per repo on a shared calendar axis, plus zoomed per-repo
panels resolving the weekly ±3-month window around each intervention point.
Surfaced one methodological wrinkle along the way: Dock's A2 window runs to
2026-06-25, past the study's nominal 2026-03-31 end, since Track A2 extends
±12 months from each repo's *own* intervention date regardless of the overall
window boundary.

https://claude.ai/code/artifact/e0731c42-8ff8-4b57-b797-21fdda5fd013

## Open items / blocked

- **Phase 1b** (full PR history pull, Track B) — needs `GITHUB_TOKEN`; not yet
  set in this environment. Unauthenticated is 60 req/hr, not viable at scale.
- **Phase 1d** — both tools now installed, but neither can produce real
  output yet: DPy's Trial license caps CSV export at <10K LOC (need
  Professional); Designite needs an actual `.sln` and Phase 1e snapshots
  only contain `*.cs` files (needs a design decision — see Phase 1d above).
- 2 crewAI commits (Phase 1e) will likely never materialize on Windows
  (NTFS-illegal filename in a test fixture) — accept the gap or find a
  Linux/WSL environment to fill it in.
- Open modeling decisions logged in `Longitudinal.md`: A2's weekly/monthly
  windowing and B2's ±10-PR window are defaults, not confirmed; no minimum-
  snapshot-count rule yet for excluding a repo from the regression; whether
  informal (pre-AIDev) agent adoption needs a separate robustness check.

