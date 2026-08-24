"""
GLMM (generalized linear mixed model) companion to
agent_code_survival_full_corpus.py's pooled Mann-Whitney/Fisher tests -
additive, not a replacement. That script pairs each pooled test with a
repo-stratified label-shuffle PERMUTATION test as its robustness check
(does the pooled point estimate survive repo composition) - a different
question from what a GLMM answers. This script fits, per outcome, ONE
mixed model across all repos with `full_name` as a random intercept:

- the permutation test asks "is the pooled point estimate an artifact of
  which repos happen to be in which group" (robustness)
- the GLMM asks "what is the is_born_agent effect, accounting for
  clustering from the start, and how much do repos vary around it"
  (effect size + between-repo heterogeneity)

Neither replaces the other; both are reported side by side in the
follow-up doc.

Uses statsmodels.genmod.bayes_mixed_glm (variational-Bayes GLMM fitting -
a DIFFERENT inferential framework from MixedLM's REML/MLE used elsewhere
in this mixed-effects layer): BinomialBayesMixedGLM for the two binary
outcomes (`ended`, `full_survival`), PoissonBayesMixedGLM for the count
outcome (`touches_after_birth`). Fixed-effect output is a posterior
mean/SD (variational Bayes), not a classical coefficient/CI - named as
such throughout, not presented as if it were REML/MLE output.

**Two named, real limitations, the second discovered only by trying it,
not anticipated when this was planned**: (1) statsmodels' bayes_mixed_glm
module has no negative-binomial variant, so if touches_after_birth is
overdispersed (variance >> mean - checked and reported below, and it is:
var/mean ~6), that's a stated gap in what this framework can model, not a
silently-accepted misfit. (2) The same module has NO offset mechanism at
all (confirmed via inspect.signature - neither from_formula nor __init__
exposes one) - the originally planned "Poisson with a log(age_days+1)
offset, replacing the original script's ad-hoc touches_per_day rate
column" is not buildable with this tool. log(age_days+1) is included
instead as an ordinary, freely-estimated covariate - a real
approximation to exposure-adjustment, not the statistically correct
offset model this was meant to be, and reported as such rather than
silently passed off as the plan's original design.

Reads today's already-pinned agent-code-survival full-corpus outputs
directly - no re-derivation of the underlying labels/similarity data.
"""

import sys
import warnings
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.genmod.bayes_mixed_glm import BinomialBayesMixedGLM, PoissonBayesMixedGLM

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "viz"))
import figures_common as fc  # noqa: E402

OUT_DIR = fc.ANALYSIS_DIR
LABELED_PATH = fc.ANALYSIS_DIR / "08-24-agent-survival-fc-labeled-lineages.csv"
MOD_SIMILARITY_PATH = fc.ANALYSIS_DIR / "08-24-agent-survival-fc-modification-similarity.csv"
MIN_GROUP_N = 5  # same floor agent_code_survival_full_corpus.py's survival_deletion_test already uses


def small_group_report(df, group_col="full_name", label_col="is_born_agent"):
    """Per-repo agent/human counts, flagging any repo contributing <5 to
    EITHER group as uninformative to that repo's random effect - reported
    explicitly, not silently absorbed into a pooled number."""
    tab = df.groupby([group_col, label_col]).size().unstack(fill_value=0)
    tab.columns = ["n_human", "n_agent"] if False in tab.columns and True in tab.columns else tab.columns
    tab = tab.rename(columns={False: "n_human", True: "n_agent"})
    for c in ("n_human", "n_agent"):
        if c not in tab.columns:
            tab[c] = 0
    tab["thin"] = (tab["n_human"] < MIN_GROUP_N) | (tab["n_agent"] < MIN_GROUP_N)
    return tab.reset_index()


def _fit_vb(model_cls, formula, vc_formulas, data):
    """Shared fit_vb() wrapper for both Binomial/Poisson BayesMixedGLM
    subclasses - catches the "VB fitting did not converge" UserWarning
    statsmodels raises separately from (not always redundant with)
    optim_retvals['success'], so both signals feed the reported
    `converged` flag rather than relying on just one."""
    model = model_cls.from_formula(formula, vc_formulas, data)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", UserWarning)
        result = model.fit_vb()
        did_not_converge_warning = any(
            "did not converge" in str(w.message).lower() for w in caught
        )
    converged = bool(result.optim_retvals.get("success", False)) and not did_not_converge_warning
    return model, result, converged


def fit_binomial_glmm(df, formula, group_col="full_name"):
    d = df.copy()
    d[group_col] = d[group_col].astype(str)
    return _fit_vb(BinomialBayesMixedGLM, formula, {"repo": f"0 + C({group_col})"}, d)


def fit_poisson_glmm(df, formula, group_col="full_name"):
    d = df.copy()
    d[group_col] = d[group_col].astype(str)
    return _fit_vb(PoissonBayesMixedGLM, formula, {"repo": f"0 + C({group_col})"}, d)


def summarize(model, result, outcome_name, fe_name, n_repos, n_obs, n_agent, n_human, converged):
    fe_idx = model.exog_names.index(fe_name)
    # Posterior mean/SD of the log-standard-deviation of the repo random
    # intercept (vcp_mean/vcp_sd) - converted to an SD-scale point value
    # (exp(vcp_mean)) for direct comparability with MixedLM's re_var_*
    # columns elsewhere in this layer (as a variance: exp(vcp_mean)**2).
    re_sd = float(np.exp(result.vcp_mean[0]))
    return {
        "outcome": outcome_name, "n_repos": n_repos, "n_obs": n_obs,
        "n_agent": n_agent, "n_human": n_human,
        "is_born_agent_posterior_mean": result.fe_mean[fe_idx],
        "is_born_agent_posterior_sd": result.fe_sd[fe_idx],
        "re_intercept_sd_posterior_mean": re_sd,
        "re_intercept_variance_approx": re_sd ** 2,
        "converged": converged,
        "optimizer_message": result.optim_retvals.get("message", ""),
    }


