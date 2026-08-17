"""
Single registry for repo exclusions.

Replaces three previously uncoordinated mechanisms that will only
multiply as the corpus grows to 100/1000 repos: materialize_snapshots.py's
hardcoded `EXCLUDED_REPOS` set (permanent, tooling-blocker exclusions like
dotnet/aspire), ad hoc `--exclude-repo` CLI flags passed per-invocation to
the pool_inhouse_*.py batch runners (per-run scope decisions like
azure-sdk-for-python's O(n^2) cohesion-computation stall), and nothing at
all recording *why* in one place.

results/repos/excluded_repos.csv columns:
- full_name: repo identifier, e.g. "dotnet/aspire"
- excluded_at: ISO8601 UTC timestamp the exclusion was recorded
- reason: free-text explanation - always fill this in, it's the entire
  point of the registry existing
- scope: "permanent" (tooling can never handle this repo, e.g. an org
  policy blocking API access, or a workspace-graph load failure) or
  "per-run" (a scale/performance workaround that a future fix - e.g. the
  cohesion-sampling cap planned for py_smells.py's O(n^2) _tcc - is
  expected to retire; kept in the registry so the reason isn't lost, not
  because it's meant to be permanent)

Does NOT cover consolidate_inhouse_metrics.py's hardcoded Dock
filename-regex drop rule - that's a row-level fix for already-stale data
from a fixed bug (the Dock repo_cache clone was frozen 3.5 years in the
past), not a repo-selection decision, and doesn't belong in the same
registry as a category matter, even though both are "exclusion" in a
loose sense.
"""

import csv
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = ROOT / "results" / "repos" / "excluded_repos.csv"

FIELDNAMES = ["full_name", "excluded_at", "reason", "scope"]


def load_exclusion_rows(path=REGISTRY_PATH):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_exclusions(scope=None, path=REGISTRY_PATH):
    """Set of excluded full_name repo identifiers. scope=None returns
    every registry row regardless of scope; pass "permanent" or "per-run"
    to filter to just one."""
    rows = load_exclusion_rows(path)
    if scope is not None:
        rows = [r for r in rows if r.get("scope") == scope]
    return {r["full_name"] for r in rows}


def record_exclusion(full_name, reason, scope="permanent", path=REGISTRY_PATH):
    """Append one exclusion to the registry. Idempotent - a full_name
    already present is left as-is (first recorded reason wins; edit the
    CSV directly to revise a reason). Returns True if a new row was
    written, False if the repo was already registered."""
    path = Path(path)
    existing = load_exclusion_rows(path)
    if any(r["full_name"] == full_name for r in existing):
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    write_header = not path.exists()
    with path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow({
            "full_name": full_name,
            "excluded_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "reason": reason,
            "scope": scope,
        })
    return True
