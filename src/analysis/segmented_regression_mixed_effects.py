"""
Hierarchical/mixed-effects companion to segmented_regression.py's core RQ1
regression - additive, not a replacement. `segmented_regression.py` fits
79 repos x 3 metrics completely independently (237 rows, zero cross-repo
pooling); the project's headline "no consistent cross-repo direction"
claim is then read off that table by hand-counting how many rows have
p<.05 in each direction (Writing/Results.md), not by any versioned
statistical test. Neither "237 independent fits" nor a naive pooled test
(the pattern every downstream script in this project already flags as
"pooled (non-independent, see caveat)") is a real hierarchical model.

This script fits ONE linear mixed model per primary metric, across ALL
eligible repos' raw snapshot rows at once, with `full_name` as a random
effect - partial pooling: a repo's fitted level_change/slope_change gets
pulled toward the population-average value by an amount that depends on
how much data that repo has and how much repos vary overall, rather than
being estimated in total isolation (the 237-row table) or averaged as if
every row were an independent draw (the naive-pooled pattern elsewhere).

Reuses segmented_regression.build_full_corpus_dataset() directly (import,
not reimplementation) - the exact same merged raw-snapshot data the
237-row CSV was itself fit from. Eligibility (min_pre/min_post >= 5) is
taken directly from which (full_name, metric) pairs already appear in the
pinned 08-19-segmented-regression-full-237.csv, not recomputed - the
mixed model covers exactly the same 237 (repo, metric) cells, on their
raw rows instead of their already-fitted summaries.

Output is entirely new files under a new naming convention
(*-mixed-effects-*.csv) - nothing existing is read for writing, nothing
existing is modified.
"""

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from statsmodels.tools.sm_exceptions import ConvergenceWarning

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
import segmented_regression as sr  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
REGRESSION_FULL_PATH = fc.ANALYSIS_DIR / "08-19-segmented-regression-full-237.csv"
DEGENERATE_SE_FLOOR = 1e-8  # same floor heterogeneity_explainers.py uses on level_change_se


def eligible_cells():
    """(full_name, metric) pairs already in the pinned 237-row output -
    the mixed model covers exactly this set, not a freshly recomputed
    min_pre/min_post filter, so the two are guaranteed comparable."""
    reg = pd.read_csv(REGRESSION_FULL_PATH)
    reg["is_degenerate"] = reg["level_change_se"].abs() < DEGENERATE_SE_FLOOR
    return reg[["full_name", "metric", "is_degenerate"]]


def build_model_frame(raw, metric, full_names):
    """One metric's raw snapshot rows, restricted to the eligible
    full_names, with the exact design columns fit_one() uses (t_abs, post,
    t_rel_post) precomputed as plain columns - MixedLM needs a flat frame,
    not fit_one()'s per-repo closed-form loop."""
    d = raw[(raw["track"] == "A1") & raw["full_name"].isin(full_names)].copy()
    d = d.dropna(subset=[metric, "months_since_intervention", "post"])
    d = d.sort_values(["full_name", "target_date"])
    days_since_start = d.groupby("full_name")["target_date"].transform(lambda s: (s - s.iloc[0]).dt.total_seconds())
    d["t_abs"] = days_since_start / 86400 / 30.436875
    d["post_num"] = d["post"].astype(float)
    d["t_rel_post"] = d["months_since_intervention"].astype(float) * d["post_num"]
    d = d.rename(columns={metric: "y"})
    return d[["full_name", "y", "t_abs", "post_num", "t_rel_post"]].reset_index(drop=True)


