
In order to standardize the analysis of each pull request. There are different levels, there is the analysis at the metadata stage and at the visual stage.


### Repository Pull Request Life Cycle






### Characteristic Metrics in Literature

| Metric | Description | Unit | Formula | Steps | Ref |
|---|---|---|---|---|---|
| `bug_fix` | fixes a bug? | boolean {0,1} | `1 if regex('(fix(e[sd])?\|bug\|defect\|fault\|error)') on lower(title ∥ body) OR ∃ related_issue(pr_id) → issue with bug label OR ∃ pr_timeline(event='labeled', label~'bug')` | 1) Concatenate `pull_request.title` + `body`, lowercase. 2) Apply keyword regex. 3) Join `related_issue`→`issue`; fetch labels via REST `GET /issues/{number}/labels`. 4) Scan `pr_timeline` for `labeled` events with bug-like label. 5) OR the three signals. | [Z22] |
| `description_length` | length of PR description | words | `count(tokens(strip_md(pull_request.body)))` | 1) Take `body`. 2) Strip markdown, code blocks, URLs. 3) Split on whitespace. 4) Count tokens (0 if body NULL). | [Y15] |
| `hash_tag` | "#" issue tag exists? | boolean {0,1} | `1 if regex('#[0-9]+') on pull_request.body` | 1) Take `body`. 2) Remove code blocks (avoid `#` in code). 3) Match `#\d+`. | [Z22] |
| `num_participants` | # participants in PR discussion | persons | `\|{pr_comments.user} ∪ {pr_reviews.user} ∪ {pr_review_comments.user}\| − 1{A ∈ set}` | 1) Collect distinct `user` from the three comment tables for the PR (review comments join via `pr_reviews.id = pull_request_review_id`). 2) Union. 3) Exclude author `A` and bots (`login ~ '\[bot\]'`). 4) Count. | [T14] |
| `ci_exists` | uses CI? | boolean {0,1} | `1 if (check_runs.total_count + statuses.total_count) > 0` for head SHA | 1) Head SHA = last `pr_commits.sha` (order by `pr_timeline` `committed` events). 2) REST `GET /repos/{o}/{r}/commits/{sha}/check-runs` and `.../status`. 3) 1 if either non-empty. | [V15] |
| `ci_latency` | time to first CI result | minutes | `(min(check_run.completed_at) − t₀)/60s` | 1) Get check runs for first head SHA after open (REST as above). 2) Take earliest `completed_at ≥ t₀`. 3) Subtract `t₀`, convert to minutes. NULL if `ci_exists=0`. | [Y15] |
| `part_num_code` | # participants in code + commit comments | persons | `\|{pr_review_comments.user} ∪ {commit_comments.user}\|` | 1) Distinct `pr_review_comments.user`. 2) For each `pr_commits.sha`: REST `GET /repos/{o}/{r}/commits/{sha}/comments`, collect users. 3) Union, drop bots, count. | [Z22] |
| `num_code_comments` | # inline code comments | comments | `COUNT(pr_review_comments ⋈ pr_reviews ON pull_request_review_id WHERE pr_reviews.pr_id = PR)` | 1) Join `pr_review_comments` to `pr_reviews`. 2) Filter to this PR. 3) Count rows (include replies `in_reply_to_id NOT NULL`; report with/without). | [Z22] |
| `reopen_or_not` | reopened? | boolean {0,1} | `1 if ∃ pr_timeline(pr_id, event='reopened')` | 1) Query `pr_timeline` for the PR. 2) Check any `event='reopened'`. | [Z22] |
| `rework` | commits after first review feedback | commits (or {0,1}) | `COUNT(pr_timeline(event='committed', created_at > min(pr_reviews.submitted_at))) + COUNT(event='head_ref_force_pushed')` | 1) Find first review time `min(pr_reviews.submitted_at)`. 2) Count `committed` timeline events after it. 3) Add force-push events. 4) Binary variant: 1 if count > 0. | [G15] |
| `friday_effect` | submitted on Friday? | boolean {0,1} | `1 if weekday(t₀) = Friday` | 1) Take `t₀` (UTC; optionally shift by author timezone from commit metadata). 2) Compute weekday. 3) Compare to Friday. | [S05], [Z22] |
| `has_comments` | any comment? | boolean {0,1} | `1 if COUNT(pr_comments) + COUNT(pr_review_comments) > 0` | 1) Count rows in both tables for the PR. 2) Threshold at 0. | [Z22] |
| `num_comments` | # discussion comments | comments | `COUNT(pr_comments WHERE pr_id = PR)` | 1) Count `pr_comments` rows. 2) Exclude bot authors. 3) (Variant incl. code comments: add `num_code_comments`.) | [G14] |
| `num_comments_con` | # contributor comments | comments | `COUNT(pr_comments WHERE user = A)` | 1) Filter `pr_comments` to `user = pull_request.user`. 2) Count. | [Z22] |
| `at_tag` | "@" mention exists? | boolean {0,1} | `1 if regex('@[A-Za-z0-9-]+') on body ∪ pr_comments.body` | 1) Concatenate `body` + all `pr_comments.body`. 2) Strip code blocks/emails. 3) Match mention regex. | [Y15] |
| `num_code_comments_con` | # contributor code comments | comments | `COUNT(pr_review_comments WHERE user = A)` (joined to this PR) | 1) Join as in `num_code_comments`. 2) Filter `user = A`. 3) Count. | [Z22] |
| `ci_test_passed` | all CI builds passed? | boolean {0,1} | `1 if ∀ check_runs(final head SHA): conclusion='success'` | 1) Final head SHA = last `pr_commits.sha`. 2) REST check-runs + combined status. 3) 1 iff every conclusion/state is `success`; NULL if `ci_exists=0`. | [V15] |
| `comment_conflict` | "conflict" mentioned? | boolean {0,1} | `1 if regex('conflict') on lower(pr_comments.body ∪ pr_reviews.body ∪ pr_review_comments.body)` | 1) Concatenate all comment bodies. 2) Lowercase, regex `conflict`. 3) Cross-validate with REST `GET /pulls/{n}` → `mergeable_state='dirty'`. | [Z22] |
| `num_commits_open` | # commits at open | commits | `COUNT(pr_timeline(event='committed', created_at < t₀))` | 1) Get `committed` events (commit author date). 2) Keep those dated before `t₀`. 3) Count. (Approximation — rebases rewrite dates; flag PRs with force-pushes.) | [G14] |
| `num_commits_close` | # commits at close | commits | `COUNT(pr_commits WHERE pr_id = PR)` | 1) Count all rows in `pr_commits`. 2) Δ-variant: `num_commits_close − num_commits_open`. | [G14] |
| `src_churn_open` | LOC changed at open | lines | `Σ pr_commit_details.commit_stats_total` over commits dated `< t₀` | 1) Identify pre-open SHAs (step 1–2 of `num_commits_open`). 2) Sum `commit_stats_additions + commit_stats_deletions` once per SHA. | [G14] |
| `src_churn_close` | LOC changed at close | lines | `pull.additions + pull.deletions` (REST `GET /pulls/{n}`) | 1) Use final-diff totals from REST (avoids double-counting across commits). 2) Fallback: `Σ (additions+deletions)` over `pr_commit_details` rows. | [G14] |
| `files_changed_open` | files touched at open | files | `COUNT(DISTINCT pr_commit_details.filename WHERE sha ∈ pre-open SHAs)` | 1) Restrict `pr_commit_details` to pre-open SHAs. 2) Count distinct `filename`. | [G14] |
| `files_changed_close` | files touched at close | files | `COUNT(DISTINCT pr_commit_details.filename WHERE pr_id = PR)` | 1) Count distinct `filename` over all commits. 2) Cross-check REST `changed_files`. | [G14] |
| `commits_touched_open` / `_close` | recent activity on touched files | commits | `Σ_f COUNT(REST GET /commits?path=f&since=t−90d&until=t)` for `t ∈ {t₀, t₁}` | 1) List distinct filenames (open/close sets as above). 2) For each file, count base-repo commits in the 90 days before `t`. 3) Sum over files. | [G14] |
| `churn_addition_open` / `_close` | added LOC | lines | open: `Σ commit_stats_additions` (pre-open SHAs); close: `pull.additions` | 1) Same SHA selection as `src_churn`. 2) Sum additions only. | [G14] |
| `churn_deletion_open` / `_close` | deleted LOC | lines | open: `Σ commit_stats_deletions` (pre-open SHAs); close: `pull.deletions` | 1) As above with deletions. | [G14] |
| `test_churn_open` / `_close` | test LOC changed | lines | `Σ (additions + deletions)` over `pr_commit_details` rows `WHERE filename ~ TEST_RE` (open: pre-open SHAs only) | 1) Filter `pr_commit_details` rows by `TEST_RE` on `filename`. 2) Restrict SHAs for the open variant. 3) Sum per-file `additions + deletions`. | [G14] |
| `test_inclusion_open` / `_close` | touches tests? | boolean {0,1} | `1 if ∃ pr_commit_details.filename ~ TEST_RE` (open: pre-open SHAs) | 1) Same filter as `test_churn`. 2) Threshold at ≥ 1 matching file. | [G14], [T14] |

