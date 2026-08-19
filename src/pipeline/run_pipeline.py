"""
Thin sequencer for the pipeline - NOT a reimplementation of any stage.
Every stage below is still the existing script, owning its own
resumability (src/common/resumable_run.py), argparse flags, and output
conventions; this orchestrator's only job is to run them in dependency
order via subprocess, stop and report clearly on the first failure
instead of continuing silently, and write one rolled-up
results/pipeline-run-<timestamp>.json log of what ran.

Before this existed, the stage sequence was documented only narratively
in Writing/ProjectStatus.md/ProjectUpdate.md and run by hand, one script
at a time, in the right order from memory. This replaces that with:

    python -m src.pipeline.run_pipeline run
    python -m src.pipeline.run_pipeline run --stages metrics,smells --dry-run --limit 3
    python -m src.pipeline.run_pipeline run --target-total 100
    python -m src.pipeline.run_pipeline status

Stage order (the dependency chain the pipeline has always had, just
undocumented as runnable code before now):

  select -> snapshot-manifest -> materialize
  -> metrics / smells / entity-history
  -> consolidate-metrics / consolidate-smells / consolidate-entity-history
  -> regression
  -> viz-track-a / viz-churn
  -> validate-metrics / validate-smells

consolidate-entity-history matters more than its metrics/smells
counterparts might suggest: viz-churn has no auto-discovery of its own
(see _entity_history_extra_args below) and under --workers>1,
pool_entity_history.py writes one fragment file per repo, not one
shared file - skipping this stage silently starves viz-churn of most of
the corpus (or points it at a single repo's fragment) rather than
failing loudly. regression also always passes --full here (see its own
stage entry below) - without it, segmented_regression.py's __main__
only re-validates the pilot reproduction and fits nothing new against
real data, which looks like a successful run but isn't one.

`legacy-dpy-designite` (src/phase0/long_analysis.py, the licensed
DPy/Designite driver - ~29 hours for a single large snapshot under its
LOC-cap chunking) is deliberately NOT in the default stage list. It's
gated by its own --force/PILOT_SIZE_CEILING guard for pilot recalibration
only, and must be named explicitly via --stages to run at all - see the
pipeline scaling plan's "explicitly not doing" section for why this tool
is kept, not retired, but must never run by accident at 100/1000-repo
scale.
"""

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "results" / "analysis"
RUN_LOG_DIR = ROOT / "results"


def _latest_file(glob_pattern, exclude_substrings=()):
    files = [
        p for p in OUT_DIR.glob(glob_pattern)
        if not any(s in p.name for s in exclude_substrings)
    ]
    if not files:
        return None
    return sorted(files, key=lambda p: p.stat().st_mtime)[-1]


def _entity_history_extra_args(args):
    """generate_churn_figures.py requires --entity-history <path> (no
    auto-discovery of its own, unlike every other stage) - resolve it to
    the latest real pooled entity-history output.

    Prefers a *-entity-history-pooled.csv file (consolidate-entity-
    history's output) over the raw glob - a real bug found and fixed
    2026-08-19: under --workers>1, pool_entity_history.py writes one
    fragment file PER REPO, so "latest-mtime *-entity-history-*.csv"
    almost always picked a single repo's fragment instead of the pooled
    table (whichever repo's worker happened to finish last), not
    "the pooled entity-history output" the old docstring here claimed.
    Falls back to the broad glob for a --workers=1 sequential run, which
    still produces one shared unscoped file with no separate pooling
    step needed."""
    pooled = _latest_file("*-entity-history-pooled.csv")
    if pooled is not None:
        return ["--entity-history", str(pooled)]
    path = _latest_file(
        "*-entity-history-*.csv",
        exclude_substrings=("-errors", "-repo-summary", "dryrun", "-pooled"),
    )
    if path is None:
        raise SystemExit(
            "viz-churn: no *-entity-history-*.csv found in "
            f"{OUT_DIR} - run the entity-history stage first (and "
            "consolidate-entity-history if it was run with --workers>1)"
        )
    return ["--entity-history", str(path)]