# Phrases that mean the optimizer genuinely failed (wrong optimum, didn't
# finish, curvature unusable) - as opposed to "The MLE may be on the
# boundary of the parameter space" alone, which just means a variance
# component's estimate landed at (or near) zero. A boundary result is
# expected and common with a modest group count and weak/no real
# between-repo variance on that particular random effect - not a fit
# failure, and treating it as one would misreport nearly every model in
# this file as "didn't converge" when the fixed-effect estimates are
# actually fine (confirmed directly: statsmodels' own `result.converged`
# is True on every boundary-only case checked by hand before writing this
# classification, and a same-parameter lbfgs refit reproduces the fixed
# effects closely - see the plan's optimizer-stability spot check).
#
# `result.converged` is trusted as the sole authority on whether the
# FINAL reported fit succeeded - NOT the presence of a "failed to
# converge"/"Hessian not positive definite" phrase in the warning stream.
# Confirmed by hand this matters, not a theoretical distinction:
# statsmodels' .fit() retries internally with lbfgs/cg when its default
# optimizer's first attempt fails, and reports every abandoned attempt's
# warning even when a later retry succeeds - so a message containing a
# hard-failure phrase can appear on a run whose final `result.converged`
# is True. Treating any such phrase as disqualifying (an earlier version
# of this function did) mislabeled cases where the model actually landed
# fine after an internal retry. `had_hard_failure_warning` is still
# recorded, but as an informational flag alongside `converged`, not a
# gate that overrides it.
_HARD_FAILURE_MARKERS = (
    "failed to converge", "gradient optimization failed",
    "not positive definite", "optimization failed,",
)


def _classify(result, warning_msgs):
    had_hard_failure_warning = any(
        marker in msg.lower() for msg in warning_msgs for marker in _HARD_FAILURE_MARKERS
    )
    at_boundary = any("boundary of the parameter space" in msg.lower() for msg in warning_msgs)
    converged = bool(result.converged)
    return converged, at_boundary, had_hard_failure_warning


def fit_metric(d, metric_label):
    """Fits the 3-random-effect model first (intercept + post +
    t_rel_post); falls back to a 2-random-effect model (intercept +
    t_rel_post only - the model's actual headline quantity, slope_change)
    only when `result.converged` is genuinely False - not merely on a
    hard-failure-sounding warning appearing somewhere in the stream (see
    _classify's docstring note: statsmodels' own internal retries can
    leave an abandoned attempt's failure warning behind even when the
    final result converged cleanly). A boundary-only warning on the 3-RE
    model is likewise not a reason to fall back - it's kept, since it's
    the richer, requested random-effects structure and the boundary
    result is itself informative (that particular variance component is
    near zero), tried standardizing t_abs/t_rel_post to rule out a scale
    artifact before accepting a genuine non-convergence (see the
    surrounding follow-up doc for that check). Whichever structure is
    actually used, and why, is recorded, not silently assumed."""
    warning_msgs = []
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model = smf.mixedlm("y ~ t_abs + post_num + t_rel_post", d,
                             groups=d["full_name"], re_formula="~ post_num + t_rel_post")
        result = model.fit(reml=True)
        warning_msgs.extend(str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning))
    re_structure = "intercept + post + t_rel_post"
    converged, at_boundary, had_hard_failure_warning = _classify(result, warning_msgs)
    if had_hard_failure_warning:
        warning_msgs.append(f"note: a hard-failure-sounding warning appeared but "
                             f"result.converged={result.converged} (see internal-retry note in _classify)")

    if not converged:
        warning_msgs.append("[fallback triggered] 3-RE model: result.converged=False")
        with warnings.catch_warnings(record=True) as caught2:
            warnings.simplefilter("always", ConvergenceWarning)
            model2 = smf.mixedlm("y ~ t_abs + post_num + t_rel_post", d,
                                  groups=d["full_name"], re_formula="~ t_rel_post")
            result2 = model2.fit(reml=True)
            fallback_warnings = [str(w.message) for w in caught2 if issubclass(w.category, ConvergenceWarning)]
        converged2, at_boundary2, hard_failure2 = _classify(result2, fallback_warnings)
        if converged2:
            result, re_structure, converged, at_boundary = result2, "intercept + t_rel_post", True, at_boundary2
            warning_msgs.append(f"fallback (2-RE) converged (at_boundary={at_boundary2})")
        else:
            warning_msgs.append(f"fallback (2-RE) ALSO did not converge (result.converged=False) - "
                                 f"keeping fallback result anyway, flagged not converged, a genuine "
                                 f"unresolved non-convergence for this metric/scope, not a display bug")
            result, re_structure, converged, at_boundary = result2, "intercept + t_rel_post", False, at_boundary2

    return result, re_structure, converged, at_boundary, warning_msgs


