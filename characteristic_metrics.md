# Characteristic Metrics in Literature

The index tables below list every metric by type. Click a metric name to jump to its full specification — definition, unit, data requirements, exact computation, step-by-step procedure, and caveats — in the sections that follow. All detail lives in those sections; the tables are only for orientation. Reference keys resolve in the [References](#references) list.

**Notation** (used throughout the specifications): `t₀ = pull_request.created_at`, `t₁ = pull_request.closed_at`, `A = pull_request.user` (the author/contributor), `R = pull_request.repo_id`. Formulas reference the local schema tables (`pull_request`, `pr_commits`, `pr_commit_details`, `pr_timeline`, `pr_comments`, `pr_reviews`, `pr_review_comments`, `related_issue`, `issue`, `user`, `repository`, `pr_task_type`); data not in the schema is marked **REST** or **GQL** with the exact endpoint. The test-file pattern is `TEST_RE = (^|/)(tests?|specs?)/ | _test\. | \.test\. | Test.*\.java`. Bots are identified by `login` ending in `[bot]` or matching a curated bot list. General caveat: profile-level fields (followers, company) reflect *collection-time* state; point-in-time values require replaying GH Archive events up to `t₀`.

## Index

### Pull Request Characteristics (PR-Level Signals)

| Metric | Definition | Ref |
|---|---|---|
| [`bug_fix`](#bug_fix--does-the-pr-fix-a-bug) | Whether the PR's purpose is to repair a defect | [Z22] |
| [`description_length`](#description_length--length-of-the-pr-description) | Size of the natural-language description provided at open | [Y15] |
| [`hash_tag`](#hash_tag--does-the-description-reference-an-issue-by-number) | Whether the description references an issue by number (`#N`) | [Z22] |
| [`num_participants`](#num_participants--participants-in-the-pr-discussion) | Distinct humans commenting on the PR in any channel | [T14] |
| [`ci_exists`](#ci_exists--does-the-pr-run-ci) | Whether any CI system ran against the head commit | [V15] |
| [`ci_latency`](#ci_latency--time-until-the-first-ci-result) | Time from PR creation to the first finished CI build | [Y15] |
| [`part_num_code`](#part_num_code--participants-in-code-level-discussion) | Distinct users in code-anchored discussion (inline + commit comments) | [Z22] |
| [`num_code_comments`](#num_code_comments--number-of-inline-code-comments) | Review comments anchored to specific diff lines | [Z22] |
| [`reopen_or_not`](#reopen_or_not--was-the-pr-reopened) | Whether the PR was closed and subsequently reopened | [Z22] |
| [`rework`](#rework--post-review-rework) | New work pushed after the first review feedback | [G15] |
| [`friday_effect`](#friday_effect--was-the-pr-submitted-on-a-friday) | Whether the PR was opened on a Friday | [S05], [Z22] |
| [`has_comments`](#has_comments--does-the-pr-have-any-comment) | Whether any discussion or inline comment exists | [Z22] |
| [`num_comments`](#num_comments--number-of-discussion-comments) | Count of conversation-thread comments | [G14] |
| [`num_comments_con`](#num_comments_con--contributors-own-discussion-comments) | Discussion comments written by the author | [Z22] |
| [`at_tag`](#at_tag--does-the-pr-text--mention-anyone) | Whether an `@username` mention appears in the PR text | [Y15] |
| [`num_code_comments_con`](#num_code_comments_con--contributors-inline-code-comments) | Inline code comments written by the author | [Z22] |
| [`ci_test_passed`](#ci_test_passed--did-all-ci-builds-pass) | Whether every CI check on the final head commit succeeded | [V15] |
| [`comment_conflict`](#comment_conflict--is-a-merge-conflict-discussed) | Whether a merge conflict is mentioned in the discussion | [Z22] |
| [`num_commits_open` / `_close`](#num_commits_open--num_commits_close--commit-counts-at-open-and-close) | Commit count at open vs at close | [G14] |
| [`src_churn_open` / `_close`](#src_churn_open--src_churn_close--code-churn-at-open-and-close) | Lines added + deleted, at open vs at close | [G14] |
| [`files_changed_open` / `_close`](#files_changed_open--files_changed_close--files-touched-at-open-and-close) | Distinct files modified, at open vs at close | [G14] |
| [`commits_touched_open` / `_close`](#commits_touched_open--commits_touched_close--recent-activity-on-touched-files) | Recent base-repo activity on the touched files ("hotness") | [G14] |
| [`churn_addition_open` / `_close`](#churn_addition_open--churn_addition_close--added-lines) | Lines added, at open vs at close | [G14] |
| [`churn_deletion_open` / `_close`](#churn_deletion_open--churn_deletion_close--deleted-lines) | Lines deleted, at open vs at close | [G14] |
| [`test_churn_open` / `_close`](#test_churn_open--test_churn_close--test-code-churn) | Test-code lines changed, at open vs at close | [G14] |
| [`test_inclusion_open` / `_close`](#test_inclusion_open--test_inclusion_close--does-the-pr-touch-tests) | Whether any test file is modified | [G14], [T14] |

### Developer Characteristics

| Metric | Definition | Ref |
|---|---|---|
| [`first_pr`](#first_pr--is-this-the-authors-first-pr-in-the-repository) | Whether this is the author's first PR in the repository | [Z22] |
| [`prior_review_num`](#prior_review_num--authors-prior-reviews-in-the-project) | PRs in the repository the author reviewed before this one | [Z22] |
| [`core_member`](#core_member--is-the-author-a-core-member) | Whether the author holds commit/maintainer rights | [G14] |
| [`first_response_time`](#first_response_time--time-to-first-human-response) | Time from open to the first non-author response | [Y15] |
| [`contrib_gender`](#contrib_gender--inferred-gender-of-the-contributor) | Author gender inferred from profile information | [TR17] |
| [`contrib_affiliation`](#contrib_affiliation--contributors-organizational-affiliation) | Organization the author belongs to | [B16] |
| [`same_affiliation`](#same_affiliation--do-contributor-and-integrator-share-an-affiliation) | Whether author and integrator share an organization | [B16] |
| [`inte_affiliation`](#inte_affiliation--integrators-organizational-affiliation) | Organization the integrator belongs to | [B16] |
| [`social_strength`](#social_strength--contributors-social-connectedness-to-the-core-team) | Fraction of the core team the author interacted with (90 d) | [T14] |
| [`prev_pullreqs`](#prev_pullreqs--authors-previous-prs-in-the-repository) | PRs the author submitted to the repository before this one | [G14] |
| [`followers`](#followers--authors-follower-count) | Author's GitHub follower count | [T14] |
| [`same_user`](#same_user--did-the-author-merge-their-own-pr) | Whether contributor and integrator are the same person | [Z22] |

### Project Characteristics

| Metric | Definition | Ref |
|---|---|---|
| [`sloc`](#sloc--project-size-in-executable-lines) | Executable lines of code of the project at the base revision | [G14] |
| [`team_size`](#team_size--active-core-team-size) | People actively integrating code in the prior 90 days | [G14] |
| [`project_age`](#project_age--project-age-at-submission) | Time from repository creation to the PR's creation | [G14] |
| [`open_pr_num`](#open_pr_num--open-pr-queue-length-at-submission) | PRs open in the repository at the moment of creation | [G14] |
| [`integrator_availability`](#integrator_availability--recency-of-integrator-activity) | Recency of the two most active integrators at submission | [Z22] |
| [`test_lines_per_kloc`](#test_lines_per_kloc--test-code-density) | Test code lines per KLOC of project code | [G14] |
| [`test_cases_per_kloc`](#test_cases_per_kloc--test-case-density) | Individual test cases per KLOC | [G14] |
| [`asserts_per_kloc`](#asserts_per_kloc--assertion-density) | Assertion statements per KLOC | [G14] |
| [`perc_external_contribs`](#perc_external_contribs--share-of-external-contributions) | Share of recently merged PRs from outside the core team | [G14] |
| [`requester_succ_rate`](#requester_succ_rate--authors-historical-merge-rate) | Fraction of the author's previously closed PRs that were merged | [G14] |

### Derived Features for the APR Signal Set

| Metric | Type | Definition | Ref |
|---|---|---|---|
| [`rejected`](#rejected--pr-closed-without-merge) | Outcome | PR closed without being merged (the outcome label) | [G14] |
| [`diffhunk_size`](#diffhunk_size--total-modified-lines-within-diff-hunks) | Diff-Level | Changed lines summed over all hunks of the final diff | [G14] |
| [`ngrams`](#ngrams--bigrams-and-trigrams-from-pr-text) | Textual | Bag of bigrams/trigrams from the PR's natural-language text | [H12] |
| [`keyword_density`](#keyword_density--density-of-process-keywords) | Textual | Fraction of tokens from a fixed process-keyword lexicon | [Z22] |
| [`duplicate_code`](#duplicate_code--clone-detected-in-pr-code) | Static Quality | Whether the PR introduces or touches duplicated code | [RC09] |
| [`unused_vars`](#unused_vars--unused-variables-in-touched-code) | Static Quality | Variables declared but never referenced in touched files | [AY08] |
| [`large_class`](#large_class--oversized-class-touched) | Design & Arch. | Whether a touched class is oversized relative to the repo | [F99] |
| [`long_method`](#long_method--long-method-touched) | Design & Arch. | Whether a touched method exceeds 100 lines | [F99] |
| [`god_object`](#god_object--god-class-touched) | Design & Arch. | Whether a touched class matches the God Class strategy | [VA09] |
| [`interaction_count`](#interaction_count--total-pr-interactions) | Social | Total recorded activity on the PR across its lifetime | [T14] |
| [`num_participants` (APR)](#num_participants-apr-variant--distinct-participants-all-channels) | Social | Distinct participants across all channels, incl. commits/events | [T14] |
| [`conflict`](#conflict--mergeworkflow-conflict-signal) | Social | Merge-conflict signal (keywords ∪ GitHub conflict state) | [Z22] |
| [`cyclomatic_complexity`](#cyclomatic_complexity--aggregate-control-flow-complexity) | Size & Complexity | McCabe complexity summed over functions in touched files | [M76] |
| [`loc`](#loc--lines-of-code-touched-including-comments) | Size & Complexity | Total size of the files the PR modifies, incl. comments | [G14] |
| [`halstead_volume`](#halstead_volume--halstead-program-volume) | Size & Complexity | Halstead volume `V = N·log₂(n)` of the touched code | [HA77] |
| [`nesting_depth`](#nesting_depth--maximum-control-structure-nesting) | Size & Complexity | Deepest control-structure nesting in the touched files | [D84] |
| [`prev_pr`](#prev_pr--authors-prior-prs-apr-alias) | Process | Author's prior PRs (alias of `prev_pullreqs`) | [G14] |
| [`linked_issues`](#linked_issues--issues-linked-after-submission) | Process | Issues linked to the PR after its creation | [Z22] |
| [`codechurn`](#codechurn--magnitude-of-code-modification-apr-alias) | Process | Final-diff churn (alias of `src_churn_close`) | [N05] |
| [`author_experience`](#author_experience--account-longevity) | Process | Age of the author's GitHub account at PR creation | [Z22] |

---

## Pull Request Characteristics (PR-Level Signals)

### `bug_fix` — does the PR fix a bug?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether the pull request's purpose is to repair a defect, as opposed to adding a feature, refactoring, or updating documentation. Bug-fixing PRs are reviewed and merged under different urgency and scrutiny than feature PRs, which is why the distinction predicts both latency and acceptance.

**Data required.** `pull_request.title`, `pull_request.body`; `related_issue` joined to `issue`; `pr_timeline` rows with `event = 'labeled'`; **REST** `GET /repos/{o}/{r}/issues/{number}/labels` for label names on linked issues.

**Computation.** `bug_fix = 1` if any of the following holds, else `0`: (a) the regex `(fix(e[sd])?|bug|defect|fault|error|crash|repair)` matches `lower(title ∥ body)` outside code blocks; (b) a linked issue (via `related_issue`) carries a label matching `bug|defect|regression`; (c) a `pr_timeline` `labeled` event attached a bug-like label to the PR itself.

**Procedure.** First concatenate the title and body, strip fenced code blocks and inline code spans (keywords inside code are not intent signals), lowercase, and apply the keyword regex. Second, join `related_issue → issue` for the PR and fetch each linked issue's labels via REST; test them against the label regex. Third, scan `pr_timeline` for `labeled` events whose `label` field matches. Take the logical OR of the three signals.

**Caveats.** Keyword matching produces false positives ("fixed formatting") and false negatives (fixes described without keywords). Label conventions vary per repository; extend the label regex per project. When linked issues are used, signal (b) is the most precise of the three.

### `description_length` — length of the PR description

**Unit:** words · **Reference:** [Y15]

**Definition.** The size of the natural-language description the author provides when opening the PR. Longer, more informative descriptions reduce reviewer effort and correlate with faster first response and higher acceptance.

**Data required.** `pull_request.body` only.

**Computation.** `description_length = |tokens(strip_md(body))|`, where `strip_md` removes fenced code blocks, inline code, URLs, and image/link markup, and `tokens` splits on whitespace.

**Procedure.** Read `body`; if `NULL`, return 0. Remove fenced code blocks (``` … ```), inline code spans, raw URLs, and markdown link/image syntax, keeping the link text. Collapse whitespace and split into tokens. Count tokens. Record the character-count variant alongside if comparability with papers using characters is needed.

**Caveats.** PR templates inflate the count with boilerplate; if the repository has a `.github/PULL_REQUEST_TEMPLATE.md`, subtract template tokens or flag templated PRs. Auto-generated bodies (e.g., by release bots or Copilot agents — check `pull_request.agent`) should be flagged separately.

### `hash_tag` — does the description reference an issue by number?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Presence of a `#N` issue/PR reference in the description. Explicit cross-references signal traceability to an existing issue, which reviewers use as evidence the change is wanted.

**Data required.** `pull_request.body`.

**Computation.** `hash_tag = 1` if regex `(^|\s)#[0-9]+` matches `body` after code-block removal, else `0`.

**Procedure.** Strip fenced code blocks and inline code from `body` (issue references inside code, e.g. `#include` or shell comments, are false positives). Apply the regex. Threshold at ≥ 1 match.

**Caveats.** Markdown headings (`# Title`) begin lines with `#` but are not followed immediately by digits, so the digit requirement excludes them. `GH-123` and full-URL references are alternative syntaxes GitHub also autolinks; include `GH-\d+` and `github.com/{o}/{r}/issues/\d+` patterns for completeness.

### `num_participants` — participants in the PR discussion

**Unit:** persons · **Reference:** [T14]

**Definition.** The number of distinct humans who commented on the PR in any channel (discussion comments, review summaries, or inline code comments), excluding the author. Captures how much community attention the PR attracted.

**Data required.** `pr_comments.user`, `pr_reviews.user`, `pr_review_comments.user` (the latter joined via `pr_review_comments.pull_request_review_id = pr_reviews.id`).

**Computation.** `num_participants = |({pr_comments.user} ∪ {pr_reviews.user} ∪ {pr_review_comments.user}) \ ({A} ∪ Bots)|`.

**Procedure.** Collect the distinct `user` values from each of the three tables for the PR. Union the three sets. Remove the author and all bot accounts. Count the remainder. If a variant *including* the author is needed for replication of a specific paper, record both.

**Caveats.** Papers differ on whether the author counts as a participant — [T14] includes all commenters; state the convention used. CI bots and code-review bots can dominate raw counts; bot filtering is essential.

### `ci_exists` — does the PR run CI?

**Unit:** boolean {0,1} · **Reference:** [V15]

**Definition.** Whether any continuous-integration system (GitHub Actions, or external systems reporting via the Checks/Status APIs) executed against the PR's head commit. CI presence changes the review process fundamentally: reviewers offload correctness checking to automation.

**Data required.** Head SHA = the last `pr_commits.sha` in chronological order (order commits by their `pr_timeline` `committed` events, or via **GQL** `pullRequest { commits(last:1) { nodes { commit { oid } } } }`); **REST** `GET /repos/{o}/{r}/commits/{sha}/check-runs` and `GET /repos/{o}/{r}/commits/{sha}/status`.

**Computation.** `ci_exists = 1` if `check_runs.total_count > 0 OR statuses.total_count > 0` for the head SHA, else `0`.

**Procedure.** Resolve the head SHA. Call both endpoints — check runs cover GitHub Actions and modern integrations; the combined-status endpoint covers legacy CI (older Travis/Jenkins webhooks). Return 1 if either is non-empty.

**Caveats.** Check-run data can be garbage-collected on very old PRs; for historical PRs, absence of check runs is weak evidence of absence of CI. Cross-check for a CI config file (`.github/workflows/`, `.travis.yml`) in the repo at `t₀` as a fallback repository-level signal.

### `ci_latency` — time until the first CI result

**Unit:** minutes · **Reference:** [Y15]

**Definition.** Minutes from PR creation until the first CI build finished. Long CI latency directly delays the earliest possible human review of validated code and is one of the strongest process predictors of overall PR latency.

**Data required.** `t₀`; check runs for the head SHA that was current at open time (the *first* head SHA, i.e., the last commit before `t₀`) via **REST** `GET /commits/{sha}/check-runs` (`completed_at` fields).

**Computation.** `ci_latency = (min{ cr.completed_at : cr ∈ check_runs(first_head_sha), cr.completed_at ≥ t₀ } − t₀) / 60 s`.

**Procedure.** Identify the head SHA at open (latest pre-`t₀` `committed` timeline event). Fetch its check runs. Filter to runs completing at or after `t₀`. Take the earliest `completed_at`, subtract `t₀`, and convert to minutes. Return `NULL` when `ci_exists = 0`.

**Caveats.** If the author pushes immediately after opening, CI may run only on the newer SHA; fall back to the earliest completed check run on *any* PR commit. Re-runs overwrite check-run timestamps on some CI systems — prefer the `started_at`/`completed_at` of the first attempt where the API exposes attempts.

### `part_num_code` — participants in code-level discussion

**Unit:** persons · **Reference:** [Z22]

**Definition.** Distinct users participating in *code-anchored* discussion: inline review comments plus comments left directly on the PR's commits. A code-level counterpart to `num_participants` that isolates technical engagement from general discussion.

**Data required.** `pr_review_comments.user`; commit comments via **REST** `GET /repos/{o}/{r}/commits/{sha}/comments` for every `pr_commits.sha`.

**Computation.** `part_num_code = |({pr_review_comments.user} ∪ {commit_comments.user}) \ Bots|`.

**Procedure.** Take distinct users from `pr_review_comments` (joined to this PR through `pr_reviews`). For each commit SHA in `pr_commits`, fetch commit comments and collect their authors. Union, remove bots, count.

**Caveats.** Commit comments are rare in modern GitHub usage; for most PRs this reduces to inline-review participants. The REST calls scale with commit count — cache per SHA.

### `num_code_comments` — number of inline code comments

**Unit:** comments · **Reference:** [Z22]

**Definition.** Count of review comments anchored to specific diff lines. Measures the intensity of line-level scrutiny the change received.

**Data required.** `pr_review_comments` joined via `pull_request_review_id` to `pr_reviews` filtered on `pr_id`.

**Computation.** `num_code_comments = COUNT(pr_review_comments ⋈ pr_reviews ON pull_request_review_id WHERE pr_reviews.pr_id = PR)`.

**Procedure.** Join the two tables, filter to the PR, count rows. Replies to inline comments carry `in_reply_to_id NOT NULL`; count them in the main figure but also record the thread-count variant (rows with `in_reply_to_id IS NULL`) since some papers count threads, not messages.

**Caveats.** Review comments submitted as part of a batch review and single-comment reviews are indistinguishable at this level, which is fine for counting but matters if pairing with `pr_reviews.state`. Exclude bots (automated review tools comment inline).

### `reopen_or_not` — was the PR reopened?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether the PR was closed and subsequently reopened at least once. Reopening signals contested or premature closure and is associated with substantially longer total latency.

**Data required.** `pr_timeline` rows for the PR.

**Computation.** `reopen_or_not = 1` if `∃ pr_timeline(pr_id = PR, event = 'reopened')`, else `0`.

**Procedure.** Scan the PR's timeline for any `reopened` event. Optionally record the count of reopen cycles (`closed`→`reopened` pairs) as an ordinal variant.

**Caveats.** None significant — the timeline event is authoritative. Note that latency computed as `t₁ − t₀` spans all cycles; per-cycle analysis needs the paired event timestamps.

### `rework` — post-review rework

**Unit:** commits (binary variant: {0,1}) · **Reference:** [G15]

**Definition.** The amount of new work pushed *after* the first review feedback arrived — the operationalization of "the PR required substantial rework before it could be merged".

**Data required.** `min(pr_reviews.submitted_at)` as the first-feedback timestamp; `pr_timeline` `committed` events (whose `created_at` is the commit author date) and `head_ref_force_pushed` events.

**Computation.** `rework = COUNT(pr_timeline(event='committed', created_at > min(pr_reviews.submitted_at))) + COUNT(pr_timeline(event='head_ref_force_pushed'))`; binary variant `1[rework > 0]`.

**Procedure.** Compute the first review time; if the PR was never reviewed, `rework = NULL` (not 0 — no opportunity for rework existed). Count commits dated after it. Add force-push events, which represent history rewrites that hide reworked commits. Report both the count and the binary indicator.

**Caveats.** Commit author dates can predate the push (local commits made earlier, pushed after review); this undercounts rework done before review but pushed later — an accepted approximation in the literature. Force-pushed (rebased) branches destroy the pre-rebase commit dates entirely; the force-push term compensates by at least flagging that rework occurred.

### `friday_effect` — was the PR submitted on a Friday?

**Unit:** boolean {0,1} · **Reference:** [S05], [Z22]

**Definition.** Whether the PR was opened on a Friday. Changes submitted just before the weekend receive delayed attention and, per the classic "Friday commit" result, are more error-prone.

**Data required.** `t₀`.

**Computation.** `friday_effect = 1[weekday(t₀) = Friday]`.

**Procedure.** Take `t₀` (stored in UTC). Compute the ISO weekday. Compare to Friday. For timezone-sensitive analysis, shift `t₀` by the author's inferred timezone (from the UTC offsets in their commit timestamps, obtainable via **GQL** `commit { authoredDate }`) before extracting the weekday, and report which convention was used.

**Caveats.** UTC weekday misclassifies authors far from UTC (a Friday evening in California is Saturday UTC). The commit-offset inference fixes most cases but fails for authors using UTC-configured CI or web commits.

### `has_comments` — does the PR have any comment?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether any discussion or inline comment exists. Silent PRs (merged or closed with zero comments) follow a distinct fast-path process.

**Data required.** Row counts of `pr_comments` and `pr_review_comments` for the PR.

**Computation.** `has_comments = 1[COUNT(pr_comments) + COUNT(pr_review_comments) > 0]`.

**Procedure.** Count both tables, sum, threshold at zero. Compute both a with-bots and without-bots variant; a PR whose only comment is a CI bot's is "silent" for social purposes.

**Caveats.** Review *summaries* with empty bodies (`pr_reviews.body = ''` approvals) are not comments; if approvals should count as interaction, use `interaction_count` instead.

### `num_comments` — number of discussion comments

**Unit:** comments · **Reference:** [G14]

**Definition.** Count of comments in the PR's conversation thread (issue-style comments), the standard measure of discussion volume.

**Data required.** `pr_comments` rows for the PR.

**Computation.** `num_comments = COUNT(pr_comments WHERE pr_id = PR AND user ∉ Bots)`.

**Procedure.** Count non-bot rows. Where replication of [G14] is intended, note that GHTorrent's `num_comments` combined discussion and code comments; the combined variant is `num_comments + num_code_comments`.

**Caveats.** Bot comments (CI status summaries, coverage bots) can be the majority on active repos; always report the bot-filtering rule.

### `num_comments_con` — contributor's own discussion comments

**Unit:** comments · **Reference:** [Z22]

**Definition.** How many discussion comments the PR author themselves wrote. High author participation signals responsiveness to feedback.

**Data required.** `pr_comments` filtered by author.

**Computation.** `num_comments_con = COUNT(pr_comments WHERE pr_id = PR AND user = A)`.

**Procedure.** Filter the PR's comments to those authored by `A`; count. The complementary reviewer-side count is `num_comments − num_comments_con`.

**Caveats.** None beyond the shared bot/author-identity issues; if the author account was renamed mid-history, `user` strings may diverge — match on `user_id` where available (`pr_comments.user_id`).

### `at_tag` — does the PR text @-mention anyone?

**Unit:** boolean {0,1} · **Reference:** [Y15]

**Definition.** Presence of an `@username` mention in the description or discussion. Mentions actively summon reviewers and shorten time-to-first-response.

**Data required.** `pull_request.body` and `pr_comments.body`.

**Computation.** `at_tag = 1` if regex `(^|\s)@[A-Za-z0-9][A-Za-z0-9-]*` matches the concatenation of `body` and all comment bodies, after code and email stripping.

**Procedure.** Concatenate the texts. Remove fenced/inline code (decorators like `@Test`, Python `@property` are false positives) and email addresses (`x@y.com`). Apply the regex; threshold at ≥ 1. A stricter variant validates that the mentioned string is an actual repo collaborator via **REST** `GET /repos/{o}/{r}/collaborators`.

**Caveats.** The description-only variant (`body` alone) is a *submission-time* signal usable for prediction at open; the with-comments variant leaks post-submission information. Choose per use case and label accordingly.

### `num_code_comments_con` — contributor's inline code comments

**Unit:** comments · **Reference:** [Z22]

**Definition.** Inline review comments written by the PR author (typically responses within review threads).

**Data required.** `pr_review_comments` joined to the PR via `pr_reviews`, filtered by author.

**Computation.** `num_code_comments_con = COUNT(pr_review_comments ⋈ pr_reviews WHERE pr_reviews.pr_id = PR AND pr_review_comments.user = A)`.

**Procedure.** Same join as `num_code_comments`, plus the author filter. Count rows.

**Caveats.** Authors can technically start inline threads on their own PR (self-review annotations); if separating self-annotation from replies matters, split on `in_reply_to_id`.

### `ci_test_passed` — did all CI builds pass?

**Unit:** boolean {0,1} · **Reference:** [V15]

**Definition.** Whether every CI check on the final head commit succeeded. A green build is a near-precondition for merging in CI-using projects.

**Data required.** Final head SHA (last row of `pr_commits` in commit order); **REST** `GET /commits/{sha}/check-runs` (`conclusion` per run) and `GET /commits/{sha}/status` (`state`).

**Computation.** `ci_test_passed = 1` if all check runs have `conclusion = 'success'` (treating `skipped`/`neutral` as non-failing) and the combined status `state = 'success'`; `0` if any run failed; `NULL` if `ci_exists = 0`.

**Procedure.** Resolve the final head SHA. Fetch check runs and combined status. Classify each conclusion: `success/skipped/neutral` → pass, `failure/timed_out/cancelled/action_required` → fail. AND across runs and status contexts. Record the pass-fraction (`passed_runs / total_runs`) as a continuous variant.

**Caveats.** Evaluating the *final* SHA measures the state at decision time; evaluating the *first* SHA measures submission quality — these are different constructs ([Z22] uses both under `ci_first_build_pass` style names). Required-vs-optional checks are distinguishable via branch-protection settings (**REST** `GET /branches/{b}/protection`) when only required checks should count.

### `comment_conflict` — is a merge conflict discussed?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether the word "conflict" appears anywhere in the PR's discussion, used as a textual proxy for the PR having encountered merge conflicts with its base branch.

**Data required.** `pr_comments.body`, `pr_reviews.body`, `pr_review_comments.body`; optionally **REST** `GET /pulls/{n}` → `mergeable_state`.

**Computation.** `comment_conflict = 1` if regex `conflict` matches `lower(⋃ all comment bodies)`, else `0`.

**Procedure.** Concatenate all comment/review bodies, lowercase, strip code blocks, apply the regex. Where the PR is still open, cross-validate against `mergeable_state = 'dirty'` (GitHub's live conflict flag).

**Caveats.** "Conflict" is polysemous (naming conflicts, dependency conflicts); expect some false positives. `mergeable_state` is computed against the base branch *as of now*, so it is not a valid historical signal for closed PRs — the keyword proxy is precisely what the literature uses for that reason.

### `num_commits_open` / `num_commits_close` — commit counts at open and close

**Unit:** commits · **Reference:** [G14]

**Definition.** The number of commits in the PR when it was opened versus when it was closed. The open-time value measures submission size; the difference (`close − open`) measures how much the PR grew during review.

**Data required.** `pr_commits` (full commit set); `pr_timeline` `committed` events (`created_at` = commit author date) for temporal placement.

**Computation.** `num_commits_close = COUNT(pr_commits WHERE pr_id = PR)`. `num_commits_open = COUNT(pr_timeline(event='committed', created_at < t₀))`. Delta variant: `close − open`.

**Procedure.** Count all rows of `pr_commits` for the close value. For the open value, take `committed` timeline events and keep those with author date strictly before `t₀`. Flag PRs having any `head_ref_force_pushed` event: their open-time reconstruction is unreliable and should be excluded or sensitivity-tested.

**Caveats.** Commit author dates are rewritten by rebase and can be arbitrarily set; the pre-`t₀` heuristic is the standard approximation (used by GHTorrent-era studies) but is biased on rebase-heavy repos. GH Archive `PushEvent`s give true push times when exactness is required.

### `src_churn_open` / `src_churn_close` — code churn at open and close

**Unit:** lines · **Reference:** [G14]

**Definition.** Total lines added plus deleted by the PR, at open time and at close time. The canonical PR size measure and among the strongest predictors of latency and rejection.

**Data required.** Close: **REST** `GET /pulls/{n}` → `additions`, `deletions` (final-diff totals). Open: `pr_commit_details.commit_stats_additions`, `commit_stats_deletions` per pre-open commit SHA.

**Computation.** `src_churn_close = pull.additions + pull.deletions`. `src_churn_open = Σ_{sha ∈ pre-open SHAs} (commit_stats_additions + commit_stats_deletions)`, taking each SHA's stats once (the stats repeat on every per-file row of `pr_commit_details` — deduplicate by SHA).

**Procedure.** For close, read the two REST fields; these describe the final squashed diff and avoid double-counting lines edited in multiple commits. For open, select pre-open SHAs as in `num_commits_open`, take one row per SHA, and sum the commit-level stats. Record additions and deletions separately as well (see `churn_addition`/`churn_deletion`).

**Caveats.** The open-time value sums per-commit churn, which double-counts lines touched by several pre-open commits; the close value uses the collapsed diff. The two are therefore not perfectly comparable — document this when computing the delta. Binary files report zero line churn.

### `files_changed_open` / `files_changed_close` — files touched at open and close

**Unit:** files · **Reference:** [G14]

**Definition.** Number of distinct files modified by the PR at open and at close. Spreading a change across many files increases review scope independent of line churn.

**Data required.** `pr_commit_details.filename` (per commit, per file); pre-open SHA set for the open variant; **REST** `GET /pulls/{n}` → `changed_files` for cross-checking.

**Computation.** `files_changed_close = COUNT(DISTINCT pr_commit_details.filename WHERE pr_id = PR)`. `files_changed_open = COUNT(DISTINCT filename WHERE sha ∈ pre-open SHAs)`.

**Procedure.** Count distinct filenames over the relevant SHA set. Validate the close value against REST `changed_files`; discrepancies indicate renames (both old and new paths appear in commit details) — resolve renames using the `status` column (`renamed`) and count the file once.

**Caveats.** Renamed files inflate the distinct-name count; the `status` field allows correction. Files changed and then reverted within the PR still appear in commit details but are absent from the final diff — the REST cross-check quantifies this drift.

### `commits_touched_open` / `commits_touched_close` — recent activity on touched files

**Unit:** commits · **Reference:** [G14]

**Definition.** How actively the files touched by this PR were being changed in the base repository during the preceding three months ("file hotness"). Hot files attract conflicts and competing changes.

**Data required.** Distinct touched filenames (open/close sets as above); **REST** `GET /repos/{o}/{r}/commits?path={filename}&since={t−90d}&until={t}` per file, with `t = t₀` (open) or `t = t₁` (close).

**Computation.** `commits_touched(t) = Σ_{f ∈ touched(t)} |commits(path=f, t−90d ≤ date < t)|`.

**Procedure.** Build the touched-file list for the relevant snapshot. For each file, page through the commits endpoint with the `path`, `since`, `until` filters and count commits. Sum over files. Report also the mean per file, which is size-independent.

**Caveats.** One API call chain per file — expensive for large PRs; a local `git log --since --until -- <path>` on a clone is equivalent and faster. The `path` filter follows the current name only; renamed files need `--follow` semantics, available only via local git.

### `churn_addition_open` / `churn_addition_close` — added lines

**Unit:** lines · **Reference:** [G14]

**Definition.** Lines added by the PR at open/close. Separating additions from deletions matters because added code carries review burden that deleted code does not.

**Data required.** Close: **REST** `GET /pulls/{n}` → `additions`. Open: `pr_commit_details.commit_stats_additions` per pre-open SHA (deduplicated by SHA).

**Computation.** `churn_addition_close = pull.additions`; `churn_addition_open = Σ_{sha ∈ pre-open} commit_stats_additions`.

**Procedure.** As in `src_churn`, restricted to the additions component. Per-file additions are available in `pr_commit_details.additions` when file-level resolution is needed.

**Caveats.** Same double-counting asymmetry between the open (per-commit) and close (final-diff) variants as `src_churn`.

### `churn_deletion_open` / `churn_deletion_close` — deleted lines

**Unit:** lines · **Reference:** [G14]

**Definition.** Lines deleted by the PR at open/close.

**Data required.** Close: **REST** `GET /pulls/{n}` → `deletions`. Open: `pr_commit_details.commit_stats_deletions` per pre-open SHA.

**Computation.** `churn_deletion_close = pull.deletions`; `churn_deletion_open = Σ_{sha ∈ pre-open} commit_stats_deletions`.

**Procedure.** Identical to `churn_addition` with the deletions component.

**Caveats.** As above.

### `test_churn_open` / `test_churn_close` — test-code churn

**Unit:** lines · **Reference:** [G14]

**Definition.** Lines of *test* code changed by the PR. PRs that adjust tests alongside production code demonstrate verification effort, which integrators reward.

**Data required.** `pr_commit_details` rows (`filename`, `additions`, `deletions`); the `TEST_RE` filename classifier; pre-open SHA set for the open variant.

**Computation.** `test_churn(t) = Σ (additions + deletions)` over `pr_commit_details` rows where `filename ~ TEST_RE` (and `sha ∈ pre-open SHAs` for `t = t₀`). For the close variant prefer per-file rows of the *final diff* (**REST** `GET /pulls/{n}/files`) to avoid cross-commit double counting.

**Procedure.** Classify every touched filename against `TEST_RE`. Sum per-file additions + deletions over matching rows in the relevant SHA set. Report the test-to-total churn ratio (`test_churn / src_churn`) as a normalized variant.

**Caveats.** Filename heuristics miss unconventional test layouts (e.g., doctests, `qa/` directories) and misfire on files like `test_data.json`; tune `TEST_RE` per ecosystem and validate on a sample. Language-specific conventions (Go `_test.go`, Java `src/test/`) should be added explicitly.

### `test_inclusion_open` / `test_inclusion_close` — does the PR touch tests?

**Unit:** boolean {0,1} · **Reference:** [G14], [T14]

**Definition.** Whether at least one test file is modified at open/close. The binary form of `test_churn`, prominent in acceptance models: PRs including tests are significantly likelier to be merged.

**Data required.** Same as `test_churn`.

**Computation.** `test_inclusion(t) = 1[∃ pr_commit_details.filename ~ TEST_RE (within the relevant SHA set)]`.

**Procedure.** Apply `TEST_RE` to the touched-file list; threshold at ≥ 1 match.

**Caveats.** Inherits the `TEST_RE` heuristics caveat. Note the metric says nothing about whether the tests are *new* — combine with per-file `status = 'added'` to distinguish adding tests from editing existing ones.

---

## Developer Characteristics

### `first_pr` — is this the author's first PR in the repository?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether the author has never before submitted a PR to this repository. Newcomer PRs face higher rejection rates and longer latency.

**Data required.** Local `pull_request` table (author's history); alternatively **GQL** `search(query: "repo:o/r type:pr author:A created:<t₀", type: ISSUE) { issueCount }`.

**Computation.** `first_pr = 1[COUNT(pull_request WHERE repo_id = R AND user = A AND created_at < t₀) = 0]`.

**Procedure.** Query the local table for earlier PRs by the same author in the same repo; threshold the count at zero. If the local dataset does not cover the repo's full history, use the GQL search count instead — the local table only knows about collected PRs.

**Caveats.** Author renames break login-based matching across time; match on `user_id` where possible. Contributions under multiple accounts (work/personal) are undetectable.

### `prior_review_num` — author's prior reviews in the project

**Unit:** reviews · **Reference:** [Z22]

**Definition.** How many *other* PRs in this repository the author had reviewed before submitting this one. Reviewing experience signals project familiarity distinct from authoring experience.

**Data required.** `pr_reviews` joined to `pull_request` on `pr_id` (to scope to repo `R`), filtered on reviewer and time.

**Computation.** `prior_review_num = COUNT(DISTINCT pr_reviews.pr_id WHERE pr_reviews.user = A AND submitted_at < t₀ AND pull_request.repo_id = R)`.

**Procedure.** Join, filter to reviews authored by `A` before `t₀`, count distinct PRs reviewed (not review events — one PR reviewed thrice counts once; record the event-count variant too if replicating papers that count events).

**Caveats.** Coverage depends on the local dataset containing the repo's other PRs; otherwise page through **GQL** review histories, which is expensive. Comment-only participation is not a review; this metric intentionally counts formal review submissions.

### `core_member` — is the author a core member?

**Unit:** boolean {0,1} · **Reference:** [G14]

**Definition.** Whether the author holds commit/maintainer rights in the project. Core members' PRs are effectively self-service and follow a much faster path.

**Data required.** **GQL** `pullRequest { authorAssociation }` or **REST** `GET /pulls/{n}` → `author_association`; fallback: `pr_timeline` `merged` events across the repo.

**Computation.** `core_member = 1[author_association ∈ {OWNER, MEMBER, COLLABORATOR}]`. Fallback: `1` if `A` appears as `actor` of any `merged` timeline event in `R` during `[t₀ − 90d, t₀)`.

**Procedure.** Prefer `author_association`, which GitHub computes relative to the repo. If unavailable (deleted accounts return `NONE`), apply the behavioral fallback: anyone who merged a PR recently demonstrably has write access.

**Caveats.** `author_association` reflects the association *at query time*, not at `t₀` — a contributor promoted after this PR will look like a member retroactively. The behavioral fallback windowed to before `t₀` is the historically-correct signal; report which was used.

### `first_response_time` — time to first human response

**Unit:** minutes · **Reference:** [Y15]

**Definition.** Minutes from PR creation to the first response by someone other than the author, across any channel (discussion comment, review, or inline comment). The classic responsiveness measure.

**Data required.** `pr_comments.created_at`, `pr_reviews.submitted_at`, `pr_review_comments.created_at`, each filtered to `user ≠ A` and non-bot.

**Computation.** `first_response_time = (min over the three tables of the earliest qualifying timestamp − t₀) / 60 s`; `NULL` if no qualifying response exists.

**Procedure.** For each table, find the earliest row with a non-author, non-bot user and timestamp ≥ `t₀`. Take the global minimum. Subtract `t₀` and convert to minutes. Negative values (responses timestamped before `t₀`, possible via clock skew on imported data) should be clamped to 0 and flagged.

**Caveats.** Bot filtering is decisive here — CI bots typically respond within seconds and would otherwise dominate. Timeline events like `assigned` or `labeled` by a maintainer are arguably "responses" too; the comment-based definition is the standard one, but record the event-based variant if studying triage speed.

### `contrib_gender` — inferred gender of the contributor

**Unit:** category {male, female, unknown} · **Reference:** [TR17]

**Definition.** Author gender inferred from profile information, used in the literature to study bias in PR acceptance.

**Data required.** **REST** `GET /users/{A}` → `name`, `location`.

**Computation.** `contrib_gender = genderComputer(name, location)`, defaulting to `unknown` on ambiguity or missing name.

**Procedure.** Fetch the profile name and location. Run a name-based inference tool (e.g., genderComputer, which uses country-specific name frequency lists keyed by `location`). Assign `unknown` whenever confidence is low, the name field is empty, or only a login is available.

**Caveats.** Methodologically noisy (nicknames, initials, non-Western names) and *ethically sensitive*: infer only for aggregate analysis, never publish individual-level inferences, and consider whether the research question justifies collection at all. [TR17] documents both the method and its error profile.

### `contrib_affiliation` — contributor's organizational affiliation

**Unit:** category (normalized organization string) · **Reference:** [B16]

**Definition.** The company or organization the author belongs to. Affiliation drives review dynamics in commercially-backed projects.

**Data required.** **REST** `GET /users/{A}` → `company`; fallback: commit author email domains via **GQL** `commit { author { email } }` for the author's commits (the local `pr_commits.author` stores a name string, not an email).

**Computation.** `contrib_affiliation = normalize(company)` if present, else `normalize(mode(email_domains(A's commits)))`, else `unknown`. `normalize` lowercases, strips `@`, punctuation, and legal suffixes, and maps known aliases (`msft → microsoft`).

**Procedure.** Fetch `company`; normalize. If empty, collect the author's commit emails across their PRs, take the modal domain, discard generic providers (gmail, outlook, users.noreply.github.com), and normalize. Maintain the alias map as a versioned artifact so the mapping is reproducible.

**Caveats.** The profile field is free text, self-reported, and current-state only (job changes rewrite history). Email fallback fails for squash-merged or privacy-masked commits. Expect `unknown` rates of 40–60% on open-source populations.

### `same_affiliation` — do contributor and integrator share an affiliation?

**Unit:** boolean {0,1} · **Reference:** [B16]

**Definition.** Whether the PR author and the person who merged/closed it belong to the same organization. Same-company review is systematically faster and more lenient in corporate-backed projects.

**Data required.** `contrib_affiliation`, `inte_affiliation` (below).

**Computation.** `same_affiliation = 1[contrib_affiliation = inte_affiliation ∧ both ≠ unknown]`; `NULL` if either side is `unknown`.

**Procedure.** Compute both affiliations with the same `normalize` function, compare exact normalized strings, propagate `NULL` on missing data rather than coding it 0 (absence of evidence is not evidence of different employers).

**Caveats.** Inherits both parents' noise multiplicatively; report the effective sample after `NULL` removal.

### `inte_affiliation` — integrator's organizational affiliation

**Unit:** category (normalized organization string) · **Reference:** [B16]

**Definition.** The affiliation of the integrator — the person who merged the PR, or who closed it if it was rejected.

**Data required.** Integrator login `I = pr_timeline.actor` of the `merged` event (else the last `closed` event); **REST** `GET /users/{I}` → `company`.

**Computation.** `inte_affiliation = normalize(company(I))`, with the same normalization and email fallback as `contrib_affiliation`.

**Procedure.** Extract the integrator from the timeline (the schema's `pull_request` has no `merged_by` column, so the timeline actor is the source of truth). Fetch and normalize their company. `NULL` for PRs closed by automation (e.g., stale bots) — flag these separately.

**Caveats.** As for `contrib_affiliation`; additionally, the closer of a rejected PR is sometimes the author themselves (self-close), which is a meaningful category of its own — record `self_closed = 1[actor = A]` alongside.

### `social_strength` — contributor's social connectedness to the core team

**Unit:** ratio [0,1] · **Reference:** [T14]

**Definition.** The fraction of core team members the author interacted with in the three months before submission. Prior social ties strongly predict favorable evaluation.

**Data required.** Repo-wide `pr_comments`, `pr_reviews`, `pr_review_comments`, and `pr_timeline` over `[t₀ − 90d, t₀)`; the core-team set from `team_size`'s procedure.

**Computation.** `social_strength = |core(t₀) ∩ interacted(A, t₀ − 90d, t₀)| / |core(t₀)|`, where `interacted(A, …)` is the set of users who co-occur with `A` on the same PR's discussion (either direction: they commented on A's PRs, or A commented on PRs they authored/reviewed) within the window.

**Procedure.** Build the core set (merge actors + default-branch pushers in the window). Build the interaction set: for every PR in the repo active in the window, if `A` authored or commented on it, add all other human commenters/reviewers/authors of that PR. Intersect with the core set; divide by core size. Return 0 for `first-time` contributors with no window activity; `NULL` if the core set is empty.

**Caveats.** Requires repo-wide data for the window, not just this PR — the most data-hungry developer metric. Co-occurrence on a PR is a coarse proxy for interaction; direct reply chains (`in_reply_to_id`) give a stricter definition if needed.

### `prev_pullreqs` — author's previous PRs in the repository

**Unit:** PRs · **Reference:** [G14]

**Definition.** Count of PRs the author submitted to this repository before this one — the standard authoring-experience measure.

**Data required.** Local `pull_request` table.

**Computation.** `prev_pullreqs = COUNT(pull_request WHERE repo_id = R AND user = A AND created_at < t₀)`.

**Procedure.** Single query on the local table (same query as `first_pr`, keeping the count). Verify dataset coverage; supplement with the GQL search count when the local table is partial.

**Caveats.** Perfectly collinear with `first_pr` at the 0/1 boundary and with the APR set's `prev_pr` (identical metric) — include only one form per model.

### `followers` — author's follower count

**Unit:** persons · **Reference:** [T14]

**Definition.** The author's GitHub follower count, a visibility/status signal that influences how submissions are evaluated.

**Data required.** Local `user.followers` for `login = A` (a collection-time snapshot); historical alternative: GH Archive `FollowEvent` replay.

**Computation.** `followers = user.followers` (snapshot). Point-in-time variant: `|{FollowEvents targeting A with created_at < t₀}| − unfollows` (unfollows are not evented — see caveats).

**Procedure.** Read the local snapshot. If the analysis window is long or status effects are central, reconstruct historical counts from GH Archive; otherwise document the snapshot assumption (follower counts change slowly relative to typical study windows).

**Caveats.** The snapshot post-dates every PR in the dataset, introducing look-ahead bias correlated with author success — the standard threat discussed in this literature. Unfollow events are not published, so archive replay yields an upper bound.

### `same_user` — did the author merge their own PR?

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether contributor and integrator are the same person. Self-merging indicates commit rights and skips independent review entirely.

**Data required.** `pull_request.user`; `pr_timeline` `merged` event `actor`.

**Computation.** `same_user = 1[A = actor(merged event)]`; `NULL` if the PR was never merged.

**Procedure.** Find the `merged` timeline event, read its `actor`, compare logins (or user IDs). Only defined for merged PRs.

**Caveats.** Merge queues and bots (e.g., `bors`, merge-when-green bots) merge on behalf of humans; classify bot integrators separately rather than as "not same user".

---

## Project Characteristics

### `sloc` — project size in executable lines

**Unit:** lines (report KLOC) · **Reference:** [G14]

**Definition.** Executable (non-comment, non-blank) lines of code of the whole project at the moment the PR was opened. The basic normalizer for all per-KLOC metrics and a proxy for codebase complexity.

**Data required.** Base SHA via **GQL** `pullRequest { baseRefOid }` (not in the local schema); a git clone; `cloc` or `scc`.

**Computation.** `sloc = Σ_{f ∈ repo@base_sha} code_lines(f)` as reported by `cloc` (the `code` column, comments and blanks excluded).

**Procedure.** Resolve `baseRefOid`. Clone the repo (a filtered/partial clone suffices), `git checkout {base_sha}`, run `cloc --json .` (or `scc`, which is faster on large repos), and sum code lines across languages. Cache per base SHA — many PRs share bases.

**Caveats.** Vendored dependencies and generated code inflate SLOC; exclude conventional directories (`vendor/`, `node_modules/`, `dist/`) and document the exclusion list. `cloc` and `scc` disagree slightly on language classification — use one tool consistently.

### `team_size` — active core team size

**Unit:** persons · **Reference:** [G14]

**Definition.** Number of people actively integrating code (merging PRs or pushing to the default branch) in the three months before the PR. Larger active teams shorten queues but diffuse responsibility.

**Data required.** Repo-wide `pr_timeline` `merged` events in `[t₀ − 90d, t₀)`; **REST** `GET /repos/{o}/{r}/commits?since={t₀−90d}&until={t₀}` for default-branch committers.

**Computation.** `team_size = |({merge actors in window} ∪ {default-branch committers in window}) \ Bots|`.

**Procedure.** Collect distinct `actor`s of `merged` events across all repo PRs in the window. Fetch default-branch commits in the window and collect committer logins (direct pushes bypass PRs). Union, remove bots, count.

**Caveats.** Squash-merges attribute the commit to the PR author with the merger as committer — the commits endpoint's `committer` field handles this correctly. GitHub's `web-flow` committer indicates UI merges; map it back to the merge actor from the timeline.

### `project_age` — project age at submission

**Unit:** months · **Reference:** [G14]

**Definition.** Time from repository creation to the PR's creation. Mature projects have established conventions, slower acceptance of external change, and larger review queues.

**Data required.** **REST** `GET /repos/{o}/{r}` → `created_at` (the local `repository` table lacks a creation timestamp); `t₀`.

**Computation.** `project_age = (t₀ − repo.created_at) / 30.44 d`.

**Procedure.** Fetch the repo creation date once per repo, subtract from each PR's `t₀`, divide by the mean month length (30.44 days). Round or keep fractional per model needs.

**Caveats.** Repos migrated to GitHub carry the *migration* date as `created_at`, understating true age; the first commit's author date (`git log --reverse`) is a better lower bound for migrated projects — use `min(repo.created_at, first_commit_date)`.

### `open_pr_num` — open PR queue length at submission

**Unit:** PRs · **Reference:** [G14]

**Definition.** How many PRs were open in the repository at the moment this one was created. Queue length measures competition for integrator attention.

**Data required.** Local `pull_request` table only — fully point-in-time reconstructible.

**Computation.** `open_pr_num = COUNT(pull_request WHERE repo_id = R AND created_at < t₀ AND (closed_at IS NULL OR closed_at > t₀))`.

**Procedure.** Single interval-overlap query on the local table. No API needed, no snapshot bias — this is one of the few historical states that closed/merged timestamps fully determine.

**Caveats.** Accuracy requires the local table to contain *all* the repo's PRs, not a sample. PRs deleted along with forks vanish from any source; this undercount is small and unavoidable.

### `integrator_availability` — recency of integrator activity

**Unit:** hours · **Reference:** [Z22]

**Definition.** How recently the project's two most active integrators were active at submission time. If both are dormant (vacation, abandonment), even perfect PRs wait.

**Data required.** Merge actors and their activity timestamps from repo-wide `pr_timeline`, `pr_comments`, `pr_reviews` before `t₀`.

**Computation.** Let `top2 = the 2 actors with most 'merged' events in [t₀ − 90d, t₀)`. For each `I ∈ top2`, `last_activity(I) = max(timestamp of any timeline event / comment / review by I before t₀)`. Then `integrator_availability = min_{I ∈ top2} (t₀ − last_activity(I)) / 3600 s`.

**Procedure.** Rank integrators by merge count in the 90-day window. For the top two, find their latest recorded activity of any kind before `t₀`. Compute both gaps; take the minimum (the *most available* of the two — matching the intuition that one active integrator suffices). Report the max-variant too if replicating papers that measure the *least* available.

**Caveats.** Activity visible in the local dataset understates true activity (integrators act in other repos too); a GQL `contributionsCollection` query per integrator gives account-wide recency at higher cost. Definitions vary across papers — always state the aggregation (min vs max vs mean).

### `test_lines_per_kloc` — test-code density

**Unit:** lines/KLOC · **Reference:** [G14]

**Definition.** Lines of test code per thousand lines of project code at the PR's base revision. A project-level quality-culture indicator: well-tested projects both attract better PRs and evaluate them faster.

**Data required.** The `sloc` checkout; `TEST_RE` file classification; `cloc`.

**Computation.** `test_lines_per_kloc = code_lines(files ~ TEST_RE) / (sloc / 1000)`.

**Procedure.** On the base-SHA checkout, partition files by `TEST_RE`. Run `cloc` restricted to test files (pass the file list). Divide test code lines by project KLOC.

**Caveats.** Shares `TEST_RE`'s heuristic limits and `sloc`'s vendoring caveat — apply the same exclusion list to numerator and denominator.

### `test_cases_per_kloc` — test-case density

**Unit:** cases/KLOC · **Reference:** [G14]

**Definition.** Number of individual test cases per KLOC at the base revision.

**Data required.** Base-SHA checkout; per-language test-case regexes: `TESTCASE_RE ∈ {python: ^\s*def test_, java: @Test, js/ts: \b(it|test)\(, go: ^func Test, ruby: ^\s*(it|test) }`; `sloc`.

**Computation.** `test_cases_per_kloc = Σ_f count(matches(TESTCASE_RE_lang(f), f)) / (sloc / 1000)`.

**Procedure.** Detect each test file's language (by extension). Grep the language's test-case pattern; sum matches over all test files. Divide by KLOC. Validate patterns against the project's actual test framework on a sample.

**Caveats.** Regex counting misses parameterized/generated tests (pytest parametrize expands one `def` into many cases) and table-driven Go tests; treat as a lower bound and keep the pattern set versioned.

### `asserts_per_kloc` — assertion density

**Unit:** assertions/KLOC · **Reference:** [G14]

**Definition.** Assertion statements per KLOC at the base revision — a finer-grained verification-intensity measure than test-case counts.

**Data required.** Base-SHA checkout; assertion patterns per language (`assert`, `assertEquals|assertTrue|…`, `expect(`, `ASSERT_|EXPECT_` for gtest); `sloc`.

**Computation.** `asserts_per_kloc = Σ_f count(assertion matches in f) / (sloc / 1000)`.

**Procedure.** Grep assertion-family tokens language-aware across the checkout (test files primarily, but production asserts count in some replications — state the scope). Divide by KLOC.

**Caveats.** The token `assert` appears in comments and strings; an AST-based count (e.g., Python `ast` walking for `Assert` nodes) eliminates that noise where precision matters.

### `perc_external_contribs` — share of external contributions

**Unit:** % · **Reference:** [G14]

**Definition.** Percentage of recently merged PRs that came from outside the core team. High external share marks a project organized around drive-by contribution, with correspondingly developed triage practices.

**Data required.** Repo-wide `pull_request.merged_at` in `[t₀ − 90d, t₀)`; the core set from `team_size`.

**Computation.** `perc_external_contribs = 100 × |{merged PRs in window : author ∉ core}| / |{merged PRs in window}|`.

**Procedure.** Select PRs with `merged_at` in the window. Classify each author against the core set (computed for the same window). Divide and scale; `NULL` if no PRs were merged in the window.

**Caveats.** Core membership is itself windowed and behavioral (see `team_size`); a contributor promoted mid-window blurs the boundary. Sensitivity-check with a 180-day window.

### `requester_succ_rate` — author's historical merge rate

**Unit:** ratio [0,1] · **Reference:** [G14]

**Definition.** The fraction of the author's previously closed PRs in this repository that were merged. The single most-used reputation feature in acceptance models.

**Data required.** Local `pull_request` table only.

**Computation.** `requester_succ_rate = COUNT(user = A AND repo_id = R AND merged_at IS NOT NULL AND closed_at < t₀) / COUNT(user = A AND repo_id = R AND closed_at < t₀)`; `NULL` when the denominator is 0 (first-time contributors).

**Procedure.** Two counts over the author's closed-before-`t₀` PRs; divide. Keep `NULL` distinct from 0 — a newcomer (no history) differs from an author whose every prior PR was rejected; models should encode this via the `first_pr` interaction, not by imputing 0.

**Caveats.** Merges performed outside GitHub (cherry-picks, patch application) leave `merged_at` NULL and undercount success; detecting them requires searching the default branch for the PR's commits or `closes #` references.

---

# Derived Features for the APR Signal Set

## Outcome

### `rejected` — PR closed without merge

**Unit:** boolean {0,1} · **Reference:** [G14]

**Definition.** The outcome label: 1 for PRs closed without being merged, 0 for merged PRs. Everything else in this document is a candidate predictor of this variable.

**Data required.** `pull_request.closed_at`, `pull_request.merged_at`; `pr_timeline`; default-branch history for edge cases.

**Computation.** `rejected = 1` if `closed_at IS NOT NULL AND merged_at IS NULL` (and no `merged` timeline event exists); `0` if `merged_at IS NOT NULL`; `NULL` (undefined) while open.

**Procedure.** Read the two timestamps. Cross-check the timeline for a `merged` event — the fields and events should agree. For apparent rejections, screen for *out-of-band merges*: search the default branch for the PR's head commits (`git branch --contains {sha}`) or for commit messages referencing the PR number; reclassify hits as merged.

**Caveats.** Out-of-band merges affect a nontrivial share of "rejected" PRs in squash/rebase-workflow projects (documented since [G14]); skipping the screen inflates the negative class with mislabeled positives. Bot-closed stale PRs are rejections of a different nature — flag `closed_by_bot` for sensitivity analysis.

## Diff-Level

### `diffhunk_size` — total modified lines within diff hunks

**Unit:** lines · **Reference:** [G14]

**Definition.** The number of changed lines summed over all hunks of the PR's final diff — churn measured directly from patch text rather than from commit statistics.

**Data required.** Per-file `patch` text: `pr_commit_details.patch` for the final head SHA's rows, or **REST** `GET /pulls/{n}/files` → `patch` (final collapsed diff — preferred).

**Computation.** `diffhunk_size = Σ_f |{lines ℓ ∈ patch(f) : ℓ starts with '+' or '−', excluding '+++'/'---' headers}|`.

**Procedure.** Fetch each file's patch from the final diff. Split into lines; count those beginning with a single `+` or `-`, skipping the file-header lines. Sum over files. Verify against per-file `changes` (`pr_commit_details.changes`) — the two must match for text files.

**Caveats.** Binary files have no patch text and contribute 0. The REST `patch` field is omitted for very large diffs (> ~3000 lines per file); fall back to the `.diff` media type on the PR (`Accept: application/vnd.github.diff`) which returns the complete unified diff.

## Textual Features

### `ngrams` — bigrams and trigrams from PR text

**Unit:** count vector (sparse) · **Reference:** [H12]

**Definition.** Bag-of-n-grams representation (n ∈ {2,3}) of the PR's natural-language content, giving the model access to recurring phrases ("fixes issue", "breaking change", "work in progress") that single keywords miss.

**Data required.** `pull_request.title`, `pull_request.body`, `pr_comments.body`.

**Computation.** `ngrams = bag({(w_i, …, w_{i+n−1}) : n ∈ {2,3}}, tokens(strip_md(title ∥ body ∥ comments)))`, vectorized as TF or TF-IDF counts.

**Procedure.** Concatenate title, body, and (for post-hoc analysis only) comment bodies — for *submission-time* prediction, exclude comments to avoid leakage. Strip markdown, code, and URLs; lowercase; tokenize; optionally stem. Slide windows of 2 and 3 tokens. Vectorize; prune n-grams appearing in fewer than 5 PRs and more than 95% of PRs. Fit the vocabulary on training data only.

**Caveats.** The feature space is large and sparse — regularization or dimensionality reduction (SVD, hashing trick) is standard. Comment-derived n-grams encode the outcome ("merging this now") and must never enter a predictive model of `rejected`.

### `keyword_density` — density of process keywords

**Unit:** ratio [0,1] · **Reference:** [Z22]

**Definition.** The fraction of PR-text tokens that belong to a fixed process-keyword lexicon (bug, fix, test, CI, build, fail, error, refactor, doc, …). A compact, interpretable summary of what the PR talks about.

**Data required.** Same text stream as `ngrams`; a fixed keyword lexicon, versioned with the analysis.

**Computation.** `keyword_density = |{tokens ∈ KEYWORDS}| / |tokens|`; 0 when the text is empty.

**Procedure.** Fix the lexicon *before* looking at outcomes. Tokenize as for `ngrams`; match stemmed tokens against the stemmed lexicon; divide hits by total tokens. Also record per-keyword-group densities (bug-terms, test-terms, CI-terms) as separate features — the aggregate hides which topic drives the signal.

**Caveats.** Density confounds with `description_length` (short texts have volatile ratios); include both length and density so the model can separate them.

## Static Quality Metrics

*All static metrics are computed on a checkout of the PR head SHA (`git checkout {last pr_commits.sha}`), restricted to touched files (`DISTINCT pr_commit_details.filename`). Computing the same metric on the base SHA and taking the delta isolates what the PR itself introduced.*

### `duplicate_code` — clone detected in PR code

**Unit:** boolean {0,1} · **Reference:** [RC09]

**Definition.** Whether the PR introduces or touches duplicated code, as found by token-based clone detection. Duplication is a canonical maintainability defect reviewers are expected to catch.

**Data required.** Head-SHA checkout; touched-file list; a clone detector (PMD-CPD, `jscpd`, NiCad).

**Computation.** `duplicate_code = 1[∃ clone pair (s₁, s₂) with min length ≈ 50 tokens such that s₁ overlaps a line added in the PR diff]`.

**Procedure.** Run the detector over the whole checkout (clones pair PR code against pre-existing code, so scanning only touched files misses half the pairs). Intersect reported clone regions with the PR's added-line ranges (from the patch hunks). Return 1 on any overlap. Record the count of overlapping clone pairs as an ordinal variant.

**Caveats.** Threshold sensitivity is high — 50 tokens is conventional; report it. Type-3 (gapped) clones need NiCad-class detectors; token-based tools find only exact/renamed clones. Generated files must be excluded or they dominate results.

### `unused_vars` — unused variables in touched code

**Unit:** variables · **Reference:** [AY08]

**Definition.** Count of variables declared but never referenced in the PR's touched files — a cheap static-analysis proxy for submission carelessness.

**Data required.** Head-SHA checkout; touched-file list; per-language linters (pylint `W0612`/`W0613`, ESLint `no-unused-vars`, `staticcheck` U1000, `cargo clippy` unused warnings).

**Computation.** `unused_vars = Σ_{f ∈ touched} |{linter warnings of the unused-variable class in f whose line ∈ PR-added lines}|`.

**Procedure.** Run the language-appropriate linter per touched file at the head SHA. Filter warnings to the unused-variable rule class. Intersect warning lines with the PR's added lines so pre-existing violations don't count against the PR; report the unrestricted per-file count as a secondary variant, and say which is used.

**Caveats.** Linter availability varies by language — restrict the feature to languages with tooling and encode "not computable" as `NULL`, not 0. Deliberately unused parameters (interface conformance, `_`-prefixed) are conventionally suppressed; keep linter default suppressions on for comparability.

## Design and Architecture

### `large_class` — oversized class touched

**Unit:** boolean {0,1} · **Reference:** [F99]

**Definition.** Whether the PR touches a class whose size is extreme relative to this repository's own class-size distribution — the "Large Class" smell, thresholded per-project rather than absolutely.

**Data required.** Base-SHA checkout (for the repo-wide distribution); head-SHA checkout (for the touched classes); an AST parser (tree-sitter grammars per language).

**Computation.** `large_class = 1[∃ class c in touched files: LOC(c) ≥ percentile₉₀({LOC(c′) : c′ ∈ repo@base_sha})]`.

**Procedure.** Parse every class in the repo at the base SHA and record class LOC (declaration to closing brace, comments included); compute the 90th percentile. Parse classes in touched files at the head SHA. Flag if any meets the threshold. Cache the percentile per base SHA.

**Caveats.** Per-repo percentile thresholds adapt to domain norms but make the feature non-comparable across repos in pooled models — add the raw max-class-LOC as a companion continuous feature. Non-OO languages need "class" mapped to modules/files.

### `long_method` — long method touched

**Unit:** boolean {0,1} · **Reference:** [F99]

**Definition.** Whether any method/function in the touched files exceeds 100 lines — the "Long Method" smell with the fixed literature threshold.

**Data required.** Head-SHA checkout; touched files; `lizard` (reports per-function NLOC across ~20 languages).

**Computation.** `long_method = 1[max_{fn ∈ touched files} NLOC(fn) > 100]`.

**Procedure.** Run `lizard` on the touched files; take the per-function NLOC column; compare the maximum to 100. Record the max itself and the count of functions over threshold as continuous companions.

**Caveats.** The 100-line cutoff is conventional but arbitrary; sensitivity-test at 50/80/120. As with `large_class`, restrict to functions overlapping PR-changed lines for a "did the PR *create* this" variant versus "does the PR *touch* code like this".

### `god_object` — God Class touched

**Unit:** boolean {0,1} · **Reference:** [VA09]

**Definition.** Whether a touched class matches the God Class detection strategy: it centralizes intelligence (accesses foreign data), is complex, and is internally incohesive.

**Data required.** Head-SHA checkout; class-level metrics ATFD (Access To Foreign Data), WMC (Weighted Methods per Class = Σ of method cyclomatic complexities), TCC (Tight Class Cohesion); computable via PMD's `GodClass` rule (Java), or per-language metric tools.

**Computation.** `god_object = 1[∃ touched class c: ATFD(c) > 5 ∧ WMC(c) ≥ percentile₇₅(repo) ∧ TCC(c) < 1/3]` (the Lanza–Marinescu strategy as operationalized in [VA09]).

**Procedure.** Compute the three metrics per touched class at the head SHA (PMD emits the composite rule directly for Java; elsewhere compute ATFD/WMC/TCC from the AST). Apply the conjunction. Compute the repo-relative WMC percentile on the base SHA, cached.

**Caveats.** Full fidelity requires resolved types (to identify *foreign* data accesses), which is language-server-grade analysis; PMD covers Java/Apex well, other languages need approximations — declare per-language method fidelity. God Class prevalence is low; expect a rare, high-signal feature.

## Social and Collaboration

### `interaction_count` — total PR interactions

**Unit:** events · **Reference:** [T14]

**Definition.** The total volume of recorded activity on the PR across its lifetime: comments, reviews, inline comments, commits, and timeline events. A single intensity measure of how much *happened*.

**Data required.** Row counts of `pr_comments`, `pr_reviews`, `pr_review_comments`, `pr_commits`, `pr_timeline` for the PR.

**Computation.** `interaction_count = COUNT(pr_comments) + COUNT(pr_reviews) + COUNT(pr_review_comments) + COUNT(pr_commits) + COUNT(pr_timeline WHERE event ∉ {'commented','reviewed','committed'})`, non-bot.

**Procedure.** Count each table. Exclude from the timeline count the event types that mirror rows already counted from their dedicated tables (`commented`, `reviewed`, `committed`) to avoid double counting. Remove bot-attributed rows throughout. Sum.

**Caveats.** As a lifetime aggregate this feature is *not* available at submission time — use only for post-hoc explanation of outcomes, never in a submission-time prediction model. Strongly correlated with PR latency by construction (longer-open PRs accumulate events).

### `num_participants` (APR variant) — distinct participants, all channels

**Unit:** persons · **Reference:** [T14]

**Definition.** The APR set's wider participant count: everyone who *did* anything on the PR — commented, reviewed, committed, or triggered a timeline event — not just commenters.

**Data required.** User fields of all five tables: `pr_comments.user`, `pr_reviews.user`, `pr_review_comments.user`, `pr_commits.author`, `pr_timeline.actor`.

**Computation.** `num_participants_apr = |({comments} ∪ {reviews} ∪ {review_comments} ∪ {commit authors} ∪ {timeline actors}) \ Bots|`.

**Procedure.** Union the distinct user sets from all five sources. Note `pr_commits.author` is a name string, not a login — map via commit author login from **GQL** where joining matters, or accept name-level dedup. Remove bots; count.

**Caveats.** Supersedes the PR-level `num_participants` (comment-channels only); keep exactly one in a model. Same lifetime-aggregation warning as `interaction_count`.

### `conflict` — merge/workflow conflict signal

**Unit:** boolean {0,1} · **Reference:** [Z22]

**Definition.** Whether the PR encountered a merge conflict, combining the textual proxy with GitHub's live conflict state.

**Data required.** `comment_conflict` (above); **REST** `GET /pulls/{n}` → `mergeable_state` for open PRs.

**Computation.** `conflict = comment_conflict ∨ 1[mergeable_state = 'dirty']`.

**Procedure.** Compute the keyword signal from all comment bodies. For PRs open at collection time, OR in the live `mergeable_state`. For closed PRs rely on the keyword signal alone.

**Caveats.** `mergeable_state` is recomputed against the *current* base branch tip, so it is meaningless as a historical measurement for closed PRs — this is why the union with the textual proxy is used rather than the API field alone.

## Code Size and Complexity

*Same head-SHA checkout and touched-file scoping as Static Quality; compute base-SHA values for deltas.*

### `cyclomatic_complexity` — aggregate control-flow complexity

**Unit:** Σ CC (dimensionless) · **Reference:** [M76]

**Definition.** McCabe cyclomatic complexity summed over all functions in the PR's touched files: the number of linearly independent control-flow paths, `E − N + 2` per function's flow graph.

**Data required.** Head-SHA (and base-SHA, for the delta) checkout; touched files; `lizard` (multi-language CCN) or `radon cc` (Python).

**Computation.** `cyclomatic_complexity = Σ_{f ∈ touched} Σ_{fn ∈ f} CCN(fn)`, where `CCN(fn) = E_fn − N_fn + 2` (equivalently: 1 + number of decision points). Delta variant: `CC(head) − CC(base)` over the same file set.

**Procedure.** Run `lizard` on touched files at the head SHA; sum the CCN column. Repeat at the base SHA (files may not exist there — treat missing as 0). Report the head-SHA sum, the delta, and the max-function CCN; the delta is the PR's own contribution and usually the better predictor.

**Caveats.** Absolute sums scale with file size, confounding with `loc` — the delta and the max are the size-robust forms. Language coverage in `lizard` is broad but not universal; `NULL` for unsupported languages.

### `loc` — lines of code touched, including comments

**Unit:** lines · **Reference:** [G14]

**Definition.** The total size of the files the PR modifies (not the diff size): how much code a reviewer must potentially understand as context.

**Data required.** Head-SHA checkout; touched-file list; `cloc --by-file`.

**Computation.** `loc = Σ_{f ∈ touched} (code(f) + comments(f) + blanks(f))` — total physical lines of each touched file at the head SHA.

**Procedure.** Run `cloc --by-file` over the touched files; sum the three per-file columns (or count raw lines with `wc -l`, which is equivalent for physical lines). Keep this distinct from `codechurn` (diff magnitude) — the two are complementary and only weakly correlated.

**Caveats.** Deleted files have no head-SHA content; use their base-SHA size so file deletions still register context size. Binary files are excluded.

### `halstead_volume` — Halstead program volume

**Unit:** bits · **Reference:** [HA77]

**Definition.** Halstead's volume `V = N·log₂(n)`: program length `N` (total operators + operands) scaled by the log of vocabulary size `n` (distinct operators + operands). An information-theoretic size/complexity measure of the touched code.

**Data required.** Head-SHA checkout; touched files; a Halstead-capable analyzer (`radon hal` for Python, `multimetric` multi-language, or a lexer-based custom count).

**Computation.** Per file: `N = N₁ + N₂` (total operator and operand occurrences), `n = n₁ + n₂` (distinct operators and operands), `V_f = N·log₂(n)`. Aggregate: `halstead_volume = Σ_{f ∈ touched} V_f`.

**Procedure.** Lex each touched file into operators and operands per the tool's language rules. Compute per-file volume; sum. Record the mean per-file volume as a size-normalized companion.

**Caveats.** Operator/operand classification is convention-dependent and differs across tools — a single tool must be used for the whole dataset. Halstead metrics are contested as complexity measures ([SH88]'s critique applies equally here); interpret as a size-family feature, correlated with `loc`.

### `nesting_depth` — maximum control-structure nesting

**Unit:** levels · **Reference:** [D84]

**Definition.** The deepest nesting of control structures (if/for/while/switch/try) anywhere in the touched files. Deep nesting is a classic comprehension-cost factor.

**Data required.** Head-SHA checkout; touched files; an AST parser (tree-sitter) or `lizard -ENS` (nesting extension).

**Computation.** `nesting_depth = max_{s ∈ S} depth(s)` over all control structures `S` in touched files, where `depth` counts enclosing control structures inclusively.

**Procedure.** Parse each touched file to an AST. Walk it, incrementing a counter on entering any control-structure node and decrementing on exit; track the maximum. Take the max over files; record the mean-of-file-maxima as a robust companion.

**Caveats.** Language constructs map unevenly (Python comprehensions, Rust `match`, callbacks/lambdas) — define the counted node set per grammar and keep it versioned. The max is sensitive to a single outlier function; that is intended (it flags the worst spot), but pair with the mean for stability.

## Process

### `prev_pr` — author's prior PRs (APR alias)

**Unit:** PRs · **Reference:** [G14]

**Definition.** Number of PRs the author submitted before this one — identical to `prev_pullreqs` in the Developer section; listed in the APR signal set under this name.

**Data required / Computation / Procedure.** See `prev_pullreqs`. `prev_pr = COUNT(pull_request WHERE repo_id = R AND user = A AND created_at < t₀)`.

**Caveats.** Perfectly collinear with `prev_pullreqs` — include exactly one of the two names in any model. A cross-repo variant (author's PRs anywhere on GitHub, via GQL search without the repo qualifier) measures general rather than project-specific experience; keep the two variants separate.

### `linked_issues` — issues linked after submission

**Unit:** issues · **Reference:** [Z22]

**Definition.** How many issues were linked to the PR *after* it was created — post-hoc traceability added during review (maintainers connecting the PR to the bugs it addresses).

**Data required.** `pr_timeline` rows with `event ∈ {'cross-referenced', 'connected'}`; `related_issue` (with its `source` column) for cross-checking; `t₀`.

**Computation.** `linked_issues = |DISTINCT issues referenced by pr_timeline events with event ∈ {'cross-referenced','connected'} AND created_at > t₀|`.

**Procedure.** Scan the timeline for linking events dated after `t₀`. Resolve each to its issue (the event's subject; join against `related_issue`/`issue` via issue number). Deduplicate issues linked multiple times. Count. Links present *at* creation (in the body, counted by `hash_tag`) are deliberately excluded — the two features capture different behaviors.

**Caveats.** `cross-referenced` fires for *any* mention from another issue/PR, including tangential ones; `connected` (manual "linked issues" UI action) is the precise signal but rarer. Report both counts.

### `codechurn` — magnitude of code modification (APR alias)

**Unit:** lines · **Reference:** [N05]

**Definition.** Lines added plus deleted in the PR's final diff — identical to `src_churn_close`; listed in the APR set under the code-churn name from the defect-prediction literature.

**Data required / Computation / Procedure.** See `src_churn_close`. `codechurn = pull.additions + pull.deletions` (**REST** `GET /pulls/{n}`).

**Caveats.** Collinear with `src_churn_close` — keep one. [N05] argues *relative* churn (churn normalized by file size) predicts defects better than absolute churn; `codechurn / loc` is the corresponding relative form and worth adding as a derived feature.

### `author_experience` — account longevity

**Unit:** years · **Reference:** [Z22]

**Definition.** Age of the author's GitHub account at PR creation. Account longevity proxies platform experience independent of this project.

**Data required.** `user.created_at` for `login = A` (present in the local `user` table); `t₀`.

**Computation.** `author_experience = (t₀ − user.created_at) / 365.25 d`.

**Procedure.** Join `pull_request.user → user`. Subtract the account creation timestamp from `t₀`; divide by 365.25. Keep fractional years.

**Caveats.** Account age is fixed at creation, so unlike followers there is *no* snapshot bias — this value is exactly reconstructible. It is, however, a weak proxy: dormant accounts age without accruing experience; pair with `prev_pr` (activity-based) rather than substituting for it.

---

## References

- **[G14]** Gousios, Pinzger, van Deursen. *An Exploratory Study of the Pull-Based Software Development Model.* ICSE 2014. https://doi.org/10.1145/2568225.2568260
- **[G15]** Gousios, Zaidman, Storey, van Deursen. *Work Practices and Challenges in Pull-Based Development: The Integrator's Perspective.* ICSE 2015. https://doi.org/10.1109/ICSE.2015.55
- **[T14]** Tsay, Dabbish, Herbsleb. *Influence of Social and Technical Factors for Evaluating Contribution in GitHub.* ICSE 2014. https://doi.org/10.1145/2568225.2568315
- **[Y15]** Yu, Wang, Filkov, Devanbu, Vasilescu. *Wait for It: Determinants of Pull Request Evaluation Latency on GitHub.* MSR 2015. https://doi.org/10.1109/MSR.2015.42
- **[V15]** Vasilescu, Yu, Wang, Devanbu, Filkov. *Quality and Productivity Outcomes Relating to Continuous Integration in GitHub.* ESEC/FSE 2015. https://doi.org/10.1145/2786805.2786850
- **[B16]** Baysal, Kononenko, Holmes, Godfrey. *Investigating Technical and Non-Technical Factors Influencing Modern Code Review.* EMSE 21(3), 2016. https://doi.org/10.1007/s10664-015-9366-8
- **[TR17]** Terrell, Kofink, Middleton, Rainear, Murphy-Hill, Parnin, Stallings. *Gender Differences and Bias in Open Source: Pull Request Acceptance of Women Versus Men.* PeerJ CS 2017. https://doi.org/10.7717/peerj-cs.111
- **[S05]** Śliwerski, Zimmermann, Zeller. *When Do Changes Induce Fixes?* MSR 2005. https://doi.org/10.1145/1082983.1083147
- **[Z22]** Zhang, Yu, Gousios, Rastogi. *Pull Request Latency Explained: An Empirical Overview.* EMSE 27(126), 2022. https://doi.org/10.1007/s10664-022-10143-4
- **[M76]** McCabe. *A Complexity Measure.* IEEE TSE 2(4), 1976. https://doi.org/10.1109/TSE.1976.233837
- **[HA77]** Halstead. *Elements of Software Science.* Elsevier, 1977.
- **[SH88]** Shepperd. *A Critique of Cyclomatic Complexity as a Software Metric.* Software Engineering Journal 3(2), 1988. https://doi.org/10.1049/sej.1988.0003
- **[D84]** Dunsmore. *The Effect of Nesting Depth on Program Comprehension.* JSS 4(3), 1984. https://doi.org/10.1016/0164-1212(84)90002-1
- **[F99]** Fowler. *Refactoring: Improving the Design of Existing Code.* Addison-Wesley, 1999. (Large Class, Long Method smells)
- **[N05]** Nagappan, Ball. *Use of Relative Code Churn Measures to Predict System Defect Density.* ICSE 2005. https://doi.org/10.1145/1062455.1062514
- **[AY08]** Ayewah, Pugh, Hovemeyer, Morgenthaler, Penix. *Using Static Analysis to Find Bugs.* IEEE Software 25(5), 2008. https://doi.org/10.1109/MS.2008.130
- **[RC09]** Roy, Cordy, Koschke. *Comparison and Evaluation of Code Clone Detection Techniques and Tools.* Science of Computer Programming 74(7), 2009. https://doi.org/10.1016/j.scico.2009.02.007
- **[VA09]** Vaucher, Khomh, Moha, Guéhéneuc. *Tracking Design Smells: Lessons from a Study of God Classes.* WCRE 2009. https://doi.org/10.1109/WCRE.2009.23
- **[H12]** Hindle, Barr, Su, Gabel, Devanbu. *On the Naturalness of Software.* ICSE 2012. https://doi.org/10.1145/2337223.2337322
