using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;
using Microsoft.CodeAnalysis.Text;

namespace RoslynMetrics;

// RQ3 entity-history mode (Stage 4 of the execution plan): given one or
// more (relpath, text) blobs extracted from arbitrary git commits (not a
// materialized snapshot directory - SnapshotAnalyzer.cs's domain), extract
// each blob's class/method inventory including SOURCE TEXT per entity, so
// Python's entity_matching.py can tokenize and fuzzy-match the same way it
// already does for Python (see py_entity_history.py's _entity_snapshot).
//
// Deliberately a SEPARATE, self-contained extraction pass, not a shared
// refactor of SnapshotAnalyzer.cs's private helpers - SnapshotAnalyzer is
// already built and validated (Writing/ProjectStatus.md §6's Tool-CS
// validation), and this needs a different output shape (source text per
// entity, no metrics computation at all - no CC, no LCOM/DIT/Fan-In/Out,
// none of which entity-history needs). The qualified-name/method-name
// logic below intentionally mirrors SnapshotAnalyzer's QualifiedNameOf/
// MethodNameOf (same node types, same Parent-chain walk) rather than
// inventing a different convention - kept in sync by design intent, not by
// sharing code, a deliberate simplicity-over-DRY tradeoff for ~40 lines of
// stable, well-understood logic touching zero already-validated output.
//
// Batched via stdin/stdout (one process handles many blobs in one call),
// not one process per commit - .NET process startup cost (checked
// empirically before committing to this design, see the build log) makes
// per-commit invocation prohibitively slow across a file's full history.
//
// Output keys are plain snake_case Dictionary<string, object?> entries,
// matching SnapshotAnalyzer.AnalyzeToJson's existing convention (manual
// dictionary, not attribute-driven serialization) rather than introducing
// a second JSON-shaping convention into this project.
public static class EntityHistory
{
    public static List<Dictionary<string, object?>> AnalyzeBatch(
        List<(string RelPath, string Text)> inputs)
    {
        var results = new List<Dictionary<string, object?>>();
        foreach (var (_, text) in inputs)
        {
            try
            {
                results.Add(AnalyzeOne(text));
            }
            catch (Exception e)
            {
                results.Add(new Dictionary<string, object?> { ["status"] = $"error: {e.Message}" });
            }
        }
        return results;
    }

    private static Dictionary<string, object?> AnalyzeOne(string text)
    {
        var tree = CSharpSyntaxTree.ParseText(text);
        var root = tree.GetCompilationUnitRoot();

        var classes = new List<Dictionary<string, object?>>();
        var callables = new List<Dictionary<string, object?>>();

        foreach (var classNode in root.DescendantNodes().OfType<ClassDeclarationSyntax>())
        {
            var qualifiedName = QualifiedNameOf(classNode);
            var (classText, classLoc) = SliceSpan(tree, text, classNode.Span);
            classes.Add(new Dictionary<string, object?>
            {
                ["name"] = classNode.Identifier.Text,
                ["qualified_name"] = qualifiedName,
                ["kind"] = "class",
                ["param_count"] = null,
                ["loc"] = classLoc,
                ["source_text"] = classText,
            });

            // BaseMethodDeclarationSyntax, not just MethodDeclarationSyntax -
            // same reasoning as SnapshotAnalyzer.BuildClassInfo: constructors
            // are a sibling node type, not a subtype, and would otherwise be
            // silently dropped.
            foreach (var methodNode in classNode.Members.OfType<BaseMethodDeclarationSyntax>())
            {
                var name = MethodNameOf(methodNode);
                var (methodText, methodLoc) = SliceSpan(tree, text, methodNode.Span);
                callables.Add(new Dictionary<string, object?>
                {
                    ["name"] = name,
                    ["qualified_name"] = $"{qualifiedName}.{name}",
                    ["kind"] = "callable",
                    ["param_count"] = methodNode.ParameterList.Parameters.Count,
                    ["loc"] = methodLoc,
                    ["source_text"] = methodText,
                });
            }
        }

        return new Dictionary<string, object?>
        {
            ["status"] = "ok",
            ["classes"] = classes,
            ["callables"] = callables,
        };
    }

    // Line-span text slice, matching py_entity_history.py's
    // file_lines[start-1:end] approach - the entity's own body text is what
    // entity_matching.py's tokenize() needs, not a metric.
    private static (string text, int loc) SliceSpan(SyntaxTree tree, string fullText, TextSpan span)
    {
        var lineSpan = tree.GetLineSpan(span);
        var loc = lineSpan.EndLinePosition.Line - lineSpan.StartLinePosition.Line + 1;
        var slice = fullText.Substring(span.Start, span.Length);
        return (slice, loc);
    }

    // Mirrors SnapshotAnalyzer.QualifiedNameOf exactly (same Parent-chain
    // walk over class/namespace declarations) - see this file's header
    // comment for why it's a separate copy, not a shared call.
    private static string QualifiedNameOf(ClassDeclarationSyntax node)
    {
        var parts = new List<string> { node.Identifier.Text };
        SyntaxNode? current = node.Parent;
        while (current is not null)
        {
            switch (current)
            {
                case ClassDeclarationSyntax outer:
                    parts.Insert(0, outer.Identifier.Text);
                    break;
                case NamespaceDeclarationSyntax ns:
                    parts.Insert(0, ns.Name.ToString());
                    break;
                case FileScopedNamespaceDeclarationSyntax fns:
                    parts.Insert(0, fns.Name.ToString());
                    break;
            }
            current = current.Parent;
        }
        return string.Join(".", parts);
    }

    private static string MethodNameOf(BaseMethodDeclarationSyntax node) => node switch
    {
        MethodDeclarationSyntax m => m.Identifier.Text,
        ConstructorDeclarationSyntax c => c.Identifier.Text,
        DestructorDeclarationSyntax d => "~" + d.Identifier.Text,
        OperatorDeclarationSyntax o => "operator" + o.OperatorToken.Text,
        ConversionOperatorDeclarationSyntax co => "operator " + co.Type,
        _ => node.GetType().Name,
    };
}