# Ordered dependency chain. `supports` lists which of the orchestrator's
# shared flags (--dry-run/--limit/--repo/--target-total/--stale-check/
# --workers) this stage's own argparse actually accepts - passing an
# unsupported flag to a stage is a silent no-op waiting to happen, so we
# only forward what each script has really defined.
STAGES = [
    {
        "name": "select",
        "script": "src/phase0/repo_pr_selection.py",
        "supports": {"target_total"},
    },
    {
        "name": "snapshot-manifest",
        "script": "src/phase0/repo_snapshot_pipeline.py",
        "supports": {"target_total"},
    },
    {
        "name": "materialize",
        "script": "src/phase0/materialize_snapshots.py",
        "supports": {"repo", "workers"},
    },
    {
        "name": "metrics",
        "script": "src/inhouse/pool_inhouse_metrics.py",
        "supports": {"dry_run", "limit", "repo", "stale_check", "workers"},
    },
    {
        "name": "smells",
        "script": "src/inhouse/pool_inhouse_smells.py",
        "supports": {"dry_run", "limit", "repo", "stale_check", "workers"},
    },
    {
        "name": "entity-history",
        "script": "src/inhouse/pool_entity_history.py",
        "supports": {"dry_run", "limit", "repo", "stale_check", "workers"},
    },
    {
        "name": "consolidate-metrics",
        "script": "src/inhouse/consolidate_inhouse_metrics.py",
        "supports": set(),
    },
    {
        "name": "consolidate-smells",
        "script": "src/inhouse/consolidate_inhouse_smells.py",
        "supports": set(),
    },
    {
        "name": "consolidate-entity-history",
        "script": "src/inhouse/consolidate_entity_history.py",
        "supports": set(),
    },
    {
        "name": "regression",
        "script": "src/analysis/segmented_regression.py",
        "supports": set(),
        # segmented_regression.py's __main__ always runs the pilot
        # reproduction check, but only fits the real corpus if --full is
        # passed - a real bug found 2026-08-19: without this, the
        # orchestrator's "regression" stage silently did NOT fit anything
        # against real data, just re-validated the pilot reproduction
        # (which always passes since the pilot data never changes) and
        # exited looking successful.
        "extra_args": lambda args: ["--full"],
    },
    {
        "name": "viz-track-a",
        "script": "src/viz/generate_track_a_figures.py",
        "supports": set(),
    },
    {
        "name": "viz-churn",
        "script": "src/viz/generate_churn_figures.py",
        "supports": set(),
        "extra_args": _entity_history_extra_args,
    },
    {
        "name": "validate-metrics",
        "script": "src/inhouse/validate_against_pilot.py",
        "supports": set(),
    },
    {
        "name": "validate-smells",
        "script": "src/inhouse/validate_smells_against_pilot.py",
        "supports": set(),
    },
]

# Runnable only by naming it explicitly in --stages - never part of the
# default sequence. See module docstring.
GATED_STAGES = [
    {
        "name": "legacy-dpy-designite",
        "script": "src/phase0/long_analysis.py",
        "supports": {"dry_run", "limit", "repo"},
    },
]

STAGES_BY_NAME = {s["name"]: s for s in STAGES + GATED_STAGES}
DEFAULT_STAGE_ORDER = [s["name"] for s in STAGES]


def build_command(spec, args):
    cmd = [sys.executable, str(ROOT / spec["script"])]
    supports = spec["supports"]
    if args.dry_run and "dry_run" in supports:
        cmd.append("--dry-run")
    if args.limit is not None and "limit" in supports:
        cmd += ["--limit", str(args.limit)]
    if args.repo and "repo" in supports:
        cmd += ["--repo", args.repo]
    if args.target_total is not None and "target_total" in supports:
        cmd += ["--target-total", str(args.target_total)]
    if args.stale_check and "stale_check" in supports:
        cmd.append("--stale-check")
    if args.workers is not None and "workers" in supports:
        cmd += ["--workers", str(args.workers)]
    if "extra_args" in spec:
        cmd += spec["extra_args"](args)
    return cmd


