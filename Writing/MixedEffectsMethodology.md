# Mixed-effects/hierarchical-model companion layer (2026-08-24)

> **Status: additive layer, complete for this pass.** Every script,
> CSV, and doc section this covers stays exactly as it was; everything
> below is new files reading existing pinned data, with new appended
> doc sections (this doc plus one new section each in `Results.md`,
> `HeterogeneityExplainersPart2.md`, `AgentCodeSurvival.md`). Branch:
> `analysis/agent-code-survival-full-corpus`.

## Why this doc exists

Across this project, every "does this hold across the corpus" statistic
has been built one of two ways:

1. **Fully independent per-repo fits** — `segmented_regression.py`'s
   core interrupted-time-series regression fits 79 repos × 3 metrics
   completely separately (237 rows, zero cross-repo pooling). The
   project's headline "no consistent cross-repo direction" claim was
   then read off that table by hand: counting how many of the 237 rows
   have p<.05 in the positive vs. negative direction and writing "close
   to evenly split" as prose in `Results.md` — no `src/` script runs
   this count, and no formal test (e.g. a binomial test against a 50/50
   null) sits behind the word "consistent."
2. **Naive full pooling downstream** — `heterogeneity_explainers.py`,
   `placebo_permutation_test.py`, `review_intensity_explainer.py`, and
   `agent_code_survival_full_corpus.py` each take per-repo fitted
   coefficients (or, for agent-code-survival, per-entity rows) and run
   ONE combined correlation/regression/test across all of them —
   explicitly labeled `"pooled (non-independent, see caveat)"` in the
   code itself. A repo contributing 3 rows (one per metric) gets
   treated as 3 independent observations, which it isn't.

Neither is a real hierarchical model. A mixed-effects model does
**partial pooling**: a repo random effect lets repos borrow statistical
strength from each other while still respecting that rows from the same
repo are correlated — the middle ground between "237 isolated fits" (no
pooling) and "act like every row is independent" (complete pooling).

## What partial pooling means, concretely — RQ1 as the running example

`segmented_regression.py` fits, per repo, per metric:

```
metric ~ intercept + slope_pre·t_abs + level_change·post + slope_change·(t_rel·post)
```

completely separately for each of 79 repos. A repo with only 5 pre/5
post data points gets exactly as much say in its own `level_change`/
`slope_change` estimate as a repo with 60 points — and that noisy
small-n estimate is never informed by what the other 78 repos' series
look like.

`segmented_regression_mixed_effects.py` fits the SAME formula as ONE
model across all repos' raw snapshot rows at once, with `full_name` as
a random effect on the intercept, `level_change`, and `slope_change`
terms. This produces two things the 237 independent fits cannot:

- A **population-average fixed effect** — "across the corpus, does
  structural health jump/change trend at intervention, on average" —
  with real between-repo clustering already accounted for in its
  standard error (unlike a naive pooled test on the 237 rows, which
  would understate the SE by treating 3 correlated rows-per-repo as 3
  independent draws).
