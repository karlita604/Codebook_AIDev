## Related Work

### 1. Agentic Software Development

**1. Li, Zhang & Hassan (2025) — "The Rise of AI Teammates in Software Engineering (SE) 3.0: How Autonomous Coding Agents Are Reshaping Software Engineering" (arXiv:2507.15003).** Arguably the foundational paper for this research area, introducing both the "SE 3.0" framing and the AIDev dataset that nearly every subsequent study in this review builds on. AIDev is the first large-scale capture of how autonomous coding agents operate in real-world projects, spanning over 456,000 pull requests by five leading agents — OpenAI Codex, Devin, GitHub Copilot, Cursor, and Claude Code — across 61,000 repositories and 47,000 developers. The authors argue that agents have moved from autocomplete-style assistance to being genuine "teammates" that initiate PRs and participate in feedback loops. Two findings stand out for workflow design: although agents often outperform humans in time-to-merge speed, their PRs are accepted less frequently, revealing a trust and utility gap; and while agents massively accelerate submission — one developer submitted as many PRs in three days as in the previous three years — agentic PRs are structurally simpler by code-complexity metrics. The paper explicitly positions itself against synthetic benchmarks, arguing that real-world PR data answers questions that benchmarks like SWE-bench cannot.

https://arxiv.org/abs/2507.15003

references\2507.15003v1.pdf

```bibtex
@misc{li2025riseaiteammatessoftware,
      title={The Rise of AI Teammates in Software Engineering (SE) 3.0: How Autonomous Coding Agents Are Reshaping Software Engineering}, 
      author={Hao Li and Haoxiang Zhang and Ahmed E. Hassan},
      year={2025},
      eprint={2507.15003},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2507.15003}, 
}
```

**2. Jimenez et al. (2024) — "SWE-bench: Can Language Models Resolve Real-World GitHub Issues?" (ICLR 2024).** SWE-bench is the canonical evaluation framework connecting the benchmark world to the PR world, and it's essential context for understanding why agents submit PRs at all. The benchmark sources task instances from real Python repositories by linking GitHub issues to the merged pull requests that resolved them; given the issue text and a codebase snapshot, models must generate a patch that is then evaluated against real tests. Resolving these issues frequently requires coordinating changes across multiple functions, classes, and files, processing very long contexts, and reasoning well beyond traditional code generation — and at publication, the best model (Claude 2) solved only 1.96% of issues. That humbling baseline (now vastly exceeded by agent scaffolds) frames the whole subsequent literature: benchmark scores rose dramatically, yet the field studies below show real-world merge rates still lag human PRs, which is precisely the "benchmark-to-deployment gap" that motivates PR-level research.

https://proceedings.iclr.cc/paper_files/paper/2024/file/edac78c3e300629acfe6cbe9ca88fb84-Paper-Conference.pdf

references\ICLR-2024-swe-bench-can-language-models-resolve-real-world-github-issues-Paper-Conference.pdf

```bibtex
@inproceedings{ICLR2024_edac78c3,
 author = {Jimenez, Carlos E and Yang, John and Wettig, Alexander and Yao, Shunyu and Pei, Kexin and Press, Ofir and Narasimhan, Karthik},
 booktitle = {International Conference on Learning Representations},
 editor = {B. Kim and Y. Yue and S. Chaudhuri and K. Fragkiadaki and M. Khan and Y. Sun},
 pages = {54107--54157},
 title = {SWE-bench: Can Language Models Resolve Real-world Github Issues?},
 url = {https://proceedings.iclr.cc/paper_files/paper/2024/file/edac78c3e300629acfe6cbe9ca88fb84-Paper-Conference.pdf},
 volume = {2024},
 year = {2024}
}
```

**3. Nachuma & Zibran (2026) — "When AI Teammates Meet Code Review" (arXiv:2602.19441).** This study asks what actually determines whether an agent-authored PR gets merged, and its answer reframes the problem as social rather than purely technical. Using logistic regression with repository-clustered standard errors over the AIDev dataset, the authors find that reviewer engagement has the strongest correlation with successful integration, whereas larger change sizes and coordination-disrupting actions such as force pushes lower the probability of merging; iteration intensity alone provides limited explanatory power once collaboration signals are considered. Their qualitative analysis shows successful integration occurs when agents engage in actionable review loops that converge toward reviewer expectations, leading to the conclusion that effective agentic software engineering requires alignment with established code review and coordination practices — i.e., agents must behave like good open-source citizens, not just good coders.

https://arxiv.org/pdf/2602.19441

references\2602.19441v1.pdf

