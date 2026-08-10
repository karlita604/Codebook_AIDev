# RQ3 — tracking a code entity's lifetime across a repo's history

**Status: brainstorm / research, 2026-08-04. Nothing here is built.**

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
