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
    (more agent PRs = easier to sanity-check the intervention-detection logic)."""
    picks = []
    for lang in ["Python", "C#"]:
        subset = repo_summary[repo_summary["language"] == lang].sort_values(
            "agent_pr_count", ascending=False
        )
        take = max(1, round(n * len(subset) / len(repo_summary)))
        picks.append(subset.head(take))
    combined = pd.concat(picks).head(n)
    return combined


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-size", type=int, default=5)
    args = parser.parse_args()

    candidates = load_candidate_repos()
    aidev_prs = load_aidev_prs_for_repos(candidates["id"])
    pr_table = build_pr_table(candidates, aidev_prs)
    repo_summary = build_repo_summary(pr_table)
    pilot = suggest_pilot(repo_summary, n=args.pilot_size)

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
