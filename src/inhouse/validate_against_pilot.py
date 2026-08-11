"""
The concrete version of Writing/InHouseTooling.md's "Validation plan" step
3: join pool_inhouse_metrics.py's output against the real pilot DPy ground
truth already on disk and report per-metric agreement - not a pass/fail
assertion, a quantified report. LOC is expected to track closely but with a
systematic offset (this engine sums whole-file physical LOC per module,
confirmed against real crewAI output to run high vs. DPy's narrower
per-module LOC row - see this script's own printed notes); CC/WMC-derived
figures are expected to diverge more (different counting conventions
between two independently-built McCabe implementations) - matching the
doc's own "direction/magnitude, not exact-count" framing for anything past
plain line-counting.

Ground truth: results/analysis/07-29-pooled-structural-metrics.csv, the
already-validated pool of the real pilot's DPy+Designite output
(ProjectStatus.md: "351 pooled rows... consolidated in" this file) - both
languages, DPy (Python) and Designite (C#/Dock). Which rows actually join
depends entirely on which repos the in-house glob covers; no language
filter is applied here on either side.

Usage:
    python validate_against_pilot.py [--inhouse-glob PATTERN]
"""

import argparse
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
GROUND_TRUTH_PATH = OUT_DIR / "07-29-pooled-structural-metrics.csv"

KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

# Metrics both schemas actually share - see py_metrics.py's module
# docstring for exactly how each is derived on the in-house side, and
# long_analysis.py's parse_tool_output() docstring for DPy's side.
SHARED_METRICS = [
    "total_loc", "n_classes", "n_methods",
    "class_loc_p50", "class_loc_p90",
    "method_loc_p50", "method_loc_p90",
    "cyclomatic_complexity_p50", "cyclomatic_complexity_p90",
]


def _load_inhouse(glob_pattern):
    paths = [
        p for p in OUT_DIR.glob(glob_pattern)
        if not p.name.endswith(("-errors.csv",))
        and "progress" not in p.name
    ]
    if not paths:
        raise FileNotFoundError(
            f"no in-house output matching {glob_pattern!r} in {OUT_DIR} - "
            "run pool_inhouse_metrics.py first"
        )
    # A repo run more than once (e.g. a --limit smoke test, then a full
    # run) can leave overlapping rows across files - keep the row from
    # whichever file was written LAST for a given key, not an arbitrary
    # duplicate, since a rerun is meant to supersede an earlier partial one.
    frames = []
    for p in paths:
        frame = pd.read_csv(p)
        frame["_mtime"] = p.stat().st_mtime
        frames.append(frame)
    df = pd.concat(frames, ignore_index=True)
    df = df.sort_values("_mtime").drop_duplicates(KEY_COLS, keep="last")
    return df.drop(columns="_mtime")


def _load_ground_truth():
    return pd.read_csv(GROUND_TRUTH_PATH)


def _normalize_target_date(df):
    """The manifest's raw target_date string ('...T00:00:00+00:00') and
    the pooled ground-truth CSV's re-serialized one ('... 00:00:00+00:00',
    space instead of 'T' - picked up when long_analysis.py's pipeline
    round-trips it through a datetime somewhere) are the same instant but
    don't string-equal, which silently zeroes out the join if left as raw
    strings. Parse to a real timestamp on both sides before merging."""
    df = df.copy()
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    return df


def build_report(merged):
    rows = []
    for metric in SHARED_METRICS:
        col_a, col_b = f"{metric}_inhouse", f"{metric}_dpy"
        pair = merged[[col_a, col_b]].dropna()
        if pair.empty:
            rows.append({
                "metric": metric, "n": 0, "mean_diff": None,
                "mean_pct_diff": None, "spearman_r": None,
            })
            continue
        diff = pair[col_a] - pair[col_b]
        # %-diff undefined at dpy==0 - excluded from that average, not
        # treated as 0% or an error.
        nonzero = pair[pair[col_b] != 0]
        pct_diff = (
            (nonzero[col_a] - nonzero[col_b]) / nonzero[col_b] * 100
            if not nonzero.empty else pd.Series(dtype=float)
        )
        corr = (
            spearmanr(pair[col_a], pair[col_b]).correlation
            if pair[col_a].nunique() > 1 and pair[col_b].nunique() > 1
            else None
        )
        rows.append({
            "metric": metric,
            "n": len(pair),
            "mean_diff": round(diff.mean(), 2),
            "mean_pct_diff": (
                round(pct_diff.mean(), 1) if not pct_diff.empty else None
            ),
            "spearman_r": round(corr, 3) if corr is not None else None,
        })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inhouse-glob", default="*-inhouse-metrics-*.csv",
        help="glob (within results/analysis/) for in-house output files",
    )
    args = parser.parse_args()

    inhouse = _normalize_target_date(_load_inhouse(args.inhouse_glob))
    ground_truth = _normalize_target_date(_load_ground_truth())
    print(f"in-house rows: {len(inhouse)} | pilot ground-truth rows: "
          f"{len(ground_truth)}")

    merged = inhouse.merge(
        ground_truth, on=KEY_COLS, suffixes=("_inhouse", "_dpy")
    )
    print(f"joined on {KEY_COLS}: {len(merged)} row(s)\n")

    out_path = OUT_DIR / "08-11-inhouse-validation-report.csv"
    all_reports = []

    # language_inhouse/language_dpy are the same value per row (both sides
    # carry a language column, merge suffixes both since it's not a join
    # key) - split by it so a Python-heavy and a C#-heavy metric offset
    # don't average into one misleading blended number, same reasoning
    # behind not comparing Dock's absolute smell share to the Python
    # repos' elsewhere in this project (Results.md).
    for lang in sorted(merged["language_inhouse"].unique()):
        sub = merged[merged["language_inhouse"] == lang]
        report = build_report(sub)
        report.insert(0, "language", lang)
        print(f"--- {lang} (n={len(sub)} joined rows) ---")
        print(report.drop(columns="language").to_string(index=False))
        print()
        all_reports.append(report)

    combined = pd.concat(all_reports, ignore_index=True)
    combined.to_csv(out_path, index=False)
    print(f"report written to {out_path}")


if __name__ == "__main__":
    main()
