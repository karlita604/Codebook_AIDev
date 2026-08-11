# RQ3 — tracking a code entity's lifetime across a repo's history

**Status: 2026-08-11 — Stages 1-4 (matcher, metrics, validation gate,
Python + C# extraction) built and validated on crewAI + Dock; see "Build
log" below. Stage 5 (full pilot + Phase 2) not yet built.**

## The question

RQ3, as stated: **track a specific code snippet (class, method, or file)
over time in a project and see how it ages** — did it stay stable, get
refactored repeatedly, or accumulate a string of bug-fix PRs? This is a
different unit of analysis than RQ1 — RQ1 asks "how does the *whole repo's*
structural health change around an intervention point"; RQ3 asks "what
happens to *one specific piece of code's* identity over its lifetime,"
independent of any single intervention point. It could be run on its own
timeline, or specifically asked of code that existed both before and after
a repo's AI-agent intervention date, to see whether *individual pieces of
code* age differently once agents start touching the repo — a
finer-grained complement to RQ1's repo-wide view.

## Why this is harder than it sounds: git doesn't track entity identity

Git tracks *file* history reasonably well (`git log --follow` survives
renames, most of the time, via similarity detection). It does **not** track
*sub-file* entity identity at all — there's no git-native way to ask "is
this method, which now lives at line 40 of `foo.py`, the same method that
used to be at line 12 of `bar.py` three years ago." Every approach to RQ3
has to solve that identity problem itself, and this is exactly where the
existing pipeline's infrastructure (materialized snapshots, cloned repo
history) becomes directly reusable — see "Practical starting point" below.

### Approach 1 — file-level only (cheapest, weakest)

