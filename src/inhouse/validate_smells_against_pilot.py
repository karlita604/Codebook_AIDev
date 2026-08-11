"""
The concrete version of Writing/PySmellDetection.md's "Validation plan":
join pool_inhouse_smells.py's output against the real pilot DPy ground
truth already on disk and report agreement - but NOT the same
exact-count-correlation check validate_against_pilot.py runs for the
OO-metrics engine. That check assumes both sides compute the *same*
metric under a shared definition (true for LOC/CC/WMC); it is NOT true
here - py_smells.py's God Class/Data Class/Feature Envy/Brain Method are
an independently-sourced catalog (Lanza & Marinescu), not a reproduction
of DPy's closed one (Writing/InHouseTooling.md's "What's hard: smell
detection" section; Writing/PySmellDetection.md's "Output schema"
section). Two different, unrelated smell catalogs computing similar
row-for-row counts on the same code would be a coincidence, not a
validation result.

What IS a meaningful check, per Writing/PySmellDetection.md's "Validation
plan": does our smell-density signal move in the same *direction* as
DPy's own, pre- vs. post-intervention, on the same repos - and does it
correlate positively (not identically) with DPy's density row-for-row.
Both computed here, neither is a pass/fail gate - a quantified report,
same posture as validate_against_pilot.py.

Ground truth: results/analysis/07-29-pooled-structural-metrics.csv,
already carrying the `post` pre/post-intervention flag this script reuses
rather than re-deriving (same convention InHouseTooling.md's
"Correlation matrix" design decision already established).

Usage:
    python validate_smells_against_pilot.py [--inhouse-glob PATTERN]
"""

import argparse
from datetime import date
from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
GROUND_TRUTH_PATH = OUT_DIR / "07-29-pooled-structural-metrics.csv"

KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

DENSITY_METRICS = [
    "design_smell_density_per_kloc",
    "implementation_smell_density_per_kloc",
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
            "run pool_inhouse_smells.py first"
        )
    # Same "last-file-wins" resumability convention as
    # validate_against_pilot.py's _load_inhouse - a repo run more than
    # once (e.g. the azure-sdk-for-python exclude/rerun, 2026-08-11) can
    # leave overlapping rows across files.
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


def _normalize_target_date(df):
    df = df.copy()
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    return df


def correlation_report(merged):
    """Row-for-row Spearman correlation between our density figures and
    DPy's - positive correlation is a meaningful signal-level agreement
    even between two independently-sourced smell catalogs; it is not the
    same claim as "the counts match" (they're not expected to)."""
    rows = []
    for metric in DENSITY_METRICS:
        col_a, col_b = f"{metric}_inhouse", f"{metric}_dpy"
        pair = merged[[col_a, col_b]].dropna()
        corr = (
            spearmanr(pair[col_a], pair[col_b]).correlation
            if len(pair) > 1
            and pair[col_a].nunique() > 1 and pair[col_b].nunique() > 1
            else None
        )
        rows.append({
            "metric": metric,
            "n": len(pair),
            "spearman_r_vs_dpy": round(corr, 3) if corr is not None else None,
        })
    return pd.DataFrame(rows)


def direction_report(merged):
    """Pre- vs. post-intervention mean density, per repo and pooled, for
    BOTH our tool and DPy's - the actual check Writing/PySmellDetection.md's
    "Validation plan" calls for: does our signal move the same direction
    DPy's already-published result did (e.g. Dock's implementation-smell
    density rising ~90% post-intervention, DockDesigniteReport.md - a C#/
    Designite figure, not directly comparable, but the same *kind* of
    check applied here to Python/DPy instead)."""
    rows = []
    groups = list(merged.groupby("full_name_inhouse")) + [
        ("ALL (pooled)", merged)
    ]
    for repo, grp in groups:
        if grp["post"].nunique() < 2:
            # No pre AND post rows for this repo in the joined sample -
            # nothing to compare a direction on.
            continue
        for metric in DENSITY_METRICS:
            for suffix, label in (("_inhouse", "inhouse"), ("_dpy", "dpy")):
                col = f"{metric}{suffix}"
                pre_mean = grp.loc[grp["post"] == 0, col].mean()
                post_mean = grp.loc[grp["post"] == 1, col].mean()
                rows.append({
                    "repo": repo,
                    "metric": metric,
                    "source": label,
                    "n_pre": int((grp["post"] == 0).sum()),
                    "n_post": int((grp["post"] == 1).sum()),
                    "pre_mean": round(pre_mean, 4) if pd.notna(pre_mean) else None,
                    "post_mean": round(post_mean, 4) if pd.notna(post_mean) else None,
                    "direction": (
                        "up" if pd.notna(post_mean) and pd.notna(pre_mean)
                        and post_mean > pre_mean
                        else "down" if pd.notna(post_mean) and pd.notna(pre_mean)
                        and post_mean < pre_mean
                        else "flat/na"
                    ),
                })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inhouse-glob", default="*-inhouse-smells-python-*.csv",
        help="glob (within results/analysis/) for in-house output files",
    )
    args = parser.parse_args()

    inhouse = _load_inhouse(args.inhouse_glob)
    ground_truth = _load_ground_truth()
    print(
        f"in-house rows: {len(inhouse)} | pilot Python ground-truth rows: "
        f"{len(ground_truth)}"
    )

    inhouse = _normalize_target_date(inhouse)
    ground_truth = _normalize_target_date(ground_truth)
    merged = inhouse.merge(
        ground_truth, on=KEY_COLS, suffixes=("_inhouse", "_dpy")
    )
    print(f"joined on {KEY_COLS}: {len(merged)} row(s)\n")

    corr = correlation_report(merged)
    print("=== Correlation vs. DPy's own smell density (informative, not")
    print("    a match requirement - independently-sourced catalogs) ===")
    print(corr.to_string(index=False))

    direction = direction_report(merged)
    print("\n=== Pre/post-intervention direction, ours vs. DPy's ===")
    print(direction.to_string(index=False))

    today = date.today()
    corr_path = OUT_DIR / f"{today.month:02d}-{today.day:02d}-inhouse-smell-validation-correlation.csv"
    direction_path = OUT_DIR / f"{today.month:02d}-{today.day:02d}-inhouse-smell-validation-direction.csv"
    corr.to_csv(corr_path, index=False)
    direction.to_csv(direction_path, index=False)
    print(f"\nreports written to {corr_path} and {direction_path}")


if __name__ == "__main__":
    main()
