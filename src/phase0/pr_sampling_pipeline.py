"""
Phase 1b: Track B1/B2 PR-event sampling.

Context (see Writing/Longitudinal.md section 5): AIDev only covers
2024-12-24 to 2025-07-30 and only agent-authored PRs, so it can supply each
repo's intervention point (Phase 1a, repo_pr_selection.py) but not the
process-metrics backbone (PR size, merge latency, review activity) across
the full study window. That has to come from a fresh GitHub API pull, which
is what this script does.

Two tracks, both PR *identity* (number, timestamps, state) - not yet the
deeper diff/review stats (additions/deletions/review comments), which need
a per-PR follow-up call and are left for a later step, same phased approach
as Phase 1c (manifest) -> Phase 1e (materialize) for Track A:

- B1: monthly, fixed calendar grid, 2022-01-01 - 2026-03-31 (51 months). A
  2-day window (day 1-2 UTC) per month, up to 10 PRs by created_at (cap
  510/repo). Months with fewer than 10 PRs in the window keep whatever's
  available, flagged is_undersampled - not excluded or padded.
- B2: not calendar-anchored. The 10 PRs immediately preceding and the 10
  immediately following each repo's intervention PR (by created_at).

Needs GITHUB_TOKEN (unauthenticated GitHub API access is 60 req/hr, not
viable at this scale - see decision log in Longitudinal.md section 10).
Uses the Search API (GET /search/issues?q=repo:...+is:pr+created:...),
which has its own tighter rate limit (30 req/min authenticated) independent
of the 5000/hr core limit - SEARCH_PAUSE_SECONDS paces requests under that.

Estimated cost: (51 B1 windows + 2 B2 queries) x N repos = search requests,
at ~24/min per token. That's ~11 minutes at 5 repos, but scales linearly -
~3.5 hours at --target-total 100 on a single token. Set GITHUB_TOKENS_FILE
to a local file (one token per line, blank lines/#-comments ignored, kept
out of git - see .gitignore) with additional tokens to round-robin
requests across; each token still sees its own traffic paced under 24/min
(TokenPool below halves/thirds/etc. the pause between requests as tokens
are added, since each token gets its own independent rate-limit bucket),
so aggregate throughput scales with token count - 2 tokens roughly halves
the wall-clock estimate above.

Resumable by design (same shape as long_analysis.py's Phase 1d run): each
unit of work is one search query - a B1 month-window or a B2 before/after
side - keyed by (repo_id, track, unit). Every unit's outcome (including a
window that legitimately has zero PRs in it) is recorded in a *query ledger*
CSV before moving on, since PR rows alone can't tell "not queried yet" apart
from "queried, found nothing". A crash or Ctrl-C loses at most the one unit
in flight; rerunning the same command skips every unit already in the
ledger and picks up where it left off. Prints one line per unit as it
completes (`[ok]`/`[FAIL]`, running count, PRs found, ETA) - run it directly
in your own terminal to watch it live.
"""

import argparse
import itertools
import json
import os
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_pr_selection import suggest_pilot  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "pr_samples"
REPO_SUMMARY_GLOB = ROOT / "results" / "repos"

GITHUB_API = "https://api.github.com"
WINDOW_START = "2022-01-01"
WINDOW_END = "2026-03-31"
B1_PRS_PER_WINDOW = 10
B2_PRS_PER_SIDE = 10
SEARCH_PAUSE_SECONDS = 2.5  # ~24 req/min, under the 30/min search-API cap


def _make_session(token):
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    return session


def _load_extra_tokens(path):
    """One token per line; blank lines and #-comment lines skipped. Kept
    as a local file (path given via GITHUB_TOKENS_FILE, gitignored - see
    .gitignore) rather than a comma-separated env var, since that's the
    natural place to drop additional personal tokens without fussing with
    shell quoting/escaping for each one."""
    lines = Path(path).read_text().splitlines()
    return [
        line.strip() for line in lines
        if line.strip() and not line.strip().startswith("#")
    ]


class TokenPool:
    """Round-robins requests.Session objects, one per GITHUB_TOKEN, so
    aggregate Search API throughput scales with token count while each
    individual token's own request rate stays under its 30/min cap - see
    module docstring. A single-token pool behaves identically to the old
    plain requests.Session (len() == 1, no rate-limit change)."""

    def __init__(self, tokens):
        if not tokens:
            raise ValueError("TokenPool needs at least one token")
        self._sessions = [_make_session(t) for t in tokens]
        self._cycle = itertools.cycle(self._sessions)

    def get(self, *args, **kwargs):
        return next(self._cycle).get(*args, **kwargs)

    def __len__(self):
        return len(self._sessions)


