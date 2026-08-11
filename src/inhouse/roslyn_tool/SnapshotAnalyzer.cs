using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace RoslynMetrics;

// Mirrors py_metrics.py end to end: same per-snapshot aggregation, same
// output keys, same percentile method (linear interpolation, matching
// pandas' default .quantile()) - so C# and Python rows pool into the same
// table with no adapter step, same as DPy/Designite's own pooling turned
// out not to need one (ProjectStatus.md's "Schema note").
//
// Syntax-only: CSharpSyntaxTree.ParseText, never MSBuildWorkspace - no
// .sln/.csproj load, no project restore. This is what's expected to
// unblock dotnet/aspire (excluded from the Designite pilot because
// MSBuildWorkspace can't evaluate its project graph without Arcade's own
// bootstrap) - see Writing/InHouseTooling.md's design-decisions section.
// Fan-In/Fan-Out/DIT are therefore heuristic, whole-snapshot-scoped
// approximations, not real semantic type resolution - documented inline
// wherever they're computed, same caveat as the Python side.
public static class SnapshotAnalyzer
{
    public static string AnalyzeToJson(string snapshotDir)
    {
        var modules = ParseSnapshot(snapshotDir);
        var allClasses = modules.SelectMany(m => m.Classes).ToList();
        var allMethods = allClasses.SelectMany(c => c.Methods).ToList();

        var classIndex = BuildClassIndex(allClasses);
        var (fanOut, fanIn) = ComputeFanInOut(classIndex);

        var totalLoc = modules.Sum(m => m.PhysicalLoc);
        var nParseErrors = modules.Sum(m => m.DiagnosticErrorCount);

        var classLoc = allClasses.Select(c => (double)c.Loc).ToList();
        var methodLoc = allMethods.Select(m => (double)m.Loc).ToList();
        var methodCc = allMethods.Select(m => (double)m.Cc).ToList();
        var methodPc = allMethods.Select(m => (double)m.ParamCount).ToList();
        var classWmc = allClasses.Select(c => (double)c.Methods.Sum(m => m.Cc)).ToList();
        var classLcom = allClasses.Select(c => (double)ComputeLcom(c)).ToList();
        var classDit = allClasses.Select(c => (double)ComputeDit(c, classIndex, new HashSet<string>())).ToList();
        var classFanIn = allClasses.Select(c => (double)fanIn.GetValueOrDefault(c.Name, 0)).ToList();
        var classFanOut = allClasses.Select(c => (double)fanOut.GetValueOrDefault(c.Name, 0)).ToList();

        var result = new Dictionary<string, object?>
        {
            ["total_loc"] = totalLoc,
            ["n_files"] = modules.Count,
            ["n_parse_errors"] = nParseErrors,
            ["n_classes"] = allClasses.Count,
            ["n_methods"] = allMethods.Count,
            ["class_loc_p50"] = Percentile(classLoc, 0.5),
            ["class_loc_p90"] = Percentile(classLoc, 0.9),
            ["method_loc_p50"] = Percentile(methodLoc, 0.5),
            ["method_loc_p90"] = Percentile(methodLoc, 0.9),
            ["cyclomatic_complexity_p50"] = Percentile(methodCc, 0.5),
            ["cyclomatic_complexity_p90"] = Percentile(methodCc, 0.9),
            ["pc_p50"] = Percentile(methodPc, 0.5),
            ["pc_p90"] = Percentile(methodPc, 0.9),
            ["wmc_p50"] = Percentile(classWmc, 0.5),
            ["wmc_p90"] = Percentile(classWmc, 0.9),
            ["lcom_p50"] = Percentile(classLcom, 0.5),
            ["lcom_p90"] = Percentile(classLcom, 0.9),
            ["dit_p50"] = Percentile(classDit, 0.5),
            ["dit_p90"] = Percentile(classDit, 0.9),
            ["fan_in_p50"] = Percentile(classFanIn, 0.5),
            ["fan_in_p90"] = Percentile(classFanIn, 0.9),
            ["fan_out_p50"] = Percentile(classFanOut, 0.5),
            ["fan_out_p90"] = Percentile(classFanOut, 0.9),
            ["status"] = "ok",
        };

        return System.Text.Json.JsonSerializer.Serialize(result);
    }

