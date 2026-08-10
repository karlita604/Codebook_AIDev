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
(ProjectStatus.md: "351 pooled rows... consolidated in" this file),
filtered to language == "Python" (DPy rows only - Designite/Dock is C#,
out of scope for Phase A, see Writing/InHouseTooling.md's design-decisions
section on why Phase A is Python-only in practice even though both
languages are in scope for the eventual tool).

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
    gt = pd.read_csv(GROUND_TRUTH_PATH)
    return gt[gt["language"] == "Python"]


def build_report(inhouse, ground_truth):
    merged = inhouse.merge(
        ground_truth, on=KEY_COLS, suffixes=("_inhouse", "_dpy")
    )
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
    return pd.DataFrame(rows), merged


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inhouse-glob", default="*-inhouse-metrics-python-*.csv",
        help="glob (within results/analysis/) for in-house output files",
    )
    args = parser.parse_args()

    inhouse = _load_inhouse(args.inhouse_glob)
    ground_truth = _load_ground_truth()
    print(
        f"in-house rows: {len(inhouse)} | pilot Python ground-truth rows: "
        f"{len(ground_truth)}"
    )

    report, merged = build_report(inhouse, ground_truth)
    print(f"joined on {KEY_COLS}: {len(merged)} row(s)\n")
    print(report.to_string(index=False))

    out_path = OUT_DIR / "08-10-inhouse-validation-report.csv"
    report.to_csv(out_path, index=False)
    print(f"\nreport written to {out_path}")


if __name__ == "__main__":
    main()
