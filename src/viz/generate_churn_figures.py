"""
Method-level churn before/after intervention (Figs 7-9, Table 3) - the
figures Part A's pre_touch_count/post_touch_count/pre_churn_rate/
post_churn_rate columns exist to feed. `kind == "callable"` (methods and
module-level functions) throughout, per the original request's wording.

Real, stated scope, not smoothed over: only `spans` entities (existed
before the intervention AND touched again at or after) can answer a
before/after churn-rate question at all - a `pre_only` or `post_created`
entity has nothing on the other side to compare. This is the same
selection-bias point the RQ3 dashboard's Finding 3 already named for the
coarser lineage-bucket view; it applies here too, restated in each
figure's own caption rather than left implicit.

Run: python generate_churn_figures.py --entity-history <path to the
Part-A-enhanced CSV>
Output: Writing/figures/method_churn/
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figures_common as fc  # noqa: E402

SUBDIR = "method_churn"


def load_spans_callables(entity_history_path):
    """Rows that can answer a before/after churn question at all:
    kind==callable, both pre_touch_count and post_touch_count > 0 (a real
    `spans` entity, not derived from the bucket label - computed directly
    from the real per-touch counts Part A added, more precise than Stage
    6's coarser first/last-date bucketing)."""
    df = pd.read_csv(entity_history_path)
    df = df[df["status"] == "ok"].copy()
    if "pre_touch_count" not in df.columns:
        raise ValueError(
            f"{entity_history_path} has no pre_touch_count column - this "
            "needs Part A's re-run output, not the original Stage 5 CSV "
            "(archived at results/analysis/archive_pre-churn-columns_2026-08-11/)"
        )
    callables = df[df["kind"] == "callable"].copy()
    spans = callables[
        (callables["pre_touch_count"] > 0) & (callables["post_touch_count"] > 0)
    ].copy()
    # Both rates need a nonzero window to be meaningful - a repo whose
    # intervention date is the same day as first/last touch would divide
    # by zero; Part A's pre_churn_rate/post_churn_rate are already None
    # for those (not fabricated), so this just drops them explicitly here
    # too rather than silently propagating NaN into a plot.
    spans = spans.dropna(subset=["pre_churn_rate", "post_churn_rate"])
    return spans


def make_fig7_paired_distribution(spans):
    """Fig 7 - pooled before/after churn-rate distribution (box + the
    individual points as a jittered strip, since box alone hides how
    heavy-tailed this is - the same "shape, not just a mean" concern
    Longitudinal.md's own §9 already raised for LOC/CC)."""
    pre = spans["pre_churn_rate"]
    post = spans["post_churn_rate"]

    fig, ax = plt.subplots(figsize=(9, 5.5))
    bp = ax.boxplot([pre, post], tick_labels=["Pre-intervention", "Post-intervention"],
                     patch_artist=True, widths=0.5, showfliers=False)
    for patch, color in zip(bp["boxes"], [fc.PERIOD_COLOR["pre"], fc.PERIOD_COLOR["post"]]):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    rng = np.random.default_rng(0)
    for i, series, color in [(1, pre, fc.PERIOD_COLOR["pre"]), (2, post, fc.PERIOD_COLOR["post"])]:
        jitter = rng.normal(0, 0.05, size=len(series))
        ax.scatter(np.full(len(series), i) + jitter, series, s=6, alpha=0.25, color=color, zorder=0)
    ax.set_ylabel("Touches / day")
    # Kept to a width that fits a 9in figure - confirmed directly that a
    # longer version overflowed a narrower figure's canvas and got clipped
    # on the right edge (same class of issue as Fig 1b's title, fixed the
    # same way: shorten the text rather than fight the layout further).
    ax.set_title(
        f"Fig 7 — Churn rate, before vs. after (n={len(spans)} spanning methods)\n"
        "Only entities that survived the intervention — see Results.md",
        fontsize=11,
    )
    ax.grid(axis="y", linewidth=0.5)
    return fc.save_fig(fig, SUBDIR, "fig7_paired_churn_rate", top=0.87)


def make_fig8_per_repo_bars(spans):
    """Fig 8 - one bar-pair per repo, mean pre-rate vs. post-rate, all 21
    repos - the cross-repo view Fig 7 pools away.

    symlog x-axis, not linear: confirmed directly that a linear scale made
    15+ of 18 repos' bars visually disappear next to browser-use's known
    BrowserSession-driven outlier (mean pre-rate ~7.7) - this is real,
    heavy-tailed rate data (same shape the whole project already treats
    with percentiles/log handling elsewhere, e.g. LOC/CC), not a case
    where hiding the outlier would make the chart more honest. `linthresh`
    keeps a linear region near zero so small-but-real rates stay visually
    distinguishable from true zero instead of all collapsing together."""
    agg = spans.groupby("full_name").agg(
        n=("pre_churn_rate", "size"),
        mean_pre=("pre_churn_rate", "mean"),
        mean_post=("post_churn_rate", "mean"),
    ).reset_index()
    agg = agg.sort_values("mean_post", ascending=False)

    fig, ax = plt.subplots(figsize=(11, 7.5))
    y = np.arange(len(agg))
    height = 0.38
    ax.barh(y + height / 2, agg["mean_pre"], height=height, color=fc.PERIOD_COLOR["pre"], label="Pre")
    ax.barh(y - height / 2, agg["mean_post"], height=height, color=fc.PERIOD_COLOR["post"], label="Post")
    ax.set_xscale("symlog", linthresh=0.01)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r} (n={n})" for r, n in zip(agg["full_name"], agg["n"])], fontsize=8.5)
    ax.set_xlabel("Mean touches / day among spanning methods (symlog scale)")
    ax.set_title("Fig 8 — Mean churn rate before vs. after, per repo (all 21 repos)", fontsize=11.5)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="x", linewidth=0.5)
    ax.invert_yaxis()
    return fc.save_fig(fig, SUBDIR, "fig8_per_repo_churn_rate", top=0.94)


