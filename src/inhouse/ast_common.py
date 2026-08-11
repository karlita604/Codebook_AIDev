"""
Shared, from-scratch AST primitives for Python source: entity extraction
(module/class/method/function inventories) and per-function cyclomatic
complexity.

Built from scratch on the stdlib `ast` module (not `radon`) so every
counting rule is explicit and documented here, rather than inherited from a
third-party library's own undocumented conventions - see
Writing/InHouseTooling.md's "What's easy: OO metrics" section for why that
matters (this project needs to know exactly what's being counted to make a
meaningful comparison against DPy's real output).

Used by both the OO-metrics engine (py_metrics.py) and, later, the RQ3
entity tracker (Writing/RQ3_CodeTracking.md, Tool-RQ3) - one AST-walking
layer, not two.
"""

import ast
from dataclasses import dataclass, field

FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _span_loc(node):
    """LOC = end_lineno - lineno + 1 (span-based: includes blank/comment
    lines within the span). This undercounts a file's own top-line total
    the same way DPy/Designite's own class-LOC figures do (confirmed
    ~18-21% undercount for Designite, DESIGNITE_TASK.md's metrics table) -
    lines outside any class/function span (module imports, top-level
    constants) aren't attributed to anything by this figure alone."""
    end = getattr(node, "end_lineno", None) or node.lineno
    return end - node.lineno + 1


def _is_public(name):
    """Python convention: a single leading underscore marks non-public.
    Dunder methods (__init__, __repr__, ...) count as public - they're part
    of a class's real interface, not internal-only."""
    if name.startswith("__") and name.endswith("__"):
        return True
    return not name.startswith("_")


def _param_count(func_node, is_method):
    """Formal parameter count, excluding the implicit receiver
    (self/cls) for methods - matches the conventional PC definition DPy
    and Designite both report (a method that only takes `self` has PC=0,
    not 1)."""
    a = func_node.args
    n = (
        len(a.posonlyargs) + len(a.args) + len(a.kwonlyargs)
        + (1 if a.vararg else 0) + (1 if a.kwarg else 0)
    )
    if is_method and (a.posonlyargs or a.args):
        n -= 1
    return n


def _base_name(base_node):
    """Best-effort textual name for a base-class expression - handles the
    common `Base` and `module.Base` forms. Anything more dynamic
    (subscripted generics, computed expressions) falls back to a
    placeholder rather than crashing; DIT resolution treats that as an
    unresolvable (external) base, same as a name genuinely not defined in
    this snapshot."""
    if isinstance(base_node, ast.Name):
        return base_node.id
    if isinstance(base_node, ast.Attribute):
        return base_node.attr
    return None


@dataclass
class MethodEntity:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    node: ast.AST
    is_public: bool
    param_count: int

    @property
    def loc(self):
        return _span_loc(self.node)

    @property
    def cc(self):
        return cyclomatic_complexity(self.node)


@dataclass
class FunctionEntity:
    """Module-level function (not a class method)."""
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    node: ast.AST
    is_public: bool
    param_count: int

    @property
    def loc(self):
        return _span_loc(self.node)

    @property
    def cc(self):
        return cyclomatic_complexity(self.node)


@dataclass
class ClassEntity:
    name: str
    qualified_name: str
    lineno: int
    end_lineno: int
    node: ast.ClassDef
    is_public: bool
    bases: list = field(default_factory=list)  # base-class names, unresolved
    methods: list = field(default_factory=list)  # direct methods only
    field_names: list = field(default_factory=list)

    @property
    def loc(self):
        return _span_loc(self.node)


