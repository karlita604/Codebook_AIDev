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

## Full results layout plan (2026-07-28) — Python + C#, assuming clean data

Designite progress check (as of this writing): still **0 real rows** —
`run_designite()` raises `NotImplementedError` unconditionally, blocked on
the same design decision as last reported (needs an actual `.sln`;
materialized Dock/aspire snapshots only contain loose `.cs` files; no .NET
SDK installed either). Every Dock/aspire Track A row currently just logs
`DESIGNITE_EXECUTABLE not set` and moves on — see `ProjectUpdate.md`'s
Phase 1d section. Nothing below is buildable with C# data yet; this section
plans for when it is.

**Assumptions this plan makes** (flagged so it's obvious what has to become
true before each part is buildable):
1. Designite is unblocked and produces the same *category* of output as
   DPy — OO metrics (LOC, WMC, LCOM, Fan-In/Fan-Out, DIT) + design/
   implementation/architecture smells (Designite is the C# tool from the
   same vendor/family as DPy, same taxonomy per `Longitudinal.md` §3) — but
   its raw column names and CSV shape are **unconfirmed** (`parse_tool_output()`
   for Designite is still a stub). A thin adapter mapping Designite's real
   schema onto the same canonical column names DPy already pools to
   (`design_smell_density_per_kloc`, `class_loc_p90`, etc.) is required
   before any chart below can mix languages — not yet built.
2. Track B1/B2 (`results/pr_samples/`) gets the deeper per-PR diff/review
   stats (additions, deletions, review comment counts) that the current
   output doesn't have yet — see `ProjectUpdate.md`'s Phase 1b section
   ("not yet the deeper diff/review stats... left for a later step").
   Without this, the process-metric charts below (§C) have only PR
   timestamps/counts to work with, not PR size.
3. All 437 Track A rows and the full Track B manifest land without
   unresolved errors (Designite's `.sln`/SDK gap and `dotnet/aspire`'s
   Track B exclusion, both above, are the two live exceptions to "clean").

### A. Written structure (paper-shaped, one RQ per subsection)

Mirrors the segmented-regression / Mann-Whitney-Cliff's-delta framing
already sketched at the top of this document and in `Longitudinal.md` §9:

- **RQ1 (primary): Does structural health level-shift when agents arrive?**
  Segmented regression per pre-registered primary metric (design smell
  density, implementation smell density, p90 cyclomatic complexity),
  reporting the level-change and slope-change coefficients with CIs, pooled
  across repos with repo random effects. This is the number the paper's
  abstract hangs on.
- **RQ2: Does smell *composition* shift, not just density?** Design vs.
  implementation vs. architecture split, before/after — tests the "agents
  fix locally, not architecturally" hypothesis (§9).
- **RQ3: Does development *process* change alongside structure?** Track B
  PR size, merge latency, review activity, before vs. after — Mann-Whitney
  U + Cliff's delta per metric (the test already specified at the top of
  this document), separating "development changed" from "code got worse."
