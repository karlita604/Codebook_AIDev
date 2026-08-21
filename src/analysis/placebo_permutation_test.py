"""
RQ-H1 follow-up: turn HeterogeneityExplainers.md's single-point placebo
check (one fake "intervention" per repo - its own median Track-A1 date,
refit once) into a real permutation test with an empirical null
distribution, per that doc's own closing "practical implication" -
a one-shot comparison is suggestive, not a p-value against a real null.

Same target relationship as before: `slope_pre_coef` (RQ1's fitted
pre-intervention trend) vs. `slope_change_coef` (how much the trend
changes post-intervention), both from the same OLS fit
(segmented_regression.fit_one's design matrix
`[intercept, t_abs, post, t_rel*post]`) - `t_abs` and `t_rel*post` share
variance by construction, so some of this correlation is mechanical
(regression-to-the-mean in a noisy trend fit twice), independent of any
real "agents reverse pre-existing trends" effect. The single placebo
point in HeterogeneityExplainers.md (cut at each repo's own median date)
found the placebo correlation at least as strong as the real one on
every metric - this script asks the sharper question the doc's own
"practical implication" flagged as unanswered: does the *real*
intervention date's correlation sit meaningfully outside the range a
large sample of *arbitrary* cut dates produces, or is it a typical draw
from that same null process?

**A priori expectation, stated before running rather than after (worth
naming directly since it bears on how to read a null result here)**: if
the mechanical-coupling story is right, it should hold for *any* cut
point, not just the median - so this permutation test is expected, going
in, to mostly reconfirm HeterogeneityExplainers.md's finding rather than
overturn it. That expectation is exactly why it's still worth running
properly: "the real cut isn't distinguishable from one arbitrary cut"
(the original check) is a much weaker claim than "the real cut isn't
distinguishable from hundreds of arbitrary cuts spanning the full range
of feasible splits" (this one) - and if the real cut *did* turn out to
sit outside that fuller null, that would be a genuine surprise worth
revising the doc's conclusion over, not a foregone negative result.

Method: for each of N_DRAWS independent draws, assign every repo an
independent random placebo cut date drawn uniformly from that repo's own
*feasible* cut points (any real Track-A1 snapshot date leaving at least
min_pre/min_post real points on each side - the same gate
segmented_regression.run() itself applies, so a placebo draw is exactly
as demanding of the data as the real fit was), refit the *identical*
segmented-regression model via sr.run() (unchanged - not reimplemented),
and record the pooled and per-metric Spearman rho between
slope_pre_coef and slope_change_coef for that draw. N_DRAWS draws build
an empirical null distribution; the real correlation (from the pinned
`08-19-segmented-regression-full-237.csv`, via
heterogeneity_explainers.load_joined/pairwise_correlations - reused, not
recomputed by hand) is then read against that distribution's own
mean/std and rank to get an empirical p-value, not a one-shot comparison.

Pinned inputs (same files HeterogeneityExplainers.md pins, unchanged
here - see that doc's "Data" section for why pinning matters this
session): results/analysis/08-19-inhouse-{metrics,smells}-pooled.csv
(via heterogeneity_explainers.load_raw_pooled()), results/analysis/
08-19-segmented-regression-full-237.csv (the real fit, via
heterogeneity_explainers.load_joined()), results/repos/
08-17-repo-summary-235.csv (covariates, via the same loader).
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis import segmented_regression as sr  # noqa: E402
from src.analysis import heterogeneity_explainers as he  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
MIN_PRE = 5
MIN_POST = 5
N_DRAWS = 300
SEED = 20260821  # today's date, for a fixed, documented, non-cherry-picked seed


def feasible_cut_candidates(a1, min_pre=MIN_PRE, min_post=MIN_POST):
    """Per-repo array of feasible placebo cut dates: any of that repo's
    own real Track-A1 snapshot dates that would leave >= min_pre points
    strictly before it and >= min_post points at-or-after it (the exact
    `post = target_date >= cut_date` convention sr.run()/the original
    placebo check both use). Repos with too few total points to ever
    satisfy both bounds are dropped here - sr.run()'s own min_pre/
    min_post gate would drop them anyway, per-metric, once real NaN
    patterns are accounted for; this is a coarser, repo-level pre-filter
    only used to pick candidate dates, not a substitute for that gate."""
    candidates = {}
    for full_name, g in a1.groupby("full_name"):
        dates = np.sort(g["target_date"].unique())
        L = len(dates)
        lo, hi = min_pre, L - min_post  # valid 0-based cut index k, inclusive
        if lo > hi:
            continue
        candidates[full_name] = dates[lo:hi + 1]
    return candidates


def apply_placebo_cuts(a1, cuts):
    """cuts: full_name -> single placebo cut date (np.datetime64/Timestamp).
    Repos with no entry in `cuts` (infeasible - see feasible_cut_candidates)
    are dropped, same as if they'd never cleared the real gate."""
    out = a1[a1["full_name"].isin(cuts.keys())].copy()
    out["intervention_date"] = out["full_name"].map(cuts)
    out["post"] = out["target_date"] >= out["intervention_date"]
    days = (out["target_date"] - out["intervention_date"]).dt.total_seconds() / 86400
    out["months_since_intervention"] = days / 30.436875
    return out


