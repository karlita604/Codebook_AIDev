"""
C# entity-lineage extraction (Tool-CS's RQ3 counterpart to
py_entity_history.py): for one repo, walks every currently-tracked `.cs`
file's `git log --follow` history (reusing py_entity_history.py's
language-agnostic git plumbing directly - `follow_history`, `_run_git`,
`_safe_dirname`, `REPO_CACHE_DIR` are not Python-specific), extracts each
touching commit's class/method inventory via the extended Roslyn tool's
`--batch` stdin mode (src/inhouse/roslyn_tool/EntityHistory.cs), and feeds
the sequence through entity_matching.py exactly the way the Python side
does.

Batched per file, not per commit: every blob in one file's touching-commit
history is sent to the Roslyn tool in ONE subprocess call
(`roslyn_tool.exe --batch`), not one call per commit - checked empirically
(see the build log) that .NET process-startup cost makes per-commit
invocation impractical across a file with dozens of commits. `git show` is
still one subprocess call per commit (that part is unavoidable - it's how
git exposes historical blob content) - only the Roslyn side is batched.
"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import csharp_metrics  # noqa: E402
from entity_matching import EntitySnapshot, sample_files, tokenize  # noqa: E402
from py_entity_history import (  # noqa: E402
    DEFAULT_SEED, REPO_CACHE_DIR, _run_git, _safe_dirname, follow_history,
)


def list_current_cs_files(repo_dir):
    """Same convention as py_entity_history.list_current_py_files, filtered
    to *.cs instead - kept as a separate function rather than
    generalizing list_current_py_files's name, since language-specific
    callers (pool_entity_history.py, Stage 5) read more clearly calling the
    language-named function directly."""
    out = _run_git(repo_dir, ["ls-tree", "-r", "--name-only", "HEAD"])
    return sorted(p for p in out.splitlines() if p.endswith(".cs"))


def _run_roslyn_batch(blobs, timeout=300):
    """blobs: list of {"relpath": ..., "text": ...}. Returns the tool's
    parsed JSON array, one entry per input blob, same order."""
    if not blobs:
        return []
    csharp_metrics.ensure_built()
    payload = json.dumps(blobs)
    result = subprocess.run(
        ["dotnet", str(csharp_metrics.TOOL_DLL), "--batch"],
        input=payload, capture_output=True, text=True, timeout=timeout,
    )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"roslyn_tool --batch produced non-JSON output "
            f"(exit {result.returncode}): "
            f"stdout={result.stdout[:2000]!r} stderr={result.stderr[:2000]!r}"
        ) from e


def _to_snapshot(record):
    return EntitySnapshot(
        qualified_name=record["qualified_name"],
        kind=record["kind"],
        name=record["name"],
        param_count=record["param_count"],
        loc=record["loc"],
        tokens=tokenize(record["source_text"]),
    )


def collect_file_sequences(repo_dir, path):
    """C# counterpart to py_entity_history.collect_file_sequences: the
    expensive, threshold-independent half of building one file's lineages.
    Returns (class_seq, callable_seq), each a chronological list of
    (commit_sha, commit_date, {qualified_name: EntitySnapshot}) - same
    shape entity_matching.match_file_history expects, language-agnostic."""
    history = follow_history(repo_dir, path)
    if not history:
        return [], []

    blobs, meta = [], []
    for sha, date, path_at_commit in history:
        try:
            text = _run_git(repo_dir, ["show", f"{sha}:{path_at_commit}"])
        except RuntimeError:
            continue
        blobs.append({"relpath": path_at_commit, "text": text})
        meta.append((sha, date))

    results = _run_roslyn_batch(blobs)
    if len(results) != len(meta):
        raise RuntimeError(
            f"roslyn_tool --batch returned {len(results)} result(s) for "
            f"{len(meta)} input blob(s) - can't align by position"
        )

    class_seq, callable_seq = [], []
    for (sha, date), result in zip(meta, results):
        if result.get("status") != "ok":
            # A per-blob parse failure (e.g. a real syntax error in an old
            # commit) - skip this commit's contribution, matching
            # py_metrics.py's _parse_snapshot convention of counting/
            # skipping rather than aborting the whole file's walk.
            continue
        class_inv = {
            c["qualified_name"]: _to_snapshot(c) for c in result["classes"]
        }
        callable_inv = {
            c["qualified_name"]: _to_snapshot(c) for c in result["callables"]
        }
        class_seq.append((sha, date, class_inv))
        callable_seq.append((sha, date, callable_inv))
    return class_seq, callable_seq


def build_repo_lineages_cs(full_name, limit_files=None, threshold=None,
                            intervention_date=None, seed=DEFAULT_SEED):
    """C# counterpart to py_entity_history.build_repo_lineages - same
    output row shape (including the optional intervention_date columns) and
    same seeded-random file sampling (entity_matching.sample_files(), not
    sorted-order truncation - see that function's docstring for why), so
    pool_entity_history.py (Stage 5) can call either one interchangeably by
    language."""
    from entity_matching import match_file_history, _parse_date

    repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
    if not repo_dir.exists():
        raise FileNotFoundError(f"no repo_cache clone at {repo_dir}")

    as_of = _parse_date(_run_git(repo_dir, ["log", "-1", "--format=%aI"]).strip())

    files = list_current_cs_files(repo_dir)
    if limit_files:
        files = sample_files(files, limit_files, f"{seed}:{full_name}")

    kwargs = {} if threshold is None else {"threshold": threshold}
    rows = []
    for path in files:
        try:
            class_seq, callable_seq = collect_file_sequences(repo_dir, path)
        except (RuntimeError, subprocess.TimeoutExpired) as e:
            rows.append({"relpath": path, "status": "error", "error": str(e)})
            continue
        lineages = (
            match_file_history(class_seq, **kwargs)
            + match_file_history(callable_seq, **kwargs)
        )
        for lineage in lineages:
            row = {
                "relpath": path,
                "lineage_id": lineage.lineage_id,
                "kind": lineage.kind,
                "status": "ok",
                "first_qualified_name": lineage.first_touch.qualified_name,
                "last_qualified_name": lineage.last_touch.qualified_name,
                "first_commit": lineage.first_touch.commit_sha,
                "first_date": lineage.first_touch.commit_date,
                "last_commit": lineage.last_touch.commit_sha,
                "last_date": lineage.last_touch.commit_date,
                "modification_count": lineage.modification_count,
                "age_days": lineage.age_days(as_of),
                "relative_churn": lineage.relative_churn,
                "change_entropy": lineage.change_entropy,
                "review_count": lineage.review_count,
                "ended": lineage.ended,
                "had_rename_or_move": any(
                    t.change_type in ("renamed", "moved")
                    for t in lineage.touches
                ),
            }
            if intervention_date is not None:
                pre_n, post_n, pre_days, post_days = lineage.pre_post_touch_counts(
                    intervention_date
                )
                row["pre_touch_count"] = pre_n
                row["post_touch_count"] = post_n
                row["pre_window_days"] = round(pre_days, 2)
                row["post_window_days"] = round(post_days, 2)
                row["pre_churn_rate"] = pre_n / pre_days if pre_days > 0 else None
                row["post_churn_rate"] = post_n / post_days if post_days > 0 else None
            rows.append(row)
    return rows


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="full_name, e.g. wieslawsoltes/Dock")
    parser.add_argument("--limit-files", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                         help="seed for the random file sample when --limit-files caps the walk")
    args = parser.parse_args()

    rows = build_repo_lineages_cs(
        args.repo, limit_files=args.limit_files, threshold=args.threshold,
        seed=args.seed,
    )
    ok = [r for r in rows if r["status"] == "ok"]
    errors = [r for r in rows if r["status"] == "error"]
    print(f"{len(ok)} lineage(s) across {len(set(r['relpath'] for r in ok))} file(s), "
          f"{len(errors)} file error(s)")
    if ok:
        by_mod = sorted(ok, key=lambda r: r["modification_count"], reverse=True)
        print("\nTop 10 by modification_count:")
        for r in by_mod[:10]:
            print(
                f"  [{r['kind']:9s}] {r['modification_count']:3d} touches  "
                f"age={r['age_days']:4d}d  {r['last_qualified_name']}  ({r['relpath']})"
                + ("  <- renamed/moved" if r["had_rename_or_move"] else "")
            )
        renamed = [r for r in ok if r["had_rename_or_move"]]
        print(f"\n{len(renamed)}/{len(ok)} lineages include a detected rename/move")

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {len(rows)} row(s) to {args.out}")


if __name__ == "__main__":
    main()