def run_stage(spec, args):
    cmd = build_command(spec, args)
    print(f"\n=== [{spec['name']}] {' '.join(cmd)} ===", flush=True)
    t0 = time.time()
    result = subprocess.run(cmd, cwd=ROOT)
    elapsed = time.time() - t0
    return {
        "name": spec["name"],
        "cmd": cmd,
        "returncode": result.returncode,
        "elapsed_seconds": round(elapsed, 1),
    }


def cmd_run(args):
    if args.stages:
        requested = [s.strip() for s in args.stages.split(",") if s.strip()]
        unknown = [s for s in requested if s not in STAGES_BY_NAME]
        if unknown:
            raise SystemExit(
                f"unknown stage(s): {unknown} - choices are "
                f"{list(STAGES_BY_NAME)}"
            )
        order = requested
    else:
        order = DEFAULT_STAGE_ORDER

    print(f"pipeline run: {len(order)} stage(s): {order}", flush=True)

    started_at = datetime.now(timezone.utc).isoformat()
    stage_results = []
    for name in order:
        spec = STAGES_BY_NAME[name]
        result = run_stage(spec, args)
        stage_results.append(result)
        if result["returncode"] != 0:
            print(
                f"\n[{name}] failed (exit {result['returncode']}) - "
                "stopping pipeline, later stages did not run.",
                flush=True,
            )
            break
        print(
            f"[{name}] ok ({result['elapsed_seconds']}s)",
            flush=True,
        )

    _write_run_log(started_at, stage_results)

    if stage_results and stage_results[-1]["returncode"] != 0:
        raise SystemExit(1)


def _write_run_log(started_at, stage_results):
    RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = RUN_LOG_DIR / f"pipeline-run-{timestamp}.json"
    total_elapsed = sum(r["elapsed_seconds"] for r in stage_results)
    log_path.write_text(json.dumps({
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "total_elapsed_seconds": round(total_elapsed, 1),
        "stages": stage_results,
    }, indent=2))
    print(f"\nrun log: {log_path}", flush=True)


def cmd_status(args):
    logs = sorted(RUN_LOG_DIR.glob("pipeline-run-*.json"))
    if not logs:
        print("no pipeline runs logged yet - run `... run` first.")
        return
    latest = logs[-1]
    data = json.loads(latest.read_text())
    print(f"latest run log: {latest}")
    print(f"started: {data['started_at']}")
    print(f"finished: {data['finished_at']}")
    print(f"total elapsed: {data['total_elapsed_seconds']}s\n")
    for stage in data["stages"]:
        status = "ok" if stage["returncode"] == 0 else f"FAILED ({stage['returncode']})"
        print(f"  {stage['name']:<20} {status:<14} {stage['elapsed_seconds']}s")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run_parser = sub.add_parser("run", help="run one or more pipeline stages")
    run_parser.add_argument(
        "--stages", type=str, default=None,
        help="comma-separated stage names to run, in the order given "
             f"(default: the full sequence, {DEFAULT_STAGE_ORDER}). "
             f"Gated stages ({[s['name'] for s in GATED_STAGES]}) must be "
             "named explicitly - never part of the default.",
    )
    run_parser.add_argument("--dry-run", action="store_true")
    run_parser.add_argument("--limit", type=int, default=None)
    run_parser.add_argument("--repo", type=str, default=None)
    run_parser.add_argument(
        "--target-total", type=int, default=None,
        help="corpus size target, forwarded as --target-total to the "
             "select/snapshot-manifest stages (both accept the deprecated "
             "--pilot-size name too, but the orchestrator always passes "
             "the current one)",
    )
    run_parser.add_argument("--stale-check", action="store_true")
    run_parser.add_argument(
        "--workers", type=int, default=None,
        help="repos to process in parallel, forwarded to whichever "
             "stages support it (materialize/metrics/smells/entity-"
             "history) - see each stage's own --help for what changes "
             "on-disk under >1. Omit for sequential (each stage's "
             "default).",
    )
    run_parser.set_defaults(func=cmd_run)

    status_parser = sub.add_parser("status", help="report the latest pipeline run")
    status_parser.set_defaults(func=cmd_status)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
