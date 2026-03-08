"""
Pure computation layer for the Statistics tab.

NO Streamlit imports. All functions accept plain Python types / DataFrames /
numpy arrays and return plain dicts. Every function uses try/except to return
{"error": str} on failure instead of raising. NaN values are dropped with a
count of removed values in the return dict.
"""

from __future__ import annotations

import ast
import math
import warnings
from functools import partial
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Safe math names for custom equation parsing
# ---------------------------------------------------------------------------

_SAFE_NAMES = {
    "x", "exp", "log", "log10", "sqrt", "sin", "cos", "tan",
    "abs", "pi", "e", "inf",
}
_SAFE_FUNCS = {
    "exp": np.exp, "log": np.log, "log10": np.log10, "sqrt": np.sqrt,
    "sin": np.sin, "cos": np.cos, "tan": np.tan, "abs": np.abs,
    "pi": np.pi, "e": np.e,
}


# ===================================================================
#  1. STATISTICAL TESTS (14 total)
# ===================================================================

# --- Helper: strip NaN and report count ---

def _clean_pair(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray, int]:
    """Drop NaN from paired arrays. Returns cleaned arrays and count removed."""
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    mask = ~(np.isnan(a) | np.isnan(b))
    removed = int((~mask).sum())
    return a[mask], b[mask], removed


def _clean_single(x: np.ndarray) -> tuple[np.ndarray, int]:
    """Drop NaN from a single array."""
    x = np.asarray(x, dtype=float)
    mask = ~np.isnan(x)
    removed = int((~mask).sum())
    return x[mask], removed


# --- Base tests (9) ---

