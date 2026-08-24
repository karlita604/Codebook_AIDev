"""
Hierarchical/mixed-effects companion to review_intensity_explainer.py's
review_intensity_correlations() - additive, not a replacement. That
function pools all repo x metric rows into ONE combined Spearman
correlation per covariate, same "pooled (non-independent, see caveat)"
pattern as heterogeneity_explainers.py.

Reuses the pinned results/analysis/08-21-review-intensity-joined.csv
directly (not recomputed) and heterogeneity_explainers_mixed_effects.py's
fit_random_intercept/_classify (imported, not duplicated).

**n=15 repos with matched review data is thin for a hierarchical model**
- flagged prominently, not glossed over: with only 15 groups, MixedLM's
random-intercept variance estimate is unstable by construction (few
groups makes it hard to distinguish real between-repo variance from
noise), so this companion is more a demonstration of method parity with
the rest of this project's mixed-effects layer than a result to lean on.
Still worth running - the fixed-effect estimate itself doesn't need many
groups to be valid, just the variance component needs many groups to be
*precise* - but report accordingly.

No companion for median_split_test() (a two-group Mann-Whitney
comparison, no natural regression analogue) - same stated scope boundary
as heterogeneity_explainers_mixed_effects.py's omission of
language_split_test().
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "src" / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis.heterogeneity_explainers_mixed_effects import fit_random_intercept  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
JOINED_PATH = fc.ANALYSIS_DIR / "08-21-review-intensity-joined.csv"
COVARIATES = ["mean_comments", "log1p_n_agent_prs_matched"]
OUTCOME_COLS = ["level_change_coef", "slope_change_coef"]


def run():
    df = pd.read_csv(JOINED_PATH)
    n_repos = df["full_name"].nunique()
    print(f"{n_repos} repos x {df['metric'].nunique()} metrics = {len(df)} rows "
          f"(pinned {JOINED_PATH.name}) - n=15-repo caveat applies, see module docstring")

    rows = []
    for outcome in OUTCOME_COLS:
        for cov in COVARIATES:
            gg = df.dropna(subset=[outcome, cov, "full_name"]).rename(columns={outcome: "y", cov: "x"})
            if gg["full_name"].nunique() < 5 or len(gg) < 10:
                print(f"skipping {outcome} ~ {cov}: only {gg['full_name'].nunique()} repos / {len(gg)} rows")
                continue
            result, converged, at_boundary, warnings_ = fit_random_intercept(gg, "y ~ x")
            rows.append({
                "outcome": outcome, "covariate": cov, "n": len(gg),
                "n_repos": gg["full_name"].nunique(),
                "mixedlm_slope": result.fe_params.get("x"),
                "mixedlm_slope_se": result.bse_fe.get("x"),
                "mixedlm_slope_p": result.pvalues.get("x"),
                "re_var_intercept": result.cov_re.iloc[0, 0],
                "converged": converged, "at_variance_boundary": at_boundary,
                "warnings": " | ".join(warnings_),
            })

    out = pd.DataFrame(rows)
    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"
    out_path = OUT_DIR / f"{prefix}-review-intensity-mixed-effects.csv"
    out.to_csv(out_path, index=False)
    print(f"\n=== review-intensity mixed-effects companion (n={n_repos} repos - thin, see docstring) -> {out_path} ===")
    print(out.to_string(index=False) if not out.empty else "(no cell reached threshold)")
    return out


if __name__ == "__main__":
    run()