def make_fig9_pooled_histogram(spans):
    """Fig 9 - distribution of (post_rate - pre_rate) per entity, pooled -
    did more surviving entities speed up or slow down. Log-scale-ish
    handling isn't attempted here (the raw difference can be negative) -
    a plain histogram, clipped to the 1st-99th percentile range so a
    handful of extreme outliers (e.g. BrowserSession-scale hotspots) don't
    compress the whole distribution into one bar."""
    diff = spans["post_churn_rate"] - spans["pre_churn_rate"]
    lo, hi = diff.quantile([0.01, 0.99])
    clipped = diff.clip(lo, hi)

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.hist(clipped, bins=40, color=fc.VIOLET, alpha=0.85)
    ax.axvline(0, color=fc.MUTED, linewidth=1.3, linestyle="--")
    ax.axvline(diff.median(), color=fc.RED, linewidth=1.3, linestyle="-",
               label=f"median = {diff.median():+.3f}")
    n_sped_up = (diff > 0).sum()
    n_slowed = (diff < 0).sum()
    ax.set_xlabel("Post-intervention rate − pre-intervention rate (touches/day)")
    ax.set_ylabel("Number of spanning methods")
    ax.set_title(
        f"Fig 9 — Churn-rate change, pooled (n={len(spans)})\n"
        f"{n_sped_up} sped up, {n_slowed} slowed down, {len(spans) - n_sped_up - n_slowed} unchanged "
        f"(clipped to 1st–99th pctile for display)",
        fontsize=10.5,
    )
    ax.legend(frameon=False, fontsize=9)
    ax.grid(axis="y", linewidth=0.5)
    return fc.save_fig(fig, SUBDIR, "fig9_churn_rate_change_histogram", top=0.86)


def make_table3_backing_stats(spans):
    rows = []
    for repo, g in spans.groupby("full_name"):
        diff = g["post_churn_rate"] - g["pre_churn_rate"]
        rows.append({
            "full_name": repo,
            "n_spanning_methods": len(g),
            "mean_pre_rate": g["pre_churn_rate"].mean(),
            "median_pre_rate": g["pre_churn_rate"].median(),
            "mean_post_rate": g["post_churn_rate"].mean(),
            "median_post_rate": g["post_churn_rate"].median(),
            "pct_sped_up": 100 * (diff > 0).mean(),
            "pct_slowed_down": 100 * (diff < 0).mean(),
        })
    df = pd.DataFrame(rows).sort_values("full_name")
    out_dir = fc.FIG_DIR / SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "table3_churn_rate_stats.csv"
    df.to_csv(path, index=False)
    return path, df


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entity-history", type=Path, required=True)
    args = parser.parse_args()

    fc.setup_style()
    spans = load_spans_callables(args.entity_history)
    print(f"{len(spans)} spanning callable(s) with a real pre/post churn rate "
          f"across {spans['full_name'].nunique()} repo(s)")

    print("Fig 7:", make_fig7_paired_distribution(spans))
    print("Fig 8:", make_fig8_per_repo_bars(spans))
    print("Fig 9:", make_fig9_pooled_histogram(spans))
    path, t3 = make_table3_backing_stats(spans)
    print("Table 3:", path, f"({len(t3)} repos)")


if __name__ == "__main__":
    main()
