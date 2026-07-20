



### Repository Pull Request Life Cycle




### Dataset

GitHub is a rich data source for software development, but repositories, issues, and pull requests can be noisy, ad-hoc, or poorly documented or maintained. To find high-quality PRs and limit the scope of our search, we filter the dataset with PRs from projects as follows:
* > 100 stars
* > 30 contributors 
* Python, C++ and C# 

#### Dataset Metadata

`pull_request`:
* `id`
* `title`
* `body`
* `agent`
* 


Artifacts:
* list of self-affirmed refactoring patterns (from titles, different type )
* distribution of commits and prs (#) by associated ai agent


We also want to analyze these behaviors through longitudinal analysis. To quantify the impact we extract object-oriented metrics and design smells before and after agents were introduced. 

In theory:
* class lines of code in project delta (class size and complexity)
* design and implementation smells
* defect density
* post-release defects 
* effort

In practice: 
* size: lines of code
* complexity: cyclomatic complexity, weighted methods per class
* coupling: fan-in, fan-out
* cohesion: lack of cohesion in methods
* inheritance depth (depth of inheritance tree)
* design and implementation smells 


### Visual Inspection


From the visual inspection, we derive the different metrics, ontop of the metrics already established for the AIDev dataset.




#### Task Formulation


*Model Input*: