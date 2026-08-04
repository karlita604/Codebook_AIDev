"""
Exploratory analysis of the Dock Designite pilot output
(results/analysis/07-28-smell-metrics-96.csv). Generates the figures and
pre/post statistics table behind Writing/DockDesigniteReport.md - that
report is hand-written, not auto-generated from this script's output, so
edit both if the underlying numbers change.

Requires scipy (not otherwise a dependency of this repo's phase0 scripts -
only used here for mannwhitneyu): pip install scipy

Usage:
    python analyze_dock_designite.py
"""
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from scipy.stats import mannwhitneyu
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "Writing" / "figures" / "dock_designite"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# --- palette (dataviz skill reference palette) ---
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
VIOLET = "#4a3aa7"
RED = "#e34948"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BASELINE = "#c3c2b7"

plt.rcParams.update({
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "axes.edgecolor": BASELINE,
    "axes.labelcolor": SECONDARY_INK,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "grid.color": GRID,
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.titlesize": 12,
    "axes.titlecolor": INK,
    "axes.titleweight": "bold",
    "axes.spines.top": False,
    "axes.spines.right": False,
})

INTERVENTION = pd.Timestamp("2025-06-25", tz="UTC")
SLNX_MIGRATION = pd.Timestamp("2025-12-25", tz="UTC")

df = pd.read_csv(ROOT / "results" / "analysis" / "07-28-smell-metrics-96.csv")
df["target_date"] = pd.to_datetime(df["target_date"])
df = df.sort_values("target_date").reset_index(drop=True)

# --- derived metrics ---
df["testability_smell_density_per_kloc"] = df["testability_smell_count"] / df["total_loc"] * 1000
df["test_smell_density_per_kloc"] = df["test_smell_count"] / df["total_loc"] * 1000
df["methods_per_class"] = df["n_methods"] / df["n_classes"]
df["class_tail_ratio"] = df["class_loc_p90"] / df["class_loc_p50"]
df["method_tail_ratio"] = df["method_loc_p90"] / df["method_loc_p50"]
df["total_smell_density_per_kloc"] = df["design_smell_density_per_kloc"] + df["implementation_smell_density_per_kloc"]

a1 = df[df["track"] == "A1"].copy()
a2 = df[df["track"] == "A2"].copy()
a2["days_rel"] = (a2["target_date"] - INTERVENTION).dt.days

print(f"A1 rows: {len(a1)}, date range {a1['target_date'].min().date()} to {a1['target_date'].max().date()}")
print(f"A2 rows: {len(a2)}, days_rel range {a2['days_rel'].min()} to {a2['days_rel'].max()}")
print(f"Chunked rows overall (n_chunks==2): {(df['n_chunks']==2).sum()} / {len(df)}")

# ============================================================
# Chart 1: A1 repo growth (total_loc) over calendar time
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["total_loc"], color=BLUE, linewidth=2, marker="o", markersize=4)
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.text(INTERVENTION, ax.get_ylim()[1]*0.96, " intervention\n (2025-06-25)", color=SECONDARY_INK, fontsize=8, va="top")
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.text(SLNX_MIGRATION + pd.Timedelta(days=10), ax.get_ylim()[1]*0.5, "no data\n(.slnx gap)",
        color=MUTED, fontsize=8, va="center")
