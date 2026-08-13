// Tool-CS's entry point: analyze one materialized C# snapshot directory
// (Phase 1e, materialize_snapshots.py) and print its metrics row as a
// single line of JSON on stdout - invoked from Python
// (src/inhouse/csharp_metrics.py) the same way run_designite() shells out
// to DesigniteConsole in long_analysis.py, just calling our own compiled
// tool instead of a licensed one.
//
// Usage: RoslynMetrics <snapshot-dir>
//
// A second mode, --batch, supports the RQ3 entity-history tool
// (Stage 4 of the execution plan, src/inhouse/cs_entity_history.py):
// reads a JSON array of {"relpath": ..., "text": ...} blobs from stdin
// (arbitrary git-show output, not a snapshot directory) and writes a JSON
// array of per-blob class/method inventories to stdout, in the same
// order as the input. Batched deliberately - one process per commit was
// checked empirically and found too slow (.NET startup cost dominates at
// that granularity, see the build log); one process handles a whole
// file's touching-commit history in a single call instead.
//
// Usage: RoslynMetrics --batch < blobs.json > results.json
//
// A third mode, --smells, mirrors the default mode but runs
// SmellDetector.cs (the C# port of py_smells.py) instead of
// SnapshotAnalyzer's OO-metrics engine - kept as a separate mode/output
// row rather than merged into the default JSON, so the smell pipeline can
// be run/resumed independently of the OO-metrics one (same separation
// src/inhouse/pool_inhouse_metrics.py vs. pool_inhouse_smells.py already
// keeps on the Python side).
//
// Usage: RoslynMetrics --smells <snapshot-dir>

if (args.Length == 1 && args[0] == "--batch")
{
    return RunBatchMode();
}

if (args.Length == 2 && args[0] == "--smells")
{
    return RunSnapshotMode(args[1], smells: true);
}

if (args.Length != 1)
{
    Console.Error.WriteLine("usage: RoslynMetrics <snapshot-dir>");
    Console.Error.WriteLine("       RoslynMetrics --batch < blobs.json > results.json");
    Console.Error.WriteLine("       RoslynMetrics --smells <snapshot-dir>");
    return 2;
}

return RunSnapshotMode(args[0], smells: false);

static int RunSnapshotMode(string snapshotDir, bool smells)
{
    if (!Directory.Exists(snapshotDir))
    {
        Console.Error.WriteLine($"snapshot dir not found: {snapshotDir}");
        return 2;
    }

    try
    {
        var json = smells
            ? RoslynMetrics.SmellDetector.AnalyzeSmellsToJson(snapshotDir)
            : RoslynMetrics.SnapshotAnalyzer.AnalyzeToJson(snapshotDir);
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
}

static int RunBatchMode()
{
    var stdin = Console.In.ReadToEnd();
    List<(string RelPath, string Text)> inputs;
    try
    {
        using var doc = System.Text.Json.JsonDocument.Parse(stdin);
        inputs = doc.RootElement.EnumerateArray()
            .Select(el => (
                RelPath: el.GetProperty("relpath").GetString() ?? "",
                Text: el.GetProperty("text").GetString() ?? ""
            ))
            .ToList();
    }
    catch (Exception e)
    {
        Console.Error.WriteLine($"failed to parse stdin JSON: {e.Message}");
        return 2;
    }

    var results = RoslynMetrics.EntityHistory.AnalyzeBatch(inputs);
    Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(results));
    return 0;
}
