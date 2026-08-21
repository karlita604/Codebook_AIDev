# RQ-H1 (continued) / RQ-H2 — a real permutation test, and review intensity as a moderator (2026-08-21)

> **Status: first pass, real data, both analyses hand-checked against a
> surprising intermediate result before trusting it (see RQ-H1's
> "hand-check" subsection below).** Not a pre-registered confirmatory
> test - see each section's own caveats. Branch:
> `analysis/review-intensity-and-null-check`, off
> `analysis/heterogeneity-explainers`. Extends the same dashboard
> artifact `HeterogeneityExplainers.md` published (new section, existing
> sections unchanged):
> https://claude.ai/code/artifact/7ae0a6d0-bbea-4fe8-a4f8-2d5f9b61c560

## Why this doc exists

`HeterogeneityExplainers.md` closed with two loose threads, both named
explicitly in its own text as follow-up rather than settled:

1. Its placebo check for the pre-slope/slope-change relationship
   compared the real intervention date against exactly **one** fake cut
   per repo (each repo's own median Track-A1 date) - "a proper p-value
   against a real null, not a one-shot comparison" was flagged as the
   obvious next step, not done that session.
2. Track B's PR-level review-comment counts had never been tested as a
   moderator of RQ1's outcome coefficients at all - a direct test of
   `Motivation.md`'s founding premise (PR review is supposed to gate
   quality collaboratively) specifically for the agentic-PR era.

Both reuse `segmented_regression.py`'s `fit_one`/`run` and
`heterogeneity_explainers.py`'s own loaders/correlation code unchanged,
per this project's established convention - not reimplemented in
parallel. Code: `src/analysis/placebo_permutation_test.py`,
`src/analysis/review_intensity_explainer.py`.

## Data

Same pinning discipline as `HeterogeneityExplainers.md`'s own "Data"
section, for the same reason - checked directly (mtime scan of
`results/analysis/`, `results/repos/`, `results/pr_samples/`) that no
newer dated file had landed since 08-19 before trusting these as fixed,
not moving, targets:

| File | Role |
|---|---|
| `results/analysis/08-19-inhouse-metrics-pooled.csv`, `08-19-inhouse-smells-pooled.csv` | Raw per-snapshot series, via `heterogeneity_explainers.load_raw_pooled()` - RQ-H1's permutation test refits on these directly, at placebo cut dates |
| `results/analysis/08-19-segmented-regression-full-237.csv` | RQ1's real fitted coefficients (both analyses' "real" comparison point) |
| `results/repos/08-17-repo-summary-235.csv` | Repo covariates + real `intervention_date`, via `heterogeneity_explainers.load_joined()`/`load_repo_summary_pinned()` |
| `results/pr_samples/08-04-pr-sample-4990.csv` | RQ-H2 only: PR-level `comments` counts, 4,990 rows, 22 repos - **pilot + Phase-2 21-repo era, not re-collected at 100-repo scale** |
| `results/repos/08-17-aidev-agent-prs-3332.csv` | RQ-H2 only: which PRs are agent-authored (`agent` column), 3,332 rows, 235 repos - no comment counts of its own |

Join keys: `repo_id` throughout (not `full_name`), same rename-hazard
reasoning `HeterogeneityExplainers.md` documents in detail - not
re-litigated here. RQ-H2's PR-comment/agent-PR match additionally joins
on `pr_number`, parsed out of the agent file's `html_url` (no
`pr_number` column there) - checked to parse cleanly on every one of the
3,332 rows before trusting it.

## RQ-H1 continued — a real permutation test for the pre-slope/slope-change relationship

### Method

`HeterogeneityExplainers.md`'s own docstring already named the two
mechanical-coupling threats to this relationship (shared-variance
regressors in the same OLS fit; a noisy series fit twice). Rather than
one placebo point, this draws **300 independent placebo cuts per repo**
- each drawn from that repo's own real Track-A1 snapshot dates, subject
to the identical `min_pre=5`/`min_post=5` feasibility gate `sr.run()`
itself applies - refits the unchanged segmented-regression model at each
draw, and records the pooled + per-metric Spearman ρ between
`slope_pre_coef` and `slope_change_coef` for that draw. 300 draws build
an empirical null distribution; the real ρ (read off the pinned
regression output, not recomputed) is then given an actual empirical
p-value against that distribution, not eyeballed against a single
number.

