"""
Track A structural-health figures (Figs 1-6, Tables 1-2) - see the
session's plan doc for the full scope table. Two real data-scope tiers
throughout, never blended without saying so:
- pilot (4 repos, DPy/Designite) - the original, "clean" comparison point
- in-house (11 Python repos, py_smells.py) - a real, substantial scope
  upgrade for smell density specifically, but a narrower, differently-
  validated smell definition (see figures_common.py's docstring)

OO-metric figures (5, and Fig 6's second panel) stay pilot-scoped in this
pass - Tool-Py hasn't been run against the other Python Phase 2 repos yet,
a real separate prerequisite this script doesn't attempt to work around.

Run: python generate_track_a_figures.py
Output: Writing/figures/track_a_structural_health/
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.insert(0, str(Path(__file__).resolve().parent))
import figures_common as fc  # noqa: E402

SUBDIR = "track_a_structural_health"
PILOT_REPOS = ["crewAIInc/crewAI", "airbytehq/airbyte", "mlflow/mlflow", "wieslawsoltes/Dock"]
INTERVENTION_DATES = {
    "crewAIInc/crewAI": pd.Timestamp("2024-12-27", tz="UTC"),
    "airbytehq/airbyte": pd.Timestamp("2025-01-21", tz="UTC"),
    "mlflow/mlflow": pd.Timestamp("2025-05-21", tz="UTC"),
    "wieslawsoltes/Dock": pd.Timestamp("2025-06-25", tz="UTC"),
}


def make_fig1_pilot_small_multiples(pooled):
    """Fig 1 - A1, full 2022-2026 grid, one panel per pilot repo (4, not
    the original plan's 5 - dotnet/aspire dropped from the pilot)."""
    a1 = pooled[pooled["track"] == "A1"]
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5), sharex=False)
    for ax, repo in zip(axes.flat, PILOT_REPOS):
        d = a1[a1["full_name"] == repo].sort_values("target_date")
        ax.plot(d["target_date"], d["design_smell_density_per_kloc"], color=fc.BLUE,
                linewidth=1.8, marker="o", markersize=3, label="Design")
        ax.plot(d["target_date"], d["implementation_smell_density_per_kloc"], color=fc.ORANGE,
                linewidth=1.8, marker="o", markersize=3, label="Implementation")
        interv = INTERVENTION_DATES[repo]
        ax.axvline(interv, color=fc.MUTED, linestyle="--", linewidth=1.1)
        ax.set_title(repo, fontsize=10)
        ax.set_ylabel("Smells / KLOC", fontsize=8.5)
        ax.grid(axis="y", linewidth=0.5)
        fc.format_year_axis(ax)
        ax.tick_params(labelsize=8)
    axes.flat[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Fig 1 — Smell density over time, Track A1 (4-repo pilot, DPy/Designite)",
                 fontsize=12, y=0.99)
    return fc.save_fig(fig, SUBDIR, "fig1_pilot_smell_density_a1", top=0.93)


