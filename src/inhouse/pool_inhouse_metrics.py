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
import parallel_repo  # noqa: E402
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


def _repo_scoped_stem(out_dir, tag, full_name, n_rows):
    """Same continue-existing-or-mint-new stem convention main()'s
    single-run logic uses below, scoped to one repo - the exact shape a
    manual `--repo <name>` invocation already produces, reused here so
    --workers>1's per-repo fragments are indistinguishable on disk from
    someone having run several --repo-scoped invocations by hand."""
    scope = re.sub(r"[^a-zA-Z0-9]+", "", full_name)[:30]
    scope_suffix = f"{scope}-{n_rows}"
    existing = sorted(
        out_dir.glob(f"*-{tag}-{scope_suffix}.csv"),
        key=lambda p: p.stat().st_mtime,
    )
    if existing:
        return existing[-1].stem
    today = date.today()
    return f"{today.month:02d}-{today.day:02d}-{tag}-{scope_suffix}"


def _process_repo_group(full_name, rows, done_keys, dry_run, tag):
    """Worker body for one repo's row-set under --workers > 1 - see
    src/common/parallel_repo.py's docstring for the dispatch mechanism.
    Must stay module-level (picklable by reference) to run in a
    ProcessPoolExecutor worker. `rows` is a list of dicts (not a
    DataFrame slice - plain dicts pickle cleanly across the process
    boundary and process_row()/_snapshot_key() only ever do dict-style
    `row[...]` access, so this is a drop-in for the row objects the
    sequential path below iterates directly from the DataFrame)."""
    total = len(rows)
    stem = _repo_scoped_stem(OUT_DIR, tag, full_name, total)
    out_path = OUT_DIR / f"{stem}.csv"
    err_path = OUT_DIR / f"{stem}-errors.csv"
    progress_path = OUT_DIR / f"{stem}-progress.json"
    rr.write_runinfo(out_path, SCHEMA_VERSION)

    started_at = time.time()
    # Scoped to this repo's own rows, unlike the sequential path's
    # ok_count seed below (which starts at the GLOBAL done_keys count,
    # a pre-existing quirk kept as-is there for behavioral parity) -
    # summing len(done_keys) globally per worker would inflate every
    # repo's summary by every OTHER repo's done count too.
    ok_count = sum(
        1 for row in rows if rr.row_key_tuple(row, KEY_COLS) in done_keys
    )
    fail_count = 0
    for i, row in enumerate(rows, start=1):
        label = (
            f"{row['full_name']} {row['track']} {row['target_date'][:10]} "
            f"@{row['commit_sha'][:8]}"
        )
        if rr.row_key_tuple(row, KEY_COLS) in done_keys:
            continue

        try:
            result = process_row(row, dry_run)
            rr.append_row(out_path, result)
            ok_count += 1
            print(f"  [ok] {full_name} ({i}/{total}) {label}", flush=True)
        except Exception as e:
            fail_count += 1
            rr.append_row(err_path, {**_snapshot_key(row), "error": str(e)})
            print(f"  [FAIL] {full_name} ({i}/{total}) {label}: {e}", flush=True)

        rr.write_progress(
            progress_path, started_at, total,
            ok_count + fail_count, ok_count, fail_count, label,
        )

    return {
        "full_name": full_name, "ok": ok_count, "fail": fail_count,
        "out_path": str(out_path),
    }


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
    parser.add_argument(
        "--workers", type=int, default=1,
        help="repos to analyze in parallel (default 1 = sequential, "
             "byte-identical to pre-concurrency behavior including the "
             "single unscoped output file). >1 dispatches one process per "
             "repo via ProcessPoolExecutor and writes one fragment file "
             "PER REPO instead - a different on-disk shape than an "
             "unscoped sequential run, though consolidate_inhouse_metrics.py "
             "and _load_done_keys() already handle either shape "
             "transparently. git/dotnet subprocess calls have real "
             "startup cost - start low (4-6) on a single workstation, not "
             "os.cpu_count().",
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

    if args.workers > 1:
        done_keys = rr.load_done_keys(
            OUT_DIR, tag, KEY_COLS, schema_version=SCHEMA_VERSION
        )
        items_by_repo = {
            full_name: group.to_dict("records")
            for full_name, group in eligible.groupby("full_name", sort=False)
        }
        print(
            f"dispatching {len(items_by_repo)} repo(s) across "
            f"{args.workers} worker(s)", flush=True,
        )
        ok_total = fail_total = 0
        for full_name, summary in parallel_repo.run_by_repo(
            items_by_repo, _process_repo_group, workers=args.workers,
            worker_args=(done_keys, args.dry_run, tag),
        ):
            ok_total += summary["ok"]
            fail_total += summary["fail"]
            print(
                f"[repo done] {full_name}: {summary['ok']} ok, "
                f"{summary['fail']} failed -> {summary['out_path']}",
                flush=True,
            )
        print(
            f"\ndone: {ok_total} ok, {fail_total} failed across "
            f"{len(items_by_repo)} repo(s)", flush=True,
        )
        return

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
