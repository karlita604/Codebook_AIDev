"""
Python smell-detection engine - Lanza & Marinescu "Detection Strategies"
(Marinescu, "Detection Strategies: Metrics-Based Rules for Detecting
Design Flaws," ICSM 2004; refined in Lanza & Marinescu, "Object-Oriented
Metrics in Practice," 2006), implemented from the published formulas, not
reverse-engineered from DPy/Designite's closed catalogs (those stay
out of scope, per Writing/InHouseTooling.md's "What's hard: smell
detection" section). Full method writeup, formula provenance, and
threshold rationale: Writing/PySmellDetection.md.

Four detection strategies (v1): God Class/Blob and Data Class (class-level),
Feature Envy and Brain Method (method-level, class methods only - both
strategies are inherently about a method's data relationship to its own
class, which a bare module-level function doesn't have). Built on
ast_common.py's shared AST primitives; reuses py_metrics.py's own
snapshot-parsing/class-indexing (_parse_snapshot/_build_class_index)
rather than duplicating it.

Threshold philosophy: fixed literature constants (ONE_THIRD/FEW/MANY/
SEVERAL) are used verbatim; "high"/"very high" magnitude thresholds (WMC,
CYCLO, class LOC) are computed as percentiles over THIS run's own class/
method population rather than importing the book's Java-2006-corpus
absolute numbers (e.g. WMC>=47) unmodified onto Python code - see
Writing/PySmellDetection.md's "The method, precisely" section for why.

Output pools into design_smell_count/design_smell_density_per_kloc
(God Class + Data Class) and implementation_smell_count/
implementation_smell_density_per_kloc (Feature Envy + Brain Method) -
bucket *names* match Designite's DesignSmells/ImpSmells split for pooling
convenience; bucket *contents* are independently sourced, not a
reproduction of Designite's specific rules.
"""

from itertools import combinations
from pathlib import Path

import pandas as pd

import ast_common
from py_metrics import _build_class_index, _parse_snapshot

ONE_THIRD = 1 / 3
FEW = 5
MANY = 7
SEVERAL = 3


def _known_field_names(class_index):
    names = set()
    for cls in class_index.values():
        names.update(cls.field_names)
    return names


def _field_sets(cls):
    """Per-method self-field-access sets, own method names excluded - the
    same inputs py_metrics.py's _lcom builds (self_attribute_names), reused
    here for TCC instead of LCOM's max(0, p-q) aggregation."""
    method_names = {m.name for m in cls.methods}
    return [
        ast_common.self_attribute_names(m.node, exclude=method_names)
        for m in cls.methods
    ]


def _tcc(cls):
    """Tight Class Cohesion: fraction of method pairs that directly share
    access to >=1 of the class's own fields. Fewer than 2 methods has no
    pairs to share anything - treated as maximally cohesive (1.0), which
    keeps a 0/1-method class out of God Class's low-TCC filter rather than
    dividing by zero.

    Above ast_common.COHESION_SAMPLE_THRESHOLD methods, computed over a
    seeded random subsample instead of the full O(n^2) pairwise scan -
    see ast_common.sample_field_sets()'s docstring for why (a confirmed
    ~20-minute stall on azure-sdk-for-python's largest generated-file
    classes). TCC is already a ratio (shared pairs / total pairs), so the
    subsample's own ratio is a direct, unbiased estimate of the true
    value - unlike py_metrics.py's _lcom (a difference of two large
    counts, where the equivalent rescale-and-subtract approach was tried
    and rejected - see that function's docstring for the ~98%-error case
    that ruled it out), TCC needs no such treatment; the sample ratio IS
    the estimate. Returns (tcc, sampled) -
    callers that pool this into a row should record `sampled` alongside
    it (see analyze_snapshot()'s n_tcc_sampled column)."""
    field_sets = _field_sets(cls)
    field_sets, sampled = ast_common.sample_field_sets(
        field_sets, seed_key=cls.qualified_name
    )
    n = len(field_sets)
    if n < 2:
        return 1.0, sampled
    total_pairs = n * (n - 1) / 2
    shared = sum(1 for a, b in combinations(field_sets, 2) if a & b)
    return shared / total_pairs, sampled


def _class_atfd(cls, known_field_names):
    accesses = set()
    for m in cls.methods:
        accesses.update(
            ast_common.foreign_attribute_accesses(m.node, known_field_names)
        )
    return len(accesses)