def make_fig2_pilot_event_window(pooled):
    """Fig 2 - A2, event-time (days relative to intervention), same 4 panels."""
    a2 = pooled[pooled["track"] == "A2"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(11, 7.5))
    for ax, repo in zip(axes.flat, PILOT_REPOS):
        d = a2[a2["full_name"] == repo].sort_values("target_date").copy()
        interv = INTERVENTION_DATES[repo]
        d["days_rel"] = (d["target_date"] - interv).dt.days
        ax.plot(d["days_rel"], d["design_smell_density_per_kloc"], color=fc.BLUE,
                linewidth=1.8, marker="o", markersize=3, label="Design")
        ax.plot(d["days_rel"], d["implementation_smell_density_per_kloc"], color=fc.ORANGE,
                linewidth=1.8, marker="o", markersize=3, label="Implementation")
        ax.axvline(0, color=fc.MUTED, linestyle="--", linewidth=1.1)
        ax.set_title(repo, fontsize=10)
        ax.set_xlabel("Days relative to intervention", fontsize=8.5)
        ax.set_ylabel("Smells / KLOC", fontsize=8.5)
        ax.grid(axis="y", linewidth=0.5)
        ax.tick_params(labelsize=8)
    axes.flat[0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.suptitle("Fig 2 — Smell density around the intervention, Track A2 (4-repo pilot)",
                 fontsize=12, y=0.99)
    return fc.save_fig(fig, SUBDIR, "fig2_pilot_smell_density_a2", top=0.93)


def make_fig1b_inhouse_small_multiples(smells):
    """The new, ~11-Python-repo tier - explicitly a separate figure, not a
    silent extension of Fig 1, per the plan's two-tier scoping. Captioned
    directly on the figure, not just in a caption file, so it can't be
    mistaken for the same metric as Fig 1 at a glance."""
    repos = sorted(smells["full_name"].unique())
    rs = fc.load_repo_summary().set_index("full_name")["intervention_date"]

    n = len(repos)
    ncols = 3
    nrows = -(-n // ncols)
    fig, axes = plt.subplots(nrows, ncols, figsize=(13, 3.3 * nrows))
    design_line = impl_line = None
    for ax, repo in zip(axes.flat, repos):
        d = smells[smells["full_name"] == repo].sort_values("target_date")
        (design_line,) = ax.plot(d["target_date"], d["design_smell_density_per_kloc"], color=fc.VIOLET,
                                  linewidth=1.5, marker="o", markersize=2.5, label="Design (God Class + Data Class)")
        (impl_line,) = ax.plot(d["target_date"], d["implementation_smell_density_per_kloc"], color=fc.RED,
                                linewidth=1.5, marker="o", markersize=2.5,
                                label="Implementation (Feature Envy + Brain Method)")
        if repo in rs.index:
            ax.axvline(rs[repo], color=fc.MUTED, linestyle="--", linewidth=1.0)
        ax.set_title(repo, fontsize=8.5)
        # Coarse quarterly ticks, rotated - 11 narrow panels with a ~4-year
        # date range each collide badly under matplotlib's default auto
        # date ticking (confirmed directly: adjacent labels ran together
        # illegibly, e.g. "2023-092024-01").
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=6))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.tick_params(labelsize=7, axis="x", rotation=40)
        ax.tick_params(labelsize=7, axis="y")
        ax.grid(axis="y", linewidth=0.4)
    for ax in axes.flat[n:]:
        ax.axis("off")
    # Title above the legend, both inside the y<=1.0 canvas - anything
    # placed above y=1.0 is off the actual saved PNG entirely (confirmed
    # directly: an earlier y=1.05 suptitle didn't just clip, it vanished
    # completely), not just visually crowded. Kept to 2 short lines - a
    # longer 2nd line was confirmed to overflow the figure width and get
    # clipped left/right (matplotlib doesn't auto-wrap suptitle text).
    # `top=` below reserves the matching room so nothing collides row 1.
    fig.suptitle(
        "Fig 1b — Smell density, in-house detector (11 Python Phase 2 repos)\n"
        "Different smell definition than Fig 1 (Lanza & Marinescu, not DPy/Designite) — see Writing/PySmellDetection.md",
        fontsize=9.5, y=0.99,
    )
    fig.legend(
        handles=[design_line, impl_line], frameon=False, fontsize=9,
        loc="upper center", bbox_to_anchor=(0.5, 0.925), ncol=2,
    )
    return fc.save_fig(fig, SUBDIR, "fig1b_inhouse_smell_density_11repo", top=0.90)


def make_fig3_forest_plot(regression):
    """Fig 3 - level-change and slope-change coefficients with real CIs,
    one row per (repo x metric), colored by language. Pilot-scoped -
    07-29-segmented-regression-A1.csv only has pilot rows regardless."""
    reg = regression.copy()
    reg["language"] = reg["full_name"].map(lambda r: "C#" if r == "wieslawsoltes/Dock" else "Python")
    reg["label"] = reg["full_name"].str.split("/").str[-1] + " — " + reg["metric"].str.replace("_", " ")
    reg = reg.sort_values(["metric", "full_name"])

    fig, axes = plt.subplots(1, 2, figsize=(13, max(4, 0.4 * len(reg))), sharey=True)
    for ax, coef_col, title in [
        (axes[0], "level_change", "Level change at intervention"),
        (axes[1], "slope_change", "Slope change (post - pre)"),
    ]:
        y = np.arange(len(reg))
        colors = [fc.LANGUAGE_COLOR[lang] for lang in reg["language"]]
        coef = reg[f"{coef_col}_coef"]
        lo = reg[f"{coef_col}_ci_lo"]
        hi = reg[f"{coef_col}_ci_hi"]
        ax.hlines(y, lo, hi, color=colors, linewidth=2)
        ax.scatter(coef, y, color=colors, s=28, zorder=3)
        ax.axvline(0, color=fc.MUTED, linewidth=1, linestyle=":")
        ax.set_title(title, fontsize=11)
        ax.grid(axis="x", linewidth=0.5)
        ax.tick_params(labelsize=8)
    axes[0].set_yticks(np.arange(len(reg)))
    axes[0].set_yticklabels(reg["label"], fontsize=8)
    axes[0].invert_yaxis()
    handles = [
        plt.Line2D([0], [0], color=fc.BLUE, lw=3, label="Python"),
        plt.Line2D([0], [0], color=fc.ORANGE, lw=3, label="C#"),
    ]
    fig.legend(handles=handles, frameon=False, fontsize=9, loc="upper right")
    fig.suptitle("Fig 3 — Segmented regression coefficients, 95% CI (RQ1, 4-repo pilot)", fontsize=12)
    return fc.save_fig(fig, SUBDIR, "fig3_forest_plot")


