"""
Generate representative figures + summary stats for
data/04_pr250 - 04_pr250.csv.
Saves PNGs to results/phase0/pr250/ and a findings.md summarizing the dataset.
"""

import csv
import math
import sys
import statistics as st
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "04_pr250 - 04_pr250.csv"
OUT_DIR = ROOT / "results" / "phase0" / "pr250"
OUT_DIR.mkdir(parents=True, exist_ok=True)

csv.field_size_limit(sys.maxsize)

# ---------------------------------------------------------------- palette --
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
SEQ_BLUE = "#3987e5"
SEQ_BLUE_LIGHT = "#9ec5f4"

AGENT_ORDER = ["Devin", "Copilot", "OpenAI_Codex", "Cursor", "Claude_Code"]
AGENT_LABEL = {
    "Devin": "Devin",
    "Copilot": "Copilot",
    "OpenAI_Codex": "OpenAI Codex",
    "Cursor": "Cursor",
    "Claude_Code": "Claude Code",
}
AGENT_COLOR = {
    "Devin": "#2a78d6",
    "Copilot": "#1baf7a",
    "OpenAI_Codex": "#eda100",
    "Cursor": "#008300",
    "Claude_Code": "#4a3aa7",
}

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Segoe UI", "Arial", "DejaVu Sans"],
        "text.color": INK_PRIMARY,
        "axes.edgecolor": BASELINE,
        "axes.labelcolor": INK_SECONDARY,
        "xtick.color": INK_MUTED,
        "ytick.color": INK_MUTED,
        "axes.facecolor": SURFACE,
        "figure.facecolor": SURFACE,
        "savefig.facecolor": SURFACE,
        "font.size": 11,
    }
)


