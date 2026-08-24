# RQ-H1/RQ-H3 — explaining the direction-split, not re-measuring it (2026-08-19)

> **Status: first pass, real 100-repo data, both analyses complete and
> code-reviewed by hand (including a placebo check on the headline
> mechanism below).** Not a pre-registered confirmatory test — see each
> section's own caveats. Branch: `analysis/heterogeneity-explainers`.
> Rendered alongside the existing structural-health dashboard (new §8,
> everything else unchanged):
> https://claude.ai/code/artifact/7ae0a6d0-bbea-4fe8-a4f8-2d5f9b61c560

## Why this doc exists

Every RQ this project has run so far (RQ1's segmented regression, RQ2's
composition shift, the entity-churn analysis) reaches the same shape of
answer: real, non-random, statistically significant change shows up
almost everywhere, but it doesn't point the same direction across repos
- "no consistent cross-repo direction," most recently confirmed at
15-repo then 100-repo scale (`Results.md`'s 2026-08-13 entry, and the
`08-19-segmented-regression-full-237.csv` run behind this doc). That
heterogeneity has never itself been the *object* of a test - every RQ so
far asks "does X change," not "what explains which way it changes." This
doc is two second-stage analyses that treat the heterogeneity as the
outcome:

- **RQ-H1** (`src/analysis/heterogeneity_explainers.py`): do repo-level
  covariates (agent-PR dosage, agent diversity, language, stars) or a
  repo's own pre-intervention trajectory predict the direction/magnitude
  of its post-intervention change?
