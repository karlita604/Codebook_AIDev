"""
Track A structural-health figures (Figs 1-6, Tables 1-2) - see the
session's plan doc for the full scope table. Two real data-scope tiers
throughout, never blended without saying so:
- pilot (4 repos, DPy/Designite) - the original, "clean" comparison point
- in-house (now both languages - py_smells.py + cs_smells.py for smells,
  the full consolidated pool for OO metrics) - a real, substantial scope
  upgrade, but smells specifically stay a narrower, differently-validated
  definition than DPy/Designite's (see figures_common.py's docstring); OO
  metrics ARE a validated 1:1 replacement (r=0.997-0.999), so Fig 5's
  in-house LOC/CC data isn't caveated the same way Fig 1b/4/6's smell
  panels are.

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
    """The in-house-detector tier - explicitly a separate figure, not a
    silent extension of Fig 1, per the plan's two-tier scoping. Captioned
    directly on the figure, not just in a caption file, so it can't be
    mistaken for the same metric as Fig 1 at a glance. Originally scoped
    to 11 Python repos; now genuinely both-language (cs_smells.py landed
    2026-08-13) since `smells` comes from figures_common.py's generalized
    load_inhouse_smells() - the title below reflects the real repo count/
    language mix dynamically rather than a stale hardcoded "11 Python"."""
    repos = sorted(smells["full_name"].unique())
    n_python = smells.loc[smells["language"] == "Python", "full_name"].nunique()
    n_csharp = smells.loc[smells["language"] == "C#", "full_name"].nunique()
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
        f"Fig 1b — Smell density, in-house detector ({n_python} Python + {n_csharp} C# repos)\n"
        "Different smell definition than Fig 1 (Lanza & Marinescu, not DPy/Designite) — see Writing/PySmellDetection.md",
        fontsize=9.5, y=0.99,
    )
    fig.legend(
        handles=[design_line, impl_line], frameon=False, fontsize=9,
        loc="upper center", bbox_to_anchor=(0.5, 0.925), ncol=2,
    )
    return fc.save_fig(fig, SUBDIR, "fig1b_inhouse_smell_density_11repo", top=0.90)


def _forest_plot(reg, language_map, suptitle, out_name):
    """Shared forest-plot renderer - level-change and slope-change
    coefficients with real 95% CIs, one row per (repo x metric), colored
    by language. Used for both the original 4-repo pilot plot (unchanged
    output) and the new full-corpus one (Stage 4's reconstructed
    segmented_regression.py, all repos with enough in-house pre/post data)."""
    reg = reg.copy()
    reg["language"] = reg["full_name"].map(language_map)
    reg["label"] = reg["full_name"].str.split("/").str[-1] + " — " + reg["metric"].str.replace("_", " ")
    reg = reg.sort_values(["metric", "full_name"]).reset_index(drop=True)

    fig, axes = plt.subplots(1, 2, figsize=(13, max(4, 0.32 * len(reg))), sharey=True)
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
    fig.suptitle(suptitle, fontsize=12)
    return fc.save_fig(fig, SUBDIR, out_name)


def make_fig3_forest_plot(regression):
    """Fig 3 - the original 4-repo pilot forest plot, unchanged output -
    07-29-segmented-regression-A1.csv only has pilot rows regardless, and
    this stays the "clean," DPy/Designite-validated reference panel."""
    language_map = {r: ("C#" if r == "wieslawsoltes/Dock" else "Python") for r in regression["full_name"].unique()}
    return _forest_plot(
        regression, language_map,
        "Fig 3 — Segmented regression coefficients, 95% CI (RQ1, 4-repo pilot)",
        "fig3_forest_plot",
    )


def make_fig3b_forest_plot_full(regression_full):
    """Fig 3b - the same analysis, full corpus: every repo with enough
    in-house pre/post data (min 5 pre, 5 post - see
    src/analysis/segmented_regression.py's run_full_corpus()), both
    languages, all 3 primary metrics. A real scope upgrade from the
    pilot's 4 repos / 12 rows, kept as its own separate figure rather than
    silently replacing Fig 3 - same two-tier convention as Fig 1/1b."""
    rs = fc.load_manifest()[["full_name", "language"]].drop_duplicates().set_index("full_name")["language"]
    language_map = rs.to_dict()
    return _forest_plot(
        regression_full, language_map,
        f"Fig 3b — Segmented regression coefficients, 95% CI, full corpus "
        f"({regression_full['full_name'].nunique()} repos, both languages)",
        "fig3b_forest_plot_full",
    )


def make_fig4_composition(pooled, smells):
    """Fig 4 - stacked area, design vs. implementation smell share over
    time. Architecture layer omitted (chunk-scoping caveat, already
    documented in Results.md's own "Caveat" section) - not silently
    dropped, stated on the figure. Two-tier: pilot panel + in-house panel,
    same split as Fig 1/1b - the in-house panel now pools BOTH languages
    (cs_smells.py landed 2026-08-13), not just the original 11 Python
    repos, since `smells` already comes from figures_common.py's
    generalized load_inhouse_smells()."""
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
    axes[1].set_title(
        f"In-house ({smells['full_name'].nunique()} repos, both languages, "
        f"py_smells.py + cs_smells.py, pooled)", fontsize=10,
    )
    fc.format_year_axis(axes[1])
    axes[1].legend(frameon=False, fontsize=8, loc="lower left")

    fig.suptitle(
        "Fig 4 — Design vs. implementation smell composition over time\n"
        "(architecture smells omitted — chunk-scoping caveat, see Results.md)",
        fontsize=11, y=0.99,
    )
    return fc.save_fig(fig, SUBDIR, "fig4_smell_composition", top=0.88)


def make_fig5_loc_cc_before_after(inhouse_metrics):
    """Fig 5 - LOC/CC before vs. after, pooled across every repo the
    in-house OO-metrics engine has real data for (18 repos, both
    languages) - scoped in the original figures plan but never actually
    built (absent from this script's main() until now). Unlike the smell
    figures, this data is a validated 1:1 DPy/Designite replacement
    (r=0.997-0.999, Writing/InHouseTooling.md), so pre/post here isn't a
    differently-defined signal the way Fig 1b/4/6's smell panels are -
    just a wider-coverage version of the same metric."""
    rs = fc.load_repo_summary().set_index("full_name")["intervention_date"]
    d = inhouse_metrics[inhouse_metrics["full_name"].isin(rs.index)].copy()
    d["intervention_date"] = d["full_name"].map(rs)
    d["is_post"] = d["target_date"] >= d["intervention_date"]

    fig, axes = plt.subplots(1, 2, figsize=(11, 5.2))
    for ax, metric, title in [
        (axes[0], "method_loc_p90", "Method LOC, p90"),
        (axes[1], "cyclomatic_complexity_p90", "Cyclomatic complexity, p90"),
    ]:
        pre = d[~d["is_post"]][metric].dropna()
        post = d[d["is_post"]][metric].dropna()
        bp = ax.boxplot([pre, post], tick_labels=[f"Pre\n(n={len(pre)})", f"Post\n(n={len(post)})"],
                         patch_artist=True, widths=0.5, showfliers=False)
        for patch, color in zip(bp["boxes"], [fc.PERIOD_COLOR["pre"], fc.PERIOD_COLOR["post"]]):
            patch.set_facecolor(color)
            patch.set_alpha(0.55)
        rng = np.random.default_rng(0)
        for i, series, color in [(1, pre, fc.PERIOD_COLOR["pre"]), (2, post, fc.PERIOD_COLOR["post"])]:
            jitter = rng.normal(0, 0.05, size=len(series))
            ax.scatter(np.full(len(series), i) + jitter, series, s=5, alpha=0.15, color=color, zorder=0)
        ax.set_title(title, fontsize=10.5)
        ax.grid(axis="y", linewidth=0.5)
    fig.suptitle(
        f"Fig 5 — LOC/CC before vs. after, in-house OO metrics "
        f"({d['full_name'].nunique()} repos, both languages, validated 1:1 vs. DPy/Designite)",
        fontsize=11, y=0.99,
    )
    return fc.save_fig(fig, SUBDIR, "fig5_loc_cc_before_after", top=0.90)


def make_fig6_cross_language(pooled, smells, inhouse_metrics):
    """Fig 6 - cross-language comparison, both panels now genuinely
    both-language in-house data (2026-08-13: cs_smells.py landed for
    panel A, the full-corpus OO-metrics consolidation for panel B) -
    neither panel is pilot-scoped or single-repo-C# anymore, so the
    "still lopsided"/"pilot only" captions from before this build are
    gone, not left stale. Real remaining scope note, stated instead:
    the smell panel (A) still uses a narrower, differently-validated
    smell definition than DPy/Designite (see figures_common.py's
    docstring) - that caveat doesn't go away just because coverage did."""
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))

    # Panel A: smell density, language boxplot - both languages now from
    # the same in-house detector family (py_smells.py / cs_smells.py).
    langs = sorted(smells["language"].dropna().unique())
    by_lang = {l: smells.loc[smells["language"] == l, "design_smell_density_per_kloc"].dropna() for l in langs}
    n_repos = smells.groupby("language")["full_name"].nunique()
    bp = axes[0].boxplot([by_lang[l] for l in langs], tick_labels=[
        f"{l}\n(in-house, n={n_repos[l]} repos)" for l in langs
    ], patch_artist=True, widths=0.5)
    for patch, lang in zip(bp["boxes"], langs):
        patch.set_facecolor(fc.LANGUAGE_COLOR.get(lang, fc.MUTED))
        patch.set_alpha(0.55)
    axes[0].set_title("Design smell density — both languages\n(in-house detector, narrower definition than DPy/Designite)", fontsize=9.5)
    axes[0].set_ylabel("Design smells / KLOC")
    axes[0].tick_params(labelsize=8)

    # Panel B: OO metric (CC p90), full in-house corpus, both languages -
    # a validated 1:1 DPy/Designite replacement, no scope caveat needed.
    labels = sorted(inhouse_metrics["language"].dropna().unique())
    cc = {l: inhouse_metrics.loc[inhouse_metrics["language"] == l, "cyclomatic_complexity_p90"].dropna() for l in labels}
    n_repos_cc = inhouse_metrics.groupby("language")["full_name"].nunique()
    bp2 = axes[1].boxplot([cc[l] for l in labels], tick_labels=[
        f"{l}\n(n={n_repos_cc[l]} repos)" for l in labels
    ], patch_artist=True, widths=0.5)
    for patch, lang in zip(bp2["boxes"], labels):
        patch.set_facecolor(fc.LANGUAGE_COLOR.get(lang, fc.MUTED))
        patch.set_alpha(0.55)
    axes[1].set_title("Cyclomatic complexity p90 — full in-house corpus\n(validated 1:1 vs. DPy/Designite)", fontsize=9.5)
    axes[1].set_ylabel("CC p90")
    axes[1].tick_params(labelsize=8)

    fig.suptitle("Fig 6 — Cross-language comparison, full in-house corpus (both panels)",
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
    regression_full = fc.load_regression_full()
    smells = fc.load_inhouse_smells()
    inhouse_metrics = fc.load_inhouse_metrics()
    manifest = fc.load_manifest()

    print("Fig 1:", make_fig1_pilot_small_multiples(pooled))
    print("Fig 1b:", make_fig1b_inhouse_small_multiples(smells))
    print("Fig 2:", make_fig2_pilot_event_window(pooled))
    print("Fig 3:", make_fig3_forest_plot(regression))
    print("Fig 3b:", make_fig3b_forest_plot_full(regression_full))
    print("Fig 4:", make_fig4_composition(pooled, smells))
    print("Fig 5:", make_fig5_loc_cc_before_after(inhouse_metrics))
    print("Fig 6:", make_fig6_cross_language(pooled, smells, inhouse_metrics))
    t1_path, t1 = make_table1_coverage(manifest, smells)
    print("Table 1:", t1_path, f"({len(t1)} repos)")
    t2_path, t2 = make_table2_descriptive_stats(pooled, smells)
    print("Table 2:", t2_path, f"({len(t2)} rows)")


# Stable, predictable entry point for src/pipeline/run_pipeline.py (this
# script has no argparse - see module docstring's "Run: python
# generate_track_a_figures.py" - every figure/table runs unconditionally,
# which is fine: cheap, idempotent operations over already-pooled data,
# not scale-sensitive - see the pipeline scaling plan's "explicitly not
# changing" section for why this isn't being parameterized further).
run = main


if __name__ == "__main__":
    run()
