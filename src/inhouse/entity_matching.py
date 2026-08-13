"""
Language-agnostic entity-lineage matcher: given a chronological sequence of
per-commit entity inventories for one file, reconstructs which entity at
commit N+1 is "the same" as which entity at commit N, even across a rename
or signature change - the identity problem git itself doesn't solve below
the file level (Writing/RQ3_CodeTracking.md, "why this is harder than it
sounds").

Two-tier match per commit step, per RQ3_CodeTracking.md's design decision:
1. Exact: identical qualified_name at consecutive commits - same scope,
   same name, unambiguously the same entity (qualified_name is derived from
   AST position/containment, so a coincidental full collision on two
   genuinely different entities in the same commit can't happen).
2. Fuzzy: for entities that don't exact-match, pairwise token-overlap
   (Jaccard) similarity on each entity's source-body tokens, greedily
   paired above SIMILARITY_THRESHOLD - the same shape of heuristic
   CodeShovel uses (~75% string-similarity threshold, see
   Writing/codeaging.md Theme 2), used here as the starting point before
   Stage 3's empirical tuning against a hand-built oracle.

Deliberately does NOT attempt cross-file matching (an extract-to-new-file
refactor is not tracked as continuous) - out of scope by design, since the
caller walks one file's `git log --follow` history at a time
(Writing/RQ3_CodeTracking.md's "Commit source" decision). A file rename
IS handled: the file's own path change already flows through into a new
qualified_name for every entity it contains, so those entities go through
the same fuzzy-match path as an in-file rename.
"""

import math
import re
from dataclasses import dataclass, field
from datetime import datetime

SIMILARITY_THRESHOLD = 0.75  # CodeShovel's published threshold - starting
# point, tuned empirically in Stage 3 (validate_entity_matching.py) against
# a hand-built oracle, not treated as final here.

MIN_TOUCHES_FOR_ENTROPY = 3  # need >=2 gaps for a "spread" to mean anything


def _parse_date(iso_date):
    """Commit dates arrive as git's %aI format (strict ISO 8601 with
    timezone, e.g. "2026-06-22T13:22:46-03:00") - fromisoformat handles
    that directly in Python 3.11+."""
    return datetime.fromisoformat(iso_date)

_TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokenize(source_text):
    """Lowercased identifier/keyword tokens as a set - "token-overlap
    similarity over the body" per RQ3_CodeTracking.md's matching-heuristic
    decision. A set (not a multiset/Counter): repeated tokens inside one
    body count once, matching a standard Jaccard-over-vocabulary framing
    rather than weighting by frequency - simplest version that's still a
    real overlap measure, not a guess at what "token-overlap" should mean
    more elaborately."""
    return frozenset(t.lower() for t in _TOKEN_RE.findall(source_text))


def jaccard(a, b):
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class EntitySnapshot:
    """One entity's state as of one commit - the matcher's input unit.
    `tokens` drives fuzzy matching; `param_count`/`loc` are carried through
    onto touches for later metrics (Stage 2) but don't affect matching
    itself. `kind` separates the class-granularity pass from the
    method/function-granularity pass (Writing/RQ3_CodeTracking.md: "both
    method and class, from the start... two separate matching passes")."""
    qualified_name: str
    kind: str  # "class" | "callable" (method or module-level function)
    name: str
    param_count: int | None
    loc: int
    tokens: frozenset


@dataclass
class EntityTouch:
    commit_sha: str
    commit_date: str
    qualified_name: str
    change_type: str  # "created" | "modified" | "renamed" | "moved"
    similarity: float | None  # None for exact/created; the match score otherwise
    param_count: int | None
    loc: int


