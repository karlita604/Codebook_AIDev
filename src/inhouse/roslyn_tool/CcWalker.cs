using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

namespace RoslynMetrics;

// McCabe cyclomatic complexity, from scratch - same reasoning as
// ast_common.py's _CCVisitor: exact control over what's counted, not
// whatever a third-party analyzer counts internally, so the two languages'
// CC definitions are directly comparable to each other (and to DPy/Designite
// via validate_against_pilot.py's agreement report).
//
// Base 1, +1 per independent decision point: if/for/foreach/while/do,
// catch clauses, switch-statement case labels, switch-expression arms,
// ternary (?:), each && / || connective. Stops at nested method/local-
// function/type-declaration boundaries - a nested method gets its own CC,
// not folded into its enclosing method's. Lambdas and anonymous methods are
// NOT a boundary (matches ast_common.py's Lambda treatment) - their internal
// branching still counts toward the enclosing method, since they have no
// name/signature of their own to hang a separate entity off of.
public sealed class CcWalker : CSharpSyntaxWalker
{
    public int Complexity { get; private set; } = 1;

    public static int Compute(BaseMethodDeclarationSyntax method)
    {
        var walker = new CcWalker();
        if (method.Body is not null)
        {
            walker.Visit(method.Body);
        }
        else if (method is MethodDeclarationSyntax { ExpressionBody: { } expr })
        {
            walker.Visit(expr.Expression);
        }
        return walker.Complexity;
    }

    public override void VisitIfStatement(IfStatementSyntax node)
    { Complexity++; base.VisitIfStatement(node); }

    public override void VisitForStatement(ForStatementSyntax node)
    { Complexity++; base.VisitForStatement(node); }

    public override void VisitForEachStatement(ForEachStatementSyntax node)
    { Complexity++; base.VisitForEachStatement(node); }

    public override void VisitWhileStatement(WhileStatementSyntax node)
    { Complexity++; base.VisitWhileStatement(node); }

    public override void VisitDoStatement(DoStatementSyntax node)
    { Complexity++; base.VisitDoStatement(node); }

    public override void VisitCatchClause(CatchClauseSyntax node)
    { Complexity++; base.VisitCatchClause(node); }

    public override void VisitCaseSwitchLabel(CaseSwitchLabelSyntax node)
    { Complexity++; base.VisitCaseSwitchLabel(node); }

    public override void VisitSwitchExpressionArm(SwitchExpressionArmSyntax node)
    { Complexity++; base.VisitSwitchExpressionArm(node); }

    public override void VisitConditionalExpression(ConditionalExpressionSyntax node)
    { Complexity++; base.VisitConditionalExpression(node); }

    public override void VisitBinaryExpression(BinaryExpressionSyntax node)
    {
        if (node.IsKind(SyntaxKind.LogicalAndExpression) || node.IsKind(SyntaxKind.LogicalOrExpression))
        {
            Complexity++;
        }
        base.VisitBinaryExpression(node);
    }

    // Boundaries: each gets its own separate CC, not folded into this walk.
    public override void VisitMethodDeclaration(MethodDeclarationSyntax node) { }
    public override void VisitLocalFunctionStatement(LocalFunctionStatementSyntax node) { }
    public override void VisitClassDeclaration(ClassDeclarationSyntax node) { }
    public override void VisitStructDeclaration(StructDeclarationSyntax node) { }
}