- **RQ-H3** (`src/analysis/smell_subtype_consistency.py`): is smell
  *type* (God Class, Data Class, Feature Envy, Brain Method - Lanza &
  Marinescu's four Detection Strategies this project's in-house detector
  implements) a more consistent grouping variable for direction than
  *repo* is - i.e. is the "agents fix locally, not architecturally"
  hypothesis (`Motivation.md`, `Results.md`'s RQ2) visible at finer
  resolution than the 2-bucket design-vs-implementation split RQ2 already
  tested?

## Data

Both scripts are **pinned to explicit, named files**, not `fc.latest_*()`
globs, on purpose: the 100-repo corpus-scaling run finished and landed
mid-session while this was being built, and "latest" would have made
these scripts a moving target against a background job. Re-point the
three path constants at the top of each script deliberately if the corpus
grows further - not automatically.

| File | Role |
|---|---|
| `results/analysis/08-19-inhouse-metrics-pooled.csv` | OO metrics, 96 repos, 7,453 `ok` rows |
| `results/analysis/08-19-inhouse-smells-pooled.csv` | Smell counts (4 Lanza & Marinescu subtypes), 94 repos, 7,431 `ok` rows |
| `results/analysis/08-19-segmented-regression-full-237.csv` | RQ1's own fitted coefficients, 79 repos x 3 primary metrics, `min_pre=min_post=5` gate |
| `results/repos/08-17-repo-summary-235.csv` | Repo-level covariates: language, stars, `agent_pr_count`, `distinct_agents`, `agent_breakdown` |

Join key is `repo_id`, not `full_name`, kept deliberately even though this
particular 79-repo cut happens to join cleanly on `full_name` alone (0
missing, checked directly) - a smaller, earlier cut of this analysis
found a real full_name mismatch (`marin-community/levanter` in the
in-house pool vs. `stanford-crfm/levanter` in the repo-summary registry,
same GitHub repo renamed/transferred, same numeric `repo_id` 496005961),
and that repo simply isn't among the 79 clearing the regression gate at
100-repo scale - the hazard didn't go away, it just isn't triggered by
this cut.

## RQ-H1 — does anything explain the direction split?

### Headline: dosage doesn't, language barely does, and the strongest-looking explainer turned out to be a placebo-confirmed artifact

**Agent-PR dosage (`agent_pr_count`, `distinct_agents`) has no
detectable relationship with which way a repo's smell density or
complexity trend moves.** Every correlation against `slope_change_coef`
is non-significant (p > 0.4, most p > 0.6) across all three primary
metrics, both with and without the degenerate CC-p90 rows (see below),
and the two-predictor OLS fit (`slope_change ~ slope_pre + log1p(agent_pr_count)`)
finds `agent_pr_count`'s coefficient indistinguishable from zero
everywhere (p = 0.45-0.98). This is a real update, not just a bigger
version of the same null: an earlier 15-repo cut of this same analysis
found a *significant* dosage correlation on CC p90 specifically (ρ=-0.65
to -0.77, p<0.01) that looked like a real finding at the time - it
evaporated entirely once the corpus grew to 79 regression-eligible repos
(ρ=0.06, p=0.65). Treat that as the headline lesson about small-N
exploratory correlations in this project generally, not just about this
one variable: RQ5 (`Results.md`) already flagged dosage as "inconclusive
at N=4, kept as a covariate for when there's enough repos to regress
properly" - there's now enough repos, and the answer is a real null, not
an unresolved question.

**Language (Python vs. C#) shows exactly one significant split, and it's
modest.** Of six (metric x outcome) Mann-Whitney tests, only
`cyclomatic_complexity_p90`'s `slope_change_coef` differs significantly
by language (p=0.020 all-rows / p=0.036 with degenerate rows excluded,
Cliff's δ ≈ -0.32 - "small-to-medium" by Romano et al.'s convention):
Python repos' CC-p90 trend improves (more negative slope-change) more
than C# repos' does, post-intervention. Neither design-smell density nor
implementation-smell density shows a significant language split on
either coefficient (all p > 0.19). This is the first time this question
has had real power to test at all - the original pilot had exactly one
C# repo (Dock), making RQ4 "barely a test" per `Results.md`'s own words;
here it's 51 Python vs. 28 C# repos. One significant result out of six
tests, unadjusted for multiple comparisons, is a real signal worth
flagging as a lead, not a settled cross-language finding.

**A weak, unreplicated lead**: `design_smell_density_per_kloc`'s
`level_change_coef` (the jump right at the intervention, not the slope
after it) correlates weakly with `agent_pr_count` (ρ≈0.23-0.24,
p≈0.037-0.043, both with and without degenerate rows) - repos with more
agent PRs show a slightly larger design-smell jump right at the
intervention. Single test, p just under .05, not corrected for the ~16
correlations run in this pass - flagged as worth a second look with an
independent replication sample, not reported as a finding.

### The headline near-miss: pre-intervention slope predicts post-intervention slope-change almost perfectly - and a placebo check shows this is mostly not about agents at all

The strongest relationship in the whole analysis, by far, is between a
repo's pre-intervention slope (`slope_pre_coef`, RQ1's own fitted
pre-trend) and its slope-*change* after the intervention
(`slope_change_coef`): pooled ρ = -0.70 (p = 7×10⁻³⁶), and a two-predictor
OLS explains **r² = 0.91** of `slope_change_coef`'s variance for design
smells (r² = 0.72 for implementation smells, 0.34-0.34 for CC p90) using
`slope_pre_coef` alone as the dominant term. Read naively, this looks
like the paper's best finding: repos on a steep pre-existing trajectory
get pulled back toward flat after agents arrive, and vice versa - a
clean "agents dampen extremes" story.

**It doesn't survive a placebo check, and this project's own culture
(hand-validate before trusting a clean-looking number - see e.g.
`Results.md`'s LCOM-rescaling and `MaxNestingLevel` catches) says a
number this strong needs one before it goes in a headline.** The check:
refit the *identical* segmented-regression model, unchanged, against a
fake "intervention date" for every repo - its own median Track-A1
snapshot date, i.e. splitting each repo's real series exactly in half,
with zero connection to any real agent-PR event - and see if the same
`slope_pre` vs. `slope_change` correlation appears anyway.

| Metric | Real ρ (real intervention date) | Placebo ρ (fake, per-repo-median date) |
|---|---|---|
| `cyclomatic_complexity_p90` | -0.70 (p=6×10⁻¹³, n=79) | -0.69 (p=4×10⁻¹⁴, n=92) |
| `design_smell_density_per_kloc` | -0.60 (p=4×10⁻⁹, n=79) | **-0.90** (p=1×10⁻³³, n=91) |
| `implementation_smell_density_per_kloc` | -0.71 (p=2×10⁻¹³, n=79) | **-0.83** (p=3×10⁻²⁴, n=91) |

The placebo correlation is **at least as strong as the real one on every
metric, and stronger on two of three.** This is decisive, not
ambiguous: an arbitrary, meaningless split point in a repo's own history
produces the same "steep pre-trend predicts a compensating post-trend"
pattern that the real intervention date produces. The most likely
explanation is that this is substantially a property of fitting two
time-slope coefficients to the same finite, noisy series (real
regression-to-the-mean in a repo's own trend noise, compounded by
`t_abs` and `t_rel*post` sharing variance by construction - see the
script's own module docstring) rather than evidence that agents
specifically reverse whatever trend a repo was already on. **This doesn't
mean nothing about the real intervention date matters** - the real
correlation is not zero, and CC p90's real and placebo numbers are close
enough that a residual real effect on top of the mechanical one can't be
ruled out from this check alone - but it means the r²=0.91 headline
number above cannot be read as "91% of the direction-split is explained
by agents correcting pre-existing trends." Most of it would show up with
no agents involved at all.

**Practical implication for future RQ1-style work in this project**:
any segmented-regression analysis that reports a pre-slope vs.
slope-change relationship should run this same placebo check before
trusting the magnitude - it's cheap (reuses `segmented_regression.fit_one`/
`run` unchanged) and this session found a real, large, previously-unflagged
gap between what the naive number claims and what a null process alone
produces.

### The zero-variance CC-p90 data-quality artifact, found and controlled for

22 of the 79 CC-p90 regression rows have `level_change_se` ≈ 1e-15 -
indistinguishable from float noise, meaning that repo's `cyclomatic_complexity_p90`
series is a flat constant across its whole Track-A1 window (the same "no
signal available, not no effect" situation already documented for
airbyte's DPy-based CC p90 in the pilot - `Results.md`). Every table in
this analysis is run twice, with and without these rows
(`is_degenerate` column, `results/analysis/08-19-heterogeneity-*-all-rows.csv`
vs. `-excl-degenerate.csv`) - the language-split CC-p90 finding above
survives the exclusion (p moves from 0.020 to 0.036, still significant),
and the dosage null and the placebo-check magnitudes are essentially
unchanged either way, so this artifact doesn't appear to be driving any
of the findings reported above - but it's worth knowing about before
citing any *other* cell in the correlation tables that isn't explicitly
checked here.

### Caveats

- **N=79 repos, repeated across 3 metrics (n=237), not 237 independent
  observations** - every test above is also run per-metric (n≈63-79)
  for exactly this reason. No p-value in this section should be read as
  surviving a formal multiple-comparison correction (~16 correlations +
  6 language tests + 3 multivariate fits ran in this one pass).
- **Regression to the mean is confirmed as a real, large contributor to
  the pre-slope/slope-change relationship** (see placebo check above) -
  the reverse is not true for the dosage/language results, which have no
  equivalent mechanical-coupling concern (agent-PR count and language
  aren't derived from the same OLS fit as the outcome).
- No matched non-adopting comparison arm yet (unchanged open item from
  `Longitudinal.md`/`ProjectStatus.md`) - everything here is still
  describing *which* ITS repos move which way, not ruling out that some
  of the movement is unrelated to agents at all.

Outputs: `results/analysis/08-19-heterogeneity-joined-237.csv` (the
merged repo x metric x covariate table), `-correlations-{all-rows,excl-degenerate}.csv`,
`-language-split-{all-rows,excl-degenerate}.csv`,
`-multivariate-{all-rows,excl-degenerate}.csv`,
`-placebo-slope-reversion.csv`.

## RQ-H3 — is smell type a more consistent grouping variable than repo?

### Method

`Results.md`'s RQ2 tested composition shift at the coarsest possible
resolution (design smells' share of all smells vs. implementation
smells', 2 buckets). The in-house smell detector already reports which
*specific* Lanza & Marinescu strategy fired per snapshot - God Class and
Data Class (both currently pooled into "design"), Feature Envy and Brain
Method (both pooled into "implementation") - as separate counts
(`n_god_class`, `n_data_class`, `n_feature_envy`, `n_brain_method`,
confirmed to sum exactly to the existing `design_smell_count`/
`implementation_smell_count` columns on every one of the 7,431 pooled
rows before building on it). Each subtype gets its own per-KLOC density
and its own segmented-regression fit per repo, via the *same*
`segmented_regression.fit_one`/`run` code RQ1 uses, unchanged - 80 repos
x 4 subtypes = 320 fitted rows, `min_pre=min_post=5` gate.

The test: among (repo, subtype) fits with a *significant* (p<.05)
slope-change, what fraction of all pairs agree in sign - grouped **by
subtype, pooled across repos** vs. grouped **by repo, pooled across its
own subtypes**? If smell type explains the direction split better than
repo identity does, the by-subtype agreement rate should be
meaningfully higher than the by-repo rate. Run twice: once at this new
4-subtype resolution, once as a baseline replication of RQ2's original
2-bucket (design/implementation) split, using the already-existing
`08-19-segmented-regression-full-237.csv` fit rather than refitting, so
the finer-grained result is read against the resolution the project
already had, not in isolation.

### Result: no - if anything, repo edges out subtype, and going finer resolution *reduces* apparent repo-coherence rather than revealing type-coherence

| Resolution | Significant (p<.05) fits | By-**type** pairwise sign agreement | By-**repo** pairwise sign agreement |
|---|---|---|---|
| 2-bucket (design vs. implementation) | 60 / 158 | 55.4% (2 groups) | **76.2%** (21 repos with ≥2 sig. subtypes) |
| 4-subtype (god class / data class / feature envy / brain method) | 98 / 320 | 56.8% (4 groups) | 61.0% (28 repos with ≥2 sig. subtypes) |

The sharp version of the "agents fix locally, not architecturally"
hypothesis - that smell *type* is the variable that actually organizes
the direction split, with repo identity mostly noise - **is not
supported.** At 4-subtype resolution, by-type and by-repo agreement are
nearly identical (56.8% vs. 61.0%), both only modestly above the 50%
a coin flip would give with two random signs. Neither grouping variable
explains most of the heterogeneity at this resolution.

**The 2-bucket baseline's 76.2% by-repo figure is a real number, but
reading it as "smell type is a weaker explainer than repo" is misleading
without the resolution context**: at 2 buckets, a repo can have at most
1 pairwise comparison (2 significant metrics = C(2,2)=1 pair), so most of
that 76.2% is built from single-pair, all-or-nothing comparisons (either
the repo's 2 buckets agree, contributing 100%, or they don't, contributing
0%) rather than an average over several independent pairs per repo - a
noisier, less reliable statistic than it looks. Going to 4 subtypes gives
repos with multiple significant subtypes up to 6 pairs to average over
(`crewAIInc/crewAI-tools`: 4 significant subtypes, 6 pairs), and the
by-repo agreement rate drops from 76.2% to 61.0% once that happens - not
because repos got less coherent, but because the coarser 2-bucket number
was inflated by measuring mostly single-pair "agreements." **The honest
reading: once there's enough resolution to measure it reliably, neither
repo nor smell type organizes the direction split much better than the
other, and neither organizes it strongly** - a different, more nuanced
conclusion than either "type explains it" (the hypothesis this analysis
set out to test) or "repo explains it" (the implicit baseline every
other RQ in this project has been structured around).

**98 of 320 fits (30.6%) are significant at p<.05, unadjusted** - far
above the ~5% a global null would produce, so there is real, substantial
signal in this data; it's just not well-organized by either the smell-type
axis or the repo axis at the granularity tested here. What *does* organize
it (agent identity mix, review intensity, something else) is an open
question this analysis doesn't answer, not a "no effect" result.

### Caveats

- Same unadjusted-multiple-comparisons caveat as RQ1 above, more acute
  here: up to 320 tests in the 4-subtype fit, not 45 or 237.
- `god_class_density_per_kloc`/`data_class_density_per_kloc`/etc. inherit
  `py_smells.py`/`SmellDetector.cs`'s own validation status - a narrower,
  differently-sourced smell definition (Lanza & Marinescu Detection
  Strategies) than DPy/Designite's closed catalogs, same caveat
  `figures_common.py`'s own docstring already states for every use of
  this smell data in this project.
- 2 rows (both `crewAIInc/crewAI-tools`' earliest snapshot, a genuine
  2-file/0-LOC state, not a bug) have `total_loc == 0`; density is `NaN`
  there rather than a division error, and those rows drop out via the
  regression's own `dropna()` the same way any other missing metric value
  would.

Outputs: `results/analysis/08-19-smell-subtype-regression-320.csv` (+`-skipped.csv`),
`08-19-smell-subtype-consistency-summary.csv`.

## What this changes about how to read the project's "no consistent direction" headline

Neither analysis found a clean explainer. That's a real result, not a
failure to find one, and it sharpens (rather than resolves) the
project's central open question:

1. **It is very unlikely to be about dosage** - not "not yet enough
   data to tell" (RQ5's original framing), but a real null at n=79.
2. **It is very unlikely to be well-organized by smell type** at the
   resolution tested, contrary to the "agents fix locally, not
   architecturally" hypothesis's sharpest reading.
3. **The one candidate that does show a small, real split is language**
   (CC p90 only, Cliff's δ≈-0.32) - worth a closer, dedicated look
   rather than the exploratory pass given here.
4. **A methodology lesson with a shelf life beyond this specific
   question**: any future explainer analysis in this project that
   reports a relationship involving a segmented-regression coefficient
   should placebo-check it the way RQ-H1 did here before treating the
   magnitude as substantive - the mechanical-coupling risk is real and,
   at least once, large enough to account for almost the entire
   apparent effect.