def get_session():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit(
            "GITHUB_TOKEN is not set. Unauthenticated GitHub API access is capped "
            "at 60 requests/hour, which Phase 1b needs far more than.\n"
            'PowerShell: $env:GITHUB_TOKEN = "ghp_..."   (current session)\n'
            '            setx GITHUB_TOKEN "ghp_..."     (persisted, new terminal needed)\n'
            "then rerun this script."
        )
    tokens = [token]
    tokens_file = os.environ.get("GITHUB_TOKENS_FILE")
    if tokens_file:
        extra = _load_extra_tokens(tokens_file)
        tokens += extra
        print(
            f"GITHUB_TOKENS_FILE: {len(extra)} additional token(s) loaded "
            f"from {tokens_file} ({len(tokens)} total - requests round-"
            "robin across them, pacing scaled accordingly)",
            flush=True,
        )
    return TokenPool(tokens)


def _search_prs(session, full_name, query_extra, sort="created", order="asc", per_page=10):
    """One page (<=per_page) of the Search API's issues/PRs endpoint.
    Retries on primary/secondary rate limiting. Returns (items, total_count).
    `session` is a TokenPool (possibly wrapping just one token) - the pause
    between requests is divided by the token count, since round-robining
    means each individual token only receives 1/N of the aggregate request
    rate."""
    q = f"repo:{full_name} is:pr {query_extra}"
    while True:
        resp = session.get(
            f"{GITHUB_API}/search/issues",
            params={"q": q, "sort": sort, "order": order, "per_page": per_page},
        )
        if resp.status_code == 403:
            retry_after = resp.headers.get("Retry-After")
            if retry_after:
                wait = int(retry_after) + 1
            else:
                reset = int(resp.headers.get("X-RateLimit-Reset", time.time() + 60))
                wait = max(reset - time.time(), 1) + 1
            print(f"    [rate limited] sleeping {wait:.0f}s")
            time.sleep(wait)
            continue
        resp.raise_for_status()
        break
    time.sleep(SEARCH_PAUSE_SECONDS / len(session))
    data = resp.json()
    return data.get("items", []), data.get("total_count", 0)


def _pr_row(item, repo_row, track, window_start=None, window_end=None,
            relative_position=None, is_undersampled=None):
    pr = item.get("pull_request") or {}
    return {
        "repo_id": repo_row["repo_id"],
        "full_name": repo_row["full_name"],
        "language": repo_row["language"],
        "track": track,
        "window_start": window_start,
        "window_end": window_end,
        "relative_position": relative_position,
        "pr_number": item["number"],
        "pr_id": item["id"],
        "title": item["title"],
        "state": item["state"],
        "created_at": item["created_at"],
        "closed_at": item["closed_at"],
        "merged_at": pr.get("merged_at"),
        "comments": item["comments"],
        "html_url": item["html_url"],
        "is_undersampled": is_undersampled,
    }


def monthly_windows(start=WINDOW_START, end=WINDOW_END):
    """Track B1 grid: one 2-day (day 1-2 UTC) window per calendar month."""
    months = pd.date_range(start=start, end=end, freq="MS", tz="UTC")
    return [(m, m + pd.Timedelta(days=1)) for m in months]


def build_units(pilot, tracks):
    """One unit = one search query (the thing that can fail/resume
    independently): a B1 month-window, or a B2 before/after side. Keyed by
    (repo_id, track, unit) - see _unit_key()."""
    units = []
    for _, repo_row in pilot.iterrows():
        if "B1" in tracks:
            for win_start, win_end in monthly_windows():
                units.append({
                    "repo_row": repo_row, "track": "B1",
                    "unit": win_start.date().isoformat(),
                    "window_start": win_start, "window_end": win_end,
                })
        if "B2" in tracks:
            for side in ("before", "after"):
                units.append({"repo_row": repo_row, "track": "B2", "unit": side})
    return units


def _unit_key(u):
    return (u["repo_row"]["repo_id"], u["track"], u["unit"])


def fetch_unit(session, unit):
    """Runs the one search query this unit represents. Returns
    (pr_rows, total_count, is_undersampled)."""
    repo_row = unit["repo_row"]

    if unit["track"] == "B1":
        win_start, win_end = unit["window_start"], unit["window_end"]
        query = f"created:{win_start.date()}..{win_end.date()}"
        items, total = _search_prs(session, repo_row["full_name"], query, per_page=B1_PRS_PER_WINDOW)
        undersampled = total < B1_PRS_PER_WINDOW
        rows = [
            _pr_row(item, repo_row, track="B1",
                    window_start=win_start.date().isoformat(),
                    window_end=win_end.date().isoformat(),
                    is_undersampled=undersampled)
            for item in items
        ]
        return rows, total, undersampled

    # B2: "before" is queried newest-first then reversed so
    # relative_position runs chronologically, -10 (earliest) to -1 (latest
    # pre-intervention) / +1 to +10 (earliest to latest post-intervention).
    intervention = repo_row["intervention_date"]
    if unit["unit"] == "before":
        items, total = _search_prs(
            session, repo_row["full_name"], f"created:<{intervention}",
            sort="created", order="desc", per_page=B2_PRS_PER_SIDE,
        )
        items = list(reversed(items))
        rows = [
            _pr_row(item, repo_row, track="B2", relative_position=-(len(items) - i))
            for i, item in enumerate(items)
        ]
    else:
        items, total = _search_prs(
            session, repo_row["full_name"], f"created:>{intervention}",
            sort="created", order="asc", per_page=B2_PRS_PER_SIDE,
        )
        rows = [
            _pr_row(item, repo_row, track="B2", relative_position=i + 1)
            for i, item in enumerate(items)
        ]
    undersampled = total < B2_PRS_PER_SIDE
    return rows, total, undersampled