**A note on what to expect before running this, stated up front because
it changes how to read a null result**: if the mechanical-coupling story
is right, it should hold for *any* reasonable cut point, not just the
median - so this test was expected, going in, to mostly reconfirm the
original doc's finding rather than overturn it. That expectation is
exactly why it's still worth running properly: "indistinguishable from
one arbitrary placebo" is a much weaker claim than "indistinguishable
from 300 arbitrary placebos spanning the feasible range," and if the
real cut *did* turn out to sit outside that fuller null, that would be a
genuine, surprising result - not a foregone one.

### A confound found by hand-checking the first version of this result, before trusting it

The first (and simplest) version of this test draws each repo's placebo
cut **uniformly** from its full feasible range. Run once, it produced a
result that looked immediately reportable - and immediately suspicious
for exactly that reason (this project's own stated culture: hand-check
anything clean before it goes in a headline):

| Metric | Real ρ | Uniform-null mean ρ (std) | Percentile of real | p (empirical, two-sided) |
|---|---|---|---|---|
| `cyclomatic_complexity_p90` | -0.701 | -0.673 (0.054) | 29th | 0.585 |
| `design_smell_density_per_kloc` | -0.602 | **-0.822** (0.042) | 100th | **0.0066** |
| `implementation_smell_density_per_kloc` | -0.712 | **-0.821** (0.036) | 100th | **0.0066** |
| pooled (non-independent) | -0.698 | -0.751 (0.030) | 94.7th | 0.113 |

Read naively, this says the real intervention date's correlation is
**significantly weaker** (less negative) than a random-cut null on two
of three metrics - the opposite of "agents specifically compress
pre-existing trends," and a genuinely new claim `HeterogeneityExplainers.md`
didn't make. Before reporting that, it's worth asking why a uniform
random cut and the real cut would differ at all beyond the mechanism
under test - and they do, in an obvious place once checked directly:

**real intervention dates are heavily pre-loaded relative to each
repo's full observation window.** Across the 79 regression-eligible
repos, the real fit averages **n_pre≈31.8 vs. n_post≈10.1** (pre/post
ratio ≈3.3-3.9x) - agent adoption lands late relative to how much
history is being measured. A cut drawn *uniformly* over the full
feasible index range averages close to a 50/50 split by construction.
An uneven split changes `slope_change_coef`'s own statistical power (a
10-point post-window gives a noisier post-slope estimate than a
45-point one, independent of any agent effect) - so "real ρ is weaker
than the uniform null" is at least partly confounded with "real cuts are
far more lopsided than uniform-null cuts," via ordinary measurement-error
attenuation, not necessarily a fact about the real intervention date
specifically.

### The controlled version: a split-balance-matched null

