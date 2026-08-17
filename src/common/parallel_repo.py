"""
Generic repo-level parallel dispatch, shared by pool_inhouse_metrics.py,
pool_inhouse_smells.py, and pool_entity_history.py rather than each
reimplementing it (the exact triplication resumable_run.py already fixed
once for the resumability logic - see that module's docstring).

Each repo's analysis is independent of every other repo's (analyzing
crewAI never needs anything from analyzing mlflow), so this is
embarrassingly parallel: group the work by repo, hand each group to its
own worker, done. `run_by_repo()` is deliberately dumb about what a
"group" actually is - each pool script defines its own worker function
that knows how to process one repo's rows/repo-object and write its own
output; this module only knows how to fan work out across workers and
collect results back.

workers<=1 (the default) runs every group inline, sequentially, in
submission order - byte-identical to the pre-concurrency code path,
including producing the same single unscoped output file a --repo-less
invocation always has. workers>1 dispatches one `ProcessPoolExecutor`
worker per repo group instead (not threads - the per-row analyzers are
CPU-bound AST/Roslyn work, so threads wouldn't actually run concurrently
under the GIL) and each worker must therefore write its own repo-scoped
fragment file rather than share one - see each pool script's
`_process_repo_group`-style worker for how that reuses the exact file-
naming convention a manual `--repo <name>` invocation already produces,
so parallel and sequential runs are structurally indistinguishable on
disk, just batched differently.

`worker_fn` must be a module-level function (picklable by reference) when
workers>1 - a closure or lambda won't survive being sent to a child
process. Default workers count is left to each caller, not fixed here -
git/dotnet subprocess calls have real per-call startup cost and this
targets a single researcher's workstation, not a dedicated batch node, so
"more workers is always better" doesn't hold much past single digits.
"""

import concurrent.futures


def run_by_repo(items_by_repo, worker_fn, workers=1, worker_args=()):
    """items_by_repo: {repo_key: items} - items is whatever worker_fn(
    repo_key, items, *worker_args) expects (a list of row dicts for the
    metrics/smells scripts, a single repo row for entity-history).
    Yields (repo_key, worker_fn's return value) pairs - submission order
    if workers<=1, completion order (not necessarily submission order) if
    workers>1, since faster repos finish out of order under real
    parallelism."""
    if workers <= 1:
        for repo_key, items in items_by_repo.items():
            yield repo_key, worker_fn(repo_key, items, *worker_args)
        return

    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {
            ex.submit(worker_fn, repo_key, items, *worker_args): repo_key
            for repo_key, items in items_by_repo.items()
        }
        for fut in concurrent.futures.as_completed(futures):
            yield futures[fut], fut.result()