def _append_row(path, row_dict):
    """Append one row to a CSV immediately, header only if new - a crash or
    Ctrl-C loses at most the one row in flight, never anything already
    written."""
    write_header = not path.exists()
    pd.DataFrame([row_dict]).to_csv(path, mode="a", header=write_header, index=False)


def _load_done_units(ledger_path):
    """Units already recorded 'ok' in a prior (possibly interrupted) run of
    this exact scope - resume skips these. A previously errored unit is
    retried, since transient failures (rate limiting, a network blip) aren't
    guaranteed to repeat."""
    if not ledger_path.exists():
        return set()
    df = pd.read_csv(ledger_path)
    ok = df[df["status"] == "ok"]
    return set(zip(ok["repo_id"], ok["track"], ok["unit"]))


def _write_progress(progress_path, started_at, total, done, ok, failed, current_label):
    elapsed = time.time() - started_at
    rate = done / elapsed if elapsed > 0 else 0
    eta_seconds = (total - done) / rate if rate > 0 else None
    progress_path.write_text(json.dumps({
        "started_at": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "total": total, "done": done, "ok": ok, "failed": failed,
        "elapsed_seconds": round(elapsed, 1),
        "eta_seconds": round(eta_seconds, 1) if eta_seconds is not None else None,
        "current": current_label,
    }, indent=2))


def _format_eta(seconds):
    if seconds is None:
        return "eta ?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"eta {h}h{m:02d}m" if h else f"eta {m}m{s:02d}s"


def _latest_repo_summary():
    summary_files = sorted(REPO_SUMMARY_GLOB.glob("*-repo-summary-*.csv"))
    if not summary_files:
        raise FileNotFoundError(
            f"No repo-summary CSV found in {REPO_SUMMARY_GLOB} - "
            "run repo_pr_selection.py first"
        )
    return pd.read_csv(summary_files[-1])


def get_pilot_repos(pilot_size=5):
    """Reads the repo-summary CSV from Phase 1a rather than re-deriving the
    candidate list here (same reasoning as repo_snapshot_pipeline.py)."""
    return suggest_pilot(_latest_repo_summary(), n=pilot_size)


