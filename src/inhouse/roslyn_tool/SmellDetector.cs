using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace RoslynMetrics;

// C# port of src/inhouse/py_smells.py - same four Lanza & Marinescu (2006)
// Detection Strategies (God Class/Blob, Data Class, Feature Envy, Brain
// Method), same fixed literature constants, same corpus-relative
// percentile thresholds (HIGH=p75, VERY_HIGH=p90, God Class's already-
// tuned TopValues(10%)/BottomValues(10%) - see Writing/PySmellDetection.md's
// "God Class threshold revision" section for why 10%/10%, not the paper's
// original 25%/25%). Full method writeup/formula provenance lives there;
// this file is the C#-side translation, not a second design.
//
// One real structural difference from the Python side, worth stating up
// front: C# has real field AND property declarations
// (ClassInfo.FieldNameSet already includes both, see Entities.cs), so
// there's no py_smells.py-style self.method()-read-as-field-access bug to
// guard against here. TCC/LCOM's field-access sets come directly from
// SnapshotAnalyzer.FieldAccessSets - reused, not re-walked.
public static class SmellDetector
{
    private const double OneThird = 1.0 / 3.0;
    private const int Few = 5;
    private const int Many = 7;
    private const int Several = 3;

    public static string AnalyzeSmellsToJson(string snapshotDir)
    {
        var modules = SnapshotAnalyzer.ParseSnapshot(snapshotDir);
        var allClasses = modules.SelectMany(m => m.Classes).ToList();
        var knownFieldNames = new HashSet<string>(allClasses.SelectMany(c => c.FieldNameSet));

        var classRows = allClasses.Select(c => ClassSmellMetrics(c, knownFieldNames)).ToList();
        var methodRows = new List<MethodSmellRow>();
        foreach (var cls in allClasses)
        {
            var fieldSets = SnapshotAnalyzer.FieldAccessSets(cls);
            var methodNodes = cls.Node.Members.OfType<BaseMethodDeclarationSyntax>().ToList();
            for (var i = 0; i < cls.Methods.Count; i++)
            {
                methodRows.Add(MethodSmellMetrics(cls.Methods[i], methodNodes[i], cls.Loc, fieldSets[i], knownFieldNames));
            }
        }

        DetectSmells(classRows, methodRows);

        var totalLoc = modules.Sum(m => m.PhysicalLoc);
        var kloc = totalLoc > 0 ? totalLoc / 1000.0 : (double?)null;
        var nGodClass = classRows.Count(r => r.IsGodClass);
        var nDataClass = classRows.Count(r => r.IsDataClass);
        var nFeatureEnvy = methodRows.Count(r => r.IsFeatureEnvy);
        var nBrainMethod = methodRows.Count(r => r.IsBrainMethod);
        var designSmellCount = nGodClass + nDataClass;
        var implSmellCount = nFeatureEnvy + nBrainMethod;

        var result = new Dictionary<string, object?>
        {
            ["total_loc"] = totalLoc,
            ["n_files"] = modules.Count,
            ["n_parse_errors"] = modules.Sum(m => m.DiagnosticErrorCount),
            ["n_classes"] = allClasses.Count,
            ["n_methods"] = methodRows.Count,
            ["n_god_class"] = nGodClass,
            ["n_data_class"] = nDataClass,
            ["n_feature_envy"] = nFeatureEnvy,
            ["n_brain_method"] = nBrainMethod,
            // How many classes' TCC (God Class's cohesion filter) was
            // estimated from a seeded sample instead of the full pairwise
            // computation - see SnapshotAnalyzer.SampleFieldSets(). Near-
            // always 0; >0 flags a snapshot with an exceptionally large
            // class.
            ["n_tcc_sampled"] = classRows.Count(r => r.TccSampled),
            ["design_smell_count"] = designSmellCount,
            ["design_smell_density_per_kloc"] = kloc is null ? null : designSmellCount / kloc,
            ["implementation_smell_count"] = implSmellCount,
            ["implementation_smell_density_per_kloc"] = kloc is null ? null : implSmellCount / kloc,
            ["status"] = "ok",
        };
        return System.Text.Json.JsonSerializer.Serialize(result);
    }

