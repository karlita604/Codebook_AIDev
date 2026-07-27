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
logged to the errors CSV rather than crashing. A real (non-dry-run) pass
against `Dock` failed both test rows with a clean, logged
`DESIGNITE_EXECUTABLE not set` error instead of crashing — orchestration
confirmed working end to end, purely blocked on tool install now.

## Visualization

Built an interactive timeline (published as a Claude artifact) showing every
A1/A2 sample point per repo on a shared calendar axis, plus zoomed per-repo
panels resolving the weekly ±3-month window around each intervention point.
Surfaced one methodological wrinkle along the way: Dock's A2 window runs to
2026-06-25, past the study's nominal 2026-03-31 end, since Track A2 extends
±12 months from each repo's *own* intervention date regardless of the overall
window boundary.

## Open items / blocked

- **Phase 1b** (full PR history pull, Track B) — needs `GITHUB_TOKEN`; not yet
  set in this environment. Unauthenticated is 60 req/hr, not viable at scale.
- **Phase 1d** — orchestration built and confirmed working against Phase
  1e's materialized snapshots (435/437 eligible rows resolve); purely
  blocked on installing DPy/Designite now.
- 2 crewAI commits (Phase 1e) will likely never materialize on Windows
  (NTFS-illegal filename in a test fixture) — accept the gap or find a
  Linux/WSL environment to fill it in.
- Open modeling decisions logged in `Longitudinal.md`: A2's weekly/monthly
  windowing and B2's ±10-PR window are defaults, not confirmed; no minimum-
  snapshot-count rule yet for excluding a repo from the regression; whether
  informal (pre-AIDev) agent adoption needs a separate robustness check.