class _CCVisitor(ast.NodeVisitor):
    """McCabe cyclomatic complexity: base 1, +1 per independent decision
    point. Stops at nested def/class boundaries - a nested function or
    class gets its own separate CC, not folded into its enclosing
    function's count. Lambdas are NOT a boundary (they have no name/
    signature of their own to hang a separate entity off of), so a
    lambda's internal branching (e.g. a ternary inside it) still counts
    toward the enclosing function - matches how lizard/radon-style tools
    commonly treat lambdas."""

    def __init__(self):
        self.complexity = 1

    def visit_FunctionDef(self, node):
        pass

    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_ClassDef(self, node):
        pass

    def visit_If(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_For(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_AsyncFor(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_While(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_BoolOp(self, node):
        self.complexity += len(node.values) - 1
        self.generic_visit(node)

    def visit_IfExp(self, node):
        self.complexity += 1
        self.generic_visit(node)

    def visit_comprehension(self, node):
        self.complexity += len(node.ifs)
        self.generic_visit(node)

    def visit_match_case(self, node):
        self.complexity += 1
        self.generic_visit(node)


def cyclomatic_complexity(func_node):
    visitor = _CCVisitor()
    for stmt in func_node.body:
        visitor.visit(stmt)
    return visitor.complexity


def self_attribute_names(node, exclude=frozenset()):
    """Every `self.<name>`/`cls.<name>` attribute name referenced anywhere
    under `node`, excluding names in `exclude`. Deliberately does NOT try
    to distinguish a field *read* from a method *call* on the attribute
    (`self.name` vs. `self.speak()` look identical at the `ast.Attribute`
    level) - callers pass the class's own method names as `exclude` so a
    call like `self.speak()` isn't mistaken for a field named "speak".
    Shared by field collection (below) and py_metrics.py's LCOM
    computation, which needs the same per-method attribute set."""
    names = set()
    for n in ast.walk(node):
        if (
            isinstance(n, ast.Attribute)
            and isinstance(n.value, ast.Name)
            and n.value.id in ("self", "cls")
            and n.attr not in exclude
        ):
            names.add(n.attr)
    return names


def _collect_self_field_names(class_node):
    """Field names: class-body-level simple assignments/annotations, plus
    `self.<name> = ...`-style assignments found anywhere in any method
    body - the common Python pattern for instance fields, since Python has
    no separate field-declaration syntax the way C#/Java do. Excludes the
    class's own method names (see self_attribute_names) so a method call
    like `self.speak()` isn't counted as a field. Not fully precise either
    way (won't catch fields set via setattr/dynamic attribute names, and a
    field that happens to share a name with a method is still excluded) -
    a documented approximation, same spirit as the Fan-In/Fan-Out/DIT
    approximations below."""
    # Only this class's OWN directly-defined methods are excluded - a call
    # to an inherited method (e.g. `self.speak()` in a subclass whose
    # `speak` is defined on its base, not itself) is NOT recognized as a
    # method call here and gets counted as a field instead. No
    # cross-class method resolution is attempted (same scope boundary as
    # Fan-In/Fan-Out/DIT below) - a known, real source of NOF/LCOM
    # overcounting for subclasses that call inherited methods, not
    # silently assumed away.
    method_names = {
        item.name for item in class_node.body if isinstance(item, FUNC_TYPES)
    }
    names = set()
    for stmt in class_node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(
            stmt.target, ast.Name
        ):
            names.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(stmt, FUNC_TYPES):
            names |= self_attribute_names(stmt, exclude=method_names)
    return sorted(names)


def _build_method_entity(node, class_qualname):
    return MethodEntity(
        name=node.name,
        qualified_name=f"{class_qualname}.{node.name}",
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", node.lineno),
        node=node,
        is_public=_is_public(node.name),
        param_count=_param_count(node, is_method=True),
    )


def _build_class_entity(node, module_qualname):
    qualname = f"{module_qualname}.{node.name}"
    methods = [
        _build_method_entity(item, qualname)
        for item in node.body
        if isinstance(item, FUNC_TYPES)
    ]
    bases = [b for b in (_base_name(n) for n in node.bases) if b is not None]
    return ClassEntity(
        name=node.name,
        qualified_name=qualname,
        lineno=node.lineno,
        end_lineno=getattr(node, "end_lineno", node.lineno),
        node=node,
        is_public=_is_public(node.name),
        bases=bases,
        methods=methods,
        field_names=_collect_self_field_names(node),
    )


def extract_classes(tree, module_qualname):
    """Top-level classes only - nested classes are a documented gap, not
    something the confirmed DPy/Designite schema (long_analysis.py's
    parse_tool_output docstring) distinguishes specially either."""
    return [
        _build_class_entity(node, module_qualname)
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    ]


def extract_functions(tree, module_qualname):
    """Module-level functions only - methods are collected via
    extract_classes/ClassEntity.methods instead."""
    return [
        FunctionEntity(
            name=node.name,
            qualified_name=f"{module_qualname}.{node.name}",
            lineno=node.lineno,
            end_lineno=getattr(node, "end_lineno", node.lineno),
            node=node,
            is_public=_is_public(node.name),
            param_count=_param_count(node, is_method=False),
        )
        for node in tree.body
        if isinstance(node, FUNC_TYPES)
    ]


def module_qualname(relative_path):
    """Dotted module name from a snapshot-relative POSIX path, e.g.
    'pkg/sub/mod.py' -> 'pkg.sub.mod', 'pkg/__init__.py' -> 'pkg'."""
    parts = list(relative_path.parts)
    if parts and parts[-1] == "__init__.py":
        parts = parts[:-1]
    elif parts:
        parts[-1] = parts[-1][:-3] if parts[-1].endswith(".py") else parts[-1]
    return ".".join(parts) if parts else relative_path.stem
