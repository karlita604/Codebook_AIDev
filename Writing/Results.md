We record the distribution of ... for the collected .. PRs. To determine whether the ... were significantly different, we perform a Mann-Whitney U Test [30] at a significance level of \alpha = 0.05. We also compute Cliff's delta d [29]


[29] Jeffrey D. Long, Du Feng, and Norman Cliff. 2003. Ordinal Analysis of Behavioral Data. In Handbook of Psychology.
John Wiley & Sons, Inc., Hoboken, NJ, USA, Chapter 25, 635–661.
[30] H. B. Mann and D. R. Whitney. 1947. On a Test of Whether one of Two Random Variables is Stochastically Larger than
the Other. Annals of Mathematical Statistics 18 (1947), 50–60.

## Phase 1d — DPy longitudinal results: planned visualizations (2026-07-27)

Notes on what the DPy metric output (`results/analysis/*-smell-metrics-*.csv`,
one row per `(repo_id, track, target_date, commit_sha)` — see `long_analysis.py`
and `Longitudinal.md` §8/§9) supports, for when enough of the background run
has landed to actually build these.

**Status as of 2026-07-27:** run in progress (`main`, PID in
`logs/phase0/long_analysis.pid`), 18/437 rows done, all `airbytehq/airbyte`
Track A1, 2022-01 through 2023-06 — pre-intervention only (airbyte's
intervention date is 2025-01-21). Nothing below is buildable as a real result
yet; only a sanity-check trend of airbyte's early metrics is possible right
now.

### Core ITS charts (the primary result)

1. **Time series per primary metric per repo (Track A1, full 2022–2026
   grid)** — design smell density, implementation smell density, p90
   cyclomatic complexity (the pre-registered primary metric set, §9), with a
   vertical marker at the repo's `intervention_date`. The headline chart type
   for the study.
2. **Event-window zoom (Track A2, weekly ±3mo / monthly ±12mo)** — same
   metrics at high resolution right around the intervention point, for a
   precise read on whether there's an actual level jump vs. gradual drift
   (this is what A2 exists for — see Longitudinal.md §5).
3. **Segmented regression overlay** — once enough pre/post points exist to
   fit `metric ~ time + intervention + time_since_intervention + covariates`
   (§9), plot raw points + fitted line, annotated with the level-change and
   slope-change coefficients. This is the number the write-up actually hangs
   on.
4. **Small multiples across the 3 Python pilot repos** (crewAI, airbyte,
   mlflow) — same metric, one panel per repo. A level break showing up in
   only 1 of 3 repos is much less convincing than 3/3 or 2/3.

### Secondary / exploratory

5. **Smell composition over time** (stacked area: design vs. implementation
   vs. — once Designite unblocks — architecture) — tests the "agents fix
   locally, not architecturally" hypothesis already flagged in §9.
6. **Before/after distributions** (box/violin, not just a mean line) for
   method LOC and cyclomatic complexity — §9 calls for p50/p90 specifically
   because these are heavy-tailed, so a shape-preserving chart matters more
   than a single trend line here.
7. **Data-completeness panel** — coverage/staleness (rows landed vs.
   expected, `is_stale`/`no_prior_commit`/materialization gaps) per repo per
   month. Refreshes the interactive sample-point timeline artifact built
   earlier in the project, now with real metric coverage instead of just
   manifest sample points.

### Caveat

`arch_smell_count_chunk_scoped` and Fan-In/Fan-Out are **not** safe to plot
as a repo-wide trend as-is — they're computed per-chunk under DPy's Trial
LOC cap (see the 2026-07-27 chunking decision in `Longitudinal.md`), so a
naive line chart of that column would mostly reflect chunk-count artifacts,
not real architecture-level change. Needs either a DPy Professional license
(no chunking, real repo-scoped architecture analysis) or explicit chunk-aware
aggregation before it's trustworthy.