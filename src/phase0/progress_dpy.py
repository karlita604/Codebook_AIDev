"""
Progress report for the Phase 1d long_analysis.py background run(s).

Prints:
- Which long_analysis.py processes are currently running (PID, --repo scope,
  how long since they last logged), discovered live via the OS process list
  rather than trusting a possibly-stale PID file.
- Real progress: unique successful rows across every
  results/analysis/*-smell-metrics-*.csv (deduplicated - several files can
  legitimately contain the same row, e.g. one written before a rescoping),
  broken down by repo, against the manifest's total eligible row count.
- Error summary across every *-errors.csv, split into "expected" (known,
  permanent or deliberately-deferred causes - see EXPECTED_ERROR_PATTERNS)
  vs "unexpected" (anything else, surfaced in full since it may need
  attention).

Usage: python progress_dpy.py
(intended to be invoked via the `progress_dpy` shell command - see
../../README or ask Claude - not typically run with arguments)
"""

import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
ANALYSIS_DIR = ROOT / "results" / "analysis"
MANIFEST_DIR = ROOT / "results" / "snapshots"
LOG_DIR = ROOT / "logs" / "phase0"

KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

# error message substrings that are known, already-understood, non-blocking
# causes - anything NOT matching one of these gets called out separately as
# possibly-new/unexpected, since a growing pile of those is worth noticing.
EXPECTED_ERROR_PATTERNS = [
    "DESIGNITE_EXECUTABLE not set",
    "not materialized at",
    # 2026-07-28 Smart App Control incident (see ProjectUpdate.md) - these
    # are draining on their own as each worker retries and succeeds (errors
    # are never in done_keys, so a resolved row just gets reprocessed). If
    # this count ever climbs instead of shrinking across repeated checks,
    # that means SAC (or something like it) blocked DPy.exe again - re-run
    # `DPy.exe version` directly to check, don't assume it's still this same
    # already-resolved incident.
    "WinError 4551",
]


def running_workers():
    """Live process list, not the PID file (which can go stale after a
    crash/restart) - queries Win32_Process directly for anything running
    long_analysis.py and pulls its --repo scope out of the command line."""
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" "
             "| Select-Object ProcessId,CommandLine | ConvertTo-Json"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        print(f"  (couldn't query running processes: {e})")
        return []

    import json
    try:
        procs = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(procs, dict):
        procs = [procs]

    workers = []
    for p in procs:
        cmdline = p.get("CommandLine") or ""
        if "long_analysis.py" not in cmdline:
            continue
        m = re.search(r"--repo\s+(\S+)", cmdline)
        scope = m.group(1) if m else "(unscoped - full manifest)"
        workers.append({"pid": p["ProcessId"], "scope": scope})
    return workers


def eligible_total():
    manifests = sorted(MANIFEST_DIR.glob("*-repo-snapshot-manifest-*.csv"))
    if not manifests:
        return None
    df = pd.read_csv(manifests[-1])
    return int((~df["no_prior_commit"] & df["commit_sha"].notna()).sum())


def real_progress():
    files = [
        f for f in ANALYSIS_DIR.glob("*-smell-metrics-*.csv")
        if not f.name.endswith("-errors.csv")
    ]
    if not files:
        return None, files
    frames = [pd.read_csv(f) for f in files]
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=KEY_COLS)
    return combined, files


def error_summary():
    err_files = list(ANALYSIS_DIR.glob("*-smell-metrics-*-errors.csv"))
    if not err_files:
        return None, None, err_files
    frames = [pd.read_csv(f) for f in err_files]
    combined = pd.concat(frames, ignore_index=True).drop_duplicates(subset=KEY_COLS)

    def _is_expected(msg):
        return any(p in str(msg) for p in EXPECTED_ERROR_PATTERNS)

    expected = combined[combined["error"].apply(_is_expected)]
    unexpected = combined[~combined["error"].apply(_is_expected)]
    return expected, unexpected, err_files


def main():
    print("=" * 60)
    print("Phase 1d (long_analysis.py) progress report")
    print("=" * 60)

    workers = running_workers()
    print(f"\nRunning workers: {len(workers)}")
    for w in workers:
        print(f"  PID {w['pid']:<7} --repo {w['scope']}")
    if not workers:
        print("  (none currently running)")

    total = eligible_total()
    combined, files = real_progress()
    print(f"\nReal progress (deduplicated across {len(files)} output file(s)):")
    if combined is None or combined.empty:
        print("  no successful rows recorded yet")
    else:
        done = len(combined)
        pct = f" ({done / total:.1%})" if total else ""
        print(f"  {done}{f'/{total}' if total else ''} rows{pct}")
        print("  by repo:")
        for repo, count in combined["full_name"].value_counts().items():
            print(f"    {repo}: {count}")

    expected, unexpected, err_files = error_summary()
    print(f"\nErrors (deduplicated across {len(err_files)} file(s)):")
    if expected is None:
        print("  none")
    else:
        print(f"  {len(expected)} expected (Designite not configured / "
              f"permanently unmaterialized commits)")
        if len(unexpected):
            print(f"  {len(unexpected)} UNEXPECTED - may need attention:")
            for _, row in unexpected.head(10).iterrows():
                print(f"    {row['full_name']} {row['track']} "
                      f"{str(row['target_date'])[:10]}: {row['error'][:100]}")
            if len(unexpected) > 10:
                print(f"    ... and {len(unexpected) - 10} more")
        else:
            print("  0 unexpected")

    pid_file = LOG_DIR / "long_analysis.pid"
    if pid_file.exists():
        print(f"\nPID file: {pid_file} -> {pid_file.read_text().strip()}")


if __name__ == "__main__":
    sys.exit(main())
