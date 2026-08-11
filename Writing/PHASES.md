# Naming crosswalk — every "phase"/"track" term this project uses

This project accumulated three separate, legitimately-orthogonal naming
schemes over ~3 weeks of work, plus a couple of real collisions where the
same word means different things in different files. Nothing here changes
what was built or found — it's a map so a new reader (or a future session)
doesn't have to reconstruct this by grepping. When in doubt, this doc is the
canonical source; if another doc disagrees with it, this one wins and the
other should be fixed.

## Scheme 1 — the data pipeline (Phase 0 → 1a–1e → 2)

The main sequence, one step feeding the next. Canonical definition:
`Longitudinal.md`. Used consistently in `src/phase0/*.py`.

| Phase | What it does | Built in | Status |
|---|---|---|---|
| **0** | Candidate repo/PR filtering from the AIDev dataset | `src/phase0/PRfilter.py` | Done, iterating in background |
| **1a** | Repo & PR picking — per-repo agent-PR summary, intervention date | `src/phase0/repo_pr_selection.py` | Done |
| **1b** | Track B1/B2 PR sampling (process metrics) | `src/phase0/pr_sampling_pipeline.py` | Done for pilot + Phase 2 |
| **1c** | Snapshot manifest — which commit per A1/A2 grid point | `src/phase0/repo_snapshot_pipeline.py` | Done |
| **1d** | Structural-metric orchestration (DPy + Designite) | `src/phase0/long_analysis.py` | Done for the 4-repo pilot; deferred for Phase 2's new repos (see Scheme 3) |
| **1e** | Snapshot materialization — source trees on disk | `src/phase0/materialize_snapshots.py` | Done |
| **2** | Scale the pilot's 4 repos to a 20-repo minimum | Phase 1a/1b/1c/1e re-run at scale | Raw collection essentially done; Phase 1d deferred for the new repos |

Current status of each: `ProjectStatus.md`'s "Where each piece stands" table.

## Scheme 2 — sampling tracks (A1 / A2 / B1 / B2)

Orthogonal to Scheme 1 — these describe *what's sampled* and *how the grid is
anchored*, not a sequence of steps. They live *inside* Phases 1c/1e (A-tracks)
and 1b (B-tracks). Canonical definition: `Longitudinal.md` §5.

| Track | Samples | Anchor |
|---|---|---|
| **A1** | Repo source-tree snapshot | Fixed calendar grid, 2022-01–2026-03, monthly |
| **A2** | Repo source-tree snapshot | Centered on each repo's own intervention date (weekly ±3mo, monthly to ±12mo) |
| **B1** | PR events | Fixed calendar grid, monthly 2-day window |
| **B2** | PR events | Centered on the intervention PR (±10 PRs) |

## Scheme 3 — the in-house metrics tool (Tool-Py / Tool-CS / Tool-Viz / Tool-RQ3)

**Renamed in this pass from "Phase A/B/C/D."** That lettering collided head-on
with Scheme 1's "Phase 1d" and "Phase 2" for anyone reading quickly — "Phase B"
and "Phase 2" sound related and aren't. New names below are used going
forward in `ProjectStatus.md` and `src/inhouse/*`. Canonical definition:
`Writing/InHouseTooling.md`, `Writing/RQ3_CodeTracking.md`.

| New name | Old name | What it is | Status |
|---|---|---|---|
| **Tool-Py** | Phase A | Python OO metrics, stdlib `ast`, no LOC cap | Built and validated 2026-08-10; pilot-only coverage (3 repos) |
| **Tool-CS** | Phase B | C# OO metrics, Roslyn `CSharpSyntaxTree.ParseText`, no `.sln`/`MSBuildWorkspace` load | Built and validated 2026-08-11; scaled to all 7 Phase 2 C# repos same day |
| **Tool-Viz** | Phase C | Time-series + pre/post correlation-matrix visualization | Scoped, not built |
| **Tool-RQ3** | Phase D | RQ3 entity/snippet lifetime tracker | **In progress, not yet merged.** Stages 1-4 of 6 (matcher, metrics, validation gate, Python+C# extraction) built and validated; Stage 5 (scale to the full pilot + Phase 2) built and running — a 21-repo pass was in progress as of this writing, not yet complete. Stage 6 (windowed pre/post cut) not started. All on `rq3-entity-tracker` branch (`Codebook_AIDev-rq3` worktree, off `main`, commit `464c8cd9a`), not `main` itself. See `Writing/RQ3_CodeTracking.md`'s build log |

**Historical note**: `ProjectUpdate.md`'s dated log entries (2026-08-10,
2026-08-11) still say "Phase A"/"Phase B" — that file is an append-only,
verbatim historical record by its own stated convention (see its intro), so
those entries weren't rewritten. Same for `Results.md`'s two "In-house tool
validation — Phase A / Phase B" sections — read "Phase A" = Tool-Py and
"Phase B" = Tool-CS wherever you see it in either of those two files.

## Real collisions found and fixed

- **`src/phase0/metrics.py`'s docstring called its own second internal step
  "Phase 2"**, and `src/phase0/phase1.py`'s docstring called that same step
  "Phase 1.5" — neither has anything to do with Scheme 1's "Phase 2" (20-repo
  scaling) or a real "Phase 1.5." Both files' own two-step process (Step 1 =
  `phase1.py` compiling PR metadata, Step 2 = `metrics.py` computing metric
  columns on top) is now relabeled "Step 1"/"Step 2" in both docstrings, with
  a note pointing here.
- **`Writing/Phase0-data.md` separately called that same file "Phase 1.5."**
  That doc is now archived (`Writing/archive/Phase0-data.md`) as a superseded
  early draft — its own internal terminology wasn't otherwise touched, since
  it's kept as a historical artifact, not a live reference.

## Known, deliberately-unfixed wart

`results/phase0/` (the folder) holds both Phase 0 *and* Phase 1 output
(`07-20-...csv` from `PRfilter.py`, and `phase1_...csv` from `phase1.py`) —
the folder name only names Phase 0. Not renamed in this pass: several scripts
hardcode this path as a default input (`src/phase0/phase1.py`'s
`DEFAULT_INPUT`, `Writing/archive/Phase0-data.md`'s documented default), and a
folder rename is a real risk to reproducing past runs for no methodological
benefit. If this bothers a future reader, it's a naming label, not a data
problem — everything in `results/phase0/` is exactly what its filename says.

## Parked, not stale

`Writing/Codebook.md` (PR-rejection reason-code table) and
`src/rejection_analysis.py` (a 3-line stub) are an unfinished pair — not
superseded by anything else, just not picked back up. Left in place, not
archived; tracked as an open item in `ProjectStatus.md`.
