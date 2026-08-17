# Project Update — 2026-07-21

> **Start with `ProjectStatus.md` and `Results.md`
> instead.** This file is the raw, append-only, chronological build log —
> every methodology decision, bug, and blocker below is real and kept
> verbatim even where it turned out to be a dead end, because it's part of
> the thesis's methodology record. But the concrete *numbers* in the
> "First real analysis" sections below are an **N=4 pilot**, explicitly
> preliminary and superseded once Phase 2's larger sample lands — see the
> 2026-08-04 entry at the end of this file, and `Results.md`'s banner, for
> current status.

## Where things stand

The goal: measure repository structural health before vs. after AI coding
agents start contributing, using DPy/Designite smells and OO metrics as the
outcome, plus PR-level process metrics, on a small set of pilot repos before
scaling up. Phase 0 (data filtering) is iterating in parallel; the
longitudinal methodology is designed and both data-collection pipelines —
Track A (repo snapshots) and Track B (PR sampling) — have run end-to-end for
the 5-repo pilot. Real DPy output is now landing for Track A (3 parallel
workers in progress, see Phase 1d); Track B1/B2 PR sampling is done except
for `dotnet/aspire`, excluded for now (see Phase 1b). Nothing has been
formally analyzed yet — this update is still about the pipelines producing
real data, not conclusions drawn from it.

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

**Live status, 2026-07-28 ~15:00 UTC (all 3 workers still running):**
`crewAI` worker finished — 75/74 rows recorded (the global dedup counts one
row shared with the original unscoped file, harmless, not an overcount of
real work). `airbyte|Dock` at 51/192. `mlflow|aspire` at 131/171 (56 ok, 75
failed — exactly the expected `dotnet/aspire` Designite-not-configured rows
draining as designed, per the known non-blocking errors above).

**Update 2026-07-29 — DPy run finished.** All 3 workers completed
overnight: 264 unique ok rows across crewAI (72/74, the 2 permanent NTFS
gaps from §8 are the only misses), airbyte (96/96), and mlflow (96/96, the
last ~2 rows closed out without any manual intervention — resumability held
under an unattended multi-day run same as designed). Designite/Dock rows
(96 of them) still fail fast with `DESIGNITE_EXECUTABLE not set` in this
checkout — that's expected, Designite work happened on a separate branch,
see immediately below.

**Update 2026-07-29 — Designite unblocked on `designite-sln-support`,
Dock has real data.** In parallel, on the `designite-sln-support` worktree
(`C:\Users\kvrlv\Projects\Codebook_AIDev-designite`), `run_designite()` /
`parse_tool_output()` went from stub to working end-to-end against real
`wieslawsoltes/Dock` commits. Full details, decisions, and the open-items
list are in that branch's `DESIGNITE_TASK.md` — condensed version:
- **.NET SDK 8.0.423 installed** (this machine had runtimes only before);
  Phase 1e's C# pathspec extended from `*.cs`-only to also pull
  `*.sln`/`*.slnx`/`*.csproj`/`*.props`/`*.targets`/`packages.config`, so
  Designite's Roslyn `MSBuildWorkspace` has an actual project graph to open.
