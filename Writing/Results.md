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

**Status as of 2026-07-28 ~18:00 UTC** (via `progress_dpy.py`, deduplicated
across all output files): **177/437 rows done (40.5%)**, 3 parallel workers
(`--repo crewAI`, `--repo "airbyte|Dock"`, `--repo "mlflow|aspire"`, see
`ProjectUpdate.md`'s Phase 1d section for the full history). By repo:

| repo | rows done | status |
|---|---|---|
| crewAIInc/crewAI | 72 | **complete** — capped at 72/74 by 2 permanently-unmaterialized commits (Phase 1e, NTFS filename gap), not still running |
| airbytehq/airbyte | 64 | in progress |
| mlflow/mlflow | 41 | in progress |
| wieslawsoltes/Dock | 0 (Designite not wired up) | blocked, see below |
| dotnet/aspire | 0 (Designite not wired up) | blocked, see below |

84 rows are logged as errors, all expected/non-blocking: `DESIGNITE_EXECUTABLE
not set` for every Dock/aspire (C#) row — Designite work is deliberately
deferred (see `ProjectUpdate.md`) — plus the 2 permanent crewAI gaps. 0
unexpected errors. **So Track A results below are Python-only for now**
(crewAI, airbyte, mlflow); C# (Dock, aspire) has zero real DPy output until
Designite is unblocked.

### First real look: crewAI, Track A1 + A2 (complete — 72/72 achievable rows)

crewAI is the only repo with a fully complete series so far, so this is a
first eyeball read, **not** a result — single repo, no formal segmented
regression yet (§9), no cross-repo comparison, no significance test. Pulled
directly from the real pooled output (`design_smell_density_per_kloc`,
Track A1 monthly + Track A2 weekly-around-intervention):

- **Design smell density drifts steadily upward across the whole window**:
  ~6.0/KLOC (Dec 2023) → ~8.3/KLOC right before the 2024-12-27 intervention →
  ~11.0/KLOC by Mar 2026. The slope doesn't visibly change at the
  intervention date.
- **Track A2's weekly resolution right around the intervention shows no
  jump either**: 8.6–8.8/KLOC in the 3 weeks immediately before (Dec 6–20,
  2024) vs. 8.0–8.7/KLOC in the 3 weeks immediately after (Dec 27–Jan 10,
  2025) — the density line crosses the intervention week essentially flat,
  continuing whatever it was already doing.
- **Implementation smell density and p90 cyclomatic complexity show the same
  pattern**: density oscillates 71–85/KLOC with no level break; p90 CC
  climbs 1→4 gradually over 2024 (as the repo grows past its earliest, tiny
  commits) and then holds flat at 4 through nearly the entire post-
  intervention period.

Read cautiously: this is exactly the ambiguity the ITS design (§2 of
`Longitudinal.md`) exists to resolve properly — "already trending up and
kept trending up" vs. "jumped when agents arrived" — and on this one repo,
the eyeball read leans toward the former, not the latter. That's a real
observation worth flagging early, but it's one repo's worth of visual
inspection, not the pre-registered regression the write-up will actually
hang a claim on. Needs airbyte/mlflow/Dock to finish (and Designite unblocked
for Dock/aspire) before any cross-repo pattern means anything.

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