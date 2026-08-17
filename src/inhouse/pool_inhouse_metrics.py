"""
In-house replacement for Phase 1d's DPy/Designite leg: run py_metrics.py
(Phase A, Python) or csharp_metrics.py (Phase B, C# via Roslyn) against
every materialized snapshot (Phase 1e, materialize_snapshots.py) and pool
the results into one table keyed the same way long_analysis.py's
DPy/Designite output already is - (repo_id, track, target_date,
commit_sha) - so this drops straight into
results/analysis/07-29-pooled-structural-metrics.csv's join without an
adapter step. See Writing/InHouseTooling.md's design-decisions section for
why this exists (no LOC cap - own code, not a licensed trial tool) and
Writing/ProjectStatus.md for why it matters now: Phase 2's ~16 new repos
already have materialized snapshots sitting in data/snapshots/ with no
structural metrics run against them yet (Phase 1d was deliberately deferred
for them - see ProjectUpdate.md's 2026-08-04 entry).

CLI shape, resumability, and progress/error-file conventions all mirror
long_analysis.py's main() deliberately - same pipeline, same tool, just a
from-scratch metrics engine instead of a subprocess call to a licensed
trial-cap tool (Roslyn is still a subprocess call - to our own compiled
console app, not a third-party one). The resumability/progress plumbing
itself now lives in src/common/resumable_run.py (2026-08-17 extraction -
this file, pool_inhouse_smells.py, and pool_entity_history.py had
independently reimplemented the same done-keys/progress/error-file
pattern) - see that module's docstring for the schema_version/staleness
behavior added at the same time.

Use --dry-run to smoke-test snapshot lookup/bookkeeping without running the
analyzer. Use --limit/--repo to test on a handful of rows first. Use
--stale-check to report done-key bookkeeping without running anything.
"""

import argparse
import re
import sys
import time
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csharp_metrics  # noqa: E402
import py_metrics  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "phase0"))
from materialize_snapshots import (  # noqa: E402
    SNAPSHOT_DIR, _is_materialized, _safe_dirname, latest_manifest,
)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
import exclusions  # noqa: E402
import resumable_run as rr  # noqa: E402

LANGUAGE_ANALYZER = {
    "Python": py_metrics.analyze_snapshot,
    "C#": csharp_metrics.analyze_snapshot,
}
LANGUAGE_GLOB = {"Python": "*.py", "C#": "*.cs"}

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"

KEY_COLS = ["repo_id", "track", "target_date", "commit_sha"]

# Bump when a fix changes what "done" should mean for existing rows (e.g.
# a metrics-engine bug fix) - see resumable_run.py's docstring. Rows
# written under a prior schema_version are excluded from the done-set and
# reprocessed rather than trusted as-is; rows from before this tracking
# existed (no .runinfo.json sidecar) are still trusted, unaffected by
# this constant.
SCHEMA_VERSION = 1


def _snapshot_key(row):
    return {
        "repo_id": row["repo_id"],
        "full_name": row["full_name"],
        "language": row["language"],
        "track": row["track"],
        "target_date": row["target_date"],
        "commit_sha": row["commit_sha"],
    }