- **Designite's Trial cap confirmed at <50,000 LOC/invocation** (stated
  directly in the tool's own output, unlike DPy's cap which had to be
  bisected empirically) — same chunking approach as DPy, bin-packing whole
  `.sln` projects (not splitting a project's files) into sub-cap groups.
- **Full batch run across Dock's 96 manifest rows: 87 ok, 9 failed** — the 9
  failures are all Dock commits dated 2025-12-25 or later, when
  `Dock.sln` → `Dock.slnx` (the installed Designite build, 5.3.0.0, doesn't
  support the newer `.slnx` format at all). Output:
  `results/analysis/07-28-smell-metrics-96.csv` (that branch's own results
  dir, not this checkout's).
- **`dotnet/aspire` dropped from the C# arm entirely**, not just Track B —
  two different, unrelated blockers depending on era (early commits: Arcade
  bootstrap needs its own restore flow, every project reports 0 source
  files; recent commits: `.slnx` + a preview SDK not installed) and no clean
  middle band was found. This pilot's C# side is now Dock-only across
  *both* Track A and Track B, not just Track B as reported 2026-07-28.
- **Two generalizable bugs found and fixed** in `archive_commit()` while
  extending the pathspec: `git archive` hard-fails if any pathspec pattern
  matches zero files in that commit (unlike `ls-tree`) — fixed by
  pre-filtering to patterns that actually match something; and that filter
  itself first checked basenames when git's own literal-pathspec matching is
  full-relative-path, caught on aspire's `eng/common/sdl/packages.config`.
- Designite's schema was pooled onto the **same canonical column names**
  DPy already uses (`design_smell_density_per_kloc`, `cyclomatic_complexity_p90`,
  etc.) — turns out no cross-language adapter step was needed after all
  (this corrects the "Assumption 1" concern raised in `Results.md`'s
  2026-07-28 planning section).
- Known unresolved gaps on that branch: multi-targeted C# projects aren't
  deduplicated (each target framework variant currently double-counts), and
  `total_loc` undercounts Designite's own reported LOC by ~18-21% (same
  category of imprecision as DPy's own LOC proxy, not investigated further).

**Update 2026-07-29 — first real analysis run.** With DPy complete and
Designite's Dock output in hand, ran the analysis pre-registered in
`Longitudinal.md` §9 for the first time — segmented (interrupted-time-series)
regression per repo per primary metric, smell-composition shift, and
Track B process metrics (Mann-Whitney U + Cliff's δ), plus a first look at
cross-language generalization and dosage. Full writeup, tables, and an
interactive visualization dashboard: see the new "First real analysis —
pilot results (2026-07-29)" section in `Results.md`. Headline: no consistent
cross-repo direction — design-smell density shows a significant post-
intervention slope change in all 4 repos (p<.05), but it's worse in 2 and
better in 2, and that split doesn't track language (Dock lands with mlflow
on the "improving" side). N=4 repos — descriptive of these repos, not yet a
general claim. Consolidated data and every intermediate table are in
`results/analysis/07-29-*.csv`.

## Phase 1b — Track B1/B2 PR sampling (built, run)

`src/phase0/pr_sampling_pipeline.py`: the GitHub-API counterpart to Phase
1c/1e — resolves Tracks B1/B2 (`Longitudinal.md` §5) into actual PR-event
data for the 5-repo pilot via the Search API
(`GET /search/issues?q=repo:...+is:pr+created:...`), since AIDev has no PR
data outside Dec 2024–Jul 2025.

- **B1**: one 2-day window (day 1–2 UTC) per calendar month across the
  51-month grid, up to 10 PRs/window by `created_at` (cap 510/repo). Months
  with fewer than 10 PRs keep whatever's available, flagged `is_undersampled`
  rather than excluded or padded.
- **B2**: the 10 PRs immediately preceding and 10 immediately following each
  repo's intervention PR, not calendar-anchored.
- Captures PR identity + timestamps (number, title, state,
  `created_at`/`closed_at`/`merged_at`, comment count, URL) straight from the
  Search API response — not yet the deeper diff/review stats
  (additions/deletions/review comments), which need a per-PR follow-up call
  and are left for a later step, same phased split as Phase 1c → Phase 1e
  for Track A.

**Resumable and verbose by design**, mirroring `long_analysis.py`'s Phase 1d
approach but adapted to a wrinkle specific to this data: a search query can
legitimately return zero PRs (a quiet repo-month), so PR rows alone can't
signal "already queried" the way manifest rows can. A separate *query
ledger* CSV (`*-queries.csv`) records every unit's outcome (one row per B1
month-window or B2 side — `status=ok/error`, PR count found,
`is_undersampled`) the moment it completes; resume skips anything already
`ok` there, and every unit prints a live terminal line (`[ok] (i/265) repo
track unit -> N PRs | M PRs so far | eta`). Verified for real, not just in
theory: killed a live run mid-flight (`wieslawsoltes/Dock`, Track B1, 10/51
windows done) and confirmed the rerun printed `resuming: 10/51 already done`
and picked up exactly at window 11.

**Environment setup hit the same underlying cause as the Phase 1d Smart App
Control incident above, discovered independently.** Needed `GITHUB_TOKEN`
(unauthenticated GitHub API is 60 req/hr) and a proper venv with
`requirements.txt` installed rather than a raw `pip install` into the active
conda `base`. The first `pip install -r requirements.txt` into a fresh venv
(built from conda's `python`) downloaded new pandas/pyarrow wheels that
Smart App Control immediately blocked
(`ImportError: DLL load failed... An Application Control policy has blocked
this file`) — the same enforcement that separately blocked `DPy.exe` during
the 3-worker launch above; the two incidents were only connected after the
fact. Fix: rebuilt the venv from `C:\Python314\python.exe` (whose packages
were already installed and already trusted) with `--system-site-packages`,
so `pip install` resolved everything as already-satisfied instead of
downloading new binaries. Hit a secondary snag getting there: deleting the
broken venv kept failing (`Access denied` on `.venv\Scripts\python.exe`)
because VS Code's Python extension had auto-selected it as the workspace
interpreter and kept relaunching its language server against it, re-locking
the file every time it was killed — resolved by closing/reloading VS Code,
not by repeatedly killing the process. `.venv/` added to `.gitignore`.

**Full run result:** 265/265 query units attempted across the 5-repo pilot
(51 B1 windows + 2 B2 sides × 5 repos) — **212 ok, 53 failed**. Every single
failure is `dotnet/aspire`, and only `dotnet/aspire` (100% of its 53 units;
0% everywhere else). Root cause confirmed directly: unauthenticated
`GET /repos/dotnet/aspire` returns `200`, but the same call with our
(fine-grained) token returns `401`, and the Search API returns `422`
(`"...do not have permission to view them"`). **Microsoft's `dotnet` GitHub
org blocks fine-grained personal access tokens from its repos entirely, even
public ones** — an org-level opt-in policy, unrelated to the Smart App
Control incident above despite the superficially similar "one thing
completely blocked" shape. Track A (Phase 1c/1e) already has full
`dotnet/aspire` data since it only ever used local git clones, not this API
— only Track B is affected.

**Decision (2026-07-28):** don't retry/collect `dotnet/aspire` PRs for now —
treat `wieslawsoltes/Dock` as the sole C# repo for Track B1/B2. This breaks
the pilot's original Python/C# stratified balance for this track
specifically (now 3 Python + 1 C#, not 3+2). Needs a methodology call before
Phase 1b is considered complete: get a classic PAT (not subject to this org
restriction), swap in a different C# pilot repo, or accept Dock-only and
disclose the imbalance in the write-up.

**Output:** `results/pr_samples/07-28-pr-sample-265.csv` (PR rows),
`-queries.csv` (resume ledger), `-progress.json`.

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

**Updated 2026-07-29** — both structural-metric tracks (DPy for Python,
Designite for Dock) are now complete and a first analysis has run; see
`Results.md`'s "First real analysis" section and the dashboard linked there.
What's still actually open:

- **`dotnet/aspire` is now dropped from the pilot entirely**, not just
  Track B — Designite work (`designite-sln-support` branch,
  `DESIGNITE_TASK.md`) found two separate blockers across its history (early
  Arcade-bootstrap commits, recent `.slnx`+preview-SDK commits) with no
  clean middle band, so the C# arm is Dock-only on *both* Track A and Track
  B now. This pilot is 3 Python + 1 C#, not 3+2 — needs a methodology call
  before it's called final: accept Dock-only and disclose, or find/onboard
  a second C# pilot repo that doesn't hit either of aspire's blockers.
- **Dock's post-intervention structural data is thin** — Designite can't
  read `.slnx` (Dock migrated 2025-12-25, 6 months after its own
  intervention date), so only 6 of Dock's ~19 possible post-intervention A1
  points have real data. A newer Designite build with `.slnx` support, or a
  `.slnx`→`.sln` conversion step, would recover the rest.
- **Designite's `designite-sln-support` branch hasn't been merged to
  `main`** — its output currently lives in a separate worktree
  (`Codebook_AIDev-designite`) and had to be read cross-checkout for the
  2026-07-29 analysis. Worth merging so Dock's data lives alongside the
  Python output in one place going forward.
- **Track B's deeper PR stats** (diff size, review-activity detail beyond
  comment count) still aren't built — flagged as a gap since 2026-07-21,
  still true.
- **No matched non-adopting comparison arm** — everything run so far is
  ITS, not difference-in-differences (`Longitudinal.md` §9).
- 2 crewAI commits (Phase 1e) will likely never materialize on Windows
  (NTFS-illegal filename in a test fixture) — accept the gap or find a
  Linux/WSL environment to fill it in.
- Open modeling decisions logged in `Longitudinal.md`: A2's weekly/monthly
  windowing and B2's ±10-PR window are defaults, not confirmed; no minimum-
  snapshot-count rule yet for excluding a repo from the regression; whether
  informal (pre-AIDev) agent adoption needs a separate robustness check;
  the 2026-07-29 analysis ran 12 unadjusted significance tests for RQ1
  alone — needs a multiple-comparison correction before anything here is
  paper-ready.

## 2026-08-04 — Designite branch merged; Phase 2 (20-repo) kickoff, DPy/Designite analysis deferred for new repos

**Merge.** `designite-sln-support` (the worktree at
`C:\Users\kvrlv\Projects\Codebook_AIDev-designite`, used to build the
Designite/`.sln` support in parallel without touching the concurrent
multi-day DPy background job on `main`) is merged into `main`. That job
finished 2026-07-29, so the reason for the separate worktree no longer
applies. The merge itself was cleaner than expected — `long_analysis.py`
auto-merged with no conflicts despite both branches editing it heavily
(DPy's chunking/resumability/parallel-worker logic on `main`, Designite's
`run_designite()`/`parse_tool_output()` on the branch); the only real
conflict was `.gitignore`. Brought over: `DESIGNITE_TASK.md` (full decision
log), `Writing/DockDesigniteReport.md` + its figures/chart data (committed
to the branch as part of this merge — they were sitting untracked),
`src/phase0/analyze_dock_designite.py`, `EXCLUDED_REPOS` (drops
`dotnet/aspire`), the extended C# `LANGUAGE_PATHSPEC`
(`*.cs`/`*.sln`/`*.slnx`/`*.csproj`/`*.props`/`*.targets`/`packages.config`),
and Dock's real Designite output
(`results/analysis/07-28-smell-metrics-96*.csv`, 87/96 rows ok). Verified
post-merge: both `long_analysis.py` and `materialize_snapshots.py` import
cleanly, `EXCLUDED_REPOS`/`LANGUAGE_PATHSPEC` resolved correctly, and a
`--dry-run --limit 5` against the existing 480-row manifest still resolves
snapshots correctly.

**Repo hygiene, done alongside the merge, not separately requested but
flagged here rather than done silently:** stopped tracking `__pycache__/*.pyc`
(6 compiled files) and the raw multi-day DPy run logs under `logs/`
(~50K+ lines across the airbyte/crewai/mlflow logs) — both categories
stay on disk, just untracked going forward; `.gitignore` gained
`data/archive/`, `__pycache__/`, and `logs/`.

**Push blocked.** `git push origin main` failed —
`Authentication failed for 'https://github.com/karlita604/Codebook_AIDev.git/'`
(stored credential rejected, not a code issue). Merge commit exists locally
(3 commits ahead of `origin/main` at merge time); needs a re-auth
(`gh auth login` or refreshed credential manager) before it reaches GitHub.

**Phase 2 kickoff — scope decision.** The pilot's 4 repos are well short of
the thesis's minimum-20-repo target. Given DPy/Designite's Trial-license LOC
caps made even the 4-repo pilot expensive (mlflow alone: ~29 hours of DPy
runtime from LOC-cap chunking into hundreds of small invocations, per the
2026-07-27 entry above), running that same tool pipeline against ~16 more
repos at pilot density was estimated at 2-4+ weeks of background compute —
and the project is moving toward building an in-house metrics tool
specifically to remove that LOC cap (see the new `Writing/InHouseTooling.md`,
added today). Decision: for Phase 2, collect PR samples (Track B) and raw
materialized source-tree snapshots (Track A) for the new repos using the
existing, already-parameterized (`--pilot-size`) Phase 1a/1b/1c/1e pipeline —
but **do not run Phase 1d (DPy/Designite) against them yet**. This is a
deliberate deferral, not a gap: the new repos' snapshots sit ready in
`data/snapshots/` for the in-house tool once it exists, without ever having
been forced through the trial LOC-cap chunking machinery built for
DPy/Designite specifically.

Also added `Writing/RQ3_CodeTracking.md` today — a research brainstorm for
RQ3 (tracking a specific code entity's lifetime/aging across a repo's
history), independent of the Phase 2 work above but requested alongside it.

Real Phase 2 collection outcomes (which repos were selected, actual
row/commit counts, any new blockers hit) are logged in the entry below once
that run completes — per this file's own convention, only real results get
recorded here, not planned ones.

## 2026-08-10 — Phase 2 raw collection lands; in-house tool Phase A (Python OO metrics) built and validated

**Phase 2 raw collection — real outcomes** (the "logged once it completes"
promised above). Repo selection refreshed 2026-08-04
(`results/repos/08-04-repo-summary-235.csv`, 235 candidates), landing on a
**21-repo manifest** (`results/snapshots/08-04-repo-snapshot-manifest-2016.csv`
— 2016 grid rows, 1673 resolved to a real `commit_sha`), up from the
pilot's 5-repo/480-row manifest. Track B PR sampling ran at the new scale:
`results/pr_samples/08-04-pr-sample-4990.csv`, 4990 PR rows (up from 265).
Track A materialization (Phase 1e) is essentially done: **20 of the 21
manifest repos have real source trees in `data/snapshots/`** — only
`julep-ai/julep` doesn't yet (not investigated further this entry). New
repos beyond the original pilot: `567-labs/instructor`,
`AgentOps-AI/agentops`, `Azure/azure-sdk-for-python`,
`Significant-Gravitas/AutoGPT`, `browser-use/browser-use`,
`crewAIInc/crewAI-tools`, `featureform/enrichmcp`, `ikamensh/flynt`,
`marimo-team/marimo`, `marin-community/levanter`, `microsoft/testfx`,
`wieslawsoltes/Svg.Skia`, `dotnet/maui`, `dotnet/aspnetcore`,
`elsa-workflows/elsa-core`, `julep-ai/julep` (per the manifest's unique
`full_name` list) — a mix of Python and C#, so the in-house tool's C# leg
(Phase B, not built yet) matters for full Phase 2 coverage, not just the
Python side built this entry.

**In-house tool, Phase A: built.** Following up on `Writing/InHouseTooling.md`
and `Writing/RQ3_CodeTracking.md` (both still brainstorm docs as of
2026-08-04), this session made the scoping decisions needed to actually
build the replacement and logged them as "Design decisions (2026-08-05)"
sections in both docs, then built Phase A per the resulting plan
(`C:\Users\kvrlv\.claude\plans\woolly-jumping-acorn.md`): a from-scratch
Python OO-metrics engine, no LOC cap.

New code, all in `src/inhouse/`:
- `ast_common.py` — shared AST primitives: entity extraction (class/method/
  function inventories via the stdlib `ast` module, not `radon`), and a
  from-scratch McCabe cyclomatic-complexity walker that stops at nested
  def/class boundaries (a nested function gets its own CC, not folded into
  its enclosing function's).
- `py_metrics.py` — assembles those primitives into the DPy-schema metrics:
  per-class LOC/NOM/NOPM/NOF/NOPF/WMC/LCOM/DIT/Fan-In/Fan-Out, per-method
  LOC/CC/PC, rolled up into a snapshot-level row matching
  `parse_tool_output()`'s confirmed DPy schema (`total_loc`, `n_classes`,
  `n_methods`, `class_loc_p50/p90`, `method_loc_p50/p90`,
  `cyclomatic_complexity_p50/p90`) plus additive CK-suite percentile
  columns (`wmc_p50/p90`, `lcom_p50/p90`, `dit_p50/p90`, `fan_in_p50/p90`,
  `fan_out_p50/p90`, `pc_p50/p90`) DPy computes per-class but never pooled
  into its own summary row.
- `pool_inhouse_metrics.py` — CLI orchestrator, deliberately copying
  `long_analysis.py`'s conventions (argparse `--repo`/`--limit`/`--dry-run`,
  resumable via a global done-keys check across every same-tag output file,
  append-per-row, separate error CSV, progress JSON) rather than inventing
  a new shape.
- `validate_against_pilot.py` — joins the in-house output against the real
  pilot's DPy ground truth (`07-29-pooled-structural-metrics.csv`, filtered
  to `language == "Python"`) on `(repo_id, track, target_date, commit_sha)`
  and reports per-metric mean diff / mean %-diff / Spearman correlation —
  the concrete version of `InHouseTooling.md`'s "Validation plan" step 3.

