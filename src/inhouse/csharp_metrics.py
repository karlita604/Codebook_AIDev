"""
Python glue for Tool-CS's C# analyzer - shells out to the compiled Roslyn
console tool (src/inhouse/roslyn_tool/) the same way long_analysis.py's
run_designite() shells out to DesigniteConsole, just calling our own
syntax-only tool instead of a licensed one. See
Writing/InHouseTooling.md's design-decisions section for why syntax-only
Roslyn (no MSBuildWorkspace/.sln load) was chosen.

analyze_snapshot() returns the same schema py_metrics.py's analyze_snapshot()
does (see that module's docstring for the exact column meanings) - the two
languages pool into one table with no adapter step.
"""

import json
import subprocess
from pathlib import Path

TOOL_DIR = Path(__file__).resolve().parent / "roslyn_tool"
TOOL_DLL = TOOL_DIR / "bin" / "Release" / "net8.0" / "roslyn_tool.dll"


def ensure_built():
    if TOOL_DLL.exists():
        return
    result = subprocess.run(
        ["dotnet", "build", "-c", "Release"],
        cwd=TOOL_DIR, capture_output=True, text=True,
    )
    if result.returncode != 0 or not TOOL_DLL.exists():
        raise RuntimeError(
            f"failed to build {TOOL_DIR}:\n{result.stdout}\n{result.stderr}"
        )


def analyze_snapshot(snapshot_dir, timeout=120):
    """Run the compiled Roslyn tool against one materialized C# snapshot
    directory and return its metrics dict. Raises on a non-zero exit or a
    stdout that isn't the expected single-line JSON - process_row-style
    callers catch and log this the same way a DPy/Designite subprocess
    failure is already caught in long_analysis.py, not swallowed here."""
    ensure_built()
    result = subprocess.run(
        ["dotnet", str(TOOL_DLL), str(snapshot_dir)],
        capture_output=True, text=True, timeout=timeout,
    )
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"roslyn_tool produced non-JSON output "
            f"(exit {result.returncode}): "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        ) from e
