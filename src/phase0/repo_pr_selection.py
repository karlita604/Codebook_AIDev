"""
Phase 1a: repo & PR picking for the longitudinal study.

Context (see Writing/Longitudinal.md): the AIDev dataset (`all_pull_request.parquet`)
contains ONLY agent-authored PRs, and only spans 2024-12-24 to 2025-07-30. It has no
pre-agent baseline PRs and nothing outside that ~7 month window. So for our 235
candidate repos (results/phase0/repos_07-21-500-pycsharp-1398_235.csv), we use AIDev
only to find each repo's *intervention point* (earliest agent-authored PR) and to
tag which PRs in that narrow window are agent PRs. Everything outside that window
(the pre-2022 -> Mar-2026 baseline) has to come from a separate GitHub API pull,
which is Phase 1b and is not done by this script.

Output (written to results/repos/):
- <date>-aidev-agent-prs-<n>.csv       : PR-level rows, all AIDev PRs for the 235
                                          candidate repos, with an is_intervention_pr
                                          flag marking each repo's earliest agent PR.
- <date>-repo-summary-<n>.csv          : one row per repo with agent PR counts,
                                          per-agent breakdown, and intervention date,
                                          to support picking the 5 (then 10) pilot repos.
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_REPOS_CSV = ROOT / "results" / "repos" / "repos_07-21-500-pycsharp-1398_235.csv"
OUT_DIR = ROOT / "results" / "repos"


def load_candidate_repos(path=CANDIDATE_REPOS_CSV):
    return pd.read_csv(path)


def load_aidev_prs_for_repos(repo_ids):
    df = pd.read_parquet("hf://datasets/hao-li/AIDev/all_pull_request.parquet")
    df["repo_id"] = pd.to_numeric(df["repo_id"], errors="coerce")
    return df[df["repo_id"].isin(repo_ids)].copy()


def build_pr_table(candidates, aidev_prs):
    prs = aidev_prs.merge(
        candidates.rename(columns={"id": "repo_id"}),
        on="repo_id",
        how="left",
        suffixes=("", "_repo"),
    )
    prs["created_at_dt"] = pd.to_datetime(prs["created_at"], utc=True)

    first_pr_idx = prs.groupby("repo_id")["created_at_dt"].idxmin()
    prs["is_intervention_pr"] = False
    prs.loc[first_pr_idx, "is_intervention_pr"] = True

    cols = [
        "id", "repo_id", "full_name", "language", "stars",
        "agent", "state", "created_at", "closed_at", "merged_at",
        "html_url", "is_intervention_pr",
    ]
    return prs[cols].sort_values(["repo_id", "created_at"]).reset_index(drop=True)


def build_repo_summary(pr_table):
    def _summarize(group):
        agent_counts = group["agent"].value_counts().to_dict()
        return pd.Series({
            "full_name": group["full_name"].iloc[0],
            "language": group["language"].iloc[0],
            "stars": group["stars"].iloc[0],
            "agent_pr_count": len(group),
            "distinct_agents": group["agent"].nunique(),
            "agent_breakdown": agent_counts,
            "intervention_date": group.loc[group["is_intervention_pr"], "created_at"].iloc[0],
            "last_agent_pr_date": group["created_at"].max(),
        })

    summary = pr_table.groupby("repo_id").apply(_summarize, include_groups=False)
    return summary.reset_index().sort_values("agent_pr_count", ascending=False)


def suggest_pilot(repo_summary, n=5):
    """Stratified pick: mix of languages, prefer repos with more agent-PR signal
    (more agent PRs = easier to sanity-check the intervention-detection logic).

    Growth property this function relies on for --target-total (see main()):
    the per-language sort order doesn't depend on n, so a larger n's pick is
    expected to be a superset of a smaller n's - verified empirically for
    every n in 1..len(repo_summary) against the real 235-row candidate pool
    (0 violations; see check_monotonic_growth() below), not proven in
    general. round()'s banker's-rounding could in principle produce a
    non-superset pick at some n for a different repo_summary shape (e.g.
    once the candidate pool is widened for a 1000-repo run, or if a third
    language is added to the ["Python", "C#"] loop below) - re-run
    check_monotonic_growth() against the actual repo_summary being used
    before relying on this property at a new scale, rather than assuming it
    still holds. Not changed here - this is a research-methodology call
    (the stratification algorithm itself), not a scaling-infrastructure one."""
    picks = []
    for lang in ["Python", "C#"]:
        subset = repo_summary[repo_summary["language"] == lang].sort_values(
            "agent_pr_count", ascending=False
        )
        take = max(1, round(n * len(subset) / len(repo_summary)))
        picks.append(subset.head(take))
    combined = pd.concat(picks).head(n)
    return combined


def check_monotonic_growth(repo_summary, verbose=True):
    """Empirical check of suggest_pilot()'s growth property (see its
    docstring): for every consecutive n, does the larger pick contain the
    smaller one? Returns the list of (n, missing_repos) violations, if any
    - empty means the property held for every n against this repo_summary.
    Cheap (linear in len(repo_summary)) - safe to re-run whenever the
    candidate pool changes size, e.g. before scaling to --target-total 1000."""
    picks = {
        n: set(suggest_pilot(repo_summary, n=n)["full_name"])
        for n in range(1, len(repo_summary) + 1)
    }
    violations = []
    for n in range(1, len(repo_summary)):
        missing = picks[n] - picks[n + 1]
        if missing:
            violations.append((n, missing))
            if verbose:
                print(
                    f"  [violation] n={n}->{n + 1}: {len(missing)} repo(s) "
                    f"dropped: {missing}", flush=True,
                )
    if verbose:
        print(
            f"check_monotonic_growth: {len(violations)} violation(s) across "
            f"{len(repo_summary) - 1} consecutive n pair(s)", flush=True,
        )
    return violations


def main():
    candidates = load_candidate_repos()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-total", "--pilot-size", dest="target_total", type=int,
        default=5,
        help=f"how many repos to select (--pilot-size is a deprecated "
             "alias, kept so old invocations don't silently break). Draws "
             f"from the {len(candidates)} candidate repos in the pool file "
             "(see load_candidate_repos()) - can't return more than that "
             "regardless of what's asked for; re-run this project's Phase 0 "
             "candidate search with wider parameters first if you need a "
             "bigger pool (e.g. before a --target-total 1000 run).",
    )
    parser.add_argument(
        "--verify-monotonic-growth", action="store_true",
        help="run check_monotonic_growth() against the current candidate "
             "pool and exit, instead of actually selecting repos",
    )
    args = parser.parse_args()

    if args.verify_monotonic_growth:
        aidev_prs = load_aidev_prs_for_repos(candidates["id"])
        pr_table = build_pr_table(candidates, aidev_prs)
        repo_summary = build_repo_summary(pr_table)
        check_monotonic_growth(repo_summary)
        return

    aidev_prs = load_aidev_prs_for_repos(candidates["id"])
    pr_table = build_pr_table(candidates, aidev_prs)
    repo_summary = build_repo_summary(pr_table)
    pilot = suggest_pilot(repo_summary, n=args.target_total)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()

    pr_path = OUT_DIR / f"{today.month:02d}-{today.day:02d}-aidev-agent-prs-{len(pr_table)}.csv"
    pr_table.to_csv(pr_path, index=False)

    summary_path = OUT_DIR / f"{today.month:02d}-{today.day:02d}-repo-summary-{len(repo_summary)}.csv"
    repo_summary.to_csv(summary_path, index=False)

    print(f"{len(pr_table)} AIDev PR rows across {len(repo_summary)} repos -> {pr_path}")
    print(f"repo summary -> {summary_path}")
    print(f"\nsuggested {len(pilot)}-repo pilot:")
    print(pilot[["repo_id", "full_name", "language", "agent_pr_count", "intervention_date"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
