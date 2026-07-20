https://designite-tools.com/docs/dpy.html

@inproceedings{Sharma2016,
  author = {Sharma, Tushar and Mishra, Pratibha and Tiwari, Rohit},
  title = {Designite: A Software Design Quality Assessment Tool},
  year = {2016},
  isbn = {9781450341530},
  publisher = {Association for Computing Machinery},
  address = {New York, NY, USA},
  url = {https://doi.org/10.1145/2896935.2896938},
  booktitle = {Proceedings of the 1st International Workshop on Bringing Architectural Design Thinking into Developers' Daily Activities},
  pages = {1–4},
  numpages = {4},
  series = {BRIDGE '16}
}

DPy (pronounced as /di:pai/) is a Python code quality assessment tool that detects architecture, design, implementation, and machine learning-specific smells, provides object-oriented metrics, and helps identify quality issues to improve structural health and support faster, more reliable code delivery.

We select DPy because it is widely used in empirical software engineering research (e.g., [27, 47]). As it performs static analysis directly on source code, it ensures
consistent metric extraction across heterogeneous projects without requiring build configuration. The tool computes class- and method-level metrics commonly used in software quality assessment [], including size (Lines of Code), complexity (Cyclomatic Complexity, Weighted Methods perClass), coupling (Fan-in, Fan-out), cohesion (Lack of Cohesion in Methods), and inheritance depth (Depth of Inheritance Tree). DesigniteJava also detects 27 design and implementation smells (e.g.,
Long Method, Complex Method, Cyclic Dependancy) enabling multi-perspective analysis of code maintainability.

We evaluate the before and after changes (\delta = after - before) in internal code quality metrics detected by DPy and Designite. These changes are aggregated aong two dimensions 1) the abstraction level of the refactoring instance (low, medium, high) and 2) the purpose category



## Artifacts
*(design and implementation) smell count per commit (before and after) 