"""
RQ-H1: what explains the direction/magnitude split in RQ1's per-repo
segmented-regression coefficients, instead of re-measuring that a split
exists (already established - see Results.md's "no consistent cross-repo
direction" headline, most recently at the pilot's 4-repo and the
in-house tool's first 15-repo full-corpus scale). Re-scoped mid-session
to the just-landed 100-repo corpus run (see REGRESSION_FULL_PATH/
SMELLS_POOLED_PATH below): 79 repos clear the regression's own
min_pre/min_post=5 gate (237 rows, 3 metrics), not 15 - the same
questions below, now with meaningfully more statistical power than the
original eyeball version of this check.

This treats the pinned full-corpus regression output's own fitted
coefficients (level_change_coef, slope_change_coef - one row per repo x
primary metric) as the *outcome* of a second-stage analysis, and asks
whether repo-level covariates already sitting in
`results/repos/*-repo-summary-*.csv` (agent-PR dosage, agent diversity,
language, stars) or the regression's own pre-intervention slope predict
which way a repo moves. RQ5 (Results.md) tried an eyeball version of the
dosage question on N=4 with one predictor and found nothing.

Join key: repo_id, not full_name, kept deliberately even though the
100-repo cut's 79 regression-eligible repos happen to join cleanly on
full_name alone (0 missing, checked directly). The smaller 15-repo cut
this script was first built against did *not* join cleanly on full_name -
`marin-community/levanter` (in-house pool) vs. `stanford-crfm/levanter`
(repo-summary registry), same GitHub repo under the same numeric repo_id
496005961, renamed/transferred between when the two source files were
generated. That repo isn't among the 79 repos clearing the regression
gate at 100-repo scale (dropped for insufficient pre/post data, not
because the rename got fixed), so the join is clean by accident here, not
because the underlying hazard went away - repo_id stays the join key so a
future corpus cut that does include a renamed repo doesn't silently drop
it instead of erroring.

A real data-quality artifact found while building this (not assumed
clean from a successful script exit - checked the joined output by hand
first, then re-checked after the corpus grew to 100 repos): **16 of the
79 regression-eligible repos have a degenerate, zero-variance
`cyclomatic_complexity_p90` series** (`level_change_se` ~1e-15,
indistinguishable from float noise) - mostly, but not only, C# repos
(`dotnet/aspire`, `dotnet/aspnetcore`, `dotnet/maui`, and 13 others - see
the printed is_degenerate breakdown). This is the same "no signal
available, not no effect" situation Results.md already documented for
airbyte's DPy-based CC p90 (constant at 3.0 for 51 months) - a broader
instance of a known artifact, not a new bug, and a *larger* fraction of
the corpus at 100-repo scale (16/79 = 20%) than the 4/15 (27%) seen at
the smaller cut, so still very much worth guarding against, not something
that becomes negligible as the corpus grows. A flat metric with a
coefficient of ~0 and an SE of ~0 is not evidence of "no correlation with
covariates" - it is missing data wearing a numeric disguise, and would
silently anchor a rank correlation or bias a two-group comparison if left
in. `is_degenerate` (True where `level_change_se < DEGENERATE_SE_FLOOR`)
is computed on the joined frame and every downstream table below is run
twice - once on the full 237 rows, once with degenerate CC-p90 rows
dropped - so a finding that only exists because of these zero points is
visible as such, not silently baked into a single reported number.

Two further threats to interpretation, named here rather than left implicit:

1. **Regression-to-the-mean / mechanical coupling.** `slope_pre_coef` and
   `slope_change_coef` are two coefficients from the *same* OLS fit on the
   same series (see segmented_regression.fit_one's design matrix:
   `[intercept, t_abs, post, t_rel*post]`). `t_abs` and `t_rel*post` are
   correlated by construction (both are time, one restricted to the post
   window), so their estimated coefficients carry some built-in negative
   covariance from ordinary multicollinearity, independent of any real
   "agents reverse an existing trend" effect. A correlation between
   slope_pre and slope_change is reported below, but it cannot be read as
   pure causal signal without a synthetic-null check (simulate a flat
   series with the same noise level and confirm the null correlation is
   ~0) - not run this session, flagged as follow-up, not silently ignored.
2. **N=79 repos, repeated across 3 metrics (n=237), not 237 independent
   observations.** Every correlation/regression below is also run
   per-metric (n=79, or n=63 for CC p90 once degenerate rows are dropped)
   precisely because pooling across metrics without accounting for
   repo-level clustering would overstate the effective sample size. A real
   improvement over the 15-repo cut this script was first built against,
   but still an exploratory pass, not a confirmatory test - reported as
   such, no p-value here should be read as surviving a multiple-comparison
   correction.
"""

