- [ ]  TODO: rename intervention point

### Motivation

We are witnessing a fundamental shift in how software gets written. AI tools began with integration at the periphery of the work; suggesting snippets within the developer's workflow, while humans retained authorship and full integration decision control. This has been rapidly shifting to fully autonomous and complete generation for repository-level PRs at scale. This has raised an entire empirical research domain of these activities at scale.

The core premise of using pull requests and code review as a system is to improve the software system internal code collaboratively with multiple points to catch bugs. Prior to agents being introduced on popular platforms and larger well sampled projects, we saw a steady, though far from perfect, system of back and forth, from refactorings to code review.

- RQ1: Investigation of repository standings PRE and POST intervention point
    
    
- RQ2: Longitudinal Study
    
    **How do we track a piece of code?**
    Method chosen: Lanza & Marinescu "Detection Strategies" (Marinescu, ICSM 2004; Lanza & Marinescu, 2006) — not Fowler's informal catalog, not an attempt to reverse-engineer DPy/Designite's closed rule sets.
Method chosen: Lanza & Marinescu "Detection Strategies" (Marinescu, ICSM 2004; Lanza & Marinescu, 2006) — not Fowler's informal catalog, not an attempt to reverse-engineer DPy/Designite's closed rule sets.
Implemented (v1, four strategies), in src/inhouse/py_smells.py (branch-only, 285 lines):
God Class/Blob and Data Class (class-level) → pooled as design_smell_count/design_smell_density_per_kloc
Feature Envy and Brain Method (method-level) → pooled as implementation_smell_count/implementation_smell_density_per_kloc
Not attempted: Shotgun Surgery (needs multi-commit history, out of scope for v1).