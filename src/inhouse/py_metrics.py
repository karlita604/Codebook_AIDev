"""
Python OO-metrics engine - class/method/module-level metrics computed
from scratch via ast_common's AST primitives.

Output row matches the schema long_analysis.py's parse_tool_output()
confirmed against real DPy output (see that function's docstring, and
_parse_dpy_output() at long_analysis.py:478): total_loc is the sum of
per-MODULE line counts (not summed class LOC - DPy's own
_class_module_metrics.csv keeps module rows, Class column empty, separate
from class rows, and pools total_loc from those), n_classes/n_methods are
row counts, and the four percentile columns are pandas .quantile() over the
same per-class/per-method value lists DPy's own _pctl() helper uses - same
method, so percentiles are directly comparable. This lets our output pool
into the same table as results/analysis/07-29-pooled-structural-metrics.csv
with no adapter step (mirrors the DPy/Designite cross-language pooling that
turned out not to need one either - see ProjectStatus.md's "Schema note").

Columns beyond DPy's pooled schema (wmc_p50/p90, lcom_p50/p90, dit_p50/p90,
fan_in_p50/p90, fan_out_p50/p90, pc_p50/p90) are real CK-suite metrics this
engine also computes per class/method (matching DPy's own
_class_module_metrics.csv columns) but that DPy's *pooled* row never
surfaced in the first place - additive, not a divergence to validate
against.

Smell columns are deliberately absent - out of scope per
Writing/InHouseTooling.md's design decision (OO metrics only, this phase).

Fan-In/Fan-Out/DIT are heuristic, whole-snapshot-scoped approximations (no
real import-alias resolution or type inference) - see the docstrings on
_referenced_class_names/_dit in this file for exactly what's being counted
and what's not.
"""

import ast
from pathlib import Path

import pandas as pd

import ast_common


