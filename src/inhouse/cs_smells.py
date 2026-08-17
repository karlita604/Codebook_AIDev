"""
Python glue for the C# smell detector (SmellDetector.cs, the C# port of
py_smells.py) - shells out to the same compiled Roslyn console tool
csharp_metrics.py already uses, just invoked in --smells mode instead of
the default OO-metrics mode. See SmellDetector.cs's module docstring for
the detection strategies themselves.

analyze_snapshot() returns the same schema py_smells.py's analyze_snapshot()
does, so the two languages' smell rows pool into one table with no adapter
step - same convention csharp_metrics.py already established for OO metrics.
"""

import json
import subprocess

from csharp_metrics import TOOL_DLL, ensure_built


def analyze_snapshot(snapshot_dir, timeout=120):
    """Run the compiled Roslyn tool's --smells mode against one materialized
    C# snapshot directory and return its smell-metrics dict. Raises on a
    non-zero exit or a stdout that isn't the expected single-line JSON -
    same convention as csharp_metrics.analyze_snapshot()."""
    ensure_built()
    result = subprocess.run(
        ["dotnet", str(TOOL_DLL), "--smells", str(snapshot_dir)],
        capture_output=True, text=True, timeout=timeout,
    )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"roslyn_tool --smells produced non-JSON output "
            f"(exit {result.returncode}): "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        ) from e
