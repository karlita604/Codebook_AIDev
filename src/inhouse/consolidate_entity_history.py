"""
Concatenates every fragmented results/analysis/*-entity-history-*.csv
(one file per repo since pool_entity_history.py's --workers>1 dispatch
writes a repo-scoped fragment per repo - the same reason
consolidate_inhouse_metrics.py/consolidate_inhouse_smells.py exist for
the metrics/smells stages, which hit this same fragmentation first) into
one canonical pooled table. This is the file
src/viz/generate_churn_figures.py's --entity-history flag expects - the
churn figures can't be built directly from per-repo fragments.

Didn't exist before 2026-08-19: entity-history was always run unscoped
(one shared output file) until --workers landed in Phase B, so no
consolidation step was ever needed for it - discovered as a real gap
when the first --workers>1 entity-history run needed pooling for
viz-churn and there was nothing to call.

Row key is (repo_id, full_name, relpath, lineage_id) - lineage_id is only
unique within one (repo, file), not globally, unlike the
(repo_id, track, target_date, commit_sha) key the metrics/smells
consolidation scripts use (entity-history's unit of work is a lineage
within a file's history, not a snapshot grid point). Deduplicates
keeping the last-seen row per key, same "a repo re-run after a bug fix
should win over an earlier one" convention as the other two consolidate
scripts.

Run: python consolidate_entity_history.py
Output: results/analysis/<date>-entity-history-pooled.csv
"""

from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT / "results" / "analysis"
KEY_COLS = ["repo_id", "full_name", "relpath", "lineage_id"]


def find_source_files():
    files = sorted(ANALYSIS_DIR.glob("*-entity-history-*.csv"))
    return [
        f for f in files
        if "dryrun" not in f.name
        and not f.name.endswith("-errors.csv")
        and not f.name.endswith("-repo-summary.csv")
        and "-pooled" not in f.name
    ]


def consolidate():
    files = find_source_files()
    if not files:
        raise FileNotFoundError(
            f"no *-entity-history-*.csv found in {ANALYSIS_DIR} - run "
            "pool_entity_history.py first"
        )

    frames = []
    per_file_counts = {}
    for f in files:
        df = pd.read_csv(f)
        if not set(KEY_COLS).issubset(df.columns):
            continue
        df = df[df["status"] == "ok"].copy()
        per_file_counts[f.name] = len(df)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=KEY_COLS, keep="last")
    after = len(combined)

    today = date.today()
    out_path = ANALYSIS_DIR / f"{today.month:02d}-{today.day:02d}-entity-history-pooled.csv"
    combined = combined.sort_values(["full_name", "relpath", "lineage_id"])
    combined.to_csv(out_path, index=False)

    print(f"consolidated {len(files)} source file(s), {before} ok rows total, "
          f"{before - after} duplicate key(s) dropped, {after} rows -> {out_path}")
    print("\nper-source-file ok-row counts:")
    for name, count in per_file_counts.items():
        print(f"  {count:5d}  {name}")
    print("\nper-repo row counts in the consolidated file:")
    print(combined.groupby("full_name").size().to_string())
    return out_path, combined


run = consolidate


if __name__ == "__main__":
    run()
