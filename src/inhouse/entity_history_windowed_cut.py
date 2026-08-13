"""
Stage 6 (RQ3 execution plan): windowed pre/post cut over Stage 5's pooled
entity-history output - a filter/join over already-collected data, not a
new collection pass, per the execution plan's Stage 6 design decision.

Joins Stage 5's output (results/analysis/*-entity-history-*.csv) against
each repo's `intervention_date` (results/repos/*-repo-summary-*.csv, the
same column Track A/B's own pre/post split already uses - see
`Longitudinal.md` and `07-29-pooled-structural-metrics.csv`'s own
`post`/`intervention_date` convention) and classifies every lineage into
one of three buckets:

- **pre_only**: `last_date < intervention_date` - every touch this entity
  ever had (in the walked sample) happened before agents started
  contributing to this repo.
- **post_created**: `first_date >= intervention_date` - the entity didn't
  exist before the intervention date at all; its whole recorded life is
  post-adoption.
- **spans**: `first_date < intervention_date <= last_date` - existed
  before, touched again at or after. This is the group an agent-adoption
  effect on an EXISTING piece of code would show up in, if it shows up at
  all - `post_created` tells you about new code volume, not about whether
  agents change how already-existing code gets treated.

**Real, stated limitation**: this classifies each LINEAGE as a whole (using
its pooled first/last touch date), not each individual touch event -
Stage 5's pooled CSV doesn't carry per-touch dates, only first/last plus an
aggregate `modification_count`. A `spans` entity's modification_count
cannot be split into "N touches before, M after" without re-deriving from
the underlying `EntityLineage.touches` list, which this script deliberately
does NOT do - that would be a new collection pass, contradicting this
stage's own "filter, not a new pass" design decision. A precise per-touch
split is real future work if the coarser bucket comparison below isn't
enough - flagged here, not silently assumed away.
"""

import argparse
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
REPO_SUMMARY_DIR = ROOT / "results" / "repos"


def latest_repo_summary():
    files = sorted(REPO_SUMMARY_DIR.glob("*-repo-summary-*.csv"))
    if not files:
        raise FileNotFoundError(f"no repo-summary csv found in {REPO_SUMMARY_DIR}")
    return files[-1]


def classify(row):
    if row["last_date"] < row["intervention_date"]:
        return "pre_only"
    if row["first_date"] >= row["intervention_date"]:
        return "post_created"
    return "spans"


def apply_windowed_cut(entity_history_path, repo_summary_path=None):
    repo_summary_path = repo_summary_path or latest_repo_summary()
    eh = pd.read_csv(entity_history_path)
    rs = pd.read_csv(repo_summary_path)

    ok = eh[eh["status"] == "ok"].copy()
    ok["first_date"] = pd.to_datetime(ok["first_date"], utc=True)
    ok["last_date"] = pd.to_datetime(ok["last_date"], utc=True)

    intervention = rs[["repo_id", "intervention_date"]].dropna().copy()
    intervention["intervention_date"] = pd.to_datetime(
        intervention["intervention_date"], utc=True
    )

    merged = ok.merge(intervention, on="repo_id", how="left")
    n_no_intervention = merged["intervention_date"].isna().sum()
    merged = merged.dropna(subset=["intervention_date"])

    merged["bucket"] = merged.apply(classify, axis=1)
    return merged, n_no_intervention


def summarize(merged):
    per_repo = merged.groupby(["full_name", "language"]).agg(
        n_lineages=("lineage_id", "count"),
        n_pre_only=("bucket", lambda s: (s == "pre_only").sum()),
        n_post_created=("bucket", lambda s: (s == "post_created").sum()),
        n_spans=("bucket", lambda s: (s == "spans").sum()),
        mean_mod_pre_only=("modification_count", lambda s: None),  # filled below
    ).drop(columns=["mean_mod_pre_only"])

    for bucket in ("pre_only", "post_created", "spans"):
        sub = merged[merged["bucket"] == bucket]
        means = sub.groupby(["full_name", "language"])["modification_count"].mean()
        per_repo[f"mean_mod_{bucket}"] = means
        churn = sub.groupby(["full_name", "language"])["relative_churn"].mean()
        per_repo[f"mean_churn_{bucket}"] = churn

    return per_repo.round(3).reset_index()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-history", type=Path, required=True)
    parser.add_argument("--repo-summary", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    merged, n_no_intervention = apply_windowed_cut(args.entity_history, args.repo_summary)
    if n_no_intervention:
        print(f"note: {n_no_intervention} lineage(s) dropped - repo had no "
              f"intervention_date in the repo-summary csv", flush=True)

    counts = merged["bucket"].value_counts()
    total = len(merged)
    print(f"{total} lineages classified against intervention_date:")
    for bucket in ("pre_only", "spans", "post_created"):
        n = counts.get(bucket, 0)
        print(f"  {bucket:14s} {n:6d}  ({100*n/total:.1f}%)")

    per_repo = summarize(merged)
    print("\nPer-repo mean modification_count by bucket:")
    print(per_repo[[
        "full_name", "language", "n_lineages",
        "mean_mod_pre_only", "mean_mod_spans", "mean_mod_post_created",
    ]].to_string(index=False))

    out_path = args.out or (OUT_DIR / (args.entity_history.stem + "-windowed-cut.csv"))
    merged.to_csv(out_path, index=False)
    per_repo_path = out_path.with_name(out_path.stem + "-per-repo.csv")
    per_repo.to_csv(per_repo_path, index=False)
    print(f"\nwrote {out_path}\nwrote {per_repo_path}")


if __name__ == "__main__":
    main()