```bibtex
@misc{nachuma2026aiteammatesmeetcode,
      title={When AI Teammates Meet Code Review: Collaboration Signals Shaping the Integration of Agent-Authored Pull Requests}, 
      author={Costain Nachuma and Minhaz Zibran},
      year={2026},
      eprint={2602.19441},
      archivePrefix={arXiv},
      primaryClass={cs.SE},
      url={https://arxiv.org/abs/2602.19441}, 
}
```

**4. Haque, Ingale & Csallner (2026) — "Do Autonomous Agents Contribute Test Code?" (arXiv:2601.03556).** Directly targeting the testing dimension, this study is the first large-scale look at whether agents test their own work. The authors mine the AIDev-pop subset of 33.5k PRs from repositories with more than 100 stars — where expectations around testing and review are likely to be more clearly established — and ask how often agentic PRs include test code, how adoption changes over time, and how testing behavior differs across the five major agents. The paper's framing is important: despite the growing presence of agentic contributors, we lack a clear understanding of how often autonomous agents integrate testing into the PR lifecycle. This matters for workflows because test inclusion is one of the strongest trust signals human reviewers use, and heterogeneity across agents suggests test discipline is a property of agent design (prompting, scaffolding, verification loops) rather than an emergent LLM behavior.

**5. "Where Do AI Coding Agents Fail?" (2026, arXiv:2601.15195).** This paper is the most direct treatment of the "difficulties" angle, characterizing not-merged agentic PRs. Analyzing over 33k PRs from five major agents, the authors find that agentic PRs involving documentation, CI, and build-update tasks are merged at higher rates, while performance and bug-fix contributions show the lowest acceptance; not-merged PRs tend to involve larger code changes, touch more files, receive more reviewer revisions, and frequently fail project CI checks. The practical takeaway is a task-difficulty gradient: agents succeed at peripheral, low-risk maintenance work and struggle with semantically deep changes, and CI failure emerges as a key mechanical bottleneck — implying teams should gate agent PRs behind mandatory CI and route complex bug fixes toward tighter human supervision.

**6. Yoshioka et al. (2026) — "Let's Make Every Pull Request Meaningful" (arXiv:2601.18749).** This study formalizes the human-vs-agent merge-outcome comparison with a feature-rich statistical model. The authors analyze 40,214 PRs from AIDev, extracting 64 features across six families and fitting regression models to compare merge outcomes for human and agentic PRs and across three AI agents; they find that submitter attributes dominate merge outcomes for both groups, while review-related features exhibit contrasting effects between human and agentic PRs. Their motivation section usefully synthesizes prior difficulties: AI-generated code has been reported to be structurally simple and repetitive, prone to containing vulnerabilities, and identifiable by lexical and syntactic features; PRs including at least one ChatGPT link take longer to be closed; and the acceptance rate of agentic PRs is significantly lower than that of humans. The finding that *who submits* matters more than *what is submitted* underscores that reputation and trust dynamics from classic PR research carry over — and perhaps intensify — in the agentic era.

**7. "AgenticFlict: A Large-Scale Dataset of Merge Conflicts in AI Coding Agent Pull Requests" (2026, arXiv:2604.03551).** Integration friction is the least glamorous but most operationally painful difficulty, and this is the first resource to quantify it. Noting that merge conflicts remain largely unexplored in the context of AI-generated contributions, the authors build a dataset of 142,652 agentic PRs from 59,412 repositories, run deterministic merge simulation on 107,026 of them, and identify 29,609 PRs with merge conflicts — a conflict rate of 27.67% — extracting 336,380 fine-grained conflict regions with file paths and line-level spans across five distinct agents. A conflict rate above a quarter of PRs is a striking signal: agents operating on stale snapshots of fast-moving repositories create real coordination costs, and the per-agent comparisons the dataset enables point toward rebasing discipline and freshness-awareness as necessary agent capabilities.

**8. "Security in the Age of AI Teammates" (2026, arXiv:2601.00477).** This work brings the security lens to agentic PRs, examining both security-related development and the human oversight applied to it. The authors use AIDev's curated subset of 33,596 agent-authored PRs from 2,807 repositories with at least 100 stars, which includes enriched artifacts such as PR titles, descriptions, timestamps, merge outcomes, review comments, review decisions, commit metadata, and file-level diffs — precisely the artifacts needed to study security outcomes and human review behavior. Given the broader literature's finding that AI-generated code is prone to containing vulnerabilities, studies like this one are critical for answering whether the PR review gate actually catches security issues in agent code, or whether reviewer fatigue and the sheer volume of agentic contributions erode that safety net.