import ast
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis import segmented_regression as sr  # noqa: E402

# Pinned, not fc.latest_*() - deliberately, not out of caution about live
# data. The 100-repo corpus-scaling run finished and landed mid-session
# (confirmed directly: results/analysis/08-19-inhouse-{metrics,smells}-pooled.csv,
# 96/94 repos respectively, 0 duplicate (repo_id, track, target_date,
# commit_sha) keys, all status=="ok"; results/analysis/
# 08-19-segmented-regression-full-237.csv, 79 repos x 3 metrics, already
# fit against the new pools and joining cleanly - 0 missing - against
# results/repos/08-17-repo-summary-235.csv's covariates). Pinned to these
# exact filenames anyway, not fc.latest_*(), purely for reproducibility:
# this script's own output should describe a named, fixed snapshot, not
# silently re-describe itself if a later run further grows the corpus.
# Bump these three constants deliberately when that happens, not
# automatically via a glob.
REGRESSION_FULL_PATH = fc.ANALYSIS_DIR / "08-19-segmented-regression-full-237.csv"
SMELLS_POOLED_PATH = fc.ANALYSIS_DIR / "08-19-inhouse-smells-pooled.csv"
METRICS_POOLED_PATH = fc.ANALYSIS_DIR / "08-19-inhouse-metrics-pooled.csv"
REPO_SUMMARY_PATH = fc.REPO_SUMMARY_DIR / "08-17-repo-summary-235.csv"

OUT_DIR = fc.ANALYSIS_DIR
OUTCOME_COLS = ["level_change_coef", "slope_change_coef"]
NUMERIC_COVARIATES = [
    "agent_pr_count", "distinct_agents", "log1p_stars", "slope_pre_coef",
]
# Same order-of-magnitude reasoning as segmented_regression.py's own
# degenerate_se_floor (1e-10) - real SEs in this table run 1e-2 to 1
# (see the printed correlation table), the 4 known-degenerate CC-p90 rows
# sit at ~1e-15, so 1e-8 cleanly separates "real, small SE" from
# "zero-variance fit, SE is float noise" with wide margin either side.
DEGENERATE_SE_FLOOR = 1e-8


def parse_dominant_agent(agent_breakdown_str):
    """agent_breakdown is stored as a Python dict repr (str(dict) from the
    Phase 1a collection script, e.g. "{'Devin': 327}") not JSON - confirmed
    directly against real rows before picking a parser; ast.literal_eval
    handles it safely (no eval() on untrusted-ish data)."""
    if pd.isna(agent_breakdown_str):
        return None
    d = ast.literal_eval(agent_breakdown_str)
    return max(d.items(), key=lambda kv: kv[1])[0]


def build_id_map():
    """full_name -> repo_id, sourced from the same pinned in-house smells
    pool (SMELLS_POOLED_PATH) the regression output's full_name values were
    built from - this is the correct side of the levanter rename to trust
    (see module docstring), not the repo-summary registry's older name."""
    smells = pd.read_csv(SMELLS_POOLED_PATH, usecols=["full_name", "repo_id"])
    return smells.drop_duplicates("full_name").set_index("full_name")["repo_id"]


def load_repo_summary_pinned():
    df = pd.read_csv(REPO_SUMMARY_PATH)
    df["intervention_date"] = pd.to_datetime(df["intervention_date"], utc=True)
    return df