def _read_module(path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    return text, tree


def _physical_loc(text):
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _parse_snapshot(snapshot_dir):
    """Parse every .py file in a materialized snapshot into per-module
    records. Files that fail to read or fail to parse (real syntax errors
    turn up in old commits, e.g. Python 2-only syntax, or files this
    environment's encoding handling can't cleanly decode) are skipped and
    counted in n_parse_errors, not silently dropped from the totals without
    a trace."""
    modules = []
    n_parse_errors = 0
    for py_file in sorted(snapshot_dir.rglob("*.py")):
        parsed = _read_module(py_file)
        if parsed is None:
            n_parse_errors += 1
            continue
        text, tree = parsed
        relpath = py_file.relative_to(snapshot_dir)
        qualname = ast_common.module_qualname(relpath)
        modules.append({
            "relpath": relpath,
            "qualname": qualname,
            "physical_loc": _physical_loc(text),
            "classes": ast_common.extract_classes(tree, qualname),
            "functions": ast_common.extract_functions(tree, qualname),
        })
    return modules, n_parse_errors


def _build_class_index(modules):
    """Bare class name -> ClassEntity, across the whole snapshot. Ambiguous
    when two classes share a name across different modules - keeps
    whichever is encountered first (files walked in sorted-path order, so
    at least deterministic run-to-run). Documented approximation, same
    class of limitation as the resolution functions below."""
    index = {}
    for mod in modules:
        for cls in mod["classes"]:
            index.setdefault(cls.name, cls)
    return index


def _dit(cls, class_index, _seen=None):
    """Depth of Inheritance Tree: number of ancestor classes resolvable
    within this snapshot. A class with no resolvable base has DIT=0 (not
    1, i.e. not counting an implicit `object` root) - a base outside the
    snapshot (stdlib, a third-party dependency, e.g. `Exception` or a
    framework base class) can't be resolved and is treated as a DIT
    boundary, not an error. `_seen` guards a base-resolution cycle (would
    indicate a bug elsewhere, not real Python semantics) - fail safe
    instead of infinite recursion."""
    if _seen is None:
        _seen = set()
    if cls.qualified_name in _seen or not cls.bases:
        return 0
    _seen = _seen | {cls.qualified_name}
    best = 0
    for base_name in cls.bases:
        base_cls = class_index.get(base_name)
        if base_cls is not None:
            best = max(best, 1 + _dit(base_cls, class_index, _seen))
    return best


def _referenced_class_names(method_node, class_names):
    """Known (in-snapshot) class names textually referenced inside a
    method body - a bare Name matching a known class, or an Attribute
    whose .attr matches one (covers `module.Class`-style access). This is
    textual/heuristic, NOT real type resolution: no import-alias
    resolution, no way to distinguish a locally-shadowed variable of the
    same name from the real class. Same category of approximation
    Designite's own chunk-boundary Fan-In/Fan-Out already carries
    (DESIGNITE_TASK.md's metrics table) - documented, not silently
    assumed exact."""
    found = set()
    for node in ast.walk(method_node):
        if isinstance(node, ast.Name) and node.id in class_names:
            found.add(node.id)
        elif isinstance(node, ast.Attribute) and node.attr in class_names:
            found.add(node.attr)
    return found


def _fan_in_fan_out(class_index):
    class_names = set(class_index.keys())
    fan_out = {}
    for cls in class_index.values():
        refs = set(cls.bases) & class_names
        for m in cls.methods:
            refs |= _referenced_class_names(m.node, class_names)
        refs.discard(cls.name)
        fan_out[cls.name] = refs

    fan_in = {name: 0 for name in class_names}
    for name, refs in fan_out.items():
        for ref in refs:
            fan_in[ref] = fan_in.get(ref, 0) + 1

    return {n: len(r) for n, r in fan_out.items()}, fan_in


def _lcom(cls):
    """Chidamber & Kemerer's original LCOM (LCOM1): for every pair of
    methods, P = pairs sharing no field access, Q = pairs sharing at least
    one field. LCOM = max(0, P - Q). Field-access set per method comes from
    ast_common.self_attribute_names(), excluding the class's own method
    names so a call like `self.speak()` isn't mistaken for a shared field
    - the same exclusion _collect_self_field_names uses, applied per-method
    here instead of per-class."""
    methods = cls.methods
    if len(methods) < 2:
        return 0
    method_names = {m.name for m in methods}
    field_sets = [
        ast_common.self_attribute_names(m.node, exclude=method_names)
        for m in methods
    ]

    p = q = 0
    for i in range(len(field_sets)):
        for j in range(i + 1, len(field_sets)):
            if field_sets[i] & field_sets[j]:
                q += 1
            else:
                p += 1
    return max(0, p - q)


def class_detail_rows(modules, class_index, fan_out, fan_in):
    """Per-class metric rows - not pooled into analyze_snapshot()'s summary
    row (matching DPy's pooled schema, which doesn't surface these either),
    but useful on their own (e.g. a future per-class time series) and
    needed by validate_against_pilot.py if a class-level comparison is ever
    wanted. Kept as a separate function so analyze_snapshot() stays a thin
    aggregator."""
    rows = []
    for mod in modules:
        for cls in mod["classes"]:
            wmc = sum(m.cc for m in cls.methods)
            rows.append({
                "module": mod["qualname"],
                "class_name": cls.qualified_name,
                "loc": cls.loc,
                "nom": len(cls.methods),
                "nopm": sum(1 for m in cls.methods if m.is_public),
                "nof": len(cls.field_names),
                "nopf": sum(
                    1 for f in cls.field_names if not f.startswith("_")
                ),
                "wmc": wmc,
                "lcom": _lcom(cls),
                "dit": _dit(cls, class_index),
                "fan_in": fan_in.get(cls.name, 0),
                "fan_out": fan_out.get(cls.name, 0),
            })
    return rows


def analyze_snapshot(snapshot_dir):
    """Analyze one materialized Python snapshot directory, returning a
    dict shaped to match parse_tool_output()'s DPy row (see this module's
    docstring) plus additive CK-suite columns DPy computes per-class but
    doesn't pool. `status` is 'ok' or an error string, same convention
    process_row() uses in long_analysis.py."""
    snapshot_dir = Path(snapshot_dir)
    modules, n_parse_errors = _parse_snapshot(snapshot_dir)

    class_index = _build_class_index(modules)
    fan_out, fan_in = _fan_in_fan_out(class_index)

    all_classes = [c for mod in modules for c in mod["classes"]]
    all_methods = [m for c in all_classes for m in c.methods]
    all_functions = [f for mod in modules for f in mod["functions"]]
    # DPy's _function_metrics.csv covers both class methods and top-level
    # functions in one table (long_analysis.py:495's n_methods = len of
    # that whole df) - mirrored here as one combined "callables" list.
    all_callables = all_methods + all_functions

    total_loc = sum(mod["physical_loc"] for mod in modules)

    def _series(values):
        return pd.Series(values, dtype=float)

    class_loc = _series([c.loc for c in all_classes])
    callable_loc = _series([c.loc for c in all_callables])
    callable_cc = _series([c.cc for c in all_callables])
    callable_pc = _series([c.param_count for c in all_callables])
    class_wmc = _series([sum(m.cc for m in c.methods) for c in all_classes])
    class_lcom = _series([_lcom(c) for c in all_classes])
    class_dit = _series([_dit(c, class_index) for c in all_classes])
    class_fan_in = _series([fan_in.get(c.name, 0) for c in all_classes])
    class_fan_out = _series([fan_out.get(c.name, 0) for c in all_classes])

    def _pctl(series, q):
        return None if series.empty else float(series.quantile(q))

    return {
        "total_loc": total_loc,
        "n_files": len(modules),
        "n_parse_errors": n_parse_errors,
        "n_classes": len(all_classes),
        "n_methods": len(all_callables),
        "class_loc_p50": _pctl(class_loc, 0.5),
        "class_loc_p90": _pctl(class_loc, 0.9),
        "method_loc_p50": _pctl(callable_loc, 0.5),
        "method_loc_p90": _pctl(callable_loc, 0.9),
        "cyclomatic_complexity_p50": _pctl(callable_cc, 0.5),
        "cyclomatic_complexity_p90": _pctl(callable_cc, 0.9),
        "pc_p50": _pctl(callable_pc, 0.5),
        "pc_p90": _pctl(callable_pc, 0.9),
        "wmc_p50": _pctl(class_wmc, 0.5),
        "wmc_p90": _pctl(class_wmc, 0.9),
        "lcom_p50": _pctl(class_lcom, 0.5),
        "lcom_p90": _pctl(class_lcom, 0.9),
        "dit_p50": _pctl(class_dit, 0.5),
        "dit_p90": _pctl(class_dit, 0.9),
        "fan_in_p50": _pctl(class_fan_in, 0.5),
        "fan_in_p90": _pctl(class_fan_in, 0.9),
        "fan_out_p50": _pctl(class_fan_out, 0.5),
        "fan_out_p90": _pctl(class_fan_out, 0.9),
        "status": "ok",
    }
