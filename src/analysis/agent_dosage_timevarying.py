"""
Time-varying agent dosage: does the *within-repo, month-to-month*
intensity of agent-PR activity during a repo's own post-intervention
window correlate with that window's structural-metric trajectory? RQ5
(the pilot) and `heterogeneity_explainers.py`'s RQ-H1 both tested dosage
as one static number per repo (total agent-PR count) against RQ1's
fitted slope-change coefficient - both came up empty. This is the
untested version: don't collapse the whole post-period to one number,
correlate each repo's own monthly dosage against that same month's
metric value.

**Hard constraint, confirmed directly on the file actually used (not
assumed from a prior session's note)**: the AIDev agent-PR registry
(`results/repos/08-17-aidev-agent-prs-3332.csv`, still the latest -
confirmed no newer `*-aidev-agent-prs-*.csv` exists) covers PRs with
`created_at` from **2024-12-24 to 2025-07-30** (`REGISTRY_START`/
`REGISTRY_END` below, computed from `created_at.min()`/`.max()` on this
exact file, not hardcoded from memory of an earlier session's number).
Any month outside this window has UNKNOWN agent activity, not zero -
scoped_repo_month_dosage() below only ever returns rows for months
inside the window; there is no code path that could turn "not covered"
into a silent 0.

**Design decision 1 - raw monthly count, not agent-PR share of total
monthly volume.** Checked before deciding, not assumed: Track B's B1
sampling track (`pr_sampling_pipeline.py`) already records a real
GitHub Search API `total_count` per query unit, in the `*-queries.csv`
ledger - but that total_count is scoped to each B1 unit's own 2-day
(day 1-2 UTC) sample window, not the full month, so it cannot be
extrapolated into a true monthly-PR-volume denominator without a
material, unvalidated assumption about within-month PR-rate uniformity.
Building a real share-based denominator would need a *new* GitHub
Search API collection (full-month `created:` range queries, count-only -
the cheaper fallback named in the request that motivated this file), not
a reuse of existing Track B output. Not launched here: a Track B
gap-fill run (`results/pr_samples/08-24-pr-sample-rq1gap-3339.csv`) was
still actively in progress against the same token pool at the time this
was written (2,708/3,339 query units done per its own progress.json),
and stacking a second concurrent GitHub collection against it risked
contention for no clear payoff - see Design decision 2 for why the
payoff is small regardless.

**Design decision 2 - repo-stratified pooled correlation, not a
per-repo regression, and not a change to segmented_regression.py
itself.** Checked directly before choosing: of the 79 RQ1-regression-
eligible repos, only 72 have ANY month where post-intervention overlaps
the registry's observed window at all (1 repo's intervention postdates
the registry entirely), and only 12/79 have >=3 distinct overlapping
months - the rest have 1-2. A per-repo trend line needs points a single
repo mostly doesn't have; this instead pools repo-months across repos
(same "pooled (non-independent, see caveat)" + repo-stratified-
permutation convention `agent_code_survival_full_corpus.py` already
established) and checks whether the pooled relationship survives
shuffling each repo's own monthly dosage values among its own months -
option (1) from the request that motivated this file (a separate,
narrower analysis) rather than (2) (folding dosage into
segmented_regression.py's own fitted model), specifically because this
scope constraint means there usually isn't enough within-repo variation
for a per-repo interaction term to mean much, and because leaving RQ1's
shared regression untouched keeps every other RQ's numbers stable.

**Data used** (state exactly which files/counts fed this run - printed
again at the top of run()'s own output, not just here):
- `results/repos/08-17-aidev-agent-prs-3332.csv` (3,332 rows, 235 repos,
  created_at 2024-12-24 to 2025-07-30) - dosage source.
- `results/analysis/08-19-segmented-regression-full-237.csv` (79 repos x
  3 metrics, 237 rows) - defines the eligible-repo set, same pinned file
  `heterogeneity_explainers.py` uses, for the same reproducibility
  reason (see that module's docstring).
- `segmented_regression.build_full_corpus_dataset()`'s own inputs
  (`08-19-inhouse-metrics-pooled.csv`, `08-19-inhouse-smells-pooled.csv`,
  `08-17-repo-summary-235.csv`) - reused unchanged, not re-derived here.
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
import segmented_regression as sr  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
AIDEV_AGENT_PRS_PATH = fc.REPO_SUMMARY_DIR / "08-17-aidev-agent-prs-3332.csv"
REGRESSION_FULL_PATH = fc.ANALYSIS_DIR / "08-19-segmented-regression-full-237.csv"

METRICS = [
    "cyclomatic_complexity_p90",
    "design_smell_density_per_kloc",
    "implementation_smell_density_per_kloc",
]


def load_agent_registry():
    df = pd.read_csv(AIDEV_AGENT_PRS_PATH)
    df["created_at"] = pd.to_datetime(df["created_at"], utc=True)
    return df


def registry_window(registry):
    return registry["created_at"].min(), registry["created_at"].max()


def monthly_dosage(registry):
    """One row per (repo_id, year_month) inside the registry's own
    observed range: raw count of agent PRs created that month. No row is
    ever emitted for a month the registry doesn't cover - there is no
    zero-fill step, so "not covered" and "covered, zero PRs" stay
    distinguishable downstream (a repo-month simply absent from this
    frame is the former)."""
    d = registry.copy()
    d["year_month"] = d["created_at"].dt.to_period("M")
    dosage = (
        d.groupby(["repo_id", "year_month"])
        .size()
        .rename("monthly_agent_pr_count")
        .reset_index()
    )
    return dosage


def eligible_repos():
    reg = pd.read_csv(REGRESSION_FULL_PATH, usecols=["full_name"])
    return sorted(reg["full_name"].unique())


def scoped_repo_month_metrics(reg_start, reg_end):
    """Per (full_name, metric, year_month): mean metric value, restricted
    to Track A1, the 79 RQ1-eligible repos, post-intervention rows only,
    and target_date inside the registry's observed window - the only
    window where dosage is actually knowable (see module docstring).
    Metrics are handled independently (not a single dropna across all
    three) since `build_full_corpus_dataset()`'s outer join means a given
    target_date row can carry one metric's value and not another's."""
    df = sr.build_full_corpus_dataset()
    df = df[df["track"] == "A1"].copy()
    df = df[df["full_name"].isin(eligible_repos())]
    df = df[df["post"] & (df["target_date"] >= reg_start) & (df["target_date"] <= reg_end)]
    df["year_month"] = df["target_date"].dt.to_period("M")

    frames = []
    for metric in METRICS:
        m = df.dropna(subset=[metric])[["repo_id", "full_name", "year_month", metric]].copy()
        m = m.groupby(["repo_id", "full_name", "year_month"], as_index=False)[metric].mean()
        m["metric"] = metric
        m = m.rename(columns={metric: "value"})
        frames.append(m)
    return pd.concat(frames, ignore_index=True)


def coverage_report(scoped, n_eligible):
    rows = []
    for metric, g in scoped.groupby("metric"):
        per_repo_months = g.groupby("full_name")["year_month"].nunique()
        rows.append({
            "metric": metric,
            "n_eligible_repos": n_eligible,
            "n_repos_with_any_scoped_month": len(per_repo_months),
            "n_repos_with_ge2_months": int((per_repo_months >= 2).sum()),
            "n_repos_with_ge3_months": int((per_repo_months >= 3).sum()),
            "n_repo_months": len(g),
            "median_months_per_repo": per_repo_months.median(),
            "max_months_per_repo": int(per_repo_months.max()),
        })
    return pd.DataFrame(rows)


def stratified_permutation_correlation(joined, n_perms=300, seed=20260824):
    """Repo-stratified permutation check on the pooled Spearman
    correlation between monthly dosage and monthly metric value - same
    mechanism as `agent_code_survival_full_corpus.py`'s label-shuffle
    tests, adapted for two continuous variables: shuffle each repo's own
    `monthly_agent_pr_count` values among that repo's own months (breaking
    any real within-repo time-alignment while preserving each repo's
    marginal dosage distribution and every repo's overall metric level),
    and see where the real pooled rho falls in the resulting null. A
    repo contributing only 1 scoped month cannot be meaningfully shuffled
    (a single value has one permutation) - it still contributes its point
    to every null draw's pooled rho, same as it does to the real one, so
    it isn't a source of null variance but isn't dropped either, matching
    how a single-observation repo group behaves in this project's other
    stratified tests."""
    rng = np.random.default_rng(seed)
    real_rho, real_p = stats.spearmanr(joined["monthly_agent_pr_count"], joined["value"])

    dosage = joined["monthly_agent_pr_count"].to_numpy(dtype=float)
    value = joined["value"].to_numpy(dtype=float)
    full_name = joined["full_name"].to_numpy()
    repo_masks = [full_name == name for name in np.unique(full_name)]

    null_rhos = np.empty(n_perms)
    for i in range(n_perms):
        shuffled = dosage.copy()
        for mask in repo_masks:
            shuffled[mask] = rng.permutation(shuffled[mask])
        null_rhos[i], _ = stats.spearmanr(shuffled, value)

    frac_le = (null_rhos <= real_rho).mean()
    p_two_sided = min(1.0, 2 * min(
        (np.sum(null_rhos <= real_rho) + 1) / (n_perms + 1),
        (np.sum(null_rhos >= real_rho) + 1) / (n_perms + 1),
    ))
    return {
        "n_perms": n_perms, "n": len(joined), "n_repos": joined["full_name"].nunique(),
        "real_pooled_rho": real_rho, "naive_p": real_p,
        "null_mean_rho": float(np.nanmean(null_rhos)),
        "null_std_rho": float(np.nanstd(null_rhos, ddof=1)),
        "null_percentile_of_real": frac_le * 100,
        "p_empirical_two_sided": p_two_sided,
    }


def run():
    registry = load_agent_registry()
    reg_start, reg_end = registry_window(registry)
    print(f"=== AIDev agent-PR registry: {len(registry)} rows, "
          f"{registry['repo_id'].nunique()} repos, "
          f"created_at {reg_start.date()} to {reg_end.date()} ===")

    dosage = monthly_dosage(registry)
    n_eligible = len(eligible_repos())
    scoped = scoped_repo_month_metrics(reg_start, reg_end)
    # Left join + fillna(0), not inner join: a scoped repo-month absent
    # from `dosage` means the registry observed that month and counted 0
    # agent PRs in it (see monthly_dosage()'s docstring) - a real zero,
    # not a missing observation. An inner join would silently drop every
    # true-zero-dosage month, biasing the sample toward months that
    # happened to have agent activity - checked and fixed before trusting
    # any correlation below (caught by the row count being suspiciously
    # identical across all three metrics, which an inner join produces
    # whenever it's dosage-availability, not metric-availability, driving
    # which rows survive).
    scoped = scoped.merge(dosage, on=["repo_id", "year_month"], how="left")
    scoped["monthly_agent_pr_count"] = scoped["monthly_agent_pr_count"].fillna(0)
    print(f"=== {n_eligible} RQ1-eligible repos; "
          f"{scoped['full_name'].nunique()} have >=1 scoped repo-month "
          f"(post-intervention, inside the registry's observed window) ===\n")

    cov = coverage_report(scoped, n_eligible)
    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    cov_path = OUT_DIR / f"{prefix}-agent-dosage-timevarying-coverage.csv"
    cov.to_csv(cov_path, index=False)
    print(f"=== coverage -> {cov_path} ===")
    print(cov.to_string(index=False))

    corr_rows, strat_rows = [], []
    for metric, g in scoped.groupby("metric"):
        rho, p = stats.spearmanr(g["monthly_agent_pr_count"], g["value"])
        corr_rows.append({
            "metric": metric, "n": len(g), "n_repos": g["full_name"].nunique(),
            "spearman_rho": rho, "naive_p": p,
        })
        strat = stratified_permutation_correlation(g)
        strat["metric"] = metric
        strat_rows.append(strat)

    corr = pd.DataFrame(corr_rows)
    corr_path = OUT_DIR / f"{prefix}-agent-dosage-timevarying-correlations.csv"
    corr.to_csv(corr_path, index=False)
    print(f"\n=== pooled Spearman correlation, monthly dosage vs. monthly metric -> {corr_path} ===")
    print(corr.to_string(index=False))

    strat_df = pd.DataFrame(strat_rows)
    strat_cols = ["metric"] + [c for c in strat_df.columns if c != "metric"]
    strat_df = strat_df[strat_cols]
    strat_path = OUT_DIR / f"{prefix}-agent-dosage-timevarying-stratified-permutation.csv"
    strat_df.to_csv(strat_path, index=False)
    print(f"\n=== repo-stratified permutation check -> {strat_path} ===")
    print(strat_df.to_string(index=False))

    return scoped, cov, corr, strat_df


if __name__ == "__main__":
    run()