- **RQ4: Does the effect generalize across language/tooling (Python vs.
  C#)?** Same RQ1 regression, split by language. A 3/3 Python + 2/2 C#
  agreement is a materially stronger claim than 3/5 mixed — the whole
  reason Track A1/A2 language-pairs the pilot (§3, tool selection).
- **RQ5 (exploratory): Does effect size track dosage?** Agent-PR count and
  per-agent breakdown (already computed in Phase 1a's repo summary) as a
  regression covariate, not just a filter — per the "not yet implemented"
  caveat in `Longitudinal.md` §4.
- **Threats to validity** section, already drafted in `Longitudinal.md` §9
  (selection, detection confounding) — reused near-verbatim, not rewritten.

### B. Figure & table inventory (structural health, Track A)

| # | Type | Data | Shows |
|---|---|---|---|
| Fig 1 | Small multiples, line chart, 5 panels (1/repo) | Track A1, full 2022–2026 grid | Per-repo trend + intervention marker — the descriptive lead-in before any statistical claim |
| Fig 2 | Zoomed line chart, 5 panels | Track A2, weekly ±3mo/monthly ±12mo | Same metrics at event-time resolution — is there an actual jump, or does Fig 1's trend just continue (as crewAI's real data currently suggests, see above) |
| Fig 3 | Forest plot, 1 row/repo × primary metric | Segmented regression output (RQ1) | Level-change + slope-change coefficients with CIs, grouped by language color — the primary result figure |
| Fig 4 | Stacked area, per repo or pooled | Design/impl/(arch, once Designite unblocks) smell counts over time | RQ2 — composition shift test |
| Fig 5 | Box/violin, before vs. after, paired per repo | Method LOC, cyclomatic complexity (p50/p90 per §9 — heavy-tailed) | Distribution shape, not just a mean line |
| Fig 6 | Small multiples grouped by language (3 Python vs. 2 C#) | Same primary metrics as Fig 1/3 | RQ4 — the cross-language comparison; this is the figure that most depends on the Designite-schema adapter (Assumption 1) existing |
| Table 1 | Coverage/completeness matrix, repo × track × month | `is_stale`/`no_prior_commit`/materialization + Designite-blocked rows | What fraction of the nominal grid is real data vs. gap, per repo — belongs early in the results section so readers can calibrate confidence in everything after it |
| Table 2 | Descriptive stats, repo × metric, pre vs. post | Track A pooled output | The plain-numbers table Fig 1–3 visualize — needed for peer review / replication even where a chart exists |

### C. Figure & table inventory (process, Track B — needs Assumption 2)

| # | Type | Data | Shows |
|---|---|---|---|
| Fig 7 | Box/violin, before vs. after, per repo | PR size (additions+deletions), merge latency, review-comment count | RQ3 — paired with the Mann-Whitney U + Cliff's delta test already specified at the top of this doc |
| Fig 8 | Bar chart, before vs. after | Reverted-commit rate, issue open/close ratio, contributor concentration (bus factor) | Secondary process indicators from `Longitudinal.md` §9's process metric list |
| Table 3 | Test-statistic table, repo × metric | Mann-Whitney U, p-value, Cliff's delta + magnitude label | The actual numbers Fig 7/8 are summarizing — required alongside the charts, not instead of them |

### D. Cross-language normalization (the actual blocker for Fig 6, Table 2 split by language)

DPy's pooled schema (`design_smell_density_per_kloc`, `class_loc_p90`, etc.,
confirmed in `long_analysis.py`'s `parse_tool_output()`) is Python-specific
in its raw column names even though the *concepts* are shared with
Designite. Before any chart mixes Python and C# repos, a canonical schema
needs both tools' output mapped onto it — e.g. Designite's smell-category
names may not match DPy's 1:1 (different vendor tooling versions, possibly
different smell catalogs even within the same "family"). This mapping is
**not yet started** and should happen as its own step once Designite
produces any real output at all, not guessed at now.

### E. What's buildable today vs. blocked

- **Buildable now, Python-only, partial data:** Fig 1/2/5 for crewAI
  (complete), partial for airbyte/mlflow (still running) — see the "First
  real look" section above for a manual first pass at Fig 1/2.
- **Blocked on the current DPy run finishing:** Fig 3/4, Table 2 (need the
  full Python-side series before segmented regression or composition
  trends mean anything, even Python-only).
- **Blocked on Designite (Assumption 1):** Fig 6, the C# half of Table 1/2,
  any RQ4 claim at all.
- **Blocked on Track B's deeper stats (Assumption 2):** Fig 7/8, Table 3,
  RQ3 entirely.
- **Buildable now, no data dependency:** Table 1's Python-side rows (coverage
  is already knowable from what's landed vs. the manifest), the RQ
  structure in §A (a writing task, not a data task).

## First real analysis — pilot results (2026-07-29)

> **Status as of 2026-08-04: preliminary, N=4, not re-run since.** Everything
> below is real data run through the pre-registered tests, not a smoke test —
> but it's still a 4-repo pilot (3 Python + 1 C#), and the project has since
> moved into Phase 2 (expanding to a 20-repo minimum, see `ProjectStatus.md`
> and `ProjectUpdate.md`'s 2026-08-04 entry). The new repos being collected
> for Phase 2 are **not** included in anything below, and won't be until an
> in-house metrics tool (`Writing/InHouseTooling.md`) exists to analyze them
> without DPy/Designite's trial-license LOC caps. Every number and caveat
> below stays as originally recorded — including the "no consistent
> cross-repo direction" headline — because it's real methodology and a real
> (if inconclusive) first result, not because it's the study's final answer.

Everything above this line was planning, written before real data existed.
DPy's run finished for all 3 Python repos (crewAI, airbyte, mlflow) and,
separately, Designite was unblocked on a parallel branch
(`designite-sln-support`, see `DESIGNITE_TASK.md`) and produced real output
for `wieslawsoltes/Dock`. This section is the first actual analysis —
**still a pilot with N=4 repos**, not a paper-ready result, but real numbers
run through the pre-registered tests from `Longitudinal.md` §9 and the
Mann-Whitney/Cliff's-delta framing at the top of this document.

**Interactive dashboard with all figures below (hover for exact values,
every chart has a data table):**
https://claude.ai/code/artifact/5ae706c9-eb9a-458a-9880-76be980d9164

### Correction to the plan above

§D's "Assumption 1" — that mixing Python and C# would need a schema-mapping
adapter — **turned out to be unnecessary**. `parse_tool_output()`'s
Designite branch was written to pool onto the *same* canonical column names
DPy already used (`design_smell_density_per_kloc`, `cyclomatic_complexity_p90`,
etc. — see `DESIGNITE_TASK.md`'s metrics table), so the two tools' output
concatenates directly. No adapter step was needed once it came time to
actually do it.

### Data going into this analysis

| Source | Rows | Repos |
|---|---|---|
| DPy (Python), main checkout, all 3 workers deduped | 264 ok | crewAI (72/74, 2 permanent NTFS gaps), airbyte (96/96), mlflow (96/96) |
| Designite (C#), `designite-sln-support` branch | 87 ok | Dock only (87/96 — 9 rows fail on Dock's post-2025-12-25 `.slnx` migration, unsupported by the installed Designite build) |
| **Pooled** (`results/analysis/07-29-pooled-structural-metrics.csv`) | **351** | 4 repos × {A1, A2} |

`dotnet/aspire` is **not** in this analysis at all — dropped from the C#
arm entirely (decision 2026-07-28, `DESIGNITE_TASK.md` §5: no clean band of
its history opens under Designite/MSBuildWorkspace without replicating its
Arcade bootstrap). This pilot is now **3 Python + 1 C#**, not 3+2, on both
the structural arm and the process arm (Track B already excluded aspire for
the org-policy reason logged 2026-07-28).

**Read the Dock numbers carefully.** Its post-intervention window (after
2025-06-25) is heavily left-censored: only 6 of a possible ~19 A1 points
have real data, because Designite goes blind the moment Dock migrates to
`.slnx` on 2025-12-25 — 6 months after its own intervention date. Dock's
*slope* estimates below use those 6 points same as everything else; its
*level* comparisons rest on a thinner post-period than the three Python
repos.

### RQ1 — segmented regression (Track A1, primary metrics)

Model per repo per metric: `metric ~ time + post + time_since_intervention×post`
(closed-form OLS, 95% CI via normal approximation). Full table:
`results/analysis/07-29-segmented-regression-A1.csv`.

| Repo | Lang | Metric | Level Δ (p) | Slope Δ /mo (p) |
|---|---|---|---|---|
| airbyte | Python | design smells/KLOC | +0.02 (.97) | **+0.167 (.002)** |
| crewAI | Python | design smells/KLOC | +1.78 (.27) | **+0.406 (.040)** |
| mlflow | Python | design smells/KLOC | +0.39 (.68) | **−0.302 (.048)** |
| Dock | C# | design smells/KLOC | +0.53 (.60) | **−0.899 (.003)** |
| airbyte | Python | impl. smells/KLOC | **−9.01 (<.001)** | −0.09 (.55) |
| crewAI | Python | impl. smells/KLOC | −2.28 (.25) | +0.46 (.06) |
| mlflow | Python | impl. smells/KLOC | **−2.74 (.006)** | **+0.551 (<.001)** |
| Dock | C# | impl. smells/KLOC | +1.69 (.13) | **+2.835 (<.001)** |
| airbyte | Python | CC p90 | ~0 (n/a — flat) | ~0 (n/a — flat) |
| crewAI | Python | CC p90 | −0.66 (.06) | **−0.145 (.001)** |
| mlflow | Python | CC p90 | **+1.22 (<.001)** | **−0.130 (<.001)** |
| Dock | C# | CC p90 | **−1.08 (.002)** | −0.02 (.82) |

**Headline: no repo shows a clean "agents made everything worse" or
"agents made everything better" pattern, and the four repos don't even
agree with each other.** For design-smell density, every repo shows a
*significant slope change* (4/4, p<.05) but the sign splits 2-and-2:
airbyte and crewAI trend worse after their intervention date; mlflow and
Dock trend better. That 2/2 split is *within* the 3 Python repos, not a
Python-vs-C# divide — Dock (the only C# repo) lands on the "improving"
side with mlflow, not off on its own. None of the 4 *level* changes
(the jump right at the intervention month) are significant for this
metric — whatever's happening plays out as a trend shift, not a discontinuity.

Implementation-smell density tells a messier story: airbyte and mlflow both
show a real, significant *drop* right at the intervention (airbyte
−9.0/KLOC, mlflow −2.7/KLOC), but Dock shows the opposite — a sharp,
significant *upward* slope afterward (+2.8/KLOC per month, the largest
coefficient in the table). crewAI shows neither effect clearly.

`airbyte`'s cyclomatic-complexity p90 is a flat constant (3.0) for **all 51
months** in this window — confirmed against the raw per-function CC values,
not a pooling bug — so there's no variance for a regression to explain
there; treat that cell as "no signal available," not "no effect." Where CC
p90 *does* move, the pattern is repo-specific again: mlflow shows a real
jump right at its intervention (+1.22, p<10⁻¹¹) immediately followed by a
significant declining slope (as if the jump got walked back over time);
Dock shows a significant *drop* at its intervention with no slope change
after; crewAI shows a gradual improving slope with no discrete jump.

### RQ2 — smell composition shift

Design smells' share of all smells (design + implementation), pre vs. post,
Mann-Whitney U + Cliff's δ (`results/analysis/07-29-rq2-composition.csv`):

| Repo | Design share, pre → post | % change | p | Cliff's δ |
|---|---|---|---|---|
| airbyte | 19.6% → 11.9% | **−39.0%** | <.001 | 1.00 (large) |
| mlflow | 18.5% → 17.3% | **−6.3%** | .006 | 0.57 (large) |
| Dock | 61.7% → 44.2% | **−28.4%** | <.001 | 0.87 (large) |
| crewAI | 9.2% → 10.8% | **+18.0%** | <.001 | −0.79 (large) |

All four shifts are statistically significant (all p<.01) — composition
genuinely moves, not just density — but again 3 repos move one way
(design's share *shrinks* — implementation smells grow disproportionately)
and crewAI moves the other way. Dock's baseline is structurally different
from the Python repos (61.7% design-smell share vs. ~9–20%), consistent
with Designite and DPy having different smell catalogs/thresholds per
language and tool family (`Longitudinal.md` §9's detection-confounding
threat to validity) — the *within-repo* before/after comparison is still
valid, but don't compare Dock's absolute share to the Python repos'.

### RQ3 — process metrics (Track B1, PR-level)

Merge latency and review-comment counts, pre vs. post, per repo
(`results/analysis/07-29-rq3-process.csv`). `dotnet/aspire` has no Track B
data at all (org-policy token block, logged 2026-07-28) and isn't in this
table.

| Repo | Merge latency, median pre→post (hrs) | p | Review comments, median pre→post | p |
|---|---|---|---|---|
| airbyte | 26.1 → 34.5 | .61 (n.s.) | 2 → 4 | **<.001** |
| crewAI | 21.9 → **6.2** | **.022** | 0 → 1 | **<.001** |
| mlflow | 12.8 → 15.0 | .83 (n.s.) | 1 → 1 | .69 (n.s.) |

crewAI is the only repo with a significant merge-latency shift, and it's a
large drop — PRs merge over 3× faster post-intervention. airbyte and crewAI
both show significantly more review comments per PR after; mlflow shows no
process change on either metric. PR volume per monthly window didn't move
significantly for any repo (all p>.07). The tightly-matched ±10-PR window
right around the intervention (Track B2) adds one more real signal: Dock's
merge latency drops sharply right at the event (0.26h → 0.03h median,
p=.023) — but on n=7/9 PRs, and Dock already merges in under an hour
typically, so treat this as suggestive, not solid.

### RQ4 — does it generalize across language? (first look, n=1 C# repo)

Now unblocked (see "Correction to the plan" above), but with exactly one
C# repo this is barely a test — a data point, not a comparison.  What it
shows: **Dock does not stand apart from the Python repos.** On design-smell
density it lands with mlflow on the "improving" side; on implementation
smells it has the single largest post-intervention slope increase in the
whole table. There's no sign here that C# behaves systematically
differently from Python — but disproving that needs more than 1 C# repo,
and this doesn't do that.

### RQ5 — does effect track dosage? (exploratory, inconclusive)

Regressed nothing formally — just checked whether agent-PR count
(`agent_pr_count` from `results/repos/07-21-repo-summary-235.csv`) lines up
with the design-smell slope-change direction/magnitude above:

| Repo | Agent PRs | Design-smell slope Δ/mo |
|---|---|---|
| Dock | 309 | −0.899 (most improving) |
| crewAI | 327 | +0.406 (most worsening) |
| airbyte | 218 | +0.167 |
| mlflow | 91 | −0.302 |

If anything this runs backwards from a naive "more agent activity, more
effect" story — the two highest-dosage repos land on opposite ends. With
N=4 this isn't evidence of anything, just a flag that dosage isn't an
obvious explainer for which way a repo moved, so it's worth keeping as a
real covariate (per `Longitudinal.md` §4) once there's enough repos to
regress it properly.

### Caveats that apply to everything above

- **N=4 repos.** Every p-value and Cliff's δ above describes *that repo's*
  own before/after series — nothing here pools across repos with random
  effects, and nothing here should be read as a general claim about "AI
  agents." Twelve tests ran for RQ1 alone, unadjusted for multiple
  comparisons — this is a first pass, not the pre-registered final analysis.
- **No matched non-adopting comparison arm yet** (`Longitudinal.md` §9) —
  everything here is ITS, not difference-in-differences. A repo-wide drift
  that happens to coincide with a repo's intervention date can't be fully
  ruled out from this data alone.
- **Dock's post-period is thin** (6 A1 points) for the reason above —
  weight its level-change numbers accordingly.
- **crewAI's pre-period is short** (n=14 vs. 37–42 for the others) — its
  repo history barely predates the study window, plus 2 permanently
  unmaterializable commits (NTFS filename gap, `Longitudinal.md` §7–8).
- **airbyte's CC p90 is degenerate** in this window (constant at 3.0) —
  not a real null result, just no variance for that one metric/repo pair.
- **Detection confounding is real and uncontrolled**: Dock's design-smell
  share (~50%+) vs. the Python repos' (~10-20%) likely reflects
  DPy/Designite tooling differences as much as real structural difference —
  cross-tool absolute comparisons are unreliable; within-repo before/after
  comparisons (what every test above actually runs) are not.

## In-house tool validation — Phase A (Python OO metrics) vs. DPy (2026-08-10)

> **Status: complete.** `pool_inhouse_metrics.py` ran against all three
> pilot Python repos' materialized snapshots (crewAI + crewAI-tools,
> airbyte, mlflow) — airbyte and mlflow finished at 96/96 real rows each,
> no errors. **All 264 pilot Python rows join against DPy's ground truth
> (100% join rate)** — the numbers below are final for this pilot, not a
> partial snapshot. See `src/inhouse/validate_against_pilot.py` and
> `results/analysis/08-10-inhouse-validation-report.csv`.

Methodology: `validate_against_pilot.py` joins the in-house output against
the real pilot's DPy ground truth (`07-29-pooled-structural-metrics.csv`,
filtered to `language == "Python"`) on `(repo_id, track, target_date,
commit_sha)`, then reports mean diff / mean %-diff / Spearman correlation
per shared metric:

| Metric | n | Mean diff | Mean %-diff | Spearman r |
|---|---|---|---|---|
| total_loc | 264 | +122,086 | +91.5% | 0.943 |
| n_classes | 264 | +826 | +28.1% | 0.999 |
| n_methods | 264 | +6.8 | +0.1% | **1.000** |
| class_loc_p50 | 264 | +6.9 | +50.5% | 0.899 |
| class_loc_p90 | 264 | +32.9 | +30.6% | 0.954 |
| method_loc_p50 | 264 | +2.1 | +25.2% | 0.942 |
| method_loc_p90 | 264 | +7.0 | +25.4% | 0.984 |
| cyclomatic_complexity_p50 | 264 | 0.0 | 0.0% | n/a (no variance either side) |
| cyclomatic_complexity_p90 | 264 | +0.7 | +20.5% | 0.563 |

**Headline: class/method *counts* track DPy almost perfectly (r=1.000
both), but absolute LOC runs high, and by a very different amount
depending on the repo** — this second part turned out to be the more
important finding, not a simple "our LOC-counting convention differs"
story.

### Two separate causes, not one

1. **A real, expected counting-convention difference**, present even in
   the *least*-affected repo (crewAI, ~1.5x). The in-house engine sums
   whole-file physical line count per module (blank lines, comments,
   imports all included — see `py_metrics.py`'s module docstring); DPy's
   own module-LOC row almost certainly uses a narrower convention (closer
   to non-blank/logical lines). This is the kind of divergence
   `InHouseTooling.md`'s validation plan explicitly anticipated and said
   not to chase exact agreement on.
2. **A second, much larger, repo-specific effect for heavily-chunked
   repos — and this one isn't a convention difference, it's DPy
   undercounting.** By repo (final, all 264 rows joined), the mean
   in-house/DPy LOC ratio is: **airbyte 2.41x, mlflow 1.71x, crewAI
   1.54x** — airbyte's gap is nearly double the other two. Cross-checked
   directly against ground truth
   *outside* either tool: for airbyte's `22ff7e0f` snapshot (2023-08-01),
   `wc -l` over every real `.py` file in the materialized snapshot gives
   **352,776 lines** — matching the in-house tool's own count almost
   exactly (352,778). **DPy's own reported figure for that identical
   commit is 125,111** — about a third of the real total. That one
   snapshot needed **411 separate DPy chunks** (`n_chunks` column,
   `07-29-pooled-structural-metrics.csv`) under DPy's Trial-license
   LOC cap; airbyte's repo-wide average is **~374 chunks/snapshot**, far
   above crewAI's ~30 and above mlflow's ~220 — and the repo-by-repo LOC
   ratio above tracks that chunk count almost exactly (more chunks →
   bigger DPy shortfall). This is consistent with DPy's chunked runs
   silently losing coverage as chunk count grows (matching the general
   instability already logged for these multi-day background jobs —
   the Windows Smart App Control incident, subprocess timeouts,
   `ProjectUpdate.md`'s 2026-07-27/07-28 entries) rather than a labeling
   or convention difference.

**This reframes what "validation" means for airbyte specifically: the
in-house tool's number is the one independently confirmed against raw
`wc -l`, and DPy's pilot output is the one that's short** — not a case of
"the new tool disagrees with ground truth," but a case where the *old*
tool's ground-truth status turns out to be weaker than assumed for the
most heavily-chunked repo in the pilot. This is exactly the class of
problem `InHouseTooling.md`'s original motivation named (LOC-cap chunking
cost and correctness) — it just turned out to also be a *correctness* risk
for DPy's own pilot numbers, not only a *cost* problem for scaling past the
pilot. Worth a note for anyone reading airbyte's absolute LOC/class-count
figures elsewhere in this document: they may be undercounts, not just
"DPy's own convention."

### Where agreement is strong

Class and method **counts** (not their LOC) agree essentially perfectly
(r=1.000, mean %-diff 0.2-15.2%) — chunking affects LOC totals (which sum
across chunks) far less than it affects whether a class/method gets
*counted* at all, since `n_classes`/`n_methods` just need every chunk's
output file to exist, not for every line within it to be captured
correctly. `method_loc_p90`/`class_loc_p50` correlations (0.94, 0.97) are
also strong — the LOC *shape* (relative sizes) tracks DPy well even where
the absolute totals run high.

### Where a real, smaller divergence remains unexplained

`cyclomatic_complexity_p90`'s correlation (0.563) is the weakest of the
metrics that have any variance at all (p50 is degenerate — 0 diff, but
also no variance on either side to correlate, same "no signal available"
situation `Results.md` already flagged for airbyte's own CC p90 in the
pilot's first analysis above). A real, smaller gap plausibly from
differing McCabe counting rules between two independently-built CC
implementations (e.g. whether comprehension `if`s or extra `and`/`or`
operands count, both implemented here — see `ast_common.py`'s
`_CCVisitor` docstring — but DPy's own exact rule set is unconfirmed, per
`InHouseTooling.md`'s original "closed smell catalog" concern extending
even to a metric as standard as CC). Not investigated further this
session.

### Hand-validation bug caught before this run (see `ProjectUpdate.md`'s
2026-08-10 entry for the full story)

A synthetic fixture with hand-computed expected values caught a real bug —
`self.method()` calls were being counted as field accesses — before this
real-data run happened, fixed by excluding a class's own method names from
its field-access scan. A documented, narrower blind spot remains (a
subclass calling an *inherited* method isn't recognized as a call), not
fixed, called out directly in `ast_common.self_attribute_names`'s
docstring rather than silently left as an unstated gap.

## In-house tool validation — Phase B (C# via Roslyn) vs. Designite (2026-08-11)

> **Status: complete.** `pool_inhouse_metrics.py` ran against Dock's full
> 96-row manifest and `dotnet/aspire`'s full 75-row manifest — both
> 100% `ok`, 0 failures. Joined against Designite's real ground truth
> (`07-29-pooled-structural-metrics.csv`, `language == "C#"`): **87/87
> Designite-successful Dock rows join** (the 9 Designite itself failed on
> — its `.slnx` gap — aren't in the ground truth to join against in the
> first place, not a Phase B miss). `dotnet/aspire` has no Designite output
> to validate against at all (excluded from the pilot entirely), so its
> 75/75 successful rows are new data, not a comparison. See
> `src/inhouse/validate_against_pilot.py` and
> `results/analysis/08-11-inhouse-validation-report.csv`.

| Metric | n | Mean diff | Mean %-diff | Spearman r |
|---|---|---|---|---|
| total_loc | 87 | +5,634 | +29.2% | 0.999 |
| n_classes | 87 | −32.1 | −11.5% | 0.998 |
| n_methods | 87 | −134.2 | −14.1% | 0.997 |
| class_loc_p50 | 87 | +3.1 | +16.7% | 0.946 |
| class_loc_p90 | 87 | +36.3 | +25.7% | 0.920 |
| method_loc_p50 | 87 | +2.7 | +82.0% | 0.781 |
| method_loc_p90 | 87 | +6.1 | +32.3% | 0.827 |
| cyclomatic_complexity_p50 | 87 | 0.0 | 0.0% | n/a (no variance either side) |
| cyclomatic_complexity_p90 | 87 | +1.2 | +37.3% | 0.546 |

**Headline: agreement is at least as strong as Phase A's Python validation
— total_loc/n_classes/n_methods all correlate above r=0.997 — and the
class/method-count offset runs the opposite direction from Python's.**
Phase A's Python engine counted *more* classes/methods than DPy (+0.1% to
+28.1%); Phase B's C# engine counts *fewer* than Designite (−11.5% to
−14.1%). The most likely explanation is a documented Designite behavior,
not a Phase B undercount: `DESIGNITE_TASK.md`'s "Known gaps" section notes
that Designite doesn't deduplicate multi-targeted projects (a project
built for more than one target framework gets a full duplicate
`ClassMetrics`/`MethodMetrics` set per framework), so Designite's own raw
counts are the inflated ones on projects that do this, not Phase B's the
deflated ones — plausible given the sign and magnitude, but not
independently re-confirmed this session (e.g. by checking how many of
Dock's projects are actually multi-targeted).

### A manifest bug, not a tool bug — found by the join failing first, not the numbers being wrong

The first real join attempt returned **2/87 matches**, not 87. Before
assuming Phase B was broken, checked what the 2 rows that *did* match had
in common with each other and not the other 94 — they were the only two
where the manifest used for this run (`08-04-repo-snapshot-manifest-2016.csv`,
`latest_manifest()`'s default) happened to resolve the same commit
Designite's original run also got. Comparing that manifest against the
older one used for the pilot's actual Designite run
(`07-21-repo-snapshot-manifest-480.csv`) directly:

| | Old manifest (07-21) | New manifest (08-04) |
|---|---|---|
| Dock unique commits (96 grid rows) | **64** | **2** |
| airbyte unique commits | 95 | 95 |
| crewAI unique commits | 71 | 71 |
| mlflow unique commits | 96 | 96 |
| dotnet/aspire unique commits | 75 | 75 |

Only Dock regressed — every other repo present in both manifest versions
kept its full commit diversity. Root cause, confirmed directly:
`data/repo_cache/wieslawsoltes__Dock`'s local clone is stale, with its
most recent commit dated 2022-01-27. The manifest-generation logic resolves
each grid point to "the closest commit at or before the target date" — for
any target date after 2022-01-27, there's nothing newer in the stale clone
to find, so it keeps returning that same commit. All 64 of the old
manifest's distinct commits are still genuinely materialized on disk
(`data/snapshots/wieslawsoltes__Dock/`), confirming the *old* resolution
was correct and the clone simply hasn't been refreshed since.

Worked around for this validation by pointing `pool_inhouse_metrics.py`'s
`--manifest` flag at the older, correct manifest explicitly — a legitimate
one-off for validating against Designite's already-fixed ground truth, but
not a fix. The underlying stale clone is still stale; anyone running the
in-house tool against Dock using `latest_manifest()`'s default from here
forward will hit the same collapse-to-2-commits problem until
`data/repo_cache/wieslawsoltes__Dock` gets a fresh `git fetch`/backfill.
Logged as an open item in `ProjectStatus.md` §7, not fixed here — it's a
Phase 1c/data-collection bug, not an in-house-tool one, and fixing it
wasn't what this session's work was scoped to.

### Two real wins, both a side effect of never loading a project graph

Neither was the goal of building Phase B — both fell out of the same
architectural choice (syntax-only `CSharpSyntaxTree.ParseText`, no
`.sln`/`MSBuildWorkspace` load) for a different reason (avoiding DPy/
Designite's trial-license chunking cost, per `InHouseTooling.md`'s
original motivation):

- **`dotnet/aspire` now has real structural data for the first time this
  project has ever had it.** Designite can't evaluate aspire's project
  graph without replicating its Arcade bootstrap (private-feed restore,
  pinned preview SDKs — `DESIGNITE_TASK.md` §5), so aspire was dropped
  from the pilot entirely, on both Track A and Track B. Phase B doesn't
  need a project graph, so that blocker simply doesn't apply — 75/75 rows,
  `ok`.
- **Dock's post-`.slnx`-migration months are no longer censored.** Designite
  fails on 9/96 Dock rows because it can't read `.slnx` (Dock migrated
  2025-12-25, six months after its own 2025-06-25 intervention date) —
  flagged repeatedly in this document's caveats as thinning exactly the
  back half of Dock's post-intervention window. Phase B doesn't touch
  `.sln`/`.slnx` either way, so all 96/96 Dock rows read cleanly, including
  every post-migration month.

Neither of these retroactively changes the segmented-regression numbers in
the "First real analysis" section above — those were run on Designite's
real output, not Phase B's, and re-running RQ1-RQ5 on the now-available
in-house Dock/aspire data is real follow-up work, not done this session.
What it does mean: the two biggest data-completeness gaps in the pilot's
C# arm (aspire's exclusion, Dock's thin post-period) both have a concrete,
already-working fix sitting in `src/inhouse/roslyn_tool/` — a methodology
decision away from being used, not an engineering one.

### Hand-validation bug caught before this run (see `ProjectUpdate.md`'s 2026-08-11 entry for the full story)

The same synthetic-fixture approach Phase A used, translated to C#, caught
a different and more severe bug before any real data was touched: C#
constructors (`ConstructorDeclarationSyntax`) are a sibling type to
ordinary methods (`MethodDeclarationSyntax`), not a subtype, so the first
version of the entity-extraction code silently skipped every constructor -
which would have dropped constructors from NOM/WMC entirely and corrupted
LCOM (a constructor is often the one method that touches every field,
exactly the case LCOM is meant to be sensitive to). Fixed by extracting
`BaseMethodDeclarationSyntax` throughout. A genuine, unplanned advantage
also surfaced during this fixture check: because C# has real field-
declaration syntax, Phase B's LCOM/NOF computation never needed Phase A's
Python-specific `self.method()`-vs-`self.field` disambiguation heuristic in
the first place - it just reads the class's actual declared fields.