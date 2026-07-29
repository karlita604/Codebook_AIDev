# Designite `.sln` support — status & decision log

Started as a task brief; now tracking what's actually been decided,
confirmed, and still open, since the original blocker is resolved. For the
full narrative (including dated updates), see `Writing/Longitudinal.md` §8
"Phase 1d" and "Open decisions" — this file is the condensed, current-state
version.

## Context

This repo runs a longitudinal study measuring repo structural-health changes
before vs. after AI coding agents start contributing, on pilot repos: 3
Python (crewAI, airbyte, mlflow — analyzed with DPy) and, for this pilot
phase, 1 C# repo (Dock — analyzed with Designite; aspire dropped, see
below). Phase 1c/1e produced a snapshot manifest and materialized per-commit
source trees at `data/snapshots/<owner>__<repo>/<commit_sha>/` (via
`src/phase0/materialize_snapshots.py`, using `git archive` filtered by
language). Phase 1d (`src/phase0/long_analysis.py`) runs DPy/Designite
against those trees and pools the results into one metrics table.

DPy's side runs a real, multi-day background batch job **on `main`, in the
primary checkout** (`C:\Users\kvrlv\Projects\Codebook_AIDev`) — do not touch
that checkout, its `long_analysis.py`, or its running process (PID in
`logs/phase0/long_analysis.pid` there) from this branch. This worktree/branch
(`Codebook_AIDev-designite`, branch `designite-sln-support`) exists so
C#/Designite work can proceed in parallel without any risk of interfering
with it.

## Status: working end-to-end for Dock

`run_designite()`/`parse_tool_output()` in `src/phase0/long_analysis.py` are
implemented and confirmed against real `wieslawsoltes/Dock` commits — both a
small one that fits in a single Designite invocation and a large one that
needs chunking. **Full unattended batch run across every Dock manifest row
completed 2026-07-28: 87/96 rows ok, 9 failed (all 9 the known `.slnx` gap,
nothing unexpected)** — see "Collection run log" below for the full
breakdown. This is real, usable output, not a smoke test.

## Metrics collected

One row per manifest grid point (`repo_id`, `full_name`, `language`, `track`,
`target_date`, `commit_sha`), keyed the same way as the DPy output so the two
can eventually sit in one pooled table. `status` is `ok`/an error string per
row; failed rows land in the separate errors CSV instead (see
`long_analysis.py` module docstring). All of the below come from
`_parse_designite_output()`, derived directly from Designite's own per-project
CSVs (`ClassMetrics`, `MethodMetrics`, `DesignSmells`, `ImpSmells`,
`TestabilitySmells`, `TestSmells`, `ArchSmells`) — not from its
`AnalysisSummary.csv`, to keep the derivation consistent with how the DPy side
computes its own totals.

| Column | Meaning | Caveat |
|---|---|---|
| `total_loc` | Sum of `ClassMetrics.LOC` across every class in the solution | Undercounts Designite's own top-line LOC figure by ~18-21% (confirmed on 2 commits) - lines not attributed to any class (usings, namespace boilerplate) aren't counted. Same category of imprecision as DPy's own LOC proxy. |
| `n_chunks` | How many sub-cap chunks this commit needed | 1 = whole solution fit under the Trial cap in one invocation |
| `n_classes` | Count of `ClassMetrics` rows | Confirmed exact vs. Designite's own console-reported class count, chunked or not |
| `n_methods` | Count of `MethodMetrics` rows | Confirmed exact vs. Designite's own console-reported method count, chunked or not |
| `class_loc_p50` / `class_loc_p90` | Median / 90th-percentile class LOC | — |
| `method_loc_p50` / `method_loc_p90` | Median / 90th-percentile method LOC | — |
| `cyclomatic_complexity_p50` / `_p90` | Median / 90th-percentile per-method cyclomatic complexity (`MethodMetrics.CC`) | — |
| `design_smell_count` / `design_smell_density_per_kloc` | Count and density of design smells (`DesignSmells.csv`) | — |
| `implementation_smell_count` / `implementation_smell_density_per_kloc` | Count and density of implementation smells (`ImpSmells.csv`) | — |
| `testability_smell_count` | Count of testability smells (`TestabilitySmells.csv`) | Designite-only category, no DPy equivalent |
| `test_smell_count` | Count of test-code smells (`TestSmells.csv`) | Designite-only category, no DPy equivalent |
| `arch_smell_count_chunk_scoped` | Count of architecture smells (`ArchSmells.csv`) | **Not a repo-level measurement when `n_chunks > 1`** - each chunk only sees its own slice of projects, so Fan-In/Fan-Out and any smell depending on an excluded project's types are invalid across a chunk boundary. Same shape of caveat as DPy's own chunk-scoped architecture smells. |