## Developer Characteristics

| Metric | Description | Unit | Formula | Steps | Ref |
|---|---|---|---|---|---|
| `first_pr` | author's first PR in repo? | boolean {0,1} | `1 if COUNT(pull_request WHERE repo_id = R AND user = A AND created_at < t₀) = 0` | 1) Query local `pull_request` table (or GQL `search(query:"repo:o/r type:pr author:A created:<t₀") { issueCount }`). 2) Threshold at 0. | [Z22] |
| `prior_review_num` | # prior reviews by author | reviews | `COUNT(DISTINCT pr_reviews.pr_id WHERE user = A AND submitted_at < t₀ AND pr_id ∈ repo R)` | 1) Join `pr_reviews` to `pull_request` on `pr_id` to restrict to repo. 2) Filter reviewer = A, `submitted_at < t₀`. 3) Count distinct PRs reviewed. | [Z22] |
| `core_member` | author is core member? | boolean {0,1} | `1 if author_association ∈ {OWNER, MEMBER, COLLABORATOR}` | 1) GQL `pullRequest { authorAssociation }` (or REST `GET /pulls/{n}` → `author_association`). 2) Map to boolean. Fallback: A merged ≥ 1 PR in prior 90 days (`pr_timeline` `merged` events). | [G14] |
| `first_response_time` | time to first non-author response | minutes | `(min over {pr_comments, pr_reviews, pr_review_comments} of created_at/submitted_at WHERE user ≠ A AND user ∉ bots) − t₀` | 1) Collect earliest timestamp per table excluding author + bots. 2) Take global min. 3) Subtract `t₀`, convert to minutes; NULL if no response. | [Y15] |
| `contrib_gender` | contributor gender | category {m, f, unknown} | `genderComputer(REST GET /users/{A}.name, .location)` | 1) Fetch profile name + location. 2) Run name-based inference tool. 3) Label `unknown` when ambiguous. ⚠ Noisy and ethically sensitive; report only in aggregate. | [TR17] |
| `contrib_affiliation` | contributor affiliation | category (org string) | `normalize(REST GET /users/{A}.company ∥ email_domain(commits by A))` | 1) Fetch profile `company`. 2) Fallback: domain of commit author email (GQL `commit { author { email } }`). 3) Normalize (strip `@`, lowercase, map aliases). | [B16] |
| `same_affiliation` | contributor = integrator org? | boolean {0,1} | `1 if contrib_affiliation = inte_affiliation ≠ unknown` | 1) Compute both affiliations. 2) Compare normalized strings; NULL if either unknown. | [B16] |
| `inte_affiliation` | integrator affiliation | category (org string) | `normalize(REST GET /users/{I}.company)` where `I = pr_timeline.actor(event='merged' or final 'closed')` | 1) Get integrator login from the `merged` (else last `closed`) timeline event `actor`. 2) Fetch and normalize `company`. | [B16] |
| `social_strength` | fraction of core team A interacted with (90 d) | ratio [0,1] | `\|core ∩ interacted(A, t₀−90d, t₀)\| / \|core\|` | 1) Core = users with `merged` timeline events in repo in window. 2) Interacted = users co-occurring with A in `pr_comments`/`pr_reviews`/`pr_review_comments` on the same PRs in window. 3) Divide intersection by core size. | [T14] |
| `prev_pullreqs` | # author's prior PRs | PRs | `COUNT(pull_request WHERE repo_id = R AND user = A AND created_at < t₀)` | 1) Same query as `first_pr`, keep the count. | [G14] |
| `followers` | author followers at t₀ | persons | `user.followers WHERE user.login = A` | 1) Read from local `user` table (collection-time snapshot). 2) For true value at `t₀`, replay `FollowEvent`s from GH Archive up to `t₀`. | [T14] |
| `same_user` | author = integrator? | boolean {0,1} | `1 if A = pr_timeline.actor(event='merged')` | 1) Get `merged` event actor. 2) Compare logins; NULL if never merged. | [Z22] |