def make_fig4_composition(pooled, smells):
    """Fig 4 - stacked area, design vs. implementation smell share over
    time. Architecture layer omitted (chunk-scoping caveat, already
    documented in Results.md's own "Caveat" section) - not silently
    dropped, stated on the figure. Two-tier: pilot panel + in-house panel,
    same split as Fig 1/1b."""
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.6))

    # Pilot panel: pooled across the 4 repos, A1 track, by target_date.
    a1 = pooled[pooled["track"] == "A1"].groupby("target_date")[
        ["design_smell_count", "implementation_smell_count"]
    ].sum().reset_index().sort_values("target_date")
    total = a1["design_smell_count"] + a1["implementation_smell_count"]
    axes[0].stackplot(
        a1["target_date"],
        a1["design_smell_count"] / total.replace(0, np.nan),
        a1["implementation_smell_count"] / total.replace(0, np.nan),
        colors=[fc.BLUE, fc.ORANGE], labels=["Design", "Implementation"], alpha=0.85,
    )
    axes[0].set_title("Pilot (4 repos, DPy/Designite, pooled A1)", fontsize=10)
    axes[0].set_ylabel("Share of design+implementation smells")
    fc.format_year_axis(axes[0])
    axes[0].legend(frameon=False, fontsize=8, loc="lower left")

    # In-house panel: pooled across the 11 Python repos, bucketed by month
    # (not raw target_date) - confirmed directly that grouping by exact
    # target_date produced an illegible sawtooth, since each repo's own
    # snapshot dates aren't aligned to the same day, so different repos'
    # points interleave along the x-axis instead of landing on top of each
    # other. Monthly bucketing is a real fix (smooths interleaving noise),
    # not just a cosmetic one.
    smells_m = smells.copy()
    smells_m["month"] = smells_m["target_date"].dt.to_period("M").dt.to_timestamp()
    s = smells_m.groupby("month")[["n_god_class", "n_data_class", "n_feature_envy", "n_brain_method"]].sum().reset_index()
    s = s.rename(columns={"month": "target_date"})
    s["design"] = s["n_god_class"] + s["n_data_class"]
    s["impl"] = s["n_feature_envy"] + s["n_brain_method"]
    s = s.sort_values("target_date")
    total2 = (s["design"] + s["impl"]).replace(0, np.nan)
    axes[1].stackplot(
        s["target_date"], s["design"] / total2, s["impl"] / total2,
        colors=[fc.VIOLET, fc.RED], labels=["Design (God+Data Class)", "Implementation (Feature Envy+Brain Method)"],
        alpha=0.85,
    )
    axes[1].set_title("In-house (11 Python repos, py_smells.py, pooled)", fontsize=10)
    fc.format_year_axis(axes[1])
    axes[1].legend(frameon=False, fontsize=8, loc="lower left")

    fig.suptitle(
        "Fig 4 — Design vs. implementation smell composition over time\n"
        "(architecture smells omitted — chunk-scoping caveat, see Results.md)",
        fontsize=11, y=0.99,
    )
    return fc.save_fig(fig, SUBDIR, "fig4_smell_composition", top=0.88)


