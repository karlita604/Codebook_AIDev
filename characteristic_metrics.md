# Characteristic Metrics in Literature

Measurement notes: REST = GitHub REST API, GQL = GraphQL API. Fields like followers or open PR counts reflect *current* state — for values *at PR creation time*, use the timeline/events API or archives (GH Archive, GHTorrent).

## Pull Request Characteristics (PR-Level Signals)

| Metric | Description | How to Measure (GitHub) |
|---|---|---|
| `bug_fix` | fixes a bug? yes/no | Regex for "fix/bug/defect" in title/body, linked issues (`closes #n`), or `bug` label |
| `description_length` | length of PR description | Word/char count of `body` field (REST `GET /pulls/{n}`) |
| `hash_tag` | "#" tag exists? yes/no | Regex `#\d+` in `body` |
| `num_participants` | # of participants in PR comments | Unique authors across issue comments + review comments (GQL `participants` connection) |
| `ci_exists` | uses CI? yes/no | Non-empty check runs/statuses on head SHA (`GET /commits/{sha}/check-runs`) |
| `ci_latency` | minutes from PR creation to first CI build finish | First check run `completed_at` − PR `created_at` |
| `part_num_code` | # of participants in PR + commit comments | Unique authors in review comments + commit comments |
| `num_code_comments` | # of code comments | PR `review_comments` field |
| `reopen_or_not` | reopened? yes/no | `reopened` event in timeline API |
| `rework` | required substantial rework | Commits/churn pushed *after* first review, or force-push events in timeline |
| `friday_effect` | submitted on Friday? yes/no | Weekday of `created_at` |
| `has_comments` | has a comment? yes/no | `comments + review_comments > 0` |
| `num_comments` | # of comments | PR `comments` field |
| `num_comments_con` | # of contributor comments | Comments filtered by `author == PR author` |
| `at_tag` | "@" tag exists? yes/no | Regex `@\w+` in `body` |
| `num_code_comments_con` | # of contributor code comments | Review comments filtered by PR author |
| `ci_test_passed` | all CI builds passed? yes/no | All check runs `conclusion == success` |
| `comment_conflict` | "conflict" in comments? yes/no | Regex over all comment bodies; cross-check `mergeable_state == dirty` |
| `num_commits_open` / `_close` | # of commits at open / close | Open: commits with `committed_date < created_at`; close: `commits` field |
| `src_churn_open` / `_close` | lines changed at open / close | Close: `additions + deletions`; open: recompute diff over pre-creation commits (`git diff base...sha`) |
| `files_changed_open` / `_close` | files touched at open / close | Close: `changed_files`; open: same recomputed diff |
| `commits_touched_open` / `_close` | commits on touched files | `git log --follow` on each touched file in base repo |
| `churn_addition_open` / `_close` | added LOC | `additions` field / per-file `patch` in `GET /pulls/{n}/files` |
| `churn_deletion_open` / `_close` | deleted LOC | `deletions` field, same as above |
| `test_churn_open` / `_close` | test LOC changed | Sum churn over files matching test patterns (`test/`, `spec/`, `*_test.*`, `*.test.*`) |
| `test_inclusion_open` / `_close` | test case exists? yes/no | Any touched file matches test patterns |

## Developer Characteristics

| Metric | Description | How to Measure (GitHub) |
|---|---|---|
| `first_pr` | first PR? yes/no | Search API: author's PRs in repo with `created < this PR` == 0 |
| `prior_review_num` | # of previous reviews in project | Count reviews authored by user across repo PRs before creation date |
| `core_member` | core member? yes/no | `author_association` ∈ {OWNER, MEMBER, COLLABORATOR} |
| `first_response_time` | minutes to first reviewer response | Earliest comment/review by non-author − `created_at` |
| `contrib_gender` | gender | Name-based inference (e.g., genderComputer) — noisy, ethically sensitive |
| `contrib_affiliation` | contributor affiliation | Profile `company` field or commit email domain |
| `same_affiliation` | same affiliation? yes/no | Compare both profiles' `company`/email domain |
| `inte_affiliation` | integrator affiliation | `merged_by` user's profile `company` |
| `social_strength` | fraction of team interacted with, last 3 months | Comment/review interaction graph over prior 90 days of repo events |
| `prev_pullreqs` | # of previous PRs | Search API count, author's PRs before creation |
| `followers` | # of followers at creation | `GET /users/{login}` (current only — use GH Archive for historical) |
| `same_user` | contributor == integrator? yes/no | `user.login == merged_by.login` |

## Project Characteristics

| Metric | Description | How to Measure (GitHub) |
|---|---|---|
| `sloc` | executable LOC | `cloc`/`scc` on repo checked out at PR base SHA |
| `team_size` | active core members, last 3 months | Unique users who merged PRs or pushed to default branch in prior 90 days |
| `project_age` | months from repo creation to PR creation | Repo `created_at` vs PR `created_at` |
| `open_pr_num` | # of open PRs | Search `is:pr is:open` (current); GH Archive for point-in-time |
| `integrator_availability` | latest activity of top-2 integrators | Max event timestamp of two most active mergers before PR creation |
| `test_lines_per_kloc` | test LOC per KLOC | `cloc` on test dirs ÷ SLOC × 1000 |
| `test_cases_per_kloc` | test cases per KLOC | Count test functions (language-specific regex, e.g. `def test_`, `@Test`) ÷ KLOC |
| `asserts_per_kloc` | assertions per KLOC | Grep `assert` variants ÷ KLOC |
| `perc_external_contribs` | % external PR contributions | Share of merged PRs from non-core authors in prior window |
| `requester_succ_rate` | past PR success rate | Author's merged ÷ closed PRs before creation date |