    private static List<ModuleInfo> ParseSnapshot(string snapshotDir)
    {
        var modules = new List<ModuleInfo>();
        var files = Directory.EnumerateFiles(snapshotDir, "*.cs", SearchOption.AllDirectories).OrderBy(f => f);

        foreach (var path in files)
        {
            string text;
            try { text = File.ReadAllText(path); }
            catch (IOException) { continue; }

            var tree = CSharpSyntaxTree.ParseText(text);
            var root = tree.GetCompilationUnitRoot();
            var errorCount = tree.GetDiagnostics().Count(d => d.Severity == DiagnosticSeverity.Error);

            var relPath = Path.GetRelativePath(snapshotDir, path);
            var classes = ExtractClasses(root, tree, relPath);
            var physicalLoc = CountPhysicalLines(text);

            modules.Add(new ModuleInfo
            {
                RelPath = relPath,
                PhysicalLoc = physicalLoc,
                Classes = classes,
                DiagnosticErrorCount = errorCount,
            });
        }

        return modules;
    }

    private static int CountPhysicalLines(string text)
    {
        if (text.Length == 0) return 0;
        var n = text.Count(c => c == '\n');
        return text.EndsWith('\n') ? n : n + 1;
    }

    // Every ClassDeclarationSyntax in the file regardless of nesting depth
    // (namespace-level and nested classes alike) - broader than
    // ast_common.py's "top-level classes only" restriction, since C# nests
    // classes far less often than Python nests functions, and this stays
    // closer to what a real class-metrics tool (Designite) would count.
    // Interfaces/structs/records are NOT counted as classes - matches
    // DPy/Designite's own "class" scope (their ClassMetrics.csv is classes
    // specifically, not every type declaration).
    private static List<ClassInfo> ExtractClasses(CompilationUnitSyntax root, SyntaxTree tree, string relPath)
    {
        var result = new List<ClassInfo>();
        foreach (var classNode in root.DescendantNodes().OfType<ClassDeclarationSyntax>())
        {
            result.Add(BuildClassInfo(classNode, tree));
        }
        return result;
    }

    private static ClassInfo BuildClassInfo(ClassDeclarationSyntax node, SyntaxTree tree)
    {
        var qualifiedName = QualifiedNameOf(node);
        // BaseMethodDeclarationSyntax, not just MethodDeclarationSyntax -
        // constructors (and destructors/operators) are a DIFFERENT Roslyn
        // node type from ordinary methods, not a subtype of
        // MethodDeclarationSyntax. Missing this would silently drop every
        // constructor from NOM/WMC and - worse - from LCOM's field-access
        // scan, where a constructor is often the ONE place that touches
        // every field (the exact case that most affects LCOM's result).
        var methods = node.Members.OfType<BaseMethodDeclarationSyntax>()
            .Select(m => BuildMethodInfo(m, qualifiedName, tree))
            .ToList();

        var fieldNames = new List<string>();
        var publicFieldNames = new List<string>();
        foreach (var field in node.Members.OfType<FieldDeclarationSyntax>())
        {
            var isPublic = field.Modifiers.Any(SyntaxKind.PublicKeyword);
            foreach (var variable in field.Declaration.Variables)
            {
                fieldNames.Add(variable.Identifier.Text);
                if (isPublic) publicFieldNames.Add(variable.Identifier.Text);
            }
        }
        // Auto-properties (public int Foo { get; set; }) are the idiomatic
        // C# equivalent of a public field in most codebases - counted
        // alongside real fields so NOF/NOPF aren't systematically low on
        // property-heavy C# code compared to Python's plain-attribute style.
        foreach (var prop in node.Members.OfType<PropertyDeclarationSyntax>())
        {
            var isPublic = prop.Modifiers.Any(SyntaxKind.PublicKeyword);
            fieldNames.Add(prop.Identifier.Text);
            if (isPublic) publicFieldNames.Add(prop.Identifier.Text);
        }

        var bases = node.BaseList?.Types.Select(t => BaseTypeName(t.Type)).Where(n => n is not null)
            .Select(n => n!).ToList() ?? new List<string>();

        var span = tree.GetLineSpan(node.Span);
        var loc = span.EndLinePosition.Line - span.StartLinePosition.Line + 1;

        return new ClassInfo
        {
            Name = node.Identifier.Text,
            QualifiedName = qualifiedName,
            Loc = loc,
            IsPublic = node.Modifiers.Any(SyntaxKind.PublicKeyword),
            Bases = bases,
            Methods = methods,
            FieldNames = fieldNames,
            PublicFieldNames = publicFieldNames,
            FieldNameSet = new HashSet<string>(fieldNames),
            Node = node,
        };
    }