def load_joined():
    """One row per (repo, metric): RQ1's fitted coefficients plus repo-level
    covariates, joined on repo_id. Raises loudly (not silently drops) if
    any regression row fails to join - the levanter case above is the only
    known instance and is handled by joining on repo_id in the first
    place, not by a special-cased exception list."""
    reg = pd.read_csv(REGRESSION_FULL_PATH)
    id_map = build_id_map()
    reg = reg.copy()
    reg["repo_id"] = reg["full_name"].map(id_map)
    unmapped = reg[reg["repo_id"].isna()]["full_name"].unique()
    if len(unmapped):
        raise ValueError(f"no repo_id found for: {list(unmapped)}")

    rs = load_repo_summary_pinned()
    rs = rs.copy()
    rs["dominant_agent"] = rs["agent_breakdown"].apply(parse_dominant_agent)
    rs["log1p_stars"] = np.log1p(rs["stars"])
    covariate_cols = [
        "repo_id", "language", "stars", "log1p_stars", "agent_pr_count",
        "distinct_agents", "dominant_agent",
    ]

    out = reg.merge(rs[covariate_cols], on="repo_id", how="left", validate="many_to_one")
    missing = out[out["language"].isna()]
    if len(missing):
        raise ValueError(f"repo_id join to repo-summary failed for: "
                          f"{missing['full_name'].unique().tolist()}")
    out["is_degenerate"] = out["level_change_se"].abs() < DEGENERATE_SE_FLOOR
    return out


def ols_small(y, X, names):
    """Same closed-form-OLS/t-test shape as segmented_regression.fit_one,
    reused here rather than pulled in via statsmodels (still not a
    dependency in this environment) - deliberately small (2-3 predictors)
    given n~79 per metric, dof reported alongside every row so an
    under-powered fit is visible, not hidden."""
    n, k = X.shape
    dof = n - k
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float(resid @ resid)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else float("-inf")
    if dof < 1:
        return {"n": n, "dof": dof, "r2": r2}
    sigma2 = ss_res / dof
    cov = sigma2 * np.linalg.pinv(X.T @ X)
    se = np.sqrt(np.clip(np.diag(cov), 0, None))
    t_stat = np.divide(beta, se, out=np.zeros_like(beta), where=se > 0)
    p = 2 * stats.t.sf(np.abs(t_stat), dof)
    row = {"n": n, "dof": dof, "r2": r2}
    for i, name in enumerate(names):
        row[f"{name}_coef"] = beta[i]
        row[f"{name}_se"] = se[i]
        row[f"{name}_p"] = p[i]
    return row


def pairwise_correlations(df, drop_degenerate):
    """Spearman rank correlation between each outcome coefficient and each
    numeric covariate, run separately per metric (n=79, or n=63 for CC p90
    when drop_degenerate=True) and pooled (n=237/221, flagged as
    clustered/non-independent in the printed output, not presented as if
    it were that many independent draws). Called twice by run() - see
    module docstring's "degenerate" paragraph for why a with/without
    comparison matters here rather than picking one silently."""
    d = df[~df["is_degenerate"]] if drop_degenerate else df
    rows = []
    groups = list(d.groupby("metric")) + [("pooled (non-independent, see caveat)", d)]
    for metric, g in groups:
        for outcome in OUTCOME_COLS:
            for cov in NUMERIC_COVARIATES:
                gg = g.dropna(subset=[outcome, cov])
                if len(gg) < 4:
                    continue
                rho, p = stats.spearmanr(gg[cov], gg[outcome])
                rows.append({
                    "metric": metric, "outcome": outcome, "covariate": cov,
                    "n": len(gg), "spearman_rho": rho, "p": p,
                })
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["outcome", "metric", "covariate"]).reset_index(drop=True)
    return out


def language_split_test(df, drop_degenerate):
    """Mann-Whitney U + Cliff's delta (this project's own established
    convention for two-group comparisons, per the framing at the top of
    Results.md) comparing Python vs C# repos' outcome coefficients, per
    metric. n=1 C# repo in the original pilot made this untestable; the
    full corpus has 6 C# / 9 Python repos here, still small but a real
    two-group test for the first time. Particularly important to run with
    drop_degenerate=True for CC p90: 3 of the 4 known-degenerate rows are
    C# repos (dotnet/aspire, dotnet/aspnetcore, dotnet/maui), so a
    Python-vs-C# split on that metric risks comparing real Python variation
    against C# zero-noise rather than a real cross-language difference."""
    d = df[~df["is_degenerate"]] if drop_degenerate else df
    rows = []
    for metric, g in d.groupby("metric"):
        for outcome in OUTCOME_COLS:
            py = g.loc[g["language"] == "Python", outcome].dropna()
            cs = g.loc[g["language"] == "C#", outcome].dropna()
            if len(py) < 2 or len(cs) < 2:
                continue
            u, p = stats.mannwhitneyu(py, cs, alternative="two-sided")
            # Cliff's delta: P(x>y) - P(x<y) over all pairs, Python vs C#
            diffs = py.to_numpy()[:, None] - cs.to_numpy()[None, :]
            delta = (np.sum(diffs > 0) - np.sum(diffs < 0)) / diffs.size
            rows.append({
                "metric": metric, "outcome": outcome,
                "n_python": len(py), "n_csharp": len(cs),
                "median_python": py.median(), "median_csharp": cs.median(),
                "mannwhitney_p": p, "cliffs_delta": delta,
            })
    return pd.DataFrame(rows)


