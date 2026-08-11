// Phase B's entry point: analyze one materialized C# snapshot directory
// (Phase 1e, materialize_snapshots.py) and print its metrics row as a
// single line of JSON on stdout - invoked from Python
// (src/inhouse/csharp_metrics.py) the same way run_designite() shells out
// to DesigniteConsole in long_analysis.py, just calling our own compiled
// tool instead of a licensed one.
//
// Usage: RoslynMetrics <snapshot-dir>

if (args.Length != 1)
{
    Console.Error.WriteLine("usage: RoslynMetrics <snapshot-dir>");
    return 2;
}

var snapshotDir = args[0];
if (!Directory.Exists(snapshotDir))
{
    Console.Error.WriteLine($"snapshot dir not found: {snapshotDir}");
    return 2;
}

try
{
    var json = RoslynMetrics.SnapshotAnalyzer.AnalyzeToJson(snapshotDir);
    Console.WriteLine(json);
    return 0;
}
catch (Exception e)
{
    // Structured error on stdout (not just stderr) so the Python caller can
    // parse a JSON object either way, matching process_row()'s convention
    // in long_analysis.py of always recording *something* keyed and moving
    // on rather than letting one bad snapshot kill a batch run.
    var err = new Dictionary<string, object?> { ["status"] = $"error: {e.Message}" };
    Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(err));
    return 1;
}
