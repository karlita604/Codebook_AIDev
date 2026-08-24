"""
RQ-H2: does the *intensity* of human review around a repo's agent PRs
predict the direction/magnitude of its RQ1 structural-health slope- and
level-change coefficients? Motivation.md's core premise is that PR
review is supposed to gate quality collaboratively; this is the first
test of that premise specifically for the agentic-PR era, joined against
the same outcome table heterogeneity_explainers.py already uses.

**Data availability - checked directly before building on it, per
ProjectStatus.md's own open item ("Track B's deeper PR stats... still
not built") and its item-3 caveat that comment counts (not diff size or
review-round detail) are what's actually captured.** Two real gaps found
before this could even be attempted, neither assumed away:

1. **Track B's original PR-comment sample predated the 100-repo scaling
   run and was never re-collected at that scale.** The first PR-level
   file with a `comments` column, `results/pr_samples/
   08-04-pr-sample-4990.csv` (4990 rows, 22 repos - the pilot + Phase 2's
   21-repo cut), only covered 16 of the 79 repos that clear RQ1's
   regression gate (`08-19-segmented-regression-full-237.csv`). Fixed by
   `pr_sampling_pipeline.py --repos-file` (added alongside this change):
   targets an exact repo set instead of suggest_pilot's stratified n-based
   pick, so a gap-fill run can be scoped to precisely the repos missing
   coverage (`results/pr_samples/rq1-gap-repos-63.csv`, the 63 repos this
   found with zero PR-comment data - re-derive with the diff shown in
   that file's own generating command if the eligible-repo set changes).
   `load_agent_pr_reviews()` below no longer pins to the single 08-04
   file - it concatenates every `*-pr-sample-*.csv` in `results/
   pr_samples/`, so a completed gap-fill run's output is picked up
   automatically without another code change. **Whether that gap-fill run
   has actually been executed against GitHub is a separate, checkable
   fact - see `coverage_report()`'s output, not this docstring, for the
   current true count.** As of the change that added --repos-file, it had
   NOT yet been run (needs GITHUB_TOKEN, which wasn't available in the
   environment that made the pipeline change - see the pipeline's own
   module docstring for the ~2-3 hour cost estimate at this scale). Note
   also: `dotnet/aspire` (1 of the 63 gap repos) returns 422 from the
   Search API regardless of token - confirmed directly that even an
   unauthenticated request gets the same "cannot be searched" error, so
   this isn't a fine-grained-vs-classic-PAT issue (both a fine-grained
   and a classic PAT search every *other* dotnet/* repo in the gap set
   fine) - it's that repo specifically excluded from GitHub's search
   index, likely tied to a repo transfer (its REST endpoint 301-redirects
   to a different internal repo ID). Nothing to fix on our end; it'll
   just stay uncovered same as the other 62 get filled in.
2. **The PR-sample file doesn't itself flag which PRs are agent-authored**
   - it's a calendar-window sample of PRs near each repo's intervention
     date (track B1/B2), a mix of human and agent PRs, with no `agent`
     column. Agent authorship lives in a separate source
     (`results/repos/08-17-aidev-agent-prs-3332.csv`, has an `agent`
     column and `is_intervention_pr`, but no comment counts). The two
     have to be matched on `(repo_id, pr_number)` - extracted from the
     agent file's `html_url` (no `pr_number` column there) - before
     "review intensity on agent PRs" is even measurable.

Pinned input for the agent-authorship side only (PR-sample side is now
dynamic, see above): `results/repos/08-17-aidev-agent-prs-3332.csv`, plus
heterogeneity_explainers.load_joined()'s own pinned regression/covariate
files (`08-19-segmented-regression-full-237.csv`, `08-19-inhouse-smells-
pooled.csv` for the repo_id map, `08-17-repo-summary-235.csv`).
"""

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402
from src.analysis import heterogeneity_explainers as he  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
PR_SAMPLE_DIR = fc.ROOT / "results" / "pr_samples"
# AIDev agent-PR registry: pinned, not fc.latest_*() - same reasoning as
# heterogeneity_explainers.py's own module docstring (a concurrent pipeline
# job was actively writing new dated files into results/analysis/ this
# session; confirmed by mtime check immediately before this script was
# written that no newer aidev-agent-prs file has landed since this one).
AIDEV_AGENT_PRS_PATH = fc.REPO_SUMMARY_DIR / "08-17-aidev-agent-prs-3332.csv"

OUTCOME_COLS = ["level_change_coef", "slope_change_coef"]


