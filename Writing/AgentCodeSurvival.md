# Tier-2 idea #1 — does agent-touched code get rewritten sooner? (2026-08-21)

> **Status: first pass, real data, three real bugs found and fixed by
> hand-checking before trusting any output** (see each section below).
> Exploratory, not a pre-registered test. Branch:
> `analysis/agent-code-survival`, off
> `analysis/review-intensity-and-null-check`.

## Why this exists

`LitReview.md`'s source #15 ("Code Change Characteristics and
Description Alignment: Agentic versus Human PRs") finds, across the
aggregate AIDev corpus, that agent-introduced symbols are removed sooner
than human ones (median 3 vs. 34 days) and churn more (7.33% vs. 4.10%).
This project has its own longitudinal, per-entity touch history (the RQ3
entity tracker) — a from-scratch, within-repo replication of that
specific claim is buildable from data already collected, not something
that has to be taken on faith from AIDev's own aggregate numbers.

## The real blocker: no file on disk links a touch to a PR

`results/analysis/08-19-entity-history-pooled.csv` carries only
first/last touch per lineage — the full per-touch list (commit SHA, date,
change type) exists only transiently inside `py_entity_history.py`'s
`build_file_lineages()` while it runs, and is discarded once summarized
into that pooled file. `results/repos/08-17-aidev-agent-prs-3332.csv`
(the agent-PR registry) carries no commit SHA at all — only PR number
(parseable from `html_url`), agent name, and timestamps. `merged_at` is
frequently null even for genuinely merged PRs (Kalliamvakou et al. 2014,
cited in `LitReview.md`'s Theme 5, found ~40% of merged PRs don't show as
merged in GitHub's own API) — gating on that field would silently drop
real merges, not just unmerged ones.

**The fix, avoiding new API collection**: local git history already has
the answer. GitHub's default squash-merge commit message is
`<title> (#NNNN)`; a traditional merge commit's default message is
`Merge pull request #NNNN from ...`. Both patterns are matched against
each repo's own `git log` (already cloned in `data/repo_cache/`, no
network needed) to build a `pr_number -> commit_sha` map per repo,
independent of — and more reliable than — AIDev's own `merged_at` field.
Confirmed directly on `crewAIInc/crewAI` before writing any matching code:
10/10 sampled recent commits use the squash format.

Code: `src/analysis/agent_code_survival.py`.

## Scope

Python only this pass (`py_entity_history.py`'s matcher; a C# pass via
`EntityHistory.cs`/`cs_entity_history.py` is a real, separate follow-up).
Top-10 Python repos by `agent_pr_count` among RQ1's 79 regression-eligible
repos, all confirmed to have a local `data/repo_cache/` clone (51/51
Python regression-eligible repos have one — clone availability wasn't the
constraint). Not claimed to generalize to the other ~41 Python repos.

## Real PR→commit resolution rates vary by repo, and track known agent
identity — not a bug in the method

| Repo | Agent PRs | Resolved to a commit |
|---|---|---|
| `crewAIInc/crewAI` | 327 | 40 (12%) |
| `mlflow/mlflow` | 91 | 74 (81%) |
| `airbytehq/airbyte` | 218 | 86 (39%) |
| `AgentOps-AI/agentops` | 51 | 18 (35%) |

Before trusting this, checked whether the low rates reflect a broken
matcher or a real "most agent PRs here were never merged" story: crewAI's
resolved count (40) sits almost exactly on its `merged_at`-non-null count
(42) — the two independent signals agree closely, and crewAI is a 100%
Devin-authored repo (`agent_breakdown` in the repo-summary registry),
consistent with `LitReview.md` source #1's documented "agents accepted
less often than humans" finding. mlflow (Copilot-heavy) resolves at 81%.
The spread is real repo/agent variation, not evidence the method is
broken.

## Bug 1, found and fixed before trusting any output: random file sampling misses agent-touched files almost entirely