**Caught a real bug via hand-checking, not just trusting the numbers.**
Built a synthetic fixture (`animals.py` — a module-level function plus a
base/subclass pair with known field/method structure) with metrics
pre-computed by hand, then ran the engine against it. Every value matched
by hand *except* the subclass's field count, which was inflated by one:
`self.speak()` (a call to an *inherited* method) was being counted as a
field access, since `self.name` and `self.speak(...)` are structurally
identical `ast.Attribute` nodes - nothing in a bare walk distinguishes a
field read from a method call. Fixed by adding an `exclude` set (the
class's own directly-defined method names) to the shared attribute-walk
helper (`ast_common.self_attribute_names`), used by both NOF/field
collection and LCOM's per-method field-access sets. Re-ran the fixture:
every value matched hand-computed expectations exactly, including the
*remaining*, now-documented blind spot the fix doesn't cover (a subclass
calling a method it only *inherits*, not one it defines itself, still
isn't recognized as a call - no cross-class method-name resolution is
attempted, same scope boundary as Fan-In/Fan-Out/DIT's own approximations).

**Real run + validation.** Ran `pool_inhouse_metrics.py` against all three
pilot Python repos' materialized snapshots (crewAI + crewAI-tools, airbyte,
mlflow - `--repo` substring matching pulled in crewAI-tools alongside
crewAI, unplanned but harmless, more real validation data). Speed: ~1
second per snapshot end to end (5 real crewAI snapshots: 4.0s total) -
qualitatively different from DPy's per-chunk runtime at LOC-cap scale (the
mlflow snapshot that cost DPy ~29 hours chunked would be seconds here,
un-chunked, since there's no license cap to chunk around at all). A
handful of rows failed with real, expected "not materialized" errors (some
Phase 2 commits, e.g. a few crewAI-tools A1/A2 grid points, don't have a
materialized snapshot yet) - logged to the errors CSV per
`pool_inhouse_metrics.py`'s convention, not silently dropped or crashing
the run.