def style_ax(ax, hide_y_spine=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    if hide_y_spine:
        ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(BASELINE)
    ax.tick_params(length=0)


def parse_dt(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    for fmt in (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(s.replace("Z", ""))
    except Exception:
        return None


# --------------------------------------------------------------- load data --
with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    rows: list[dict[str, Any]] = list(csv.DictReader(f))

n = len(rows)

for r in rows:
    r["_created"] = parse_dt(r.get("created_at"))
    r["_closed"] = parse_dt(r.get("closed_at"))
    r["_duration_h"] = (
        (r["_closed"] - r["_created"]).total_seconds() / 3600
        if r["_created"] and r["_closed"]
        else None
    )
    r["_body_words"] = len(r["body"].split()) if r.get("body") else 0

# --------------------------------------------------------------- aggregates -
agent_counts = Counter(r["agent"].strip() for r in rows)

agent_duration = defaultdict(list)
agent_body = defaultdict(list)
for r in rows:
    a = r["agent"].strip()
    if r["_duration_h"] is not None:
        agent_duration[a].append(r["_duration_h"])
    agent_body[a].append(r["_body_words"])

months = sorted(
    {r["_created"].strftime("%Y-%m") for r in rows if r["_created"]}
)
agent_month: defaultdict[str, Counter] = defaultdict(Counter)
for r in rows:
    if r["_created"]:
        agent_month[r["_created"].strftime("%Y-%m")][r["agent"].strip()] += 1

label_counts = Counter(r["manual_label"].strip() for r in rows).most_common()

repo_counts = Counter(r["repo_url"].strip() for r in rows).most_common()

durations = sorted(
    r["_duration_h"] for r in rows if r["_duration_h"] is not None
)


def pct(lst, p):
    idx = min(int(len(lst) * p), len(lst) - 1)
    return lst[idx]


duration_summary = {
    "n": len(durations),
    "min": min(durations),
    "p25": pct(durations, 0.25),
    "median": st.median(durations),
    "p75": pct(durations, 0.75),
    "p90": pct(durations, 0.90),
    "max": max(durations),
    "mean": st.mean(durations),
}

merged_count = sum(
    1 for r in rows if r.get("merged_at") and r["merged_at"].strip()
)
empty_body = sum(1 for r in rows if not r.get("body") or not r["body"].strip())
unique_repos = len(repo_counts)
unique_users = len(set(r["user"] for r in rows if r.get("user")))
repo_agents = defaultdict(set)
for r in rows:
    repo_agents[r["repo_url"]].add(r["agent"].strip())
multi_agent_repos = sum(1 for v in repo_agents.values() if len(v) > 1)

# ============================================================== FIGURE 1 ===
# Agent distribution
fig, ax = plt.subplots(figsize=(7, 3.2), dpi=200)
agents = AGENT_ORDER
values = [agent_counts[a] for a in agents]
colors = [AGENT_COLOR[a] for a in agents]
ypos = range(len(agents))
bars = ax.barh(ypos, values, color=colors, height=0.6)
ax.set_yticks(list(ypos))
ax.set_yticklabels([AGENT_LABEL[a] for a in agents])
ax.invert_yaxis()
for b, v in zip(bars, values):
    ax.text(
        v + max(values) * 0.015,
        b.get_y() + b.get_height() / 2,
        str(v),
        va="center",
        fontsize=10,
        color=INK_PRIMARY,
    )
ax.set_xlabel("Number of PRs")
ax.set_title(
    "Figure 1. PRs by coding agent (n=250)",
    loc="left",
    fontsize=12,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.xaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)
fig.tight_layout()
fig.savefig(OUT_DIR / "fig1_agent_distribution.png")
plt.close(fig)

# ============================================================== FIGURE 2 ===
# Monthly volume stacked by agent
fig, ax = plt.subplots(figsize=(8, 3.6), dpi=200)
month_labels = [
    datetime.strptime(m, "%Y-%m").strftime("%b'%y") for m in months
]
bottom = [0] * len(months)
for a in agents:
    vals = [agent_month[m].get(a, 0) for m in months]
    ax.bar(
        month_labels,
        vals,
        bottom=bottom,
        color=AGENT_COLOR[a],
        label=AGENT_LABEL[a],
        width=0.6,
    )
    bottom = [b + v for b, v in zip(bottom, vals)]
ax.set_ylabel("PRs created")
ax.set_title(
    "Figure 2. Monthly PR volume by agent",
    loc="left",
    fontsize=12,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.yaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
ax.legend(
    frameon=False,
    ncol=5,
    fontsize=9,
    loc="upper left",
    bbox_to_anchor=(0, -0.12),
)
style_ax(ax)
fig.tight_layout()
fig.savefig(OUT_DIR / "fig2_monthly_volume_by_agent.png")
plt.close(fig)

# ============================================================== FIGURE 3 ===
# manual_label distribution: top 10 + other
top_labels = label_counts[:10]
other_sum = sum(v for _, v in label_counts[10:])
other_n = len(label_counts) - 10
cats = [f"Code {k}" for k, _ in top_labels] + [f"Other ({other_n} codes)"]
vals = [v for _, v in top_labels] + [other_sum]
colors3 = [SEQ_BLUE] * len(top_labels) + [SEQ_BLUE_LIGHT]

fig, ax = plt.subplots(figsize=(7, 3.6), dpi=200)
ypos = range(len(cats))
bars = ax.barh(ypos, vals, color=colors3, height=0.6)
ax.set_yticks(list(ypos))
ax.set_yticklabels(cats)
ax.invert_yaxis()
for b, v in zip(bars, vals):
    ax.text(
        v + max(vals) * 0.015,
        b.get_y() + b.get_height() / 2,
        str(v),
        va="center",
        fontsize=9.5,
        color=INK_PRIMARY,
    )
ax.set_xlabel("Number of PRs")
ax.set_title(
    "Figure 3. Rejection-reason code frequency (manual_label)",
    loc="left",
    fontsize=12,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.xaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)
fig.tight_layout()
fig.savefig(OUT_DIR / "fig3_rejection_label_distribution.png")
plt.close(fig)

# ============================================================== FIGURE 4 ===
# Top repositories
top_repos = repo_counts[:12]
repo_names = [
    u.replace("https://api.github.com/repos/", "") for u, _ in top_repos
]
repo_vals = [v for _, v in top_repos]

fig, ax = plt.subplots(figsize=(7, 4.2), dpi=200)
ypos = range(len(repo_names))
bars = ax.barh(ypos, repo_vals, color=SEQ_BLUE, height=0.6)
ax.set_yticks(list(ypos))
ax.set_yticklabels(repo_names, fontsize=9.5)
ax.invert_yaxis()
for b, v in zip(bars, repo_vals):
    ax.text(
        v + max(repo_vals) * 0.015,
        b.get_y() + b.get_height() / 2,
        str(v),
        va="center",
        fontsize=9.5,
        color=INK_PRIMARY,
    )
ax.set_xlabel("Number of PRs")
ax.set_title(
    f"Figure 4. Top repositories by PR count (of {unique_repos} total)",
    loc="left",
    fontsize=12,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.xaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)
fig.tight_layout()
fig.savefig(OUT_DIR / "fig4_top_repositories.png")
plt.close(fig)

# ============================================================== FIGURE 5 ===
# Duration distribution (log scale) with percentile markers + per-agent medians
fig, axes = plt.subplots(1, 2, figsize=(10, 3.6), dpi=200)

ax = axes[0]
plot_durations = [max(d, 0.05) for d in durations]  # avoid log(0)
lo, hi = math.log10(min(plot_durations)), math.log10(max(plot_durations))
log_bins = [10 ** (lo + (hi - lo) * i / 24) for i in range(25)]
ax.hist(
    plot_durations,
    bins=log_bins,
    color=SEQ_BLUE,
    edgecolor=SURFACE,
    linewidth=0.5,
)
ax.set_xscale("log")
ax.set_xlabel("Hours to close (log scale)")
ax.set_ylabel("Number of PRs")
ax.set_title(
    "Figure 5a. PR close-time distribution",
    loc="left",
    fontsize=11.5,
    fontweight="bold",
    color=INK_PRIMARY,
)
for p, lbl in [
    (duration_summary["median"], "median"),
    (duration_summary["p75"], "p75"),
]:
    ax.axvline(p, color=INK_SECONDARY, linewidth=1, linestyle="--")
ax.yaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)

ax = axes[1]
med_vals = [st.median(agent_duration[a]) for a in agents]
colors = [AGENT_COLOR[a] for a in agents]
ypos = range(len(agents))
bars = ax.barh(ypos, med_vals, color=colors, height=0.6)
ax.set_yticks(list(ypos))
ax.set_yticklabels([AGENT_LABEL[a] for a in agents])
ax.invert_yaxis()
ax.set_xscale("log")
for b, v in zip(bars, med_vals):
    ax.text(
        v * 1.08,
        b.get_y() + b.get_height() / 2,
        f"{v:.1f}h",
        va="center",
        fontsize=9.5,
        color=INK_PRIMARY,
    )
ax.set_xlabel("Median hours to close (log scale)")
ax.set_title(
    "Figure 5b. Median close time by agent",
    loc="left",
    fontsize=11.5,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.xaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)

fig.tight_layout()
fig.savefig(OUT_DIR / "fig5_duration_distribution.png")
plt.close(fig)

# ============================================================== FIGURE 6 ===
# Median description length (words) by agent
fig, ax = plt.subplots(figsize=(6.5, 3.2), dpi=200)
body_med = [st.median(agent_body[a]) for a in agents]
colors = [AGENT_COLOR[a] for a in agents]
ypos = range(len(agents))
bars = ax.barh(ypos, body_med, color=colors, height=0.6)
ax.set_yticks(list(ypos))
ax.set_yticklabels([AGENT_LABEL[a] for a in agents])
ax.invert_yaxis()
for b, v in zip(bars, body_med):
    ax.text(
        v + max(body_med) * 0.02,
        b.get_y() + b.get_height() / 2,
        f"{v:.0f}",
        va="center",
        fontsize=9.5,
        color=INK_PRIMARY,
    )
ax.set_xlabel("Median PR description length (words)")
ax.set_title(
    "Figure 6. Description length by agent",
    loc="left",
    fontsize=12,
    fontweight="bold",
    color=INK_PRIMARY,
)
ax.xaxis.grid(True, color=GRID, linewidth=1)
ax.set_axisbelow(True)
style_ax(ax)
fig.tight_layout()
fig.savefig(OUT_DIR / "fig6_description_length_by_agent.png")
plt.close(fig)

print(f"Saved 6 figures to {OUT_DIR}")

# =========================================================== findings.md ===
lines = []


def fmt_hours(h):
    return f"{h/24:.1f}d" if h >= 24 else f"{h:.1f}h"


lines.append("# Phase 0 — PR250 Dataset Summary\n")
lines.append(
    f"Descriptive summary of `data/04_pr250 - 04_pr250.csv`: "
    f"**{n} closed pull requests** authored by {len(agent_counts)} "
    f"autonomous coding agents across **{unique_repos} repositories** "
    f"and {unique_users} distinct authors. Figures generated by "
    f"`src/phase0/generate_phase0_figures.py`.\n"
)

lines.append("## Headline numbers\n")
lines.append(f"- Total PRs: **{n}**")
lines.append(
    f"- Unique repositories: **{unique_repos}** "
    f"(avg {n/unique_repos:.2f} PRs/repo)"
)
lines.append(f"- Unique authors: **{unique_users}**")
lines.append(
    f"- Coding agents: **{len(agent_counts)}** "
    f"({', '.join(AGENT_LABEL[a] for a in agents)})"
)
lines.append(
    "- Date range: "
    f"**{min(r['_created'] for r in rows if r['_created']):%Y-%m-%d}** "
    f"to **{max(r['_created'] for r in rows if r['_created']):%Y-%m-%d}**"
)
lines.append(
    f"- Closed without merge: **{n - merged_count} / {n} "
    f"({(n-merged_count)/n*100:.0f}%)**"
)
lines.append(
    f"- Repos with >1 agent represented: "
    f"**{multi_agent_repos} / {unique_repos}**\n"
)

lines.append("## Agent mix (Figure 1)\n")
lines.append("| Agent | PRs | Share |")
lines.append("|---|---|---|")
for a in agents:
    lines.append(
        f"| {AGENT_LABEL[a]} | {agent_counts[a]} | "
        f"{agent_counts[a]/n*100:.1f}% |"
    )
lines.append("")

lines.append("## Submission volume over time (Figure 2)\n")
lines.append(
    "Devin is the only agent present before May 2025. Copilot, OpenAI "
    "Codex and Cursor enter the sample from May 2025 onward; monthly "
    "volume roughly triples between April and June 2025, then eases "
    "slightly in July."
)
lines.append("")

lines.append("## Rejection-reason codes (Figure 3)\n")
lines.append(
    f"`manual_label` has **{len(label_counts)} distinct numeric codes**, "
    f"all populated (0 missing). The top 5 codes "
    f"({', '.join('Code ' + k for k, _ in label_counts[:5])}) account "
    f"for {sum(v for _, v in label_counts[:5])/n*100:.0f}% of PRs; "
    f"the remaining {len(label_counts)-5} codes are long-tail."
)
lines.append(
    "**Caveat:** `writing/Codebook.md` defines the qualitative rejection "
    "themes (Build Failure, CI Fail, Agent Draft, Unresolved Merge State, "
    "Incomplete Solution, Did Not Follow Instructions, Unrequested "
    "Changes, Infinite Loops, Tool Call Failures) but does not yet "
    "publish a code-number legend for all values — numeric codes are "
    "reported as-is.\n"
)

lines.append("## Repositories (Figure 4)\n")
lines.append(
    f"250 PRs span {unique_repos} repositories. `crewAIInc/crewAI` is "
    f"the single largest source ({repo_counts[0][1]} PRs), followed by "
    f"`airbytehq/airbyte` ({repo_counts[1][1]}). Only {multi_agent_repos} "
    f"repositories contain PRs from more than one agent — agent "
    f"assignment is almost entirely repo-exclusive in this sample."
)
lines.append("")

lines.append("## PR lifecycle duration (Figure 5)\n")
d = duration_summary
lines.append(
    f"Hours from `created_at` to `closed_at` are heavily right-skewed "
    f"(n={d['n']}): min {d['min']:.1f}h, p25 {d['p25']:.1f}h, "
    f"median {d['median']:.1f}h, p75 {d['p75']:.1f}h, "
    f"p90 {d['p90']:.1f}h, max {d['max']:.1f}h "
    f"(mean {d['mean']:.1f}h, pulled up by the tail)."
)
lines.append("")
lines.append("| Agent | n | Median close time | Mean close time |")
lines.append("|---|---|---|---|")
for a in agents:
    dur = agent_duration[a]
    med = st.median(dur)
    mean = st.mean(dur)
    lines.append(
        f"| {AGENT_LABEL[a]} | {len(dur)} | {fmt_hours(med)} | "
        f"{fmt_hours(mean)} |"
    )
lines.append("")
lines.append(
    "OpenAI Codex closes fastest (median "
    f"{st.median(agent_duration['OpenAI_Codex']):.1f}h); Devin is "
    f"slowest (median {st.median(agent_duration['Devin']):.1f}h ≈ "
    f"{st.median(agent_duration['Devin'])/24:.1f} days).\n"
)

lines.append("## Description length (Figure 6)\n")
lines.append(
    "Copilot PRs carry the longest descriptions (median "
    f"{st.median(agent_body['Copilot']):.0f} words), OpenAI Codex the "
    f"shortest (median {st.median(agent_body['OpenAI_Codex']):.0f} "
    f"words). {empty_body} PRs ({empty_body/n*100:.1f}%) have an "
    f"empty body.\n"
)

lines.append("## Data quality notes\n")
lines.append(
    '- `merged_at` is empty for all 250 rows and `state` is "closed" '
    "for all rows — consistent with the sample being deliberately "
    "curated to closed, non-merged agent PRs for rejection-reason "
    "coding, not a random PR sample.\n"
    "- `id` is unique across all rows; `(repo_id, number)` is also "
    "unique — one row per PR, no duplicates.\n"
    f"- `body` is empty for {empty_body} rows "
    f"({empty_body/n*100:.1f}%).\n"
)

lines.append("## Figures\n")
lines.append("| File | Description |")
lines.append("|---|---|")
lines.append("| `fig1_agent_distribution.png` | PR count by coding agent |")
lines.append(
    "| `fig2_monthly_volume_by_agent.png` | Monthly PR volume, "
    "stacked by agent |"
)
lines.append(
    "| `fig3_rejection_label_distribution.png` | `manual_label` code "
    "frequency (top 10 + other) |"
)
lines.append(
    "| `fig4_top_repositories.png` | Top 12 repositories by PR count |"
)
lines.append(
    "| `fig5_duration_distribution.png` | Close-time histogram + "
    "median close time by agent |"
)
lines.append(
    "| `fig6_description_length_by_agent.png` | Median PR description "
    "length by agent |"
)

(OUT_DIR / "findings.md").write_text("\n".join(lines), encoding="utf-8")
print(f"Saved findings.md to {OUT_DIR}")