- A **between-repo variance component** — how much repos actually vary
  around that average, separate from noise. A near-zero variance here
  is itself a real finding ("repos don't differ much once modeled
  properly"), not evidence the model failed.

A repo's own fitted `level_change` under this model gets pulled
("shrunk") toward the population average by an amount that depends on
how little data that repo has and how much repos vary overall — a
short, noisy series shrinks more than a long, stable one. This is
different from, and more principled than, either extreme.

## New dependency

`statsmodels` (0.14.6) was not installed in this environment before
this pass — confirmed directly (only numpy 2.5.1, scipy 1.18.0, pandas
3.0.3 were present). Added to `requirements.txt`, unpinned, matching
that file's existing style. Installed cleanly against this project's
unusually new stack (Python 3.14.5, pandas 3.0.3) — a native `cp314`
wheel exists, no compatibility issue found. Needed for:
- `statsmodels.regression.mixed_linear_model` (`MixedLM`, via
  `smf.mixedlm(...)`) — REML-fit linear mixed models, used for every
  continuous outcome below (RQ1's raw metrics, and the fitted-coefficient
  companions, whose outcome is itself a continuous regression
  coefficient).
- `statsmodels.genmod.bayes_mixed_glm` (`BinomialBayesMixedGLM`,
  `PoissonBayesMixedGLM`) — variational-Bayes GLMM fitting, a
  **different inferential framework** (approximate posterior mean/SD,
  not classical MLE/REML coefficient+CI), used only for
  `agent_code_survival_mixed_effects.py`'s binary/count outcomes, named
  as such throughout rather than presented as if it were the same kind
  of output as the MixedLM results.

## Cross-link table

| Original ("naive pooled" or "237 independent") | New companion script | New output CSVs | Appended doc section |
|---|---|---|---|
| `segmented_regression.py` (237 independent fits) | `segmented_regression_mixed_effects.py` | `*-segmented-regression-mixed-effects-{fixed,random-effects,convergence}.csv` | `Writing/Results.md`, "Mixed-effects companion to RQ1" |
| `heterogeneity_explainers.py` (`pairwise_correlations`, `multivariate_fits`, `placebo_slope_reversion_check`) | `heterogeneity_explainers_mixed_effects.py` | `*-heterogeneity-mixed-effects-{correlations,multivariate}-{all-rows,excl-degenerate}.csv`, `*-heterogeneity-mixed-effects-placebo.csv` | `writing/HeterogeneityExplainersPart2.md`, "Mixed-effects companions" |
| `review_intensity_explainer.py` (`review_intensity_correlations`) | `review_intensity_mixed_effects.py` | `*-review-intensity-mixed-effects.csv` | `writing/HeterogeneityExplainersPart2.md`, "Mixed-effects companions" |
| `agent_code_survival_full_corpus.py` (`frequency_test`, `survival_deletion_test`, `full_survival_test` + their repo-stratified permutation checks) | `agent_code_survival_mixed_effects.py` | `*-agent-survival-fc-mixed-effects.csv`, `*-agent-survival-fc-mixed-effects-group-diagnostics.csv` | `Writing/AgentCodeSurvival.md`, "GLMM companion" |

Not companioned this pass, stated as a deliberate scope boundary, not a
silent omission:
- `language_split_test()` / `median_split_test()` (heterogeneity,
  review-intensity) — two-group Mann-Whitney comparisons, no natural
  MixedLM/GLMM analogue.
- `placebo_permutation_test.py`'s own 300-draw × 2-null-strategy
  permutation engine — already a rigor upgrade on a different axis
  (empirical null, not a clustering fix); 600 MixedLM refits for a
  secondary check wasn't judged worth the cost this pass.
- `smell_subtype_consistency.py` — already runs a real per-repo-vs-
  per-subtype stratified comparison, not the naive-pooling pattern this
  layer targets.

## Verification recipe (applied to every model below before reporting a number)

1. **Random-effect variance** checked for near-zero (a valid finding:
   "no real cross-repo heterogeneity once modeled properly") vs.
   implausibly large relative to residual variance.
2. **Convergence diagnostics** captured into a dedicated column/file,
   not left to print-and-vanish. `MixedLM`'s own `result.converged` is
   trusted as the authority on whether the FINAL fit succeeded — NOT
   the mere presence of a "failed to converge"/"Hessian not positive
   definite" phrase in the warning stream, since statsmodels' `.fit()`
   retries internally with `lbfgs`/`cg` when its default optimizer's
   first attempt fails, and reports every abandoned attempt's warning
   even when a later retry succeeds. An earlier version of this layer's
   code conflated the two and mislabeled several cleanly-converged
   models as failures — caught and fixed before any number below was
   taken at face value, not after.
3. **"Boundary of the parameter space" warnings are not treated as
   failures.** They mean a variance component's estimate landed at (or
   near) zero — expected and common with a modest group count and weak
   real between-repo variance on that particular random effect, not a
   fit problem. Nearly every model in this layer hits this on at least
   one term; reported as `at_variance_boundary`, separate from
   `converged`.
4. **Optimizer stability spot-check**: RQ1's models refit with `lbfgs`
   vs. the default optimizer — fixed effects agreed within ~0.5% on the
   spot-checked metric (cyclomatic_complexity_p90: `post_num` 0.2327 vs.
   0.2346, `t_rel_post` -0.0157 vs. -0.0164).
5. **Degenerate CC-p90 repos** (16/79, `level_change_se` ~1e-15 — the
   same zero-variance-series artifact `heterogeneity_explainers.py`
   already flags) run with and without, per that module's existing
   convention, not a new one.
6. **Small-group GLMM inputs tabulated and flagged**: 11/32 repos in
   the `full_survival` candidate set contribute <5 rows to at least one
   cohort (`*-agent-survival-fc-mixed-effects-group-diagnostics.csv`) —
   named, not silently absorbed into the pooled number.

## Real deviations from the plan, found only by building this

- **RQ1's 3-random-effect model (intercept + level_change + slope_change)
  converges fine on all 3 metrics once the convergence-classification
  bug in item 2 above was fixed** — the plan anticipated needing a
  2-random-effect fallback "empirically," and the fallback machinery is
  built and works, but in practice every metric's 3-RE model landed on
  `converged=True` (with an expected boundary warning on at least one
  variance term) once `result.converged` was trusted correctly instead
  of any warning text.
- **`statsmodels.genmod.bayes_mixed_glm` has no offset mechanism at
  all** (confirmed via `inspect.signature` on both `from_formula` and
  `__init__`) — not anticipated in planning, which assumed a
  `offset(log(age_days+1))` term would work the way it does in R's
  `mgcv`/`lme4`. `log(age_days+1)` is included in
  `agent_code_survival_mixed_effects.py`'s Poisson model as an ordinary,
  freely-estimated covariate instead of a fixed-coefficient offset — a
  real approximation to exposure-adjustment, not the statistically
  correct offset model originally planned, and reported as such rather
  than silently substituted.
- **The `touches_after_birth` GLMM does not reliably converge**, tried
  with and without feature scaling (`scale_fe=True/False`) — the fit
  either collapses toward a degenerate near-zero-variance posterior or
  diverges to numerical overflow depending on the run, with the severe
  overdispersion already flagged (variance/mean ≈ 6, no
  negative-binomial option available in this statsmodels module) the
  most likely cause. **No reliable effect estimate is reported for this
  outcome** — see `Writing/AgentCodeSurvival.md`'s GLMM section for the
  full account; this is a genuine tool/data-fit limitation, not
  something further code changes were able to resolve this pass.
- **The `ended` GLMM's fixed-effect point estimate is stable across
  repeated runs (-0.098, SD 0.125, every time checked) but its
  `optim_retvals['success']` flag is not** (True on some runs, False on
  others, no code change between runs) — reported with this caveat
  rather than picking whichever run looked cleanest.
