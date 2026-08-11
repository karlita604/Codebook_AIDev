# Timeline

Dated milestones only — headline outcomes, not the debugging narrative. Full
detail (bugs, blockers, dead ends, exact numbers) lives in
`ProjectUpdate.md`'s matching dated entry; this doc just makes "what
happened, in order" a 30-second read. Phase/tool names follow `PHASES.md`'s
current terms even where `ProjectUpdate.md`'s own entries use the older
"Phase A/B" labels (that file is a verbatim historical record, not rewritten).

| Date | Milestone |
|---|---|
| 2026-07-21 | Methodology designed (`Longitudinal.md`, interrupted time series, A1/A2/B1/B2 tracks). Phase 1a done: 5-repo pilot selected (crewAI, airbyte, mlflow, Dock, aspire). Phase 1c done: 480-row snapshot manifest, 5 repos cloned. Phase 1e done: 399/401 unique commits materialized. Phase 1d built but blocked — DPy/Designite not yet installed. |
| 2026-07-27 | DPy + Designite installed. Two new blockers found: DPy's Trial license caps CSV export at <10,000 LOC/invocation; Designite requires a real `.sln`, which materialized snapshots didn't have yet. Chunking wrapper built for DPy; cost measured at ~29 hours of DPy runtime for `mlflow` alone. Decision: run the full manifest as a multi-day background job anyway; pipeline made crash-resilient (incremental writes, resumable, chunk cleanup). |
| 2026-07-28 | DPy background run hit and recovered from: a silent-death/resume bug, then a Windows Smart App Control incident that blocked `DPy.exe` outright (user disabled SAC directly). Parallelized to 3 workers. Separately: Track B1/B2 PR sampling completed, 212/265 query units ok — every failure was `dotnet/aspire` (Microsoft's org blocks fine-grained PATs). Decision: Dock becomes the sole C# repo for Track B. |
| 2026-07-29 | DPy run finished: 264 unique ok rows (crewAI 72/74, airbyte 96/96, mlflow 96/96). In parallel, on the `designite-sln-support` branch: Designite unblocked, Dock gets real structural data (87/96 rows); `dotnet/aspire` dropped from the C# arm entirely (no clean commit range works). **First real analysis run** — segmented regression (RQ1), composition shift (RQ2), process metrics (RQ3) — see `Results.md`, dashboard linked there. N=4 pilot, explicitly preliminary. |
| 2026-08-04 | `designite-sln-support` merged into `main` — Dock's data and the pilot's Python data now live in one checkout. **Phase 2 kickoff**: decision to collect raw snapshots/PR samples for a 20-repo minimum using the existing pipeline, but *defer* Phase 1d (DPy/Designite) for the new repos — the trial-license LOC caps don't scale. `InHouseTooling.md` and `RQ3_CodeTracking.md` added as brainstorm docs, the trigger for building an in-house replacement. |
| 2026-08-10 | **Phase 2 raw collection essentially done**: 21-repo manifest (1673/2016 grid points resolved), 4990-row PR sample, 20/21 repos materialized (`julep-ai/julep` pending). **Tool-Py built and validated** (Python OO metrics, stdlib `ast`, no LOC cap) — validated against the pilot's real DPy output; surfaced a finding that DPy's own airbyte numbers look undercounted (chunking artifact, not a convention difference). |
| 2026-08-11 | **Tool-CS built and validated** (C# via Roslyn, syntax-only — no `.sln`/`MSBuildWorkspace` load). Two unplanned wins: `dotnet/aspire` gets real structural data for the first time ever (75/75 rows), and Dock's post-`.slnx`-migration months are no longer censored (96/96 vs. Designite's 87/96). Also found: Dock's local `repo_cache` clone is stale, so the *latest* snapshot manifest under-resolves Dock's commit diversity — worked around for this validation, not yet fixed. |
| 2026-08-11 (later) | **Tool-CS scaled to every C# repo in the Phase 2 manifest** — the remaining 5 (`dotnet/maui`, `dotnet/aspnetcore`, `elsa-workflows/elsa-core`, `microsoft/testfx`, `wieslawsoltes/Svg.Skia`) all analyzed after materializing their previously-empty snapshots; **all 7 C# repos now have full structural data, 651 rows, 100% `ok`**. Along the way, cleaned up 94 leftover bad-manifest rows that had been sitting in Dock's output files uncaught. |
| 2026-08-11 (separate branch) | **Tool-RQ3 (the RQ3 entity/snippet lifetime tracker) built through Stage 5 of 6**, on a new branch (`rq3-entity-tracker`, `Codebook_AIDev-rq3` worktree, off `main` — not yet merged). Stages 1-4 (matcher, metrics, validation gate, Python+C# extraction) are built *and validated*: Stage 3's gate found a real true-positive rename (0.933 similarity) and a real false-merge case (a class split in two, misattributed only below the design's actual 0.75 threshold), validating the matcher's threshold with evidence rather than assumption; Stage 4 (C#) cross-checked exactly against already-validated Tool-CS ground truth (208 classes/584 methods, exact match). Stage 5's orchestrator is built and a 21-repo Phase 2 run was in progress as of this entry — not yet complete, not yet validated. See `Writing/RQ3_CodeTracking.md`'s build log and `Writing/PHASES.md` for the full detail. |

## What's next (not yet on this timeline)

Per `ProjectStatus.md` §7: Tool-Viz (time-series/correlation figures) isn't
built; Tool-RQ3's Stage 5 run (21-repo Phase 2 scale-up) needs to finish
and Stage 6 (windowed pre/post cut) hasn't started, and none of Tool-RQ3
is merged into `main` yet regardless; Tool-Py hasn't been run against the
10 non-pilot Phase 2 Python repos; the pilot's first analysis hasn't been
re-run against the now-available in-house Dock/aspire data; Dock's stale
clone isn't fixed; Track B's deeper PR-diff stats aren't built; no
multiple-comparison correction or matched non-adopting comparison arm
exists yet. Also in flight on its own separate branch, not reflected in
detail here: Python-side smell detection (`python-smell-detection`
branch). This is the honest "still open" list, not a promise of order.