def multivariate_fits(df, drop_degenerate):
    """slope_change_coef ~ intercept + slope_pre_coef + log1p(agent_pr_count),
    fit separately per metric (n=79, dof=76, or n=63/dof=60 for CC p90 when
    drop_degenerate=True) - the two predictors named explicitly in the
    module docstring as the ones worth a combined check (pre-trajectory and
    dosage), not a kitchen-sink model with 4 predictors at n=79."""
    d = df[~df["is_degenerate"]] if drop_degenerate else df
    rows = []
    for metric, g in d.groupby("metric"):
        gg = g.dropna(subset=["slope_change_coef", "slope_pre_coef", "agent_pr_count"])
        y = gg["slope_change_coef"].to_numpy(dtype=float)
        x1 = gg["slope_pre_coef"].to_numpy(dtype=float)
        x2 = np.log1p(gg["agent_pr_count"].to_numpy(dtype=float))
        X = np.column_stack([np.ones(len(gg)), x1, x2])
        fit = ols_small(y, X, ["intercept", "slope_pre_coef", "log1p_agent_pr_count"])
        rows.append({"metric": metric, **fit})
    return pd.DataFrame(rows)


def load_raw_pooled():
    """Metrics + smells merged the same way segmented_regression.
    build_full_corpus_dataset() does (same key, same column selection),
    pinned to the 08-19 100-repo files rather than that function's own
    fc.latest_*() loaders - and deliberately stops short of attaching
    post/months_since_intervention, since the placebo check below needs to
    attach those against a *fake* date, not the real intervention_date."""
    metrics_df = pd.read_csv(METRICS_POOLED_PATH)
    metrics_df = metrics_df[metrics_df["status"] == "ok"].copy()
    metrics_df["target_date"] = pd.to_datetime(metrics_df["target_date"], utc=True)
    smells_df = pd.read_csv(SMELLS_POOLED_PATH)
    smells_df = smells_df[smells_df["status"] == "ok"].copy()
    smells_df["target_date"] = pd.to_datetime(smells_df["target_date"], utc=True)

    key_cols = ["repo_id", "track", "target_date", "commit_sha"]
    shared_cols = key_cols + ["full_name", "language"]
    merged = pd.merge(
        metrics_df[shared_cols + ["cyclomatic_complexity_p90"]],
        smells_df[shared_cols + [
            "design_smell_density_per_kloc", "implementation_smell_density_per_kloc",
        ]],
        on=key_cols, how="outer", suffixes=("", "_smells"),
    )
    for col in ["full_name", "language"]:
        merged[col] = merged[col].fillna(merged[f"{col}_smells"])
        merged.drop(columns=[f"{col}_smells"], inplace=True, errors="ignore")
    return merged


