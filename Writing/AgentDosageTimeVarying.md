# Time-varying agent dosage (2026-08-24)

> **Status: full eligible-repo scope (72/79), real data, one naive-significant
> result checked and rejected by repo-stratified permutation.** Branch:
> `fix/track-b-pr-sample-coverage`. Code:
> `src/analysis/agent_dosage_timevarying.py`.

## Why this exists

RQ5 (the pilot, `Results.md`) and `HeterogeneityExplainers.md`'s RQ-H1 both
tested agent dosage as one static number per repo (total `agent_pr_count`)
against RQ1's fitted slope-change coefficient — both came up empty. Neither
asked the more direct question: within a single repo's own post-intervention
window, does the *month-to-month* intensity of agent activity track that
window's own metric trajectory? A repo that front-loads its agent PRs in
month 1 and goes quiet afterward is a different story from one with steady
monthly agent activity throughout — collapsing both to one "total PR count"
erases exactly the variation this asks about.

## Data used

- `results/repos/08-17-aidev-agent-prs-3332.csv` (3,332 rows, 235 repos) —
  the dosage source. **`created_at` runs 2024-12-24 to 2025-07-30**,
  confirmed directly on this exact file at run time (`registry_window()`),
  not assumed from an earlier session's note. Still the latest file
  matching `*-aidev-agent-prs-*.csv` — no newer one exists.
- `results/analysis/08-19-segmented-regression-full-237.csv` (79 repos × 3
  metrics, 237 rows) — defines the eligible-repo set. Same pinned file
  `heterogeneity_explainers.py` uses, for the same reproducibility reason
  (see that module's docstring): a fixed, named snapshot, not a `fc.latest_*()`
  glob that could silently redescribe itself later.
- `segmented_regression.build_full_corpus_dataset()`'s own inputs
  (`08-19-inhouse-metrics-pooled.csv`, `08-19-inhouse-smells-pooled.csv`,
  `08-17-repo-summary-235.csv`) — reused unchanged via that function, not
  re-derived here.
- Track B's PR-comment samples (`07-28-pr-sample-265.csv`,
  `08-04-pr-sample-4990.csv`, and the in-progress
  `08-24-pr-sample-rq1gap-3339.csv`) were **checked, not used** — see
  Design decision 1. At the time of this run: 70 distinct repos across all
  three concatenated files (up from the 15/79 baseline
  `HeterogeneityExplainersPart2.md` measured), and the RQ1-gap-fill
  collection was still actively running against GitHub (2,708/3,339 query
  units done, per its own `-progress.json`) — a real, in-flight coverage
  improvement, not a stale number, but not something this analysis's
  results depend on either way (see below).

## Two design decisions, resolved before writing any code

**1. Raw monthly agent-PR count, not agent-PR share of total monthly PR
volume.** Track B's B1 sampling track already records a real GitHub Search
API `total_count` per query unit (in `*-queries.csv`) — but that count is
scoped to each B1 unit's own 2-day (day 1-2 UTC) sample window, not the full
month. Turning it into a monthly-volume denominator would need extrapolating
a 2-day count across ~30 days, a material and unvalidated within-month-rate-
uniformity assumption, not a reuse of existing data. A real share-based
denominator needs a *new* GitHub Search API collection (full-month
`created:` range queries, count-only — the cheaper fallback named in the
request that motivated this file). Not launched: a Track B gap-fill run was
already active against the same token pool while this was being built (see
Data used above), and stacking a second concurrent collection against it
risked rate-limit contention for a payoff that Design decision 2 shows is
small regardless (median 2 overlapping months per repo leaves little room
for a raw-vs-share distinction to matter). **This is a real scope limitation
of the result below, not a silently-made simplification** — "5 of 5 PRs
that month" and "5 of 500" are treated identically here.

**2. A separate, narrower analysis (option 1), not a change to
`segmented_regression.py` (option 2).** Checked directly before choosing:
of the 79 RQ1-eligible repos, 72 have at least one month where post-
intervention overlaps the registry's observed window at all (1 repo's
intervention postdates the registry entirely, 6 more have zero metric
snapshots landing inside the overlap even though the intervention itself
does), and **only 12/79 have ≥3 distinct overlapping months** — the rest
have 1-2 (median 2 across all three metrics, max 7). A per-repo trend line
needs within-repo variation a single repo mostly doesn't have at this
window's length; a pooled, repo-stratified design (see below) uses what
data exists without requiring it. Keeping RQ1's shared regression untouched
also means this doesn't risk moving any other RQ's already-reported numbers.

## A real bug caught before trusting any number

