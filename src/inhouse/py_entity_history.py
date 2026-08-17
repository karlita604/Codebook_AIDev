"""
Python entity-lineage extraction: for one repo (a `data/repo_cache/`
clone), walks every currently-tracked `.py` file's `git log --follow`
history, extracts a class/method/function inventory at each touching
commit via ast_common (in-process, no subprocess needed for the Python
side), and feeds consecutive inventories through entity_matching.py to
reconstruct each entity's lineage across renames, moves, and signature
changes.

Stage 1 scope (Writing/RQ3_CodeTracking.md / the RQ3 execution plan):
prototype against one repo (crewAI) only, hand-checked before extending to
the rest of the pilot or Phase 2. Metrics beyond raw touch history (age,
relative churn, change entropy - Stage 2) and the empirical matcher
validation (Stage 3) are deliberately not part of this file.

Known, deliberate limitations (not oversights):
- Only files present at the repo's current HEAD are walked - a file
  deleted earlier in history and never brought back isn't discovered. Files
  are `git log --follow`-ed individually, so cross-file moves (an
  extract-to-new-file refactor) are not tracked as continuous - both are
  the direct consequence of the "walk `git log --follow` per file, not a
  full-history snapshot grid" design decision, not new gaps introduced
  here.
- Merge commits are not specially handled - `git log --follow` on a single
  path already skips commits that didn't actually change that path's
  content, which in practice excludes most merge commits from this walk.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ast
import ast_common  # noqa: E402
from entity_matching import (  # noqa: E402
    EntitySnapshot, _parse_date, match_file_history, tokenize,
)

ROOT = Path(__file__).resolve().parents[2]
REPO_CACHE_DIR = ROOT / "data" / "repo_cache"

_COMMIT_MARK = "@@COMMIT@@"


def _safe_dirname(full_name):
    """Same convention as materialize_snapshots.py's _safe_dirname - kept
    duplicated rather than imported to avoid a cross-package (src/phase0 <->
    src/inhouse) import for one three-line function."""
    return full_name.replace("/", "__")


def _run_git(repo_dir, args, timeout=120):
    result = subprocess.run(
        ["git", "-C", str(repo_dir)] + args,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed in {repo_dir}: {result.stderr.strip()}"
        )
    return result.stdout


def list_current_py_files(repo_dir):
    """Every .py file present in the repo's current HEAD tree - the
    starting point for per-file history walks (see module docstring's
    "only files present at HEAD" limitation)."""
    out = _run_git(repo_dir, ["ls-tree", "-r", "--name-only", "HEAD"])
    return sorted(p for p in out.splitlines() if p.endswith(".py"))


def _head_commit_date(repo_dir):
    return _run_git(repo_dir, ["log", "-1", "--format=%aI"]).strip()


def follow_history(repo_dir, path):
    """Chronological (oldest-first) list of (commit_sha, commit_date_iso,
    path_at_that_commit) for one file, resolved across renames via
    `--follow`. Stops (excludes) a commit where the file was deleted - that
    commit's status is 'D', which has no "path at that commit" to extract
    content from, so it's not a valid inventory point; it just marks where
    this walk ends."""
    out = _run_git(repo_dir, [
        "log", "--follow", "--reverse", "--name-status",
        f"--format={_COMMIT_MARK}%x09%H%x09%aI", "--", path,
    ])

    commits = []
    current_path = path
    sha = date = None
    for line in out.splitlines():
        if line.startswith(_COMMIT_MARK):
            _, sha, date = line.split("\t")
            continue
        if not line.strip() or sha is None:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R"):
            # "R100\told\tnew" - historical commits (older than this rename)
            # were extracted under `old`; this commit and everything newer
            # use `new`.
            current_path = parts[2]
            commits.append((sha, date, current_path))
        elif status == "D":
            # File deleted here - no content to extract, walk ends. Any
            # earlier-collected commits stay valid.
            break
        else:
            commits.append((sha, date, current_path))
    return commits


def _entity_snapshot(entity, kind, file_lines):
    start, end = entity.lineno, entity.end_lineno
    source = "\n".join(file_lines[start - 1:end])
    param_count = getattr(entity, "param_count", None)
    return EntitySnapshot(
        qualified_name=entity.qualified_name, kind=kind, name=entity.name,
        param_count=param_count, loc=entity.loc, tokens=tokenize(source),
    )


def entities_at(repo_dir, commit_sha, path):
    """One commit's entity inventory for one file, split into the two
    granularity passes match_file_history operates on separately: "class"
    and "callable" (methods + module-level functions pooled, matching
    ast_common's own module-level function/method split - a method and a
    same-named top-level function are never in the same qualified_name
    namespace anyway, so pooling them into one matching pass is safe).
    Returns (class_inventory, callable_inventory), either {} if the blob
    fails to parse (real syntax errors turn up in old commits, same
    py_metrics.py already documents) - an empty inventory just means no
    entities matched at this commit, not a crash."""
    try:
        text = _run_git(repo_dir, ["show", f"{commit_sha}:{path}"])
        tree = ast.parse(text)
    except (RuntimeError, SyntaxError):
        return {}, {}

    file_lines = text.splitlines()
    module_qualname = ast_common.module_qualname(Path(path))
    classes = ast_common.extract_classes(tree, module_qualname)
    functions = ast_common.extract_functions(tree, module_qualname)

    class_inv = {
        c.qualified_name: _entity_snapshot(c, "class", file_lines)
        for c in classes
    }
    callable_inv = {
        f.qualified_name: _entity_snapshot(f, "callable", file_lines)
        for f in functions
    }
    for c in classes:
        for m in c.methods:
            callable_inv[m.qualified_name] = _entity_snapshot(
                m, "callable", file_lines
            )
    return class_inv, callable_inv


def collect_file_sequences(repo_dir, path):
    """The expensive, threshold-independent half of building a file's
    lineages: every git subprocess call and every AST parse. Split out from
    build_file_lineages so a caller that wants to try several similarity
    thresholds (validate_entity_matching.py's Stage 3 sweep) can pay this
    cost once per file and re-run the cheap in-memory matching step
    per threshold, instead of re-walking git history each time. Returns
    (class_seq, callable_seq), each a chronological list of
    (commit_sha, commit_date, {qualified_name: EntitySnapshot})."""
    history = follow_history(repo_dir, path)
    class_seq, callable_seq = [], []
    for sha, date, path_at_commit in history:
        class_inv, callable_inv = entities_at(repo_dir, sha, path_at_commit)
        class_seq.append((sha, date, class_inv))
        callable_seq.append((sha, date, callable_inv))
    return class_seq, callable_seq


def build_file_lineages(repo_dir, path, threshold=None):
    """All class-lineages and callable-lineages for one file's full
    (currently-live) history. Returns (class_lineages, callable_lineages)."""
    class_seq, callable_seq = collect_file_sequences(repo_dir, path)
    kwargs = {} if threshold is None else {"threshold": threshold}
    return (
        match_file_history(class_seq, **kwargs),
        match_file_history(callable_seq, **kwargs),
    )


def build_repo_lineages(full_name, limit_files=None, threshold=None, intervention_date=None):
    """All lineages across every current .py file in one repo. Returns a
    flat list of dicts (one per lineage) ready to serialize - each lineage
    tagged with the file it came from, so a lineage's identity in the
    output is (relpath_at_creation, lineage_id_within_that_file), not
    globally unique across the whole repo (two different files' lineage_id
    0 are unrelated) - fine for this stage's per-file matching design.

    `intervention_date` (a timezone-aware datetime, already parsed - not a
    string) is optional: when given, each row also gets
    pre_touch_count/post_touch_count/pre_churn_rate/post_churn_rate from
    EntityLineage.pre_post_touch_counts(). When omitted, those four columns
    are absent - existing callers that don't pass it see no schema change."""
    repo_dir = REPO_CACHE_DIR / _safe_dirname(full_name)
    if not repo_dir.exists():
        raise FileNotFoundError(f"no repo_cache clone at {repo_dir}")

    # Reference date for a still-live lineage's age_days - the repo's own
    # latest known commit, not wall-clock "now" (see EntityLineage.age_days'
    # docstring for why that distinction matters).
    as_of = _parse_date(_head_commit_date(repo_dir))

    files = list_current_py_files(repo_dir)
    if limit_files:
        files = files[:limit_files]

    rows = []
    for path in files:
        try:
            class_lineages, callable_lineages = build_file_lineages(
                repo_dir, path, threshold=threshold
            )
        except RuntimeError as e:
            rows.append({
                "relpath": path, "status": "error", "error": str(e),
            })
            continue
        for lineage in class_lineages + callable_lineages:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, help="full_name, e.g. crewAIInc/crewAI")
    parser.add_argument("--limit-files", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--out", type=Path, default=None, help="write full row JSON here")
    args = parser.parse_args()

    rows = build_repo_lineages(
        args.repo, limit_files=args.limit_files, threshold=args.threshold
    )

    ok = [r for r in rows if r["status"] == "ok"]
    errors = [r for r in rows if r["status"] == "error"]
    print(f"{len(ok)} lineage(s) across {len(set(r['relpath'] for r in ok))} file(s), "
          f"{len(errors)} file error(s)")
    if ok:
        by_mod = sorted(ok, key=lambda r: r["modification_count"], reverse=True)
        print("\nTop 10 by modification_count:")
        for r in by_mod[:10]:
            churn = f"{r['relative_churn']:.3f}" if r["relative_churn"] is not None else "-"
            entropy = f"{r['change_entropy']:.2f}" if r["change_entropy"] is not None else "-"
            print(
                f"  [{r['kind']:9s}] {r['modification_count']:3d} touches  "
                f"age={r['age_days']:4d}d  churn={churn:>6s}  entropy={entropy:>5s}  "
                f"{r['last_qualified_name']}  ({r['relpath']})"
                + ("  <- renamed/moved" if r["had_rename_or_move"] else "")
            )
        renamed = [r for r in ok if r["had_rename_or_move"]]
        print(f"\n{len(renamed)}/{len(ok)} lineages include a detected rename/move")

    if args.out:
        args.out.write_text(json.dumps(rows, indent=2))
        print(f"\nwrote {len(rows)} row(s) to {args.out}")


if __name__ == "__main__":
    main()