@dataclass
class EntityLineage:
    """One entity's reconstructed identity across a file's history. `kind`
    matches EntitySnapshot.kind. `ended` is True if the entity was no
    longer found in the file's later inventories (deleted, or the file
    itself was deleted) - False means it was still present as of the last
    commit this lineage was built against (which may or may not be the
    repo's current HEAD, depending on what the caller processed)."""
    lineage_id: int
    kind: str
    touches: list = field(default_factory=list)
    ended: bool = False

    @property
    def first_touch(self):
        return self.touches[0]

    @property
    def last_touch(self):
        return self.touches[-1]

    @property
    def modification_count(self):
        """Touch count including creation - a lineage seen exactly once has
        modification_count=1, not 0, matching "how many times has this
        entity's state been recorded" rather than "how many times after
        creation was it changed." Stage 2 can subtract 1 if a
        changes-after-creation framing is wanted instead."""
        return len(self.touches)

    def age_days(self, as_of):
        """Days between first and last touch - Eick et al.'s code-decay-
        index "average age" framing (Writing/codeaging.md Theme 1). `as_of`
        is required, not defaulted to `datetime.now()`: a still-live
        lineage's age should be measured against the REPO's latest known
        commit (what the caller actually walked up to), not wall-clock
        "now" - those differ whenever the walk doesn't reach the repo's
        current HEAD, and silently using wall-clock time would make age
        depend on when this tool happens to be run rather than on the data
        itself. Callers pass the repo's HEAD commit date for a still-live
        lineage, or the lineage's own last_touch date if `ended`."""
        end = _parse_date(self.last_touch.commit_date) if self.ended else as_of
        start = _parse_date(self.first_touch.commit_date)
        return (end - start).days

    @property
    def relative_churn(self):
        """modification_count normalized by the entity's current (most
        recent) size - Nagappan & Ball (ICSE 2005), cited in
        Writing/codeaging.md as the reason to prefer size-normalized churn
        over a raw modification count: "relative churn measures... strongly
        predict defect density... while absolute churn is a poor
        predictor." Normalizes by the LAST touch's LOC specifically (not an
        average across touches) - "how much has this entity been touched
        relative to what it looks like today," a deliberate choice among
        several defensible options, not the only one. None (not a
        division-by-zero crash or a silent 0) if the last known LOC is 0,
        which can happen for a since-emptied entity."""
        loc = self.last_touch.loc
        if not loc:
            return None
        return self.modification_count / loc

    @property
    def change_entropy(self):
        """Shannon entropy (log2) over the normalized inter-touch time
        gaps, treating each gap's share of the lineage's total span as a
        probability. This is a SIMPLIFIED PROXY for Hassan's entropy-of-
        changes (ICSE 2009, Writing/codeaging.md Theme 3) - the original
        computes entropy over amount-of-code-changed within fixed time
        windows, not gap-timing alone; this is "how evenly spread out in
        time were this entity's touches," a related but narrower question,
        named accordingly so it isn't mistaken for a faithful
        reimplementation. None (not 0) below MIN_TOUCHES_FOR_ENTROPY - a
        lineage with 1-2 touches has 0-1 gaps, too few for "spread" to mean
        anything; silently reporting 0 there would read as "maximally
        regular" rather than "not enough data," so it's withheld instead."""
        if len(self.touches) < MIN_TOUCHES_FOR_ENTROPY:
            return None
        dates = [_parse_date(t.commit_date) for t in self.touches]
        total_span = (dates[-1] - dates[0]).total_seconds()
        if total_span <= 0:
            return None
        gaps = [
            (dates[i + 1] - dates[i]).total_seconds()
            for i in range(len(dates) - 1)
        ]
        probs = [g / total_span for g in gaps if g > 0]
        if not probs:
            return None
        return -sum(p * math.log2(p) for p in probs)

    @property
    def review_count(self):
        """Always None - "number of reviews per method" needs Track B's
        deeper per-PR diff/review-thread data, which isn't built
        (Writing/ProjectStatus.md §7 item 5, unchanged since 2026-07-21).
        codeaging.md's own conclusion: "I found no single tool that outputs
        'number of reviews per method' out of the box - this is a genuine
        gap." An explicit placeholder column, not a fabricated proxy (e.g.
        not silently substituting modification_count or PR count as a
        stand-in for something it doesn't measure)."""
        return None

    def pre_post_touch_counts(self, intervention_date):
        """Real per-touch split against `intervention_date`, the thing
        Stage 6's windowed cut explicitly couldn't do (it only had each
        lineage's first/last touch date pooled, not every individual
        touch). Returns (pre_count, post_count, pre_window_days,
        post_window_days).

        `pre_window_days`/`post_window_days` are the REAL observed span on
        each side - `intervention_date - first_touch` and
        `last_touch - intervention_date`, each clipped at 0 - not a fixed
        window. This is required, not optional, for any figure comparing
        "churn before" vs. "churn after": the two windows are different
        lengths for every repo (a repo whose intervention date is 3 years
        old has a much longer post-window than one intervened last month),
        so a raw touch-count comparison would conflate "touched more
        often" with "observed for longer." Callers should divide by these
        to get touches/day before comparing across entities or repos.

        A touch exactly ON `intervention_date` counts as post (`>=`), same
        convention `entity_history_windowed_cut.py`'s `classify()` already
        uses for lineage-level bucketing - kept consistent rather than
        picking a different boundary rule for touch-level counting."""
        pre_count = post_count = 0
        for touch in self.touches:
            touch_date = _parse_date(touch.commit_date)
            if touch_date >= intervention_date:
                post_count += 1
            else:
                pre_count += 1

        first_date = _parse_date(self.first_touch.commit_date)
        last_date = _parse_date(self.last_touch.commit_date)
        pre_window_days = max(0.0, (intervention_date - first_date).total_seconds() / 86400)
        post_window_days = max(0.0, (last_date - intervention_date).total_seconds() / 86400)

        return pre_count, post_count, pre_window_days, post_window_days