    private static MethodInfo BuildMethodInfo(BaseMethodDeclarationSyntax node, string classQualifiedName, SyntaxTree tree)
    {
        var span = tree.GetLineSpan(node.Span);
        var loc = span.EndLinePosition.Line - span.StartLinePosition.Line + 1;
        var name = MethodNameOf(node);
        return new MethodInfo
        {
            Name = name,
            QualifiedName = $"{classQualifiedName}.{name}",
            Loc = loc,
            Cc = CcWalker.Compute(node),
            ParamCount = node.ParameterList.Parameters.Count,
            IsPublic = node.Modifiers.Any(SyntaxKind.PublicKeyword),
        };
    }

    // BaseMethodDeclarationSyntax's concrete subtypes each name themselves
    // differently (MethodDeclarationSyntax/ConstructorDeclarationSyntax use
    // .Identifier, operators use .OperatorToken/.Type instead) - no shared
    // .Identifier on the base type itself.
    private static string MethodNameOf(BaseMethodDeclarationSyntax node) => node switch
    {
        MethodDeclarationSyntax m => m.Identifier.Text,
        ConstructorDeclarationSyntax c => c.Identifier.Text,
        DestructorDeclarationSyntax d => "~" + d.Identifier.Text,
        OperatorDeclarationSyntax o => "operator" + o.OperatorToken.Text,
        ConversionOperatorDeclarationSyntax co => "operator " + co.Type,
        _ => node.GetType().Name,
    };

    // Best-effort textual name for a base-type expression - handles plain
    // `Base` and generic `Base<T>` (base name only, type args dropped for
    // DIT/Fan-Out resolution purposes). Anything more complex falls back to
    // null (treated as unresolvable, same as ast_common.py's `_base_name`
    // returning None for a dynamic base expression).
    private static string? BaseTypeName(TypeSyntax type) => type switch
    {
        IdentifierNameSyntax id => id.Identifier.Text,
        GenericNameSyntax gen => gen.Identifier.Text,
        QualifiedNameSyntax qn => qn.Right is IdentifierNameSyntax r ? r.Identifier.Text
            : qn.Right is GenericNameSyntax rg ? rg.Identifier.Text : null,
        _ => null,
    };

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

    // Bare class name -> ClassInfo across the whole snapshot. Ambiguous
    // when two classes share a name across different files/namespaces -
    // keeps whichever is encountered first (files walked in sorted-path
    // order). Same documented approximation as py_metrics.py's
    // _build_class_index.
    private static Dictionary<string, ClassInfo> BuildClassIndex(List<ClassInfo> classes)
    {
        var index = new Dictionary<string, ClassInfo>();
        foreach (var c in classes)
        {
            index.TryAdd(c.Name, c);
        }
        return index;
    }

    // Depth of Inheritance Tree: ancestor classes resolvable within this
    // snapshot only. A base outside the snapshot (BCL, a NuGet dependency,
    // e.g. `Exception` or a framework base class) can't be resolved and is
    // a DIT boundary, not an error. `seen` guards a base-resolution cycle.
    private static int ComputeDit(ClassInfo cls, Dictionary<string, ClassInfo> classIndex, HashSet<string> seen)
    {
        if (seen.Contains(cls.QualifiedName) || cls.Bases.Count == 0) return 0;
        var nextSeen = new HashSet<string>(seen) { cls.QualifiedName };
        var best = 0;
        foreach (var baseName in cls.Bases)
        {
            if (classIndex.TryGetValue(baseName, out var baseCls))
            {
                best = Math.Max(best, 1 + ComputeDit(baseCls, classIndex, nextSeen));
            }
        }
        return best;
    }