## Project Characteristics

| Metric | Description | Unit | Formula | Steps | Ref |
|---|---|---|---|---|---|
| `sloc` | executable LOC at t₀ | lines (KLOC) | `cloc(checkout(base_sha)).code` | 1) Base SHA via GQL `pullRequest { baseRefOid }`. 2) `git clone` + `git checkout {base_sha}`. 3) Run `cloc`/`scc`; take code lines (comments/blanks excluded). | [G14] |
| `team_size` | active core members (90 d) | persons | `\|{pr_timeline.actor: event='merged', created_at ∈ [t₀−90d, t₀)} ∪ {default-branch pushers}\|` | 1) Distinct merge actors across repo PRs in window. 2) Add committers to default branch (REST `GET /commits?since&until`). 3) Union, drop bots, count. | [G14] |
| `project_age` | repo age at t₀ | months | `(t₀ − repo.created_at) / 30.44 d` | 1) REST `GET /repos/{o}/{r}` → `created_at` (not in local `repository` table). 2) Subtract, divide by 30.44 days. | [G14] |
| `open_pr_num` | open PRs at t₀ | PRs | `COUNT(pull_request WHERE repo_id = R AND created_at < t₀ AND (closed_at IS NULL OR closed_at > t₀))` | 1) Single query over local `pull_request` — fully point-in-time reconstructible. | [G14] |
| `integrator_availability` | recency of top-2 integrators | hours | `min over I∈top2 of (t₀ − last_activity(I))` | 1) Top-2 integrators = most `merged` events in prior 90 days. 2) `last_activity(I)` = max timestamp of I across `pr_timeline`/`pr_comments`/`pr_reviews` before `t₀`. 3) Take min gap, in hours. | [Z22] |
| `test_lines_per_kloc` | test LOC density | lines/KLOC | `cloc(files ~ TEST_RE).code / (sloc/1000)` | 1) From the `sloc` checkout, classify files by `TEST_RE`. 2) Count test code lines. 3) Divide by KLOC. | [G14] |
| `test_cases_per_kloc` | test-case density | cases/KLOC | `count(matches(TESTCASE_RE)) / (sloc/1000)` | 1) Per language define `TESTCASE_RE` (`def test_`, `@Test`, `it\(`, `func Test`). 2) Grep the checkout. 3) Divide by KLOC. | [G14] |
| `asserts_per_kloc` | assertion density | asserts/KLOC | `count(matches('assert')) / (sloc/1000)` | 1) Grep `assert`-family calls in the checkout (language-aware). 2) Divide by KLOC. | [G14] |
| `perc_external_contribs` | share of external contributions | % | `100 × COUNT(merged PRs, author ∉ core, window) / COUNT(merged PRs, window)` | 1) Merged PRs in `[t₀−90d, t₀)` from `pull_request.merged_at`. 2) Core set as in `team_size`. 3) Compute percentage. | [G14] |
| `requester_succ_rate` | author's past merge rate | ratio [0,1] | `COUNT(pull_request WHERE user=A AND merged_at IS NOT NULL AND closed_at < t₀) / COUNT(... closed_at < t₀)` | 1) Author's PRs in repo closed before `t₀`. 2) Divide merged by total closed; NULL if denominator 0. | [G14] |