def _greedy_fuzzy_match(unmatched_prev, unmatched_curr, threshold):
    """Pairwise Jaccard over every (prev, curr) unmatched pair, sorted
    descending, assigned greedily one-to-one above threshold. Greedy (not
    optimal bipartite matching) - simplest version that behaves correctly
    for the common case (few renames per commit step, not a mass rewrite);
    a real bipartite-optimal matcher would be more work for a difference
    that's very unlikely to matter at this problem's scale (per-file,
    per-commit entity counts are small). Returns
    {curr_key: (prev_key, similarity)} for matched pairs only."""
    pairs = []
    for pk, prev in unmatched_prev.items():
        for ck, curr in unmatched_curr.items():
            if prev.kind != curr.kind:
                continue
            sim = jaccard(prev.tokens, curr.tokens)
            if sim >= threshold:
                pairs.append((sim, pk, ck))
    pairs.sort(key=lambda t: t[0], reverse=True)

    matched = {}
    used_prev, used_curr = set(), set()
    for sim, pk, ck in pairs:
        if pk in used_prev or ck in used_curr:
            continue
        used_prev.add(pk)
        used_curr.add(ck)
        matched[ck] = (pk, sim)
    return matched


def match_file_history(commit_inventories, threshold=SIMILARITY_THRESHOLD):
    """commit_inventories: chronological (oldest-first) list of
    (commit_sha, commit_date, {qualified_name: EntitySnapshot}) - one entry
    per commit that touched this file, already filtered to commits where
    the file exists (the caller stops feeding entries once the file is
    deleted). Returns (lineages, next_lineage_id) - a flat list of
    EntityLineage covering every entity ever seen across the sequence,
    both still-live and ended.

    Algorithm: walk commits in order, maintaining `live` = {qualified_name
    at last-seen commit -> (lineage, EntitySnapshot)}. Each step: exact
    qualified_name matches continue their lineage directly; leftover
    unmatched prev/curr entities go through fuzzy matching
    (_greedy_fuzzy_match); still-unmatched curr entities start new
    lineages; still-unmatched prev entities' lineages end here (not
    fabricated a synthetic "deleted" touch - the lineage's own `touches`
    list and `ended` flag carry that information)."""
    live = {}  # qualified_name -> (EntityLineage, EntitySnapshot)
    finished = []
    next_id = 0

    for commit_sha, commit_date, curr_inv in commit_inventories:
        matched_curr = set()
        # Old qnames (keys into `live` before this commit) resolved this
        # round, whether the entity actually changed or not - used at the
        # end of the round to tell "no successor found -> lineage ends"
        # apart from "found but content identical -> still alive, just no
        # new touch recorded."
        resolved_prev_keys = set()

        # Tier 1: exact qualified_name match. A file-touching commit
        # re-extracts the WHOLE file's inventory, so most entities in a
        # busy file will exact-match here on every commit even though only
        # one sibling entity actually changed - only append a touch when
        # the entity's own tokens/signature actually differ from last time,
        # otherwise just refresh `live`'s stored snapshot silently. Without
        # this check, every entity in a file would get a spurious
        # "modified" touch on every commit that touched ANYTHING else in
        # that file, badly inflating modification_count.
        for qname, snap in curr_inv.items():
            if qname in live:
                lineage, prev_snap = live[qname]
                changed = (
                    snap.tokens != prev_snap.tokens
                    or snap.param_count != prev_snap.param_count
                )
                if changed:
                    lineage.touches.append(EntityTouch(
                        commit_sha=commit_sha, commit_date=commit_date,
                        qualified_name=qname, change_type="modified",
                        similarity=None, param_count=snap.param_count,
                        loc=snap.loc,
                    ))
                live[qname] = (lineage, snap)
                matched_curr.add(qname)
                resolved_prev_keys.add(qname)

        unmatched_prev = {
            k: v[1] for k, v in live.items() if k not in resolved_prev_keys
        }
        unmatched_curr = {
            k: v for k, v in curr_inv.items() if k not in matched_curr
        }

        # Tier 2: fuzzy match on whatever's left - these always represent a
        # real change (a rename/move can't produce an identical
        # qualified_name, which would've been caught by tier 1), so a touch
        # is always recorded here.
        fuzzy = _greedy_fuzzy_match(unmatched_prev, unmatched_curr, threshold)
        for ck, (pk, sim) in fuzzy.items():
            lineage, prev_snap = live.pop(pk)
            snap = unmatched_curr[ck]
            change_type = "renamed" if prev_snap.name != snap.name else "moved"
            lineage.touches.append(EntityTouch(
                commit_sha=commit_sha, commit_date=commit_date,
                qualified_name=ck, change_type=change_type,
                similarity=sim, param_count=snap.param_count, loc=snap.loc,
            ))
            live[ck] = (lineage, snap)
            matched_curr.add(ck)
            resolved_prev_keys.add(pk)

        # Remaining curr entities: brand new lineages.
        new_keys = set()
        for qname, snap in curr_inv.items():
            if qname in matched_curr:
                continue
            lineage = EntityLineage(lineage_id=next_id, kind=snap.kind)
            next_id += 1
            lineage.touches.append(EntityTouch(
                commit_sha=commit_sha, commit_date=commit_date,
                qualified_name=qname, change_type="created",
                similarity=None, param_count=snap.param_count, loc=snap.loc,
            ))
            live[qname] = (lineage, snap)
            new_keys.add(qname)

        # Any `live` entry whose key wasn't resolved (exact or fuzzy) and
        # isn't one of this round's brand-new keys had no successor in
        # curr_inv at all - that lineage genuinely ends here.
        resolved_or_new = resolved_prev_keys | new_keys
        for pk in [k for k in live if k not in resolved_or_new]:
            lineage, _snap = live.pop(pk)
            lineage.ended = True
            finished.append(lineage)

    # Whatever's still live at the end of the sequence is not "ended" -
    # still present as of the last commit processed.
    for lineage, _snap in live.values():
        finished.append(lineage)

    return finished
