"""
Shared palette, style, and data-loading for the Track A structural-health
and method-churn figure sets (Figs 1-9, Tables 1-3 - see the session's plan
doc for the full inventory). Deliberately reuses
src/phase0/analyze_dock_designite.py's established convention (same hex
palette, same rcParams, same Writing/figures/<name>/NN_description.png
output shape) rather than inventing a second house style - that script
isn't modified itself (it backs Writing/DockDesigniteReport.md directly),
this is new, parallel code following the same look.

Two real data-scope facts baked into the loaders below, not left implicit:
- Smell density (design/implementation) exists at two different scopes,
  from two different tools, with two different validation stories: the
  4-repo pilot (DPy/Designite, `07-29-pooled-structural-metrics.csv`) and
  an 11-Python-repo in-house layer (`py_smells.py`,
  `08-11-inhouse-smells-python-926.csv`) that uses a narrower, differently-
  validated smell definition (Lanza & Marinescu Detection Strategies, not
  DPy/Designite's closed catalogs - see Writing/PySmellDetection.md).
  Never blended into one series without a `source` column saying which is
  which.
- OO metrics (LOC/CC/WMC/LCOM/DIT/Fan-In/Out) now have two scopes too,
  same split as smells: `load_pooled_metrics()`'s original 4-repo
  DPy/Designite pilot, and `load_inhouse_metrics()`'s full-corpus in-house
  pool (consolidate_inhouse_metrics.py) - unlike smells, OO metrics ARE a
  validated 1:1 replacement (r=0.997-0.999 against real DPy/Designite
  output), so the in-house side isn't a differently-defined signal the way
  smells are, just a wider-coverage version of the same metric.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
FIG_DIR = ROOT / "Writing" / "figures"

# --- palette (dataviz skill reference palette, same hex values already
# proven out in analyze_dock_designite.py and the RQ3 HTML dashboard) ---
BLUE = "#2a78d6"
ORANGE = "#eb6834"
AQUA = "#1baf7a"
VIOLET = "#4a3aa7"
RED = "#e34948"
YELLOW = "#eda100"
INK = "#0b0b0b"
SECONDARY_INK = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
SURFACE = "#fcfcfb"
BASELINE = "#c3c2b7"

# Fixed roles used across every figure in this set, so "blue = Python,
# orange = C#" (etc.) means the same thing on every chart, not re-picked
# per figure.
LANGUAGE_COLOR = {"Python": BLUE, "C#": ORANGE}
SOURCE_COLOR = {"dpy_designite": BLUE, "inhouse": VIOLET}
PERIOD_COLOR = {"pre": BLUE, "post": ORANGE}


def setup_style():
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


def save_fig(fig, subdir, name, dpi=150, top=None):
    """Writing/figures/<subdir>/<name>.png - creates subdir if needed,
    closes the figure after saving (matplotlib figures aren't free, and
    this set produces dozens of them in one run).

    `top` (0-1, e.g. 0.90) reserves headroom above the axes for a
    fig.suptitle() - tight_layout() on its own doesn't know about a
    suptitle placed above the normal axes bounds (y > ~0.98), so a
    multi-line suptitle gets silently clipped at the saved PNG's top edge
    without this. Pass it whenever suptitle needs more than one line."""
    out_dir = FIG_DIR / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{name}.png"
    if top is not None:
        fig.tight_layout(rect=[0, 0, 1, top])
    else:
        fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    return path


def draw_intervention_line(ax, x, label="intervention", color=MUTED):
    """The vline+label pattern analyze_dock_designite.py already uses on
    every time-series chart - factored out here since this figure set
    needs it far more than 11 times."""
    ax.axvline(x, color=color, linestyle="--", linewidth=1.2)
    ylim = ax.get_ylim()
    ax.text(x, ylim[1] * 0.96, f" {label}", color=SECONDARY_INK, fontsize=8, va="top")


def format_year_axis(ax):
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))


# --------------------------------------------------------------------- #
# Data loading
# --------------------------------------------------------------------- #

ANALYSIS_DIR = ROOT / "results" / "analysis"
REPO_SUMMARY_DIR = ROOT / "results" / "repos"
MANIFEST_DIR = ROOT / "results" / "snapshots"

PILOT_LANGUAGES = {
    "crewAIInc/crewAI": "Python", "airbytehq/airbyte": "Python",
    "mlflow/mlflow": "Python", "wieslawsoltes/Dock": "C#",
}


def load_pooled_metrics():
    """The 4-repo pilot's DPy/Designite output - smell density AND OO
    metrics, 351 rows, the "clean," originally-validated comparison
    point for everything in this figure set."""
    df = pd.read_csv(ANALYSIS_DIR / "07-29-pooled-structural-metrics.csv")
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    df["intervention_date"] = pd.to_datetime(df["intervention_date"], utc=True)
    return df.sort_values("target_date").reset_index(drop=True)


def load_regression():
    return pd.read_csv(ANALYSIS_DIR / "07-29-segmented-regression-A1.csv")


def latest_inhouse_metrics_pooled():
    files = sorted(ANALYSIS_DIR.glob("*-inhouse-metrics-pooled.csv"))
    if not files:
        raise FileNotFoundError(
            f"no *-inhouse-metrics-pooled.csv in {ANALYSIS_DIR} - run "
            "src/inhouse/consolidate_inhouse_metrics.py first"
        )
    return files[-1]


def load_inhouse_metrics():
    """The consolidated in-house OO-metrics pool (consolidate_inhouse_metrics.py) -
    every repo/language pool_inhouse_metrics.py has been run against, not
    just the 3-repo Python pilot. Caller captions this as full-corpus
    OO metrics (validated 1:1 against DPy/Designite, r=0.997-0.999 - see
    Writing/InHouseTooling.md) - a genuinely different scope claim than
    load_inhouse_smells()'s narrower, differently-validated smell data."""
    df = pd.read_csv(latest_inhouse_metrics_pooled())
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    return df.sort_values("target_date").reset_index(drop=True)