The first version of this script reused `py_entity_history.py`'s own
random 150-file sample, matching this project's usual convention for
scoping an entity-history walk. Run for real, it produced 0-9
agent-tagged touches per repo out of 1,300-3,500 touches walked — a
random sample of 150 files out of a repo's full file count essentially
never lands on the handful of files a specific agent commit actually
touched. Fixed by resolving each agent commit's own changed `.py` files
(`git diff --name-only {sha}~1 {sha}`, works uniformly for both a squash
commit and a merge commit since `~1` follows first-parent by default —
exactly the PR's own contributed diff) and walking exactly that targeted
set instead.

**A real, named trade-off this creates**: the "other" (non-agent) touches
compared against are still real human/other touches, but on files that
happen to attract agent attention specifically — not a repo-wide random
sample. The comparison this analysis actually runs is "what happens on a
file after an agent touches it, within that file's own history," not
"agent-touched files vs. typical files repo-wide."

## Bug 2, found by hand-checking a suspicious `gap_days=0` row: duplicate touches from a single commit

`entity_matching.py`'s matcher can record the same commit twice for the
same lineage — confirmed directly: `mlflow/mlflow`'s
`dev/check_function_signatures.py` lineage 1 lists commit `4d99802...`
twice, both `change_type="created"`. A real characteristic of the shared,
already-validated matcher, not something to alter there. For this
script's own purposes, two touch rows from the literal same commit aren't
a real "gap" — one event double-counted, not two events zero days apart.
5.4% of raw gap-pairs (666/12,391) were affected before this fix.
Deduplicated by `commit_sha` within each lineage before computing gaps.

**This fix mattered substantively, not just cosmetically**: before it,
mlflow alone showed a dramatic, seemingly clean result (p=5.7×10⁻⁹,
agent-touched code surviving *shorter*) that vanished entirely after
dedup (p=0.28) — the duplicate-touch artifact was inflating mlflow's
"after an agent touch" sample with spurious zero-day gaps. Reported here
as the reason this fix isn't optional, not as a curiosity.

## Coverage, after both fixes

| Repo | Agent-tagged touches | Gap-pairs after an agent touch |
|---|---|---|
| `mlflow/mlflow` | 277 | 119 |
| `Significant-Gravitas/AutoGPT` | 120 | 69 |
| `567-labs/instructor` | 30 | 14 |
| `getsentry/sentry` | 29 | 19 |
| `airbytehq/airbyte` | 71 | 0 |
| `AgentOps-AI/agentops` | 28 | 1 |
| `ikamensh/flynt` | 11 | 0 |
| `crewAIInc/crewAI` | 0 | 0 |
| `browser-use/browser-use`, `crewAIInc/crewAI-tools` | 0 | 0 |

Only 4 repos clear `n>=2` in both groups for a per-repo test at all
(mlflow, AutoGPT, instructor, getsentry). `crewAIInc/crewAI` contributes
nothing — every one of its 72 agent-touched files has since been moved or
deleted as part of the `lib/` restructuring `Results.md` already
documented (0/72 still present at HEAD), independently reconfirming that
finding through a completely different code path. `browser-use` and
`crewAI-tools` resolved real commits but none of their touched files
matched any lineage the AST matcher tracks in this walk (not further
diagnosed this session).

## Result: no generalizable signal, and the one seemingly strong pooled result doesn't survive a repo-composition check

| Repo | n (agent / other) | Median gap after agent (days) | Median gap after other | Mann-Whitney p | Cliff's δ |
|---|---|---|---|---|---|
| `567-labs/instructor` | 14 / 151 | 33.4 | 31.4 | 0.745 | -0.05 |
| `Significant-Gravitas/AutoGPT` | 69 / 613 | 68.7 | 48.2 | 0.515 | +0.05 |
| `getsentry/sentry` | 19 / 1,918 | 15.3 | 0.9 | **0.0025** | **+0.40** |
| `mlflow/mlflow` | 119 / 5,628 | 42.0 | 50.0 | 0.285 | -0.06 |
| **pooled (naive)** | 222 / 11,513 | 42.0 | 9.9 | **4.5×10⁻¹³** | **+0.28** |

Read naively, the pooled row says agent-touched entities take
*longer* to be touched again than other-touched entities — the opposite
direction from `LitReview.md`'s aggregate finding, and dramatically
significant. **This doesn't survive a repo-stratified permutation
check, built specifically because the pooled p-value was far more
extreme than any individual repo's own result (getsentry, the one real
per-repo signal, alone reaches only p=0.0025 on n=19)** — exactly the
mismatch shape a repo-composition confound produces: mlflow alone
supplies 54% of all agent-tagged gap-pairs, repos differ hugely in their
own baseline touch-gap distribution, and the "agent" group's repo mix
differs from the "other" group's by construction. Shuffling the
`is_agent_touch` label *within each repo separately* (preserving each
repo's own agent/other count and gap_days values, 300 draws) places the
real pooled Cliff's δ (0.283) at the **77th percentile** of that null
(mean 0.262, std 0.030), **p=0.465** — unremarkable. The naive pooled
significance is a repo-composition artifact, not evidence of a real
cross-repo effect.

**The one real, surviving result is getsentry alone** (p=0.0025, n=19,
δ=+0.40 — agent-touched entities take longer to be re-touched there) —
a single-repo lead on a small sample, 1 of 4 per-repo tests run in this
pass, unadjusted for multiple comparisons. Not a confirmed finding, and
not consistent with `LitReview.md`'s aggregate direction either.

**Bottom line: this analysis does not replicate `LitReview.md` source
#15's aggregate "agent code removed sooner" finding within this
project's own repos** — at least not from this 10-repo, Python-only,
exploratory pass. This is a genuine non-replication worth stating
plainly, not a failure to find something that's really there; it also
adds a third instance of this project's now-recurring lesson (after the
Findings-1/2 sampling-bias fix and the pre-slope/slope-change placebo
check) that a naive pooled or single-shot result needs a real
composition/randomization check before it goes in a headline.