`validate_against_pilot.py`'s real agreement numbers against DPy: see
`Writing/Results.md`'s new in-house-tool section - not duplicated here per
this file's "real results belong in the entry, but the actual numbers/
interpretation belong in Results.md" split already used for the pilot's
first analysis. **One finding from that validation is worth flagging here
directly, not just in Results.md**: airbyte's total_loc/n_classes disagree
with DPy far more (2.41x, final across all 96/96 rows) than crewAI/mlflow
(1.54x/1.71x), and a direct
`wc -l` cross-check on one commit confirms the in-house number
(352,778 lines) is right and DPy's own reported figure (125,111) is the
one that's off - that commit needed 411 DPy chunks (airbyte's repo-wide
average: ~374 chunks/snapshot, vs. crewAI's ~30), consistent with DPy's
Trial-cap chunking silently losing coverage as chunk count grows, not a
labeling/convention difference. Full writeup: `Results.md`.

**Not built this entry** (scoped in the plan, follow-on work): Phase B
(C# via Roslyn `CSharpSyntaxTree.ParseText`, no `.sln`/`MSBuildWorkspace`
load - expected to also unblock `dotnet/aspire`, still excluded from the
pilot on the Designite side), Phase C (time-series + pre/post
Spearman-correlation-matrix visualization, reusing
`analyze_dock_designite.py`'s existing chart conventions), Phase D (RQ3
entity/snippet lifetime tracker - reuses `ast_common.py`'s entity
extraction, walks `git log --follow` per file rather than the monthly
snapshot grid). Also un-investigated: exactly why `julep-ai/julep` didn't
materialize, and the handful of Phase 2 commits that produced "not
materialized" errors during the validation run above.

## 2026-08-11 — In-house tool Phase B (C# via Roslyn) built and validated; a real manifest bug found along the way

Prompted by a direct question: why hadn't the in-house tool been run
against Phase 2's ~16 new repos yet? Answer at the time: it couldn't be,
not just hadn't been - Phase A only computes OO metrics (no smell
detection, the pilot's actual headline metric), and 9 of the 21 manifest
repos are C# with no analyzer at all. Asked which gap to close first;
answer was Phase B (C#), not smell detection - get all 21 repos onto some
structural-metrics footing before deepening what's measured for the
Python-only 12.

**Reconnaissance before committing to the build** (per the pattern that
worked for Phase A - hand-check before trusting): confirmed `dotnet`
8.0.423 restores `Microsoft.CodeAnalysis.CSharp` from NuGet fine (network
access, not a given - checked), confirmed `CSharpSyntaxTree.ParseText`
correctly extracts classes/methods/bases/LOC with a throwaway probe
program before writing anything real, confirmed Dock's materialized
snapshots are genuinely plain `.cs` files with no `.sln` needed for a
syntax-only read.

**Built** (`src/inhouse/roslyn_tool/`, a small .NET console project):
- `Entities.cs` / `CcWalker.cs` / `SnapshotAnalyzer.cs` - direct
  translation of Phase A's design (`ast_common.py`/`py_metrics.py`) onto
  Roslyn's syntax model: same McCabe CC rules (adapted node types - `if`/
  `for`/`foreach`/`while`/`do`/`catch`/`case`/switch-expression-arm/
  ternary/`&&`/`||`, same nested-def/type boundary rule, lambdas not a
  boundary), same WMC/NOM/NOPM/NOF/NOPF/LCOM/DIT/Fan-In/Fan-Out
  definitions, same span-based LOC, same output schema (pools directly
  onto Phase A's columns, no adapter).
- `Program.cs` - CLI entry point, one materialized snapshot dir in, one
  line of JSON on stdout, mirroring how `run_designite()` already shells
  out to `DesigniteConsole` in `long_analysis.py`.
- `src/inhouse/csharp_metrics.py` - Python subprocess glue, same
  `analyze_snapshot(dir) -> dict` interface Phase A's `py_metrics.py`
  exposes, so `pool_inhouse_metrics.py` could route by `row["language"]`
  instead of hardcoding Python.

**A real gap caught by hand-checking, before real data**: the same
`Animal`/`Dog` synthetic fixture used for Phase A, translated to C#.
Every value matched by hand except the whole thing was initially wrong in
a worse way than Phase A's bug - constructors weren't being extracted at
all. `ConstructorDeclarationSyntax` is a sibling of
`MethodDeclarationSyntax`, not a subtype, so
`node.Members.OfType<MethodDeclarationSyntax>()` silently skips every
constructor - which would have dropped constructors from NOM/WMC and,
worse, from LCOM's field-access scan (a constructor is often the one
method that touches every field, exactly the case LCOM is supposed to be
sensitive to). Fixed by extracting `BaseMethodDeclarationSyntax`
throughout (covers methods, constructors, destructors, operators) and
adding a `MethodNameOf()` helper since the concrete subtypes name
themselves differently (`.Identifier` vs. `.OperatorToken`). Re-ran the
fixture: exact match on every hand-computed value. Bonus finding, not a
bug: C#'s real field-declaration syntax means the LCOM/NOF computation
never needed Phase A's self.method()-vs-self.field disambiguation hack in
the first place - the same fixture's `Dog` class correctly gets `NOF=0` in
C# (it declares no fields), vs. Python's `NOF=1` from mis-reading
`self.speak()` as a field access. A structural advantage of C# having
field declarations at all, not a fix applied here.

**Real run, real validation**:
- Full Dock set (96/96 rows, `ok`, 0 failures) and full `dotnet/aspire`
  set (75/75 rows, `ok`) - both from real materialized snapshots, ~1s per
  snapshot.
- `validate_against_pilot.py` extended to stop hardcoding Python: ground
  truth is no longer filtered to `language == "Python"`, and the report
  now splits by language instead of averaging Python and C# into one
  blended (and misleading) number.
- **First join attempt returned 2/87 matches for Dock - not a validation
  failure.** Traced it to the *manifest*, not the tool: the latest
  snapshot manifest (`08-04-repo-snapshot-manifest-2016.csv`) resolves 94
  of Dock's 96 grid points to just 2 distinct commits (mostly one from
  2022-01-27), while the original manifest
  (`07-21-repo-snapshot-manifest-480.csv`) correctly resolves 64 distinct
  commits, all genuinely materialized on disk already. Root cause:
  `data/repo_cache/wieslawsoltes__Dock`'s local clone is currently stale,
  capped at that same January 2022 commit - the newer manifest's
  "closest commit at or before this date" resolution has nothing newer to
  resolve to, so it keeps returning the same one. Checked whether this was
  systemic before treating it as Dock-specific: it isn't - airbyte
  (95→95), crewAI (71→71), mlflow (96→96), and `dotnet/aspire` (75→75) all
  kept full commit diversity across both manifest versions. Worked around
  for this validation run via `pool_inhouse_metrics.py --manifest
  results/snapshots/07-21-repo-snapshot-manifest-480.csv`; the underlying
  clone staleness itself is unresolved (needs a fresh `git fetch`/backfill
  for Dock specifically) - logged in `ProjectStatus.md` §7, not fixed here,
  since it's a Phase 1c/data-collection issue, not an in-house-tool one.
- **Real numbers, 87/87 Designite-successful Dock rows joined**:
  `total_loc` r=0.999, `n_classes` r=0.998, `n_methods` r=0.997,
  `cyclomatic_complexity_p90` r=0.546 (weaker - same class of
  cross-implementation CC-counting divergence Phase A's Python validation
  already showed). Class/method counts run negative vs. Designite (-11 to
  -15%), the opposite sign from Phase A's Python offset - plausibly
  explained by a Designite quirk already logged in `DESIGNITE_TASK.md`:
  multi-targeted projects get a full duplicate metrics set per target
  framework, undeduplicated, so Designite's own counts run inflated, not
  ours short. Not independently re-confirmed this session (noting the
  plausible explanation, not asserting it as proven).