- **[G14]** Gousios, Pinzger, van Deursen. *An Exploratory Study of the Pull-Based Software Development Model.* ICSE 2014. https://doi.org/10.1145/2568225.2568260
- **[G15]** Gousios, Zaidman, Storey, van Deursen. *Work Practices and Challenges in Pull-Based Development: The Integrator's Perspective.* ICSE 2015. https://doi.org/10.1109/ICSE.2015.55
- **[T14]** Tsay, Dabbish, Herbsleb. *Influence of Social and Technical Factors for Evaluating Contribution in GitHub.* ICSE 2014. https://doi.org/10.1145/2568225.2568315
- **[Y15]** Yu, Wang, Filkov, Devanbu, Vasilescu. *Wait for It: Determinants of Pull Request Evaluation Latency on GitHub.* MSR 2015. https://doi.org/10.1109/MSR.2015.42
- **[V15]** Vasilescu, Yu, Wang, Devanbu, Filkov. *Quality and Productivity Outcomes Relating to Continuous Integration in GitHub.* ESEC/FSE 2015. https://doi.org/10.1145/2786805.2786850
- **[B16]** Baysal, Kononenko, Holmes, Godfrey. *Investigating Technical and Non-Technical Factors Influencing Modern Code Review.* EMSE 21(3), 2016. https://doi.org/10.1007/s10664-015-

### Visual Inspection


From the visual inspection, we derive the different metrics, ontop of the metrics already established for the AIDev dataset.



### Metric Analysis