def _load_all_pr_samples():
    """Concatenates every Track B PR-comment sample file rather than
    pinning one - coverage accumulates across separate collection runs
    (the original pilot/21-repo cut, plus any --repos-file gap-fill run
    scoped to repos that cut missed, see pr_sampling_pipeline.py and this
    module's docstring), and a completed gap-fill run should be picked up
    here without another code change. Excludes the pipeline's own query-
    ledger files (`*-pr-sample-*-queries.csv`), which share the stem but
    aren't PR data."""
    files = sorted(
        p for p in PR_SAMPLE_DIR.glob("*-pr-sample-*.csv")
        if not p.stem.endswith("-queries")
    )
    if not files:
        raise FileNotFoundError(f"no *-pr-sample-*.csv in {PR_SAMPLE_DIR}")
    return pd.concat([pd.read_csv(f) for f in files], ignore_index=True)


def load_agent_pr_reviews():
    """Matches Track B's PR-comment sample against the AIDev agent-PR
    registry on (repo_id, pr_number) - the only way to know which
    sampled PRs are agent-authored, since the PR-sample file itself
    carries no agent flag (see module docstring). pr_number isn't a
    column on the agent-PR side; extracted from its html_url instead,
    checked to parse cleanly on every row before trusting it."""
    prs = _load_all_pr_samples()
    agent = pd.read_csv(AIDEV_AGENT_PRS_PATH)

    # A handful of PRs are sampled twice under different tracks/windows
    # (e.g. once B1 windowed, once as a B2 undersample fill-in) - checked
    # directly that every duplicate (repo_id, pr_number) group agrees on
    # `comments` (6/6 groups, single unique value each) before collapsing
    # to one row per PR, so this dedup can't silently average over two
    # different comment counts for the same PR.
    dup_mask = prs.duplicated(subset=["repo_id", "pr_number"], keep=False)
    if dup_mask.any():
        n_inconsistent = (
            prs[dup_mask].groupby(["repo_id", "pr_number"])["comments"].nunique() > 1
        ).sum()
        if n_inconsistent:
            raise ValueError(f"{n_inconsistent} duplicate (repo_id, pr_number) "
                              f"groups disagree on comment count - dedup assumption violated")
    prs = prs.drop_duplicates(subset=["repo_id", "pr_number"], keep="first")

    agent = agent.copy()
    agent["pr_number"] = agent["html_url"].str.extract(r"/pull/(\d+)$")
    unparsed = agent["pr_number"].isna().sum()
    if unparsed:
        raise ValueError(f"{unparsed} agent-PR rows failed to parse a PR "
                          f"number out of html_url - check the URL format")
    agent["pr_number"] = agent["pr_number"].astype("int64")
    prs = prs.copy()
    prs["pr_number"] = prs["pr_number"].astype("int64")

    matched = prs.merge(
        agent[["repo_id", "pr_number", "agent", "is_intervention_pr"]],
        on=["repo_id", "pr_number"], how="inner", validate="one_to_one",
    )
    return matched


def coverage_report(matched, reg_repos):
    """One row per repo in the 79-repo regression-eligible set: whether
    it has any matched agent-PR review data, and how much - printed and
    saved so the partial-coverage claim in the module docstring is a
    checkable number, not an assertion."""
    by_repo = matched.groupby("full_name").agg(
        n_agent_prs_matched=("pr_number", "count"),
        mean_comments=("comments", "mean"),
        median_comments=("comments", "median"),
    ).reset_index()
    cov = pd.DataFrame({"full_name": sorted(reg_repos)})
    cov = cov.merge(by_repo, on="full_name", how="left")
    cov["has_review_data"] = cov["n_agent_prs_matched"].notna()
    cov["n_agent_prs_matched"] = cov["n_agent_prs_matched"].fillna(0).astype(int)
    return cov.sort_values(["has_review_data", "full_name"], ascending=[False, True])


def review_intensity_correlations(joined_with_review):
    """Spearman rank correlation between each outcome coefficient and
    each review-intensity measure, per metric and pooled - same shape as
    heterogeneity_explainers.pairwise_correlations, small n so every row
    reports its own n rather than assuming the pooled 79-repo scale."""
    rows = []
    covariates = ["mean_comments", "median_comments", "log1p_n_agent_prs_matched"]
    groups = list(joined_with_review.groupby("metric")) + [
        ("pooled (non-independent, see caveat)", joined_with_review)
    ]
    for metric, g in groups:
        for outcome in OUTCOME_COLS:
            for cov in covariates:
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


