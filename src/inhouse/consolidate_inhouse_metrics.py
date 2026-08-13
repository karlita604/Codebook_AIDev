"""
Concatenates every fragmented results/analysis/*-inhouse-metrics-*.csv
(one file per repo/run since pool_inhouse_metrics.py's --repo-scoped
invocations each get their own output file - the same reason
py_smells.py's pooled output needed no consolidation step, since it was
always run unscoped) into one canonical pooled table, keyed the same way
everything else in this project is: (repo_id, track, target_date,
commit_sha). This is the file figures_common.py's load_inhouse_metrics()
reads - there was previously no single "the pooled in-house OO-metrics
table" the way 07-29-pooled-structural-metrics.csv is for DPy/Designite.

Excludes the older "-dryrun-inhouse*" smoke-test files (bookkeeping only,
no real metric columns) and any "-errors.csv"/"-progress.json" siblings.
Deduplicates on the key columns, keeping the last-seen row per key (a
repo re-run after a bug fix should win over an earlier one) - if this ever
matters in practice it will be logged, not silently guessed at.

One deliberate, documented exception to "last-seen wins": Dock rows from
any run against the *default* (08-04) manifest are dropped outright, not
just deduplicated - wieslawsoltes/Dock's local repo_cache clone is stale
(frozen years in the past, a known issue logged in ProjectStatus.md and
InHouseTooling.md's own smell-detection batch-run log), so the default
manifest resolves ~94 of its 96 A1/A2 grid points to a single collapsed
commit instead of real commit diversity. Confirmed directly on the
2026-08-13 full-manifest run: 94 Dock rows, 1 unique commit_sha. The
correct Dock data (96 rows, 64 unique commits, already validated against
Designite - see ProjectUpdate.md's 2026-08-11 "leftover bad-manifest
rows cleaned up" entry) lives in the older 07-21-manifest-based files and
is kept; the new bad-manifest rows are excluded by full_name before the
dedup step even runs, so a "last-seen wins" tiebreak can never
accidentally prefer the bad ones.

Run: python consolidate_inhouse_metrics.py
Output: results/analysis/<date>-inhouse-metrics-pooled.csv
"""

import re
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT / "results" / "analysis"
KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

# pool_inhouse_metrics.py's own filename convention: <tag>-<scope>.csv,
# where scope is a bare row-count ("1577") for an unscoped (no --repo)
# run, or "<repo-slug>-<row-count>" for a --repo-scoped one. A bare-number
# scope means the run used the *default* manifest across every repo -
# which is the one Dock can't safely use (see the module docstring's Dock
# stale-clone note) - so any such file's Dock rows are dropped
# unconditionally rather than deduplicated, so "last-seen wins" can never
# accidentally prefer them over the older, --repo=Dock-scoped (and
# therefore correctly --manifest-overridden) file.
UNSCOPED_FILE_RE = re.compile(r"-inhouse-metrics-\d+\.csv$")


def find_source_files():
    files = sorted(ANALYSIS_DIR.glob("*-inhouse-metrics-*.csv"))
    return [
        f for f in files
        if "dryrun" not in f.name
        and not f.name.endswith("-errors.csv")
    ]


def consolidate():
    files = find_source_files()
    if not files:
        raise FileNotFoundError(
            f"no *-inhouse-metrics-*.csv found in {ANALYSIS_DIR} - run "
            "pool_inhouse_metrics.py first"
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
    out_path = ANALYSIS_DIR / f"{today.month:02d}-{today.day:02d}-inhouse-metrics-pooled.csv"
    combined = combined.sort_values(["full_name", "track", "target_date"])
    combined.to_csv(out_path, index=False)

    print(f"consolidated {len(files)} source file(s), {before} ok rows total "
          f"({dock_dropped} Dock row(s) dropped from unscoped/default-manifest "
          f"files - see module docstring), {before - after} duplicate key(s) "
          f"dropped, {after} rows -> {out_path}")
    print("\nper-source-file ok-row counts:")
    for name, count in per_file_counts.items():
        print(f"  {count:5d}  {name}")
    print("\nper-repo row counts in the consolidated file:")
    print(combined.groupby("full_name").size().to_string())
    return out_path, combined


if __name__ == "__main__":
    consolidate()
