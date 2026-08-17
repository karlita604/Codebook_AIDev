# In-house metrics tooling — brainstorm & comparison plan

**Status: brainstorm / planning, 2026-08-04. Nothing here is built yet.**
Written alongside the Phase 2 kickoff (`ProjectUpdate.md`'s 2026-08-04
entry) — the immediate trigger for writing this now is that Phase 2's ~16
new repos are being collected *without* running them through DPy/Designite,
specifically because this document's premise (that those tools' cost model
doesn't scale) is why that call was made.

## Why consider this at all

DPy and Designite (designite-tools.com) are the two tools this study uses
for structural/OO metrics and code smells — DPy for Python, Designite for
C#. Both worked, and both produced real, usable pilot data (see
`Results.md`, `DESIGNITE_TASK.md`). But three things about them are a real
constraint on scaling past a small pilot:

1. **Trial-license LOC caps force chunking, and chunking is expensive.**
   DPy's Trial cap is <10,000 LOC per invocation (confirmed empirically,
   `ProjectUpdate.md` 2026-07-27); Designite's is <50,000 LOC (stated
   directly by the tool). Every pilot repo is far over that, so
   `long_analysis.py` splits each snapshot into sub-cap chunks and runs the
   tool once per chunk. Measured cost: **one `mlflow` snapshot alone took
   304 chunks × ~3.4s ≈ 29 hours of DPy runtime**, and that's one snapshot
   out of dozens per repo. This is the direct cause of the multi-day
   background jobs and the Windows Smart App Control incident logged in
   `ProjectUpdate.md`.
2. **Closed smell catalogs limit reproducibility.** Neither tool documents
   its exact smell-detection heuristics publicly — `parse_tool_output()`'s
   schema had to be *confirmed empirically* against real output rather than
   read from documentation (see its docstring in `long_analysis.py`). For a
   dataset meant to be published, that's a real limitation: readers can't
   independently verify what "design smell" means without owning a license.