def run():
    labeled = pd.read_csv(LABELED_PATH)
    mod = pd.read_csv(MOD_SIMILARITY_PATH)
    resolved = mod.dropna(subset=["similarity_birth_to_last"]).copy()
    resolved["full_survival"] = resolved["survived_modification"]

    today = date.today()
    prefix = f"{today.month:02d}-{today.day:02d}"

    print("=== small-group check: full_survival candidate set (repos with <5 in either cohort) ===")
    sg = small_group_report(resolved)
    thin = sg[sg["thin"]]
    print(f"{len(thin)}/{len(sg)} repos have <5 rows in at least one cohort:")
    print(thin.to_string(index=False) if not thin.empty else "(none)")
    sg_path = OUT_DIR / f"{prefix}-agent-survival-fc-mixed-effects-group-diagnostics.csv"
    sg.to_csv(sg_path, index=False)

    rows = []

    # --- ended (binary, all 166K lineages, both languages) ---
    d = labeled.dropna(subset=["ended", "is_born_agent", "full_name"]).copy()
    n_agent, n_human = int(d["is_born_agent"].sum()), int((~d["is_born_agent"]).sum())
    d["ended"] = d["ended"].astype(int)
    d["is_born_agent"] = d["is_born_agent"].astype(int)
    model, result, converged = fit_binomial_glmm(d, "ended ~ is_born_agent")
    rows.append(summarize(model, result, "ended", "is_born_agent",
                           d["full_name"].nunique(), len(d), n_agent, n_human, converged))
    print(f"\nended ~ is_born_agent: posterior mean={result.fe_mean[model.exog_names.index('is_born_agent')]:.4f} "
          f"(sd={result.fe_sd[model.exog_names.index('is_born_agent')]:.4f})")

    # --- full_survival (binary, 3,688-row resolved modification-similarity subset) ---
    d = resolved.dropna(subset=["full_survival", "is_born_agent", "full_name"]).copy()
    n_agent, n_human = int(d["is_born_agent"].sum()), int((~d["is_born_agent"]).sum())
    d["full_survival"] = d["full_survival"].astype(int)
    d["is_born_agent"] = d["is_born_agent"].astype(int)
    model, result, converged = fit_binomial_glmm(d, "full_survival ~ is_born_agent")
    rows.append(summarize(model, result, "full_survival", "is_born_agent",
                           d["full_name"].nunique(), len(d), n_agent, n_human, converged))
    print(f"full_survival ~ is_born_agent: posterior mean={result.fe_mean[model.exog_names.index('is_born_agent')]:.4f} "
          f"(sd={result.fe_sd[model.exog_names.index('is_born_agent')]:.4f})")

    # --- touches_after_birth (count, Poisson with log(age_days+1) offset) ---
    d = labeled.dropna(subset=["touches_after_birth", "age_days", "is_born_agent", "full_name"]).copy()
    d = d[d["age_days"] >= 0]
    mean_touches, var_touches = d["touches_after_birth"].mean(), d["touches_after_birth"].var()
    print(f"\ntouches_after_birth overdispersion check: mean={mean_touches:.4f}, var={var_touches:.4f}, "
          f"var/mean={var_touches / mean_touches:.2f} (Poisson assumes ~1.0 - "
          f"no negative-binomial variant available in bayes_mixed_glm, see module docstring)")
    # PLAN DEVIATION, discovered only by trying it (not anticipated in
    # planning): statsmodels' bayes_mixed_glm has NO offset mechanism at
    # all - no `offset=` kwarg on __init__/from_formula, and bare
    # patsy formulas don't provide an offset() term unless the caller
    # supplies one (statsmodels' own formula plumbing doesn't wire one in
    # for this model class - confirmed via inspect.signature on both
    # from_formula and __init__, neither exposes it). A true fixed-
    # coefficient offset (rate = count / exposure, log(exposure) forced
    # into the linear predictor with coefficient exactly 1) is therefore
    # NOT buildable with this tool. log(age_days+1) is included below as
    # an ordinary, freely-estimated covariate instead - an approximation
    # to exposure-adjustment, not a real offset, and named as such here
    # and in the follow-up doc rather than silently presented as the
    # planned offset model.
    d["log_age"] = np.log(d["age_days"] + 1)
    n_agent, n_human = int(d["is_born_agent"].sum()), int((~d["is_born_agent"]).sum())
    d["is_born_agent"] = d["is_born_agent"].astype(int)
    model, result, converged = fit_poisson_glmm(d, "touches_after_birth ~ is_born_agent + log_age")
    rows.append(summarize(model, result,
                           "touches_after_birth (log_age covariate, NOT a true offset - see docstring)",
                           "is_born_agent", d["full_name"].nunique(), len(d), n_agent, n_human, converged))
    print(f"touches_after_birth ~ is_born_agent + log_age (covariate, not offset): posterior mean="
          f"{result.fe_mean[model.exog_names.index('is_born_agent')]:.4f} "
          f"(sd={result.fe_sd[model.exog_names.index('is_born_agent')]:.4f}), converged={converged}")

    out = pd.DataFrame(rows)
    out_path = OUT_DIR / f"{prefix}-agent-survival-fc-mixed-effects.csv"
    out.to_csv(out_path, index=False)
    print(f"\n=== GLMM companions -> {out_path} ===")
    print(out.to_string(index=False))
    print(f"group diagnostics -> {sg_path}")
    return out


if __name__ == "__main__":
    run()
