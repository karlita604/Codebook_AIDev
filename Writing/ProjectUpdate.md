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
- **Phase 1d** (actually running DPy/Designite against the Phase 1c manifest)
  — neither tool is installed yet.
- Open modeling decisions logged in `Longitudinal.md`: A2's weekly/monthly
  windowing and B2's ±10-PR window are defaults, not confirmed; no minimum-
  snapshot-count rule yet for excluding a repo from the regression; whether
  informal (pre-AIDev) agent adoption needs a separate robustness check.
- Phase 0 filtering is still moving under this work (dead-link filter just
  added) — worth re-running Phase 1a once phase 0's candidate list settles,
  to confirm the pilot repos are still representative of the final set.