def summarize_fixed(result, metric, drop_degenerate, re_structure, converged, at_boundary, n_repos, n_obs):
    names = ["Intercept", "t_abs", "post_num", "t_rel_post"]
    row = {
        "metric": metric, "drop_degenerate": drop_degenerate,
        "re_structure": re_structure, "converged": converged, "at_variance_boundary": at_boundary,
        "n_repos": n_repos, "n_obs": n_obs,
        # aic/bic are NaN by statsmodels' own design under REML (fit(reml=True)
        # below) - REML's likelihood integrates out the fixed effects, so it
        # isn't directly comparable across models the way ML likelihood is;
        # statsmodels returns nan rather than a misleading number. REML is
        # used here anyway (not ML) because it gives less-biased variance-
        # component estimates at this group count (~79) - the standard
        # trade-off, not an oversight. log_likelihood (llf) is still real.
        "aic": result.aic, "bic": result.bic, "log_likelihood": result.llf,
        "scale": result.scale,
    }
    for name in names:
        row[f"{name}_coef"] = result.fe_params.get(name, np.nan)
        row[f"{name}_se"] = result.bse_fe.get(name, np.nan)
        row[f"{name}_p"] = result.pvalues.get(name, np.nan)
    cov_re = result.cov_re
    for i, ni in enumerate(cov_re.index):
        for j, nj in enumerate(cov_re.columns):
            if j < i:
                continue
            label = f"re_var_{ni}" if ni == nj else f"re_cov_{ni}_{nj}"
            row[label] = cov_re.iloc[i, j]
    return row


def summarize_random_effects(result, metric, drop_degenerate):
    rows = []
    for full_name, re in result.random_effects.items():
        row = {"full_name": full_name, "metric": metric, "drop_degenerate": drop_degenerate}
        for name, val in re.items():
            row[f"re_{name}"] = val
        rows.append(row)
    return rows


def run():
    raw = sr.build_full_corpus_dataset()
    cells = eligible_cells()

    fixed_rows, re_rows, conv_rows = [], [], []
    for drop_degenerate in (False, True):
        for metric in sr.PRIMARY_METRICS:
            cell = cells[cells["metric"] == metric]
            if drop_degenerate:
                cell = cell[~cell["is_degenerate"]]
            full_names = cell["full_name"].unique()
            d = build_model_frame(raw, metric, full_names)
            n_repos, n_obs = d["full_name"].nunique(), len(d)

            result, re_structure, converged, at_boundary, warning_msgs = fit_metric(d, metric)
            tag = "excl-degenerate" if drop_degenerate else "all-rows"
            print(f"{metric} ({tag}): n_repos={n_repos}, n_obs={n_obs}, "
                  f"re_structure=[{re_structure}], converged={converged}, at_boundary={at_boundary}")

            fixed_rows.append(summarize_fixed(result, metric, drop_degenerate, re_structure,
                                               converged, at_boundary, n_repos, n_obs))
            re_rows.extend(summarize_random_effects(result, metric, drop_degenerate))
            conv_rows.append({
                "metric": metric, "drop_degenerate": drop_degenerate,
                "re_structure": re_structure, "converged": converged, "at_variance_boundary": at_boundary,
                "warnings": " | ".join(warning_msgs) if warning_msgs else "",
                "cov_re_condition_number": np.linalg.cond(result.cov_re.to_numpy()),
            })

    fixed = pd.DataFrame(fixed_rows)
    random_effects = pd.DataFrame(re_rows)
    convergence = pd.DataFrame(conv_rows)

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    fixed_path = OUT_DIR / f"{prefix}-segmented-regression-mixed-effects-fixed.csv"
    re_path = OUT_DIR / f"{prefix}-segmented-regression-mixed-effects-random-effects.csv"
    conv_path = OUT_DIR / f"{prefix}-segmented-regression-mixed-effects-convergence.csv"
    fixed.to_csv(fixed_path, index=False)
    random_effects.to_csv(re_path, index=False)
    convergence.to_csv(conv_path, index=False)

    print(f"\n=== fixed effects -> {fixed_path} ===")
    print(fixed.to_string(index=False))
    print(f"\n=== convergence -> {conv_path} ===")
    print(convergence.to_string(index=False))
    print(f"\nrandom effects (per repo x metric) -> {re_path}")

    return fixed, random_effects, convergence


if __name__ == "__main__":
    run()
