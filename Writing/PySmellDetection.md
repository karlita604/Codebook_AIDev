# In-house Python smell detection — brainstorm & design

**Status: brainstorm / build kickoff, 2026-08-11.** Branch
`python-smell-detection` (worktree `Codebook_AIDev-pysmells`, junctioned
`data/repo_cache` and `data/snapshots` to the primary checkout the same way
`designite-sln-support` did — see `DESIGNITE_TASK.md`'s "Working environment"
section for why a separate worktree, not an in-place branch switch: the
primary checkout has a live DPy batch job running against it,
`logs/phase0/long_analysis.pid`).

This picks up exactly where `InHouseTooling.md` left off: that doc scoped
its build to **OO metrics only** and explicitly parked smell detection as
"hard, separate phase" (see its "What's hard: smell detection" section).
`py_metrics.py`/`ast_common.py` are done and validated for that phase
(`validate_against_pilot.py`, `results/analysis/08-10-inhouse-validation-report.csv`).
This doc is that parked phase, now getting picked up.

## Why this is worth doing now

Same three reasons `InHouseTooling.md` gave for the OO-metrics build — LOC
caps forcing expensive chunking, closed/unpublished smell catalogs, and
per-seat licensing cost at Phase 2/3 scale — apply identically to
DPy/Designite's smell output, which the OO-metrics phase deliberately left
alone. Nothing new to argue there; see that doc.

## Picking a method: not Fowler, not "whatever DPy/Designite do"

`InHouseTooling.md` already ruled out trying to reproduce DPy/Designite's
*exact* smell counts (their thresholds are proprietary and unpublished —
`parse_tool_output()`'s schema had to be reverse-engineered from real output,
not read from docs). The realistic options for a *transparent, reproducible*
substitute:

1. **Fowler & Beck's catalog** (*Refactoring*, 1999) — the original "bad
   smells in code" list (Long Method, Feature Envy, Data Class, God
   Class/Large Class, ...). Deliberately qualitative — no formal thresholds,
   meant for human judgment during refactoring, not automated detection. Not
   directly implementable without inventing our own numbers, which would
   just relocate the "whose threshold is this" problem rather than solve it.