    // Known (in-snapshot) class names textually referenced inside a method
    // body - a bare IdentifierNameSyntax matching a known class, or a
    // MemberAccessExpression whose .Name matches one. Textual/heuristic,
    // NOT real type resolution (no semantic model, no using-alias
    // resolution) - same category of approximation
    // py_metrics.py's _referenced_class_names carries, and the same
    // chunk-boundary caveat Designite's own Fan-In/Fan-Out already has
    // (DESIGNITE_TASK.md's metrics table).
    private static HashSet<string> ReferencedClassNames(SyntaxNode node, HashSet<string> classNames)
    {
        var found = new HashSet<string>();
        foreach (var id in node.DescendantNodes().OfType<IdentifierNameSyntax>())
        {
            if (classNames.Contains(id.Identifier.Text)) found.Add(id.Identifier.Text);
        }
        foreach (var ma in node.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
        {
            if (classNames.Contains(ma.Name.Identifier.Text)) found.Add(ma.Name.Identifier.Text);
        }
        return found;
    }

    private static (Dictionary<string, int> fanOut, Dictionary<string, int> fanIn) ComputeFanInOut(
        Dictionary<string, ClassInfo> classIndex)
    {
        var classNames = new HashSet<string>(classIndex.Keys);
        var fanOut = new Dictionary<string, int>();
        var fanOutSets = new Dictionary<string, HashSet<string>>();

        foreach (var cls in classIndex.Values)
        {
            var refs = new HashSet<string>(cls.Bases.Where(classNames.Contains));
            foreach (var method in cls.Node.Members.OfType<BaseMethodDeclarationSyntax>())
            {
                refs.UnionWith(ReferencedClassNames(method, classNames));
            }
            refs.Remove(cls.Name);
            fanOutSets[cls.Name] = refs;
            fanOut[cls.Name] = refs.Count;
        }

        var fanIn = classIndex.Keys.ToDictionary(name => name, _ => 0);
        foreach (var (name, refs) in fanOutSets)
        {
            foreach (var target in refs)
            {
                fanIn[target] = fanIn.GetValueOrDefault(target, 0) + 1;
            }
        }

        return (fanOut, fanIn);
    }

    // Chidamber & Kemerer's original LCOM (LCOM1): P = method pairs sharing
    // no field access, Q = pairs sharing at least one. LCOM = max(0, P-Q).
    // Field-access set per method is real declared fields (+ auto-
    // properties) referenced in that method's body, bare or via `this.` -
    // built from the class's actual FieldNameSet, not inferred from usage
    // the way ast_common.py's Python-side heuristic has to (Python has no
    // field-declaration syntax). This sidesteps the "method call misread as
    // field access" bug the Python engine hit and had to special-case
    // (ast_common.self_attribute_names' `exclude` parameter) - a method
    // name only ever ends up in this set if it ALSO happens to be a real
    // declared field name, which a lookup against FieldNameSet already
    // guards against structurally.
    private static int ComputeLcom(ClassInfo cls)
    {
        var methods = cls.Node.Members.OfType<BaseMethodDeclarationSyntax>().ToList();
        if (methods.Count < 2) return 0;

        var fieldSets = methods.Select(m =>
        {
            var fields = new HashSet<string>();
            foreach (var id in m.DescendantNodes().OfType<IdentifierNameSyntax>())
            {
                if (cls.FieldNameSet.Contains(id.Identifier.Text)) fields.Add(id.Identifier.Text);
            }
            foreach (var ma in m.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
            {
                if (ma.Expression.IsKind(SyntaxKind.ThisExpression) && cls.FieldNameSet.Contains(ma.Name.Identifier.Text))
                {
                    fields.Add(ma.Name.Identifier.Text);
                }
            }
            return fields;
        }).ToList();

        int p = 0, q = 0;
        for (var i = 0; i < fieldSets.Count; i++)
        {
            for (var j = i + 1; j < fieldSets.Count; j++)
            {
                if (fieldSets[i].Overlaps(fieldSets[j])) q++;
                else p++;
            }
        }
        return Math.Max(0, p - q);
    }

    // Linear-interpolation percentile - matches pandas' default
    // .quantile(q), which is what both the DPy/Designite pooling
    // (long_analysis.py's _pctl helper) and py_metrics.py already use, so
    // percentiles are directly comparable across all three.
    private static double? Percentile(List<double> values, double q)
    {
        if (values.Count == 0) return null;
        var sorted = values.OrderBy(v => v).ToList();
        var pos = q * (sorted.Count - 1);
        var lo = (int)Math.Floor(pos);
        var hi = (int)Math.Ceiling(pos);
        if (lo == hi) return sorted[lo];
        var frac = pos - lo;
        return sorted[lo] + (sorted[hi] - sorted[lo]) * frac;
    }
}
