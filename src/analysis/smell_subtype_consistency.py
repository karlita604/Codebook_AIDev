"""
RQ-H3: is smell *type* a more consistent grouping variable than *repo* for
the direction of post-intervention change?

Motivation.md's RQ2 already names the "agents fix locally, not
architecturally" hypothesis, and Results.md's RQ2 (design-smell share of
all smells, pre vs. post) found real, significant composition shifts in
all 4 pilot repos - but split 3-vs-1 in direction, at the coarsest
possible resolution (2 buckets: design vs. implementation). This script
goes one level finer: the in-house smell detector
(`py_smells.py`/`SmellDetector.cs`) already reports which *specific*
Lanza & Marinescu strategy fired - God Class, Data Class (both pooled into
"design"), Feature Envy, Brain Method (both pooled into "implementation")
- as separate counts (`n_god_class`, `n_data_class`, `n_feature_envy`,
`n_brain_method`) on every row of the consolidated smells pool. Confirmed
directly before building on it: these four counts sum exactly to the
existing `design_smell_count`/`implementation_smell_count` columns on
every one of the 7,431 pooled rows (94-repo, 100-corpus-scale run) - not
an approximation.

Each of the 4 subtypes gets its own per-KLOC density and its own
segmented-regression fit per repo (reusing segmented_regression.fit_one
unchanged - same model, same closed-form OLS, same min_pre/min_post=5
gate - not a parallel reimplementation). The question this answers: among
repos with a *significant* (p<.05) slope-change on a given smell subtype,
do they agree on direction more often *within a subtype, pooled across
repos* than *within a repo, pooled across its own subtypes*? If smell type
explains more of the agreement than repo identity does, that's a real,
actionable resolution of the "no consistent direction" finding - it would
mean the inconsistency is about *what kind* of smell, not *which repo*.

Two of the same caveats segmented_regression.py and
heterogeneity_explainers.py already carry apply here unchanged, not
re-litigated: closed-form OLS/min_pre=min_post=5 gate, and small-sample
significance counts unadjusted for multiple comparisons (now 4 subtypes x
up to 94 repos = up to 376 tests, far more than RQ1's 237-row full-corpus
run, so this matters more here, not less).
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis import segmented_regression as sr

# Pinned, not fc.latest_*()/fc.load_inhouse_smells() - see
# heterogeneity_explainers.py's module-level comment for the full story:
# the 100-repo corpus-scaling run landed mid-session (94 repos, 7,431 ok
# rows, 0 duplicate keys - verified directly), and this script is pinned
# to those exact filenames for reproducibility (a named, fixed snapshot),
# matching heterogeneity_explainers.py's own pin so both scripts describe
# the same repo set/vintage.
SMELLS_POOLED_PATH = fc.ANALYSIS_DIR / "08-19-inhouse-smells-pooled.csv"
REGRESSION_FULL_PATH = fc.ANALYSIS_DIR / "08-19-segmented-regression-full-237.csv"
REPO_SUMMARY_PATH = fc.REPO_SUMMARY_DIR / "08-17-repo-summary-235.csv"

OUT_DIR = fc.ANALYSIS_DIR

SUBTYPE_COUNT_COLS = {
    "god_class_density_per_kloc": "n_god_class",
    "data_class_density_per_kloc": "n_data_class",
    "feature_envy_density_per_kloc": "n_feature_envy",
    "brain_method_density_per_kloc": "n_brain_method",
}
SUBTYPE_CATEGORY = {
    "god_class_density_per_kloc": "design",
    "data_class_density_per_kloc": "design",
    "feature_envy_density_per_kloc": "implementation",
    "brain_method_density_per_kloc": "implementation",
}
SUBTYPE_METRICS = list(SUBTYPE_COUNT_COLS)
SIG_P = 0.05


def build_subtype_dataset():
    """The in-house smells pool, with 4 new per-KLOC subtype-density
    columns, joined to each repo's intervention_date the same repo_id-safe
    way heterogeneity_explainers.py joins (the `marin-community/levanter`
    vs. `stanford-crfm/levanter` rename affects this pool too, since it's
    the same source file - handled identically here, not re-derived)."""
    df = pd.read_csv(SMELLS_POOLED_PATH)
    df = df[df["status"] == "ok"].copy()
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    # 2 rows (both crewAIInc/crewAI-tools, its earliest snapshot - 2 real
    # files, genuinely 0 LOC, not a bug - confirmed directly) have
    # total_loc==0; density is NaN there rather than a division error,
    # and NaN rows get dropped by fit_one's own dropna() the same way a
    # missing metric value anywhere else in the pipeline would be.
    kloc = (df["total_loc"] / 1000).replace(0, np.nan)
    for density_col, count_col in SUBTYPE_COUNT_COLS.items():
        df[density_col] = df[count_col] / kloc

    rs = pd.read_csv(REPO_SUMMARY_PATH)
    rs["intervention_date"] = pd.to_datetime(rs["intervention_date"], utc=True)
    rs = rs.set_index("repo_id")["intervention_date"]
    unmapped = df.loc[~df["repo_id"].isin(rs.index), "full_name"].unique()
    if len(unmapped):
        raise ValueError(f"no repo_id match in repo-summary for: {list(unmapped)}")
    df["intervention_date"] = df["repo_id"].map(rs)
    df["post"] = df["target_date"] >= df["intervention_date"]
    days_since_intervention = (
        df["target_date"] - df["intervention_date"]
    ).dt.total_seconds() / 86400
    df["months_since_intervention"] = days_since_intervention / 30.436875
    return df


def fit_subtypes(min_pre=5, min_post=5):
    """Segmented regression, all 4 subtype densities, Track A1, reusing
    segmented_regression.run() unchanged."""
    df = build_subtype_dataset()
    fitted, skipped = sr.run(df, metrics=SUBTYPE_METRICS, min_pre=min_pre, min_post=min_post)
    fitted["category"] = fitted["metric"].map(SUBTYPE_CATEGORY)
    return fitted, skipped


def fit_aggregate_baseline(min_pre=5, min_post=5):
    """The existing 2-bucket (design/implementation) aggregate fit, as the
    baseline this script's finer-grained result is compared against -
    reuses the already-committed full-corpus regression output
    (segmented_regression's own build_full_corpus_dataset/run) rather than
    refitting, so the baseline is exactly the numbers already in
    Results.md, not a re-derived approximation of them."""
    reg = pd.read_csv(REGRESSION_FULL_PATH)
    agg = reg[reg["metric"].isin([
        "design_smell_density_per_kloc", "implementation_smell_density_per_kloc",
    ])].copy()
    agg["category"] = agg["metric"].map({
        "design_smell_density_per_kloc": "design",
        "implementation_smell_density_per_kloc": "implementation",
    })
    return agg


def _pairwise_sign_agreement(rows):
    """Fraction of all pairs within `rows` (a list of +1/-1 signs) that
    match. Undefined (None) for fewer than 2 rows - reported as such, not
    as a fabricated 100%/0%."""
    if len(rows) < 2:
        return None, 0
    agree, total = 0, 0
    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            total += 1
            if rows[i] == rows[j]:
                agree += 1
    return agree / total, total


def consistency_comparison(fitted, group_a_col, group_a_label, group_b_col, group_b_label):
    """Core comparison: pairwise sign-agreement rate among *significant*
    (p<.05) slope_change_coef rows, grouped by group_a vs. by group_b.
    Applied twice by run() - once with group_a='metric'/group_b='full_name'
    on the 4-subtype fit (the real question), once on the 2-bucket
    aggregate baseline, so the finer-grained result is read against the
    resolution the project already had, not in isolation."""
    sig = fitted[fitted["slope_change_p"] < SIG_P].copy()
    sig["sign"] = np.sign(sig["slope_change_coef"])

    def agreement_table(group_col):
        rows = []
        for key, g in sig.groupby(group_col):
            rate, n_pairs = _pairwise_sign_agreement(list(g["sign"]))
            rows.append({group_col: key, "n_significant": len(g), "n_pairs": n_pairs,
                         "pairwise_sign_agreement": rate})
        return pd.DataFrame(rows)

    a_table = agreement_table(group_a_col)
    b_table = agreement_table(group_b_col)

    def weighted_mean_agreement(table):
        t = table.dropna(subset=["pairwise_sign_agreement"])
        if t["n_pairs"].sum() == 0:
            return None
        return float((t["pairwise_sign_agreement"] * t["n_pairs"]).sum() / t["n_pairs"].sum())

    summary = {
        f"n_significant_total": len(sig),
        f"{group_a_label}_weighted_mean_agreement": weighted_mean_agreement(a_table),
        f"{group_a_label}_n_groups_with_2plus_sig": int((a_table["n_significant"] >= 2).sum()),
        f"{group_b_label}_weighted_mean_agreement": weighted_mean_agreement(b_table),
        f"{group_b_label}_n_groups_with_2plus_sig": int((b_table["n_significant"] >= 2).sum()),
    }
    return a_table, b_table, summary


def run(min_pre=5, min_post=5):
    fitted, skipped = fit_subtypes(min_pre=min_pre, min_post=min_post)
    subtype_by_metric, subtype_by_repo, subtype_summary = consistency_comparison(
        fitted, "metric", "by_type", "full_name", "by_repo",
    )

    aggregate = fit_aggregate_baseline(min_pre=min_pre, min_post=min_post)
    # Same "by_type" label as the 4-subtype call above (not "by_bucket") -
    # deliberately, so the two summaries share column names below and can
    # be stacked into one comparison table without a post-hoc rename.
    agg_by_metric, agg_by_repo, agg_summary = consistency_comparison(
        aggregate, "metric", "by_type", "full_name", "by_repo",
    )

    from datetime import date
    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    fitted_path = OUT_DIR / f"{prefix}-smell-subtype-regression-{len(fitted)}.csv"
    skipped_path = OUT_DIR / f"{prefix}-smell-subtype-regression-{len(fitted)}-skipped.csv"
    fitted.to_csv(fitted_path, index=False)
    skipped.to_csv(skipped_path, index=False)

    print(f"fitted {len(fitted)} (repo, subtype) rows ({fitted['full_name'].nunique()} repos, "
          f"4 subtypes) -> {fitted_path}")
    print(f"skipped {len(skipped)} combos (insufficient pre/post data) -> {skipped_path}")

    print("\n=== 4-subtype resolution: significant (p<.05) slope_change sign agreement ===")
    print("-- by subtype (pooled across repos) --")
    print(subtype_by_metric.to_string(index=False))
    print("-- by repo (pooled across its own subtypes) --")
    print(subtype_by_repo.to_string(index=False))
    print("-- summary --")
    for k, v in subtype_summary.items():
        print(f"  {k}: {v}")

    print("\n=== 2-bucket baseline (design vs. implementation, already-existing aggregate fit) ===")
    print("-- by bucket (pooled across repos) --")
    print(agg_by_metric.to_string(index=False))
    print("-- by repo (pooled across its own 2 buckets) --")
    print(agg_by_repo.to_string(index=False))
    print("-- summary --")
    for k, v in agg_summary.items():
        print(f"  {k}: {v}")

    summary_path = OUT_DIR / f"{prefix}-smell-subtype-consistency-summary.csv"
    pd.DataFrame([
        {"resolution": "4-subtype", **subtype_summary},
        {"resolution": "2-bucket-baseline", **agg_summary},
    ]).to_csv(summary_path, index=False)
    print(f"\nsummary table -> {summary_path}")

    return fitted, skipped, (subtype_by_metric, subtype_by_repo, subtype_summary), \
        (agg_by_metric, agg_by_repo, agg_summary)


if __name__ == "__main__":
    run()