`git log --follow --` per file gives a reasonably reliable rename-aware
history for whole files. Cheap, works today with plain git, no new tooling.
Doesn't answer the "class/method" granularity the RQ explicitly asks for,
but could be a fast first pass (e.g. "how many commits touched this file
over its life") before investing in entity-level tracking.

### Approach 2 — AST-based per-commit entity inventories, matched across commits

For each commit (or each materialized snapshot, since those already exist
for the RQ1 repos — see below), parse the source into an AST and extract an
inventory of entities (class/method) with a qualified name, signature, and
body. Match entities across consecutive commits by a combination of:
- exact qualified-name + signature match (cheapest, catches the common case
  of "nothing changed about its identity, only its body")
- fuzzy match (name similarity + body similarity, e.g. AST diff size or
  token-overlap) for renames/signature changes, the same class of problem
  `git log --follow`'s similarity heuristic solves at the file level, just
  one level down
- an explicit "no match found" case for genuine deletion or a rewrite so
  total it isn't reasonably "the same" entity anymore — this boundary is a
  real methodological judgment call, not a solved problem, and needs its
  own documented threshold once this is prototyped for real.

This is the approach that actually answers "what happened to this specific
method" but is real engineering: needs a language-aware parser per language
in scope (same multi-language question `InHouseTooling.md` raises for RQ1's
metrics — worth building any shared AST-handling infrastructure once, not
twice, if both RQs end up needing Python/C# parsing).

### Approach 3 — existing research tools, evaluate before building

Worth evaluating before committing to a from-scratch Approach 2 build:
- **CodeShovel** — purpose-built for method-level history mining
  (`git log`-equivalent but at method granularity), the closest existing
  match to exactly what RQ3 asks for. Would need evaluation against a real
  pilot repo before trusting it for the thesis (unfamiliar tool, unverified
  accuracy on this codebase's languages).
- **PyDriller** — a Python library for mining git repos commit-by-commit
  (diffs, modified methods via a lizard-based CC integration) — lower-level
  than CodeShovel but well-maintained and already Python-native, which fits
  this project's existing Python tooling.
- **git-of-theseus** — computes repo-wide "code survival" curves (what
  fraction of a repo's current code, by line, came from which past commit)
  — coarser than entity-level tracking (line-attribution, not
  class/method identity) but could be a fast, cheap first descriptive look
  at "how much of this repo's code is old vs. new" before investing in
  full entity tracking.

None of these are evaluated yet — this is a list of what to actually try,
not a recommendation of one over the others.

## Linking entity lifetimes to PR/process data

Once an entity's lineage exists (whichever approach), the actually
interesting RQ3 questions are about connecting it to the process data this
project already collects:

- **"How many PRs touched this entity?"** — join the entity's file
  (and, at method granularity, its line range) against Track B's PR data
  (`results/pr_samples/`) via the PR's diff (needs Track B's still-not-built
  deeper per-PR diff stats — see `ProjectUpdate.md`'s open items — this is a
  second, independent reason to prioritize that gap, not just for RQ3's
  parent RQ1's PR-size analysis).
- **"How many were bug fixes specifically?"** — needs a bug-fix
  classification heuristic on top of the PR title/body (keyword matching,
  or reusing whatever the AIDev dataset already encodes about PR intent if
  anything), or linking to the repo's issue tracker if PRs reference issues.
- **"Did it stabilize, or keep changing?"** — a survival-analysis framing
  (time between successive touches to the same entity) is a natural fit
  once the entity-touch events exist as a timeline.

## Practical starting point

The existing RQ1 infrastructure is directly reusable here, which is the
main reason to prototype this now rather than treat it as a separate
project:
- `data/repo_cache/` already has partial (`blob:none`) clones with full
  commit history for every pilot repo — the git-log work above doesn't need
  a fresh clone.
- `data/snapshots/<owner>__<repo>/<commit_sha>/` already has materialized,
  language-filtered source trees at every RQ1 grid point — a natural set of
  checkpoints to run an AST inventory against without needing every single
  commit.

Recommended first step: prototype Approach 2 (or evaluate Approach 3's
tools) against **one pilot repo already fully collected** (crewAI is the
smallest/most complete Python pilot repo, per `ProjectStatus.md`) before
deciding on a tooling investment — same "validate on a known-good subset
before scaling" pattern already used for the DPy chunker and Designite's
`.sln` chunking (`ProjectUpdate.md`, 2026-07-27/07-28).

## Open questions to resolve before committing to an approach

- **Entity identity across a rename+edit in the same commit** — the hardest
  case for any matching heuristic (is it confidently "renamed" or
  confidently "deleted + new entity created"?), and the pilot's own repos
  likely have real examples of this worth checking early.
- **Language scope** — Python/C# to match the existing RQ1 tooling, or
  broader? Broader adds real parser-support cost (see `InHouseTooling.md`'s
  same concern for RQ1's metrics).
- **How far back to trace** — full repo history, or windowed around each
  repo's intervention date (mirroring RQ1's A2 track)? A full-history trace
  answers "how does this repo's code age in general"; a windowed trace
  answers the more RQ1-adjacent "does aging change post-intervention" —
  worth deciding based on which framing the thesis actually wants to lead
  with.
- **Granularity choice (class vs. method vs. both)** — methods age faster
  and more atomically (easier identity matching, more of them, noisier
  individually); classes are coarser but more stable as a unit — likely
  worth prototyping at method granularity first since it's the more
  common case in the smell/metric data RQ1 already tracks.

## Design decisions (2026-08-05, build kickoff)

Status upgrade: moving from brainstorm to implementation. Decisions below,
against the open questions above.

**Approach: 2 (custom AST entity-matcher), built directly** — no separate
evaluation phase for CodeShovel/PyDriller/git-of-theseus first. Shares its
AST-parsing layer with `InHouseTooling.md`'s OO-metrics engine (Python `ast`,
C# `CSharpSyntaxTree.ParseText` — see that doc's design-decisions section for
why `ParseText` over `MSBuildWorkspace`) rather than building a second,
separate parser — "worth building any shared AST-handling infrastructure
once, not twice" (this doc, "Approach 2," above) is exactly what happens
here: one entity inventory pass over a parsed file produces both the
OO-metrics rows and the entity-tracking rows.

**Granularity: both method and class, from the start** — two separate
matching passes (methods within their enclosing class don't block class-level
matching, and vice versa), not a phased method-first rollout.

**Window: both** — full repo history (a per-entity survival/aging view, no
intervention framing) and an intervention-windowed cut (mirrors RQ1's A2
event-window track, for the agent-adjacent question). Both are cuts over the
*same* underlying entity-touch timeline, not two separate collection passes —
the windowed view is just a filter on `commit_date` relative to each repo's
`intervention_date`.

**Commit source: `git log --follow -- <path>` per file, not a full-history
snapshot grid.** The existing `data/snapshots/` grid only materializes
monthly checkpoints (RQ1's cadence) — too coarse to catch "how many times was
this method edited," which needs every commit that touched the file. Walking
`git log --follow` per file against the already-cloned `data/repo_cache/`
gives exactly the touching commits without needing a full materialized tree
at every one of them — only those specific blobs get pulled per commit
(same `git show <sha>:<path>` extraction model `materialize_snapshots.py`
already uses for archiving, just per-commit-per-file instead of
per-commit-whole-tree).

**Matching heuristic**: exact qualified-name + signature match first: falls
back to fuzzy match (token-overlap similarity over the body) for
renames/signature changes when no exact match exists in the same file's
prior/next inventory; below a similarity threshold (to be tuned empirically
against a real pilot repo, not guessed up front) counts as "no match" —
genuine deletion or a rewrite total enough it isn't reasonably the same
entity. The rename-vs-delete+create boundary noted in "Open questions" above
is exactly this threshold — expect to revisit it once real pilot output
exists to eyeball.

**A real scope gap surfaced by this build, not yet resolved**: "edited N
times" and "went through multiple rounds of review" are two different
claims, resting on different data:
- **Edit count** is answerable now, purely from the entity-touch timeline
  above (commits that changed this method/class) — no new data collection
  needed.
- **Review rounds** (requested-changes cycles, re-review counts) needs
  PR-level review-thread detail, which `ProjectStatus.md` §6 item 4 already
  flags as *not yet built* — Track B currently has PR identity, timestamps,
  and comment counts only, not the deeper per-PR diff/review stats that
  would let an entity's touches be joined to *which PR* touched it and *how
  many review rounds that PR went through*. This build ships the entity-touch
  timeline and edit-count first; entity-to-PR-review linkage stays blocked on
  that separate, not-yet-started Track B gap, same dependency
  `InHouseTooling.md`'s "Linking entity lifetimes to PR/process data" section
  already named.

## Build log (2026-08-11, Stages 1-3 of the execution plan)

Built on a new worktree (`rq3-entity-tracker` branch, `Codebook_AIDev-rq3`)
off `main`, isolated from live work on `main` the same way
`designite-sln-support` was. Full plan: see the session's plan file
(`glimmering-snacking-torvalds.md`).

**Stage 1 — matcher + Python extraction, prototyped on crewAI.** Built
`src/inhouse/entity_matching.py` (the language-agnostic exact-then-fuzzy
matcher, `EntityTouch`/`EntityLineage` dataclasses) and
`src/inhouse/py_entity_history.py` (per-file `git log --follow` walker,
reusing `ast_common.extract_classes`/`extract_functions` in-process, per
that module's own "one AST-walking layer, not two" design intent). Caught
and fixed a real bug before running anything on real data: re-extracting a
whole file's entity inventory at every commit that touched *anything* in
that file meant an unchanged sibling entity would get a spurious "modified"
touch every time - fixed by only recording a touch when the entity's own
token/signature content actually differs from its last-seen state.

**Stage 2 — metrics.** Added to `EntityLineage`: `age_days(as_of)` (first-
to-last touch, Eick et al.'s code-decay-index framing), `relative_churn`
(`modification_count` / current LOC — Nagappan & Ball, ICSE 2005, cited in
`codeaging.md` as outperforming absolute churn as a defect-density
predictor), `change_entropy` (Shannon entropy over normalized inter-touch
time gaps — an explicitly-labeled *simplified proxy* for Hassan's
entropy-of-changes, ICSE 2009, not a faithful reimplementation of the
original window/amount-of-change formula), and `review_count` (always
`None` — codeaging.md's own Theme 4 conclusion is that no existing tool
does this, and it needs Track B's still-missing PR-diff data, so this is an
explicit placeholder, not a fabricated proxy).

**Stage 3 — validation gate, real findings.** `src/inhouse/
validate_entity_matching.py` sweeps the similarity threshold
(0.6-0.8) and runs two checks against real crewAI data. Since a single AI
session can't do literal by-hand review with a human's eyes, the "hand-
trace" the plan calls for was operationalized as: (a) an automated
subset-check against `git log -L :func:file` — git's own, independently-
implemented function-history algorithm — for never-renamed lineages, and
(b) direct diff inspection of every detected rename/move, done in-session.

Real results, not projected ones:
- **A 100-file, tree-broad sample** (stride-12 across crewAI's 1,269 `.py`
  files — a first alphabetically-first 80-file sample turned out to miss
  whole subtrees entirely, corrected once noticed) produced 585 lineages.
  At the design's default threshold (0.75), exactly **1 rename/move fired**
  across the whole sample.
- **A real true positive, confirmed by hand**: `ef40bc0bc` renames
  `AgentExecutor.force_final_answer` → `ensure_force_final_answer` with an
  otherwise-untouched body. Jaccard similarity: 0.933 — caught correctly at
  every threshold from 0.6 through 0.9 (only an unrealistically strict 0.95
  misses it). Real, independent confirmation the fuzzy tier works as
  designed on the common case (rename, no other change).
- **A real false-merge case, found by the sweep itself, not by chance**: a
  test file's commit `a1f44eb27` splits one class
  (`TestFlowResumeReplaysEvents`) into two
  (`TestCheckpointResumeReplaysEvents`, a near-total rewrite, and
  `TestPersistResumeDoesNotReplayCompletedEvents`, which retained more of
  the original method's token content). At threshold 0.60-0.65, the matcher
  attaches the old class's identity to the token-similar-but-arguably-wrong
  successor (0.617 similarity) instead of the class that actually continues
  its stated intent. **At the design's actual default (0.75), this false
  merge does not fire** — 0.617 falls below it. This is exactly the
  untracked/misattributed-history risk Hora et al. (cited in codeaging.md)
  warn about, caught concretely on this corpus rather than left as an
  abstract literature caveat — and it argues for *keeping or raising* the
  threshold, not lowering it, the opposite of what "harder to catch renames"
  intuition might suggest.
- **Automated baseline check found its own real limitation**: `git log -L`
  failed to resolve the sampled function at all for 20/30 candidates
  (confirmed on one case directly: `parallel_find_similar` genuinely exists
  in the file, `git log -L` still reports "no match") - not a bug in the
  cross-check's invocation, but git's own line-history heuristic being
  unreliable on this corpus, consistent with codeaging.md's "git tooling"
  caveat. Of the 10 candidates `-L` *could* resolve, 9 agreed (the tool's
  touch-commit set was a subset of `-L`'s). Effective sample size is smaller
  than the 30 planned, and reported as such — not inflated by treating
  unresolved cases as agreements.

**Decision: keep the 0.75 default**, not lower it. The evidence gathered
argues for this directly: the one real false-merge case found requires
threshold ≤0.65 to fire; the one real true-positive rename found is caught
robustly up through 0.9. This is a validated choice now, not an assumed
one — though the sample (100 of 1,269 files, one repo) is small enough that
this isn't a final word; extending Stage 3's sweep across more of the pilot
before Stage 5's full-Phase-2 run would strengthen it further.

**Known, now-quantified limitation for the write-up**: class-level splits
(one class rewritten into two) are a real, confirmed failure mode at low
thresholds and a source of residual ambiguity even at 0.75 (the one
method-level match that *did* fire sits inside a class-restructuring the
matcher has no way to know about, since it can't see "this class was split"
as a category of event — only "these two entities' bodies are similar
enough"). Not fixed in this build; documented as the kind of case a future
refactoring-aware tool (PyRef, or a real bipartite-optimal matcher instead
of the current greedy one) would handle better, per the execution plan's
"out of scope for this plan" section.

**Not done this entry**: Stage 4 (C# / Roslyn extension, Dock validation)
and Stage 5 (scale to the full pilot + Phase 2) — both explicitly gated on
this stage's validation gate landing first, which it now has.

Raw output: `results/analysis/rq3-validation-baseline-check.csv`,
`rq3-validation-manual-review-candidates.csv`,
`rq3-prototype-crewai-80files.json`.

## Build log (2026-08-11, continued — Stage 4, C# via Roslyn)

**Extraction, not matching, is what's new here.** `entity_matching.py`
(the matcher itself) is unchanged and reused as-is — it's already language-
agnostic and already validated on Python data (Stage 3 above). What Stage 4
actually needed to build and validate was C# *extraction*: pulling a
class/method inventory with source text out of an arbitrary git blob, the
thing `SnapshotAnalyzer.cs` doesn't do (it only reads whole materialized
snapshot directories, not single blobs from arbitrary commits).

**Built**:
- `src/inhouse/roslyn_tool/EntityHistory.cs` — a new, self-contained
  extraction pass (deliberately *not* a refactor of `SnapshotAnalyzer.cs`'s
  private helpers, to keep zero risk to that already-validated tool's
  output). Mirrors its `QualifiedNameOf`/`MethodNameOf` logic (same node
  types, same Parent-chain walk) by design intent, not by sharing code —
  documented as a deliberate simplicity-over-DRY tradeoff in the file's own
  header comment. Batched via a new `--batch` stdin/stdout mode on
  `Program.cs` (`roslyn_tool.exe --batch < blobs.json`), not one process per
  commit — checked directly (see below) that batching a whole file's
  history into one process call avoids paying .NET's ~0.4s startup cost per
  commit, the same amortization concern the execution plan flagged in
  advance.
- `src/inhouse/cs_entity_history.py` — Python glue mirroring
  `py_entity_history.py`'s shape, reusing its `follow_history`/`_run_git`/
  `_safe_dirname`/`REPO_CACHE_DIR` directly (all already language-agnostic,
  not Python-specific) rather than duplicating the git-plumbing half.

**Real validation, not projected**:
1. **Exact cross-check against already-validated ground truth.** Ran the
   new extraction against every `.cs` file (245 of them) at a real Dock
   commit (`e9b28879...`, 2022-04-01) already analyzed by the existing,
   validated `SnapshotAnalyzer.cs`
   (`results/analysis/08-11-inhouse-metrics-Dock-96.csv`: 208 classes, 584
   methods). **Result: exact match** — 208 classes, 584 methods, 0 parse
   errors, both tools agreeing to the entity. A stronger check than a
   sampled hand-validation, since it's a full-corpus comparison against
   numbers already independently confirmed against real Designite output
   (`Writing/ProjectStatus.md` §6's Tool-CS validation section).
2. **End-to-end rename detection, synthetic then real-shaped.** A synthetic
   C# method rename (body untouched, name-only change) through the full
   pipeline (`roslyn_tool --batch` → `tokenize()` → `match_file_history`)
   scored 0.846 similarity and was correctly classified `renamed` — confirms
   the C# extraction's `source_text` output is real, taggable text the
   Python-side tokenizer can use the same way it already uses Python source
   slices. (A real Dock commit search for an in-file class-rename came up
   empty in the time spent looking — the "Rename ..." commits found either
   touched only call sites or spanned multiple files without a clean single-
   file before/after to isolate — not pursued further given the exact
   cross-check above already gives strong extraction-correctness evidence.)
3. **Real prototype run**: 40 Dock files → 85 lineages, 0 file errors, 15s
   wall time (vs. Python's 30s for 80 crewAI files — the batching design
   holds up on real, not just synthetic, history).

**Not done this entry**: a Stage-3-style full validation sweep specifically
for C# (threshold tuning, false-merge hunting) — not repeated because the
matching algorithm being swept *is* the same one Stage 3 already validated
on Python; what needed independent validation for C# was extraction
correctness, which the exact cross-check above covers more strongly than a
sampled sweep would have. Scaling to the rest of the pilot and full Phase 2
(Stage 5) is next.

Raw output: `results/analysis/rq3-prototype-dock-5files` (console output,
not saved to disk — see this entry's numbers above).