Not currently pooled into the row, but collected and available per-chunk in
the raw CSVs if `--keep-tool-output` is passed: `NamespaceMetrics.csv`
(afferent/efferent coupling at namespace level), per-class `Fan-In`/`Fan-Out`
(in `ClassMetrics.csv`), and `Designite_AnalysisSummary.csv` itself.

**Known unresolved skew**: multi-targeted projects (a project built for more
than one target framework/configuration) produce a full duplicate set of
per-project CSVs per variant, which are currently all pooled together rather
than deduplicated - see "Known gaps" below.

## Collection run log

- **2026-07-28**: full materialization + analysis run for `wieslawsoltes/Dock`
  (64 unique commits, 96 manifest rows across the A1/A2 grid).
  `DESIGNITE_EXECUTABLE` set to the installed trial build.
  - Materialization: **61/61 not-yet-materialized commits archived, 0
    failed** (3 were already done from earlier manual testing).
  - Analysis: **87/96 rows ok, 9 failed** → `results/analysis/07-28-smell-metrics-96.csv`
    (+ matching `-errors.csv`, `-progress.json`). All 9 failures are the known
    `.slnx` gap (every Dock commit dated 2026-01-01 or later) - no
    unexpected errors.
  - **17 of the 87 ok rows needed chunking** (`n_chunks == 2`) - the LOC-cap
    wrapper handled every one of them without incident.
  - This is real, usable per-commit structural-metric data for Dock across
    2022-01 through 2025-12 - not a smoke test. Ready to feed into the
    pooled cross-repo table alongside DPy's Python-side output whenever
    that's assembled.

## Decisions made

1. **`.NET SDK 8.0.423` installed** (this machine previously had runtimes
   only, 6.0.32/8.0.22). Confirmed necessary — `DesigniteConsole.exe` with no
   args explicitly warned about a missing SDK beforehand; that warning is
   gone post-install, and `.sln` loading now works.

2. **`materialize_snapshots.py`'s C# pathspec extended** from `*.cs`-only to
   `*.cs, *.sln, *.slnx, *.csproj, *.props, *.targets, packages.config`
   (`LANGUAGE_PATHSPEC["C#"]`). Needed so Designite's Roslyn `MSBuildWorkspace`
   has an actual project graph to open, not just source files.