**Two unplanned wins, both a direct consequence of never loading a project
graph**: `dotnet/aspire` (excluded from the pilot entirely - Designite
can't evaluate its project without replicating Arcade's private-feed
bootstrap) now has real structural data for the first time this project
has ever had it. Dock's post-`.slnx`-migration months (9/96 rows Designite
can't read, censoring exactly the back half of its post-intervention
window - a real, repeatedly-flagged limitation on the pilot's Dock
results) are no longer censored for the in-house tool - all 96/96 read
cleanly.

**Not done this entry**: re-running the pilot's actual RQ1-RQ5 analysis
(segmented regression etc.) on the now-available in-house Dock/aspire data
- that's a real next step (Phase C territory) but wasn't asked for this
entry, which was scoped to "get Phase B built and validated." Also not
done: fixing Dock's stale `repo_cache` clone, or running Phase B against
the other 8 Phase 2 C# repos (`dotnet/maui`, `dotnet/aspnetcore`,
`wieslawsoltes/Svg.Skia`, `microsoft/testfx`, `elsa-workflows/elsa-core`) -
the tool is ready for them, just not pointed at them yet.

## 2026-08-11 (later) — Phase B rolled out to all 7 C# repos; Dock's leftover bad-manifest rows cleaned up

Follow-up to the same day's Phase B entry above: asked to run Phase B
"on everything" for the most accurate results possible, with Python-side
smell detection explicitly called out as being worked on separately (a
different branch) - so this entry is C#-only by design, not an oversight.

**Materialization gap found first.** Of the 5 remaining Phase 2 C# repos
(`dotnet/maui`, `dotnet/aspnetcore`, `elsa-workflows/elsa-core`,
`microsoft/testfx`, `wieslawsoltes/Svg.Skia`), only `dotnet/aspnetcore`
had any materialized snapshots at all (65/96), and three had zero. Their
`git` clones existed in `data/repo_cache/` already, just never archived
(Phase 1e). Ran `materialize_snapshots.py --repo <name>` for all 5 in
parallel background jobs. One transient Windows failure
(`dotnet/aspnetcore@9642bab`: "directory is not empty" on a leftover
`.tmp` extraction folder from an earlier interrupted attempt) - cleared
the stale `.tmp` dir manually and reran; `materialize_snapshots.py`'s own
idempotent design meant this was a one-line fix, not a real problem.
Final: `dotnet/maui` 94/94, `elsa-workflows/elsa-core` 93/93,
`microsoft/testfx` 93/93, `wieslawsoltes/Svg.Skia` 53/53,
`dotnet/aspnetcore` 96/96 (95 + the 1 retried).

**Checked each new repo for the Dock manifest bug before trusting it** -
same method as when the bug was first found: compare unique-commit count
against the 96 grid rows, and check the local clone's most recent commit
date. All four (`aspnetcore` 95, `maui` 94, `elsa-core` 93, `testfx` 93 -
`Svg.Skia` was already checked in the earlier entry, 54 unique) showed
healthy diversity and clones current as of late July/early August 2026.
Confirms, again, that the collapse-to-2-commits bug is specific to
`wieslawsoltes/Dock`'s clone, not a property of the manifest-generation
code itself.

**Ran Phase B against all 5**, each as its own background job:
`wieslawsoltes/Svg.Skia` 96/96 ok, `elsa-workflows/elsa-core` 96/96 ok,
`microsoft/testfx` 96/96 ok, `dotnet/maui` 96/96 ok, `dotnet/aspnetcore`
96/96 ok. Combined with the earlier Dock (96) and `dotnet/aspire` (75)
runs: **all 7 C# repos in the manifest now have full in-house structural
data, 651 rows total, 100% `ok`, zero failures.**

**Found and fixed a real data-hygiene issue while consolidating.** Pooling
all in-house output files together to summarize, Dock showed 190 rows
instead of 96 - the 94 leftover rows from the *broken*-manifest run
(logged in the earlier entry) were still sitting in
`08-11-inhouse-metrics-Dock-{5,96}.csv` alongside the 96 correct ones,
un-deduplicated because they carry a different `commit_sha` for the same
`target_date` (so the resumability logic's key-based dedup never saw them
as redundant - they're genuinely different rows, just wrong ones). Filtered
both files down to exactly the 96 rows matching the verified-correct old
manifest's `(track, target_date, commit_sha)` triples before calling this
done - confirmed after: 96 rows, 64 unique commits, 0 duplicate
`(track, target_date)` pairs. Re-ran `validate_against_pilot.py` after the
cleanup to confirm the join numbers didn't change (they didn't - 87/87,
same figures as the first Dock validation) - the bad rows were extras, not
substitutions, so they weren't silently corrupting the validated numbers,
just cluttering the output file.

**Not done this entry**: anything on the Python side (by design - see
above), fixing Dock's actual stale `repo_cache` clone (still just papered
over via the `--manifest` override, not fixed at the source), and
re-running the pilot's RQ1-RQ5 analysis on any of this newly-available
data (Phase C territory, not asked for here).

## 2026-08-12 — Real per-touch churn rates (Part A), method-churn figures (Part B), Track A two-tier figure set (Part C)

Prompted by a direct question about which of a proposed 8-figure/2-table
inventory could actually be built from data already on hand (6/8 buildable,
1 partial, 1 not directly). The approved plan was rewritten twice before
execution, both times on real feedback: first, to stop scoping churn
figures to the 4-repo pilot and instead show method-level churn behavior
across all the data; second, to re-check `main` before finalizing, which
surfaced that `python-smell-detection` (11-repo in-house Python smell
detector, `py_smells.py`) had merged since the plan was last drafted -
`main` was merged into this worktree first (`git merge main`, one real
conflict in `Writing/Results.md`, resolved by keeping both sides' sections
in sequence, not choosing one) so the final figure set could use both
datasets rather than shipping a plan already stale on arrival.

**Part A - real per-touch pre/post churn counts.** No prior branch had ever
persisted per-touch dates, so `EntityLineage.pre_post_touch_counts
(intervention_date)` (`src/inhouse/entity_matching.py`) is genuinely new:
walks a lineage's touches, splits by the repo's real intervention date, and
returns touches/day on each side using the *actual observed* pre/post
window length (not a fixed period) so repos with different-length windows
stay comparable. Threaded through `py_entity_history.py`/
`cs_entity_history.py`'s builders and `pool_entity_history.py` (which now
loads `08-04-repo-summary-235.csv` once for intervention dates) as
additive columns (`pre_touch_count`/`post_touch_count`/`pre_churn_rate`/
`post_churn_rate`), existing callers unaffected.

**Real bug, caught by resumability's own dedup logic working too well.**
Re-running `pool_entity_history.py` across all 21 repos to backfill the new
columns instantly reported "resuming: 21/21 already done" - the
`*-entity-history-*.csv` resumability glob matched not just the original
Stage 5 output but Stage 6's own derived `-windowed-cut*.csv` files sitting
in the same directory, so the script saw prior output and skipped the real
work entirely. Fixed by archiving (not deleting) everything pre-dating this
change to `results/analysis/archive_pre-churn-columns_2026-08-11/`, mirroring
the existing `archive_pre-godclass-fix_2026-08-11/` convention from the
smell-detector branch, then re-running for real. Output:
`results/analysis/08-12-entity-history-21.csv` - 27,572 rows, an exact match
to the original row count (confirms the walk itself didn't change, only the
new columns), 21/21 repos ok, 584 spanning callables (entities with
touches on both sides of the intervention, the only ones a before/after
churn question can even be asked of).

**Part B - method-churn figures (`src/viz/generate_churn_figures.py`),
all 21 repos, not just the pilot.** Fig 7 (pooled before/after churn-rate
box+strip), Fig 8 (per-repo mean churn rate, symlog x-axis - a linear scale
made 15+ of 18 repos' bars vanish next to `browser-use/browser-use`'s
outlier mean pre-rate of ~7.75 touches/day), Fig 9 (pooled
post-minus-pre-rate histogram, clipped to 1st-99th percentile), Table 3
(per-repo backing stats). **Headline finding, no net signal**: 584 spanning
methods across 18/21 repos (3 repos had zero surviving methods to compare),
302 sped up vs. 282 slowed down post-intervention - real spread, not a
consistent direction. `browser-use/browser-use` alone accounts for 162 of
the 584 (mean pre-rate 7.75 touches/day, next-highest repo 0.64) - flagged
directly in the figures' own captions as a real outlier dominating the
per-repo view, not smoothed into the pooled numbers silently.