The first version of this script inner-joined each scoped repo-month
against the registry's monthly-count table. That silently dropped every
registry-covered month with a *true* zero agent-PR count — a month the
registry actually observed and found no agent PRs in — treating it the same
as a month outside the registry's window entirely (unknown, not zero; the
distinction the request that motivated this file explicitly warned against
collapsing). Caught by a suspicious tell: row counts were identical
(118/118/118) across all three metrics, which only happens when dosage-
availability, not each metric's own data availability, is what's actually
filtering rows. Fixed to a left join + explicit zero-fill for registry-
covered months with no counted PR; row counts moved to 162/162/162 and 65→72
repos once corrected. All numbers below reflect the fixed version.

## Coverage

| Metric | Eligible repos | Repos with ≥1 scoped month | ≥2 months | ≥3 months | Repo-months (n) | Median months/repo |
|---|---|---|---|---|---|---|
| All 3 (identical coverage — same repo/window scope, per-metric `dropna` didn't change which rows survived) | 79 | 72 | 49 | 12 | 162 | 2.0 (max 7) |

Output: `results/analysis/08-24-agent-dosage-timevarying-coverage.csv`.

## Result: one naive-significant correlation, and it's a repo-composition artifact — same pattern as three prior findings in this project

Pooled Spearman correlation, monthly agent-PR count vs. that same month's
metric value, across all 162 repo-months:

| Metric | Pooled ρ | Naive p | Stratified-permutation percentile | Stratified p |
|---|---|---|---|---|
| Cyclomatic complexity p90 | **-0.256** | **0.0010** | 76th | **0.485** |
| Design smell density/kLOC | +0.090 | 0.254 | 78th | 0.445 |
| Implementation smell density/kLOC | -0.003 | 0.973 | 22nd | 0.452 |

CC p90's naive pooled correlation looked real: more agent PRs in a given
month associated with *lower* complexity that month, p=0.001. It does not
survive the repo-stratified check. The permutation shuffles each repo's own
`monthly_agent_pr_count` values among that repo's own scoped months —
preserving each repo's marginal dosage level and overall metric level while
breaking any real within-repo month-to-month alignment. The resulting null
is itself centered near the real value (mean ρ=-0.265, std 0.013, real
ρ=-0.256 at the 76th percentile) — meaning the negative pooled correlation
is explained by **which repos** tend to have both higher agent-PR volume and
lower complexity (a between-repo association baked into repo composition),
not by **which months** happened to have more agent activity within a given
repo. This is the same composition-artifact shape this project has now
caught four times (the pilot's mlflow result, RQ-H1's pre-slope/slope-change
relationship, `AgentCodeSurvival.md` Finding 2's deletion rate, and Finding
4's change-entropy result above it) — a naive pooled p<0.05 that repo
composition alone fully explains once controlled for.

The other two metrics don't even clear the naive-pooled bar.

Outputs: `results/analysis/08-24-agent-dosage-timevarying-correlations.csv`,
`08-24-agent-dosage-timevarying-stratified-permutation.csv`.

## Bottom line

**No real time-varying dosage effect found, on any of the three primary
metrics, at this corpus's current scale.** This is a genuine, previously-
untested empty result, not a re-confirmation of RQ5/RQ-H1's static-dosage
null by another route — those asked "does total agent-PR count predict the
overall slope change," this asks "does month-to-month agent activity track
month-to-month metric movement within the same repo," and the answer is
still no. Read together with RQ5 and RQ-H1: this project has now tested
agent dosage as a static per-repo total (twice) and as a time-varying
monthly signal (here) against structural-metric outcomes, in three separate
analyses, and found no real predictive relationship under any framing.

## Caveats specific to this pass

- **Severely power-limited by design, not by an implementation choice**:
  median 2 overlapping months per repo, only 12/79 with ≥3. A repo
  contributing 1 scoped month adds a point to the pooled correlation but
  cannot be meaningfully shuffled in the permutation null (one value has one
  permutation) — it isn't a source of the null's variance the way a
  multi-month repo is, though it isn't dropped either. A wider-coverage
  agent-PR registry (the current one's `created_at` window ends 2025-07-30)
  would meaningfully increase within-repo power in a way this analysis
  cannot on its own.
- **Raw count, not share** (Design decision 1) — a repo with 5 agent PRs out
  of 5 total that month and one with 5 out of 500 are the same "dosage"
  here. If Track B's gap-fill run (still active as of this writing) lands
  full monthly-volume coverage for these 79 repos at some point, or a
  dedicated full-month `total_count`-only collection is run later, a share-
  based version of this same design is buildable without re-deriving
  anything else in this file.
- **A1-track only, same 3 primary metrics as RQ1** — no attempt to test
  dosage against other in-house metrics not part of `segmented_regression.py`'s
  `PRIMARY_METRICS`.
- **`monthly_agent_pr_count` is PR *creation* volume, not necessarily
  "PRs actively being worked" or "PRs merged that month"** — same
  created_at-based convention Track B's B1 grid and the registry itself
  already use elsewhere in this project, not a new definition introduced
  here.
