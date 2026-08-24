"""
Hierarchical/mixed-effects companion to heterogeneity_explainers.py's
pairwise_correlations()/multivariate_fits()/placebo_slope_reversion_check()
- additive, not a replacement. Those functions each pool all repo x metric
rows into ONE combined Spearman correlation or OLS fit, explicitly labeled
"pooled (non-independent, see caveat)" in that module's own code - a repo
contributing up to 3 correlated rows (one per metric) is treated as 3
independent observations.

This script refits the same relationships as a MixedLM with a random
intercept on `full_name` - partial pooling that respects the repo-level
clustering the original pooled tests could only flag, not correct for.
Random-intercept-only (not random-slope): each repo contributes at most 3
rows here, one per metric, so there's no meaningful per-repo slope on
"metric" (a categorical, unordered predictor) the way segmented_regression_
mixed_effects.py's per-repo slopes on continuous time variables are.

Reuses heterogeneity_explainers.load_joined() and its OUTCOME_COLS/
NUMERIC_COVARIATES/DEGENERATE_SE_FLOOR unchanged (imported, not
reimplemented) - same 237-row joined table (79 repos x 3 metrics x
covariates), same is_degenerate flag and drop_degenerate=True/False
convention.

One genuine capability gain over the original, not just parity: because
the random intercept absorbs each repo's own baseline across metrics,
multivariate_fits()'s per-metric OLS loop can be replaced with a SINGLE
model spanning all 3 metrics' rows at once (metric added as a fixed
effect) - something the original per-metric-only loop structurally
couldn't do. Reported alongside the per-metric versions, not instead of
them.

No companion for language_split_test() (a two-group Mann-Whitney
comparison, no natural regression/MixedLM analogue) - a stated scope
boundary, not a silent omission.
"""

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats
from statsmodels.tools.sm_exceptions import ConvergenceWarning

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "src" / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis import heterogeneity_explainers as he  # noqa: E402
from src.analysis import segmented_regression as sr  # noqa: E402
from src.analysis.segmented_regression_mixed_effects import _classify  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR


def fit_random_intercept(d, formula, group_col="full_name"):
    """One MixedLM, random intercept only (re_formula defaults to `~1`
    when omitted). Captures convergence warnings rather than letting them
    print-and-vanish, and classifies them via segmented_regression_mixed_
    effects._classify (reused, not duplicated) - trusts statsmodels' own
    `result.converged` as authoritative rather than flagging on any
    hard-failure-sounding warning text, since statsmodels' internal
    optimizer retries can leave an abandoned attempt's failure warning
    behind even when the final result converged cleanly (see that
    function's docstring)."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ConvergenceWarning)
        model = smf.mixedlm(formula, d, groups=d[group_col])
        result = model.fit(reml=True)
        warning_msgs = [str(w.message) for w in caught if issubclass(w.category, ConvergenceWarning)]
    converged, at_boundary, had_hard_failure_warning = _classify(result, warning_msgs)
    if had_hard_failure_warning:
        warning_msgs.append(f"note: hard-failure-sounding warning present but "
                             f"result.converged={result.converged}")
    return result, converged, at_boundary, warning_msgs


def correlation_companions(df, drop_degenerate):
    """Companion to pairwise_correlations(): outcome ~ covariate,
    groups=full_name, random intercept, for every (outcome, covariate)
    pair the original tests. Reported alongside the pooled Spearman for
    direct comparison - Spearman is rank-based/nonparametric, this is a
    parametric linear slope, so this is not an apples-to-apples
    significance comparison, only an apples-to-apples "does modeling the
    clustering change the read" comparison, stated as such."""
    d = df[~df["is_degenerate"]] if drop_degenerate else df
    rows = []
    for outcome in he.OUTCOME_COLS:
        for cov in he.NUMERIC_COVARIATES:
            gg = d.dropna(subset=[outcome, cov, "full_name"])
            if gg["full_name"].nunique() < 5 or len(gg) < 10:
                continue
            gg = gg.rename(columns={outcome: "y", cov: "x"})
            # naive pooled Spearman, reported alongside for direct comparison
            rho, p_spearman = stats.spearmanr(gg["x"], gg["y"])
            result, converged, at_boundary, warnings_ = fit_random_intercept(gg, "y ~ x")
            rows.append({
                "outcome": outcome, "covariate": cov, "n": len(gg),
                "n_repos": gg["full_name"].nunique(),
                "pooled_spearman_rho": rho, "pooled_spearman_p": p_spearman,
                "mixedlm_slope": result.fe_params.get("x", np.nan),
                "mixedlm_slope_se": result.bse_fe.get("x", np.nan),
                "mixedlm_slope_p": result.pvalues.get("x", np.nan),
                "re_var_intercept": result.cov_re.iloc[0, 0],
                "converged": converged, "at_variance_boundary": at_boundary,
                "warnings": " | ".join(warnings_),
            })
    return pd.DataFrame(rows)