def _woc(cls):
    """Weight Of a Class: functional (non-accessor, non-constructor)
    public methods / all public methods. No public methods at all is
    treated as 1.0 (nothing "non-functional" to flag) rather than 0.0,
    which would otherwise trivially satisfy Data Class's WOC < ONE_THIRD
    filter on an empty/near-empty class."""
    public_methods = [m for m in cls.methods if m.is_public]
    if not public_methods:
        return 1.0
    functional = [
        m for m in public_methods
        if m.name not in ("__init__", "__new__")
        and not ast_common.is_accessor_method(m.node)
    ]
    return len(functional) / len(public_methods)


def _noam(cls):
    return sum(1 for m in cls.methods if ast_common.is_accessor_method(m.node))


def _class_smell_metrics(cls, known_field_names):
    tcc, tcc_sampled = _tcc(cls)
    return {
        "class_name": cls.qualified_name,
        "loc": cls.loc,
        "wmc": sum(m.cc for m in cls.methods),
        "tcc": tcc,
        "tcc_sampled": tcc_sampled,
        "atfd": _class_atfd(cls, known_field_names),
        "woc": _woc(cls),
        "nopa": sum(1 for f in cls.field_names if not f.startswith("_")),
        "noam": _noam(cls),
    }


def _method_smell_metrics(method, class_loc, known_field_names, own_method_names):
    accesses = ast_common.foreign_attribute_accesses(
        method.node, known_field_names
    )
    local = len(
        ast_common.self_attribute_names(method.node, exclude=own_method_names)
    )
    foreign = len(set(accesses))
    total = local + foreign
    # No attribute access at all (local or foreign) => nothing to be
    # "envious" of - LAA=1.0 keeps such a method out of Feature Envy's
    # low-LAA filter instead of a 0/0 division.
    laa = 1.0 if total == 0 else local / total
    return {
        "method_name": method.qualified_name,
        "class_loc": class_loc,
        "loc": method.loc,
        "cyclo": method.cc,
        "atfd": foreign,
        "fdp": len({receiver for receiver, _attr in accesses}),
        "laa": laa,
        "maxnesting": ast_common.max_nesting_level(method.node),
        "noav": len(ast_common.accessed_variable_names(method.node)),
    }


def _percentile(values, q):
    s = pd.Series(values, dtype=float)
    return None if s.empty else float(s.quantile(q))


def detect_smells(class_rows, method_rows):
    """Flags each class/method row in place (adds boolean smell columns),
    using percentile thresholds computed from THIS run's own population -
    see this module's docstring and Writing/PySmellDetection.md for why."""
    wmc_values = [r["wmc"] for r in class_rows]
    wmc_p75 = _percentile(wmc_values, 0.75)
    wmc_p90 = _percentile(wmc_values, 0.90)
    tcc_p10 = _percentile([r["tcc"] for r in class_rows], 0.10)

    for r in class_rows:
        # God Class/Blob: WMC in TopValues(10%) AND TCC in
        # BottomValues(10%) AND ATFD > 1. Marinescu's own worked example
        # (2004, Eq. 1) used TopValues(25%)/BottomValues(25%) - his own
        # text calls that "a simplistic approach ... for now", not a
        # validated constant. Tightened to 10%/10% here (2026-08-11,
        # decision logged in Writing/PySmellDetection.md) after the first
        # full batch run measured an 11.7% pooled flag rate - confirmed
        # empirically as WMC/TCC being strongly anti-correlated in real
        # code (Spearman r -0.53 to -0.82 across 3 sampled snapshots), not
        # a bug: two independent ~25% filters intersect far above the
        # naive 6.25% independence estimate when the two metrics move
        # together. Reuses wmc_p90 (already computed below for Data
        # Class's VERY_HIGH tier) rather than a separate WMC threshold -
        # same numeric value, no new computation needed.
        r["is_god_class"] = bool(
            wmc_p90 is not None and r["wmc"] >= wmc_p90
            and tcc_p10 is not None and r["tcc"] <= tcc_p10
            and r["atfd"] > 1
        )
        # Data Class (Lanza & Marinescu 2006): WOC < ONE_THIRD AND
        # ((NOPA+NOAM > FEW AND WMC < HIGH) OR (NOPA+NOAM > MANY AND
        # WMC < VERY_HIGH)).
        few_many = r["nopa"] + r["noam"]
        r["is_data_class"] = bool(
            r["woc"] < ONE_THIRD
            and (
                (few_many > FEW and wmc_p75 is not None and r["wmc"] < wmc_p75)
                or (
                    few_many > MANY
                    and wmc_p90 is not None and r["wmc"] < wmc_p90
                )
            )
        )

    class_loc_p75 = _percentile([r["loc"] for r in class_rows], 0.75)
    cyclo_p75 = _percentile([r["cyclo"] for r in method_rows], 0.75)
    for r in method_rows:
        # Feature Envy (Lanza & Marinescu 2006): ATFD > FEW AND
        # LAA < ONE_THIRD AND FDP <= FEW.
        r["is_feature_envy"] = bool(
            r["atfd"] > FEW and r["laa"] < ONE_THIRD and r["fdp"] <= FEW
        )
        # Brain Method (Lanza & Marinescu 2006): LOC > HIGH(class LOC)/2
        # AND CYCLO >= HIGH(CYCLO) AND MAXNESTING >= SEVERAL AND
        # NOAV > MANY.
        r["is_brain_method"] = bool(
            class_loc_p75 is not None and r["loc"] > class_loc_p75 / 2
            and cyclo_p75 is not None and r["cyclo"] >= cyclo_p75
            and r["maxnesting"] >= SEVERAL
            and r["noav"] > MANY
        )
    return class_rows, method_rows


