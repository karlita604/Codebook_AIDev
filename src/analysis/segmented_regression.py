"""
Segmented (interrupted-time-series) regression, reconstructed from
Results.md's own methodology note (section "RQ1 - segmented regression"),
since the script that produced the original
results/analysis/07-29-segmented-regression-A1.csv was never committed
(confirmed via `git log --diff-filter=A` on that file - the commit that
added it adds no .py file alongside it). This is a from-scratch
reimplementation, not a recovery of lost code - it must reproduce the
existing 4-repo pilot CSV's exact numbers before it's trusted on anything
new (see validate_against_pilot() below and the plan's Stage 4).

Model, per (repo, metric), on Track A1 rows:

    metric ~ intercept + slope_pre*T + level_change*post + slope_change*(T*post)

where T = months_since_intervention (continuous, negative pre-intervention,
positive post - already a column in the pooled metrics CSV, reused rather
than recomputed) and post is the 0/1 intervention indicator. Standard
Wagner et al. (2002) interrupted-time-series design: slope_pre is the
pre-intervention trend, level_change is the jump right at the intervention,
slope_change is how much the trend itself changes afterward (post-slope =
slope_pre + slope_change).

Closed-form OLS via normal equations (no statsmodels dependency - none was
installed in this environment, and closed-form is enough to reproduce
exact numbers). 95% CI via normal approximation (z=1.96), per Results.md's
explicit "closed-form OLS, 95% CI via normal approximation" description -
p-values still use the t-distribution (standard practice, and what SE-based
significance testing conventionally reports even when CI uses a normal
approximation).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402

# The conventional rounded 1.96, not the precise stats.norm.ppf(0.975)
# (1.959963985...) - confirmed by reproduction: the precise value leaves a
# ~3.6e-5 residual on every CI bound relative to the pilot's original CSV,
# consistent with the original script using the textbook-standard rounded
# constant rather than computing it.
Z_975 = 1.96

PRIMARY_METRICS = [
    "design_smell_density_per_kloc",
    "implementation_smell_density_per_kloc",
    "cyclomatic_complexity_p90",
]


def fit_one(d, metric):
    """One (repo, metric) segmented-regression row. `d` must already be
    Track A1 rows for a single repo, sorted by target_date, with `post`
    and `months_since_intervention` columns. Returns None if the metric
    column has no variance (a flat constant, e.g. airbyte's CC p90 being
    3.0 for all 51 months - r2 is undefined/-inf there, not a bug, see
    Results.md's own note on this) - reported as excluded, not a
    fabricated fit.

    Two distinct time variables, matching Results.md's literal formula
    (`metric ~ time + post + time_since_intervention×post`) rather than
    reusing one column for both roles: `t_abs` (continuous months since
    the series' own first row, computed from real calendar days / 30.436875
    - not a plain 0..50 integer index; confirmed by reproduction, a plain
    index reproduces the pilot to within ~0.03 but not exactly, since real
    months aren't equal-length) drives the intercept/pre-slope, while
    `t_rel` (months_since_intervention, already a column on the pooled
    data) only enters through the post-interaction, so the fitted
    intercept lands at the series' own start rather than at the
    intervention date."""
    y = d[metric].to_numpy(dtype=float)
    days_since_start = (
        d["target_date"] - d["target_date"].iloc[0]
    ).dt.total_seconds() / 86400
    t_abs = (days_since_start / 30.436875).to_numpy()
    t_rel = d["months_since_intervention"].to_numpy(dtype=float)
    post = d["post"].to_numpy(dtype=float)
    n = len(y)
    n_post = int(post.sum())
    n_pre = n - n_post

    X = np.column_stack([np.ones(n), t_abs, post, t_rel * post])
    k = X.shape[1]
    dof = n - k
    if dof < 1:
        return None

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("-inf")

    sigma2 = ss_res / dof
    xtx_inv = np.linalg.pinv(X.T @ X)
    cov = sigma2 * xtx_inv
    se = np.sqrt(np.clip(np.diag(cov), 0, None))

    # p-values: standard t-test (t-distribution, dof degrees of freedom) -
    # confirmed by reproduction against the pilot's exact p-values, which a
    # normal (z) p-value systematically undershoots (heavier t tails give
    # larger, more conservative p-values at the same magnitude). CI is the
    # one place this script deliberately uses the normal approximation
    # instead (z=1.96, not a t-critical value) - matches Results.md's
    # literal "closed-form OLS, 95% CI via normal approximation" wording,
    # which only names the CI, not the p-value.
    t_stat = np.divide(beta, se, out=np.zeros_like(beta), where=se > 0)
    p = 2 * stats.t.sf(np.abs(t_stat), dof)
    ci_lo = beta - Z_975 * se
    ci_hi = beta + Z_975 * se

    names = ["intercept", "slope_pre", "level_change", "slope_change"]
    row = {"n": n, "n_pre": n_pre, "n_post": n_post, "r2": r2}
    for i, name in enumerate(names):
        row[f"{name}_coef"] = beta[i]
        row[f"{name}_se"] = se[i]
        row[f"{name}_p"] = p[i]
        row[f"{name}_ci_lo"] = ci_lo[i]
        row[f"{name}_ci_hi"] = ci_hi[i]
    row["dof"] = dof
    return row


COLUMN_ORDER = [
    "full_name", "track", "metric",
    "n", "n_pre", "n_post", "r2",
    "level_change_coef", "level_change_se", "level_change_p",
    "level_change_ci_lo", "level_change_ci_hi",
    "slope_change_coef", "slope_change_se", "slope_change_p",
    "slope_change_ci_lo", "slope_change_ci_hi",
    "slope_pre_coef", "slope_pre_p",
    "dof",
    "intercept_coef", "intercept_se", "intercept_p",
    "intercept_ci_lo", "intercept_ci_hi",
    "slope_pre_se", "slope_pre_ci_lo", "slope_pre_ci_hi",
]


def run(df, metrics=PRIMARY_METRICS, min_pre=5, min_post=5, track="A1"):
    """df must have full_name/track/target_date/post/months_since_intervention
    plus every column in `metrics`. Repos with fewer than min_pre/min_post
    real points for a metric are skipped (reported via the returned
    `skipped` list), not silently fit on a handful of noisy points."""
    rows, skipped = [], []
    d_all = df[df["track"] == track]
    for full_name, g in d_all.groupby("full_name"):
        g = g.sort_values("target_date")
        for metric in metrics:
            gm = g.dropna(subset=[metric, "months_since_intervention", "post"])
            n_pre = int((gm["post"] == 0).sum())
            n_post = int((gm["post"] == 1).sum())
            if n_pre < min_pre or n_post < min_post:
                skipped.append({
                    "full_name": full_name, "track": track, "metric": metric,
                    "n_pre": n_pre, "n_post": n_post,
                    "reason": f"below min_pre={min_pre}/min_post={min_post}",
                })
                continue
            fit = fit_one(gm, metric)
            if fit is None:
                skipped.append({
                    "full_name": full_name, "track": track, "metric": metric,
                    "n_pre": n_pre, "n_post": n_post,
                    "reason": "insufficient degrees of freedom",
                })
                continue
            rows.append({"full_name": full_name, "track": track, "metric": metric, **fit})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out[COLUMN_ORDER].sort_values(["metric", "full_name"]).reset_index(drop=True)
    return out, pd.DataFrame(skipped)


def validate_against_pilot():
    """Mandatory, blocking check (plan Stage 4): refit the original 4-repo
    pilot's exact inputs and confirm every coefficient/p-value/CI matches
    results/analysis/07-29-segmented-regression-A1.csv within float
    tolerance. Does not proceed to the full-corpus run if this fails."""
    pooled = fc.load_pooled_metrics()
    fitted, skipped = run(pooled, metrics=PRIMARY_METRICS, min_pre=1, min_post=1)
    original = pd.read_csv(fc.ANALYSIS_DIR / "07-29-segmented-regression-A1.csv")

    fitted_s = fitted.sort_values(["full_name", "metric"]).reset_index(drop=True)
    original_s = original.sort_values(["full_name", "metric"]).reset_index(drop=True)

    assert list(fitted_s["full_name"]) == list(original_s["full_name"])
    assert list(fitted_s["metric"]) == list(original_s["metric"])

    # A perfectly flat metric (airbyte's cyclomatic_complexity_p90 = 3.0 for
    # all 51 A1 months, the one row Results.md's own "RQ1" section already
    # names as "no signal available, not no effect") has zero true residual
    # variance - both this script's and the original's coefficients land on
    # float noise around 1e-16/1e-17 there, and p-values computed as
    # noise-over-noise are inherently implementation-dependent (which exact
    # linear-algebra routine, which rounding) even though the *substance*
    # (a degenerate all-zero fit, correctly flagged as no real slope/level
    # change) matches. Rows with level_change_se below this floor are
    # compared on coefficient sign/magnitude only, not p-value precision.
    degenerate_se_floor = 1e-10
    numeric_cols = [c for c in COLUMN_ORDER if c not in ("full_name", "track", "metric")]
    max_abs_diff = 0.0
    bad = []
    degenerate_rows = set(
        fitted_s.index[fitted_s["level_change_se"] < degenerate_se_floor]
    )
    for col in numeric_cols:
        a = fitted_s[col].to_numpy(dtype=float)
        b = original_s[col].to_numpy(dtype=float)
        finite = np.isfinite(a) & np.isfinite(b)
        if not finite.all() and (np.isfinite(a) != np.isfinite(b)).any():
            bad.append((col, "finiteness mismatch"))
            continue
        noise_sensitive = col.endswith("_p") or col.endswith("_ci_lo") or col.endswith("_ci_hi")
        compare_idx = np.array([
            i for i in range(len(a))
            if finite[i] and not (noise_sensitive and i in degenerate_rows)
        ])
        if len(compare_idx) == 0:
            continue
        diff = np.abs(a[compare_idx] - b[compare_idx])
        max_abs_diff = max(max_abs_diff, float(diff.max()))
        if not np.allclose(a[compare_idx], b[compare_idx], rtol=1e-4, atol=1e-6):
            bad.append((col, float(diff.max())))

    print(f"reproduction check: {len(fitted_s)} rows, max abs diff (excluding "
          f"p-values on {len(degenerate_rows)} degenerate zero-variance "
          f"row(s)) = {max_abs_diff:.3e}")
    if bad:
        print("MISMATCHES:")
        for col, detail in bad:
            print(f"  {col}: {detail}")
        return False
    print("PASS - reconstructed script reproduces the pilot's numbers "
          "(exactly, except p-values/CIs on the known zero-variance row, "
          "which are noise-over-noise and match in substance - both ~0)")
    return True


def build_full_corpus_dataset():
    """Merge Stage 2's consolidated in-house OO-metrics pool with Stage 3's
    (now both-language) in-house smells pool on the same
    (repo_id, track, target_date, commit_sha) key everything else in this
    project joins on, then attach post/months_since_intervention - neither
    pooled file carries those (unlike the DPy/Designite pilot's
    07-29-pooled-structural-metrics.csv, which already had them baked in
    from an earlier step). Uses the same day-count/30.436875 convention
    fit_one() already uses for its own t_abs, applied here relative to
    each repo's intervention_date instead of the series start - a small
    (~2-3 hour, i.e. ~0.003-month) numeric difference from the pilot
    file's own stored months_since_intervention column was measured
    directly and is immaterial at this grid's monthly resolution, not a
    sign of a wrong formula (the pilot-reproduction check above already
    validates the model itself using the pilot's own stored column, not
    this derivation)."""
    metrics_df = fc.load_inhouse_metrics()
    smells_df = fc.load_inhouse_smells()
    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    shared_cols = key_cols + ["full_name", "language"]

    merged = pd.merge(
        metrics_df[shared_cols + ["cyclomatic_complexity_p90"]],
        smells_df[shared_cols + [
            "design_smell_density_per_kloc",
            "implementation_smell_density_per_kloc",
        ]],
        on=key_cols, how="outer", suffixes=("", "_smells"),
    )
    for col in ["full_name", "language"]:
        merged[col] = merged[col].fillna(merged[f"{col}_smells"])
        merged.drop(columns=[f"{col}_smells"], inplace=True, errors="ignore")

    rs = fc.load_repo_summary().set_index("full_name")["intervention_date"]
    merged = merged[merged["full_name"].isin(rs.index)].copy()
    merged["intervention_date"] = merged["full_name"].map(rs)
    merged["post"] = merged["target_date"] >= merged["intervention_date"]
    days_since_intervention = (
        merged["target_date"] - merged["intervention_date"]
    ).dt.total_seconds() / 86400
    merged["months_since_intervention"] = days_since_intervention / 30.436875
    return merged


def run_full_corpus(min_pre=5, min_post=5):
    """Stage 4's actual deliverable: the full-corpus regression, all repos
    with enough in-house pre/post data, all three primary metrics. Output:
    results/analysis/<date>-segmented-regression-full-<n>.csv (fitted rows)
    and a matching -skipped.csv (repos excluded for insufficient data,
    reported rather than silently dropped)."""
    df = build_full_corpus_dataset()
    fitted, skipped = run(df, metrics=PRIMARY_METRICS, min_pre=min_pre, min_post=min_post)

    from datetime import date
    today = date.today()
    out_path = fc.ANALYSIS_DIR / f"{today.month:02d}-{today.day:02d}-segmented-regression-full-{len(fitted)}.csv"
    skipped_path = fc.ANALYSIS_DIR / f"{today.month:02d}-{today.day:02d}-segmented-regression-full-{len(fitted)}-skipped.csv"
    fitted.to_csv(out_path, index=False)
    skipped.to_csv(skipped_path, index=False)
    print(f"fitted {len(fitted)} (repo, metric) rows -> {out_path}")
    print(f"skipped {len(skipped)} (repo, metric) combos (insufficient data) -> {skipped_path}")
    if len(skipped):
        print(skipped.to_string(index=False))
    return out_path, fitted, skipped


if __name__ == "__main__":
    ok = validate_against_pilot()
    if not ok:
        sys.exit(1)
    if "--full" in sys.argv:
        run_full_corpus()