def latest_regression_full():
    files = sorted(ANALYSIS_DIR.glob("*-segmented-regression-full-*.csv"))
    if not files:
        raise FileNotFoundError(
            f"no *-segmented-regression-full-*.csv in {ANALYSIS_DIR} - run "
            "src/analysis/segmented_regression.py's full-corpus run first"
        )
    return files[-1]


def load_regression_full():
    """The full-corpus segmented-regression output (src/analysis/
    segmented_regression.py, run across every repo with enough pre/post
    in-house data - see that module's docstring for the model and the
    mandatory pilot-reproduction check that validates it). Separate from
    load_regression()'s original 4-repo DPy/Designite-backed table, never
    silently merged with it."""
    return pd.read_csv(latest_regression_full())


def load_composition():
    return pd.read_csv(ANALYSIS_DIR / "07-29-rq2-composition.csv")


def latest_inhouse_smells_pooled():
    files = sorted(ANALYSIS_DIR.glob("*-inhouse-smells-pooled.csv"))
    if not files:
        raise FileNotFoundError(
            f"no *-inhouse-smells-pooled.csv in {ANALYSIS_DIR} - run "
            "src/inhouse/consolidate_inhouse_smells.py first"
        )
    return files[-1]


def load_inhouse_smells():
    """py_smells.py (Python) + cs_smells.py (C#) real output, consolidated
    (consolidate_inhouse_smells.py) - now both languages, not just the
    original 11-Python-repo run. Caller is responsible for captioning this
    as a different, narrower smell definition than the pilot's DPy/Designite
    data (see this module's docstring) - not done automatically here, since
    it depends on how each figure presents it."""
    df = pd.read_csv(latest_inhouse_smells_pooled())
    df = df[df["status"] == "ok"].copy()
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    return df.sort_values("target_date").reset_index(drop=True)


def latest_repo_summary():
    files = sorted(REPO_SUMMARY_DIR.glob("*-repo-summary-*.csv"))
    if not files:
        raise FileNotFoundError(f"no repo-summary csv in {REPO_SUMMARY_DIR}")
    return files[-1]


def load_repo_summary():
    df = pd.read_csv(latest_repo_summary())
    df["intervention_date"] = pd.to_datetime(df["intervention_date"], utc=True)
    return df


def latest_manifest():
    files = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not files:
        raise FileNotFoundError(f"no manifest csv in {MANIFEST_DIR}")
    return files[-1]


def load_manifest():
    df = pd.read_csv(latest_manifest())
    df["target_date"] = pd.to_datetime(df["target_date"], utc=True)
    return df


def attach_smell_source(pilot_df, inhouse_df, metric):
    """One tidy long-form frame for a given smell metric, both sources
    stacked with an explicit `source` column - `dpy_designite` (pilot,
    4 repos) and `inhouse` (py_smells.py, 11 Python repos). Never returns
    a blended mean across sources - that's the caller's decision to make
    explicitly if it ever wants one, not this function's default."""
    a = pilot_df[["full_name", "language", "track", "target_date", metric]].copy()
    a["source"] = "dpy_designite"
    b = inhouse_df[["full_name", "language", "track", "target_date", metric]].copy()
    b["source"] = "inhouse"
    return pd.concat([a, b], ignore_index=True)