3. **Two real bugs found and fixed in `archive_commit()`/`_present_patterns()`**
   while extending the pathspec (both generalizable, not Dock- or
   aspire-specific):
   - `git archive` (unlike `ls-tree`) hard-fails (exit 128) if *any* given
     pathspec pattern matches zero files in that commit's tree — there's no
     `--ignore-unmatch` for `archive`. A fixed multi-extension pathspec was
     guaranteed to hit this per-commit (e.g. Dock has no `.sln` at all after
     its `.slnx` migration, see #5below). Fixed by pre-filtering the pathspec
     to patterns that actually match something in that specific commit
     before archiving.
   - That filter itself first got this wrong by checking basenames: git's
     own literal (non-wildcard) pathspec matching (e.g. `packages.config`)
     is a top-level-path match, not a basename match at any depth. Caught on
     aspire's `eng/common/sdl/packages.config` — a basename check wrongly
     kept that pattern, and `git archive` itself then rejected it anyway.
     Fixed to match against full relative paths.

4. **Designite's Trial cap confirmed: <50,000 LOC per invocation**, a
   solution-wide total (not per-project) — stated explicitly in the tool's
   own message text, unlike DPy's cap which had to be bisected empirically.
   A 58,243-LOC full-solution run computed everything (namespaces, classes,
   smells) but wrote zero CSVs; a 13,065-LOC one exported fully.

5. **`dotnet/aspire` dropped from the C# analysis arm for this pilot phase**
   (decision made 2026-07-28, see `Writing/Longitudinal.md` for the full
   investigation). Two *different*, unrelated blockers depending on era:
   - Early commits (2023, pre-1.0): `.sln` opens without crashing, but every
     project reports zero source files. Root cause confirmed via `dotnet
     restore`: aspire bootstraps via Arcade (`global.json` pins a prerelease
     SDK + `Microsoft.DotNet.Arcade.Sdk`), needing its own
     `restore.cmd`/private feed setup, not a plain restore/`MSBuildWorkspace`
     open.
   - Recent commits (2026): use `.slnx` (see #6) *and* pin .NET SDK 10.0.201
     preview, not installed, fetched by the repo's own local-install script.
   - No confirmed "clean middle band" of aspire history was found (not
     exhaustively searched). Mechanism: `EXCLUDED_REPOS` in
     `materialize_snapshots.py` (imported by `long_analysis.py`), applied
     generically so any future repo needing the same treatment has somewhere
     to go. Aspire's exploration artifacts (materialized snapshots, test
     Designite output) archived at `data/archive/dotnet__aspire_2026-07-28/`
     rather than deleted.

6. **This installed DesigniteConsole build (5.3.0.0) does not support
   `.slnx`** (the newer XML solution format) — confirmed directly ("could
   not find any project to analyze"). Dock itself migrated `Dock.sln` →
   `Dock.slnx` on 2025-12-25 (`b8fb130d`), so **Dock commits after that date
   are currently unanalyzable** too, same as aspire's recent history. Handled
   in `run_designite()` by raising a distinguishable `NotImplementedError`
   (not the generic `FileNotFoundError` used for a genuinely missing/corrupt
   snapshot) so it's logged as a known gap, not confused with a real failure.

7. **Chunking design for the LOC cap** (`plan_designite_chunks()` /
   `_write_sub_solution()` / `run_designite()` in `long_analysis.py`):
   unlike DPy, Designite analyzes at solution/project granularity, not a raw
   source directory, so a chunk can't split a single project's files —
   confirmed empirically before designing this:
   - Built a real sub-solution (via `dotnet new sln` + `dotnet sln add`,
     not hand-rolled `.sln` text) containing only `Dock.Avalonia.csproj`,
     excluding five projects it references via `ProjectReference`.
     Designite reported ~7,884 LOC — matching Dock.Avalonia's own size
     alone, **not** the ~20,000 LOC that would include its dependencies'
     source. Confirms `MSBuildWorkspace` only loads what's explicitly listed
     in the `.sln`, not the transitive reference closure.
   - Checked the resulting `ClassMetrics.csv` for Fan-Out entries pointing at
     the excluded `Dock.Model` project's types: none appeared. So excluding
     a referenced project doesn't crash or inflate LOC, it just leaves that
     cross-reference unresolved.
   - **Chosen design**: bin-pack whole projects (in `.sln` file order, for
     determinism) into groups under `DESIGNITE_LOC_CAP` (45,000 — headroom
     under the confirmed 50,000 cap, same reasoning as `DPY_LOC_CAP`'s
     headroom), *without* trying to keep a project's reference closure
     together in one chunk. This reuses DPy's already-established caveat
     philosophy rather than inventing a new one: Fan-In/Fan-Out and any
     smell depending on an excluded project's types are **not valid** for
     that chunk (same shape as DPy's chunk-scoped architecture smells) —
     `parse_tool_output()` collects `ArchSmells.csv` rows but keeps them
     under `arch_smell_count_chunk_scoped`, never pooled as repo-wide, same
     as DPy's `arch_smell_count_chunk_scoped`.
   - Confirmed on a real 58,243-LOC Dock commit: planned into 2 chunks (44K +
     17K LOC), both exported successfully, and the pooled `n_classes`/
     `n_methods` (832/2908) exactly matched the un-chunked console summary
     from before chunking existed — chunking doesn't lose or duplicate
     entities, only cross-chunk relationship data.
   - **A real gotcha found along the way**: `DesigniteConsole.exe` exits `0`
     unconditionally, even when the Trial cap silently blocks CSV export.
     `_run_designite_once()` cannot rely on the exit code alone — it
     explicitly checks that CSVs were actually written afterward and raises
     if not (this would mean our LOC proxy underestimated a chunk that's
     still over the real cap, not a normal crash).

8. **Designite's CSV output schema confirmed directly** (not guessed) — see
   `parse_tool_output()`'s docstring in `long_analysis.py` for the full
   column list. Shape is materially different from DPy's: one full set of 8
   CSVs (`ClassMetrics`, `MethodMetrics`, `NamespaceMetrics`, `DesignSmells`,
   `ImpSmells`, `ArchSmells`, `TestabilitySmells`, `TestSmells`) *per project*
   in the solution (or sub-solution, when chunked), plus one
   `Designite_AnalysisSummary.csv`. `TestabilitySmells`/`TestSmells` have no
   DPy equivalent and are pooled as their own new columns
   (`testability_smell_count`, `test_smell_count`) rather than folded into
   existing design/implementation smell counts.

## Known gaps / open items — not yet resolved

- **Multi-targeted projects are not deduplicated.** A project built for more
  than one target framework/configuration produces a separate full CSV set
  per variant, with the variant suffixed onto the project name (confirmed:
  one project produced `AvaloniaDemo`, `AvaloniaDemo.Debug`,
  `AvaloniaDemo.Perspectives`, `AvaloniaDemo.Xaml` as four separate entries
  in one run). `parse_tool_output()` currently pools all of them, meaning
  such a project's classes/methods get counted once per variant. Needs a
  decision (keep one canonical variant? sum? something else?) before this
  is used for anything where that skew matters.
- **`total_loc` (derived by summing `ClassMetrics.LOC`) undercounts vs.
  Designite's own top-line "Total lines of code" figure** — confirmed on two
  commits (47,667 vs. 58,243 reported; 10,366 vs. 13,065 reported, both
  ~18-21% lower). Same category of imprecision as DPy's naive-`readlines()`
  vs. DPy's-own-count gap, not investigated further — likely Designite
  counting non-class-body lines (usings, namespace boilerplate) that
  `ClassMetrics.csv` doesn't attribute to any class.
- **`.slnx` unsupported**, blocking Dock commits after 2025-12-25 (and all of
  aspire's recent history). Options not yet decided: find/install a newer
  Designite build with `.slnx` support, or convert `.slnx` back to `.sln`
  before analysis (tooling availability unconfirmed).
- **aspire scope** — dropped for this pilot phase, not permanently. Revisit
  only if the study later needs a second C# repo (see
  `Writing/Longitudinal.md` for the options considered: full Arcade
  bootstrap replication, hunting for a clean middle band of aspire history,
  or swapping in a different C# pilot repo).
- **Generalization to "any C# repo on request" is explicitly deferred.** The
  mechanisms built so far (pathspec presence-filtering, `.sln` project
  parsing, chunk planning) are written repo-agnostically already, but they've
  only been exercised against Dock. Repos with their own Arcade-style
  bootstrap requirements (like aspire) aren't handled by anything here yet.
- **Full unattended batch run across all Dock manifest rows** not yet done
  (in progress as of this writing) — expect some rows to fail because of the
  `.slnx` gap above, to be logged to the errors CSV per existing convention,
  not silently skipped.

## Working environment for this task

Separate git worktree (`Codebook_AIDev-designite`, branch
`designite-sln-support`) off a clean `main`, so it doesn't interfere with the
Phase 1d DPy job running there. `data/repo_cache` is an NTFS junction to the
main checkout's (`mklink /J data\repo_cache C:\Users\kvrlv\Projects\Codebook_AIDev\data\repo_cache`)
rather than a fresh clone — no admin rights needed, and avoids re-cloning
Dock/aspire.

To re-run Designite manually against a materialized snapshot:
```
export DESIGNITE_EXECUTABLE="/c/Users/kvrlv/Downloads/DesigniteConsole/DesigniteConsole/DesigniteConsole.exe"
python src/phase0/long_analysis.py --repo Dock
```

## Relevant files

- `src/phase0/materialize_snapshots.py` — Phase 1e, snapshot materialization;
  see `LANGUAGE_PATHSPEC`, `EXCLUDED_REPOS`, `_present_patterns()`
- `src/phase0/long_analysis.py` — Phase 1d; see `run_designite()`,
  `plan_designite_chunks()`, `_write_sub_solution()`, `parse_tool_output()`
- `Writing/Longitudinal.md` — full methodology + dated decision log (search
  "Designite")
- `data/archive/dotnet__aspire_2026-07-28/` — archived aspire exploration
  artifacts + README explaining the two blockers found
