# Codebook_AIDev

A longitudinal study measuring how repository structural health (design/
implementation smells, OO metrics) and PR-level process change around the
point where AI coding agents start contributing to a repo — using an
interrupted time series, not a naive before/after, so ordinary codebase
drift doesn't get mistaken for an agent effect.

## Start here

- **[`Writing/ProjectStatus.md`](Writing/ProjectStatus.md)** — current state, in one read: what's done, what's in progress, what's still open.
- **[`Writing/PHASES.md`](Writing/PHASES.md)** — naming crosswalk. This project has three overlapping "phase" schemes (data pipeline, sampling tracks, in-house tool build stages); this doc reconciles them.
- **[`Writing/TIMELINE.md`](Writing/TIMELINE.md)** — dated milestones, 2026-07-21 to present, in one table.
- **[`Writing/Results.md`](Writing/Results.md)** — findings, tables, and the interactive dashboard. Read its banner first — it's a running log, not a final report.
- **[`Writing/ProjectUpdate.md`](Writing/ProjectUpdate.md)** — the full raw, append-only build log (every decision, bug, and blocker), for when `ProjectStatus.md`'s summary isn't enough detail.

## Layout

| Path | What's there |
|---|---|
| `src/phase0/` | Data pipeline: repo/PR filtering and selection, snapshot manifest + materialization, DPy/Designite orchestration (Phase 0-2, see `PHASES.md`) |
| `src/inhouse/` | In-house structural-metrics tool (Tool-Py, Tool-CS) — a from-scratch replacement for DPy/Designite with no license LOC cap |
| `src/repos/` | Repo-list utilities |
| `Writing/` | Methodology, status, results, and design-decision docs |
| `Writing/archive/` | Superseded early drafts, kept for historical reference |
| `results/` | Pipeline output (CSVs) — repo selection, snapshot manifests, PR samples, structural-metric analysis |
| `data/` | Local working data. Most subfolders (`repo_cache/`, `snapshots/`, `tool_output/`) are gitignored — populated by running the pipeline, not checked in |
| `references/` | Source papers for the lit review |

## Setup

```
pip install -r requirements.txt
```

Individual pipeline stages are documented in their own docstrings under
`src/phase0/` and `src/inhouse/`, and in `Writing/Longitudinal.md` §7-§8 for
the full pipeline design.
