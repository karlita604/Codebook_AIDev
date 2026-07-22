"""
Phase 1c: Track A1/A2 repo-snapshot pipeline.

For each pilot repo, clone once (partial clone: full commit history, blobs
fetched lazily on checkout later), then resolve two independent snapshot
grids against that clone:

- A1: fixed calendar grid, monthly, 2022-01-01 - 2026-03-31 (51 points).
- A2: grid centered on the repo's own intervention_date - weekly for
  +/-3 months, monthly out to +/-12 months (45 points).

For each grid point we resolve the nearest commit at or before that date
(`git log --until`) and record how stale that commit is (see the "Staleness"
section of Writing/Longitudinal.md). This produces a *manifest* -  which
commit represents which (repo, track, date) - not the DPy/Designite output
itself. Running those tools per snapshot is Phase 1d and needs the tools
installed, which they are not in this environment yet.

No GitHub API, no token: only needs each repo's git clone URL (from
`full_name`) and local disk.
"""

import argparse
import subprocess
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from repo_pr_selection import suggest_pilot  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CLONE_CACHE_DIR = ROOT / "data" / "repo_cache"
OUT_DIR = ROOT / "results" / "snapshots"
REPO_SUMMARY_GLOB = ROOT / "results" / "repos"

WINDOW_START = "2022-01-01"
WINDOW_END = "2026-03-31"
STALENESS_THRESHOLD_DAYS = 45
CLONE_TIMEOUT_SECONDS = 480


def _safe_dirname(full_name):
    return full_name.replace("/", "__")


def clone_repo(full_name, cache_dir=CLONE_CACHE_DIR):
    """Idempotent partial clone: full commit history, blobs fetched lazily
    on checkout. Returns the repo directory, or None if the clone failed."""
    dest = cache_dir / _safe_dirname(full_name)
    if (dest / ".git").exists():
        print(f"  [clone] {full_name}: already cloned at {dest}")
        return dest

    cache_dir.mkdir(parents=True, exist_ok=True)
    url = f"https://github.com/{full_name}.git"
    print(f"  [clone] {full_name}: cloning from {url} ...")
    try:
        subprocess.run(
            [
                "git", "-c", "core.longpaths=true", "clone",
                "--filter=blob:none", "--no-tags", url, str(dest),
            ],
            check=True, capture_output=True, text=True, timeout=CLONE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        print(f"  [clone] {full_name}: TIMED OUT after {CLONE_TIMEOUT_SECONDS}s")
        return None
    except subprocess.CalledProcessError as e:
        print(f"  [clone] {full_name}: FAILED - {e.stderr.strip()[:300]}")
        return None
    print(f"  [clone] {full_name}: done")
    return dest


def nearest_commit(repo_dir, until_ts):
    """Latest commit at or before until_ts (UTC), on the checked-out branch.
    Returns (sha, commit_date) or (None, None) if no such commit exists."""
    until_iso = until_ts.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    result = subprocess.run(
        ["git", "log", f"--until={until_iso}", "-1", "--format=%H\x1f%cI"],
        cwd=repo_dir, capture_output=True, text=True, check=True,
    )
    line = result.stdout.strip()
    if not line:
        return None, None
    sha, commit_date = line.split("\x1f")
    return sha, pd.Timestamp(commit_date)


def monthly_grid(start=WINDOW_START, end=WINDOW_END):
    """Track A1: fixed calendar grid, one point per month start."""
    return list(pd.date_range(start=start, end=end, freq="MS", tz="UTC"))


def intervention_grid(intervention_date):
    """Track A2: weekly +/-3mo, monthly out to +/-12mo, centered on the
    repo's own intervention date."""
    base = pd.Timestamp(intervention_date)
    if base.tzinfo is None:
        base = base.tz_localize("UTC")
    points = {base + pd.Timedelta(days=offset) for offset in range(-91, 92, 7)}
    for m in range(4, 13):
        points.add(base + pd.DateOffset(months=m))
        points.add(base - pd.DateOffset(months=m))
    return sorted(points)


def build_rows(repo_row, repo_dir, grid, track):
    rows = []
    for target_date in grid:
        sha, commit_date = nearest_commit(repo_dir, target_date)
        no_prior_commit = sha is None
        staleness_days = None if no_prior_commit else (target_date - commit_date).days
        is_stale = (not no_prior_commit) and staleness_days > STALENESS_THRESHOLD_DAYS
        rows.append({
            "repo_id": repo_row["repo_id"],
            "full_name": repo_row["full_name"],
            "language": repo_row["language"],
            "track": track,
            "target_date": target_date.isoformat(),
            "commit_sha": sha,
            "commit_date": commit_date.isoformat() if commit_date is not None else None,
            "staleness_days": staleness_days,
            "is_stale": is_stale,
            "no_prior_commit": no_prior_commit,
        })
    return rows


def get_pilot_repos(pilot_size=5):
    """Reads the repo-summary CSV already produced by repo_pr_selection.py
    (Phase 1a) rather than re-deriving the candidate list here, so this
    script doesn't break every time the phase0 candidate-list file gets
    moved/renamed/regenerated elsewhere."""
    summary_files = sorted(REPO_SUMMARY_GLOB.glob("*-repo-summary-*.csv"))
    if not summary_files:
        raise FileNotFoundError(
            f"No repo-summary CSV found in {REPO_SUMMARY_GLOB} - "
            "run repo_pr_selection.py first"
        )
    repo_summary = pd.read_csv(summary_files[-1])
    return suggest_pilot(repo_summary, n=pilot_size)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-size", type=int, default=5)
    args = parser.parse_args()

    pilot = get_pilot_repos(pilot_size=args.pilot_size)
    print(f"Pilot set: {len(pilot)} repos")

    all_rows = []
    for _, repo_row in pilot.iterrows():
        full_name = repo_row["full_name"]
        print(f"\n=== {full_name} (repo_id={repo_row['repo_id']}) ===")
        repo_dir = clone_repo(full_name)
        if repo_dir is None:
            print(f"  skipping {full_name}: clone unavailable")
            continue

        a1_grid = monthly_grid()
        a2_grid = intervention_grid(repo_row["intervention_date"])
        print(f"  A1 grid: {len(a1_grid)} points, A2 grid: {len(a2_grid)} points")

        rows = build_rows(repo_row, repo_dir, a1_grid, "A1")
        rows += build_rows(repo_row, repo_dir, a2_grid, "A2")
        all_rows.extend(rows)

        stale_ct = sum(1 for r in rows if r["is_stale"])
        missing_ct = sum(1 for r in rows if r["no_prior_commit"])
        print(f"  {len(rows)} snapshot rows ({stale_ct} stale, {missing_ct} no-prior-commit)")

    manifest = pd.DataFrame(all_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = date.today()
    out_path = OUT_DIR / f"{today.month:02d}-{today.day:02d}-repo-snapshot-manifest-{len(manifest)}.csv"
    manifest.to_csv(out_path, index=False)
    print(f"\n{len(manifest)} total snapshot rows -> {out_path}")


if __name__ == "__main__":
    main()