def one_draw(a1, candidates, rng):
    cuts = {name: arr[rng.integers(len(arr))] for name, arr in candidates.items()}
    a1_draw = apply_placebo_cuts(a1, cuts)
    fitted, _skipped = sr.run(a1_draw, metrics=sr.PRIMARY_METRICS,
                               min_pre=MIN_PRE, min_post=MIN_POST)
    rows = []
    for metric, g in fitted.groupby("metric"):
        gg = g.dropna(subset=["slope_pre_coef", "slope_change_coef"])
        if len(gg) < 4:
            continue
        rho, _p = stats.spearmanr(gg["slope_pre_coef"], gg["slope_change_coef"])
        rows.append({"metric": metric, "n": len(gg), "spearman_rho": rho})
    gg_all = fitted.dropna(subset=["slope_pre_coef", "slope_change_coef"])
    if len(gg_all) >= 4:
        rho_all, _p = stats.spearmanr(gg_all["slope_pre_coef"], gg_all["slope_change_coef"])
        # Exact string match to heterogeneity_explainers.pairwise_correlations'
        # own pooled-group label, so real_correlations()'s lookup below joins
        # cleanly rather than silently dropping the pooled row.
        rows.append({"metric": "pooled (non-independent, see caveat)", "n": len(gg_all),
                      "spearman_rho": rho_all})
    return rows


def real_k_per_repo(a1, repo_summary):
    """Per-repo (k_real, L): k_real = count of that repo's own Track-A1
    snapshot dates strictly before its real intervention_date (so
    post = date >= intervention_date has L - k_real points, matching
    fit_one's own convention exactly). Used only to build the
    split-balance-matched null below - not itself a fit."""
    iv = repo_summary.set_index("full_name")["intervention_date"]
    out = {}
    for full_name, g in a1.groupby("full_name"):
        if full_name not in iv.index:
            continue
        dates = np.sort(g["target_date"].unique())
        k = int((dates < iv.loc[full_name]).sum())
        out[full_name] = (k, len(dates))
    return out


def feasible_cut_candidates_matched(a1, repo_summary, min_pre=MIN_PRE, min_post=MIN_POST,
                                     window_frac=0.15, min_margin=3):
    """Second null, addressing a real confound found by hand-checking the
    first (uniform) null's result before trusting it: real intervention
    dates turn out to be heavily pre-loaded (79-repo mean n_pre~32 vs.
    n_post~10, ratio ~3.25x - real-world agent adoption lands late
    relative to each repo's full observed history), while a cut sampled
    *uniformly* over the whole feasible index range averages close to a
    50/50 split. An uneven split changes slope_change_coef's own
    statistical power (fewer post points -> noisier post-slope estimate)
    independent of any agent effect, which could by itself weaken an
    observed correlation via ordinary measurement-error attenuation - so
    "real rho is weaker than the uniform null" is confounded with "real
    cuts are far more lopsided than uniform-null cuts" and shouldn't be
    read as a finding about the real intervention date specifically until
    that's controlled for.

    This null instead restricts each repo's candidate cuts to a window
    around that repo's own *real* split position (k_real +/- max(min_margin,
    window_frac * L)) - varying the exact placebo date (no connection to
    the real agent-PR event) while holding the pre/post balance, and thus
    the statistical power of the fit, approximately fixed at the real
    value. Falls back to the repo's full feasible range, clipped to the
    window, same infeasible-repo drop as the uniform version."""
    real_k = real_k_per_repo(a1, repo_summary)
    candidates = {}
    for full_name, g in a1.groupby("full_name"):
        if full_name not in real_k:
            continue
        k_real, L = real_k[full_name]
        margin = max(min_margin, round(window_frac * L))
        lo = max(min_pre, k_real - margin)
        hi = min(L - min_post, k_real + margin)
        if lo > hi:
            continue
        dates = np.sort(g["target_date"].unique())
        candidates[full_name] = dates[lo:hi + 1]
    return candidates