def multivariate_companion(df, drop_degenerate):
    """Companion to multivariate_fits(): slope_change_coef ~ slope_pre_coef
    + log1p_agent_pr_count, groups=full_name, random intercept. Run per
    metric (direct analogue of the original per-metric OLS loop) AND once
    across all 3 metrics pooled together with `metric` as an added fixed
    effect - the genuine new capability the random intercept enables (see
    module docstring)."""
    d = df[~df["is_degenerate"]] if drop_degenerate else df
    d = d.dropna(subset=["slope_change_coef", "slope_pre_coef", "agent_pr_count", "full_name"]).copy()
    d["y"] = d["slope_change_coef"]
    d["log1p_agent_pr_count"] = np.log1p(d["agent_pr_count"])

    rows = []
    for metric, g in d.groupby("metric"):
        if g["full_name"].nunique() < 5:
            continue
        result, converged, at_boundary, warnings_ = fit_random_intercept(
            g, "y ~ slope_pre_coef + log1p_agent_pr_count")
        rows.append({
            "scope": metric, "n": len(g), "n_repos": g["full_name"].nunique(),
            "slope_pre_coef_coef": result.fe_params.get("slope_pre_coef", np.nan),
            "slope_pre_coef_p": result.pvalues.get("slope_pre_coef", np.nan),
            "log1p_agent_pr_count_coef": result.fe_params.get("log1p_agent_pr_count", np.nan),
            "log1p_agent_pr_count_p": result.pvalues.get("log1p_agent_pr_count", np.nan),
            "re_var_intercept": result.cov_re.iloc[0, 0],
            "converged": converged, "warnings": " | ".join(warnings_),
        })

    # New capability: all 3 metrics' rows in one model, metric as a fixed
    # effect, repo random intercept absorbing each repo's own baseline
    # across metrics - not possible in the original per-metric-only loop.
    if d["full_name"].nunique() >= 5:
        result, converged, at_boundary, warnings_ = fit_random_intercept(
            d, "y ~ slope_pre_coef + log1p_agent_pr_count + C(metric)")
        rows.append({
            "scope": "all-3-metrics-pooled-with-metric-fixed-effect",
            "n": len(d), "n_repos": d["full_name"].nunique(),
            "slope_pre_coef_coef": result.fe_params.get("slope_pre_coef", np.nan),
            "slope_pre_coef_p": result.pvalues.get("slope_pre_coef", np.nan),
            "log1p_agent_pr_count_coef": result.fe_params.get("log1p_agent_pr_count", np.nan),
            "log1p_agent_pr_count_p": result.pvalues.get("log1p_agent_pr_count", np.nan),
            "re_var_intercept": result.cov_re.iloc[0, 0],
            "converged": converged, "warnings": " | ".join(warnings_),
        })
    return pd.DataFrame(rows)


def placebo_companion(min_pre=5, min_post=5):
    """Companion to placebo_slope_reversion_check(): refits the SAME
    placebo-cut regression (sr.fit_one/sr.run via
    he.placebo_slope_reversion_check's own construction, reused not
    duplicated) then a random-intercept MixedLM slope_change_coef ~
    slope_pre_coef, groups=full_name, alongside the pooled Spearman that
    function already reports."""
    corr, fitted, skipped = he.placebo_slope_reversion_check(min_pre=min_pre, min_post=min_post)
    gg = fitted.dropna(subset=["slope_pre_coef", "slope_change_coef", "full_name"]).copy()
    gg["y"] = gg["slope_change_coef"]
    if gg["full_name"].nunique() < 5:
        return pd.DataFrame(), corr
    result, converged, at_boundary, warnings_ = fit_random_intercept(gg, "y ~ slope_pre_coef")
    row = {
        "n": len(gg), "n_repos": gg["full_name"].nunique(),
        "slope_pre_coef_coef": result.fe_params.get("slope_pre_coef", np.nan),
        "slope_pre_coef_p": result.pvalues.get("slope_pre_coef", np.nan),
        "re_var_intercept": result.cov_re.iloc[0, 0],
        "converged": converged, "warnings": " | ".join(warnings_),
    }
    return pd.DataFrame([row]), corr


def run():
    df = he.load_joined()
    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"

    for drop_degenerate in (False, True):
        tag = "excl-degenerate" if drop_degenerate else "all-rows"
        corr = correlation_companions(df, drop_degenerate)
        mv = multivariate_companion(df, drop_degenerate)
        corr_path = OUT_DIR / f"{prefix}-heterogeneity-mixed-effects-correlations-{tag}.csv"
        mv_path = OUT_DIR / f"{prefix}-heterogeneity-mixed-effects-multivariate-{tag}.csv"
        corr.to_csv(corr_path, index=False)
        mv.to_csv(mv_path, index=False)
        print(f"\n########## {tag} ##########")
        print(f"=== correlation companions -> {corr_path} ===")
        print(corr.to_string(index=False) if not corr.empty else "(no cell reached threshold)")
        print(f"=== multivariate companions -> {mv_path} ===")
        print(mv.to_string(index=False) if not mv.empty else "(no cell reached threshold)")

    placebo_mixed, placebo_pooled = placebo_companion()
    placebo_path = OUT_DIR / f"{prefix}-heterogeneity-mixed-effects-placebo.csv"
    placebo_mixed.to_csv(placebo_path, index=False)
    print(f"\n=== placebo companion -> {placebo_path} ===")
    print(placebo_mixed.to_string(index=False) if not placebo_mixed.empty else "(insufficient data)")
    print("original pooled Spearman placebo result, for comparison:")
    print(placebo_pooled.to_string(index=False))


if __name__ == "__main__":
    run()