def make_fig6_cross_language(pooled, smells):
    """Fig 6 - cross-language comparison. Smell panel: 11 Python (in-house)
    vs. 1 C# (Dock, pilot) - still lopsided, no C# smell detector exists.
    OO-metric panel: pilot-scoped (3 Python + 1 C#) until Tool-Py runs
    wider - a real, separate, not-yet-done prerequisite."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    # Panel A: smell density, language boxplot.
    py_vals = smells["design_smell_density_per_kloc"].dropna()
    dock_vals = pooled[(pooled["full_name"] == "wieslawsoltes/Dock")]["design_smell_density_per_kloc"].dropna()
    bp = axes[0].boxplot([py_vals, dock_vals], tick_labels=[
        f"Python (in-house,\nn={smells['full_name'].nunique()} repos)",
        "C# (Dock only,\nDesignite pilot)",
    ], patch_artist=True, widths=0.5)
    for patch, color in zip(bp["boxes"], [fc.BLUE, fc.ORANGE]):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    axes[0].set_title("Design smell density — still lopsided\n(no C# smell detector exists)", fontsize=9.5)
    axes[0].set_ylabel("Design smells / KLOC")
    axes[0].tick_params(labelsize=8)

    # Panel B: OO metric (CC p90), pilot-scoped, all 4 repos.
    cc = pooled.groupby("language")["cyclomatic_complexity_p90"].apply(list)
    labels = list(cc.index)
    bp2 = axes[1].boxplot(cc.values, tick_labels=[f"{l}\n(pilot only)" for l in labels],
                           patch_artist=True, widths=0.5)
    for patch, color in zip(bp2["boxes"], [fc.BLUE, fc.ORANGE][:len(labels)]):
        patch.set_facecolor(color)
        patch.set_alpha(0.55)
    axes[1].set_title("Cyclomatic complexity p90 — pilot only\n(Tool-Py not yet run wider)", fontsize=9.5)
    axes[1].set_ylabel("CC p90")
    axes[1].tick_params(labelsize=8)

    fig.suptitle("Fig 6 — Cross-language comparison (two different scope ceilings, stated per panel)",
                 fontsize=11, y=0.99)
    return fc.save_fig(fig, SUBDIR, "fig6_cross_language", top=0.85)


def make_table1_coverage(manifest, smells):
    """Table 1 - coverage matrix, all 21 repos: how many A1/A2 grid points
    resolved a commit, how many have in-house smell data, whether pilot
    DPy/Designite data exists. The table that tells a reader where smell
    data stops (11 Python + 1 C#) vs. where OO-metric-only data starts."""
    rows = []
    for full_name, g in manifest.groupby("full_name"):
        language = g["language"].iloc[0]
        n_grid = len(g)
        n_resolved = g["commit_sha"].notna().sum()
        n_stale = g["is_stale"].sum() if "is_stale" in g else None
        has_pilot_dpy = full_name in PILOT_REPOS
        n_inhouse_smell_rows = (smells["full_name"] == full_name).sum()
        rows.append({
            "full_name": full_name, "language": language,
            "n_grid_points": n_grid, "n_commit_resolved": int(n_resolved),
            "n_stale": int(n_stale) if n_stale is not None else None,
            "has_pilot_dpy_designite_smells": has_pilot_dpy,
            "n_inhouse_smell_rows": int(n_inhouse_smell_rows),
        })
    df = pd.DataFrame(rows).sort_values("full_name")
    out_dir = fc.FIG_DIR / SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "table1_coverage.csv"
    df.to_csv(path, index=False)
    return path, df


def make_table2_descriptive_stats(pooled, smells):
    """Table 2 - pre vs. post descriptive stats, both tiers, same split
    as Fig 1/1b."""
    rows = []
    for repo in PILOT_REPOS:
        d = pooled[(pooled["full_name"] == repo) & (pooled["track"] == "A1")]
        for metric in ["design_smell_density_per_kloc", "implementation_smell_density_per_kloc",
                        "cyclomatic_complexity_p90"]:
            pre = d[d["post"] == False][metric].dropna()
            post = d[d["post"] == True][metric].dropna()
            rows.append({
                "source": "dpy_designite", "full_name": repo, "metric": metric,
                "n_pre": len(pre), "n_post": len(post),
                "mean_pre": pre.mean(), "mean_post": post.mean(),
                "median_pre": pre.median(), "median_post": post.median(),
            })
    rs = fc.load_repo_summary().set_index("full_name")["intervention_date"]
    for repo in sorted(smells["full_name"].unique()):
        if repo not in rs.index:
            continue
        d = smells[smells["full_name"] == repo]
        is_post = d["target_date"] >= rs[repo]
        for metric in ["design_smell_density_per_kloc", "implementation_smell_density_per_kloc"]:
            pre = d[~is_post][metric].dropna()
            post = d[is_post][metric].dropna()
            rows.append({
                "source": "inhouse", "full_name": repo, "metric": metric,
                "n_pre": len(pre), "n_post": len(post),
                "mean_pre": pre.mean(), "mean_post": post.mean(),
                "median_pre": pre.median(), "median_post": post.median(),
            })
    df = pd.DataFrame(rows)
    out_dir = fc.FIG_DIR / SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "table2_descriptive_stats.csv"
    df.to_csv(path, index=False)
    return path, df


def main():
    fc.setup_style()
    pooled = fc.load_pooled_metrics()
    regression = fc.load_regression()
    smells = fc.load_inhouse_smells()
    manifest = fc.load_manifest()

    print("Fig 1:", make_fig1_pilot_small_multiples(pooled))
    print("Fig 1b:", make_fig1b_inhouse_small_multiples(smells))
    print("Fig 2:", make_fig2_pilot_event_window(pooled))
    print("Fig 3:", make_fig3_forest_plot(regression))
    print("Fig 4:", make_fig4_composition(pooled, smells))
    print("Fig 6:", make_fig6_cross_language(pooled, smells))
    t1_path, t1 = make_table1_coverage(manifest, smells)
    print("Table 1:", t1_path, f"({len(t1)} repos)")
    t2_path, t2 = make_table2_descriptive_stats(pooled, smells)
    print("Table 2:", t2_path, f"({len(t2)} rows)")


if __name__ == "__main__":
    main()