**Part C - Track A structural-health figures
(`src/viz/generate_track_a_figures.py`), two-tier by design.** Figs 1/1b
(smell-density trend), 2 (event-window), 4 (composition), 6
(cross-language) now each carry two panels: the original 4-repo DPy/
Designite pilot (unchanged, the "clean" comparison point) alongside a new
~11-repo Python-only panel from `py_smells.py`'s in-house detector,
captioned as a genuinely different smell definition rather than presented
as equivalent, per the caveats `InHouseTooling.md` already logged.
Fig 3 (forest plot) and Table 1/2 stay pilot- and 21-repo-scoped
respectively, per the plan's scope table. New shared module
`src/viz/figures_common.py` centralizes the palette, `rcParams`, and a
`save_fig()` helper - copied from `analyze_dock_designite.py`'s established
convention rather than inventing a new one.

**Real, non-cosmetic bugs caught by reading every rendered PNG, not just
trusting a clean script exit** - matches this project's established
verification pattern: a suptitle placed at `y=1.05` didn't clip, it
vanished from the canvas entirely (matplotlib doesn't extend beyond y=1.0
without `bbox_inches='tight'`, which `save_fig` doesn't use) - fixed by
keeping every suptitle `y<=0.99` and reserving headroom via
`save_fig(..., top=...)`'s `tight_layout(rect=...)`; a long single-line
caption overflowed a narrower figure's canvas and clipped at both edges
(shortened text / widened the figure, case by case); Fig 4's in-house panel
produced an illegible high-frequency sawtooth from grouping 11 repos by
exact (misaligned) snapshot date - fixed by bucketing to month before
grouping, confirmed as a real fix via a direct before/after visual
comparison, not a cosmetic tweak; one literal syntax bug
(`linewidth(1.3) if False else 1.3`, a leftover invalid expression) caught
before the script even ran.

Output: `Writing/figures/track_a_structural_health/` (6 PNGs + `table1_
coverage.csv` + `table2_descriptive_stats.csv`) and `Writing/figures/
method_churn/` (3 PNGs + `table3_churn_rate_stats.csv`). Full writeup in
`Results.md`; plan and verification log in
`C:\Users\kvrlv\.claude\plans\glimmering-snacking-torvalds.md`.

**Not done this entry**: Fig 5 (LOC/CC before/after, still pilot-scoped -
needs Tool-Py run wider, a separate prerequisite not part of this plan);
a C# smell detector (Fig 6's cross-language panel stays 11 Python vs. 1 C#,
lopsided, no in-house tool exists for the C# side yet); multiple-comparison
correction across the growing set of significance tests this project has
now run (flagged repeatedly since 2026-07-29, still true).

## 2026-08-13 — C# smell detector, full-corpus OO metrics, reconstructed regression script, Figs 3b/4/5/6

Prompted by a direct question about what "in-house tooling replaces DPy/
Designite entirely" actually requires, and a request to get Figs 3/4/5
covering all repos in the dataset, not just the 4-repo pilot. Answered
the underlying question first (see `Results.md`/session record): OO
metrics already are a validated 1:1 replacement; smells never can be a
row-for-row one, since DPy/Designite's rule catalogs are closed and the
raw per-smell CSVs that would show their exact rule names were deleted
after pooling - only aggregate counts survive. What was actually missing
for "replaces DPy/Designite" was coverage: no C# smell detector existed
at all, and OO metrics had only been run against the 3-repo Python pilot
despite `pool_inhouse_metrics.py` already supporting every repo.

**Part 1 - C# smell detector (`src/inhouse/roslyn_tool/SmellDetector.cs`,
new).** Direct C# port of `py_smells.py`'s four Lanza & Marinescu
strategies (God Class, Data Class, Feature Envy, Brain Method), reusing
the already-existing `SnapshotAnalyzer.FieldAccessSets` field-access-set
machinery (refactored out of `ComputeLcom`, additive, no behavior change
to the existing OO-metrics engine) rather than re-walking the AST. C# has
real field/property declarations, so there's no `self.method()`-read-as-
field-access heuristic bug to guard against here, unlike the Python side.

**A real, pre-existing build break found and fixed along the way,
unrelated to this work but blocking it**: the checked-in `roslyn_tool`
didn't actually compile at HEAD - `ClassInfo`/`MethodInfo`'s `StartLine`/
`EndLine` (added for the RQ3 entity tracker, 2026-08-11) were `required`
members that `BuildClassInfo`/`BuildMethodInfo` never set. Confirmed via
`git stash` that this predates any change this entry made. The compiled
`bin/roslyn_tool.dll` had simply never been rebuilt since - `csharp_metrics.py`'s
`ensure_built()` only rebuilds when the DLL is missing, so this had been
silently masked. Fixed by setting both fields from the same `LineSpan`
already computed for `Loc`.

**A real bug in the new smell detector, caught by hand-validation before
trusting it on real data** - the exact discipline `PySmellDetection.md`'s
own build log already established: two small, fully hand-computable C#
fixtures (one designed to trigger God Class + Data Class with predictable
percentile math, one designed to trigger Feature Envy + Brain Method).
First run: God Class/Data Class/Feature Envy all matched hand-computed
expectations exactly, but Brain Method returned 0 where 1 was expected.
Root cause: `MaxNestingLevel`'s walker was invoked as `Visit(methodNode)`
on the method declaration itself, which immediately hit the walker's own
`VisitMethodDeclaration` no-op boundary (there so a *nested* method's
depth doesn't fold into its enclosing method's) and returned before ever
descending into the body - the exact pitfall `CcWalker.Compute` already
avoids by starting from `method.Body`, not `method`. Fixed by matching
that pattern. Re-ran both fixtures after the fix: exact match on every
value, including the corrected nesting depth (7, traced by hand through
an `if/else-if/else-if` chain nested inside a `for` inside three more
`if`s).

