# Project Status — 2026-07-29 (updated: first analysis complete)

*Companion to `ProjectUpdate.md` (the raw chronological build log — kept
append-only, dated entries). This doc is a clean, current snapshot,
structured for talking through out loud. Full methodology: `Longitudinal.md`.
Full findings with tables and figures: `Results.md`'s "First real analysis"
section and the interactive dashboard linked there.*

## The one-paragraph version

We're measuring whether repo structural health (design/implementation
smells, OO metrics) and PR-level process changes when AI coding agents
start contributing — using an interrupted time series, not a naive
before/after, so ordinary codebase drift doesn't get mistaken for an agent
effect. **Data collection is done and a first analysis has run**: 4 pilot
repos (3 Python via DPy, 1 C# via Designite), segmented regression on the
pre-registered primary metrics, composition-shift and process-metric tests.
Headline: **no consistent cross-repo direction** — real, statistically
significant changes show up almost everywhere, but they point different
ways in different repos, and the split doesn't track language. This is
still N=4 — descriptive of these repos, not a general claim about "AI
agents." `dotnet/aspire` is now dropped from the pilot entirely (both
tracks), leaving 3 Python + 1 C#, not the original 3+2.

## Where each piece stands

| Piece | Status |
|---|---|
| Phase 0 — candidate repo filtering | Done, iterating in background |
| Phase 1a — pilot selection & intervention dates | Done |
| Phase 1c — snapshot manifest (which commit per grid point) | Done — 480 rows |
| Phase 1e — snapshot materialization (source on disk) | Done — 399/401 unique commits |
| Phase 1d — structural metrics (DPy + Designite) | **Done** — 351 pooled rows, 4 repos |
| Phase 1b — PR-level process metrics | **Done, with one exclusion** |
| First analysis (segmented regression, composition, process) | **Done — see `Results.md`** |

## 1. The pilot (now 4 repos, not 5)

| repo | language | agent PRs | intervention date | structural data | process (Track B) data |
|---|---|---|---|---|---|
| crewAIInc/crewAI | Python | 327 | 2024-12-27 | 72/74 rows | full |
| airbytehq/airbyte | Python | 218 | 2025-01-21 | 96/96 rows | full |
| mlflow/mlflow | Python | 91 | 2025-05-21 | 96/96 rows | full |
| wieslawsoltes/Dock | C# | 309 | 2025-06-25 | 87/96 rows (post-period thin, below) | full |
| ~~dotnet/aspire~~ | ~~C#~~ | — | — | **dropped** | **dropped** |

`dotnet/aspire` is out of the pilot entirely now, not just Track B as of
07-28. Track A (structural) hit its own, separate blocker: Designite can't
open any of aspire's history cleanly — early commits fail via its Arcade
bootstrap (every project reports 0 source files without a private-feed
restore), recent commits need a preview .NET SDK not installed. No clean
middle band was found. See `DESIGNITE_TASK.md` (on the
`designite-sln-support` branch) for the full investigation. **This pilot is
3 Python + 1 C#, not the original 3+2** — an open methodology question, not
resolved (§ Open decisions).

## 2. Structural metrics — done

| repo | tool | rows ok | notes |
|---|---|---|---|
| crewAIInc/crewAI | DPy | 72/74 | 2 permanent gaps — NTFS-illegal filename in a test fixture, Windows-only limitation |
| airbytehq/airbyte | DPy | 96/96 | complete |
| mlflow/mlflow | DPy | 96/96 | complete |
| wieslawsoltes/Dock | Designite | 87/96 | 9 fail — Dock migrated `Dock.sln`→`Dock.slnx` on 2025-12-25, unsupported by the installed Designite build |

**351 pooled rows** across both tracks (A1 fixed-calendar, A2 event-window),
consolidated in `results/analysis/07-29-pooled-structural-metrics.csv`. DPy
ran in the main checkout; Designite was built and run on a separate branch
(`designite-sln-support`, worktree `Codebook_AIDev-designite`) to avoid
touching the multi-day DPy background job — **not yet merged to `main`**,
so Dock's data currently has to be read cross-checkout (done for the
2026-07-29 analysis; worth merging so it lives in one place).

**Dock's post-intervention data is thin** — only 6 of a possible ~19 A1
points, because the `.slnx` gap above starts just 6 months after Dock's own
intervention date (2025-06-25). Its slope estimates use those 6 points same
as everything else; its level-change comparisons rest on less data than the
three Python repos. Recovering the rest needs a newer Designite build with
`.slnx` support, or a `.slnx`→`.sln` conversion step — neither started.