def real_correlations():
    """Real, per-metric + pooled Spearman rho for slope_pre_coef vs.
    slope_change_coef, read off the pinned real regression output via
    heterogeneity_explainers' own loader/correlation function (reused,
    not recomputed independently) - the same "all-rows" number
    HeterogeneityExplainers.md's original single-point placebo check
    compared against."""
    joined = he.load_joined()
    corr = he.pairwise_correlations(joined, drop_degenerate=False)
    real = corr.query("outcome == 'slope_change_coef' and covariate == 'slope_pre_coef'")
    return real[["metric", "n", "spearman_rho", "p"]].rename(
        columns={"spearman_rho": "real_rho", "p": "real_p_parametric", "n": "real_n"}
    )


def summarize_against_real(null_df, real):
    summary_rows = []
    for metric, g in null_df.groupby("metric"):
        null_rhos = g["spearman_rho"].to_numpy()
        real_row = real[real["metric"] == metric]
        if real_row.empty:
            continue
        real_rho = float(real_row["real_rho"].iloc[0])
        null_mean = float(null_rhos.mean())
        null_std = float(null_rhos.std(ddof=1))
        # two-sided empirical p-value: how extreme is the real value
        # relative to the null draws, either direction, with the
        # standard +1 correction (Davison & Hinkley) so p is never
        # reported as exactly 0 off a finite sample of draws.
        frac_le = float((null_rhos <= real_rho).mean())
        p_two_sided = min(1.0, 2 * min(
            (np.sum(null_rhos <= real_rho) + 1) / (len(null_rhos) + 1),
            (np.sum(null_rhos >= real_rho) + 1) / (len(null_rhos) + 1),
        ))
        z = (real_rho - null_mean) / null_std if null_std > 0 else float("nan")
        summary_rows.append({
            "metric": metric,
            "n_draws": len(null_rhos),
            "real_rho": real_rho,
            "real_n_repos": int(real_row["real_n"].iloc[0]),
            "null_mean_rho": null_mean,
            "null_std_rho": null_std,
            "null_min_rho": float(null_rhos.min()),
            "null_max_rho": float(null_rhos.max()),
            "null_percentile_of_real": frac_le * 100,
            "z_vs_null": z,
            "p_empirical_two_sided": p_two_sided,
        })
    return pd.DataFrame(summary_rows)


def run_null(candidates, a1, n_draws, seed):
    rng = np.random.default_rng(seed)
    draw_rows = []
    for i in range(n_draws):
        for row in one_draw(a1, candidates, rng):
            draw_rows.append({"draw": i, **row})
    return pd.DataFrame(draw_rows)


def run(n_draws=N_DRAWS, seed=SEED):
    he_raw = he.load_raw_pooled()
    a1 = he_raw[he_raw["track"] == "A1"].copy()
    repo_summary = he.load_repo_summary_pinned()
    real = real_correlations()

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"

    uniform_candidates = feasible_cut_candidates(a1)
    print(f"[uniform null] {len(uniform_candidates)} repos have >=1 feasible "
          f"placebo cut date (min_pre={MIN_PRE}, min_post={MIN_POST})")
    uniform_null = run_null(uniform_candidates, a1, n_draws, seed)
    uniform_summary = summarize_against_real(uniform_null, real)

    matched_candidates = feasible_cut_candidates_matched(a1, repo_summary)
    print(f"[split-matched null] {len(matched_candidates)} repos have >=1 "
          f"feasible placebo cut date within the matched window")
    matched_null = run_null(matched_candidates, a1, n_draws, seed + 1)
    matched_summary = summarize_against_real(matched_null, real)

    uniform_null["null_kind"] = "uniform"
    matched_null["null_kind"] = "split_matched"
    uniform_summary["null_kind"] = "uniform"
    matched_summary["null_kind"] = "split_matched"
    null_df = pd.concat([uniform_null, matched_null], ignore_index=True)
    summary = pd.concat([uniform_summary, matched_summary], ignore_index=True)

    null_path = OUT_DIR / f"{prefix}-placebo-permutation-null-draws.csv"
    summary_path = OUT_DIR / f"{prefix}-placebo-permutation-summary.csv"
    null_df.to_csv(null_path, index=False)
    summary.to_csv(summary_path, index=False)

    print(f"\n{n_draws} draws x 2 null strategies x metric groups -> {null_path}")
    print(f"\n=== real rho vs. empirical null (both strategies) -> {summary_path} ===")
    print(summary.to_string(index=False))
    return null_df, summary


if __name__ == "__main__":
    run()
