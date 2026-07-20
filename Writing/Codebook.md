We attempt to classify rejection reasons and construct an inductive codebook:




* Did Not Follow Instructions
* Unrequested Changes
* Infinite Loops
* Tool Call Failures




| Theme | Code Name | Description | Example |
|---|---|---|---|
| Process | Build Failure | The pull request fails required automated checks (e.g., build, test, packaging, lint) and is closed or left unmerged without resolution. | |
| Process | CI Fail |The PR failed due to unsuccessful CI checks attributed to external infrastructure issues (e.g., network or firewall restrictions), and was closed without remediation.| #5606: ``Attempted build validation but encountered environment setup challenges.''|
| Process | Agent Draft |  Opened and closed as draft. A follow-up PR contains the actual implementation. &
PR was not intended to be merged in this form. ||
| Process | Unresolved Merge State|||
| Process | Incomplete Solution | Partial solution achieved.|"Almost", "Not quite" |
| Process |