**Schema note that changed the plan**: Designite's output was written to
pool onto the *same* canonical column names DPy already uses. The
cross-language adapter step earlier planning assumed would be needed
(`Results.md`'s 07-28 "Assumption 1") **wasn't** — the two CSVs concatenate
directly.

## 3. PR-level process metrics — done, one exclusion

212/265 query units ok (all 53 failures on `dotnet/aspire` — Microsoft's
`dotnet` org blocks fine-grained PATs at the org-policy level, confirmed
directly, unrelated to any code issue). `wieslawsoltes/Dock` is the sole C#
repo for Track B, same imbalance as Track A now. Captured: PR identity,
timestamps, comment counts. **Still not captured**: diff size, deeper
review stats — needs a per-PR follow-up call, not yet built.

## 4. First analysis — done (2026-07-29)

Ran the pre-registered tests from `Longitudinal.md` §9 for the first time.
Full tables and an interactive dashboard (hover for exact values, every
chart has a data table) are in `Results.md`'s "First real analysis" section:
https://claude.ai/code/artifact/5ae706c9-eb9a-458a-9880-76be980d9164

**What it found, in brief:**
- **Segmented regression (RQ1)**: design-smell density shows a
  statistically significant *slope* change post-intervention in all 4
  repos — but 2 trend worse (airbyte, crewAI) and 2 trend better (mlflow,
  Dock). That split is *within* the Python repos, not a Python-vs-C#
  divide. No repo shows a significant *level* jump on this metric.
- **Implementation-smell density**: airbyte and mlflow both show a real
  drop right at the intervention; Dock shows the opposite — the sharpest
  upward slope in the whole table.
- **Composition (RQ2)**: design smells' share of all smells shifts
  significantly in all 4 repos (p<.01) — shrinking in 3 (airbyte, mlflow,
  Dock), growing in crewAI.
- **Process (RQ3)**: crewAI is the only repo with a significant
  merge-latency change (a large drop); airbyte and crewAI both show
  significantly more review comments per PR post-intervention; mlflow shows
  no process change on either metric.
- **Cross-language (RQ4)**: Dock (the one C# repo) doesn't stand apart from
  the Python repos on any metric — but n=1 C# repo barely tests this.
- **Dosage (RQ5)**: agent-PR count doesn't predict effect direction or size
  across the 4 repos — if anything runs backwards. Inconclusive at N=4, kept
  as a covariate for when there's enough repos to regress properly.

**The honest read**: real, non-random signal is showing up almost
everywhere, but it's repo-specific, not a uniform "agents help" or "agents
hurt" story, and doesn't cleanly split by language either. That's a
legitimate finding on its own, not a failure to find one — but it's N=4,
unadjusted for the 12 significance tests RQ1 alone ran, with no matched
non-adopting comparison arm yet. Not paper-ready; a real first look.

## 5. What's still open

Ranked by what would change the analysis most:

1. **`dotnet/aspire`'s exclusion / the 3+1 language imbalance** — needs a
   methodology call: accept and disclose, or bring in a second C# repo that
   doesn't hit either of aspire's blockers.
2. **Dock's `.slnx` gap** — recovering its censored post-period needs a
   Designite build update or a conversion step.
3. **Merging `designite-sln-support` to `main`** — housekeeping, but blocks
   a clean single-checkout re-run of the analysis.
4. **Track B's deeper PR stats** (diff size, review detail) — needed to
   extend RQ3 beyond timestamps/comments.
5. **Multiple-comparison correction + a matched non-adopting comparison
   arm** — needed before any of this is a defensible general claim, not
   just a per-repo descriptive result.

## Where things live

- Methodology & full rationale: `writing/Longitudinal.md`
- **Findings, tables, and the dashboard link: `writing/Results.md`**
  ("First real analysis — pilot results" section)
- Raw chronological build log: `writing/ProjectUpdate.md`
- Designite build/decision log: `DESIGNITE_TASK.md` (on `designite-sln-support`)
- Pooled structural data: `results/analysis/07-29-pooled-structural-metrics.csv`
- Regression / composition / process output: `results/analysis/07-29-{segmented-regression-A1,rq2-composition,rq3-process}.csv`
- PR samples: `results/pr_samples/07-28-pr-sample-265.csv`
- Snapshot manifest / materialized source: `results/snapshots/`, `data/snapshots/`