def placebo_slope_reversion_check(min_pre=5, min_post=5):
    """Tests this module's own "regression-to-the-mean / mechanical
    coupling" caveat directly, rather than leaving it an unverified
    footnote - the real slope_pre-vs-slope_change correlation turned out
    to be far stronger at 100-repo scale (pooled rho ~-0.70 to -0.71 across
    all 3 primary metrics, r2 up to 0.91 in the multivariate fit) than the
    15-repo cut this caveat was first written against, which raises the
    stakes on knowing whether it's substantially real.

    Refits the *same* segmented-regression model (sr.fit_one/sr.run,
    unchanged - not a parallel reimplementation) per repo per metric, but
    against a placebo "intervention" date: each repo's own median Track-A1
    target_date, i.e. splitting its real series exactly in half, with no
    connection to any actual agent-PR event. If the slope_pre/slope_change
    correlation is comparably strong under this placebo, the real result
    is substantially a generic artifact of fitting two time-slope
    coefficients to the same series (real regression to the mean in a
    noisy trend, or the two regressors' shared multicollinearity - see
    module docstring) rather than evidence that agents specifically
    reverse pre-existing trends. If the placebo correlation is much
    weaker, the real intervention date carries genuine information a
    same-shaped placebo cut can't reproduce."""
    raw = load_raw_pooled()
    a1 = raw[raw["track"] == "A1"].copy()
    a1["intervention_date"] = a1.groupby("full_name")["target_date"].transform("median")
    a1["post"] = a1["target_date"] >= a1["intervention_date"]
    days = (a1["target_date"] - a1["intervention_date"]).dt.total_seconds() / 86400
    a1["months_since_intervention"] = days / 30.436875

    fitted, skipped = sr.run(a1, metrics=sr.PRIMARY_METRICS, min_pre=min_pre, min_post=min_post)
    rows = []
    for metric, g in fitted.groupby("metric"):
        gg = g.dropna(subset=["slope_pre_coef", "slope_change_coef"])
        if len(gg) < 4:
            continue
        rho, p = stats.spearmanr(gg["slope_pre_coef"], gg["slope_change_coef"])
        rows.append({"metric": metric, "n": len(gg), "spearman_rho": rho, "p": p})
    gg_all = fitted.dropna(subset=["slope_pre_coef", "slope_change_coef"])
    if len(gg_all) >= 4:
        rho_all, p_all = stats.spearmanr(gg_all["slope_pre_coef"], gg_all["slope_change_coef"])
        rows.append({"metric": "pooled (non-independent)", "n": len(gg_all),
                      "spearman_rho": rho_all, "p": p_all})
    return pd.DataFrame(rows), fitted, skipped


def run():
    df = load_joined()
    n_degenerate = int(df["is_degenerate"].sum())

    from datetime import date
    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    joined_path = OUT_DIR / f"{prefix}-heterogeneity-joined-{len(df)}.csv"
    df.to_csv(joined_path, index=False)
    print(f"joined {len(df)} (repo, metric) rows, {df['repo_id'].nunique()} repos "
          f"-> {joined_path}")
    print(f"{n_degenerate} rows flagged is_degenerate (zero-variance CC p90 fit) - "
          f"every table below is run twice, with and without them")

    results = {}
    for drop_degenerate in (False, True):
        tag = "excl-degenerate" if drop_degenerate else "all-rows"
        corr = pairwise_correlations(df, drop_degenerate)
        lang = language_split_test(df, drop_degenerate)
        mv = multivariate_fits(df, drop_degenerate)

        corr_path = OUT_DIR / f"{prefix}-heterogeneity-correlations-{tag}.csv"
        lang_path = OUT_DIR / f"{prefix}-heterogeneity-language-split-{tag}.csv"
        mv_path = OUT_DIR / f"{prefix}-heterogeneity-multivariate-{tag}.csv"
        corr.to_csv(corr_path, index=False)
        lang.to_csv(lang_path, index=False)
        mv.to_csv(mv_path, index=False)

        print(f"\n########## {tag} ##########")
        print(f"\n=== pairwise Spearman correlations (n>=4 only) -> {corr_path} ===")
        print(corr.to_string(index=False))
        print(f"\n=== Python vs C# split (Mann-Whitney + Cliff's delta) -> {lang_path} ===")
        print(lang.to_string(index=False))
        print(f"\n=== multivariate: slope_change ~ slope_pre + log1p(agent_pr_count) -> {mv_path} ===")
        print(mv.to_string(index=False))
        results[tag] = (corr, lang, mv)

    placebo, placebo_fitted, placebo_skipped = placebo_slope_reversion_check()
    placebo_path = OUT_DIR / f"{prefix}-heterogeneity-placebo-slope-reversion.csv"
    placebo.to_csv(placebo_path, index=False)
    real_slope_pre_rho = (
        results["all-rows"][0]
        .query("outcome == 'slope_change_coef' and covariate == 'slope_pre_coef'")
        [["metric", "n", "spearman_rho", "p"]]
        .rename(columns={"spearman_rho": "real_rho", "p": "real_p", "n": "real_n"})
    )
    placebo_cmp = placebo.rename(
        columns={"spearman_rho": "placebo_rho", "p": "placebo_p", "n": "placebo_n"}
    ).merge(real_slope_pre_rho, on="metric", how="left")
    print(f"\n########## placebo check: slope_pre vs slope_change under a fake, "
          f"per-repo-median-date 'intervention' -> {placebo_path} ##########")
    print(placebo_cmp.to_string(index=False))
    print("(real_* columns are the same all-rows correlation reported above, "
          "for direct comparison against the placebo)")

    return df, results, placebo_cmp


if __name__ == "__main__":
    run()
