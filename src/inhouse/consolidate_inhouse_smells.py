"""
Concatenates every fragmented results/analysis/*-inhouse-smells-*.csv
(one file per --repo-scoped pool_inhouse_smells.py invocation - the
generalized-to-both-languages C# run was launched --repo-scoped
separately from the original Python-only run, same fragmentation
consolidate_inhouse_metrics.py already exists to fix for OO metrics) into
one canonical pooled table, keyed the same way everything else is:
(repo_id, track, target_date, commit_sha). This is the file
figures_common.py's load_inhouse_smells() reads.

Includes the older "-inhouse-smells-python-*.csv" files (pre-C# tag) via
the same glob - they're real Python rows, still valid, just produced
before the tag dropped "-python" (see pool_inhouse_smells.py's own
comment on why the tag rename doesn't orphan them). Excludes
"-dryrun-inhouse-smells-*.csv" (bookkeeping only) and "-errors.csv"
siblings.

Same Dock exclusion as consolidate_inhouse_metrics.py, same reason: any
unscoped (no --repo, bare-number-suffixed) run resolves Dock's stale
repo_cache clone to a single collapsed commit across ~94 of its 96 grid
points. Confirmed again on the 2026-08-13 gap-fill run
(08-13-inhouse-smells-1577.csv: 94 Dock rows, 1 unique commit_sha) - the
correct Dock smell data (96 rows, from the --manifest-overridden
08-13-inhouse-smells-Dock-96.csv run) is kept instead. Same reasoning as
consolidate_inhouse_metrics.py for why this isn't in
results/repos/excluded_repos.csv (src/common/exclusions.py): a row-level
fix for already-stale data from a fixed bug, not a repo-selection
decision.

Run: python consolidate_inhouse_smells.py
Output: results/analysis/<date>-inhouse-smells-pooled.csv
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT / "results" / "analysis"
KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

# Same convention/reasoning as consolidate_inhouse_metrics.py's own
# UNSCOPED_FILE_RE: a bare-number scope suffix means no --repo filter was
# used, i.e. the default (stale-clone-affected, for Dock) manifest.
UNSCOPED_FILE_RE = re.compile(r"-inhouse-smells-\d+\.csv$")


def find_source_files():
    files = sorted(ANALYSIS_DIR.glob("*-inhouse-smells-*.csv"))
    return [
        f for f in files
        if "dryrun" not in f.name
        and not f.name.endswith("-errors.csv")
        and "-pooled" not in f.name
    ]


def consolidate():
    files = find_source_files()
    if not files:
        raise FileNotFoundError(
            f"no *-inhouse-smells-*.csv found in {ANALYSIS_DIR} - run "
            "pool_inhouse_smells.py first"
        )

    frames = []
    per_file_counts = {}
    dock_dropped = 0
    for f in files:
        df = pd.read_csv(f)
        if not set(KEY_COLS).issubset(df.columns):
            continue
        df = df[df["status"] == "ok"].copy()
        if UNSCOPED_FILE_RE.search(f.name):
            is_dock = df["full_name"] == "wieslawsoltes/Dock"
            dock_dropped += int(is_dock.sum())
            df = df[~is_dock]
        per_file_counts[f.name] = len(df)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=KEY_COLS, keep="last")
    after = len(combined)

    today = date.today()
    out_path = ANALYSIS_DIR / f"{today.month:02d}-{today.day:02d}-inhouse-smells-pooled.csv"
    combined = combined.sort_values(["full_name", "track", "target_date"])
    combined.to_csv(out_path, index=False)

    print(f"consolidated {len(files)} source file(s), {before} ok rows total "
          f"({dock_dropped} Dock row(s) dropped from unscoped/default-manifest "
          f"files - see module docstring), {before - after} duplicate key(s) "
          f"dropped, {after} rows -> {out_path}")
    print("\nper-source-file ok-row counts:")
    for name, count in per_file_counts.items():
        print(f"  {count:5d}  {name}")
    print("\nper-repo/language row counts in the consolidated file:")
    print(combined.groupby(["language", "full_name"]).size().to_string())
    return out_path, combined


# Stable, predictable entry point for src/pipeline/run_pipeline.py (this
# script has no argparse - see module docstring's "Run: python
# consolidate_inhouse_smells.py" - so the orchestrator calls run()
# directly rather than shelling out with flags it doesn't have).
run = consolidate


if __name__ == "__main__":
    run()