2. **Lanza & Marinescu, *Object-Oriented Metrics in Practice*** (Springer,
   2006), operationalizing Marinescu's own **"Detection Strategies"**
   mechanism (Marinescu, *"Detection Strategies: Metrics-Based Rules for
   Detecting Design Flaws,"* ICSM 2004 — the primary source, PDF confirmed
   directly, not secondhand). Formalizes exactly the smells Fowler names
   informally as **explicit metric formulas with published, named
   thresholds** (`FEW`, `MANY`, `ONE_THIRD`, ...), composed with logical
   `and`/`or`/`butnot`. This is the method underlying a large fraction of
   downstream academic and commercial smell tooling (inFusion, iPlasma,
   NDepend's own CQLinq replications) — arguably the closest thing the field
   has to a citable, reproducible standard.

**Chosen: Lanza & Marinescu Detection Strategies.** Decisive reason beyond
"more rigorous": it **composes directly with metrics `py_metrics.py`/
`ast_common.py` already compute** (WMC, LCOM's field-access machinery, DIT,
Fan-In/Fan-Out) — implementing it is additive to the OO-metrics engine, not
a rebuild. It also reframes the comparison the same way `InHouseTooling.md`
already committed to: not "does our count match DPy/Designite's," but
"does our independently-sourced, transparently-thresholded smell signal move
in the same direction" (see that doc's "Validation plan" step 4).

## The method, precisely

A **detection strategy** = one or more *metrics*, each reduced by a
**filter** to "interesting" values, combined with **and**/**or**/**butnot**.
Marinescu (2004) §3.1 names two filter families:

- **Semantical (absolute)**: `HigherThan(k)` / `LowerThan(k)` — a fixed,
  literature-cited constant.
- **Statistical / relative**: `TopValues(p%)` / `BottomValues(p%)` — computed
  from the *actual analyzed population's* percentiles, not an imported
  constant. Marinescu's own Rule 3 (§3.2) recommends this for "large
  systems" specifically, and his own worked God Class example (Eq. 1) uses
  exactly this form.

**Deliberate implementation choice**: wherever the source material gives a
genuinely fixed, dimensionless constant (a fraction, a small-integer
"few/many" convention), we use it verbatim. Wherever it gives a
*statistically-derived* threshold (WMC "Very High," CYCLO "High," ...) —
the book's own published numbers (e.g. WMC≥47) were fit to **45 Java
projects circa 2006** — we use Marinescu's own statistical-filter mechanism
(percentile over *this* run's own class/method population) instead of
porting a 20-year-old, other-language corpus constant unmodified onto
Python code. This mirrors a caveat already logged in this repo:
`DESIGNITE_TASK.md` §"Known gaps" notes NDepend's own replication had to
hand-adjust Lanza & Marinescu's LOC threshold downward (130→100) because its
own LOC-counting convention didn't match the book's — i.e. even *within*
one language and one tool family, the fixed constants don't transfer
cleanly. A self-calibrating percentile filter sidesteps that problem
entirely, at the honest cost of being corpus-relative rather than absolute
(documented, not silently assumed — same posture as every approximation
already logged in `ast_common.py`).

Fixed constants used (Lanza & Marinescu's own named conventions):

| Name | Value | Source |
|---|---|---|
| `ONE_THIRD` | 0.33 | Explicit fraction, used identically everywhere it appears (TCC, LAA, WOC) |
| `FEW` | 5 | Literature states a 2–5 range (confirmed via 2 independent secondary sources on the God Class/Feature Envy formulas); we use the top of that range |
| `MANY` | 7 | Miller's "7±2" short-term-memory-capacity convention, the stated rationale for this constant across the strategies that use it (NOAV, NOPA+NOAM) |
| `SEVERAL` | 3 | Literature states a 2–5 range for nesting; low end chosen (nesting compounds fast) |

Statistically-derived thresholds (computed per-run, not imported):

| Name | Operationalization |
|---|---|
| `VERY_HIGH(metric)` | 90th percentile of `metric` over this run's population |
| `HIGH(metric)` | 75th percentile of `metric` over this run's population |

## Detection strategies implemented (v1: four, class- and method-level)

**God Class / Blob** (class-level) — the one strategy with a **primary-source
equation**, used essentially verbatim (Marinescu 2004, Eq. 1):

```
GodClass(C) = WMC(C) ∈ TopValues(25%)  ∧  TCC(C) ∈ BottomValues(25%)  ∧  ATFD(C) > 1
```

`TopValues(25%)`/`BottomValues(25%)` are the same operationalization as
`HIGH`/`VERY_HIGH` above but at the 75th percentile boundary directly (the
paper's own worked parameterization, not the book's later WMC≥47 refinement
— using the primary source's own numbers where we have them, rather than a
secondhand paraphrase). `ATFD(C) > 1` is Marinescu's own stated threshold
verbatim (his text says "no direct access ... should be permitted," then
parameterizes the filter as `HigherThan(1)` — reproduced as written, that
looseness is the source's, not introduced here).

**Data Class** (class-level; book-refined formula, corroborated via 2
independent secondary sources reporting the same formula and constants):

```
DataClass(C) = WOC(C) < ONE_THIRD
               ∧ ( (NOPA(C)+NOAM(C) > FEW  ∧ WMC(C) < HIGH(WMC))
                   ∨ (NOPA(C)+NOAM(C) > MANY ∧ WMC(C) < VERY_HIGH(WMC)) )
```

**Feature Envy** (method-level; book formula, 2 independent secondary
sources agree):

```
FeatureEnvy(m) = ATFD(m) > FEW  ∧  LAA(m) < ONE_THIRD  ∧  FDP(m) ≤ FEW
```

**Brain Method** (method-level; book formula, corroborated secondarily):

```
BrainMethod(m) = LOC(m) > HIGH(class LOC)/2
                 ∧ CYCLO(m) ≥ HIGH(CYCLO)
                 ∧ MAXNESTING(m) ≥ SEVERAL
                 ∧ NOAV(m) > MANY
```

Not attempted in v1: **Shotgun Surgery** and any strategy needing real
change-history (multi-commit correlation) rather than a single-snapshot
AST pass — same "Analysis of Multiple Versions" extension Marinescu (2004)
§3.4 flags as future work, not core to the strategy mechanism itself. Could
revisit once/if this composes with `RQ3_CodeTracking.md`'s entity tracker.

## New metric primitives needed (beyond what `py_metrics.py` already has)

Reused as-is from the existing OO-metrics engine: `WMC` (`class_wmc` in
`py_metrics.py`), `NOPF`→`NOPA` (identical definition, just renamed to match
the smell literature's term), `CC`/`CYCLO` (same metric, same name
difference), class/method `LOC`. **`TCC` reuses `_lcom`'s own field-access
machinery** — `_lcom` already builds one field-access set per method via
`ast_common.self_attribute_names()`; TCC is `(pairs sharing ≥1 field) /
(total pairs)`, i.e. the `q` LCOM already computes, divided by `C(n,2)`
instead of turned into `max(0, p-q)`. Same inputs, different aggregation —
no new AST walking needed for this one.

Genuinely new, added to `ast_common.py` (shared layer, same rationale as
its own docstring: "one AST-walking layer, not two," now three consumers —
`py_metrics.py`, this, and eventually the RQ3 tracker):

- **`foreign_attribute_accesses(func_node, known_field_names)`** — the
  primitive `ATFD`/`FDP`/`LAA` are all built from. Heuristic, same category
  of approximation as `py_metrics.py`'s existing `_referenced_class_names`
  (itself used for Fan-In/Fan-Out): every `X.attr` access where `X` is a
  bare `Name` other than `self`/`cls`, filtered to `attr` names present in
  `known_field_names` (the whole-snapshot field-name catalog `ast_common`'s
  class index already builds) — textual, **not** real type resolution. No
  import-alias resolution; a receiver whose *actual* type doesn't declare
  that field (false positive, e.g. a stdlib object with a same-named
  attribute) or whose field the snapshot's own catalog didn't happen to
  include (false negative) are both accepted, documented approximations —
  filtering against the known-field catalog is a deliberate precision/recall
  tradeoff to cut stdlib-call noise, same tradeoff `_referenced_class_names`
  already made for class names.
- **`max_nesting_level(func_node)`** — deepest control-flow nesting
  (`If`/`For`/`While`/`Try`/`With`, async variants), stopping at nested
  `def`/`class` boundaries (same boundary convention as
  `cyclomatic_complexity`'s `_CCVisitor`).
- **`accessed_variable_names(func_node)`** — distinct `Name`
  loads/stores/dels plus `self.attr`/`cls.attr` accesses (kept as
  `"self.attr"`, not just `"attr"`, so it can't collide with an unrelated
  local of the same bare name) — proxy for `NOAV`. Doesn't distinguish
  reads from writes; the published metric doesn't either.
- **`is_accessor_method(method_entity)`** — a method is a getter/setter
  (needed for `NOAM`/`WOC`) if it's `@property`-decorated, or its body is
  exactly one `return self.<name>` statement, or exactly one
  `self.<name> = <param>` statement. Python has no getter/setter *syntax*
  the way the metric's originating languages (Java/C++) do, so this is a
  structural proxy for the same intent, not a language-native concept —
  worth flagging as a Python-specific operationalization, same spirit as
  `ast_common.py`'s existing `_is_public`'s underscore convention already
  being a Python-specific stand-in for Java's `public`/`private` keywords.

## Output schema

Pools into the same DPy/Designite-comparable shape the OO-metrics engine
already established (`(repo_id, track, target_date, commit_sha)` keys, no
adapter step) — `design_smell_count`/`design_smell_density_per_kloc` (God
Class + Data Class, both class-level structural flaws — matches Designite's
own bucketing of God-Class-family smells under `DesignSmells.csv`) and
`implementation_smell_count`/`implementation_smell_density_per_kloc`
(Feature Envy + Brain Method, both method-level — matches Designite's
`ImpSmells.csv` bucketing, which is where it puts Long-Method-family
smells). Bucket *names* match Designite's for pooling convenience; bucket
*contents* are our own, independently-sourced smells — per
`InHouseTooling.md`'s validation plan, the comparison target is
direction/magnitude of the density signal, not row-for-row agreement with
Designite's specific rule set. Per-class/per-method detail rows (which
smell, which entity, the metric values that triggered it) also kept,
mirroring `py_metrics.py`'s `class_detail_rows()` — not pooled into the
summary row, but there for inspection and for a future correlation pass.

## Validation plan

Same shape as `InHouseTooling.md`'s (step-for-step): run against the same
already-materialized Python snapshots the pilot used, compare direction/
magnitude of `implementation_smell_density_per_kloc` against DPy's own
`_implementation_smells.csv`-derived density in
`07-29-pooled-structural-metrics.csv` (not exact-count agreement — different
smell catalogs by design, see above). No god-class-shaped ground truth to
check exact recall against without hand-labeling a sample; a lighter check
is planned first — spot-inspect the top-N highest-WMC/lowest-TCC classes
flagged on a real repo and confirm they're subjectively plausible God
Classes (the "Manual Investigation" validation Marinescu himself used,
§6.2) before trusting the pooled density numbers for anything.

## Open questions

- **`known_field_names` catalog scope**: whole-snapshot (current plan,
  matches `ast_common._build_class_index`'s existing scope for Fan-In/
  Fan-Out) vs. something narrower. Whole-snapshot is more permissive (more
  false-positive foreign-access hits on common field names like `name`/
  `id`/`value`) — worth revisiting once real output is in hand and this
  can be checked empirically rather than guessed.
- **Percentile-based `HIGH`/`VERY_HIGH` thresholds are corpus-relative by
  construction** — a class that would be an obvious God Class in a small,
  simple repo might not clear the 90th-percentile bar in a large, uniformly
  complex one, and vice versa. This is an explicit tradeoff (see "The
  method, precisely" above), not an oversight — flagging here so it's not
  mistaken for one later. Whether percentiles should be computed per-repo
  or pooled across the whole corpus is itself an open call; starting
  per-snapshot (simplest, matches how `py_metrics.py` already scopes its
  own DIT/Fan-In/Fan-Out resolution to one snapshot at a time) and revisiting
  if per-repo turns out too noisy on small repos.