ax.set_title("Dock repo size over time (Track A1, monthly)")
ax.set_ylabel("Total LOC (sum of ClassMetrics.LOC)")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "01_loc_growth_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 2: A1 smell density trend (design + implementation)
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["design_smell_density_per_kloc"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Design smells / KLOC")
ax.plot(a1["target_date"], a1["implementation_smell_density_per_kloc"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="Implementation smells / KLOC")
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Dock smell density over time (Track A1, monthly)")
ax.set_ylabel("Smells per 1,000 LOC")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "02_smell_density_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 3: A1 cyclomatic complexity trend
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["cyclomatic_complexity_p50"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Median (p50)")
ax.plot(a1["target_date"], a1["cyclomatic_complexity_p90"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="90th percentile (p90)")
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Per-method cyclomatic complexity over time (Track A1)")
ax.set_ylabel("Cyclomatic complexity")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "03_cyclomatic_complexity_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 4: A1 class size distribution over time
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["class_loc_p50"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Median (p50)")
ax.plot(a1["target_date"], a1["class_loc_p90"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="90th percentile (p90)")
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Class size (LOC/class) over time (Track A1)")
ax.set_ylabel("LOC per class")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "04_class_size_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 5: A1 method size distribution over time
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["method_loc_p50"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Median (p50)")
ax.plot(a1["target_date"], a1["method_loc_p90"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="90th percentile (p90)")
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Method size (LOC/method) over time (Track A1)")
ax.set_ylabel("LOC per method")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "05_method_size_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 6: A1 testability + test smell density
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["testability_smell_density_per_kloc"], color=VIOLET, linewidth=2, marker="o", markersize=4, label="Testability smells / KLOC")
ax.plot(a1["target_date"], a1["test_smell_density_per_kloc"], color=RED, linewidth=2, marker="o", markersize=4, label="Test-code smells / KLOC")
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Testability & test-code smell density over time (Track A1)")
ax.set_ylabel("Smells per 1,000 LOC")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "06_testability_test_smells_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 7: A1 methods-per-class (cohesion/complexity proxy)
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a1["target_date"], a1["methods_per_class"], color=AQUA, linewidth=2, marker="o", markersize=4)
ax.axvline(INTERVENTION, color=MUTED, linestyle="--", linewidth=1.2)
ax.axvspan(SLNX_MIGRATION, a1["target_date"].max() + pd.Timedelta(days=60), color=MUTED, alpha=0.08)
ax.set_title("Methods per class over time (Track A1)")
ax.set_ylabel("Methods / class")
ax.grid(axis="y", linewidth=0.6)
ax.xaxis.set_major_locator(mdates.YearLocator())
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
fig.tight_layout()
fig.savefig(FIG_DIR / "07_methods_per_class_a1.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 7b: A2 event-time LOC growth (the key contextual chart -
# repo was flat pre-intervention, then grew explosively right after)
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.4))
ax.plot(a2["days_rel"], a2["total_loc"], color=BLUE, linewidth=2, marker="o", markersize=4)
ax.axvline(0, color=MUTED, linestyle="--", linewidth=1.2)
ax.text(3, ax.get_ylim()[1]*0.9, "intervention", color=SECONDARY_INK, fontsize=8, va="top")
chunk_switch = a2[a2["n_chunks"] == 2]["days_rel"].min()
ax.axvline(chunk_switch, color=ORANGE, linestyle=":", linewidth=1.2)
ax.text(chunk_switch + 2, ax.get_ylim()[1]*0.55, "crosses Designite's\n50K-LOC cap\n(chunking kicks in)",
        color=ORANGE, fontsize=7.5, va="top")
ax.set_title("Dock's LOC trajectory around the intervention point (Track A2)")
ax.set_xlabel("Days relative to intervention (2025-06-25)")
ax.set_ylabel("Total LOC")
ax.grid(axis="y", linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG_DIR / "07b_loc_growth_a2.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 8: A2 event-time smell density (zoomed around intervention)
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a2["days_rel"], a2["design_smell_density_per_kloc"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Design smells / KLOC")
ax.plot(a2["days_rel"], a2["implementation_smell_density_per_kloc"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="Implementation smells / KLOC")
ax.axvline(0, color=MUTED, linestyle="--", linewidth=1.2)
ax.text(2, ax.get_ylim()[1]*0.96, "intervention", color=SECONDARY_INK, fontsize=8, va="top")
ax.set_title("Smell density around the intervention point (Track A2)")
ax.set_xlabel("Days relative to intervention (2025-06-25)")
ax.set_ylabel("Smells per 1,000 LOC")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG_DIR / "08_smell_density_a2.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 9: A2 event-time cyclomatic complexity
# ============================================================
fig, ax = plt.subplots(figsize=(9, 4.2))
ax.plot(a2["days_rel"], a2["cyclomatic_complexity_p50"], color=BLUE, linewidth=2, marker="o", markersize=4, label="Median (p50)")
ax.plot(a2["days_rel"], a2["cyclomatic_complexity_p90"], color=ORANGE, linewidth=2, marker="o", markersize=4, label="90th percentile (p90)")
ax.axvline(0, color=MUTED, linestyle="--", linewidth=1.2)
ax.set_title("Cyclomatic complexity around the intervention point (Track A2)")
ax.set_xlabel("Days relative to intervention (2025-06-25)")
ax.set_ylabel("Cyclomatic complexity")
ax.legend(frameon=False, loc="upper left")
ax.grid(axis="y", linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG_DIR / "09_cyclomatic_complexity_a2.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 10: pre/post paired bar comparison (A2)
# ============================================================
a2["period"] = np.where(a2["days_rel"] < 0, "pre", "post")
metrics_for_bars = [
    ("design_smell_density_per_kloc", "Design smells\n/ KLOC"),
    ("implementation_smell_density_per_kloc", "Implementation\nsmells / KLOC"),
    ("testability_smell_density_per_kloc", "Testability\nsmells / KLOC"),
    ("cyclomatic_complexity_p50", "Median cyclomatic\ncomplexity"),
    ("methods_per_class", "Methods\n/ class"),
]
pre_means = [a2[a2["period"]=="pre"][m].mean() for m, _ in metrics_for_bars]
post_means = [a2[a2["period"]=="post"][m].mean() for m, _ in metrics_for_bars]
labels = [lbl for _, lbl in metrics_for_bars]

x = np.arange(len(labels))
width = 0.35
fig, ax = plt.subplots(figsize=(9.5, 4.6))
ax.bar(x - width/2, pre_means, width, label="Pre-intervention (n=22)", color=BLUE)
ax.bar(x + width/2, post_means, width, label="Post-intervention (n=17)", color=ORANGE)
ax.set_xticks(x)
ax.set_xticklabels(labels, fontsize=8.5)
ax.set_title("Pre vs. post intervention means (Track A2)")
ax.legend(frameon=False, loc="upper right")
ax.grid(axis="y", linewidth=0.6)
fig.tight_layout()
fig.savefig(FIG_DIR / "10_pre_post_bars_a2.png", dpi=150)
plt.close(fig)

# ============================================================
# Chart 11: correlation heatmap among key metrics
# ============================================================
corr_cols = [
    "total_loc", "n_classes", "n_methods", "methods_per_class",
    "class_loc_p50", "method_loc_p50", "cyclomatic_complexity_p90",
    "design_smell_density_per_kloc", "implementation_smell_density_per_kloc",
    "testability_smell_density_per_kloc",
]
# cyclomatic_complexity_p50 dropped - constant (1.0) across every single row,
# so its correlation with anything is mathematically undefined (all-NaN row/col).
corr = df[corr_cols].corr()
corr_labels = [
    "Total LOC", "# Classes", "# Methods", "Methods/class",
    "Class LOC p50", "Method LOC p50", "Cyclo. complexity p90",
    "Design smell density", "Impl. smell density", "Testability smell density",
]
fig, ax = plt.subplots(figsize=(8.5, 7.5))
im = ax.imshow(corr.values, cmap="RdBu_r", vmin=-1, vmax=1)
ax.set_xticks(range(len(corr_labels)))
ax.set_yticks(range(len(corr_labels)))
ax.set_xticklabels(corr_labels, rotation=45, ha="right", fontsize=8)
ax.set_yticklabels(corr_labels, fontsize=8)
for i in range(len(corr_labels)):
    for j in range(len(corr_labels)):
        v = corr.values[i, j]
        color = "white" if abs(v) > 0.6 else INK
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", color=color, fontsize=7.5)
ax.set_title("Correlation matrix across all 87 rows (A1+A2)", pad=12)
cbar = fig.colorbar(im, ax=ax, shrink=0.8)
cbar.ax.tick_params(labelsize=8)
fig.tight_layout()
fig.savefig(FIG_DIR / "11_correlation_heatmap.png", dpi=150)
plt.close(fig)

print("\nAll figures written to", FIG_DIR)

# ============================================================
# Statistics: Mann-Whitney U + Cliff's delta, pre vs post (A2)
# ============================================================
def cliffs_delta(x, y):
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    diff = x[:, None] - y[None, :]
    greater = (diff > 0).sum()
    less = (diff < 0).sum()
    return (greater - less) / (len(x) * len(y))

def delta_label(d):
    ad = abs(d)
    if ad < 0.147: return "negligible"
    if ad < 0.33: return "small"
    if ad < 0.474: return "medium"
    return "large"

stat_cols = [
    "total_loc", "n_classes", "n_methods", "methods_per_class",
    "class_loc_p50", "class_loc_p90", "method_loc_p50", "method_loc_p90",
    "cyclomatic_complexity_p50", "cyclomatic_complexity_p90",
    "design_smell_density_per_kloc", "implementation_smell_density_per_kloc",
    "testability_smell_density_per_kloc", "class_tail_ratio", "method_tail_ratio",
]

print("\n=== Pre vs Post (Track A2, intervention = 2025-06-25) ===")
print(f"{'metric':<38}{'pre_median':>12}{'post_median':>12}{'%chg':>9}{'U p-value':>11}{'cliffs_d':>10}{'magnitude':>11}")
rows_out = []
pre = a2[a2["period"]=="pre"]
post = a2[a2["period"]=="post"]
for col in stat_cols:
    pre_vals = pre[col].dropna()
    post_vals = post[col].dropna()
    pre_med, post_med = pre_vals.median(), post_vals.median()
    pct_chg = (post_med - pre_med) / pre_med * 100 if pre_med else float("nan")
    try:
        u_stat, p_val = mannwhitneyu(pre_vals, post_vals, alternative="two-sided")
    except ValueError:
        p_val = float("nan")
    d = cliffs_delta(pre_vals, post_vals)
    rows_out.append((col, pre_med, post_med, pct_chg, p_val, d, delta_label(d)))
    print(f"{col:<38}{pre_med:>12.3f}{post_med:>12.3f}{pct_chg:>8.1f}%{p_val:>11.4f}{d:>10.3f}{delta_label(d):>11}")

stats_df = pd.DataFrame(rows_out, columns=["metric","pre_median","post_median","pct_change","p_value","cliffs_delta","magnitude"])
stats_df.to_csv(ROOT / "Writing" / "figures" / "dock_designite" / "pre_post_stats.csv", index=False)
print("\nWrote pre_post_stats.csv")

# also print full descriptive stats for A1 (start vs end of history) as a sanity check
print("\n=== A1 first-4 vs last-4 available points (long-run drift sanity check) ===")
a1_ok = a1.sort_values("target_date")
first4 = a1_ok.head(4)
last4 = a1_ok.tail(4)
for col in ["design_smell_density_per_kloc", "implementation_smell_density_per_kloc", "testability_smell_density_per_kloc", "cyclomatic_complexity_p50"]:
    print(f"{col:<40} first4={first4[col].mean():.3f}  last4={last4[col].mean():.3f}")