`feasible_cut_candidates_matched()` restricts each repo's placebo cuts
to a window around that repo's own real split position (`k_real ± max(3,
round(0.15·L))` - averaging ~11 candidate dates per repo, vs. ~29 for
the uniform version, 87/92 repos retaining at least one valid candidate)
- varying the exact placebo date, with no connection to any real
agent-PR event, while holding the pre/post statistical-power profile
approximately fixed at the real value. Same 300 draws, same refit,
same comparison:

| Metric | Real ρ | Matched-null mean ρ (std) | Percentile of real | p (empirical, two-sided) |
|---|---|---|---|---|
| `cyclomatic_complexity_p90` | -0.701 | -0.639 (0.048) | 12th | 0.246 |
| `design_smell_density_per_kloc` | -0.602 | -0.710 (0.040) | 99.3rd | **0.0199** |
| `implementation_smell_density_per_kloc` | -0.712 | -0.746 (0.036) | 83rd | 0.346 |
| **pooled (non-independent)** | **-0.698** | **-0.705 (0.028)** | **57.3rd** | **0.857** |

### Result: mostly confirms and strengthens the original finding - with one narrower, real exception, in the opposite direction from what "residual agent effect" would predict

**The pooled test - the number that best answers "does the real
intervention date behave differently from an arbitrary same-shaped cut,
overall" - is not significant (p=0.857, real ρ sits almost exactly at
the null's own mean).** Two of three individual metrics
(`cyclomatic_complexity_p90`, `implementation_smell_density_per_kloc`)
are also not significant once split-balance is controlled for. This is
the **stronger, more defensible version of the prior session's finding**
the original placebo check's own "practical implication" asked for: not
"one arbitrary cut looks similar," but "300 cuts spanning the feasible
range, matched to the real split's own statistical power, look similar
- the real intervention date is not doing anything a same-shaped
arbitrary cut wouldn't."

**`design_smell_density_per_kloc` is the one exception, and it survives
the confound check** (p=0.0066 uniform → p=0.0199 matched - weaker, but
still below .05, one of 4 tests run in this pass, unadjusted). This
*is* a real, new result relative to `HeterogeneityExplainers.md` - but
reading it as "a residual agent effect on top of the mechanical
coupling" would get the direction backwards. The real correlation
(-0.602) is **weaker** than the matched null's (-0.710), not stronger:
real intervention dates for design-smell density show *less* of the
"steep pre-trend triggers a compensating post-trend change" pattern than
an arbitrary same-shaped cut in that repo's own history would produce.
The honest reading isn't "agents dampen pre-existing design-smell
trends more than chance" - it's closer to "whatever is different about
design-smell trajectories specifically around the real agent-adoption
date, it's *less* mechanically self-correcting than a same-shaped random
split, not more." That's a real update worth flagging as a lead, not a
confirmed mechanism - single test, p just under .02, one of 4 metrics/
pooled comparisons in this pass.

**Answering the question this doc's own commissioning note asked
("would this not change anything because intervention points won't
change the trend overall?")**: mostly right, and now demonstrated rather
than assumed - the mechanical-coupling artifact really is a property of
*splitting a noisy series in two*, largely independent of *where* the
split falls, which is exactly why 2 of 3 metrics and the pooled test
land the real cut squarely inside a 300-draw null. Where that
expectation *doesn't* fully hold (design-smell density) it doesn't hold
in the direction "agents reverse trends" would predict either - it's a
narrower, different, and smaller-magnitude puzzle than the doc's closing
"practical implication" anticipated finding.

### Caveats

- **Two null strategies given deliberately, not one silently picked** -
  the uniform null's headline-looking result was a confound
  (split-balance), found by hand-checking before reporting, not by
  running the "right" test first. Both are kept in the committed output
  so this reasoning is auditable, not asserted.
- 300 draws per null strategy (600 total refits of the full 79-92 repo
  corpus x 3 metrics) - enough for p-values to a ±0.003 resolution
  (`1/(300+1)`), not enough to distinguish e.g. p=0.02 from p=0.01
  precisely. `N_DRAWS` is a named constant in the script, cheap to raise
  if a specific borderline number needs tighter resolution.
- Same N=79-repos-x-3-metrics non-independence caveat as
  `HeterogeneityExplainers.md` throughout - the pooled row is the
  headline for exactly this reason, not the per-metric rows in
  isolation.
- The matched-null window (`±max(3, 15% of series length)`) is one
  reasonable choice, not the only one - a tighter window would track the
  real split even more closely (at the cost of fewer, more repetitive
  candidate dates per repo); this wasn't swept, flagged as a modeling
  choice rather than a finding in itself.

Outputs: `results/analysis/08-21-placebo-permutation-null-draws.csv`
(600 draw-level rows), `08-21-placebo-permutation-summary.csv` (the two
tables above).

## RQ-H2 — review intensity as a moderator of RQ1's outcome coefficients

### Motivation

`Motivation.md`'s founding premise: "the core premise of using pull
requests and code review as a system is to improve the software system
[...] collaboratively with multiple points to catch bugs." This is the
first direct test of that premise for agent-authored PRs specifically -
does more human review scrutiny around a repo's agent PRs associate with
a better-behaved (or at least different-signed) post-intervention
structural trend than less-reviewed repos show?

### Data availability - checked first, not assumed

Two real gaps, neither known before checking directly:

1. **Track B's PR-comment sample predates the 100-repo scaling run.**
   The only file with a `comments` column
   (`results/pr_samples/08-04-pr-sample-4990.csv`) is the pilot + Phase-2
   21-repo era's window sample - 22 repos total, not the 100-repo
   corpus the current regression (`08-19-segmented-regression-full-237.csv`,
   79 regression-eligible repos) runs against. `ProjectStatus.md`'s own
   item 3 and item 5 already flagged Track B process metrics as
   pilot-scoped and PR-review detail as "still not built" - confirmed
   directly here rather than re-asserted.
2. **The PR-sample file doesn't flag which sampled PRs are agent-authored.**
   It's a calendar-window sample of *any* PR near each repo's
   intervention date (Track B1/B2), not filtered to agent PRs. Agent
   authorship lives in a separate file
   (`results/repos/08-17-aidev-agent-prs-3332.csv`) with no comment
   counts of its own. The two only become useful together after an
   explicit `(repo_id, pr_number)` join - 6 duplicate-PR groups in the
   sample (a PR window-sampled twice under different tracks) were
   checked to agree on comment count before being collapsed to one row
   each, and the agent file's `pr_number` (absent as a column) was
   parsed out of every one of its 3,332 `html_url`s and confirmed to
   parse cleanly before trusting the join.

**Real coverage after both fixes, restricted to the 79 regression-eligible
repos: 15 of 79 (19%), 109 matched agent-PR rows total, 2-20 PRs per
covered repo** (full per-repo table:
`results/analysis/08-21-review-intensity-coverage.csv`). This is
genuinely partial - reported as an N=15 exploratory pass on the repos
that happen to have data, not extrapolated to the other 64. **Not run
this session**: closing this gap for the other 64 repos would need a
fresh `src/collection/pr_sampling_pipeline.py` run scoped to their
intervention windows - that needs `GITHUB_TOKEN` and hits GitHub's API
rate limits at real cost across 64 repos' worth of PR history. Flagged
here as a cost to weigh, not run silently and not skipped without
saying so.

### Method

For each of the 15 covered repos: mean and median `comments` across its
matched agent-authored PRs, plus the raw matched-PR count (`log1p`'d as
a dosage-style covariate). Joined onto `heterogeneity_explainers.load_joined()`'s
own outcome table by `repo_id` (not `full_name`, same rename-hazard
discipline as RQ-H1) - 15 repos x 3 metrics = 45 rows. Two tests, both
reusing this project's established small-n conventions: Spearman
correlation (continuous review-intensity measures vs. `level_change_coef`/
`slope_change_coef`, per metric + pooled, same shape as
`heterogeneity_explainers.pairwise_correlations`) and a median-comments
high/low split (Mann-Whitney + Cliff's δ, same shape as
`heterogeneity_explainers.language_split_test`).

### Result: no clean signal in the correlations; one modest, hand-checked lead in the split test

**24 Spearman tests (3 covariates x 2 outcomes x 4 metric groups), all
n=15 (n=45 pooled): none reach p<0.05.** The strongest is
`implementation_smell_density_per_kloc`'s `level_change_coef` vs.
`mean_comments` (ρ=-0.43, p=0.11, n=15) - a plausible-shaped lead (more
review, smaller design/implementation-smell jump at intervention) but
not close to significant at this n. Full table:
`results/analysis/08-21-review-intensity-correlations.csv`.

**One median-split result clears p<0.05**:
`implementation_smell_density_per_kloc`'s `level_change_coef`, high- vs.
low-review-intensity repos (split at median `mean_comments`=2.67, n=7
high / 8 low), Mann-Whitney p=0.029, Cliff's δ=-0.68 ("large" by Romano
et al.'s convention). High-review repos cluster near zero-to-negative
at the intervention jump (median -0.016); low-review repos skew
noticeably positive (median 0.234) - directionally consistent with
`Motivation.md`'s premise (more review, smaller adverse jump), and,
hand-checked against the underlying 15 rows before reporting it
(`results/analysis/08-21-review-intensity-joined.csv`), **not an
artifact of one or two extreme repos**: 6 of 8 low-review repos sit at
level_change_coef ≥0.15 and 5 of 7 high-review repos sit at ≤0.13, a
broad separation, not two outliers driving a median split.

**Still reported as a lead, not a finding, for reasons specific to this
n=15 sample, not just the usual multiple-comparisons caveat**: 1
significant result out of 24 correlation tests + 6 split tests (30
total, unadjusted) is close to chance-rate on its own; several covered
repos' `mean_comments` rests on as few as 2 matched agent PRs
(`567-labs/instructor`, `AgentOps-AI/agentops`, `browser-use/browser-use`
- see the coverage table), meaning the review-intensity measure itself
is a noisy per-repo estimate for a third of the covered sample, before
any question of whether it predicts the outcome.

### Caveats

- **19% coverage is the headline caveat, not a footnote** - this tests
  whether the relationship holds among the 15 repos happening to have
  both Track B PR-comment data and 100-repo-scale structural data, not
  among the 79 that clear RQ1's own regression gate. No claim here
  should be read as describing "the corpus" the way RQ1's own tables can.
- Review intensity here is comment *count* only (`ProjectStatus.md`
  item 3's own long-standing caveat: diff size and deeper review-round
  detail were never captured for any repo, pilot or scaled) - a coarser
  proxy for "review scrutiny" than round-trip count or reviewer
  diversity would be.
- The PR-sample file is a calendar-window *sample*, not a census, of
  each repo's PRs near its intervention date - `mean_comments`/`n_agent_prs_matched`
  describe the sampled agent PRs that happened to fall in-window and
  get matched, not necessarily every agent PR the repo ever merged.
- Same N=15/45-rows-not-independent-observations caveat as every other
  small-n test in this project's heterogeneity-explainer work - the
  pooled row exists for exactly this reason, and finds nothing
  (ρ ≤0.18 in magnitude on every pooled cell).

Outputs: `results/analysis/08-21-review-intensity-coverage.csv` (79-row
coverage table), `08-21-review-intensity-joined.csv` (45-row joined
outcome/review table), `08-21-review-intensity-correlations.csv`,
`08-21-review-intensity-median-split.csv`.

## What this changes about the project's running "no consistent direction" story

1. **The pre-slope/slope-change relationship's mechanical-coupling
   explanation is now demonstrated with a real null distribution, not
   asserted from one placebo point** - and it holds up better than the
   single-point check alone could show: the pooled test (the number
   that matters most, given the non-independence caveat every RQ in this
   project carries) lands the real intervention date at the 57th
   percentile of 300 split-balance-matched arbitrary cuts. This is a
   genuine strengthening of `HeterogeneityExplainers.md`'s conclusion,
   not just a repeat of it.
2. **One narrower exception** (`design_smell_density_per_kloc`
   specifically, p=0.02, one of 4 tests) is real but points the opposite
   direction from "agents suppress trend-reversal beyond chance" - it
   says the real cut is *less* self-correcting than an arbitrary
   same-shaped cut, for that one metric. Worth a dedicated follow-up
   (why would design-smell density specifically behave this way at real
   agent-adoption timing?), not treated as resolved by this pass.
3. **Review intensity - the most direct test yet of `Motivation.md`'s
   founding premise for the agentic era - finds one plausible-shaped,
   hand-checked, but statistically thin lead** (more human review around
   agent PRs, smaller adverse smell-density jump at intervention) on 15
   of 79 repos. This is real signal worth returning to once PR-sampling
   coverage catches up to the 100-repo structural corpus, not a
   confirmed answer to "does review intensity matter" at the scale this
   project's other RQ1 tables already operate at.