## Caveats

- **N=4 repos with a usable per-repo test, not independent draws** — the
  pooled row (now shown to be a composition artifact, not a real
  aggregate) was the whole reason a stratified check was built, not an
  afterthought.
- **The "other" comparison group is files agents happen to touch, not a
  repo-wide random sample** (see Bug 1's trade-off above) — this
  analysis answers "what happens after an agent touches a file it
  touches," not "agent-touched files vs. typical files."
- **Coverage is real but partial and repo-dependent** — 3 of 10 repos
  contribute 0 usable gap-pairs for reasons ranging from a documented
  repo restructuring (crewAI) to unexplained zero AST-matcher overlap
  (browser-use, crewAI-tools) - not investigated further this pass.
- **Python only** — the C# side (`EntityHistory.cs`) would need its own
  merge-commit resolution and touch-walk; not attempted here.
- **PR→commit resolution via commit-message pattern matching, not
  GitHub's own PR-commit API** — a rebase-merge workflow (no PR-number-
  bearing commit message at all) would silently under-resolve; not
  distinguished from "PR never merged" in the resolved-rate numbers
  above.

Outputs: `results/analysis/08-21-agent-code-survival-coverage.csv`,
`-gaps.csv` (12,391 rows, one per gap-pair), `-test.csv`,
`-stratified-permutation.csv`.

## Full-corpus follow-up (2026-08-24): a birth-cohort redesign, not just more repos

> **Status: full corpus (99/100 repos, both languages), real data, one
> naive result checked and rejected by stratification before being
> reported as a finding.** Branch: `analysis/agent-code-survival-full-corpus`,
> off `main`. Code: `src/analysis/agent_code_survival_full_corpus.py`.