**Re-checked, not assumed, that the Python-tuned God Class threshold
transfers to C#**: pulled real per-class WMC/TCC pairs from Dock's largest
snapshot (1,489 classes) and measured the same anti-correlation the Python
side found - Spearman r=-0.743 (p≈3e-261), squarely inside Python's
observed -0.53 to -0.82 range across sample repos. Confirms the already-
tuned 10%/10% percentile threshold (not the paper's original 25%/25%) is
the right call here too, not just assumed to carry over.

**Real run: all 7 C# repos, 1,354 ok / 0 failed.** Dock's design-smell
rate (3.40% of classes) and cross-language comparison (Fig 6) both landed
in a plausible, informative range - not spot-checked further beyond the
fixture/correlation validation above.

**Part 2 - full-corpus OO metrics.** `pool_inhouse_metrics.py` already
routed by language and had no LOC cap; it just hadn't been pointed at the
~8 Python Phase 2 repos beyond the pilot. Ran it unscoped (full manifest,
`--exclude-repo azure-sdk-for-python` - same O(n²) `_lcom`/`_tcc`
cohesion-computation risk already flagged for smells, not re-litigated
here). New: `src/inhouse/consolidate_inhouse_metrics.py` and
`consolidate_inhouse_smells.py`, concatenating the now dozen-plus
fragmented per-repo/per-run output files into one canonical pooled table
each (`results/analysis/08-13-inhouse-{metrics,smells}-pooled.csv`) -
there was previously no single "the pooled in-house table" the way
`07-29-pooled-structural-metrics.csv` is for DPy/Designite.

**A real data-hygiene bug caught before it reached the pooled files, same
category as the one already fixed 2026-08-11 for Dock's OO metrics**: the
unscoped full-manifest run resolves `wieslawsoltes/Dock`'s stale local
clone to a single collapsed commit across ~94 of its 96 grid points -
reproduced directly (94 rows, 1 unique `commit_sha`) in *both* the new
OO-metrics run and the new smells gap-fill run. Both consolidation
scripts now recognize an unscoped/bare-number-suffixed source file by
its own filename convention and drop that file's Dock rows
unconditionally (not just deduplicated) before pooling, keeping the
older `--manifest`-overridden, verified-correct Dock data instead.
Confirmed: both pooled files land at exactly 96 Dock rows, matching the
already-verified count.

**`browser-use/browser-use` confirmed as a genuine, separate gap while
gap-filling smells** - Table 1 had shown 0 in-house smell rows for it
despite an earlier build-log entry implying it landed in the full re-run;
checked for real rather than assumed still true. All 57 of its rows fail
with "not materialized" - Phase 1e never actually checked out its source
trees, despite the manifest resolving real commits for it. Not fixed here
(a different pipeline, materialize_snapshots.py) - flagged as a real,
separate, open item.

**Final pooled coverage**: 1,450 rows each in the OO-metrics and smells
pools, 18 repos (11 Python + 7 C#) - `julep-ai/julep` (never
materialized) and `Azure/azure-sdk-for-python` (excluded, O(n²) risk)
are the only Phase 2 repos still without in-house data, both pre-existing,
documented gaps, not new ones.

**Part 3 - reconstructed `src/analysis/segmented_regression.py` (new).**
`results/analysis/07-29-segmented-regression-A1.csv` (Fig 3's data) turned
out to have no committed generating script at all - confirmed via
`git log --diff-filter=A` on the CSV, which shows no `.py` file added in
the same commit. Reconstructed the model from `Results.md`'s own
methodology note (`metric ~ time + post + time_since_intervention×post`,
the standard Wagner et al. 2002 interrupted-time-series design), closed-
form OLS via normal equations (no `statsmodels` in this environment).

**Reconstructing this faithfully took real iteration, each step checked
against the pilot's actual stored numbers rather than assumed correct**:
first pass (a single time variable reused for both the pre-trend and the
post-interaction) reproduced most coefficients but left the intercept off
by ~13-32 depending on the row; tracing it showed the pilot's intercept
sits at the *series' own start* (2022-01), not at the intervention date,
meaning "time" and "time since intervention" are two genuinely different
variables in the original design, not one column serving double duty.
Switching to two variables (a continuous month-index from the series
start for the main/pre-trend term, the already-stored
`months_since_intervention` column for the interaction only) closed the
gap to ~0.03 - then tightened to ~1e-10 once the first variable was
computed from real calendar days (`/30.436875`) instead of a plain
integer row index, since real months aren't equal-length. p-values
initially used a normal (z) test to match the CI's stated "normal
approximation," which reproduced most rows but systematically undershot
the pilot's own p-values (a z p-value never fully underflows to a literal
`0.0` the way a t-distribution one does at extreme z, and the pilot's
`slope_pre_p=0.0` exactly is the tell) - switched p-values to a standard
t-test (dof degrees of freedom), keeping the CI itself on the normal
approximation as `Results.md`'s wording specifically names. A last ~1e-5
residual on CI bounds only, traced to the conventional rounded `1.96`
vs. `scipy.stats.norm.ppf(0.975)`'s precise `1.959964` - switched to the
rounded constant. Final reproduction: max absolute difference 2.3e-6
across all 12 pilot rows and every reported column, with one named,
understood exception (airbyte's `cyclomatic_complexity_p90`, a perfectly
flat 3.0 for all 51 months - `Results.md`'s own "no signal available, not
no effect" row - where both this script's and the original's p-values/CIs
are noise-over-noise on a genuinely zero-variance fit, not comparable to
float precision).

**Full-corpus run**: 45 (repo, metric) rows fit across 15 repos (both
languages) × 3 primary metrics, minimum-N rule `n_pre>=5 and n_post>=5`
(matching the pilot's own thinnest cell, Dock's `n_post=6`) - 9 combos
skipped for insufficient data (`crewAIInc/crewAI-tools`,
`featureform/enrichmcp`, `marimo-team/marimo`, all genuinely thin on one
side), reported in a `-skipped.csv`, not silently dropped. **20/45
significant level changes, 17/45 significant slope changes at p<.05,
split roughly evenly in sign** - the same "real, non-random signal, no
consistent cross-repo direction" shape the 4-repo pilot already showed,
now confirmed at roughly 4x the repo count.

**Part 4 - figures.** `generate_track_a_figures.py`: added Fig 3b (the
full-corpus forest plot, kept as its own figure alongside the unchanged
pilot-scoped Fig 3, same two-tier convention as Fig 1/1b - a 45-row
figure, scaled the same way Fig 3's height formula already handles
arbitrary row counts); built Fig 5 for real (LOC/CC before/after, all 18
repos - scoped in an earlier plan but never actually implemented, absent
from `main()` until now); rewrote Fig 6 so both panels use the full
in-house corpus instead of falling back to the pilot's Dock-only Designite
data for panel A or staying pilot-scoped for panel B - dropped the
"still lopsided"/"pilot only" captions since neither is true anymore, kept
a real remaining caveat (the smell panel's narrower, differently-validated
definition vs. DPy/Designite doesn't go away just because coverage did).
Fig 4's in-house panel required no code change - `smells` already comes
from the now-both-language `load_inhouse_smells()` - just an updated
caption (11 Python + 7 C# repos, was 11 Python).

**A stale-caption bug caught during visual verification, not by the
script exiting cleanly**: Fig 1b's small-multiples grid silently expanded
from 11 panels to 18 the moment `load_inhouse_smells()` was generalized -
correctly rendering all 7 new C# repos' panels with real data - but its
title still read "11 Python Phase 2 repos" until caught by actually
looking at the rendered PNG (not just checking the script's exit code),
this session's established verification bar. Fixed to compute the
Python/C# repo counts dynamically rather than hardcoding them.

**Not done this entry**: committing/pushing this work (a concurrent
session was found to be using this same worktree mid-session for an
unrelated fix, so git actions were held pending explicit direction - see
`ProjectStatus.md`); a multiple-comparison correction across the now
larger set of significance tests (still an open item, flagged repeatedly
since 2026-07-29); re-materializing `browser-use/browser-use` or
`julep-ai/julep`.

## 2026-08-17 — Pipeline scaling, Phase A: shared resumability, exclusion registry, orchestrator

Prompted by the next real target: growing the corpus from ~18-21 repos to
100, then eventually 1000, "as pain-free as possible." Before touching
repo count at all, a research pass across the whole pipeline (repo
selection through consolidation/regression/viz) turned up the actual
blockers: no single orchestrator (every stage run by hand, in an order
documented only in prose, `README.md` empty); the same done-keys/progress/
error-file resumability logic reimplemented three times, with a stale-file
footgun that had already bitten twice (`PySmellDetection.md`'s and
`RQ3_CodeTracking.md`'s full re-runs, both worked around by manually
moving files into `archive_*/` folders); three uncoordinated exclusion
mechanisms with no shared record of *why* a repo was excluded; zero
concurrency anywhere in `src/inhouse`/`src/analysis` (wall-clock scales
linearly with repo count); and two already-documented O(n)-blowup
bottlenecks (`_tcc`/`_lcom`'s O(n²) cohesion computation, confirmed
~20min on `azure-sdk-for-python`; entity-history's per-touch `git show`
subprocess cost, confirmed 68min on `browser-use/browser-use`). A phased
plan (Phase A: foundational fixes / Phase B: repo-level concurrency +
bottleneck fixes / Phase C: 1000-repo validation) was written up and
approved before any code changed - full detail in `InHouseTooling.md`'s
new "Pipeline orchestration & scaling, Phase A" section rather than
duplicated here; short version below.

**Built**: `src/common/resumable_run.py` (extracted, shared
done-keys/progress/error logic + a `schema_version`/`.runinfo.json`
staleness check + `--stale-check` on all three pool scripts);
`results/repos/excluded_repos.csv` + `src/common/exclusions.py` (single
exclusion registry, `scope=permanent`/`per-run`, replacing the hardcoded
`EXCLUDED_REPOS` set and undocumented `--exclude-repo` one-offs);
`src/pipeline/run_pipeline.py` (a thin subprocess sequencer for the
13-stage pipeline, `--stages`/`--target-total`/`--dry-run`/`--limit`/
`--repo`/`--stale-check`, stops on first failure, writes a rolled-up
`results/pipeline-run-<timestamp>.json`); a corpus-size gate
(`PILOT_SIZE_CEILING=25`, `--force` override) added directly to
`long_analysis.py` so the licensed DPy/Designite path - ~29 hours for one
large snapshot under its LOC-cap chunking - can never run by accident at
scale, and is excluded from the orchestrator's default stage list
entirely (name it explicitly via `--stages legacy-dpy-designite` to run
it at all). `consolidate_inhouse_metrics.py`, `consolidate_inhouse_smells.py`,
and `generate_track_a_figures.py` (none had a CLI before) each got a
stable `run()` entry point.

**Verification**: no formal test suite exists in this repo (hand-
validation against known-good numbers is the established pattern - see
every tool's own build-log entry above), so this was checked the same
way: isolated unit-style tests for the new staleness/registry logic (12
assertions, all passing - schema-version trust/exclusion, legacy-file
backward compatibility, idempotent registry writes, scope filtering),
dry-run smoke tests of all three pool scripts through both their own CLI
and the orchestrator (resumability/skip-on-resume/stale-check all
reconfirmed working identically to pre-refactor behavior), a synthetic
failing-stage test confirming the orchestrator actually stops a run
rather than continuing past a bad stage, and command-construction checks
for every one of the 13 stages. All touched files `py_compile` clean.

**Real side effect, not a test artifact**: exercising `viz-churn`
end-to-end (part of orchestrator verification) surfaced that
`Writing/figures/method_churn/`'s `fig7`/`fig8`/`fig9`/`table3` were
stale - last generated before the 2026-08-13 entity-history
sampling-bias fix landed. Regenerating them changed real numbers (e.g.
`wieslawsoltes/Dock` now shows real churn stats instead of being absent)
- kept as a genuine correction, committed alongside this entry rather than
reverted.

**Not done this entry**: Phase B (repo-level `ProcessPoolExecutor`
concurrency, the `_tcc`/`_lcom` cohesion-sampling cap, entity-history
`git cat-file --batch` port, `data/repo_cache` storage lifecycle) - the
actual wall-clock levers for 100+ repos, still to come; `--pilot-size` →
`--target-total` rename across `repo_pr_selection.py`/
`repo_snapshot_pipeline.py` (planned, not yet renamed - the orchestrator
currently translates `--target-total` to `--pilot-size` under the hood);
re-running the Phase 0 candidate search with a wider pool (235 candidates
is enough for 100 repos, not 1000 - flagged as a precondition, not
addressed).

## 2026-08-17 (later) — Pipeline scaling, Phase B: concurrency, cohesion sampling, git batching, storage lifecycle

Same day as Phase A above - the actual wall-clock levers the earlier
entry flagged as "not done this entry": repo-level concurrency, the two
confirmed O(n) blowups (`_tcc`/`_lcom`'s O(n²) cohesion computation,
entity-history's per-touch `git show` cost), and a storage-reclaim tool.
Full design rationale in `InHouseTooling.md`'s new "Pipeline scaling,
Phase B" section; short version below.

**Built**: `src/common/parallel_repo.py` (`run_by_repo()`, a shared
repo-level dispatcher - `--workers N` on `pool_inhouse_metrics.py`,
`pool_inhouse_smells.py`, `pool_entity_history.py`, and
`materialize_snapshots.py`, default sequential/unchanged, `>1` dispatches
one `ProcessPoolExecutor` worker per repo); `ast_common.sample_field_sets()`
(seeded sampling above 300 methods, applied to `py_smells.py`'s `_tcc`,
`py_metrics.py`'s `_lcom`, and their C# mirrors in `SmellDetector.cs`/
`SnapshotAnalyzer.cs`, fixing the confirmed ~20-minute
`azure-sdk-for-python` stall); `py_entity_history.py`'s `batch_show()`
(one `git cat-file --batch` process per file instead of one `git show`
per commit-touch, fixing the confirmed 68-minute `browser-use/browser-use`
stall, also wired into `cs_entity_history.py` since both languages shared
the bottleneck); `src/common/storage_lifecycle.py` (dry-run-by-default,
`--confirm`-gated `data/repo_cache/` pruning tool, deliberately not
auto-wired into the pipeline).

**A real bug caught during verification, not shipped**: the first LCOM
sampling implementation rescaled the sampled P/Q pair counts by (true
pair count / sampled pair count) before subtracting - the same treatment
that works fine for TCC. Checked directly with a controlled synthetic
case (600 methods split evenly across 2 fields) before trusting it:
true P-Q=300, the naively rescaled estimate=593, ~98% relative error.
Root cause (full derivation in `InHouseTooling.md`): LCOM is a
*difference* of two large, nearly-equal counts, not a ratio like TCC -
subtracting two independently sampling-noisy estimates amplifies error
catastrophically when their true difference is small relative to either
count. Fixed by reporting the raw p-q computed on the sample directly,
not an extrapolated guess - both the Python and C# implementations were
already written with the (wrong) extrapolation before this was caught,
so both got the same fix.

**Verification**: real multi-repo `--workers` dispatch tested against
all four scripts (correct row/repo counts, no duplication, cross-mode
resumability between parallel and sequential runs); a synthetic
failing-worker case confirming `ProcessPoolExecutor` failures propagate
rather than vanish; `sample_field_sets()` tested for reproducibility and
correct threshold behavior; a synthetic 2000-method class confirmed both
`_tcc` and `_lcom` complete in ~0.02s under sampling (vs. the unbounded
O(n²) cost before); `batch_show()` checked byte-for-byte identical
against the old per-commit approach on a real 80-commit sample from
`crewAIInc/crewAI` (38.7x speedup, 4.339s → 0.112s), then re-verified
end-to-end on both the Python and C# entity-history paths against real
repos (`crewAIInc/crewAI`, `wieslawsoltes/Dock`); `storage_lifecycle.py`
dry-run checked against this repo's real `data/repo_cache/` (9.37GB
across 21 repos, correctly sorted, `--repo`/`keep_cache.csv` filtering
both confirmed) - a real performance bug in the first version (computing
every candidate's directory size before filtering by `--repo`, making a
single-repo query as slow as a full scan) was caught and fixed during
this pass, not left in. All touched files `py_compile`/`dotnet build`
clean throughout.

**Not done this entry**: actually running a 100-repo (or larger) batch
through the now-scaled pipeline - `--target-total` is parameterized and
`--workers` is wired everywhere it matters, but no real corpus-growth run
has started; re-running the Phase 0 candidate search with a wider
candidate pool (235 rows caps out around 100 repos, not 1000); retiring
`Azure/azure-sdk-for-python`'s now-unnecessary per-run exclusion in
`results/repos/excluded_repos.csv` (the cohesion-sampling fix makes it
safe to remove, just not done here); the lighter secondary storage-lifecycle
policy for `data/snapshots/` (documented as a real follow-up in
`storage_lifecycle.py`'s own module docstring, not built).