3. **Cost, at real Phase-2/Phase-3 scale.** Trial licenses are free but
   capped; removing the cap needs a paid license (DPy Professional,
   Designite's paid tier) per seat/machine, which doesn't obviously get
   cheaper as the repo count grows into the dozens.

None of this means DPy/Designite were a bad choice for the pilot — they
gave real, validated numbers fast, which is exactly what a pilot needs. The
question is what's worth building in-house *now that the pilot has proven
the study design works*, ahead of a much larger Phase 2/3 sample.

## What's actually being measured today (ground truth for comparison)

Pulled directly from `parse_tool_output()`'s confirmed schema in
`long_analysis.py` (both tools' output was verified against real runs, not
guessed):

| Category | DPy (Python) | Designite (C#) | Replicable in-house? |
|---|---|---|---|
| Size | `LOC` (class/module) | `LOC` (class) | **Easy** — line counting, same caveats either tool already has (both undercount vs. their own top-line totals by not attributing boilerplate lines to a class) |
| Class-level OO metrics | `WMC`, `NOM`, `NOPM`, `NOF`, `NOPF`, `LCOM`, `Fan-In`, `Fan-Out`, `DIT` | same set, plus `NC`, `NOP` | **Easy–Medium** — all are standard, well-published metrics (Chidamber & Kemerer's suite, mostly) computable from an AST/symbol table. Fan-In/Fan-Out and DIT need whole-project type resolution, not just per-file parsing — the harder end of "easy." |
| Method-level | `CC` (cyclomatic complexity), `PC` (param count), `LOC` | same | **Easy** — CC is a well-defined graph metric over a control-flow graph; both `radon`/`lizard` (Python) and Roslyn (C#) compute it already. |
| Design/Implementation/Architecture smells | `_design_smells.csv`, `_implementation_smells.csv`, `_arch_smells.csv` | `DesignSmells.csv`, `ImpSmells.csv`, `ArchSmells.csv` | **Hard** — these are the vendor's own heuristic rule catalogs, not published in a way that lets us reproduce the *exact same* smell for the *exact same* code. See below. |
| Testability / test-code smells | — (no DPy equivalent) | `TestabilitySmells.csv`, `TestSmells.csv` | **Hard**, same reason, and Designite-only to begin with (no DPy baseline to even compare against). |

## What's easy: OO metrics

Everything in the "size"/"class-level"/"method-level" rows above traces to
metrics with public, decades-old definitions (Chidamber & Kemerer 1994 for
WMC/DIT/LCOM/NOC; McCabe 1976 for cyclomatic complexity). Off-the-shelf
building blocks that already compute most of these:

- **Python**: `ast` (stdlib) for a from-scratch implementation with full
  control over exactly what's counted (useful for 1:1 comparison, see
  below); `radon` (CC, LOC, maintainability index) and `lizard`
  (cross-language CC/LOC/param-count) as existing libraries that already
  do most of the method-level work.
- **C#**: `Microsoft.CodeAnalysis` (Roslyn) — notably, **this is the same
  underlying engine Designite itself uses** (`DESIGNITE_TASK.md` confirms
  Designite is an `MSBuildWorkspace`-based Roslyn tool), so an in-house
  Roslyn-based analyzer is working from the same AST/symbol-resolution
  primitives Designite is, not a weaker substitute. `lizard` also has C#
  support for the simpler per-method metrics without needing a full
  Roslyn/MSBuild project load (which is what currently requires a real
  `.sln` and blocks repos like `dotnet/aspire` — see `DESIGNITE_TASK.md`
  §5 — a from-scratch tokenizer/lizard-style approach could sidestep that
  requirement entirely for whole-file metrics, at the cost of losing
  whole-project metrics like Fan-In/Fan-Out).

**No LOC cap** on any of these — they're just libraries we run ourselves,
which is the entire point.

## What's hard: smell detection

**Update 2026-08-11: this is no longer just future work — v1 is built and
partially validated for Python.** See "Smell detection: built and partially
validated (2026-08-11)" below and `PySmellDetection.md` for the full
build/validation log. The reasoning in this section is still why it was
scoped out of the first build pass, and still governs the approach taken.

Design/implementation/architecture smells are the harder half, and worth
being honest about *why* before committing to reproducing them:

- The exact rule for e.g. "Unnecessary Abstraction" or "God Component" is a
  specific threshold/heuristic choice by the tool vendor, not a single
  agreed-upon algorithm. Multiple published catalogs exist (Fowler's
  refactoring catalog, Lanza & Marinescu's *Object-Oriented Metrics in
  Practice*, Tufano et al.'s empirical smell studies) and they don't all
  define the same smell identically.
- Reproducing DPy/Designite's *specific* smell counts would require
  reverse-engineering their exact thresholds — not generally reproducible
  from a paper, and arguably not the right goal anyway (their thresholds
  aren't validated as "correct," just as what those specific tools do).
- The more defensible path for a published dataset is probably: **pick one
  or two well-documented smell definitions from the literature, implement
  those transparently and reproducibly ourselves, and report them as their
  own (differently-sourced) metric** — not attempt to match DPy/Designite's
  smell counts number-for-number. That changes the comparison framing (see
  below) from "does our tool agree with theirs" to "does our tool's smell
  signal move the same *direction* as theirs, on the same repos."

## Validation plan: use the pilot as ground truth

The pilot already produced real DPy/Designite output for known snapshots —
this is a genuine opportunity to validate against real data before trusting
an in-house tool on repos with no reference answer:

1. Build the OO-metrics half of the in-house tool first (the "easy" row
   above) — it has a clean 1:1 target to check against.
2. Run it against the **same already-materialized snapshots** the pilot
   used (`data/snapshots/<owner>__<repo>/<commit_sha>/`) — no need to
   re-clone or re-materialize anything.
3. Compare metric-by-metric against the real pilot output already on disk
   (`results/analysis/07-28-smell-metrics-96.csv` for Dock/Designite,
   `results/analysis/07-27-smell-metrics-437.csv` +
   `07-28-smell-metrics-{airbyteDock-192,crewAI-74,mlflowaspire-171}.csv`
   for DPy) — same `(repo_id, track, target_date, commit_sha)` keys already
   used to join everything else, so this is a straightforward join +
   correlation, not new data engineering.
4. For smells specifically: don't aim for exact-count agreement (see above)
   — instead check whether an in-house smell signal (once one is
   implemented) shows the same *before/after* pattern the pilot already
   found (e.g. Dock's implementation-smell density rising ~90%
   post-intervention, per `DockDesigniteReport.md`) — a direction/magnitude
   check, not a row-for-row match.
5. Once validated on the pilot, apply to Phase 2's already-collected raw
   snapshots (which exist specifically because Phase 1d was skipped for
   them, see `ProjectUpdate.md`'s 2026-08-04 entry) — this closes the loop
   the Phase 2 scope decision opened.

## Open questions / what would make this harder than expected

- **Whole-project resolution for C#.** Fan-In/Fan-Out/DIT need real
  cross-file type resolution, which either means a full Roslyn/MSBuild
  project load (same `.sln` requirement Designite already has, including
  its `dotnet/aspire`/`.slnx` blockers) or accepting a weaker
  file-local-only approximation for those specific metrics.
- **Multi-language growth.** If Phase 2/3 adds languages beyond Python/C#,
  an in-house tool needs per-language AST support each time — DPy/Designite
  don't cover other languages either, so this isn't a regression, but it's
  a real scope question for how far "in-house" needs to reach.
- **Time budget vs. the thesis timeline.** This is real engineering work on
  top of an already-busy pipeline — worth scoping the *first* version
  narrowly (OO metrics only, Python first since `ast`/`radon` need no
  project-file setup at all) rather than trying to match Designite's full
  8-CSV-per-project output on day one.

## Design decisions (2026-08-05, build kickoff)

Status upgrade: this section documents the decisions made when moving from
brainstorm to implementation. Answers to the open questions above, plus the
concrete architecture the code will follow.

**Scope: OO metrics only, both languages built in parallel** — smells were
out of scope for this pass (see "What's hard: smell detection" above), but
have since had their own build pass for Python; see "Smell detection: built
and partially validated (2026-08-11)" below. Python and C# analyzers are both in scope for this
build, not sequenced as two separate phases — but Python ships first in
practice (no toolchain/project-load setup needed, and the pilot's DPy output
is the fastest ground truth to validate against per the "Validation plan"
above), with the C# analyzer following the same schema once Python is
validated.

**C# approach: syntax-only Roslyn, not `MSBuildWorkspace`.** This is the
single biggest architectural fork and worth being explicit about *why*:
Designite's `dotnet/aspire` blocker (`DESIGNITE_TASK.md` §5,
`materialize_snapshots.py`'s `EXCLUDED_REPOS`) is entirely a consequence of
`MSBuildWorkspace` needing a real, restorable `.sln`/`.csproj` graph —
Arcade bootstrap, pinned preview SDKs, private feeds. `Microsoft.CodeAnalysis`
also exposes `CSharpSyntaxTree.ParseText`, which parses a single `.cs` file
into a full AST with **no project load at all**. Using that instead means:
- File/class/method-local metrics (LOC, WMC, NOM, NOPM, NOF, NOPF, CC, PC,
  LCOM) are all computable per-file, no `.sln` required — this is the
  `lizard`-style tradeoff the original doc flagged above, chosen deliberately.
- **Fan-In/Fan-Out/DIT need real cross-file type resolution**, which
  `ParseText` alone doesn't give (that's exactly what `MSBuildWorkspace`
  buys Designite). Building these ourselves means a lightweight, in-house
  symbol table: walk every parsed file's class/interface declarations once
  to build a name → declaring-file index, then resolve base-class/interface
  names and field/parameter/return types against that index. This is
  necessarily an approximation (no generic instantiation, no NuGet-package
  type resolution, no partial-class merging across files unless we handle
  `partial` explicitly) — good enough for DIT and same-repo Fan-In/Fan-Out,
  not a full semantic compile.
- **This is expected to unblock `dotnet/aspire`** for the in-house tool even
  though it stays excluded from Designite's own output — worth flagging
  explicitly when Phase 2 analysis runs, since it changes the "3 Python + 1
  C#" language imbalance noted in `ProjectStatus.md` §6 item 1.
- Output schema mirrors DPy/Designite's confirmed columns (see
  `long_analysis.py`'s `parse_tool_output()` docstring) so pooling continues
  to work the way `07-29-pooled-structural-metrics.csv` already does —
  no adapter step, same as the DPy/Designite pooling turned out not to need
  one.

**Correlation matrix: pre vs. post, using the existing `post`/
`intervention_date` convention.** Reuses the same pre/post split
`07-29-pooled-structural-metrics.csv` and `07-29-rq3-process.csv` already
encode (rows before vs. at-or-after each repo's intervention date) rather
than inventing a new split. Two metric-by-metric matrices per unit of
analysis (pre and post), **Spearman** not Pearson — consistent with the
existing process-metrics test choice (`07-29-rq3-process.csv` uses
Mann-Whitney/Cliff's delta, nonparametric throughout) and because smell
counts/LOC aren't expected to be normally distributed. Computed **both**
per-repo (small-N, descriptive) and pooled across the full sample (once
Phase 2 gives enough rows for pooled correlation to mean something) — matches
the existing per-repo-table + pooled-CSV pattern already used elsewhere in
`results/analysis/`.

**Time-series graphs**: one figure per metric, `target_date` on the x-axis,
one line per repo (or faceted small-multiples once the repo count grows past
what's readable on one plot) — built with the `dataviz` skill, reading
directly from the same pooled CSV shape the correlation matrices use, no
separate data prep.

**Entity/snippet tracking (RQ3)**: superseded by decisions logged in
`RQ3_CodeTracking.md`'s own "Design decisions" section, not duplicated here.

## Smell detection: built and partially validated (2026-08-11)

Status upgrade from "hard, separate phase" above: a Python v1 is built,
run against the full available sample, and checked against the pilot's
DPy output. Full design rationale, batch-run log, and validation numbers
live in `PySmellDetection.md`; this is the summary.

**Method**: Lanza & Marinescu's "Detection Strategies" (Marinescu, ICSM
2004; Lanza & Marinescu, 2006) — the well-documented-literature-definition
path this doc's "What's hard" section above called the defensible option,
not an attempt to reverse-engineer DPy/Designite's closed rule catalogs.

**Implemented (`src/inhouse/py_smells.py`), four strategies**:
- **God Class/Blob** and **Data Class** (class-level) → pooled as
  `design_smell_count` / `design_smell_density_per_kloc`
- **Feature Envy** and **Brain Method** (method-level) → pooled as
  `implementation_smell_count` / `implementation_smell_density_per_kloc`
- **Not attempted**: Shotgun Surgery (needs multi-commit history, out of
  scope for v1)

**What was found**: first full run (926 rows, `azure-sdk-for-python`
excluded — its `_tcc` cohesion computation is O(n²) and stalled on its
23,744-file / 40k+-line-file monorepo shape) over-flagged God Class at
~11.7% of classes, 5–25x the other three strategies' rate. Root cause,
confirmed empirically: WMC and TCC are strongly anti-correlated in real
code (Spearman r between −0.53 and −0.82 across sample repos), so ANDing
two independent 25th-percentile filters lands far above the naive 6.25%
independence estimate. Fixed by tightening both thresholds to 10%/10%,
which brought God Class down to 2.46% — in line with the other three
strategies. Re-run on the full corrected corpus: 799/926 ok.

**Validation against the pilot's DPy ground truth** (264 joined rows,
`airbyte`/`crewAI`/`mlflow` only): row-level Spearman correlation is weak
and slightly negative — expected, since this measures a different,
narrower smell definition than DPy's, not the same thing done wrong (see
"What's hard" above on why exact-count agreement was never the goal).
Pre/post-intervention *direction* agreement — the metric the validation
plan above actually cares about — is mixed-but-leaning-positive: 2/2 on
the pooled cross-repo signal, 4/6 per-repo-per-metric.
`implementation_smell_density_per_kloc` (Feature Envy + Brain Method) is
on firmer footing than `design_smell_density_per_kloc` (God Class + Data
Class) — God Class's double-percentile-filter structure is the piece
still flagged as needing more work.

**Open**: `_tcc`'s O(n²) cost is unfixed (a method-count guard is
proposed, not built — and confirmed to affect the OO-metrics engine's own
`_lcom`/C#'s `ComputeLcom` too, same complexity class, both currently
worked around by excluding `azure-sdk-for-python` rather than a guard); a
God Class v2 (absolute WMC floor, or corpus-pooled rather than
per-snapshot percentiles) is suggested but not started. **Update
2026-08-13: a C# equivalent now exists** (`SmellDetector.cs`, a direct
port reusing the same field-access machinery `ComputeLcom` already had —
see `PySmellDetection.md`'s "C# port" section for the build/validation
log and a real bug caught before trusting it on real data). OO metrics'
own coverage also expanded this entry from the 3-repo Python pilot to
every repo with a materialized snapshot (18 repos, both languages,
consolidated into `results/analysis/08-13-inhouse-metrics-pooled.csv`) —
see `ProjectUpdate.md`'s 2026-08-13 entry for the full account, including
a real Dock stale-clone data-hygiene bug caught and fixed in the
consolidation step.

Built on the (now-merged) `python-smell-detection` branch, commits
`6084ef9f6`..`ace21ab6f`.