The pilot above scoped to 10 Python repos and asked "what happens after
an agent touches a file it already touched" - a real question, but not
the one motivating this project's Tier-2 idea: **was an entity *created*
by an agent-authored commit touched more often than one created by a
human, and did it survive** (survival defined here, per direct request,
as: not deleted AND not rewritten past 50% token-overlap loss from its
birth state - not the pilot's "gap until next touch").

**Scope, and why it's cheap this time.** `results/analysis/08-19-entity-history-pooled.csv`
already carries a first/last-touch summary row per lineage for all 100
scaled-corpus repos, both languages - the C# entity-history walk
(`EntityHistory.cs`/`cs_entity_history.py`) already ran for the RQ3
tracker; only the *agent-PR linking* step was Python-only before, not the
underlying walk. Reusing that pooled file means this pass needed one
`git log` per repo (PR->commit resolution, reusing `agent_code_survival.py`'s
already-validated regex) rather than re-walking git history - the
expensive part already paid for once. **99/100 repos** with a local clone
have at least one registered agent PR (65 Python + 34 C#, 3,057 agent PRs
total) and are in scope; the 100th has a clone but 0 agent PRs.

**166,369 lineages labeled, 1,007 agent-born / 165,362 human-born**
(`is_born_agent` = the lineage's own first-touch commit resolves to a
commit this repo's agent-PR registry flags) - `results/analysis/08-24-agent-survival-fc-labeled-lineages.csv`.
Sanity-checked the single largest agent-born contributor before trusting
it: `NewFuture/DDNS` supplies 421/1,007 (42%) from just 10 resolved
commits, one of which (`6c24557`, Copilot, "add task subcommand for
automated scheduled task management") alone created 202 entities across
53 files, 5,471 insertions - a real large feature PR, not a matcher
false-positive (confirmed by reading the commit message and diffstat
directly).

### Finding 1: agent-born code IS touched more often - real, and it survives the composition check this time

| Metric | Pooled Cliff's δ | Naive pooled p | Stratified-permutation percentile | Stratified p |
|---|---|---|---|---|
| Touches after birth (raw count) | **+0.117** | 9.0×10⁻²⁰ | **100th** (above every one of 300 within-repo-shuffled draws) | **0.0066** |
| Touches per day since birth (age-normalized) | **+0.126** | 1.4×10⁻²² | **100th** | **0.0066** |

Unlike every pooled result this project has checked before (the
pre-slope/slope-change placebo, this doc's own pilot mlflow result, and
the deletion result immediately below), **this one does not evaporate
under repo-stratified shuffling** - the real pooled effect sits above the
entire null distribution built by shuffling `is_born_agent` within each
repo separately (300 draws), not inside it. Agent-born entities being
touched again more often than human-born entities, within the same
repos, is the one part of this analysis with real cross-repo support.
Per-repo results are mixed in direction (`microsoft/testfx` alone:
δ=+0.47, p≈2×10⁻²⁴⁵ on n=11,881; several smaller repos lean the other
way), consistent with a real but uneven effect, not a single repo
driving a spurious pooled number the way mlflow did in the pilot.

Outputs: `results/analysis/08-24-agent-survival-fc-freq-touches_after_birth.csv`,
`-touches_per_day.csv`, and each metric's own `-stratified-permutation.csv`.

### Finding 2: "survived" by deletion alone does NOT survive the same check - a repo-composition artifact, same failure mode as before

Naive pooled: 6.95% of agent-born lineages were later deleted vs. 9.51%
of human-born (Fisher p=0.005, OR=0.71 - agent-born deleted *less*
often). This looked like a real result until stratified the same way as
Finding 1: the real pooled percentage-point difference (-2.56pp) lands at
the **25th percentile** of the repo-shuffled null (p=0.51) - well inside
it, not extreme. `microsoft/testfx` alone is a dramatic outlier in the
*opposite* direction (36.5% of its 85 agent-born lineages deleted vs.
0.6% of its human-born, OR=99, p=2×10⁻⁴⁴) that the naive pooled number
doesn't reflect - exactly the composition-confound shape this project's
convention (established by the pilot's mlflow result and
`HeterogeneityExplainersPart2.md`'s placebo work) says to check before
reporting. **No real cross-repo deletion-rate difference found.**

Outputs: `results/analysis/08-24-agent-survival-fc-deletion.csv`,
`-deletion-stratified-permutation.csv`.

### Finding 3: the requested full survival definition (not deleted AND <50% modified) - no signal either way, now confirmed on both languages

The "modified >50%" half needed a new per-lineage computation not in the
pooled file: Jaccard token-similarity between each entity's birth-state
source and its last-known-state source (reusing the matcher's own
similarity metric and `py_entity_history.py`'s batched
`git cat-file --batch` blob-fetch - the same fix that took a documented
68-minute single-`git-show`-per-touch stall down to seconds, applied
here to one birth/last pair per lineage). **First landed Python-only,
extended to C# same day** via `cs_entity_history.py`'s Roslyn-batch path
(`_run_roslyn_batch`, one `dotnet` subprocess call per repo covering all
of that repo's needed blobs at once - the same per-repo batching
Finding 1/2's git-log resolution and this Python path already use, not a
per-pair subprocess). Survived = similarity ≥ 0.5 AND not deleted.

Candidates: all 937 agent-born lineages still alive (both languages),
plus a per-repo random sample of human-born alive lineages (3x the
repo's own agent-alive count, capped by availability - 2,751 lineages,
32 repos total, 10 of them C#) - not all ~150K alive human-born
lineages, to keep the added git/AST/Roslyn work bounded while preserving
the repo-stratified design Finding 1/2 already established as necessary.
**3,688/3,688 candidates resolved (100%, both languages)** - every
birth/last qualified-name pair was found in its recorded commit's own
entity inventory, no silent misses on either extraction path.

**Pooled: 96.7% of agent-born lineages survived vs. 96.9% of
human-born** (Fisher p=0.75). Repo-stratified permutation: real
percentage-point difference (-0.22pp) sits at the **37th percentile** of
the null (p=0.75) - solidly unremarkable, same conclusion as the
Python-only pass before C# was added (97.0% vs. 96.8%, p=0.91/0.94).
**No detectable difference by this definition, in either direction, on
either language.** Both cohorts overwhelmingly survive (>96%) within
this corpus's observation window - token-level rewrite-past-50% and
outright deletion are both rare events for either group, at least among
entities still alive to check. One per-repo exception worth naming, not
correcting for multiple comparisons: `microsoft/testfx` alone shows
agent-born surviving *less* often (92.6% vs. 100%, p=0.004, n=54/162) -
a single-repo lead in the opposite direction from nothing, same
"interesting but uncorrected" status as the pilot's getsentry result.

Outputs: `results/analysis/08-24-agent-survival-fc-modification-similarity.csv`
(per-lineage similarity + resolution status, both languages),
`-full-survival.csv`, `-full-survival-stratified-permutation.csv`.

### Bottom line

Splitting the request's two questions gives two different answers, not
one combined "does or doesn't replicate":

- **"Touched more often" - yes, and it's the one result in this entire
  analysis (pilot or full-corpus) that survives a repo-composition
  check.** Real, if modest (δ≈0.12), and directionally consistent with
  `LitReview.md` source #15's "agents churn more" finding (7.33% vs.
  4.10%), though not the same metric.
- **"Survived longer," under the requested modified->50%-or-deleted
  definition - no.** Neither cohort shows a real survival disadvantage
  relative to the other; the one component that looked different
  (deletion rate) turned out to be a composition artifact once checked,
  and the modification-based half shows no gap at all.

Read together: agent-created code in this corpus gets revisited more,
but when it's revisited, it isn't disproportionately rewritten past
recognition or deleted, relative to human-created code in the same
repos. "Touched more" and "survives worse" are not the same claim, and
this data separates them.

### Caveats specific to this pass

- **`is_born_agent` depends on the same PR->commit resolution as the
  pilot** - real, variable resolution rates per repo (see the pilot's own
  table above), not distinguished here from "PR never merged."
- **The modification-similarity candidate set is partially sampled**
  (all agent-alive, a 3x-capped human sample, both languages) - not a
  full-corpus number the way Findings 1/2 are, though it does now cover
  both languages rather than Python only.
- **A single-touch lineage (no touches after birth) trivially "survives"
  by the modification definition** (similarity of a snapshot against
  itself = 1.0) - correct by the definition as stated, but worth naming:
  most of both cohorts' high survival rate reflects entities that simply
  haven't been touched again yet within the walked history, not
  necessarily evidence of durable, unmodified code under active use.
- **Right-censoring**: "survived" and "touched more" are both measured
  against each repo's walked history, not a fixed follow-up window -
  an entity born recently has had less time to be either touched again
  or rewritten than one born early, a real confound `touches_per_day`
  partially addresses (age-normalized) but the modification-survival
  check does not.

## GLMM companion to the full-corpus follow-up (2026-08-24)

> Additive, not a replacement - Findings 1-3 above (the repo-stratified
> permutation checks) stand as-is. Full methodology and shared
> verification recipe: `writing/MixedEffectsMethodology.md`. Code:
> `src/analysis/agent_code_survival_mixed_effects.py`.

**Two different questions, not two versions of the same one**: the
existing repo-stratified permutation test asks "is the pooled point
estimate an artifact of which repos happen to be in the agent vs. human
bucket" (robustness). A GLMM (generalized linear mixed model) with
`full_name` as a random intercept asks "what is the `is_born_agent`
effect, accounting for clustering from the start, and how much do repos
vary around it" (effect size + between-repo heterogeneity). Neither
replaces the other.

**A real methodological difference from the rest of this mixed-effects
layer, not just a naming detail**: this uses
`statsmodels.genmod.bayes_mixed_glm` (variational-Bayes GLMM fitting),
not `MixedLM` (REML) - a different inferential framework. Output is a
posterior mean/SD, not a classical coefficient/CI, named as such below.

**`ended` (binary, all 166,369 lineages, both languages)**: posterior
mean for `is_born_agent` = -0.098 (SD 0.125) - direction-consistent with
Finding 2's naive-pooled read (agent-born deleted somewhat less), but
Finding 2 already showed that direction doesn't survive a
repo-composition check, and this GLMM's own posterior SD is wide enough
that -0.098 is not distinguishable from zero either. **Point estimate is
stable across repeated runs; the optimizer's own `success` flag is not**
(true on some runs, false on others, no code change between runs) -
reported with this caveat rather than picking whichever run looked
cleanest.

**`full_survival` (binary, 3,688-row resolved modification-similarity
subset)**: posterior mean for `is_born_agent` = -0.052 (SD 0.185),
consistently reproducible across runs, optimizer converged cleanly every
time. Small and not distinguishable from zero - agrees with Finding 3's
null result (97.0% vs. 96.8%/96.7% vs. 96.9% survived, no real
difference either way).

**`touches_after_birth` (count) - genuinely did not converge, no
reliable estimate reported.** This is the one place this mixed-effects
layer produced a real fitting failure rather than a null/small result:
two limitations compounded. (1) statsmodels' `bayes_mixed_glm` has no
negative-binomial option, and `touches_after_birth` is severely
overdispersed (variance/mean ≈ 6, Poisson assumes ≈1). (2) The module
also has no offset mechanism at all (discovered only by trying it, not
anticipated when this was planned) - `log(age_days+1)` had to be
included as an ordinary covariate rather than the statistically correct
fixed-coefficient offset the original plan called for. Tried with and
without feature scaling; the fit either collapses toward a degenerate
near-zero-variance posterior or diverges to numerical overflow depending
on the run. **No effect estimate for `touches_after_birth` is reported
from this GLMM** - Finding 1's own repo-stratified permutation result
(the real, robust finding: agent-born entities touched more, p=0.0066)
is unaffected and remains the standing result for touch frequency.

Full output, including the group-size diagnostics (11/32 repos with <5
rows in at least one cohort for the `full_survival` model, flagged not
silently absorbed): `results/analysis/08-24-agent-survival-fc-mixed-effects.csv`,
`08-24-agent-survival-fc-mixed-effects-group-diagnostics.csv`.

## Finding 4: change entropy — a fourth naive-pooled result, and a fourth composition artifact (2026-08-24)

**Data used**: `results/analysis/08-24-agent-survival-fc-labeled-lineages.csv`
(166,369 lineages, 1,007 agent-born / 165,362 human-born — same labeled
pool Findings 1-3 above use, re-confirmed current before this run: no
newer `08-24-agent-survival-fc-labeled-lineages.csv` or
`08-19-entity-history-pooled.csv` had landed). `change_entropy` (Shannon
entropy over normalized inter-touch time gaps — `EntityLineage
.change_entropy` in `src/inhouse/entity_matching.py`, a proxy for
Hassan's entropy-of-changes, ICSE 2009 — see that property's own
docstring) was already a column on both files; nobody had compared it
between cohorts before this pass. Added as a third outcome to
`agent_code_survival_full_corpus.py`'s existing `frequency_test`/
`stratified_permutation_test` harness (same functions Finding 1 uses,
unmodified) rather than a new computation.

**Coverage, checked before trusting anything**: `change_entropy` is
`None` below `MIN_TOUCHES_FOR_ENTROPY=3` (a lineage touched only once or
twice has 0-1 gaps — not enough to call anything "spread out" or
"clustered"). At this corpus's full scale, **9.44% of all lineages
clear the bar (15,713/166,369)** — up from the 7.5% `Results.md`
measured at the smaller 21-repo cut, but still a small, non-random
minority: entities that get touched at least 3 times are inherently the
more actively-maintained tail of the corpus, not a representative sample
of it. Coverage differs by cohort too — **12.02% of agent-born lineages
(121/1,007) vs. 9.43% of human-born (15,592/165,362)** — consistent with
Finding 1's own result (agent-born entities get touched again more
often, so more of them clear a touch-count floor). Every number below is
computed only on this 15,713-lineage resolved subset, same convention as
Finding 3's modification-similarity subsample.
Output: `results/analysis/08-24-agent-survival-fc-entropy-coverage.csv`.

**Naive pooled result looked real**: median entropy 0.653 (agent-born,
n=121) vs. 0.977 (human-born, n=15,592), Cliff's δ=-0.195, Mann-Whitney
p=0.00022 — agent-born entities' touches read as *more clustered in
time* (lower entropy) than human-born entities', not more evenly spread
out. `results/analysis/08-24-agent-survival-fc-freq-change_entropy.csv`.

**Does not survive the repo-stratified permutation check.** The real
pooled δ=-0.195 lands at the **49.3rd percentile** of the null built by
shuffling `is_born_agent` within each repo (300 draws) — dead center,
empirical p=0.99. This is the same failure mode as Finding 2's deletion
result: a naive pooled p<0.001 that repo composition alone fully
explains once controlled for.
Output: `results/analysis/08-24-agent-survival-fc-freq-change_entropy-stratified-permutation.csv`.

One per-repo result worth naming, same "interesting but uncorrected"
status as Finding 3's `microsoft/testfx` and getsentry's pilot result:
**`dotnet/aspire` alone shows the opposite direction and a real-looking
per-repo effect** (median entropy 1.997 agent-born vs. 0.999 human-born,
δ=+0.719, p=0.00014, n=10 vs. 159) — agent-born touches on this one repo
read as *more* evenly spread out, not more clustered. Consistent with
this repo's general pattern of being an outlier across this project's
analyses (see [[phase1b_aspire_excluded]] for its unrelated GitHub
Search API exclusion) rather than evidence either direction generalizes.

**Bottom line: no real cross-repo change-entropy difference between
agent-born and human-born code.** This is the fourth time a naive pooled
result in this analysis (and the third in this specific
touched-more/survives-worse/entropy trio) initially looked significant
and evaporated under stratification — reinforcing, not just repeating,
the project's now-standard read that Finding 1 (touch frequency) is the
outlier: the one outcome tested here that's both naive-pooled significant
*and* stratification-robust. Coverage is also a real limitation
independent of the null result: at 9.44%, any change-entropy finding —
had one survived — would describe only the actively-touched minority of
the corpus, not the median (single-touch) entity.