**9. Ogenrwot & Businge (2026) — "How AI Coding Agents Modify Code" (MSR '26).** This MSR paper zooms into the *content* of agentic changes rather than their outcomes. The authors study how tools such as GitHub Copilot, OpenAI Codex, Claude Code, Cursor, and Devin autonomously generate code, fix bugs, and submit PRs, framing these systems as evolving from assistive tools into active collaborators in the transition to Software Engineering 3.0. It extends the same group's earlier PatchTrack line of work, which analyzed ChatGPT's impact on software patch decision-making in pull requests and its influence on PR outcomes. Understanding modification patterns — what kinds of edits agents make, where in the codebase, at what granularity — is a prerequisite for building review tooling that highlights the change types agents most often get wrong.

**10. "How AI Coding Agents Communicate" (2026, arXiv:2602.17084).** This study isolates a frequently overlooked workflow variable: the PR description itself. The authors show that in AI-generated pull requests, how changes are communicated is associated with the review process in addition to functional correctness — more structured PR descriptions are associated with faster reviewer responses and shorter completion times. They also surface striking per-agent differences in the social reception of PRs: Claude Code elicited the longest comments and the highest proportion of positive sentiment, GitHub Copilot received the most comments per PR with predominantly neutral sentiment, Devin and OpenAI Codex received minimal engagement, and Cursor received the highest proportion of negative sentiment. The underlying argument — that programmers face a significant cognitive burden verifying that generated code aligns with their intent, making the communication of changes a potential bottleneck in human–AI collaborative development — connects PR-description quality directly to reviewer throughput.

**11. Yamasaki et al. (2026) — "Who Writes the Docs in SE 3.0?" (arXiv:2601.20171).** Documentation PRs are where agents have penetrated deepest, and this paper documents both the scale and a worrying oversight gap. Analyzing 1,997 documentation-related PRs authored by AI agents and humans in AIDev, the authors find that agents submit substantially more documentation PRs than humans in the studied repositories, and that agent-authored documentation edits are typically integrated with little follow-up modification from humans — raising concerns about review practices and the reliability of agent-generated documentation. Since documentation shapes how developers understand and use software, the combination of high agent volume plus light human review creates a quiet quality-assurance risk: errors in agent-written docs may propagate unchecked precisely because docs PRs are perceived as low-stakes and merged fast (consistent with source 5's finding that docs PRs enjoy the highest acceptance rates).

**12. "Automated Code Review in Practice" (2024, arXiv:2412.18531).** This is one of the few *industrial* field studies of LLM review bots inside real PR workflows. The authors collaborated with Beko, a multinational home-appliances company whose software division adopted an automated review tool based on the open-source Qodo PR-Agent using GPT-4 Turbo, providing automatic review comments on every pull request across 10 projects and 22 repositories. The results were broadly positive: developers received the tool well and 73.8% of its comments were accounted for in the pull requests, suggesting LLMs can enhance the code review process, with one respondent noting it improved team awareness of code quality — though the study also observed frustration caused by recurring low-value comments, a friction pattern echoed throughout the review-bot literature. It's a valuable counterweight to purely mining-based studies because it measures how automation changes human review *volume* and behavior, not just PR metadata.

**13. Chowdhury et al. (2026) — "From Industry Claims to Empirical Reality: Code Review Agents in Pull Requests" (MSR '26).** Where source 12 is optimistic, this paper delivers the skeptical empirical check on autonomous code review agents (CRAs) like CodeRabbit. Analyzing 3,109 PRs from AIDev in the Commented review state, the authors find that CRA-only PRs achieve a 45.20% merge rate — 23.17 percentage points lower than human-only reviews (68.37%) — with significantly higher abandonment; their signal-to-noise analysis shows 60.2% of closed CRA-only PRs fall into the 0–30% signal range, and 12 of 13 CRAs exhibit average signal ratios below 60%. Their conclusion — CRAs without human oversight often generate low-signal feedback associated with higher abandonment — combined with the observation that CRA adoption is limited by trust issues and lack of project-specific context, argues strongly that fully agent-reviewed PR pipelines are premature and human-in-the-loop review remains load-bearing.

**14. "Rethinking Code Review Workflows with LLM Assistance" (2025, arXiv:2505.16339).** This mixed-method industrial study (field study plus field experiment) examines how LLMs should be *positioned* within review workflows rather than whether they work at all. The field study identifies key challenges in traditional code reviews — frequent context switching and insufficient contextual information — and highlights both opportunities (automatic summarization of complex pull requests) and concerns (false positives and trust issues); the authors then built two prototypes, one offering LLM-generated reviews upfront and one enabling on-demand interaction, both using a retrieval-augmented semantic search pipeline to assemble relevant context. In real-world evaluation, AI-led reviews were overall preferred, but preference remained conditional on reviewers' familiarity with the codebase and on the severity of the pull request — a nuanced result suggesting LLM review assistance should be adaptive: front-loaded for routine changes, human-led for high-severity ones.

**15. "Code Change Characteristics and Description Alignment: Agentic versus Human PRs" (2026, arXiv:2601.17627).** This comparative study quantifies structural differences between agent and human contributions at the symbol level. Comparing 33,596 agentic PRs against 6,618 human PRs, the authors find that agent-introduced symbols are removed sooner (median 3 vs. 34 days) and churn more (7.33% vs. 4.10%), indicating a focus on narrow tasks; agents produce stronger commit-level messages (semantic similarity 0.72 vs. 0.68) but lag in PR-level summarization, highlighting limited full-PR reasoning. The churn finding is particularly consequential for maintenance: agent code that gets rewritten within days imposes hidden downstream costs invisible at merge time, and the commit-vs-PR asymmetry suggests agents reason well locally but struggle to synthesize a coherent narrative across a whole changeset — informing task assignment, review practices, and agent training.

---

### 2. Metrics, Methodology, and Foundational Software Engineering Literature

The papers below don't study coding agents directly — they are the classic pull-request, code-review, and code-quality literature that the project's metric families (bracket codes such as `[G14]`, `[Z22]`, `[M76]` in [characteristic_metrics.md](../characteristic_metrics.md)) are drawn from, plus the statistical methods used to compare agentic and human PR distributions.

**16. Long, Feng & Cliff (2003) — "Ordinal Analysis of Behavioral Data" (Handbook of Psychology, Chapter 25).** Handbook chapter on ordinal statistical methods for behavioral data, including Cliff's delta as a non-parametric effect size measure for comparing two groups without distributional assumptions. This is the methodological source for computing Cliff's delta when comparing agent-authored and human-authored PR metric distributions in this project.

**17. Mann & Whitney (1947) — "On a Test of Whether One of Two Random Variables Is Stochastically Larger Than the Other" (Annals of Mathematical Statistics).** Classic statistics paper introducing the Mann-Whitney U test, a non-parametric test of whether one of two random variables is stochastically larger than the other. Cited as the methodological source for distribution comparison at α = 0.05 throughout the codebook's statistical analyses.

**18. Sharma, Mishra & Tiwari (2016) — "Designite: A Software Design Quality Assessment Tool" (BRIDGE '16).** Tool paper presenting Designite, a software design quality assessment tool; its Python variant DPy detects architecture, design, implementation, and ML-specific smells and computes object-oriented metrics (size, complexity, coupling, cohesion, inheritance depth). Used in this project for before/after code quality analysis of agent-touched files.

**19. Gousios, Pinzger & van Deursen (2014) — "An Exploratory Study of the Pull-Based Software Development Model" (ICSE 2014).** Foundational study of pull-based development on GitHub, establishing canonical PR metrics (churn, commits, files changed, team size, project age, test coverage density) and models of PR acceptance and latency. Source of the `[G14]` metric family used throughout the codebook, including `num_commits_open`/`_close`, `src_churn_open`/`_close`, `files_changed_open`/`_close`, `sloc`, `team_size`, and `requester_succ_rate`.

**20. Gousios, Zaidman, Storey & van Deursen (2015) — "Work Practices and Challenges in Pull-Based Development: The Integrator's Perspective" (ICSE 2015).** Survey of integrators in pull-based projects, documenting how maintainers evaluate contributions, prioritize work, and struggle with review workload and quality assessment. Source of the `rework` metric `[G15]` — new work pushed after the first review feedback.

**21. Tsay, Dabbish & Herbsleb (2014) — "Influence of Social and Technical Factors for Evaluating Contribution in GitHub" (ICSE 2014).** Study showing PR acceptance depends on both technical factors (test inclusion) and social factors (follower count, social connection between submitter and core team, prior interaction). Source of the `[T14]` metrics: `num_participants`, `social_strength`, and `followers`.

**22. Yu, Wang, Filkov, Devanbu & Vasilescu (2015) — "Wait for It: Determinants of Pull Request Evaluation Latency on GitHub" (MSR 2015).** Study of what determines PR evaluation latency: description length, @-mentions, CI latency, and first response time are key predictors. Source of the `[Y15]` metrics, including `description_length`, `at_tag`, `ci_latency`, and `first_response_time`.

**23. Vasilescu, Yu, Wang, Devanbu & Filkov (2015) — "Quality and Productivity Outcomes Relating to Continuous Integration in GitHub" (ESEC/FSE 2015).** Study showing CI adoption changes team productivity and quality outcomes in GitHub projects: teams using CI merge more external PRs while maintaining quality. Source of the `[V15]` metrics: `ci_exists` and `ci_test_passed`.

**24. Baysal, Kononenko, Holmes & Godfrey (2016) — "Investigating Technical and Non-Technical Factors Influencing Modern Code Review" (Empirical Software Engineering).** Study showing non-technical factors — including organizational affiliation of author and reviewer — significantly influence code review outcomes and timeliness. Source of the `[B16]` affiliation metrics: `contrib_affiliation`, `same_affiliation`, and `inte_affiliation`.

**25. Terrell et al. (2017) — "Gender Differences and Bias in Open Source: Pull Request Acceptance of Women Versus Men" (PeerJ Computer Science).** Study of gender bias in open source: women's PRs are accepted at higher rates overall, but at lower rates than men's when gender is identifiable and they are outsiders. Source of the `contrib_gender` inference methodology `[TR17]`, used here with the same ethical caveats the original authors note about individual-level inference.

**26. Śliwerski, Zimmermann & Zeller (2005) — "When Do Changes Induce Fixes?" (MSR 2005).** Paper introducing the SZZ algorithm for linking fixes to fix-inducing changes; finds changes made on Fridays are more error-prone (the "Friday effect"). Source of the `friday_effect` metric `[S05]`.

**27. Zhang, Yu, Gousios & Rastogi (2022) — "Pull Request Latency Explained: An Empirical Overview" (Empirical Software Engineering).** Large-scale empirical overview of PR latency, synthesizing and validating predictors across many projects. Source of the extensive `[Z22]` metric family (`bug_fix`, `hash_tag`, `reopen_or_not`, `first_pr`, `integrator_availability`, and others) that forms the backbone of the codebook's process and outcome metrics.

references\s10664-022-10143-4.pdf

**28. McCabe (1976) — "A Complexity Measure" (IEEE Transactions on Software Engineering).** Classic paper introducing cyclomatic complexity, a graph-theoretic measure of the number of linearly independent paths through a program's control flow. Source of the `cyclomatic_complexity` metric `[M76]`.

**29. Halstead (1977) — "Elements of Software Science" (book).** Book establishing Halstead software science metrics — vocabulary, length, and volume (V = N·log₂ n) — computed from operator and operand counts. Source of the `halstead_volume` metric `[HA77]`.

**30. Shepperd (1988) — "A Critique of Cyclomatic Complexity as a Software Metric" (Software Engineering Journal).** Critique showing cyclomatic complexity correlates strongly with lines of code and questioning its independent value as a complexity metric. Cited `[SH88]` as a caveat on the codebook's complexity metrics.

**31. Dunsmore (1984) — "The Effect of Nesting Depth on Program Comprehension" (Journal of Systems and Software).** Study of how control-structure nesting depth affects programmer comprehension, motivating nesting depth as a complexity indicator. Source of the `nesting_depth` metric `[D84]`.

**32. Fowler (1999) — "Refactoring: Improving the Design of Existing Code" (book).** Classic book cataloguing refactorings and code smells, including Large Class and Long Method, which underpin the `large_class` and `long_method` design-smell detection metrics `[F99]`.

**33. Nagappan & Ball (2005) — "Use of Relative Code Churn Measures to Predict System Defect Density" (ICSE 2005).** Study showing relative code churn measures are strong predictors of system defect density in large systems. Source of the `codechurn` metric `[N05]`.

**34. Ayewah, Pugh, Hovemeyer, Morgenthaler & Penix (2008) — "Using Static Analysis to Find Bugs" (IEEE Software).** Paper on FindBugs-style static analysis for defect detection, including patterns such as unused variables. Source of the `unused_vars` metric `[AY08]`.

**35. Roy, Cordy & Koschke (2009) — "Comparison and Evaluation of Code Clone Detection Techniques and Tools" (Science of Computer Programming).** Survey comparing code clone detection techniques and tools across clone types. Source of the `duplicate_code` metric `[RC09]`.

**36. Vaucher, Khomh, Moha & Guéhéneuc (2009) — "Tracking Design Smells: Lessons from a Study of God Classes" (WCRE 2009).** Study tracking God Classes over software evolution, distinguishing classes born as God Classes from those that degrade into them. Source of the `god_object` metric `[VA09]`.

**37. Hindle, Barr, Su, Gabel & Devanbu (2012) — "On the Naturalness of Software" (ICSE 2012).** Landmark paper showing software is highly repetitive and predictable, capturable by n-gram language models — foundational for statistical and ML models of code. Source of the `ngrams` textual feature `[H12]`.