def median_split_test(joined_with_review):
    """Two-group Mann-Whitney (this project's own convention for small-n
    two-group comparisons - see heterogeneity_explainers.language_split_test)
    on repos above vs. at-or-below the median mean_comments-per-agent-PR,
    per metric. Directly tests Motivation.md's premise in its simplest
    form: do more-reviewed repos land on a different slope_change/
    level_change direction than less-reviewed ones. Median computed once
    on the repo-level review-intensity table (not per metric-row), so the
    same repo isn't split into different groups on different metrics."""
    repo_level = joined_with_review.drop_duplicates("repo_id")[
        ["repo_id", "mean_comments"]
    ]
    med = repo_level["mean_comments"].median()
    grp = joined_with_review.copy()
    grp["review_group"] = np.where(grp["mean_comments"] > med, "high", "low")

    rows = []
    for metric, g in grp.groupby("metric"):
        for outcome in OUTCOME_COLS:
            hi = g.loc[g["review_group"] == "high", outcome].dropna()
            lo = g.loc[g["review_group"] == "low", outcome].dropna()
            if len(hi) < 2 or len(lo) < 2:
                continue
            u, p = stats.mannwhitneyu(hi, lo, alternative="two-sided")
            diffs = hi.to_numpy()[:, None] - lo.to_numpy()[None, :]
            delta = (np.sum(diffs > 0) - np.sum(diffs < 0)) / diffs.size
            rows.append({
                "metric": metric, "outcome": outcome,
                "median_split_comments": med,
                "n_high": len(hi), "n_low": len(lo),
                "median_high": hi.median(), "median_low": lo.median(),
                "mannwhitney_p": p, "cliffs_delta": delta,
            })
    return pd.DataFrame(rows)


def run():
    joined = he.load_joined()  # RQ1 outcome table, repo_id-joined, all 237 rows
    reg_repos = set(joined["full_name"].unique())
    print(f"{len(reg_repos)} regression-eligible repos (from heterogeneity_explainers.load_joined())")

    matched = load_agent_pr_reviews()
    print(f"{len(matched)} PR-sample rows matched to an agent-authored PR "
          f"(via repo_id, pr_number join) across {matched['full_name'].nunique()} repos total")

    cov = coverage_report(matched, reg_repos)
    n_covered = int(cov["has_review_data"].sum())
    print(f"\n=== coverage: {n_covered} / {len(cov)} regression-eligible repos have "
          f"any matched agent-PR review data ===")
    print(cov.to_string(index=False))

    review = matched.groupby(["repo_id"]).agg(
        n_agent_prs_matched=("pr_number", "count"),
        mean_comments=("comments", "mean"),
        median_comments=("comments", "median"),
    ).reset_index()
    review["log1p_n_agent_prs_matched"] = np.log1p(review["n_agent_prs_matched"])

    joined_with_review = joined.merge(review, on="repo_id", how="inner")
    print(f"\n{joined_with_review['repo_id'].nunique()} repos x "
          f"{joined_with_review['metric'].nunique()} metrics = "
          f"{len(joined_with_review)} rows have both an RQ1 outcome coefficient "
          f"and a review-intensity measure")

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"

    cov_path = OUT_DIR / f"{prefix}-review-intensity-coverage.csv"
    joined_path = OUT_DIR / f"{prefix}-review-intensity-joined.csv"
    cov.to_csv(cov_path, index=False)
    joined_with_review.to_csv(joined_path, index=False)

    corr = review_intensity_correlations(joined_with_review)
    corr_path = OUT_DIR / f"{prefix}-review-intensity-correlations.csv"
    corr.to_csv(corr_path, index=False)
    print(f"\n=== Spearman correlations: outcome coef vs. review intensity (n>=4 only) -> {corr_path} ===")
    print(corr.to_string(index=False) if not corr.empty else "(no cell reached n>=4)")

    split = median_split_test(joined_with_review)
    split_path = OUT_DIR / f"{prefix}-review-intensity-median-split.csv"
    split.to_csv(split_path, index=False)
    print(f"\n=== high- vs low-review-intensity split (Mann-Whitney + Cliff's delta) -> {split_path} ===")
    print(split.to_string(index=False) if not split.empty else "(no cell reached n>=2 per group)")

    print(f"\ncoverage table -> {cov_path}")
    print(f"joined table -> {joined_path}")

    return cov, joined_with_review, corr, split


if __name__ == "__main__":
    run()