def _analyze(snapshot_dir):
    snapshot_dir = Path(snapshot_dir)
    modules, n_parse_errors = _parse_snapshot(snapshot_dir)
    class_index = _build_class_index(modules)
    known_fields = _known_field_names(class_index)

    all_classes = [c for mod in modules for c in mod["classes"]]
    class_rows = [_class_smell_metrics(c, known_fields) for c in all_classes]

    method_rows = []
    for cls in all_classes:
        own_method_names = {m.name for m in cls.methods}
        for m in cls.methods:
            method_rows.append(_method_smell_metrics(
                m, cls.loc, known_fields, own_method_names,
            ))

    class_rows, method_rows = detect_smells(class_rows, method_rows)
    total_loc = sum(mod["physical_loc"] for mod in modules)
    return modules, n_parse_errors, all_classes, class_rows, method_rows, total_loc


def smell_detail_rows(snapshot_dir):
    """Per-class/per-method smell rows for inspection - not pooled into
    analyze_snapshot()'s summary row, mirrors py_metrics.py's
    class_detail_rows() being kept separate from its own analyze_snapshot()."""
    _, _, _, class_rows, method_rows, _ = _analyze(snapshot_dir)
    return class_rows, method_rows


def analyze_snapshot(snapshot_dir):
    """Analyze one materialized Python snapshot directory, returning a
    summary dict shaped to pool alongside py_metrics.py's/DPy's/
    Designite's output (same (repo_id, track, target_date, commit_sha)
    join keys, added by the caller - see pool_inhouse_smells.py)."""
    modules, n_parse_errors, all_classes, class_rows, method_rows, total_loc = (
        _analyze(snapshot_dir)
    )

    n_god_class = sum(1 for r in class_rows if r["is_god_class"])
    n_data_class = sum(1 for r in class_rows if r["is_data_class"])
    n_feature_envy = sum(1 for r in method_rows if r["is_feature_envy"])
    n_brain_method = sum(1 for r in method_rows if r["is_brain_method"])
    n_tcc_sampled = sum(1 for r in class_rows if r["tcc_sampled"])
    design_smell_count = n_god_class + n_data_class
    implementation_smell_count = n_feature_envy + n_brain_method
    kloc = total_loc / 1000 if total_loc else None

    return {
        "total_loc": total_loc,
        "n_files": len(modules),
        "n_parse_errors": n_parse_errors,
        "n_classes": len(all_classes),
        "n_methods": len(method_rows),
        "n_god_class": n_god_class,
        "n_data_class": n_data_class,
        "n_feature_envy": n_feature_envy,
        "n_brain_method": n_brain_method,
        # How many classes' TCC (God Class's cohesion filter) was
        # estimated from a seeded sample instead of the full pairwise
        # computation - see ast_common.sample_field_sets(). Near-always 0;
        # >0 flags a snapshot with an exceptionally large class, worth a
        # second look rather than trusting God Class's flag rate blindly.
        "n_tcc_sampled": n_tcc_sampled,
        "design_smell_count": design_smell_count,
        "design_smell_density_per_kloc": (
            design_smell_count / kloc if kloc else None
        ),
        "implementation_smell_count": implementation_smell_count,
        "implementation_smell_density_per_kloc": (
            implementation_smell_count / kloc if kloc else None
        ),
        "status": "ok",
    }