def run_ttest(group1, group2) -> dict:
    """Independent t-test (Welch's) via pingouin."""
    try:
        import pingouin as pg
        g1, removed1 = _clean_single(group1)
        g2, removed2 = _clean_single(group2)
        total_removed = removed1 + removed2
        if len(g1) < 3:
            return {"error": f"Group 1 has fewer than 3 observations (n={len(g1)})."}
        if len(g2) < 3:
            return {"error": f"Group 2 has fewer than 3 observations (n={len(g2)})."}
        if np.std(g1) == 0 and np.std(g2) == 0:
            return {"error": "Both groups have zero variance (all identical values). Cannot compute test statistic."}
        result = pg.ttest(g1, g2, paired=False, alternative="two-sided")
        return {
            "test_name": "Independent Samples t-test (Welch's)",
            "T": float(result["T"].iloc[0]),
            "dof": float(result["dof"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "CI95": result["CI95"].iloc[0],
            "cohen_d": float(result["cohen_d"].iloc[0]),
            "BF10": str(result["BF10"].iloc[0]),
            "power": float(result["power"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": total_removed,
        }
    except Exception as e:
        return {"error": f"Independent t-test failed: {e}"}


def run_paired_ttest(x, y) -> dict:
    """Paired t-test via pingouin."""
    try:
        import pingouin as pg
        x_c, y_c, removed = _clean_pair(x, y)
        if len(x_c) < 3:
            return {"error": f"Fewer than 3 paired observations after removing NaN (n={len(x_c)})."}
        diffs = x_c - y_c
        if np.std(diffs) == 0:
            return {"error": "All differences are identical (zero variance). Cannot compute test statistic."}
        result = pg.ttest(x_c, y_c, paired=True, alternative="two-sided")
        return {
            "test_name": "Paired Samples t-test",
            "T": float(result["T"].iloc[0]),
            "dof": float(result["dof"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "CI95": result["CI95"].iloc[0],
            "cohen_d": float(result["cohen_d"].iloc[0]),
            "BF10": str(result["BF10"].iloc[0]),
            "power": float(result["power"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Paired t-test failed: {e}"}


def run_mannwhitney(group1, group2) -> dict:
    """Mann-Whitney U test via pingouin."""
    try:
        import pingouin as pg
        g1, removed1 = _clean_single(group1)
        g2, removed2 = _clean_single(group2)
        total_removed = removed1 + removed2
        if len(g1) < 3:
            return {"error": f"Group 1 has fewer than 3 observations (n={len(g1)})."}
        if len(g2) < 3:
            return {"error": f"Group 2 has fewer than 3 observations (n={len(g2)})."}
        result = pg.mwu(g1, g2, alternative="two-sided")
        return {
            "test_name": "Mann-Whitney U test",
            "U": float(result["U_val"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "RBC": float(result["RBC"].iloc[0]),
            "CLES": float(result["CLES"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": total_removed,
        }
    except Exception as e:
        return {"error": f"Mann-Whitney U test failed: {e}"}


def run_wilcoxon(x, y) -> dict:
    """Wilcoxon signed-rank test via pingouin."""
    try:
        import pingouin as pg
        x_c, y_c, removed = _clean_pair(x, y)
        if len(x_c) < 6:
            return {"error": f"Wilcoxon requires at least 6 paired observations (n={len(x_c)})."}
        diffs = x_c - y_c
        if np.all(diffs == 0):
            return {"error": "All paired differences are zero. Cannot compute Wilcoxon test."}
        result = pg.wilcoxon(x_c, y_c, alternative="two-sided")
        return {
            "test_name": "Wilcoxon Signed-Rank test",
            "W": float(result["W_val"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "RBC": float(result["RBC"].iloc[0]),
            "CLES": float(result["CLES"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Wilcoxon signed-rank test failed: {e}"}


def run_one_way_anova(df: pd.DataFrame, dv: str, between: str) -> dict:
    """One-way ANOVA with Tukey post-hoc if significant."""
    try:
        import pingouin as pg
        df_clean = df[[dv, between]].dropna()
        removed = len(df) - len(df_clean)
        groups = df_clean[between].unique()
        if len(groups) < 2:
            return {"error": f"Need at least 2 groups, found {len(groups)}."}
        for g in groups:
            n_g = (df_clean[between] == g).sum()
            if n_g < 2:
                return {"error": f"Group '{g}' has fewer than 2 observations (n={n_g})."}
        result = pg.anova(data=df_clean, dv=dv, between=between, detailed=False)
        p_val = float(result["p_unc"].iloc[0])
        posthoc = None
        if p_val < 0.05:
            posthoc = pg.pairwise_tukey(data=df_clean, dv=dv, between=between)
        return {
            "test_name": "One-way ANOVA",
            "F": float(result["F"].iloc[0]),
            "p_val": p_val,
            "eta_squared": float(result["np2"].iloc[0]),
            "df_between": int(result["ddof1"].iloc[0]),
            "df_within": int(result["ddof2"].iloc[0]),
            "result_df": result.to_dict("records"),
            "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"One-way ANOVA failed: {e}"}


def run_kruskal(df: pd.DataFrame, dv: str, between: str) -> dict:
    """Kruskal-Wallis H test with Dunn's post-hoc."""
    try:
        import pingouin as pg
        df_clean = df[[dv, between]].dropna()
        removed = len(df) - len(df_clean)
        groups = df_clean[between].unique()
        if len(groups) < 2:
            return {"error": f"Need at least 2 groups, found {len(groups)}."}
        result = pg.kruskal(data=df_clean, dv=dv, between=between)
        p_val = float(result["p_unc"].iloc[0])
        posthoc = None
        if p_val < 0.05:
            posthoc = pg.pairwise_tests(
                data=df_clean, dv=dv, between=between,
                parametric=False, padjust="bonf",
            )
        return {
            "test_name": "Kruskal-Wallis H test",
            "H": float(result["H"].iloc[0]),
            "p_val": p_val,
            "result_df": result.to_dict("records"),
            "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Kruskal-Wallis test failed: {e}"}


def run_pearson(x, y) -> dict:
    """Pearson correlation via pingouin."""
    try:
        import pingouin as pg
        x_c, y_c, removed = _clean_pair(x, y)
        if len(x_c) < 3:
            return {"error": f"Need at least 3 paired observations (n={len(x_c)})."}
        if np.std(x_c) == 0 or np.std(y_c) == 0:
            return {"error": "One or both variables have zero variance. Cannot compute correlation."}
        result = pg.corr(x_c, y_c, method="pearson")
        return {
            "test_name": "Pearson Correlation",
            "r": float(result["r"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "CI95": result["CI95"].iloc[0],
            "r_squared": float(result["r"].iloc[0]) ** 2,
            "power": float(result["power"].iloc[0]),
            "n": int(result["n"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Pearson correlation failed: {e}"}


def run_spearman(x, y) -> dict:
    """Spearman rank correlation via pingouin."""
    try:
        import pingouin as pg
        x_c, y_c, removed = _clean_pair(x, y)
        if len(x_c) < 3:
            return {"error": f"Need at least 3 paired observations (n={len(x_c)})."}
        result = pg.corr(x_c, y_c, method="spearman")
        return {
            "test_name": "Spearman Correlation",
            "r": float(result["r"].iloc[0]),
            "p_val": float(result["p_val"].iloc[0]),
            "CI95": result["CI95"].iloc[0],
            "r_squared": float(result["r"].iloc[0]) ** 2,
            "power": float(result["power"].iloc[0]),
            "n": int(result["n"].iloc[0]),
            "result_df": result.to_dict("records"),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Spearman correlation failed: {e}"}


def run_chi_square(df: pd.DataFrame, col1: str, col2: str) -> dict:
    """Chi-square test of independence."""
    try:
        from scipy.stats import chi2_contingency
        df_clean = df[[col1, col2]].dropna()
        removed = len(df) - len(df_clean)
        ct = pd.crosstab(df_clean[col1], df_clean[col2])
        if ct.shape[0] < 2 or ct.shape[1] < 2:
            return {"error": f"Contingency table must be at least 2x2, got {ct.shape[0]}x{ct.shape[1]}."}
        chi2, p, dof, expected = chi2_contingency(ct)
        low_expected = int((expected < 5).sum())
        min_dim = min(ct.shape) - 1
        cramers_v = float(np.sqrt(chi2 / (ct.values.sum() * min_dim))) if min_dim > 0 else 0.0
        warning_msg = None
        if low_expected > 0:
            warning_msg = (
                f"{low_expected} cell(s) have expected frequency < 5. "
                "Consider Fisher's exact test for 2x2 tables."
            )
        return {
            "test_name": "Chi-square Test of Independence",
            "chi2": float(chi2),
            "p_val": float(p),
            "dof": int(dof),
            "cramers_v": cramers_v,
            "contingency_table": ct.to_dict(),
            "expected_frequencies": pd.DataFrame(
                expected, index=ct.index, columns=ct.columns
            ).to_dict(),
            "low_expected_cells": low_expected,
            "warning": warning_msg,
            "result_df": [{"chi2": float(chi2), "p_value": float(p), "dof": int(dof),
                           "cramers_v": cramers_v}],
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Chi-square test failed: {e}"}


# --- Tier 1 additions (5) ---

def run_two_way_anova(
    df: pd.DataFrame,
    dv: str,
    factor_a: str,
    factor_b: str,
) -> dict:
    """Two-way ANOVA with interaction term."""
    try:
        import pingouin as pg
        cols = [dv, factor_a, factor_b]
        df_clean = df[cols].dropna()
        removed = len(df) - len(df_clean)

        if not pd.api.types.is_numeric_dtype(df_clean[dv]):
            return {"error": f"Dependent variable '{dv}' must be numeric."}
        levels_a = df_clean[factor_a].nunique()
        levels_b = df_clean[factor_b].nunique()
        if levels_a < 2:
            return {"error": f"Factor '{factor_a}' has only {levels_a} level(s). Need at least 2."}
        if levels_b < 2:
            return {"error": f"Factor '{factor_b}' has only {levels_b} level(s). Need at least 2."}

        # Check for empty cells — use reindex to detect missing combinations
        all_combos = pd.MultiIndex.from_product(
            [df_clean[factor_a].unique(), df_clean[factor_b].unique()],
            names=[factor_a, factor_b],
        )
        cell_counts = df_clean.groupby([factor_a, factor_b]).size().reindex(all_combos, fill_value=0)
        missing = cell_counts[cell_counts == 0]
        if len(missing) > 0:
            missing_labels = [f"({a}, {b})" for a, b in missing.index[:3]]
            return {
                "error": f"Missing factor combinations: {', '.join(missing_labels)}. "
                         "Two-way ANOVA requires at least 1 observation per cell."
            }

        result = pg.anova(data=df_clean, dv=dv, between=[factor_a, factor_b], detailed=True)

        effects = {}
        for _, row in result.iterrows():
            source = row["Source"]
            effects[source] = {
                "F": float(row["F"]) if pd.notna(row["F"]) else None,
                "p_val": float(row["p_unc"]) if pd.notna(row["p_unc"]) else None,
                "eta_squared": float(row["np2"]) if "np2" in row and pd.notna(row["np2"]) else None,
                "df": int(row["DF"]) if "DF" in row and pd.notna(row.get("DF")) else (
                    int(row["ddof1"]) if "ddof1" in row and pd.notna(row.get("ddof1")) else None
                ),
            }

        interaction_key = f"{factor_a} * {factor_b}"
        posthoc = None
        interaction_p = effects.get(interaction_key, {}).get("p_val", 1.0)
        if interaction_p is not None and interaction_p < 0.05:
            posthoc = pg.pairwise_tests(
                data=df_clean, dv=dv, between=[factor_a, factor_b],
                padjust="bonf",
            )

        return {
            "test_name": "Two-way ANOVA",
            "main_effect_a": effects.get(factor_a, {}),
            "main_effect_b": effects.get(factor_b, {}),
            "interaction": effects.get(interaction_key, {}),
            "result_df": result.to_dict("records"),
            "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Two-way ANOVA failed: {e}"}


def run_fisher_exact(table_2x2) -> dict:
    """Fisher's exact test for 2x2 contingency tables.

    Accepts either a 2x2 array-like or a pd.DataFrame (crosstab).
    """
    try:
        from scipy.stats import fisher_exact as _fisher

        if isinstance(table_2x2, pd.DataFrame):
            ct = table_2x2
        else:
            ct_arr = np.asarray(table_2x2)
            if ct_arr.shape != (2, 2):
                return {
                    "test_name": "Fisher's Exact Test",
                    "error": f"Requires a 2x2 table, got {ct_arr.shape[0]}x{ct_arr.shape[1]}. "
                             "Reduce to 2 levels per variable or use Chi-square.",
                }
            ct = pd.DataFrame(ct_arr)

        if ct.shape != (2, 2):
            return {
                "test_name": "Fisher's Exact Test",
                "error": f"Requires a 2x2 table, got {ct.shape[0]}x{ct.shape[1]}. "
                         "Reduce to 2 levels per variable or use Chi-square.",
            }

        oddsratio, p_value = _fisher(ct.values, alternative="two-sided")

        a, b, c, d = ct.values.ravel().astype(float)

        # Confidence interval for odds ratio (Woolf logit method)
        if 0 in (a, b, c, d):
            # Haldane-Anscombe continuity correction
            a_c, b_c, c_c, d_c = a + 0.5, b + 0.5, c + 0.5, d + 0.5
        else:
            a_c, b_c, c_c, d_c = a, b, c, d

        log_or = np.log(a_c * d_c / (b_c * c_c))
        se_log_or = np.sqrt(1.0 / a_c + 1.0 / b_c + 1.0 / c_c + 1.0 / d_c)
        ci_lower = float(np.exp(log_or - 1.96 * se_log_or))
        ci_upper = float(np.exp(log_or + 1.96 * se_log_or))

        # Relative risk
        rr = None
        if (a + b) > 0 and (c + d) > 0 and c > 0:
            rr = float((a / (a + b)) / (c / (c + d)))

        return {
            "test_name": "Fisher's Exact Test",
            "odds_ratio": float(oddsratio),
            "p_val": float(p_value),
            "CI95_odds_ratio": (ci_lower, ci_upper),
            "relative_risk": rr,
            "contingency_table": ct.to_dict(),
            "result_df": [{"odds_ratio": float(oddsratio), "p_value": float(p_value),
                           "CI_lower": ci_lower, "CI_upper": ci_upper}],
        }
    except Exception as e:
        return {"error": f"Fisher's exact test failed: {e}"}


def run_welch_anova(df: pd.DataFrame, dv: str, between: str) -> dict:
    """Welch's one-way ANOVA (robust to unequal variances)."""
    try:
        import pingouin as pg
        df_clean = df[[dv, between]].dropna()
        removed = len(df) - len(df_clean)
        groups = df_clean[between].unique()
        if len(groups) < 2:
            return {"error": f"Need at least 2 groups, found {len(groups)}."}
        for g in groups:
            n_g = (df_clean[between] == g).sum()
            if n_g < 2:
                return {"error": f"Group '{g}' has fewer than 2 observations (n={n_g})."}
        result = pg.welch_anova(data=df_clean, dv=dv, between=between)
        p_val = float(result["p_unc"].iloc[0])
        posthoc = None
        if p_val < 0.05:
            posthoc = pg.pairwise_gameshowell(data=df_clean, dv=dv, between=between)
        # Compute eta-squared: F * df_between / (F * df_between + df_within)
        f_val = float(result["F"].iloc[0])
        df_b = int(result["ddof1"].iloc[0])
        df_w = float(result["ddof2"].iloc[0])
        eta_sq = (f_val * df_b) / (f_val * df_b + df_w) if (f_val * df_b + df_w) > 0 else None

        return {
            "test_name": "Welch's ANOVA",
            "F": f_val,
            "p_val": p_val,
            "eta_squared": eta_sq,
            "df_between": df_b,
            "df_within": df_w,
            "result_df": result.to_dict("records"),
            "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Welch's ANOVA failed: {e}"}


def run_logistic_regression(
    df: pd.DataFrame,
    target: str,
    features: list[str],
) -> dict:
    """Logistic regression for binary outcome."""
    try:
        import statsmodels.api as sm

        df_work = df[[target] + features].copy()
        initial_len = len(df_work)

        y = df_work[target].copy()
        if y.dtype == object or y.dtype.name == "category":
            levels = sorted(y.dropna().unique())
            if len(levels) != 2:
                return {"error": f"Outcome must have exactly 2 levels, got {len(levels)}."}
            y = (y == levels[1]).astype(int)
        else:
            unique_vals = sorted(y.dropna().unique())
            if len(unique_vals) != 2:
                return {"error": f"Outcome must have exactly 2 unique values, got {len(unique_vals)}."}
            # Map any two numeric levels to 0/1 (e.g. {1,2} -> {0,1})
            if set(unique_vals) != {0, 1}:
                y = (y == unique_vals[1]).astype(int)

        X = df_work[features].copy().astype(float)
        X = sm.add_constant(X)

        mask = ~(X.isna().any(axis=1) | y.isna())
        X_clean = X[mask]
        y_clean = y[mask]
        removed = initial_len - len(y_clean)

        min_obs = len(features) + 10
        if len(y_clean) < min_obs:
            return {"error": f"Need at least {min_obs} observations, have {len(y_clean)}."}

        model = sm.Logit(y_clean, X_clean)
        try:
            result = model.fit(disp=0, maxiter=100)
        except Exception as e:
            return {"error": f"Model did not converge: {e}"}

        coef_names = [c for c in X_clean.columns if c != "const"]

        coefficients = {}
        odds_ratios = {}
        p_values = {}
        ci95 = {}
        conf = result.conf_int()
        for n in coef_names:
            coefficients[n] = float(result.params[n])
            odds_ratios[n] = float(np.exp(result.params[n]))
            p_values[n] = float(result.pvalues[n])
            ci95[n] = (float(conf.loc[n, 0]), float(conf.loc[n, 1]))

        summary_table = result.summary2().tables[1]
        result_df = summary_table.to_dict("records") if hasattr(summary_table, "to_dict") else []

        return {
            "test_name": "Logistic Regression",
            "coefficients": coefficients,
            "odds_ratios": odds_ratios,
            "p_values": p_values,
            "ci95": ci95,
            "pseudo_r_squared": float(result.prsquared),
            "aic": float(result.aic),
            "bic": float(result.bic),
            "result_df": result_df,
            "y_pred_proba": result.predict(X_clean).tolist(),
            "y_true": y_clean.tolist(),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Logistic regression failed: {e}"}


def compute_roc_curve(y_true, y_scores, pos_label: int = 1) -> dict:
    """Compute ROC curve and AUC with bootstrap CI and Youden's optimal threshold."""
    try:
        from sklearn.metrics import roc_curve, roc_auc_score

        y_true = np.asarray(y_true, dtype=int)
        y_scores = np.asarray(y_scores, dtype=float)

        # Drop NaN
        mask = ~(np.isnan(y_scores))
        y_true = y_true[mask]
        y_scores = y_scores[mask]
        removed = int((~mask).sum())

        unique_classes = np.unique(y_true)
        if len(unique_classes) < 2:
            return {"error": "ROC requires both positive and negative examples."}

        fpr, tpr, thresholds = roc_curve(y_true, y_scores, pos_label=pos_label)
        auc_val = roc_auc_score(y_true, y_scores)

        # Bootstrap CI for AUC
        n_bootstraps = 1000
        rng = np.random.default_rng(42)
        bootstrapped_aucs = []
        for _ in range(n_bootstraps):
            indices = rng.choice(len(y_true), len(y_true), replace=True)
            if len(np.unique(y_true[indices])) < 2:
                continue
            bootstrapped_aucs.append(roc_auc_score(y_true[indices], y_scores[indices]))

        if len(bootstrapped_aucs) > 0:
            ci_lower = float(np.percentile(bootstrapped_aucs, 2.5))
            ci_upper = float(np.percentile(bootstrapped_aucs, 97.5))
        else:
            ci_lower = float(auc_val)
            ci_upper = float(auc_val)

        # Youden's J statistic for optimal threshold
        j_scores = tpr - fpr
        optimal_idx = int(np.argmax(j_scores))

        return {
            "test_name": "ROC Curve & AUC",
            "fpr": fpr.tolist(),
            "tpr": tpr.tolist(),
            "thresholds": thresholds.tolist(),
            "auc": float(auc_val),
            "ci95_auc": (ci_lower, ci_upper),
            "optimal_threshold": float(thresholds[optimal_idx]),
            "optimal_sensitivity": float(tpr[optimal_idx]),
            "optimal_specificity": float(1 - fpr[optimal_idx]),
            "youden_j": float(j_scores[optimal_idx]),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"ROC curve computation failed: {e}"}


# ===================================================================
#  2. ASSUMPTION CHECKS
# ===================================================================

def check_normality(x, label: str = "sample") -> dict:
    """Check normality. Shapiro-Wilk for n < 5000, D'Agostino-Pearson otherwise."""
    try:
        from scipy import stats
        x_c, removed = _clean_single(x)
        n = len(x_c)
        if n < 3:
            return {
                "test": "n/a", "statistic": None, "p_val": None,
                "normal": None,
                "message": f"Too few observations (n={n}) to test normality.",
                "nan_removed": removed,
            }
        if np.std(x_c) == 0:
            return {
                "test": "n/a", "statistic": None, "p_val": None,
                "normal": None,
                "message": f"{label}: Zero variance. Normality test not applicable.",
                "nan_removed": removed,
            }
        if n < 5000:
            stat, p = stats.shapiro(x_c)
            test_name = "Shapiro-Wilk"
        else:
            stat, p = stats.normaltest(x_c)
            test_name = "D'Agostino-Pearson"
        return {
            "test": test_name,
            "statistic": float(stat),
            "p_val": float(p),
            "normal": bool(p > 0.05),
            "message": (
                f"{label}: {test_name} W={stat:.4f}, p={p:.4f} -- "
                f"{'Normal' if p > 0.05 else 'Not normal'}"
            ),
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Normality check failed: {e}"}


def check_equal_variance(*groups) -> dict:
    """Levene's test for equal variance."""
    try:
        from scipy import stats
        cleaned_groups = []
        total_removed = 0
        for g in groups:
            g_c, rem = _clean_single(g)
            cleaned_groups.append(g_c)
            total_removed += rem
        if any(len(g) < 2 for g in cleaned_groups):
            return {
                "test": "Levene's", "statistic": None, "p_val": None,
                "equal": None,
                "message": "At least one group has fewer than 2 observations.",
                "nan_removed": total_removed,
            }
        stat, p = stats.levene(*cleaned_groups)
        return {
            "test": "Levene's",
            "statistic": float(stat),
            "p_val": float(p),
            "equal": bool(p > 0.05),
            "message": (
                f"Levene's F={stat:.4f}, p={p:.4f} -- "
                f"{'Equal variance' if p > 0.05 else 'Unequal variance'}"
            ),
            "nan_removed": total_removed,
        }
    except Exception as e:
        return {"error": f"Equal variance check failed: {e}"}


def apply_multiple_comparison_correction(
    p_values: list[float],
    method: str = "bonferroni",
) -> list:
    """Apply multiple testing correction via pingouin.multicomp.

    Supported methods: 'bonferroni', 'holm', 'fdr_bh'.
    Returns adjusted p-values as a list of floats.
    """
    try:
        if not p_values:
            return []
        import pingouin as pg
        reject, p_adj = pg.multicomp(p_values, method=method)
        return p_adj.tolist()
    except Exception as e:
        return [{"error": f"Multiple comparison correction failed: {e}"}]


def compute_bland_altman(
    method1,
    method2,
    method1_name: str = "Method 1",
    method2_name: str = "Method 2",
) -> dict:
    """Bland-Altman analysis for method comparison."""
    try:
        from scipy import stats

        m1 = np.asarray(method1, dtype=float)
        m2 = np.asarray(method2, dtype=float)

        if len(m1) != len(m2):
            return {"error": f"Arrays must have the same length. Got {len(m1)} and {len(m2)}."}

        mask = ~(np.isnan(m1) | np.isnan(m2))
        m1_c, m2_c = m1[mask], m2[mask]
        removed = int((~mask).sum())
        n = len(m1_c)

        if n < 10:
            return {"error": f"Bland-Altman requires at least 10 paired observations (n={n})."}

        means = ((m1_c + m2_c) / 2).tolist()
        diffs = (m1_c - m2_c).tolist()
        mean_diff = float(np.mean(diffs))
        sd_diff = float(np.std(diffs, ddof=1))

        if sd_diff == 0:
            return {
                "test_name": "Bland-Altman",
                "warning": "No variation between methods. All differences are identical.",
                "mean_diff": mean_diff,
                "sd_diff": 0.0,
                "upper_loa": mean_diff,
                "lower_loa": mean_diff,
                "means": means,
                "diffs": diffs,
                "n": n,
                "nan_removed": removed,
            }

        upper_loa = mean_diff + 1.96 * sd_diff
        lower_loa = mean_diff - 1.96 * sd_diff

        se_mean = sd_diff / np.sqrt(n)
        t_crit = stats.t.ppf(0.975, n - 1)
        ci_mean = (float(mean_diff - t_crit * se_mean), float(mean_diff + t_crit * se_mean))

        se_loa = np.sqrt(3.0 * sd_diff ** 2 / n)
        ci_upper_loa = (float(upper_loa - t_crit * se_loa), float(upper_loa + t_crit * se_loa))
        ci_lower_loa = (float(lower_loa - t_crit * se_loa), float(lower_loa + t_crit * se_loa))

        # Proportional bias check
        slope, intercept, r_val, p_val, se_slope = stats.linregress(means, diffs)

        return {
            "test_name": "Bland-Altman",
            "mean_diff": mean_diff,
            "sd_diff": sd_diff,
            "upper_loa": float(upper_loa),
            "lower_loa": float(lower_loa),
            "ci95_mean_diff": ci_mean,
            "ci95_upper_loa": ci_upper_loa,
            "ci95_lower_loa": ci_lower_loa,
            "means": means,
            "diffs": diffs,
            "proportional_bias_p": float(p_val),
            "proportional_bias_slope": float(slope),
            "n": n,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Bland-Altman analysis failed: {e}"}


# ===================================================================
#  3. CURVE FITTING
# ===================================================================

# --- Initial parameter guess algorithms ---

def _guess_4pl(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Bottom = min(y), Top = max(y), LogIC50 = median(x), Hill = 1."""
    return [float(np.nanmin(y)), float(np.nanmax(y)), float(np.nanmedian(x)), 1.0]


def _guess_mm(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Vmax = max(y)*1.1, Km = x at half-max-y."""
    vmax = float(np.nanmax(y)) * 1.1
    half = vmax / 2
    idx = np.argmin(np.abs(y - half))
    km = float(x[idx]) if len(x) > 0 else 1.0
    return [vmax, max(km, 1e-10)]


def _guess_hill(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Bmax = max(y)*1.1, Kd = x at half-max, n = 1."""
    bmax = float(np.nanmax(y)) * 1.1
    half = bmax / 2
    idx = np.argmin(np.abs(y - half))
    kd = float(x[idx]) if len(x) > 0 else 1.0
    return [bmax, max(kd, 1e-10), 1.0]


def _guess_exp_decay(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Y0 = y at min(x), Plateau = y at max(x), K = rough estimate."""
    sort_idx = np.argsort(x)
    y0 = float(y[sort_idx[0]])
    plateau = float(y[sort_idx[-1]])
    x_range = float(x[sort_idx[-1]] - x[sort_idx[0]])
    k = 1.0 / (x_range + 1e-10)
    return [y0, plateau, abs(k)]


def _guess_one_site_binding(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Bmax = max(y)*1.1, Kd = x at half-max."""
    bmax = float(np.nanmax(y)) * 1.1
    half = bmax / 2
    idx = np.argmin(np.abs(y - half))
    kd = float(x[idx]) if len(x) > 0 else 1.0
    return [max(bmax, 1e-10), max(kd, 1e-10)]


def _guess_two_site_binding(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 0.6,
        float(np.nanmedian(x)) * 0.1 if np.nanmedian(x) > 0 else 0.1,
        float(np.nanmax(y)) * 0.4,
        float(np.nanmedian(x)) * 10 if np.nanmedian(x) > 0 else 10.0,
    ]


def _guess_competitive_binding(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.1,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
    ]


def _guess_saturation_nsb(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [float(np.nanmax(y)) * 0.8, float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0, 0.01]


def _guess_substrate_inhibition(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.2,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        float(np.nanmax(x)) * 5 if np.nanmax(x) > 0 else 50.0,
    ]


def _guess_allosteric_sigmoidal(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.1,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        2.0,
    ]


def _guess_competitive_inhibition(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.1,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
    ]


def _guess_uncompetitive_inhibition(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.1,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        float(np.nanmedian(x)) * 5 if np.nanmedian(x) > 0 else 5.0,
    ]


def _guess_noncompetitive_inhibition(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [
        float(np.nanmax(y)) * 1.5,
        float(np.nanmedian(x)) if np.nanmedian(x) > 0 else 1.0,
        float(np.nanmedian(x)) * 5 if np.nanmedian(x) > 0 else 5.0,
    ]


def _guess_exp_growth(x: np.ndarray, y: np.ndarray) -> list[float]:
    y0 = float(y[np.argmin(x)]) if len(y) > 0 else 1.0
    return [max(y0, 1e-10), 0.1]


def _guess_logistic_growth(x: np.ndarray, y: np.ndarray) -> list[float]:
    k_cap = float(np.nanmax(y)) * 1.1
    y_pos = y[y > 0]
    y0 = float(np.nanmin(y_pos)) if len(y_pos) > 0 else 0.1
    return [max(k_cap, 1e-10), max(y0, 1e-10), 0.1]


def _guess_gompertz(x: np.ndarray, y: np.ndarray) -> list[float]:
    a = float(np.nanmax(y)) if np.nanmax(y) > 0 else 1.0
    mu = float(np.nanmax(np.diff(y))) if len(y) > 1 else 1.0
    lag = float(x[0]) if len(x) > 0 else 0.0
    return [max(a, 1e-10), max(mu, 1e-10), lag]


def _guess_one_compartment_iv(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [float(np.nanmax(y)) if np.nanmax(y) > 0 else 1.0, 0.1]


def _guess_one_compartment_oral(x: np.ndarray, y: np.ndarray) -> list[float]:
    return [float(np.nanmax(y)) * 5 if np.nanmax(y) > 0 else 5.0, 1.0, 0.1]


def _guess_two_compartment_iv(x: np.ndarray, y: np.ndarray) -> list[float]:
    ymax = float(np.nanmax(y)) if np.nanmax(y) > 0 else 1.0
    return [ymax * 0.7, 1.0, ymax * 0.3, 0.1]


def _guess_two_phase_decay(x: np.ndarray, y: np.ndarray) -> list[float]:
    span = float(np.nanmax(y) - np.nanmin(y)) if len(y) > 0 else 1.0
    plateau = float(np.nanmin(y)) if len(y) > 0 else 0.0
    return [span * 0.6, 1.0, span * 0.4, 0.1, plateau]


def _guess_plateau_then_decay(x: np.ndarray, y: np.ndarray) -> list[float]:
    y0 = float(np.nanmax(y)) if len(y) > 0 else 1.0
    # Heuristic: t_lag = x where y first drops below 95% of max
    threshold = y0 * 0.95
    below = np.where(y < threshold)[0]
    if len(below) > 0:
        t_lag = float(x[below[0]])
    else:
        t_lag = float(np.nanmedian(x))
    return [max(y0, 1e-10), 0.1, t_lag]


# --- Equation functions (defined as regular functions so they're picklable) ---

def _func_4pl(x, bottom, top, log_ic50, hill):
    return bottom + (top - bottom) / (1.0 + 10.0 ** ((log_ic50 - x) * hill))


def _func_one_site_binding(x, bmax, kd):
    return bmax * x / (kd + x)


def _func_two_site_binding(x, bmax1, kd1, bmax2, kd2):
    return bmax1 * x / (kd1 + x) + bmax2 * x / (kd2 + x)


def _func_competitive_binding(x, bmax, kd, ki):
    # Fixed inhibitor concentration is handled via partial application
    # This is the version with I already baked in via fixed_param_values
    # Default I=0 makes it reduce to one-site binding
    return bmax * x / (x + kd * (1.0 + 0.0 / (ki + 1e-300)))


def _func_competitive_binding_with_I(x, bmax, kd, ki, I):
    return bmax * x / (x + kd * (1.0 + I / ki))


def _func_saturation_nsb(x, bmax, kd, ns):
    return bmax * x / (kd + x) + ns * x


def _func_michaelis_menten(x, vmax, km):
    return vmax * x / (km + x)


def _func_substrate_inhibition(x, vmax, km, ki):
    return vmax * x / (km + x * (1.0 + x / ki))


def _func_allosteric_sigmoidal(x, vmax, k_half, n):
    return vmax * x ** n / (k_half ** n + x ** n)


def _func_competitive_inhibition_with_I(x, vmax, km, ki, I):
    return vmax * x / (x + km * (1.0 + I / ki))


def _func_uncompetitive_inhibition_with_I(x, vmax, km, ki, I):
    return vmax * x / (km + x * (1.0 + I / ki))


def _func_noncompetitive_inhibition_with_I(x, vmax, km, ki, I):
    return vmax * x / ((km + x) * (1.0 + I / ki))


def _func_hill(x, bmax, kd, n):
    return bmax * x ** n / (kd ** n + x ** n)


def _func_exp_decay(x, y0, plateau, k):
    return (y0 - plateau) * np.exp(-k * x) + plateau


def _func_linear(x, m, b):
    return m * x + b


def _func_quadratic(x, a, b, c):
    return a * x ** 2 + b * x + c


def _func_cubic(x, a, b, c, d):
    return a * x ** 3 + b * x ** 2 + c * x + d


def _func_quartic(x, a, b, c, d, e):
    return a * x ** 4 + b * x ** 3 + c * x ** 2 + d * x + e


def _func_exp_growth(x, y0, k):
    return y0 * np.exp(k * x)


def _func_logistic_growth(x, k_cap, y0, r):
    return k_cap / (1.0 + ((k_cap - y0) / (y0 + 1e-300)) * np.exp(-r * x))


def _func_gompertz(x, a, mu, lag):
    return a * np.exp(-np.exp(mu * np.e / (a + 1e-300) * (lag - x) + 1.0))


def _func_one_compartment_iv(x, d_vd, ke):
    return d_vd * np.exp(-ke * x)


def _func_one_compartment_oral(x, fdk_v, ka, ke):
    return fdk_v * ka / (ka - ke + 1e-300) * (np.exp(-ke * x) - np.exp(-ka * x))


def _func_two_compartment_iv(x, a, alpha, b, beta):
    return a * np.exp(-alpha * x) + b * np.exp(-beta * x)


def _func_two_phase_decay(x, span1, k1, span2, k2, plateau):
    return span1 * np.exp(-k1 * x) + span2 * np.exp(-k2 * x) + plateau


def _func_plateau_then_decay(x, y0, k, t_lag):
    return np.where(x < t_lag, y0, y0 * np.exp(-k * (x - t_lag)))


# --- BUILTIN_EQUATIONS dict (25 equations) ---

BUILTIN_EQUATIONS: dict[str, dict[str, Any]] = {
    # ----- Dose-Response -----
    "4PL (Dose-Response)": {
        "formula_display": "f(x) = Bottom + (Top - Bottom) / (1 + 10^((LogIC50 - x) * HillSlope))",
        "func": _func_4pl,
        "param_names": ["Bottom", "Top", "LogIC50", "HillSlope"],
        "initial_guess": _guess_4pl,
        "bounds": ([-np.inf, -np.inf, -np.inf, -np.inf], [np.inf, np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "4-Parameter Logistic for dose-response curves. X should be log10(concentration).",
        "category": "Dose-Response",
        "fixed_params": None,
    },

    # ----- Binding -----
    "One-Site Specific Binding": {
        "formula_display": "Y = Bmax * X / (Kd + X)",
        "func": _func_one_site_binding,
        "param_names": ["Bmax", "Kd"],
        "initial_guess": _guess_one_site_binding,
        "bounds": ([0, 0], [np.inf, np.inf]),
        "min_points": 4,
        "description": "Single binding site (identical to Michaelis-Menten form). X = ligand concentration, Y = bound fraction.",
        "category": "Binding",
        "fixed_params": None,
    },
    "Two-Site Binding": {
        "formula_display": "Y = Bmax1 * X / (Kd1 + X) + Bmax2 * X / (Kd2 + X)",
        "func": _func_two_site_binding,
        "param_names": ["Bmax1", "Kd1", "Bmax2", "Kd2"],
        "initial_guess": _guess_two_site_binding,
        "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Two independent binding sites with different affinities. Use when one-site fit is poor.",
        "category": "Binding",
        "fixed_params": None,
    },
    "Competitive Binding": {
        "formula_display": "Y = Bmax * X / (X + Kd * (1 + [I]/Ki))",
        "func": _func_competitive_binding_with_I,
        "param_names": ["Bmax", "Kd", "Ki"],
        "initial_guess": _guess_competitive_binding,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Binding in presence of competitive inhibitor at fixed concentration [I]. Ki = inhibitor dissociation constant.",
        "category": "Binding",
        "fixed_params": ["I_conc"],
    },
    "Saturation Binding (with NSB)": {
        "formula_display": "Y = Bmax * X / (Kd + X) + NS * X",
        "func": _func_saturation_nsb,
        "param_names": ["Bmax", "Kd", "NS"],
        "initial_guess": _guess_saturation_nsb,
        "bounds": ([0, 0, -np.inf], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "Saturation binding with non-specific binding (NSB) component. NS = slope of linear NSB.",
        "category": "Binding",
        "fixed_params": None,
    },
    "Hill Equation": {
        "formula_display": "Y = Bmax * x^n / (Kd^n + x^n)",
        "func": _func_hill,
        "param_names": ["Bmax", "Kd", "n"],
        "initial_guess": _guess_hill,
        "bounds": ([0, 0, 0], [np.inf, np.inf, 20]),
        "min_points": 5,
        "description": "Cooperative binding. n > 1 = positive cooperativity, n < 1 = negative.",
        "category": "Binding",
        "fixed_params": None,
    },

    # ----- Enzyme Kinetics -----
    "Michaelis-Menten": {
        "formula_display": "v = Vmax * [S] / (Km + [S])",
        "func": _func_michaelis_menten,
        "param_names": ["Vmax", "Km"],
        "initial_guess": _guess_mm,
        "bounds": ([0, 0], [np.inf, np.inf]),
        "min_points": 4,
        "description": "Enzyme kinetics. X = substrate concentration, Y = reaction velocity.",
        "category": "Enzyme Kinetics",
        "fixed_params": None,
    },
    "Substrate Inhibition": {
        "formula_display": "v = Vmax * [S] / (Km + [S] * (1 + [S]/Ki))",
        "func": _func_substrate_inhibition,
        "param_names": ["Vmax", "Km", "Ki"],
        "initial_guess": _guess_substrate_inhibition,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "Michaelis-Menten with substrate inhibition at high [S]. Velocity decreases beyond optimal [S].",
        "category": "Enzyme Kinetics",
        "fixed_params": None,
    },
    "Allosteric Sigmoidal": {
        "formula_display": "v = Vmax * [S]^n / (K_half^n + [S]^n)",
        "func": _func_allosteric_sigmoidal,
        "param_names": ["Vmax", "K_half", "n"],
        "initial_guess": _guess_allosteric_sigmoidal,
        "bounds": ([0, 0, 0.1], [np.inf, np.inf, 20]),
        "min_points": 5,
        "description": "Sigmoidal enzyme kinetics (Hill equation for enzymes). n > 1 = positive cooperativity.",
        "category": "Enzyme Kinetics",
        "fixed_params": None,
    },
    "Competitive Inhibition": {
        "formula_display": "v = Vmax * [S] / ([S] + Km * (1 + [I]/Ki))",
        "func": _func_competitive_inhibition_with_I,
        "param_names": ["Vmax", "Km", "Ki"],
        "initial_guess": _guess_competitive_inhibition,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Competitive enzyme inhibition. Fixed [I] increases apparent Km, Vmax unchanged.",
        "category": "Enzyme Kinetics",
        "fixed_params": ["I_conc"],
    },
    "Uncompetitive Inhibition": {
        "formula_display": "v = Vmax * [S] / (Km + [S] * (1 + [I]/Ki))",
        "func": _func_uncompetitive_inhibition_with_I,
        "param_names": ["Vmax", "Km", "Ki"],
        "initial_guess": _guess_uncompetitive_inhibition,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Uncompetitive inhibition. Decreases both apparent Vmax and Km by same factor.",
        "category": "Enzyme Kinetics",
        "fixed_params": ["I_conc"],
    },
    "Noncompetitive Inhibition": {
        "formula_display": "v = Vmax * [S] / ((Km + [S]) * (1 + [I]/Ki))",
        "func": _func_noncompetitive_inhibition_with_I,
        "param_names": ["Vmax", "Km", "Ki"],
        "initial_guess": _guess_noncompetitive_inhibition,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Noncompetitive (mixed) inhibition. Decreases apparent Vmax, Km unchanged.",
        "category": "Enzyme Kinetics",
        "fixed_params": ["I_conc"],
    },

    # ----- Growth -----
    "Exponential Growth": {
        "formula_display": "Y = Y0 * exp(K * x)",
        "func": _func_exp_growth,
        "param_names": ["Y0", "K"],
        "initial_guess": _guess_exp_growth,
        "bounds": ([0, -np.inf], [np.inf, np.inf]),
        "min_points": 3,
        "description": "Unlimited exponential growth. K > 0 = growth, K < 0 = decay.",
        "category": "Growth",
        "fixed_params": None,
    },
    "Logistic Growth": {
        "formula_display": "Y = K_cap / (1 + ((K_cap - Y0)/Y0) * exp(-r * x))",
        "func": _func_logistic_growth,
        "param_names": ["K_cap", "Y0", "r"],
        "initial_guess": _guess_logistic_growth,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "S-shaped growth with carrying capacity K_cap. Standard for bacterial/cell growth.",
        "category": "Growth",
        "fixed_params": None,
    },
    "Gompertz Growth": {
        "formula_display": "Y = A * exp(-exp(mu * e / A * (lag - x) + 1))",
        "func": _func_gompertz,
        "param_names": ["A", "mu", "lag"],
        "initial_guess": _guess_gompertz,
        "bounds": ([0, 0, -np.inf], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "Asymmetric sigmoidal growth. Common for tumor growth and microbial growth with lag phase.",
        "category": "Growth",
        "fixed_params": None,
    },

    # ----- Pharmacokinetics -----
    "One-Compartment IV Bolus": {
        "formula_display": "C(t) = D/Vd * exp(-Ke * t)",
        "func": _func_one_compartment_iv,
        "param_names": ["D_over_Vd", "Ke"],
        "initial_guess": _guess_one_compartment_iv,
        "bounds": ([0, 0], [np.inf, np.inf]),
        "min_points": 4,
        "description": "Plasma concentration after IV bolus. D/Vd = dose/volume of distribution. Ke = elimination rate.",
        "category": "Pharmacokinetics",
        "fixed_params": None,
    },
    "One-Compartment Oral": {
        "formula_display": "C(t) = F*D*Ka / (Vd*(Ka-Ke)) * (exp(-Ke*t) - exp(-Ka*t))",
        "func": _func_one_compartment_oral,
        "param_names": ["FDK_over_Vd", "Ka", "Ke"],
        "initial_guess": _guess_one_compartment_oral,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "Plasma concentration after oral dose. Ka = absorption rate, Ke = elimination rate. Ka must be > Ke.",
        "category": "Pharmacokinetics",
        "fixed_params": None,
    },
    "Two-Compartment IV": {
        "formula_display": "C(t) = A * exp(-alpha * t) + B * exp(-beta * t)",
        "func": _func_two_compartment_iv,
        "param_names": ["A", "alpha", "B", "beta"],
        "initial_guess": _guess_two_compartment_iv,
        "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
        "min_points": 6,
        "description": "Bi-exponential PK model. Fast (alpha) distribution phase + slow (beta) elimination phase.",
        "category": "Pharmacokinetics",
        "fixed_params": None,
    },

    # ----- Decay -----
    "Exponential Decay": {
        "formula_display": "Y = (Y0 - Plateau) * exp(-K * x) + Plateau",
        "func": _func_exp_decay,
        "param_names": ["Y0", "Plateau", "K"],
        "initial_guess": _guess_exp_decay,
        "bounds": ([-np.inf, -np.inf, 0], [np.inf, np.inf, np.inf]),
        "min_points": 4,
        "description": "One-phase exponential decay (e.g., drug elimination, radioactive decay).",
        "category": "Decay",
        "fixed_params": None,
    },
    "Two-Phase Decay": {
        "formula_display": "Y = Span1 * exp(-K1 * x) + Span2 * exp(-K2 * x) + Plateau",
        "func": _func_two_phase_decay,
        "param_names": ["Span1", "K1", "Span2", "K2", "Plateau"],
        "initial_guess": _guess_two_phase_decay,
        "bounds": ([0, 0, 0, 0, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf]),
        "min_points": 7,
        "description": "Bi-exponential decay. Fast and slow components (e.g., protein degradation with two pathways).",
        "category": "Decay",
        "fixed_params": None,
    },
    "Plateau Then Decay": {
        "formula_display": "Y = IF(x < t_lag, Y0, Y0 * exp(-K * (x - t_lag)))",
        "func": _func_plateau_then_decay,
        "param_names": ["Y0", "K", "t_lag"],
        "initial_guess": _guess_plateau_then_decay,
        "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "Stable plateau followed by exponential decay after a lag time. Common for protein stability assays.",
        "category": "Decay",
        "fixed_params": None,
    },

    # ----- Polynomial -----
    "Linear": {
        "formula_display": "Y = m * x + b",
        "func": _func_linear,
        "param_names": ["Slope (m)", "Intercept (b)"],
        "initial_guess": lambda x, y: [1.0, 0.0],
        "bounds": ([-np.inf, -np.inf], [np.inf, np.inf]),
        "min_points": 3,
        "description": "Simple linear regression.",
        "category": "Polynomial",
        "fixed_params": None,
    },
    "Quadratic": {
        "formula_display": "Y = a*x^2 + b*x + c",
        "func": _func_quadratic,
        "param_names": ["a", "b", "c"],
        "initial_guess": lambda x, y: [0.0, 1.0, 0.0],
        "bounds": ([-np.inf] * 3, [np.inf] * 3),
        "min_points": 4,
        "description": "Quadratic polynomial.",
        "category": "Polynomial",
        "fixed_params": None,
    },
    "Cubic": {
        "formula_display": "Y = a*x^3 + b*x^2 + c*x + d",
        "func": _func_cubic,
        "param_names": ["a", "b", "c", "d"],
        "initial_guess": lambda x, y: [0.0, 0.0, 1.0, 0.0],
        "bounds": ([-np.inf] * 4, [np.inf] * 4),
        "min_points": 5,
        "description": "Cubic polynomial.",
        "category": "Polynomial",
        "fixed_params": None,
    },
    "Quartic": {
        "formula_display": "Y = a*x^4 + b*x^3 + c*x^2 + d*x + e",
        "func": _func_quartic,
        "param_names": ["a", "b", "c", "d", "e"],
        "initial_guess": lambda x, y: [0.0, 0.0, 0.0, 1.0, 0.0],
        "bounds": ([-np.inf] * 5, [np.inf] * 5),
        "min_points": 6,
        "description": "Quartic polynomial.",
        "category": "Polynomial",
        "fixed_params": None,
    },
}


def fit_curve(
    x,
    y,
    equation_name: str,
    fixed_param_values: dict[str, float] | None = None,
    max_iterations: int = 10_000,
) -> dict:
    """Master curve fitting function.

    For equations with fixed_params (e.g. inhibitor concentration),
    pass fixed_param_values={"I_conc": 1.0} to bake in the value.

    Returns dict with params, errors, CI, R-squared, AIC, BIC,
    confidence/prediction bands, residuals, and convergence info.
    """
    try:
        from scipy.optimize import curve_fit
        from scipy.stats import t as t_dist
        from scipy.optimize import approx_fprime

        x = np.asarray(x, dtype=float)
        y = np.asarray(y, dtype=float)

        if equation_name not in BUILTIN_EQUATIONS:
            return {"converged": False, "message": f"Unknown equation: {equation_name}"}

        eq = BUILTIN_EQUATIONS[equation_name]
        func = eq["func"]
        param_names = list(eq["param_names"])
        p0 = list(eq["initial_guess"](x, y))
        bounds_lower = list(eq["bounds"][0])
        bounds_upper = list(eq["bounds"][1])

        # Handle fixed parameters by creating a partial function
        if eq.get("fixed_params") and fixed_param_values:
            for fp_name in eq["fixed_params"]:
                if fp_name in fixed_param_values:
                    fp_val = fixed_param_values[fp_name]
                    # The original func signature has the fixed param as the last arg
                    # Create a wrapper that injects the fixed value
                    _original_func = func
                    _fp_val = fp_val

                    def _make_wrapper(orig_fn, val):
                        def wrapper(x_val, *params):
                            return orig_fn(x_val, *params, val)
                        return wrapper

                    func = _make_wrapper(_original_func, _fp_val)
                    # param_names, p0, bounds already exclude the fixed param
                    # (they are defined in the dict without the fixed param)
        elif eq.get("fixed_params") and not fixed_param_values:
            # Fixed params required but not provided -- use default I=1.0
            for fp_name in eq["fixed_params"]:
                _original_func = func
                _default_val = 1.0

                def _make_default_wrapper(orig_fn, val):
                    def wrapper(x_val, *params):
                        return orig_fn(x_val, *params, val)
                    return wrapper

                func = _make_default_wrapper(_original_func, _default_val)

        n_params = len(param_names)

        # Remove NaN pairs
        mask = ~(np.isnan(x) | np.isnan(y))
        x_clean, y_clean = x[mask], y[mask]
        nan_removed = int((~mask).sum())
        n = len(x_clean)

        if n <= n_params:
            return {
                "converged": False,
                "message": f"Need at least {n_params + 1} data points for {n_params} parameters. Have {n}.",
                "nan_removed": nan_removed,
            }

        # Ensure initial guesses are within bounds
        for i in range(len(p0)):
            lo = bounds_lower[i]
            hi = bounds_upper[i]
            if np.isfinite(lo) and p0[i] < lo:
                p0[i] = lo + abs(lo) * 0.01 + 1e-10
            if np.isfinite(hi) and p0[i] > hi:
                p0[i] = hi - abs(hi) * 0.01 - 1e-10

        bounds = (bounds_lower, bounds_upper)

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                popt, pcov = curve_fit(
                    func, x_clean, y_clean,
                    p0=p0, bounds=bounds,
                    maxfev=max_iterations, full_output=False,
                )
        except RuntimeError as e:
            return {"converged": False, "message": f"Fit did not converge: {e}", "nan_removed": nan_removed}
        except ValueError as e:
            return {"converged": False, "message": f"Invalid input: {e}", "nan_removed": nan_removed}

        # Standard errors from covariance matrix
        if np.any(np.isinf(pcov)):
            perr = np.full(n_params, np.inf)
        else:
            perr = np.sqrt(np.diag(pcov))

        # Confidence intervals (95%)
        alpha = 0.05
        dof = max(n - n_params, 1)
        tval = t_dist.ppf(1.0 - alpha / 2.0, dof)
        param_ci = {
            name: (float(p - tval * e), float(p + tval * e))
            for name, p, e in zip(param_names, popt, perr)
        }

        # R-squared
        y_fit = func(x_clean, *popt)
        ss_res = np.sum((y_clean - y_fit) ** 2)
        ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
        r_squared = float(1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        adj_r_squared = (
            float(1.0 - (1.0 - r_squared) * (n - 1) / (n - n_params - 1))
            if n > n_params + 1 else r_squared
        )

        # AIC / BIC
        mse = ss_res / n
        aic = float(n * np.log(mse + 1e-300) + 2 * n_params)
        bic = float(n * np.log(mse + 1e-300) + n_params * np.log(n))

        # Residuals
        residuals = (y_clean - y_fit).tolist()

        # Smooth curve for plotting
        x_min, x_max = float(np.nanmin(x_clean)), float(np.nanmax(x_clean))
        x_smooth = np.linspace(x_min, x_max, 200)

        try:
            y_smooth = func(x_smooth, *popt)
        except Exception:
            y_smooth = np.full_like(x_smooth, np.nan)

        # Confidence and prediction bands (delta method via Jacobian)
        s = np.sqrt(ss_res / dof)  # residual standard error

        try:
            J = np.array([
                approx_fprime(popt, lambda p, xi=xi: float(func(np.array([xi]), *p)[0])
                              if hasattr(func(np.array([xi]), *p), '__len__')
                              else float(func(xi, *p)),
                              1e-8)
                for xi in x_smooth
            ])
            var_ci = np.array([j @ pcov @ j for j in J])
            var_ci = np.clip(var_ci, 0, None)  # Guard negative from numerical noise
            ci_band = tval * s * np.sqrt(var_ci)
            pi_band = tval * s * np.sqrt(1.0 + var_ci)
            # Replace any NaN/Inf with flat fallback
            flat_ci = tval * s
            flat_pi = tval * s * np.sqrt(2.0)
            ci_band = np.where(np.isfinite(ci_band), ci_band, flat_ci)
            pi_band = np.where(np.isfinite(pi_band), pi_band, flat_pi)
        except Exception:
            # Fallback: flat bands
            ci_band = np.full_like(x_smooth, tval * s)
            pi_band = np.full_like(x_smooth, tval * s * np.sqrt(2.0))

        return {
            "params": dict(zip(param_names, [float(p) for p in popt])),
            "param_errors": dict(zip(param_names, [float(e) for e in perr])),
            "param_ci95": param_ci,
            "r_squared": r_squared,
            "adj_r_squared": adj_r_squared,
            "aic": aic,
            "bic": bic,
            "residuals": residuals,
            "y_fit": y_fit.tolist(),
            "x_smooth": x_smooth.tolist(),
            "y_smooth": y_smooth.tolist() if hasattr(y_smooth, 'tolist') else list(y_smooth),
            "ci_lower": (y_smooth - ci_band).tolist(),
            "ci_upper": (y_smooth + ci_band).tolist(),
            "pi_lower": (y_smooth - pi_band).tolist(),
            "pi_upper": (y_smooth + pi_band).tolist(),
            "converged": True,
            "message": "Fit converged successfully.",
            "nan_removed": nan_removed,
        }
    except Exception as e:
        return {"converged": False, "message": f"Curve fitting failed: {e}"}


def parse_custom_equation(expr: str) -> tuple:
    """Parse a safe mathematical expression string into a callable and parameter names.

    Example: "a * exp(-b * x) + c" -> (func, ["a", "b", "c"])

    Raises ValueError if expression is unsafe or malformed.
    """
    tree = ast.parse(expr, mode="eval")

    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
                raise ValueError(f"Unsupported function: {ast.dump(node.func)}")
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                               ast.ClassDef, ast.AsyncFunctionDef, ast.Attribute)):
            raise ValueError(
                "Unsafe expression: imports, classes, and attribute access are not allowed."
            )

    param_names = sorted(names - _SAFE_NAMES - {"x"})
    if "x" not in names:
        raise ValueError("Expression must contain 'x' as the independent variable.")
    if not param_names:
        raise ValueError("Expression must contain at least one parameter besides 'x'.")

    code = compile(tree, "<custom_equation>", "eval")

    def _func(x_val, *args):
        namespace = {**_SAFE_FUNCS, "x": x_val}
        for name, val in zip(param_names, args):
            namespace[name] = val
        return eval(code, {"__builtins__": {}}, namespace)  # noqa: S307

    return _func, param_names


# ===================================================================
#  4. SURVIVAL ANALYSIS
# ===================================================================

def run_kaplan_meier(
    time,
    event,
    group=None,
) -> dict:
    """Run Kaplan-Meier survival estimation.

    Returns curves with CI, at-risk counts, and median survival per group.
    """
    try:
        from lifelines import KaplanMeierFitter

        time = np.asarray(time, dtype=float)
        event = np.asarray(event, dtype=int)

        # Validate
        mask = ~(np.isnan(time) | np.isnan(event.astype(float)))
        if group is not None:
            group = np.asarray(group, dtype=object)
            # Mask out None/NaN group labels
            group_valid = np.array([
                g is not None and str(g) not in ("nan", "NaN", "")
                for g in group
            ])
            mask = mask & group_valid
        time_c = time[mask]
        event_c = event[mask]
        removed = int((~mask).sum())

        if len(time_c) == 0:
            return {"error": "No valid observations after removing NaN."}
        if (time_c < 0).any():
            return {"error": "Time column contains negative values. Survival analysis requires non-negative times."}
        if event_c.sum() == 0:
            return {"error": "No events observed. Cannot estimate survival."}

        if group is not None:
            group_c = np.asarray(group[mask], dtype=str)
        else:
            group_c = np.array(["All"] * len(time_c))

        results = {"curves": {}, "median_survival": {}, "nan_removed": removed}

        for grp_name in np.unique(group_c):
            grp_mask = group_c == grp_name
            kmf = KaplanMeierFitter()
            kmf.fit(time_c[grp_mask], event_observed=event_c[grp_mask], label=str(grp_name))

            ci = kmf.confidence_interval_survival_function_
            results["curves"][str(grp_name)] = {
                "timeline": kmf.timeline.tolist(),
                "survival": kmf.survival_function_.iloc[:, 0].tolist(),
                "ci_lower": ci.iloc[:, 0].tolist(),
                "ci_upper": ci.iloc[:, 1].tolist(),
                "at_risk": kmf.event_table["at_risk"].tolist(),
            }
            median = kmf.median_survival_time_
            results["median_survival"][str(grp_name)] = (
                float(median) if not np.isinf(median) else None
            )

        return results
    except Exception as e:
        return {"error": f"Kaplan-Meier estimation failed: {e}"}


def run_logrank(
    time,
    event,
    group,
    weighted: bool = False,
) -> dict:
    """Log-rank test comparing survival between groups.

    If weighted=True, uses Wilcoxon (Gehan-Breslow) weighting.
    """
    try:
        from lifelines.statistics import logrank_test, multivariate_logrank_test

        time = np.asarray(time, dtype=float)
        event = np.asarray(event, dtype=int)
        group = np.asarray(group, dtype=object)

        mask = ~(np.isnan(time) | np.isnan(event.astype(float)))
        # Mask out None/NaN group labels
        group_valid = np.array([
            g is not None and str(g) not in ("nan", "NaN", "")
            for g in group
        ])
        mask = mask & group_valid
        time_c, event_c = time[mask], event[mask]
        group_c = np.asarray(group[mask], dtype=str)
        removed = int((~mask).sum())

        if len(time_c) == 0:
            return {"error": "No valid observations after removing NaN."}

        groups = np.unique(group_c)
        if len(groups) < 2:
            return {"error": f"Need at least 2 groups for log-rank test, found {len(groups)}."}

        if len(groups) == 2:
            mask1 = group_c == groups[0]
            mask2 = group_c == groups[1]
            result = logrank_test(
                time_c[mask1], time_c[mask2],
                event_observed_A=event_c[mask1],
                event_observed_B=event_c[mask2],
                weightings="wilcoxon" if weighted else None,
            )
            return {
                "test_name": "Wilcoxon (Gehan-Breslow)" if weighted else "Log-rank",
                "test_statistic": float(result.test_statistic),
                "p_val": float(result.p_value),
                "groups": groups.tolist(),
                "nan_removed": removed,
            }
        else:
            result = multivariate_logrank_test(time_c, group_c, event_c)
            return {
                "test_name": "Multivariate log-rank",
                "test_statistic": float(result.test_statistic),
                "p_val": float(result.p_value),
                "groups": groups.tolist(),
                "nan_removed": removed,
            }
    except Exception as e:
        return {"error": f"Log-rank test failed: {e}"}


def run_cox_regression(
    df: pd.DataFrame,
    duration_col: str = "time",
    event_col: str = "event",
    covariates: list[str] | None = None,
) -> dict:
    """Fit Cox Proportional Hazards model."""
    try:
        from lifelines import CoxPHFitter

        fit_cols = [duration_col, event_col] + (covariates or [])
        df_clean = df[fit_cols].dropna()
        removed = len(df) - len(df_clean)

        if len(df_clean) < 10:
            return {"error": f"Need at least 10 observations for Cox regression (n={len(df_clean)})."}
        if df_clean[event_col].sum() == 0:
            return {"error": "No events observed. Cannot fit Cox model."}
        if (df_clean[duration_col] < 0).any():
            return {"error": "Duration column contains negative values."}

        cph = CoxPHFitter()
        cph.fit(df_clean, duration_col=duration_col, event_col=event_col)

        summary = cph.summary

        # PH assumption test — capture stdout output and parse violations
        ph_violations = []
        try:
            import io
            import contextlib

            f = io.StringIO()
            with contextlib.redirect_stdout(f), contextlib.redirect_stderr(f):
                cph.check_assumptions(df_clean, p_value_threshold=0.05, show_plots=False)
            ph_output = f.getvalue()

            # Parse the Schoenfeld test results from summary table
            ph_results = cph.summary
            for covar in (covariates or []):
                try:
                    # lifelines stores PH test p-values via proportional_hazard_test
                    from lifelines.statistics import proportional_hazard_test
                    ph_df = proportional_hazard_test(cph, df_clean, time_transform="rank")
                    for idx in ph_df.summary.index:
                        p = float(ph_df.summary.loc[idx, "p"])
                        if p < 0.05:
                            ph_violations.append(
                                f"{idx}: p={p:.4f} — PH assumption may be violated"
                            )
                    break  # Only need to run once
                except Exception:
                    # Fallback: extract from stdout
                    if "reject" in ph_output.lower() or "violated" in ph_output.lower():
                        ph_violations.append(ph_output.strip()[:300])
                    break
        except Exception:
            pass

        hazard_ratios = {}
        for row in summary.index:
            hazard_ratios[row] = float(summary.loc[row, "exp(coef)"])

        return {
            "test_name": "Cox Proportional Hazards",
            "summary_df": summary.reset_index().to_dict("records"),
            "concordance": float(cph.concordance_index_),
            "log_likelihood": float(cph.log_likelihood_),
            "aic": float(cph.AIC_partial_),
            "hazard_ratios": hazard_ratios,
            "ph_assumption": ph_violations,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Cox regression failed: {e}"}


# ===================================================================
#  5. TIER 2
# ===================================================================

def run_pca(df: pd.DataFrame, n_components: int = 2) -> dict:
    """PCA with standardization.

    Returns explained variance, loadings, and scores.
    """
    try:
        from sklearn.preprocessing import StandardScaler
        from sklearn.decomposition import PCA

        # Use only numeric columns
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) < 2:
            return {"error": "PCA requires at least 2 numeric columns."}

        df_numeric = df[numeric_cols].dropna()
        removed = len(df) - len(df_numeric)

        if len(df_numeric) < 10:
            return {"error": f"PCA requires at least 10 observations (n={len(df_numeric)})."}

        # Remove zero-variance columns
        zero_var = [c for c in numeric_cols if df_numeric[c].std() == 0]
        if zero_var:
            numeric_cols = [c for c in numeric_cols if c not in zero_var]
            df_numeric = df_numeric[numeric_cols]
        if len(numeric_cols) < 2:
            return {"error": "After removing zero-variance columns, fewer than 2 remain."}

        X = df_numeric.values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        actual_n = min(n_components, len(numeric_cols), len(X_scaled))
        pca = PCA(n_components=actual_n)
        scores = pca.fit_transform(X_scaled)

        loadings = {
            col: pca.components_[:, i].tolist()
            for i, col in enumerate(numeric_cols)
        }

        score_dicts = []
        for i in range(len(scores)):
            entry = {f"PC{j + 1}": float(scores[i, j]) for j in range(scores.shape[1])}
            score_dicts.append(entry)

        return {
            "test_name": "PCA",
            "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
            "cumulative_variance": np.cumsum(pca.explained_variance_ratio_).tolist(),
            "loadings": loadings,
            "scores": score_dicts,
            "n_components": int(pca.n_components_),
            "columns_used": numeric_cols,
            "zero_var_removed": zero_var,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"PCA failed: {e}"}


def run_kmeans(df: pd.DataFrame, max_k: int = 10) -> dict:
    """K-means clustering with elbow analysis.

    Returns elbow data, optimal k, cluster labels, centroids, and silhouette score.
    """
    try:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler
        from sklearn.metrics import silhouette_score

        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(numeric_cols) < 2:
            return {"error": "K-means requires at least 2 numeric columns."}

        df_numeric = df[numeric_cols].dropna()
        removed = len(df) - len(df_numeric)

        if len(df_numeric) < 10:
            return {"error": f"K-means requires at least 10 observations (n={len(df_numeric)})."}

        # Remove zero-variance columns
        zero_var = [c for c in numeric_cols if df_numeric[c].std() == 0]
        if zero_var:
            numeric_cols = [c for c in numeric_cols if c not in zero_var]
            df_numeric = df_numeric[numeric_cols]
        if len(numeric_cols) < 2:
            return {"error": "After removing zero-variance columns, fewer than 2 remain."}

        X = df_numeric.values
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        max_k = min(max_k, len(X_scaled) - 1)
        if max_k < 2:
            return {"error": "Need at least 3 observations for k=2 clustering."}

        # Elbow analysis
        inertias = {}
        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            km.fit(X_scaled)
            inertias[k] = float(km.inertia_)

        # Elbow heuristic
        if len(inertias) >= 3:
            ks = sorted(inertias.keys())
            diffs = [inertias[ks[i]] - inertias[ks[i + 1]] for i in range(len(ks) - 1)]
            diffs2 = [diffs[i] - diffs[i + 1] for i in range(len(diffs) - 1)]
            optimal_k = ks[np.argmax(diffs2) + 1] if diffs2 else ks[0]
        else:
            optimal_k = 2

        # Final clustering with optimal k
        km_final = KMeans(n_clusters=optimal_k, n_init=10, random_state=42)
        labels = km_final.fit_predict(X_scaled)

        sil = 0.0
        if optimal_k > 1 and optimal_k < len(X_scaled):
            sil = float(silhouette_score(X_scaled, labels))

        # Centroids in original scale
        centroids_orig = scaler.inverse_transform(km_final.cluster_centers_)
        centroids = [
            {col: float(centroids_orig[c, i]) for i, col in enumerate(numeric_cols)}
            for c in range(optimal_k)
        ]

        return {
            "test_name": "K-Means Clustering",
            "elbow_data": inertias,
            "optimal_k": optimal_k,
            "labels": labels.tolist(),
            "centroids": centroids,
            "silhouette": sil,
            "chosen_k": optimal_k,
            "columns_used": numeric_cols,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"K-means clustering failed: {e}"}


def run_multiple_regression(
    df: pd.DataFrame,
    target: str,
    features: list[str],
) -> dict:
    """Multiple linear regression with diagnostics."""
    try:
        import statsmodels.api as sm
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        from statsmodels.stats.stattools import durbin_watson

        df_work = df[[target] + features].copy()
        initial_len = len(df_work)

        y = df_work[target].astype(float)
        X = df_work[features].astype(float)
        X = sm.add_constant(X)

        mask = ~(X.isna().any(axis=1) | y.isna())
        X_clean, y_clean = X[mask], y[mask]
        removed = initial_len - len(y_clean)

        min_obs = len(features) + 10
        if len(y_clean) < min_obs:
            return {"error": f"Need at least {min_obs} observations, have {len(y_clean)}."}

        model = sm.OLS(y_clean, X_clean)
        result = model.fit()

        # VIF for multicollinearity
        vif = {}
        for i, col in enumerate(features):
            col_idx = i + 1  # skip constant
            try:
                vif[col] = float(variance_inflation_factor(X_clean.values, col_idx))
            except Exception:
                vif[col] = float("inf")

        pred_names = [c for c in X_clean.columns if c != "const"]

        coefficients = {n: float(result.params[n]) for n in pred_names}
        p_values = {n: float(result.pvalues[n]) for n in pred_names}
        conf = result.conf_int()
        ci95 = {n: (float(conf.loc[n, 0]), float(conf.loc[n, 1])) for n in pred_names}

        summary_table = result.summary2().tables[1]
        result_df = summary_table.to_dict("records") if hasattr(summary_table, "to_dict") else []

        dw = float(durbin_watson(result.resid))

        return {
            "test_name": "Multiple Linear Regression",
            "r_squared": float(result.rsquared),
            "adj_r_squared": float(result.rsquared_adj),
            "f_statistic": float(result.fvalue),
            "f_pvalue": float(result.f_pvalue),
            "coefficients": coefficients,
            "p_values": p_values,
            "ci95": ci95,
            "vif": vif,
            "durbin_watson": dw,
            "residuals": result.resid.tolist(),
            "y_true": y_clean.tolist(),
            "y_pred": result.fittedvalues.tolist(),
            "result_df": result_df,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Multiple regression failed: {e}"}


def run_repeated_measures_anova(
    df: pd.DataFrame,
    dv: str,
    within: str,
    subject: str,
) -> dict:
    """Repeated measures ANOVA with sphericity check and post-hoc."""
    try:
        import pingouin as pg

        cols = [dv, within, subject]
        df_clean = df[cols].dropna()
        removed = len(df) - len(df_clean)

        if not pd.api.types.is_numeric_dtype(df_clean[dv]):
            return {"error": f"Dependent variable '{dv}' must be numeric."}

        levels = df_clean[within].nunique()
        if levels < 2:
            return {"error": f"Within-subject factor '{within}' needs at least 2 levels, got {levels}."}

        subjects = df_clean[subject].nunique()
        if subjects < 3:
            return {"error": f"Need at least 3 subjects, got {subjects}."}

        # Validate balanced design: each subject must have exactly the same levels
        obs_per_subject = df_clean.groupby(subject)[within].nunique()
        if obs_per_subject.nunique() != 1:
            unbalanced = obs_per_subject[obs_per_subject != obs_per_subject.mode().iloc[0]]
            return {
                "error": f"Unbalanced design: {len(unbalanced)} subject(s) have different numbers "
                         f"of within-factor levels. Repeated-measures ANOVA requires each subject "
                         f"to have exactly {levels} observations (one per level of '{within}')."
            }
        counts_per_cell = df_clean.groupby([subject, within]).size()
        if (counts_per_cell != 1).any():
            return {
                "error": "Duplicate observations: some subjects have multiple measurements "
                         f"for the same level of '{within}'. Each subject must appear exactly "
                         "once per condition."
            }

        result = pg.rm_anova(data=df_clean, dv=dv, within=within, subject=subject, detailed=False)

        # Sphericity
        sphericity_p = None
        epsilon_gg = None
        try:
            spher_result = pg.sphericity(data=df_clean, dv=dv, within=within, subject=subject)
            if isinstance(spher_result, tuple) and len(spher_result) >= 2:
                sphericity_p = float(spher_result[1])
        except Exception:
            pass

        p_val = float(result["p_unc"].iloc[0])

        if "eps" in result.columns:
            epsilon_gg = float(result["eps"].iloc[0])

        # GG-corrected p is not a separate column in pingouin 0.6 —
        # apply correction manually if epsilon < 1
        p_val_gg = None
        if epsilon_gg is not None and epsilon_gg < 1.0:
            from scipy.stats import f as f_dist
            df1 = float(result["ddof1"].iloc[0]) * epsilon_gg
            df2 = float(result["ddof2"].iloc[0]) * epsilon_gg
            f_val = float(result["F"].iloc[0])
            p_val_gg = float(1 - f_dist.cdf(f_val, df1, df2))

        posthoc = None
        if p_val < 0.05:
            posthoc = pg.pairwise_tests(
                data=df_clean, dv=dv, within=within, subject=subject,
                padjust="bonf",
            )

        # Use ng2 (generalized eta-squared) for RM ANOVA
        eta_col = "ng2" if "ng2" in result.columns else "np2"
        return {
            "test_name": "Repeated Measures ANOVA",
            "F": float(result["F"].iloc[0]),
            "p_val": p_val,
            "p_val_gg": p_val_gg,
            "eta_squared": float(result[eta_col].iloc[0]),
            "sphericity_p": sphericity_p,
            "epsilon_gg": epsilon_gg,
            "result_df": result.to_dict("records"),
            "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
            "nan_removed": removed,
        }
    except Exception as e:
        return {"error": f"Repeated measures ANOVA failed: {e}"}


# ===================================================================
#  6. UTILITY
# ===================================================================

def detect_column_types(df: pd.DataFrame) -> dict[str, str]:
    """Auto-detect column types.

    Returns {col_name: "numeric" | "categorical" | "text" | "datetime" | "empty"}.
    """
    result = {}
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            result[col] = "empty"
            continue

        # Try numeric
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() / len(series) >= 0.8:
            result[col] = "numeric"
            continue

        # Try datetime
        try:
            pd.to_datetime(series, format="mixed", errors="raise")
            result[col] = "datetime"
            continue
        except (ValueError, TypeError):
            pass

        # Categorical vs text
        if series.nunique() / len(series) < 0.05 or series.nunique() <= 20:
            result[col] = "categorical"
        else:
            result[col] = "text"

    return result


def compute_correlation_matrix(
    df: pd.DataFrame,
    columns: list[str] | None = None,
    method: str = "pearson",
) -> dict:
    """Compute pairwise correlation matrix with p-values.

    If columns is None, uses all numeric columns.
    """
    try:
        import pingouin as pg

        if columns is None:
            columns = df.select_dtypes(include=[np.number]).columns.tolist()
        if len(columns) < 2:
            return {"error": "Need at least 2 numeric columns for correlation matrix."}

        n = len(columns)
        corr = np.zeros((n, n))
        pvals = np.ones((n, n))

        for i in range(n):
            for j in range(i, n):
                if i == j:
                    corr[i, j] = 1.0
                    pvals[i, j] = 0.0
                else:
                    # Use only rows where both columns are non-NaN
                    valid = df[[columns[i], columns[j]]].dropna()
                    if len(valid) < 3:
                        corr[i, j] = corr[j, i] = np.nan
                        pvals[i, j] = pvals[j, i] = np.nan
                        continue
                    x_vals = valid[columns[i]].values
                    y_vals = valid[columns[j]].values
                    if np.std(x_vals) == 0 or np.std(y_vals) == 0:
                        corr[i, j] = corr[j, i] = np.nan
                        pvals[i, j] = pvals[j, i] = np.nan
                        continue
                    r = pg.corr(x_vals, y_vals, method=method)
                    corr[i, j] = corr[j, i] = float(r["r"].iloc[0])
                    pvals[i, j] = pvals[j, i] = float(r["p_val"].iloc[0])

        corr_df = pd.DataFrame(corr, index=columns, columns=columns)
        p_df = pd.DataFrame(pvals, index=columns, columns=columns)

        return {
            "corr_matrix": corr_df.to_dict(),
            "p_matrix": p_df.to_dict(),
            "method": method,
        }
    except Exception as e:
        return {"error": f"Correlation matrix computation failed: {e}"}