def process_row(row, dry_run):
    snapshot_dir = (
        SNAPSHOT_DIR / _safe_dirname(row["full_name"]) / row["commit_sha"]
    )
    if not _is_materialized(snapshot_dir):
        raise FileNotFoundError(
            f"{row['full_name']}@{row['commit_sha'][:8]} not materialized at "
            f"{snapshot_dir} - run materialize_snapshots.py (Phase 1e) first"
        )

    language = row["language"]
    analyze = LANGUAGE_ANALYZER.get(language)
    if analyze is None:
        raise ValueError(
            f"no in-house analyzer mapped for language={language!r}"
        )

    if dry_run:
        glob = LANGUAGE_GLOB[language]
        n_files = sum(1 for p in snapshot_dir.rglob(glob) if p.is_file())
        return {
            **_snapshot_key(row), "n_source_files": n_files,
            "status": "dry_run",
        }

    metrics = analyze(snapshot_dir)
    return {**_snapshot_key(row), **metrics}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest", type=Path, default=None,
        help="snapshot manifest csv (default: latest in results/snapshots/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="look up each materialized snapshot and record bookkeeping "
             "only - skip the actual metrics analysis",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="only process the first N eligible rows (smoke testing)",
    )
    parser.add_argument(
        "--repo", type=str, default=None,
        help="only process rows whose full_name contains this substring",
    )
    parser.add_argument(
        "--exclude-repo", type=str, default=None,
        help="skip rows whose full_name contains this substring - for "
             "azure-sdk-for-python specifically (2026-08-13): _lcom's O(n^2) "
             "pairwise cohesion computation is the same complexity class "
             "that stalled py_smells.py's _tcc on this repo's 40k-line "
             "generated files (see Writing/PySmellDetection.md's batch-run "
             "log), same per-run scope decision, not a permanent "
             "tooling-blocker exclusion like EXCLUDED_REPOS.",
    )
    parser.add_argument(
        "--stale-check", action="store_true",
        help="report done-key bookkeeping (file count, oldest/newest, any "
             "stale schema_version exclusions) and exit without running "
             "anything - sanity-check before a real run.",
    )
    args = parser.parse_args()

    if args.stale_check:
        tag = "dryrun-inhouse" if args.dry_run else "inhouse-metrics"
        rr.stale_check_report(
            OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION
        )
        return

    manifest_path = args.manifest or latest_manifest()
    manifest = pd.read_csv(manifest_path)
    print(f"manifest: {manifest_path} ({len(manifest)} rows)", flush=True)

    # Deliberately NOT filtering out materialize_snapshots.py's
    # EXCLUDED_REPOS ({"dotnet/aspire"}) here - that exclusion is specific
    # to MSBuildWorkspace not being able to evaluate aspire's project graph
    # (Designite's blocker), which doesn't apply to us: Phase B never loads
    # a .sln/.csproj at all (syntax-only Roslyn - see
    # Writing/InHouseTooling.md's design-decisions section). Inheriting that
    # exclusion here would silently reproduce a limitation this tool exists
    # specifically to not have.
    eligible = manifest[
        manifest["commit_sha"].notna()
        & manifest["language"].isin(LANGUAGE_ANALYZER.keys())
    ].sort_values("full_name")
    if args.repo:
        eligible = eligible[eligible["full_name"].str.contains(args.repo)]
    # Auto-apply the registry's scope="per-run" exclusions (e.g.
    # azure-sdk-for-python's O(n^2) cohesion-computation stall, which
    # applies to this tool's own _lcom just as much as py_smells.py's
    # _tcc) - but NOT scope="permanent" ones: those (dotnet/aspire) are
    # Designite-project-graph-specific and deliberately don't apply here,
    # per the comment above.
    per_run_excluded = exclusions.load_exclusions(scope="per-run")
    if per_run_excluded:
        eligible = eligible[~eligible["full_name"].isin(per_run_excluded)]
    if args.exclude_repo:
        eligible = eligible[
            ~eligible["full_name"].str.contains(args.exclude_repo)
        ]
        print(
            f"  (--exclude-repo is a one-off filter for this invocation - "
            f"if {args.exclude_repo!r} should be excluded persistently, "
            "add it to results/repos/excluded_repos.csv via "
            "src/common/exclusions.py's record_exclusion())",
            flush=True,
        )
    if args.limit:
        eligible = eligible.head(args.limit)
    total = len(eligible)
    print(
        f"{total} eligible row(s) (have a resolved commit, "
        f"Python or C#)",
        flush=True,
    )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Not "-python" anymore - covers both languages now that Phase B (C#)
    # exists. "inhouse-metrics" is still a glob-prefix match against the
    # older Python-only "inhouse-metrics-python-*.csv" files from Phase A's
    # validation runs, so _load_done_keys() still sees those rows as done
    # and won't reprocess them under the new tag.
    tag = "dryrun-inhouse" if args.dry_run else "inhouse-metrics"

    scope = re.sub(r"[^a-zA-Z0-9]+", "", args.repo)[:30] if args.repo else None
    scope_suffix = f"{scope}-{total}" if scope else str(total)

    existing = sorted(
        OUT_DIR.glob(f"*-{tag}-{scope_suffix}.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if existing:
        stem = existing[-1].stem
        print(f"continuing existing run: {existing[-1]}", flush=True)
    else:
        today = date.today()
        stem = f"{today.month:02d}-{today.day:02d}-{tag}-{scope_suffix}"
    out_path = OUT_DIR / f"{stem}.csv"
    err_path = OUT_DIR / f"{stem}-errors.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"
    rr.write_runinfo(out_path, SCHEMA_VERSION)

    done_keys = rr.load_done_keys(
        OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION
    )
    if done_keys:
        print(
            f"resuming: {len(done_keys)} row(s) already done in {out_path}, "
            "skipping",
            flush=True,
        )

    started_at = time.time()
    ok_count, fail_count = len(done_keys), 0
    for i, (_, row) in enumerate(eligible.iterrows(), start=1):
        label = (
            f"{row['full_name']} {row['track']} {row['target_date'][:10]} "
            f"@{row['commit_sha'][:8]}"
        )
        if rr.row_key_tuple(row, KEY_COLS) in done_keys:
            continue

        try:
            result = process_row(row, args.dry_run)
            rr.append_row(out_path, result)
            ok_count += 1
            print(f"  [ok] ({i}/{total}) {label}", flush=True)
        except Exception as e:
            fail_count += 1
            rr.append_row(err_path, {**_snapshot_key(row), "error": str(e)})
            print(f"  [FAIL] ({i}/{total}) {label}: {e}", flush=True)

        rr.write_progress(
            progress_path, started_at, total,
            ok_count + fail_count, ok_count, fail_count, label,
        )

    print(
        f"\ndone: {ok_count} ok, {fail_count} failed -> {out_path}",
        flush=True,
    )


if __name__ == "__main__":
    main()