def get_target_repos(repos_file):
    """Targets an exact, externally-determined repo set instead of
    suggest_pilot's stratified n-based pick - needed because which repos
    end up e.g. RQ1 regression-eligible is a downstream data fact with no
    relationship to suggest_pilot's language-stratified ordering, so there's
    no n for which suggest_pilot(n) would reproduce that set. `repos_file`
    is a CSV with a full_name column, or a newline-delimited list of
    full_names (owner/repo). Every requested full_name must resolve against
    the latest repo-summary CSV (same source get_pilot_repos reads, so
    repo_id/language/intervention_date are available for B1/B2) - raises
    loudly rather than silently sampling a subset of what was asked for."""
    repo_summary = _latest_repo_summary()
    path = Path(repos_file)
    if path.suffix == ".csv":
        wanted = pd.read_csv(path)["full_name"].tolist()
    else:
        wanted = [line.strip() for line in path.read_text().splitlines() if line.strip()]

    target = repo_summary[repo_summary["full_name"].isin(wanted)]
    missing = set(wanted) - set(target["full_name"])
    if missing:
        raise ValueError(
            f"{len(missing)} repo(s) from {repos_file} not found in the "
            f"repo-summary CSV: {sorted(missing)}"
        )
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target-total", "--pilot-size", dest="target_total", type=int,
        default=5,
        help="how many repos to select (--pilot-size is a deprecated "
             "alias). Same growth-property caveat as "
             "repo_pr_selection.py's suggest_pilot() - see that module's "
             "docstring. Cost scales linearly with this - see the "
             "--dry-run grid-size estimate below before running a large "
             "value for real.",
    )
    parser.add_argument("--repo", help="Only sample this one full_name (owner/repo), for smoke-testing")
    parser.add_argument(
        "--repos-file",
        help="Path to a CSV (full_name column) or newline-delimited list of "
             "exact full_names to target, bypassing suggest_pilot's "
             "stratified --target-total pick entirely - use this to close "
             "coverage gaps against an externally-determined repo set (e.g. "
             "RQ1's regression-eligible repos). Overrides --target-total.",
    )
    parser.add_argument(
        "--tag", default="pr-sample",
        help="Output filename tag (default 'pr-sample') - override to keep "
             "a targeted run's output distinctly named from the general "
             "pilot-scaling runs, e.g. --tag pr-sample-rq1gap",
    )
    parser.add_argument("--tracks", default="B1,B2", help="Comma-separated subset of tracks to run")
    parser.add_argument("--dry-run", action="store_true",
                         help="Print grid sizes only, no API calls (no GITHUB_TOKEN needed)")
    args = parser.parse_args()

    pilot = get_target_repos(args.repos_file) if args.repos_file else get_pilot_repos(pilot_size=args.target_total)
    if args.repo:
        pilot = pilot[pilot["full_name"] == args.repo]
        if pilot.empty:
            raise SystemExit(f"{args.repo} not found in the target repo set")

    tracks = {t.strip().upper() for t in args.tracks.split(",")}
    units = build_units(pilot, tracks)
    total = len(units)
    print(f"{'[dry-run] ' if args.dry_run else ''}"
          f"{len(pilot)} repo(s), tracks={sorted(tracks)}, {total} query units total", flush=True)

    if args.dry_run:
        n_windows = len(monthly_windows())
        for _, repo_row in pilot.iterrows():
            print(f"  {repo_row['full_name']}: B1 up to {n_windows * B1_PRS_PER_WINDOW} PRs "
                  f"across {n_windows} months; B2 up to {2 * B2_PRS_PER_SIDE} PRs "
                  f"around {repo_row['intervention_date']}", flush=True)
        return

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Stable filenames across a resumed run: reuse the existing files for
    # this exact scope (tag + total units) if present, so a rerun after a
    # crash appends to what's already there instead of starting a fresh,
    # empty file under today's date. Only mint a new dated stem for a
    # genuinely new scope (different --target-total/--tracks/--repo).
    tag = args.tag
    existing = sorted(OUT_DIR.glob(f"*-{tag}-{total}.csv"), key=lambda p: p.stat().st_mtime)
    if existing:
        stem = existing[-1].stem
        print(f"continuing existing run: {stem}", flush=True)
    else:
        today = date.today()
        stem = f"{today.month:02d}-{today.day:02d}-{tag}-{total}"
    out_path = OUT_DIR / f"{stem}.csv"
    ledger_path = OUT_DIR / f"{stem}-queries.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"

    done_units = _load_done_units(ledger_path)
    if done_units:
        print(f"resuming: {len(done_units)}/{total} query unit(s) already done, skipping those", flush=True)

    session = get_session()
    started_at = time.time()
    ok_count, fail_count = len(done_units), 0
    n_prs_total = len(pd.read_csv(out_path)) if out_path.exists() else 0

    for i, unit in enumerate(units, start=1):
        repo_row = unit["repo_row"]
        label = f"{repo_row['full_name']} {unit['track']} {unit['unit']}"

        if _unit_key(unit) in done_units:
            continue

        try:
            rows, found_total, undersampled = fetch_unit(session, unit)
            for row in rows:
                _append_row(out_path, row)
            n_prs_total += len(rows)
            _append_row(ledger_path, {
                "repo_id": repo_row["repo_id"], "full_name": repo_row["full_name"],
                "track": unit["track"], "unit": unit["unit"],
                "n_prs_found": len(rows), "total_count": found_total,
                "is_undersampled": undersampled, "status": "ok", "error": "",
            })
            ok_count += 1
            elapsed = time.time() - started_at
            rate = (ok_count + fail_count - len(done_units)) / elapsed if elapsed > 0 else 0
            eta = (total - ok_count - fail_count) / rate if rate > 0 else None
            flag = " [undersampled]" if undersampled else ""
            print(f"  [ok] ({i}/{total}) {label} -> {len(rows)} PRs{flag} "
                  f"| {n_prs_total} PRs so far | {_format_eta(eta)}", flush=True)
        except Exception as e:
            fail_count += 1
            _append_row(ledger_path, {
                "repo_id": repo_row["repo_id"], "full_name": repo_row["full_name"],
                "track": unit["track"], "unit": unit["unit"],
                "n_prs_found": 0, "total_count": None,
                "is_undersampled": None, "status": "error", "error": str(e),
            })
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        _write_progress(progress_path, started_at, total, ok_count + fail_count, ok_count, fail_count, label)

    print(f"\ndone: {ok_count} ok, {fail_count} failed, {n_prs_total} total PR rows -> {out_path}", flush=True)


if __name__ == "__main__":
    main()
