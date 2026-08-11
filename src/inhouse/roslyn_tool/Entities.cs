using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace RoslynMetrics;

// Mirrors ast_common.py's MethodEntity/ClassEntity - same shape, same fields,
// so the two languages' analyzers read as one design translated twice, not
// two unrelated implementations. See py_metrics.py's module docstring for
// why each metric is defined the way it is; the C# side follows the same
// definitions, adapted to Roslyn's syntax model.
public sealed class MethodInfo
{
    public required string Name { get; init; }
    public required string QualifiedName { get; init; }
    public required int Loc { get; init; }
    public required int Cc { get; init; }
    public required int ParamCount { get; init; }
    public required bool IsPublic { get; init; }
}

public sealed class ClassInfo
{
    public required string Name { get; init; }
    public required string QualifiedName { get; init; }
    public required int Loc { get; init; }
    public required bool IsPublic { get; init; }
    public required List<string> Bases { get; init; }
    public required List<MethodInfo> Methods { get; init; }
    public required List<string> FieldNames { get; init; }
    public required List<string> PublicFieldNames { get; init; }

    // Field-name -> is-declared-public, kept alongside FieldNames/PublicFieldNames
    // (which are just the flattened lists other code reads) so LCOM can look up
    // "is this identifier one of the class's own declared fields" without
    // Python's self.X-usage-heuristic problem - C# has real field-declaration
    // syntax, so the field set here comes directly from FieldDeclarationSyntax,
    // not inferred from how the field is used anywhere in a method body.
    public required HashSet<string> FieldNameSet { get; init; }

    public ClassDeclarationSyntax Node { get; init; } = null!;
}

public sealed class ModuleInfo
{
    public required string RelPath { get; init; }
    public required int PhysicalLoc { get; init; }
    public required List<ClassInfo> Classes { get; init; }
    public required int DiagnosticErrorCount { get; init; }
}