    private sealed class ClassSmellRow
    {
        public required double Loc;
        public required double Wmc;
        public required double Tcc;
        public required bool TccSampled;
        public required double Atfd;
        public required double Woc;
        public required double Nopa;
        public required double Noam;
        public bool IsGodClass;
        public bool IsDataClass;
    }

    private sealed class MethodSmellRow
    {
        public required double ClassLoc;
        public required double Loc;
        public required double Cyclo;
        public required double Atfd;
        public required double Fdp;
        public required double Laa;
        public required double MaxNesting;
        public required double Noav;
        public bool IsFeatureEnvy;
        public bool IsBrainMethod;
    }

    // Bare `receiver.member` accesses where receiver is a simple identifier
    // other than `this`, and `member` is a name present in the whole-
    // snapshot known-field catalog - direct translation of
    // ast_common.py's foreign_attribute_accesses. Textual/heuristic, same
    // documented tradeoff: no semantic type resolution, filtered against
    // the known-field catalog to cut noise from unrelated same-named
    // members (a stdlib/BCL object with a same-named property, etc.).
    private static HashSet<(string Receiver, string Attr)> ForeignAccesses(
        SyntaxNode methodNode, HashSet<string> knownFieldNames)
    {
        var found = new HashSet<(string, string)>();
        foreach (var ma in methodNode.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
        {
            if (ma.Expression is IdentifierNameSyntax id
                && knownFieldNames.Contains(ma.Name.Identifier.Text))
            {
                found.Add((id.Identifier.Text, ma.Name.Identifier.Text));
            }
        }
        return found;
    }

    // Distinct accessed identifiers - bare Name reads/writes plus
    // this.member accesses (kept as "this.X" so they can't collide with an
    // unrelated local of the same bare name) - proxy for NOAV, same
    // convention as ast_common.py's accessed_variable_names.
    private static HashSet<string> AccessedVariableNames(SyntaxNode methodNode)
    {
        var found = new HashSet<string>();
        foreach (var id in methodNode.DescendantNodes().OfType<IdentifierNameSyntax>())
        {
            if (id.Parent is MemberAccessExpressionSyntax) continue;
            found.Add(id.Identifier.Text);
        }
        foreach (var ma in methodNode.DescendantNodes().OfType<MemberAccessExpressionSyntax>())
        {
            if (ma.Expression.IsKind(SyntaxKind.ThisExpression))
            {
                found.Add("this." + ma.Name.Identifier.Text);
            }
        }
        return found;
    }

    // Deepest control-flow nesting - if/for/foreach/while/do/try/switch/
    // using, stopping at nested method/local-function/type boundaries
    // (same boundary convention as CcWalker). Direct translation of
    // ast_common.py's max_nesting_level.
    private sealed class NestingWalker : CSharpSyntaxWalker
    {
        public int MaxDepth { get; private set; }
        private int _depth;

        private void Enter(Action visitBase)
        {
            _depth++;
            if (_depth > MaxDepth) MaxDepth = _depth;
            visitBase();
            _depth--;
        }

        public override void VisitIfStatement(IfStatementSyntax node) => Enter(() => base.VisitIfStatement(node));
        public override void VisitForStatement(ForStatementSyntax node) => Enter(() => base.VisitForStatement(node));
        public override void VisitForEachStatement(ForEachStatementSyntax node) => Enter(() => base.VisitForEachStatement(node));
        public override void VisitWhileStatement(WhileStatementSyntax node) => Enter(() => base.VisitWhileStatement(node));
        public override void VisitDoStatement(DoStatementSyntax node) => Enter(() => base.VisitDoStatement(node));
        public override void VisitTryStatement(TryStatementSyntax node) => Enter(() => base.VisitTryStatement(node));
        public override void VisitSwitchStatement(SwitchStatementSyntax node) => Enter(() => base.VisitSwitchStatement(node));
        public override void VisitUsingStatement(UsingStatementSyntax node) => Enter(() => base.VisitUsingStatement(node));

        public override void VisitMethodDeclaration(MethodDeclarationSyntax node) { }
        public override void VisitLocalFunctionStatement(LocalFunctionStatementSyntax node) { }
        public override void VisitClassDeclaration(ClassDeclarationSyntax node) { }
        public override void VisitStructDeclaration(StructDeclarationSyntax node) { }
    }

    // Same pitfall CcWalker.Compute avoids: Visit()ing the
    // BaseMethodDeclarationSyntax node itself immediately hits the walker's
    // own VisitMethodDeclaration boundary override (a no-op, there so a
    // nested method's nesting doesn't fold into its enclosing method's) and
    // stops before ever descending into the body. Must start from the body
    // (or expression-body), matching CcWalker.Compute's exact pattern.
    private static int MaxNestingLevel(BaseMethodDeclarationSyntax methodNode)
    {
        var walker = new NestingWalker();
        if (methodNode.Body is not null)
        {
            walker.Visit(methodNode.Body);
        }
        else if (methodNode is MethodDeclarationSyntax { ExpressionBody: { } expr })
        {
            walker.Visit(expr.Expression);
        }
        return walker.MaxDepth;
    }

    // A method is accessor-shaped if its entire body is exactly one
    // `return this.X;` or `this.X = <expr>;` statement - the explicit-
    // method-form analogue of ast_common.py's is_accessor_method. Most
    // idiomatic C# expresses getters/setters as properties instead (handled
    // separately, see WOC/NOAM below) - this only catches the rarer
    // explicit-method style, same as the Python heuristic catching Python's
    // occasional explicit get_x()/set_x() methods.
    private static bool IsAccessorShaped(BaseMethodDeclarationSyntax node)
    {
        if (node.Body is not { Statements.Count: 1 } body) return false;
        var stmt = body.Statements[0];
        if (stmt is ReturnStatementSyntax { Expression: MemberAccessExpressionSyntax ma }
            && ma.Expression.IsKind(SyntaxKind.ThisExpression))
        {
            return true;
        }
        if (stmt is ExpressionStatementSyntax { Expression: AssignmentExpressionSyntax assign }
            && assign.Left is MemberAccessExpressionSyntax lma
            && lma.Expression.IsKind(SyntaxKind.ThisExpression))
        {
            return true;
        }
        return false;
    }

    // WOC/NOAM adaptation, documented explicitly (not a silent Python
    // port): idiomatic C# expresses most getters/setters as properties, not
    // as classic getX()/setX() methods the way the smell literature's
    // originating languages (Java/C++) do - PropertyDeclarationSyntax
    // itself already means "this member is an accessor pair" the same way
    // is_accessor_method's structural check does for Python. So the
    // "public methods" population for WOC/NOAM here is public
    // BaseMethodDeclarationSyntax methods (excluding constructors) PLUS
    // public properties; NOAM counts every property (accessor by
    // definition) plus any explicit accessor-shaped method; WOC's
    // "functional" numerator excludes both.
    private static (double Woc, double Noam) WocNoam(ClassInfo cls)
    {
        var publicMethods = cls.Node.Members.OfType<BaseMethodDeclarationSyntax>()
            .Where(m => m.Modifiers.Any(SyntaxKind.PublicKeyword) && m is not ConstructorDeclarationSyntax)
            .ToList();
        var publicProperties = cls.Node.Members.OfType<PropertyDeclarationSyntax>()
            .Where(p => p.Modifiers.Any(SyntaxKind.PublicKeyword))
            .ToList();

        var totalPublic = publicMethods.Count + publicProperties.Count;
        if (totalPublic == 0) return (1.0, 0.0);

        var accessorMethods = publicMethods.Count(IsAccessorShaped);
        var noam = accessorMethods + publicProperties.Count;
        var functional = publicMethods.Count - accessorMethods;
        return ((double)functional / totalPublic, noam);
    }

    // Above SnapshotAnalyzer.CohesionSampleThreshold methods, computed
    // over a seeded random subsample instead of the full O(n^2) pairwise
    // scan - see SnapshotAnalyzer.SampleFieldSets(). TCC is already a
    // ratio (shared pairs / total pairs), so the subsample's own ratio is
    // a direct, unbiased estimate of the true value - no extrapolation
    // needed, unlike ComputeLcom's absolute-count version of this same
    // fix (SnapshotAnalyzer.cs).
    private static ClassSmellRow ClassSmellMetrics(ClassInfo cls, HashSet<string> knownFieldNames)
    {
        var full = SnapshotAnalyzer.FieldAccessSets(cls);
        var (fieldSets, tccSampled) = SnapshotAnalyzer.SampleFieldSets(full, cls.QualifiedName);
        var n = fieldSets.Count;
        double tcc;
        if (n < 2)
        {
            tcc = 1.0;
        }
        else
        {
            var totalPairs = n * (n - 1) / 2.0;
            var shared = 0;
            for (var i = 0; i < n; i++)
                for (var j = i + 1; j < n; j++)
                    if (fieldSets[i].Overlaps(fieldSets[j])) shared++;
            tcc = shared / totalPairs;
        }

        var atfdSet = new HashSet<(string, string)>();
        foreach (var m in cls.Node.Members.OfType<BaseMethodDeclarationSyntax>())
        {
            atfdSet.UnionWith(ForeignAccesses(m, knownFieldNames));
        }

        var (woc, noam) = WocNoam(cls);

        return new ClassSmellRow
        {
            Loc = cls.Loc,
            Wmc = cls.Methods.Sum(m => m.Cc),
            Tcc = tcc,
            TccSampled = tccSampled,
            Atfd = atfdSet.Count,
            Woc = woc,
            Nopa = cls.PublicFieldNames.Count,
            Noam = noam,
        };
    }

    private static MethodSmellRow MethodSmellMetrics(
        MethodInfo methodInfo, BaseMethodDeclarationSyntax node, double classLoc,
        HashSet<string> ownFieldAccessSet, HashSet<string> knownFieldNames)
    {
        var foreign = ForeignAccesses(node, knownFieldNames);
        var local = ownFieldAccessSet.Count;
        var foreignCount = foreign.Count;
        var total = local + foreignCount;
        var laa = total == 0 ? 1.0 : (double)local / total;

        return new MethodSmellRow
        {
            ClassLoc = classLoc,
            Loc = methodInfo.Loc,
            Cyclo = methodInfo.Cc,
            Atfd = foreignCount,
            Fdp = foreign.Select(f => f.Receiver).Distinct().Count(),
            Laa = laa,
            MaxNesting = MaxNestingLevel(node),
            Noav = AccessedVariableNames(node).Count,
        };
    }

    private static void DetectSmells(List<ClassSmellRow> classRows, List<MethodSmellRow> methodRows)
    {
        var wmcP75 = SnapshotAnalyzer.Percentile(classRows.Select(r => r.Wmc).ToList(), 0.75);
        var wmcP90 = SnapshotAnalyzer.Percentile(classRows.Select(r => r.Wmc).ToList(), 0.90);
        var tccP10 = SnapshotAnalyzer.Percentile(classRows.Select(r => r.Tcc).ToList(), 0.10);

        foreach (var r in classRows)
        {
            // God Class/Blob: WMC in TopValues(10%) AND TCC in
            // BottomValues(10%) AND ATFD > 1 - 10%/10%, not Marinescu's own
            // 25%/25% worked example, per PySmellDetection.md's empirically-
            // justified revision (re-checked on real C# data before trusting
            // it here too - see the batch-run validation log).
            r.IsGodClass = wmcP90.HasValue && r.Wmc >= wmcP90.Value
                && tccP10.HasValue && r.Tcc <= tccP10.Value
                && r.Atfd > 1;

            var fewMany = r.Nopa + r.Noam;
            r.IsDataClass = r.Woc < OneThird
                && (
                    (fewMany > Few && wmcP75.HasValue && r.Wmc < wmcP75.Value)
                    || (fewMany > Many && wmcP90.HasValue && r.Wmc < wmcP90.Value)
                );
        }

        var classLocP75 = SnapshotAnalyzer.Percentile(classRows.Select(r => r.Loc).ToList(), 0.75);
        var cycloP75 = SnapshotAnalyzer.Percentile(methodRows.Select(r => r.Cyclo).ToList(), 0.75);
        foreach (var r in methodRows)
        {
            r.IsFeatureEnvy = r.Atfd > Few && r.Laa < OneThird && r.Fdp <= Few;
            r.IsBrainMethod = classLocP75.HasValue && r.Loc > classLocP75.Value / 2
                && cycloP75.HasValue && r.Cyclo >= cycloP75.Value
                && r.MaxNesting >= Several
                && r.Noav > Many;
        }
    }
}
