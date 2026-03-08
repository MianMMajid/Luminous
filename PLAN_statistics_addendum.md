I have a comprehensive understanding of the codebase. Let me now produce the detailed addendum plan.

---

# Statistics Tab Addendum: Focused Expansions for Bench Biologists

## Scope and Relationship to Existing Plan

The existing `PLAN_statistics.md` covers 8 statistical tests (independent/paired t-test, Mann-Whitney U, Wilcoxon, one-way ANOVA, Kruskal-Wallis, Pearson/Spearman correlation, chi-square), 8 curve equations (4PL, Michaelis-Menten, Hill, exponential decay, linear, polynomial deg 2/3/4), and survival analysis (Kaplan-Meier, log-rank, Cox PH). This addendum expands those foundations without changing the existing architecture: all new computations go in `src/statistics_engine.py`, all new chart builders go in `src/statistics_charts.py`, and all new UI goes into `components/statistics_tab.py`.

---

## TIER 1: "Every biologist uses this weekly" (MUST HAVE)

### T1.1 Two-Way ANOVA (with Interaction Term)

**Biological context for protein analysis:** A researcher treats cells expressing wild-type vs mutant protein (factor 1: genotype) with drug vs vehicle (factor 2: treatment), then measures protein expression/activity. The interaction term reveals whether the drug effect depends on genotype -- the core question in most mutation studies.

**Function signature:**

```python
# In src/statistics_engine.py

def run_two_way_anova(
    df: pd.DataFrame,
    dv: str,          # dependent variable column name (numeric)
    factor_a: str,    # first between-subjects factor column (categorical)
    factor_b: str,    # second between-subjects factor column (categorical)
) -> dict:
    """Two-way ANOVA with interaction term.

    Returns dict with keys:
        test_name: str
        main_effect_a: dict  -- {F, p_val, eta_squared, df}
        main_effect_b: dict  -- {F, p_val, eta_squared, df}
        interaction: dict    -- {F, p_val, eta_squared, df}
        result_df: list[dict]  -- full ANOVA table as records
        posthoc_df: list[dict] | None  -- pairwise comparisons if any effect significant
        interpretation: str
    """
    import pingouin as pg

    result = pg.anova(data=df, dv=dv, between=[factor_a, factor_b], detailed=True)

    # Extract rows: factor_a, factor_b, factor_a * factor_b, Residual
    effects = {}
    for _, row in result.iterrows():
        source = row["Source"]
        effects[source] = {
            "F": float(row["F"]),
            "p_val": float(row["p-unc"]),
            "eta_squared": float(row["np2"]),
            "df": int(row["DF"]) if "DF" in row else int(row["ddof1"]),
        }

    # Post-hoc: if interaction is significant, do simple effects
    posthoc = None
    interaction_key = f"{factor_a} * {factor_b}"
    if effects.get(interaction_key, {}).get("p_val", 1.0) < 0.05:
        posthoc = pg.pairwise_tests(
            data=df, dv=dv, between=[factor_a, factor_b],
            padjust="bonf"
        )

    return {
        "test_name": "Two-way ANOVA",
        "main_effect_a": effects.get(factor_a, {}),
        "main_effect_b": effects.get(factor_b, {}),
        "interaction": effects.get(interaction_key, {}),
        "result_df": result.to_dict("records"),
        "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
    }
```

**Input validation:**
- `dv` column must be numeric (checked via `pd.api.types.is_numeric_dtype`)
- `factor_a` and `factor_b` must be categorical with 2+ levels each
- Minimum 2 observations per cell (each combination of factor_a x factor_b)
- Edge case: empty cells in the design matrix -> `st.error("Unbalanced design: some factor combinations have no observations. Two-way ANOVA requires at least 1 observation per cell.")`
- Edge case: only 1 level in a factor -> degrade to one-way ANOVA with warning

**Plotly chart: Interaction Plot (line chart with error bars)**

```python
# In src/statistics_charts.py

def build_interaction_plot(
    df: pd.DataFrame,
    dv: str,
    factor_a: str,
    factor_b: str,
    result: dict,
) -> go.Figure:
    """Interaction plot: factor_a on x-axis, separate lines for each level of factor_b."""
    import pandas as pd

    grouped = df.groupby([factor_a, factor_b])[dv].agg(["mean", "sem"]).reset_index()
    fig = go.Figure()

    for i, level_b in enumerate(df[factor_b].unique()):
        subset = grouped[grouped[factor_b] == level_b]
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Scatter(
            x=subset[factor_a].astype(str),
            y=subset["mean"],
            error_y=dict(type="data", array=subset["sem"].tolist(), visible=True),
            mode="lines+markers",
            name=f"{factor_b}={level_b}",
            marker=dict(color=color, size=10),
            line=dict(color=color, width=2.5),
            hovertemplate=(
                f"{factor_a}: %{{x}}<br>"
                f"Mean {dv}: %{{y:.3f}} +/- %{{error_y.array:.3f}}<br>"
                f"{factor_b}: {level_b}<extra></extra>"
            ),
        ))

    # Annotate interaction p-value
    p_int = result.get("interaction", {}).get("p_val")
    if p_int is not None:
        fig.add_annotation(
            text=f"Interaction: p = {p_int:.4f}" if p_int >= 0.001 else "Interaction: p < 0.001",
            xref="paper", yref="paper", x=0.98, y=0.98,
            showarrow=False, font=dict(size=12, color="rgba(60,60,67,0.75)"),
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=factor_a,
        yaxis_title=f"Mean {dv} (+/- SEM)",
        height=400,
        legend=dict(orientation="h", y=-0.15),
    )
    return fig
```

**Integration with protein data:** When a user sends pLDDT data with region labels from the Structure tab, factor_a could be "region" (helix vs loop vs sheet) and factor_b could be "chain" (in a multimer). The DV is pLDDT score. The interaction tells whether confidence varies differently across regions depending on the chain -- important for assessing inter-chain interface reliability.

**UI changes in `components/statistics_tab.py`:** Add `"Two-way ANOVA"` to the `"Compare Multiple Groups"` category in the test selector (section 5.1 of existing plan). Show two `st.selectbox` widgets for factor_a and factor_b (categorical columns) plus one for dv (numeric column). Widget keys: `stats_factor_a`, `stats_factor_b`.

---

### T1.2 Fisher's Exact Test (2x2 Tables)

**Biological context:** Enrichment analysis -- is a mutation more common in the active site than expected? Association testing -- is pathogenicity associated with a particular structural domain? Fisher's is the gold standard when expected cell counts < 5, which is common with rare variants.

**Function signature:**

```python
def run_fisher_exact(
    df: pd.DataFrame,
    col1: str,
    col2: str,
) -> dict:
    """Fisher's exact test for 2x2 contingency tables.

    Returns dict with keys:
        test_name, odds_ratio, p_val, contingency_table, CI95_odds_ratio,
        relative_risk, warning (if table is not 2x2)
    """
    from scipy.stats import fisher_exact

    ct = pd.crosstab(df[col1], df[col2])

    if ct.shape != (2, 2):
        return {
            "test_name": "Fisher's Exact Test",
            "error": f"Requires a 2x2 table, got {ct.shape[0]}x{ct.shape[1]}. "
                     "Reduce to 2 levels per variable or use Chi-square.",
        }

    oddsratio, p_value = fisher_exact(ct.values, alternative="two-sided")

    # Confidence interval for odds ratio (Woolf logit method)
    a, b, c, d = ct.values.ravel()
    if 0 in (a, b, c, d):
        # Add 0.5 continuity correction (Haldane-Anscombe)
        a_c, b_c, c_c, d_c = a + 0.5, b + 0.5, c + 0.5, d + 0.5
    else:
        a_c, b_c, c_c, d_c = a, b, c, d
    log_or = np.log(a_c * d_c / (b_c * c_c))
    se_log_or = np.sqrt(1/a_c + 1/b_c + 1/c_c + 1/d_c)
    ci_lower = np.exp(log_or - 1.96 * se_log_or)
    ci_upper = np.exp(log_or + 1.96 * se_log_or)

    # Relative risk
    rr = (a / (a + b)) / (c / (c + d)) if (a + b) > 0 and (c + d) > 0 and c > 0 else None

    return {
        "test_name": "Fisher's Exact Test",
        "odds_ratio": float(oddsratio),
        "p_val": float(p_value),
        "CI95_odds_ratio": (float(ci_lower), float(ci_upper)),
        "relative_risk": float(rr) if rr else None,
        "contingency_table": ct.to_dict(),
        "result_df": [{"odds_ratio": oddsratio, "p_value": p_value,
                        "CI_lower": ci_lower, "CI_upper": ci_upper}],
    }
```

**Input validation:**
- Both columns must be categorical
- Must have exactly 2 unique values per column (after dropping NaN)
- Edge case: zero cells -> apply Haldane-Anscombe 0.5 correction (already handled above)
- Edge case: all observations in one cell -> `st.warning("Perfect separation detected.")`

**Plotly chart: Mosaic-style stacked bar**

```python
def build_contingency_chart(
    contingency_table: dict,
    col1_name: str,
    col2_name: str,
    p_value: float,
    odds_ratio: float,
) -> go.Figure:
    """Stacked bar chart for 2x2 contingency table with annotation."""
    ct_df = pd.DataFrame(contingency_table)
    fig = go.Figure()

    for i, col in enumerate(ct_df.columns):
        fig.add_trace(go.Bar(
            x=ct_df.index.astype(str),
            y=ct_df[col],
            name=str(col),
            marker_color=CB_PALETTE[i % len(CB_PALETTE)],
            hovertemplate=f"{col2_name}={col}<br>Count: %{{y}}<extra></extra>",
        ))

    p_text = f"p = {p_value:.4f}" if p_value >= 0.001 else "p < 0.001"
    fig.add_annotation(
        text=f"Fisher's exact: {p_text}<br>OR = {odds_ratio:.2f}",
        xref="paper", yref="paper", x=0.98, y=0.98,
        showarrow=False, font=dict(size=11, color="rgba(60,60,67,0.75)"),
    )

    fig.update_layout(
        **_BASE_LAYOUT, barmode="group",
        xaxis_title=col1_name, yaxis_title="Count", height=350,
    )
    return fig
```

**Integration with protein data:** Cross-tabulate (pathogenic/benign) x (buried/exposed) based on SASA from `structure_analysis.py`. Fisher's exact tells whether pathogenic variants are enriched in buried residues. Also: (in active site / not in active site) x (pathogenic / VUS) for variant_landscape data.

**UI integration:** Add `"Fisher's Exact Test"` to the `"Contingency"` category. The existing chi-square test already warns when expected frequencies < 5 and suggests Fisher's -- now that suggestion becomes an actionable link.

---

### T1.3 Welch's ANOVA (Brown-Forsythe)

**Biological context:** When comparing pLDDT across 3+ structural domains (alpha-helix, beta-sheet, loop) and Levene's test flags unequal variance, Welch's ANOVA is the correct fallback. The existing plan's one-way ANOVA already suggests it but doesn't implement it.

**Function signature:**

```python
def run_welch_anova(
    df: pd.DataFrame,
    dv: str,
    between: str,
) -> dict:
    """Welch's one-way ANOVA (robust to unequal variances).

    Returns dict with keys:
        test_name, F, p_val, df_between, df_within, result_df, posthoc_df
    """
    import pingouin as pg

    result = pg.welch_anova(data=df, dv=dv, between=between)
    posthoc = None
    if float(result["p-unc"].iloc[0]) < 0.05:
        posthoc = pg.pairwise_gameshowell(data=df, dv=dv, between=between)

    return {
        "test_name": "Welch's ANOVA",
        "F": float(result["F"].iloc[0]),
        "p_val": float(result["p-unc"].iloc[0]),
        "df_between": int(result["ddof1"].iloc[0]),
        "df_within": float(result["ddof2"].iloc[0]),  # non-integer for Welch
        "result_df": result.to_dict("records"),
        "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
    }
```

**Key difference from standard ANOVA:** Post-hoc uses Games-Howell (`pg.pairwise_gameshowell`) instead of Tukey HSD, because Games-Howell does not assume equal variances.

**Input validation:** Same as one-way ANOVA. The check_equal_variance function from the existing plan detects the need; the UI flow is: run assumption checks -> if Levene's fails -> offer "Use Welch's ANOVA instead" button.

**Plotly chart:** Reuse the existing `build_comparison_chart()` from section 8.3.2 of the existing plan. No new chart builder needed.

**UI integration:** Add `"Welch's ANOVA"` to `"Compare Multiple Groups"` category. Better yet: when the user selects standard ANOVA and Levene's test fails, show an `st.warning` with a button that reruns using Welch's.

---

### T1.4 Logistic Regression (Binary Outcome)

**Biological context:** Given a set of structural features (SASA, pLDDT, secondary structure type, distance to active site), predict whether a variant is pathogenic or benign. This is the standard binary classifier in clinical genomics.

**Function signature:**

```python
def run_logistic_regression(
    df: pd.DataFrame,
    outcome: str,       # binary column (0/1 or two-level categorical)
    predictors: list[str],  # numeric columns
) -> dict:
    """Logistic regression for binary outcome.

    Returns dict with keys:
        test_name, coefficients (dict of {name: coef}),
        odds_ratios (dict of {name: OR}), p_values (dict of {name: p}),
        ci95 (dict of {name: (lo, hi)}), pseudo_r_squared (McFadden),
        aic, bic, concordance, result_df, y_pred_proba (list[float])
    """
    import statsmodels.api as sm

    # Encode binary outcome
    y = df[outcome].copy()
    if y.dtype == object or y.dtype.name == "category":
        levels = sorted(y.dropna().unique())
        if len(levels) != 2:
            return {"error": f"Outcome must have exactly 2 levels, got {len(levels)}."}
        y = (y == levels[1]).astype(int)

    X = df[predictors].copy().astype(float)
    X = sm.add_constant(X)

    # Drop rows with NaN
    mask = ~(X.isna().any(axis=1) | y.isna())
    X_clean = X[mask]
    y_clean = y[mask]

    if len(y_clean) < len(predictors) + 10:
        return {"error": f"Need at least {len(predictors) + 10} observations, have {len(y_clean)}."}

    model = sm.Logit(y_clean, X_clean)
    try:
        result = model.fit(disp=0, maxiter=100)
    except Exception as e:
        return {"error": f"Model did not converge: {e}"}

    summary = result.summary2().tables[1]
    coef_names = [c for c in X_clean.columns if c != "const"]

    return {
        "test_name": "Logistic Regression",
        "coefficients": {n: float(result.params[n]) for n in coef_names},
        "odds_ratios": {n: float(np.exp(result.params[n])) for n in coef_names},
        "p_values": {n: float(result.pvalues[n]) for n in coef_names},
        "ci95": {n: (float(result.conf_int().loc[n, 0]),
                     float(result.conf_int().loc[n, 1])) for n in coef_names},
        "pseudo_r_squared": float(result.prsquared),
        "aic": float(result.aic),
        "bic": float(result.bic),
        "result_df": summary.to_dict("records") if hasattr(summary, "to_dict") else [],
        "y_pred_proba": result.predict(X_clean).tolist(),
        "y_true": y_clean.tolist(),
    }
```

**Input validation:**
- Outcome must be binary (exactly 2 unique non-NaN values)
- Predictors must be numeric
- Edge case: perfect separation (all pathogenic variants have SASA=0) -> `statsmodels` raises `PerfectSeparationError` -> catch and show `st.error("Perfect or quasi-perfect separation detected. One predictor perfectly predicts the outcome.")`
- Edge case: multicollinearity -> compute VIF for each predictor, warn if any VIF > 10

**Plotly chart: Forest Plot of Odds Ratios**

```python
def build_odds_ratio_forest(
    result: dict,
) -> go.Figure:
    """Forest plot showing odds ratios with 95% CI for each predictor."""
    names = list(result["odds_ratios"].keys())
    ors = [result["odds_ratios"][n] for n in names]
    ci_lo = [np.exp(result["ci95"][n][0]) for n in names]
    ci_hi = [np.exp(result["ci95"][n][1]) for n in names]
    p_vals = [result["p_values"][n] for n in names]

    fig = go.Figure()
    for i, name in enumerate(names):
        color = CB_PALETTE[0] if p_vals[i] < 0.05 else "rgba(142,142,147,0.6)"
        fig.add_trace(go.Scatter(
            x=[ors[i]], y=[name],
            error_x=dict(
                type="data",
                symmetric=False,
                array=[ci_hi[i] - ors[i]],
                arrayminus=[ors[i] - ci_lo[i]],
            ),
            mode="markers",
            marker=dict(color=color, size=10, symbol="diamond"),
            name=name,
            showlegend=False,
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"OR: %{{x:.2f}} (95% CI: {ci_lo[i]:.2f}-{ci_hi[i]:.2f})<br>"
                f"p = {p_vals[i]:.4f}<extra></extra>"
            ),
        ))

    fig.add_vline(x=1, line_dash="dash", line_color="rgba(60,60,67,0.3)")
    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Odds Ratio (95% CI)",
        xaxis_type="log",
        height=max(200, 50 * len(names)),
    )
    return fig
```

**Integration with protein data:** From `structure_analysis.py`, compute per-residue SASA, secondary structure, packing density, and B-factor centrality. Combine with variant pathogenicity labels from `variant_analyzer.py`. Run logistic regression to predict pathogenicity from structural features. This directly answers the question: "Which structural properties predict whether a variant is disease-causing?"

---

### T1.5 ROC Curve + AUC

**Biological context:** After logistic regression (or any binary classifier), the ROC curve shows how well structural features discriminate pathogenic from benign variants at every threshold. AUC is the single number biologists compare across models ("Model A has AUC 0.85 vs Model B with AUC 0.72").

Also used standalone: "At what pLDDT threshold should I trust a predicted residue position?" Plot pLDDT against experimentally validated residues to determine the optimal cutoff.

**Function signature:**

```python
def compute_roc_curve(
    y_true: np.ndarray,      # binary (0/1)
    y_score: np.ndarray,     # continuous scores (probabilities or raw scores)
    pos_label: int = 1,
) -> dict:
    """Compute ROC curve and AUC.

    Returns dict with keys:
        fpr (list[float]), tpr (list[float]), thresholds (list[float]),
        auc (float), ci95_auc (tuple[float, float]),
        optimal_threshold (float), optimal_sensitivity (float),
        optimal_specificity (float), youden_j (float)
    """
    from sklearn.metrics import roc_curve, roc_auc_score

    fpr, tpr, thresholds = roc_curve(y_true, y_score, pos_label=pos_label)
    auc_val = roc_auc_score(y_true, y_score)

    # DeLong CI for AUC (bootstrap approximation)
    n_bootstraps = 1000
    rng = np.random.default_rng(42)
    bootstrapped_aucs = []
    for _ in range(n_bootstraps):
        indices = rng.choice(len(y_true), len(y_true), replace=True)
        if len(np.unique(y_true[indices])) < 2:
            continue
        bootstrapped_aucs.append(roc_auc_score(y_true[indices], y_score[indices]))
    ci_lower = float(np.percentile(bootstrapped_aucs, 2.5))
    ci_upper = float(np.percentile(bootstrapped_aucs, 97.5))

    # Youden's J statistic for optimal threshold
    j_scores = tpr - fpr
    optimal_idx = np.argmax(j_scores)

    return {
        "fpr": fpr.tolist(),
        "tpr": tpr.tolist(),
        "thresholds": thresholds.tolist(),
        "auc": float(auc_val),
        "ci95_auc": (ci_lower, ci_upper),
        "optimal_threshold": float(thresholds[optimal_idx]),
        "optimal_sensitivity": float(tpr[optimal_idx]),
        "optimal_specificity": float(1 - fpr[optimal_idx]),
        "youden_j": float(j_scores[optimal_idx]),
    }
```

**Input validation:**
- `y_true` must be binary (0/1)
- `y_score` must be numeric with no NaN
- Edge case: only one class present -> `return {"error": "ROC requires both positive and negative examples."}`
- Edge case: fewer than 10 positive examples -> `st.warning("Very few positive cases. ROC may be unreliable.")`

**Plotly chart:**

```python
def build_roc_chart(
    roc_result: dict,
    model_name: str = "Model",
) -> go.Figure:
    fig = go.Figure()

    # Chance line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color="rgba(60,60,67,0.3)", width=1.5, dash="dash"),
        name="Chance (AUC = 0.5)", showlegend=True,
    ))

    # ROC curve
    auc = roc_result["auc"]
    ci = roc_result["ci95_auc"]
    fig.add_trace(go.Scatter(
        x=roc_result["fpr"], y=roc_result["tpr"], mode="lines",
        line=dict(color=CB_PALETTE[0], width=2.5),
        name=f"{model_name} (AUC = {auc:.3f}, 95% CI: {ci[0]:.3f}-{ci[1]:.3f})",
        fill="tonexty", fillcolor="rgba(100,143,255,0.1)",
        hovertemplate="FPR: %{x:.3f}<br>TPR: %{y:.3f}<extra></extra>",
    ))

    # Optimal threshold point
    opt_fpr = 1 - roc_result["optimal_specificity"]
    opt_tpr = roc_result["optimal_sensitivity"]
    fig.add_trace(go.Scatter(
        x=[opt_fpr], y=[opt_tpr], mode="markers",
        marker=dict(color=CB_PALETTE[1], size=12, symbol="star"),
        name=f"Optimal (threshold = {roc_result['optimal_threshold']:.3f})",
        hovertemplate=(
            f"Optimal threshold: {roc_result['optimal_threshold']:.3f}<br>"
            f"Sensitivity: {opt_tpr:.3f}<br>"
            f"Specificity: {roc_result['optimal_specificity']:.3f}<extra></extra>"
        ),
    ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="False Positive Rate (1 - Specificity)",
        yaxis_title="True Positive Rate (Sensitivity)",
        xaxis_range=[-0.02, 1.02],
        yaxis_range=[-0.02, 1.02],
        height=450,
        legend=dict(x=0.4, y=0.05),
    )
    return fig
```

**Integration with protein data:** Use pLDDT scores as `y_score` and a binary "experimentally verified correct / incorrect" label as `y_true` (from comparison against known X-ray structures, available via RCSB). This produces the optimal pLDDT cutoff for the specific protein -- more useful than the generic 70/90 guidelines.

**UI integration:** Add `"ROC Curve & AUC"` as a new category in the test selector: `"Classifier Performance"`. Requires selecting one binary column (outcome) and one numeric column (score/probability). Also automatically offered after logistic regression completes.

---

### T1.6 Bland-Altman Plot

**Biological context:** Method comparison -- if you measure binding affinity by both SPR and ITC, or protein expression by Western blot and ELISA, a Bland-Altman plot shows systematic bias and limits of agreement. Correlation alone is misleading for method comparison (two methods can have r=0.99 but a 2-fold systematic offset).

**Function signature:**

```python
def compute_bland_altman(
    method1: np.ndarray,
    method2: np.ndarray,
    method1_name: str = "Method 1",
    method2_name: str = "Method 2",
) -> dict:
    """Bland-Altman analysis for method comparison.

    Returns dict with keys:
        mean_diff (float), sd_diff (float),
        upper_loa (float), lower_loa (float),  # limits of agreement
        ci95_mean_diff (tuple), ci95_upper_loa (tuple), ci95_lower_loa (tuple),
        means (list[float]), diffs (list[float]),
        proportional_bias_p (float),  # slope of diff vs mean regression
    """
    from scipy import stats

    mask = ~(np.isnan(method1) | np.isnan(method2))
    m1, m2 = method1[mask], method2[mask]
    n = len(m1)

    means = ((m1 + m2) / 2).tolist()
    diffs = (m1 - m2).tolist()
    mean_diff = float(np.mean(diffs))
    sd_diff = float(np.std(diffs, ddof=1))

    upper_loa = mean_diff + 1.96 * sd_diff
    lower_loa = mean_diff - 1.96 * sd_diff

    # CIs for mean diff and LoA
    se_mean = sd_diff / np.sqrt(n)
    t_crit = stats.t.ppf(0.975, n - 1)
    ci_mean = (mean_diff - t_crit * se_mean, mean_diff + t_crit * se_mean)

    se_loa = np.sqrt(3 * sd_diff**2 / n)
    ci_upper_loa = (upper_loa - t_crit * se_loa, upper_loa + t_crit * se_loa)
    ci_lower_loa = (lower_loa - t_crit * se_loa, lower_loa + t_crit * se_loa)

    # Proportional bias check (regression of diff on mean)
    slope, intercept, r_val, p_val, se_slope = stats.linregress(means, diffs)

    return {
        "mean_diff": mean_diff,
        "sd_diff": sd_diff,
        "upper_loa": float(upper_loa),
        "lower_loa": float(lower_loa),
        "ci95_mean_diff": (float(ci_mean[0]), float(ci_mean[1])),
        "ci95_upper_loa": (float(ci_upper_loa[0]), float(ci_upper_loa[1])),
        "ci95_lower_loa": (float(ci_lower_loa[0]), float(ci_lower_loa[1])),
        "means": means,
        "diffs": diffs,
        "proportional_bias_p": float(p_val),
        "proportional_bias_slope": float(slope),
        "n": n,
    }
```

**Input validation:**
- Both columns must be numeric
- Must have same length (paired measurements)
- Minimum 10 pairs
- Edge case: identical values everywhere -> `sd_diff == 0` -> warn "No variation between methods"

**Plotly chart:**

```python
def build_bland_altman_chart(
    ba_result: dict,
    method1_name: str,
    method2_name: str,
) -> go.Figure:
    fig = go.Figure()

    # Scatter of diffs vs means
    fig.add_trace(go.Scatter(
        x=ba_result["means"], y=ba_result["diffs"],
        mode="markers",
        marker=dict(color=CB_PALETTE[0], size=7, opacity=0.7),
        name="Observations",
        hovertemplate=f"Mean: %{{x:.3f}}<br>Diff ({method1_name} - {method2_name}): %{{y:.3f}}<extra></extra>",
    ))

    # Mean difference line
    fig.add_hline(y=ba_result["mean_diff"], line_color=CB_PALETTE[1],
                  line_width=2, annotation_text=f"Mean diff: {ba_result['mean_diff']:.3f}",
                  annotation_position="right")

    # Upper and lower limits of agreement
    fig.add_hline(y=ba_result["upper_loa"], line_dash="dash", line_color=CB_PALETTE[2],
                  annotation_text=f"+1.96 SD: {ba_result['upper_loa']:.3f}",
                  annotation_position="right")
    fig.add_hline(y=ba_result["lower_loa"], line_dash="dash", line_color=CB_PALETTE[2],
                  annotation_text=f"-1.96 SD: {ba_result['lower_loa']:.3f}",
                  annotation_position="right")

    # Zero line
    fig.add_hline(y=0, line_color="rgba(60,60,67,0.15)", line_width=1)

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=f"Mean of {method1_name} and {method2_name}",
        yaxis_title=f"Difference ({method1_name} - {method2_name})",
        height=400,
    )
    return fig
```

**Integration with protein data:** Compare pLDDT scores from two different prediction methods (e.g., Boltz-2 via Tamarind vs AlphaFold2 precomputed). Also: compare SASA computed from predicted vs experimental structures to quantify structural prediction quality.

**UI integration:** New category `"Method Comparison"` in the test selector. Two numeric columns selected.

---

### T1.7 Violin Plots (Complement Box Plots)

**Biological context:** Violin plots show the distribution shape, not just quartiles. A bimodal pLDDT distribution (one peak at ~40, another at ~90) indicates a protein with both well-predicted and disordered regions -- this is invisible in a box plot.

**Function signature (chart builder only, no new computation):**

```python
def build_violin_chart(
    groups: dict[str, np.ndarray],
    dv_label: str,
    p_value: float | None = None,
    show_box: bool = True,
    show_points: bool = True,
) -> go.Figure:
    fig = go.Figure()
    for i, (name, values) in enumerate(groups.items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Violin(
            y=values, name=name,
            fillcolor=color.replace(")", ",0.3)").replace("rgb", "rgba")
                      if "rgb" in color
                      else f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.3)",
            line_color=color,
            box_visible=show_box,
            meanline_visible=True,
            points="all" if show_points and len(values) <= 100 else "outliers",
            pointpos=-0.5 if show_points else 0,
            jitter=0.3,
            hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
        ))

    fig.update_layout(**_BASE_LAYOUT, yaxis_title=dv_label, height=400, showlegend=False)

    if p_value is not None and len(groups) == 2:
        fig = _add_significance_bracket(fig, list(groups.keys()), p_value)
    return fig
```

**UI integration:** Add a toggle `st.radio("Plot type", ["Box", "Violin"], horizontal=True, key="stats_plot_type")` wherever the existing `build_comparison_chart` is displayed. Same data, different visualization.

---

### T1.8 Volcano Plot

**Biological context:** The standard chart for differential expression/proteomics data. X-axis = log2(fold change), Y-axis = -log10(p-value). Points in the upper corners are both statistically significant AND biologically meaningful. In the context of Luminous: compare variant effect sizes across structural domains, or compare predicted vs observed binding affinities across drug candidates.

**Function signature:**

```python
def build_volcano_plot(
    df: pd.DataFrame,
    fc_col: str,            # fold change column (will be log2-transformed if not already)
    p_col: str,             # p-value column
    label_col: str | None = None,  # optional labels for points
    fc_threshold: float = 1.0,     # log2FC threshold for significance
    p_threshold: float = 0.05,     # p-value threshold
    is_log2: bool = False,         # True if fc_col is already log2-transformed
) -> go.Figure:
    plot_df = df.dropna(subset=[fc_col, p_col]).copy()

    if not is_log2:
        plot_df["_log2fc"] = np.log2(plot_df[fc_col].clip(lower=1e-300))
    else:
        plot_df["_log2fc"] = plot_df[fc_col]

    plot_df["_neg_log10p"] = -np.log10(plot_df[p_col].clip(lower=1e-300))

    # Classify points
    conditions = [
        (plot_df["_log2fc"].abs() >= fc_threshold) & (plot_df[p_col] < p_threshold),  # significant
        (plot_df["_log2fc"].abs() >= fc_threshold) & (plot_df[p_col] >= p_threshold), # large FC, not sig
        (plot_df["_log2fc"].abs() < fc_threshold) & (plot_df[p_col] < p_threshold),   # sig, small FC
    ]
    categories = ["Significant", "Large FC only", "Significant (small FC)"]
    colors = [CB_PALETTE[1], CB_PALETTE[4], CB_PALETTE[3]]  # magenta, gold, purple
    default_color = "rgba(142,142,147,0.4)"

    fig = go.Figure()

    # Non-significant background
    ns_mask = ~(conditions[0] | conditions[1] | conditions[2])
    if ns_mask.sum() > 0:
        fig.add_trace(go.Scatter(
            x=plot_df.loc[ns_mask, "_log2fc"],
            y=plot_df.loc[ns_mask, "_neg_log10p"],
            mode="markers",
            marker=dict(color=default_color, size=5),
            name="Not significant",
            hovertemplate="log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>",
        ))

    for mask, cat, color in zip(conditions, categories, colors):
        if mask.sum() == 0:
            continue
        subset = plot_df[mask]
        hover_labels = subset[label_col].astype(str) if label_col else [""]*len(subset)
        fig.add_trace(go.Scatter(
            x=subset["_log2fc"],
            y=subset["_neg_log10p"],
            mode="markers+text" if label_col and len(subset) <= 20 else "markers",
            text=hover_labels if label_col and len(subset) <= 20 else None,
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(color=color, size=8, line=dict(color="white", width=0.5)),
            name=cat,
            hovertemplate=(
                f"<b>%{{text}}</b><br>" if label_col else ""
            ) + "log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>",
        ))

    # Threshold lines
    fig.add_vline(x=fc_threshold, line_dash="dash", line_color="rgba(60,60,67,0.2)")
    fig.add_vline(x=-fc_threshold, line_dash="dash", line_color="rgba(60,60,67,0.2)")
    fig.add_hline(y=-np.log10(p_threshold), line_dash="dash", line_color="rgba(60,60,67,0.2)",
                  annotation_text=f"p = {p_threshold}", annotation_position="right")

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="log2(Fold Change)",
        yaxis_title="-log10(p-value)",
        height=500,
    )
    return fig
```

**Input validation:**
- `fc_col` must be numeric; if values include 0 or negative (and `is_log2=False`), clip with warning
- `p_col` must be numeric in (0, 1]; values of exactly 0 are clipped to 1e-300
- Edge case: all p-values identical -> flat horizontal line, warn "No variation in p-values"

**Integration with protein data:** After running multiple per-residue tests (e.g., ANOVA across chains for each residue position), collect the fold changes and p-values into a DataFrame. Volcano plot shows which residue positions have significantly different behavior across chains/conditions.

**UI integration:** New analysis sub-type under `"Statistical Tests"` category, or as a dedicated visualization option when the user has a DataFrame with fold change and p-value columns. The UI auto-detects columns named `fold_change`, `fc`, `log2fc`, `pvalue`, `p_value`, `padj`.

---

### T1.9 Correlation Matrix Heatmap

**Biological context:** When a biologist has 5+ structural properties per residue (pLDDT, SASA, packing density, B-factor, distance to active site), they need a quick overview of which properties correlate. A correlation matrix heatmap is the standard first step.

**Function signature:**

```python
def compute_correlation_matrix(
    df: pd.DataFrame,
    columns: list[str],
    method: str = "pearson",  # or "spearman"
) -> dict:
    """Compute pairwise correlation matrix with p-values.

    Returns dict with keys:
        corr_matrix: dict (DataFrame.to_dict())
        p_matrix: dict (DataFrame.to_dict())
        method: str
    """
    import pingouin as pg

    n = len(columns)
    corr = np.zeros((n, n))
    pvals = np.zeros((n, n))

    for i in range(n):
        for j in range(i, n):
            if i == j:
                corr[i, j] = 1.0
                pvals[i, j] = 0.0
            else:
                result = pg.corr(
                    df[columns[i]].dropna(),
                    df[columns[j]].dropna(),
                    method=method,
                )
                corr[i, j] = corr[j, i] = float(result["r"].iloc[0])
                pvals[i, j] = pvals[j, i] = float(result["p-val"].iloc[0])

    corr_df = pd.DataFrame(corr, index=columns, columns=columns)
    p_df = pd.DataFrame(pvals, index=columns, columns=columns)

    return {
        "corr_matrix": corr_df.to_dict(),
        "p_matrix": p_df.to_dict(),
        "method": method,
    }
```

**Plotly chart:**

```python
def build_correlation_heatmap(
    corr_result: dict,
    p_threshold: float = 0.05,
) -> go.Figure:
    corr_df = pd.DataFrame(corr_result["corr_matrix"])
    p_df = pd.DataFrame(corr_result["p_matrix"])
    labels = corr_df.columns.tolist()

    # Build annotation text: r value with significance stars
    annotations = []
    for i in range(len(labels)):
        for j in range(len(labels)):
            r_val = corr_df.iloc[i, j]
            p_val = p_df.iloc[i, j]
            stars = "***" if p_val < 0.001 else "**" if p_val < 0.01 else "*" if p_val < 0.05 else ""
            annotations.append(f"{r_val:.2f}{stars}")

    text_matrix = np.array(annotations).reshape(len(labels), len(labels))

    fig = go.Figure(data=go.Heatmap(
        z=corr_df.values,
        x=labels, y=labels,
        colorscale=[
            [0, CB_PALETTE[1]],     # magenta for -1
            [0.5, "#FFFFFF"],       # white for 0
            [1, CB_PALETTE[0]],     # blue for +1
        ],
        zmin=-1, zmax=1,
        text=text_matrix,
        texttemplate="%{text}",
        textfont=dict(size=11),
        hovertemplate="%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>",
        colorbar=dict(title="r", len=0.8),
    ))

    fig.update_layout(
        **_BASE_LAYOUT,
        height=max(350, 60 * len(labels)),
        width=max(350, 60 * len(labels)),
        xaxis_tickangle=-45,
    )
    return fig
```

**Input validation:**
- At least 2 numeric columns required
- At most 20 columns (above that, the heatmap is unreadable)
- Each column pair must have at least 3 non-NaN overlapping observations

**Integration:** Select multiple numeric columns from the data editor. Natural for residue-level data from `structure_analysis.py`.

---

### T1.10 Paired Before/After Plot (Slopegraph)

**Biological context:** Longitudinal paired measurements -- protein expression before/after drug treatment in the same samples. Each line connects one sample's before and after, making it immediately clear which samples responded.

**Function signature (chart builder):**

```python
def build_slopegraph(
    before: np.ndarray,
    after: np.ndarray,
    labels: list[str] | None = None,
    before_label: str = "Before",
    after_label: str = "After",
    p_value: float | None = None,
) -> go.Figure:
    fig = go.Figure()
    n = len(before)

    # Individual lines
    for i in range(n):
        change = after[i] - before[i]
        color = CB_PALETTE[0] if change >= 0 else CB_PALETTE[1]  # blue=increase, magenta=decrease
        label = labels[i] if labels else f"Sample {i+1}"
        fig.add_trace(go.Scatter(
            x=[before_label, after_label],
            y=[before[i], after[i]],
            mode="lines+markers",
            line=dict(color=color, width=1.5),
            marker=dict(color=color, size=7),
            name=label,
            showlegend=False,
            hovertemplate=f"<b>{label}</b><br>%{{x}}: %{{y:.3f}}<extra></extra>",
        ))

    # Mean lines (thicker)
    mean_before = float(np.nanmean(before))
    mean_after = float(np.nanmean(after))
    fig.add_trace(go.Scatter(
        x=[before_label, after_label],
        y=[mean_before, mean_after],
        mode="lines+markers",
        line=dict(color="#000000", width=3),
        marker=dict(color="#000000", size=10),
        name="Mean",
    ))

    if p_value is not None:
        p_text = f"p = {p_value:.4f}" if p_value >= 0.001 else "p < 0.001"
        fig.add_annotation(
            text=f"Paired test: {p_text}",
            xref="paper", yref="paper", x=0.5, y=1.05,
            showarrow=False, font=dict(size=12, color="rgba(60,60,67,0.75)"),
        )

    fig.update_layout(**_BASE_LAYOUT, height=400, yaxis_title="Value")
    return fig
```

**Integration:** Natural companion to paired t-test and Wilcoxon signed-rank test already in the plan. When a paired test is selected, offer slopegraph as the default visualization instead of (or alongside) box plots.

---

### T1.11 Additional Curve Equations (Expanding from 8 to ~25)

All of the following use the existing `fit_curve()` function from section 6.3 of the existing plan. They only need a new entry in the `BUILTIN_EQUATIONS` dict. No new infrastructure needed.

**Group 1: Binding equations**

```python
# All entries for BUILTIN_EQUATIONS dict in src/statistics_engine.py

"One-Site Specific Binding": {
    "formula_display": "Y = Bmax * X / (Kd + X)",
    "func": lambda x, bmax, kd: bmax * x / (kd + x),
    "param_names": ["Bmax", "Kd"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(x[np.argmin(np.abs(y - np.nanmax(y)/2))])],
    "bounds": ([0, 0], [np.inf, np.inf]),
    "min_points": 4,
    "description": "Single binding site (identical to Michaelis-Menten form). X = ligand concentration, Y = bound fraction.",
    "category": "Binding",
},

"Two-Site Binding": {
    "formula_display": "Y = Bmax1 * X / (Kd1 + X) + Bmax2 * X / (Kd2 + X)",
    "func": lambda x, bmax1, kd1, bmax2, kd2: bmax1 * x / (kd1 + x) + bmax2 * x / (kd2 + x),
    "param_names": ["Bmax1", "Kd1", "Bmax2", "Kd2"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 0.6, float(np.nanmedian(x)) * 0.1,
                                    float(np.nanmax(y)) * 0.4, float(np.nanmedian(x)) * 10],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Two independent binding sites with different affinities. Use when one-site fit is poor.",
    "category": "Binding",
},

"Competitive Binding": {
    "formula_display": "Y = Bmax * X / (X + Kd * (1 + I/Ki))",
    "func": lambda x, bmax, kd, ki, I: bmax * x / (x + kd * (1 + I / ki)),
    "param_names": ["Bmax", "Kd", "Ki", "I_conc"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(np.nanmedian(x)), float(np.nanmedian(x)), 1.0],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Binding in presence of competitive inhibitor at concentration I. Ki = inhibitor dissociation constant.",
    "category": "Binding",
},

"Saturation Binding (with NSB)": {
    "formula_display": "Y = Bmax * X / (Kd + X) + NS * X",
    "func": lambda x, bmax, kd, ns: bmax * x / (kd + x) + ns * x,
    "param_names": ["Bmax", "Kd", "NS"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 0.8, float(np.nanmedian(x)), 0.01],
    "bounds": ([0, 0, -np.inf], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "Saturation binding with non-specific binding (NSB) component. NS = slope of linear NSB.",
    "category": "Binding",
},
```

**Group 2: Enzyme kinetics (extending Michaelis-Menten already in plan)**

```python
"Substrate Inhibition": {
    "formula_display": "v = Vmax * [S] / (Km + [S] * (1 + [S]/Ki))",
    "func": lambda x, vmax, km, ki: vmax * x / (km + x * (1 + x / ki)),
    "param_names": ["Vmax", "Km", "Ki"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.2, float(np.nanmedian(x)), float(np.nanmax(x)) * 5],
    "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "Michaelis-Menten with substrate inhibition at high [S]. Velocity decreases beyond optimal [S].",
    "category": "Enzyme Kinetics",
},

"Allosteric Sigmoidal": {
    "formula_display": "v = Vmax * [S]^n / (K_half^n + [S]^n)",
    "func": lambda x, vmax, k_half, n: vmax * x**n / (k_half**n + x**n),
    "param_names": ["Vmax", "K_half", "n"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(np.nanmedian(x)), 2.0],
    "bounds": ([0, 0, 0.1], [np.inf, np.inf, 20]),
    "min_points": 5,
    "description": "Sigmoidal enzyme kinetics (Hill equation for enzymes). n > 1 = positive cooperativity.",
    "category": "Enzyme Kinetics",
},

"Competitive Inhibition": {
    "formula_display": "v = Vmax * [S] / ([S] + Km * (1 + [I]/Ki))",
    "func": lambda x, vmax, km, ki, I: vmax * x / (x + km * (1 + I / ki)),
    "param_names": ["Vmax", "Km", "Ki", "I_conc"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(np.nanmedian(x)), float(np.nanmedian(x)), 1.0],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Competitive enzyme inhibition. I_conc is fixed inhibitor concentration. Increases apparent Km, Vmax unchanged.",
    "category": "Enzyme Kinetics",
},

"Uncompetitive Inhibition": {
    "formula_display": "v = Vmax * [S] / (Km + [S] * (1 + [I]/Ki))",
    "func": lambda x, vmax, km, ki, I: vmax * x / (km + x * (1 + I / ki)),
    "param_names": ["Vmax", "Km", "Ki", "I_conc"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(np.nanmedian(x)), float(np.nanmedian(x)) * 5, 1.0],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Uncompetitive inhibition. Decreases both apparent Vmax and Km by same factor.",
    "category": "Enzyme Kinetics",
},

"Noncompetitive Inhibition": {
    "formula_display": "v = Vmax * [S] / ((Km + [S]) * (1 + [I]/Ki))",
    "func": lambda x, vmax, km, ki, I: vmax * x / ((km + x) * (1 + I / ki)),
    "param_names": ["Vmax", "Km", "Ki", "I_conc"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.5, float(np.nanmedian(x)), float(np.nanmedian(x)) * 5, 1.0],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Noncompetitive (mixed) inhibition. Decreases apparent Vmax, Km unchanged.",
    "category": "Enzyme Kinetics",
},
```

**Group 3: Growth models**

```python
"Exponential Growth": {
    "formula_display": "Y = Y0 * exp(K * x)",
    "func": lambda x, y0, k: y0 * np.exp(k * x),
    "param_names": ["Y0", "K"],
    "initial_guess": lambda x, y: [float(y[np.argmin(x)]), 0.1],
    "bounds": ([0, -np.inf], [np.inf, np.inf]),
    "min_points": 3,
    "description": "Unlimited exponential growth. K > 0 = growth, K < 0 = decay.",
    "category": "Growth",
},

"Logistic Growth": {
    "formula_display": "Y = K_cap / (1 + ((K_cap - Y0)/Y0) * exp(-r * x))",
    "func": lambda x, k_cap, y0, r: k_cap / (1 + ((k_cap - y0) / y0) * np.exp(-r * x)),
    "param_names": ["K_cap", "Y0", "r"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 1.1, float(np.nanmin(y[y > 0])) if (y > 0).any() else 0.1, 0.1],
    "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "S-shaped growth with carrying capacity K_cap. Standard for bacterial/cell growth.",
    "category": "Growth",
},

"Gompertz Growth": {
    "formula_display": "Y = A * exp(-exp(mu * e / A * (lag - x) + 1))",
    "func": lambda x, a, mu, lag: a * np.exp(-np.exp(mu * np.e / a * (lag - x) + 1)),
    "param_names": ["A", "mu", "lag"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)), float(np.nanmax(np.diff(y))) if len(y) > 1 else 1.0, float(x[0])],
    "bounds": ([0, 0, -np.inf], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "Asymmetric sigmoidal growth. Common for tumor growth and microbial growth with lag phase.",
    "category": "Growth",
},
```

**Group 4: Pharmacokinetics**

```python
"One-Compartment IV Bolus": {
    "formula_display": "C(t) = D/Vd * exp(-Ke * t)",
    "func": lambda x, d_vd, ke: d_vd * np.exp(-ke * x),
    "param_names": ["D_over_Vd", "Ke"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)), 0.1],
    "bounds": ([0, 0], [np.inf, np.inf]),
    "min_points": 4,
    "description": "Plasma concentration after IV bolus. D/Vd = dose/volume of distribution. Ke = elimination rate.",
    "category": "Pharmacokinetics",
},

"One-Compartment Oral": {
    "formula_display": "C(t) = F*D*Ka / (Vd*(Ka-Ke)) * (exp(-Ke*t) - exp(-Ka*t))",
    "func": lambda x, fdk_v, ka, ke: fdk_v * ka / (ka - ke) * (np.exp(-ke * x) - np.exp(-ka * x)),
    "param_names": ["FDK_over_Vd", "Ka", "Ke"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 5, 1.0, 0.1],
    "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "Plasma concentration after oral dose. Ka = absorption rate, Ke = elimination rate. Ka must be > Ke.",
    "category": "Pharmacokinetics",
},

"Two-Compartment IV": {
    "formula_display": "C(t) = A * exp(-alpha * t) + B * exp(-beta * t)",
    "func": lambda x, a, alpha, b, beta: a * np.exp(-alpha * x) + b * np.exp(-beta * x),
    "param_names": ["A", "alpha", "B", "beta"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)) * 0.7, 1.0, float(np.nanmax(y)) * 0.3, 0.1],
    "bounds": ([0, 0, 0, 0], [np.inf, np.inf, np.inf, np.inf]),
    "min_points": 6,
    "description": "Bi-exponential PK model. Fast (alpha) distribution phase + slow (beta) elimination phase.",
    "category": "Pharmacokinetics",
},
```

**Group 5: Decay (extending existing exponential decay)**

```python
"Two-Phase Decay": {
    "formula_display": "Y = Span1 * exp(-K1 * x) + Span2 * exp(-K2 * x) + Plateau",
    "func": lambda x, span1, k1, span2, k2, plateau: span1 * np.exp(-k1 * x) + span2 * np.exp(-k2 * x) + plateau,
    "param_names": ["Span1", "K1", "Span2", "K2", "Plateau"],
    "initial_guess": lambda x, y: [float(np.nanmax(y) - np.nanmin(y)) * 0.6, 1.0,
                                    float(np.nanmax(y) - np.nanmin(y)) * 0.4, 0.1, float(np.nanmin(y))],
    "bounds": ([0, 0, 0, 0, -np.inf], [np.inf, np.inf, np.inf, np.inf, np.inf]),
    "min_points": 7,
    "description": "Bi-exponential decay. Fast and slow components (e.g., protein degradation with two pathways).",
    "category": "Decay",
},

"Plateau Then Decay": {
    "formula_display": "Y = IF(x < t_lag, Y0, Y0 * exp(-K * (x - t_lag)))",
    "func": lambda x, y0, k, t_lag: np.where(x < t_lag, y0, y0 * np.exp(-k * (x - t_lag))),
    "param_names": ["Y0", "K", "t_lag"],
    "initial_guess": lambda x, y: [float(np.nanmax(y)), 0.1, float(np.nanmedian(x))],
    "bounds": ([0, 0, 0], [np.inf, np.inf, np.inf]),
    "min_points": 5,
    "description": "Stable plateau followed by exponential decay after a lag time. Common for protein stability assays.",
    "category": "Decay",
},
```

**Which use existing fit_curve() vs need new infrastructure:**

All 17 new equations above use the existing `fit_curve()` function. They only require adding their dict entry to `BUILTIN_EQUATIONS`. The fit_curve function handles arbitrary lambdas, bounds, initial guesses, confidence bands, and goodness-of-fit metrics generically.

**The only exception:** The "Plateau Then Decay" uses `np.where()`, which creates a discontinuous function. `scipy.optimize.curve_fit` can handle this but may be more sensitive to initial guesses. The `_guess` function for this equation should use a heuristic: t_lag = x value where y first drops below 95% of max(y).

**UI change for curve equations:** Instead of a flat dropdown of ~25 equations, organize by category:

```python
eq_categories = {
    "Dose-Response": ["4PL (Dose-Response)"],
    "Binding": ["One-Site Specific Binding", "Two-Site Binding", "Competitive Binding",
                 "Saturation Binding (with NSB)"],
    "Enzyme Kinetics": ["Michaelis-Menten", "Substrate Inhibition", "Allosteric Sigmoidal",
                         "Competitive Inhibition", "Uncompetitive Inhibition", "Noncompetitive Inhibition"],
    "Growth": ["Exponential Growth", "Logistic Growth", "Gompertz Growth"],
    "Pharmacokinetics": ["One-Compartment IV Bolus", "One-Compartment Oral", "Two-Compartment IV"],
    "Decay": ["Exponential Decay", "Two-Phase Decay", "Plateau Then Decay"],
    "Cooperativity": ["Hill Equation"],
    "Polynomial": ["Linear", "Polynomial (degree 2)", "Polynomial (degree 3)", "Polynomial (degree 4)"],
}

cat = st.selectbox("Equation category", list(eq_categories.keys()), key="stats_eq_category")
eq_name = st.selectbox("Equation", eq_categories[cat], key="stats_eq_selector")
```

For equations with a fixed parameter (like I_conc in competitive inhibition), show an additional `st.number_input` for the fixed inhibitor concentration. The `fit_curve` function receives a partial application:

```python
if "I_conc" in eq["param_names"]:
    i_conc = st.number_input("Inhibitor concentration [I]", value=1.0, key="stats_i_conc")
    # Create a wrapper that fixes I_conc
    original_func = eq["func"]
    eq["func"] = lambda x, *params, _i=i_conc: original_func(x, *params, _i)
    eq["param_names"] = [p for p in eq["param_names"] if p != "I_conc"]
    eq["initial_guess"] = lambda x, y: eq["initial_guess"](x, y)[:-1]
    eq["bounds"] = (eq["bounds"][0][:-1], eq["bounds"][1][:-1])
```

---

## TIER 2: "Power users need this monthly" (NICE TO HAVE)

### T2.1 PCA (2D Biplot + Scree Plot)

**Biological context:** A researcher has per-residue data with 5-10 features (pLDDT, SASA, packing density, B-factor, secondary structure encoding, distance to active site, distance to nearest pathogenic variant, conservation score). PCA reveals whether residues cluster by functional region (active site vs surface vs interface) and which structural properties drive that clustering.

**Function signature:**

```python
def run_pca(
    df: pd.DataFrame,
    columns: list[str],
    n_components: int = 2,
    label_col: str | None = None,
    color_col: str | None = None,
) -> dict:
    """PCA with standardization.

    Returns dict with keys:
        explained_variance_ratio: list[float]
        cumulative_variance: list[float]
        loadings: dict[str, list[float]]  -- {col_name: [PC1_loading, PC2_loading, ...]}
        scores: list[dict]  -- [{PC1: x, PC2: y, label: ..., color: ...}, ...]
        n_components: int
    """
    from sklearn.preprocessing import StandardScaler
    from sklearn.decomposition import PCA

    X = df[columns].dropna().values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    pca = PCA(n_components=min(n_components, len(columns), len(X)))
    scores = pca.fit_transform(X_scaled)

    loadings = {col: pca.components_[:, i].tolist() for i, col in enumerate(columns)}

    score_dicts = []
    clean_idx = df[columns].dropna().index
    for i in range(len(scores)):
        entry = {f"PC{j+1}": float(scores[i, j]) for j in range(scores.shape[1])}
        if label_col and label_col in df.columns:
            entry["label"] = str(df.loc[clean_idx[i], label_col])
        if color_col and color_col in df.columns:
            entry["color"] = str(df.loc[clean_idx[i], color_col])
        score_dicts.append(entry)

    return {
        "explained_variance_ratio": pca.explained_variance_ratio_.tolist(),
        "cumulative_variance": np.cumsum(pca.explained_variance_ratio_).tolist(),
        "loadings": loadings,
        "scores": score_dicts,
        "n_components": pca.n_components_,
    }
```

**Input validation:**
- At least 2 numeric columns
- At least 10 rows
- No columns with zero variance (remove with warning)
- Edge case: more columns than rows -> warn "More features than samples. Results may be unstable."

**Plotly charts (two):**

1. **Biplot** (scores + loading vectors):

```python
def build_pca_biplot(pca_result: dict) -> go.Figure:
    fig = go.Figure()

    scores = pca_result["scores"]
    evr = pca_result["explained_variance_ratio"]

    # Color by group if available
    colors_available = "color" in scores[0]
    if colors_available:
        unique_colors = list(dict.fromkeys(s["color"] for s in scores))
        color_map = {c: CB_PALETTE[i % len(CB_PALETTE)] for i, c in enumerate(unique_colors)}

    for s in scores:
        color = color_map[s["color"]] if colors_available else CB_PALETTE[0]
        fig.add_trace(go.Scatter(
            x=[s["PC1"]], y=[s["PC2"]], mode="markers",
            marker=dict(color=color, size=7, opacity=0.7),
            name=s.get("color", ""), showlegend=False,
            hovertemplate=f"PC1: %{{x:.2f}}<br>PC2: %{{y:.2f}}<br>{s.get('label', '')}<extra></extra>",
        ))

    # Loading vectors as arrows
    for col_name, loading in pca_result["loadings"].items():
        scale = 3  # scale arrows for visibility
        fig.add_annotation(
            ax=0, ay=0, x=loading[0]*scale, y=loading[1]*scale,
            arrowhead=3, arrowsize=1.5, arrowwidth=1.5,
            arrowcolor=CB_PALETTE[1],
        )
        fig.add_annotation(
            x=loading[0]*scale*1.15, y=loading[1]*scale*1.15,
            text=col_name, showarrow=False,
            font=dict(size=10, color=CB_PALETTE[1]),
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=f"PC1 ({evr[0]*100:.1f}%)",
        yaxis_title=f"PC2 ({evr[1]*100:.1f}%)" if len(evr) > 1 else "PC2",
        height=450,
    )
    return fig
```

2. **Scree plot:**

```python
def build_scree_plot(pca_result: dict) -> go.Figure:
    evr = pca_result["explained_variance_ratio"]
    cumvar = pca_result["cumulative_variance"]
    pcs = [f"PC{i+1}" for i in range(len(evr))]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=pcs, y=[v*100 for v in evr],
        marker_color=CB_PALETTE[0], name="Individual",
    ))
    fig.add_trace(go.Scatter(
        x=pcs, y=[v*100 for v in cumvar],
        mode="lines+markers", line=dict(color=CB_PALETTE[1], width=2),
        marker=dict(color=CB_PALETTE[1], size=8), name="Cumulative",
    ))
    fig.add_hline(y=80, line_dash="dash", line_color="rgba(60,60,67,0.3)",
                  annotation_text="80% threshold")

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Principal Component",
        yaxis_title="Variance Explained (%)",
        height=300,
    )
    return fig
```

**Integration with protein data:** Feed residue-level data from `structure_analysis.py` (SASA, packing density, secondary structure) + `prediction_result` (pLDDT) + `variant_analyzer` (pathogenicity labels for coloring). PCA reveals whether pathogenic variants cluster in a distinct structural "neighborhood".

**UI integration:** New analysis mode under the `"Statistical Tests"` radio or as a fourth mode: `"Dimensionality Reduction"`. User selects multiple numeric columns and optionally a color/label column.

---

### T2.2 K-Means Clustering with Elbow Plot

**Biological context:** Group residues into clusters based on structural properties. Are there 2 or 5 distinct structural environments in this protein? Which residues belong to each cluster? This is exploratory -- used before hypothesis testing to find natural groupings.

**Function signature:**

```python
def run_kmeans(
    df: pd.DataFrame,
    columns: list[str],
    max_k: int = 10,
    chosen_k: int | None = None,
) -> dict:
    """K-means clustering with elbow analysis.

    Returns dict with keys:
        elbow_data: dict  -- {k: inertia} for k=2..max_k
        optimal_k: int  -- from elbow heuristic
        labels: list[int]  -- cluster assignments for chosen_k
        centroids: list[dict]  -- {col_name: centroid_value} for each cluster
        silhouette: float  -- silhouette score for chosen_k
    """
    from sklearn.cluster import KMeans
    from sklearn.preprocessing import StandardScaler
    from sklearn.metrics import silhouette_score

    X = df[columns].dropna().values
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Elbow analysis
    max_k = min(max_k, len(X) - 1)
    inertias = {}
    for k in range(2, max_k + 1):
        km = KMeans(n_clusters=k, n_init=10, random_state=42)
        km.fit(X_scaled)
        inertias[k] = float(km.inertia_)

    # Elbow heuristic: largest drop in inertia
    if len(inertias) >= 3:
        ks = sorted(inertias.keys())
        diffs = [inertias[ks[i]] - inertias[ks[i+1]] for i in range(len(ks)-1)]
        diffs2 = [diffs[i] - diffs[i+1] for i in range(len(diffs)-1)]
        optimal_k = ks[np.argmax(diffs2) + 1] if diffs2 else ks[0]
    else:
        optimal_k = 2

    # Final clustering
    final_k = chosen_k or optimal_k
    km_final = KMeans(n_clusters=final_k, n_init=10, random_state=42)
    labels = km_final.fit_predict(X_scaled)

    sil = silhouette_score(X_scaled, labels) if final_k > 1 and final_k < len(X) else 0.0

    # Centroids in original scale
    centroids_orig = scaler.inverse_transform(km_final.cluster_centers_)
    centroids = [{col: float(centroids_orig[c, i]) for i, col in enumerate(columns)}
                 for c in range(final_k)]

    return {
        "elbow_data": inertias,
        "optimal_k": optimal_k,
        "labels": labels.tolist(),
        "centroids": centroids,
        "silhouette": float(sil),
        "chosen_k": final_k,
    }
```

**Input validation:**
- At least 2 numeric columns, at least 10 rows
- max_k cannot exceed n_samples - 1
- Edge case: all values identical in a column -> remove column with warning

**Plotly charts:** Elbow plot (bar of inertia vs k) and scatter of PC1 vs PC2 colored by cluster label (reuse PCA biplot with cluster colors).

**Integration:** After PCA reveals structure in the data, K-means finds the clusters formally. Labels can then be used as the grouping variable for ANOVA ("does pLDDT differ across structural clusters?").

---

### T2.3 Multiple Linear Regression

**Biological context:** Predict a continuous outcome (e.g., binding affinity) from multiple structural features (SASA, pLDDT, distance to active site, packing density). More interpretable than logistic regression when the outcome is continuous.

**Function signature:**

```python
def run_multiple_regression(
    df: pd.DataFrame,
    outcome: str,
    predictors: list[str],
) -> dict:
    """Multiple linear regression with diagnostics.

    Returns dict with keys:
        test_name, r_squared, adj_r_squared, f_statistic, f_p_value,
        coefficients (dict), p_values (dict), ci95 (dict),
        vif (dict), durbin_watson, residuals (list), y_pred (list),
        result_df (list[dict])
    """
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.stats.stattools import durbin_watson

    y = df[outcome].astype(float)
    X = df[predictors].astype(float)
    X = sm.add_constant(X)

    mask = ~(X.isna().any(axis=1) | y.isna())
    X_clean, y_clean = X[mask], y[mask]

    model = sm.OLS(y_clean, X_clean)
    result = model.fit()

    # VIF for multicollinearity
    vif = {}
    for i, col in enumerate(predictors):
        col_idx = i + 1  # skip constant
        vif[col] = float(variance_inflation_factor(X_clean.values, col_idx))

    pred_names = [c for c in X_clean.columns if c != "const"]

    return {
        "test_name": "Multiple Linear Regression",
        "r_squared": float(result.rsquared),
        "adj_r_squared": float(result.rsquared_adj),
        "f_statistic": float(result.fvalue),
        "f_p_value": float(result.f_pvalue),
        "coefficients": {n: float(result.params[n]) for n in pred_names},
        "p_values": {n: float(result.pvalues[n]) for n in pred_names},
        "ci95": {n: (float(result.conf_int().loc[n, 0]),
                     float(result.conf_int().loc[n, 1])) for n in pred_names},
        "vif": vif,
        "durbin_watson": float(durbin_watson(result.resid)),
        "residuals": result.resid.tolist(),
        "y_pred": result.fittedvalues.tolist(),
        "result_df": result.summary2().tables[1].to_dict("records") if hasattr(result.summary2().tables[1], "to_dict") else [],
    }
```

**Input validation:**
- All columns must be numeric
- n > p + 10 (at least 10 more observations than predictors)
- VIF > 10 triggers warning about multicollinearity
- Durbin-Watson far from 2.0 triggers warning about autocorrelation

**Plotly charts:** Coefficient forest plot (similar to odds ratio forest) + residuals vs fitted values scatter + Q-Q plot of residuals (reuse existing `build_residual_plot` and `build_qq_plot`).

---

### T2.4 Repeated Measures ANOVA

**Biological context:** Measuring the same protein's binding affinity at multiple time points or under multiple conditions. Each sample contributes multiple measurements, so observations are not independent.

**Function signature:**

```python
def run_repeated_measures_anova(
    df: pd.DataFrame,
    dv: str,
    within: str,
    subject: str,
) -> dict:
    """Repeated measures ANOVA.

    Returns dict with keys:
        test_name, F, p_val, eta_squared, sphericity (Mauchly test),
        epsilon (Greenhouse-Geisser), corrected_p (if sphericity violated),
        posthoc_df, result_df
    """
    import pingouin as pg

    result = pg.rm_anova(data=df, dv=dv, within=within, subject=subject, detailed=True)

    # Sphericity
    sphericity = pg.sphericity(data=df, dv=dv, within=within, subject=subject)

    posthoc = None
    if float(result["p-unc"].iloc[0]) < 0.05:
        posthoc = pg.pairwise_tests(
            data=df, dv=dv, within=within, subject=subject,
            padjust="bonf"
        )

    return {
        "test_name": "Repeated Measures ANOVA",
        "F": float(result["F"].iloc[0]),
        "p_val": float(result["p-unc"].iloc[0]),
        "p_val_gg": float(result["p-GG-corr"].iloc[0]) if "p-GG-corr" in result.columns else None,
        "eta_squared": float(result["np2"].iloc[0]),
        "sphericity_p": float(sphericity[1]) if isinstance(sphericity, tuple) else None,
        "epsilon_gg": float(result["eps"].iloc[0]) if "eps" in result.columns else None,
        "result_df": result.to_dict("records"),
        "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
    }
```

**Input validation:**
- Data must be in long format
- `subject` column identifies repeated measurements
- Each subject must have same number of observations per level of `within`
- Edge case: missing data for some subjects at some time points -> `st.warning("Incomplete data. Subjects with missing timepoints will be excluded.")`
- Sphericity: if Mauchly's test is significant (p < 0.05), automatically report Greenhouse-Geisser corrected p-value

**Plotly chart:** Slopegraph (reuse `build_slopegraph`) with individual subject trajectories, or line plot with mean +/- SEM at each within-level.

**Integration:** For a protein measured at multiple drug concentrations, or residue properties measured across multiple conformational states (from molecular dynamics trajectories).

---

## TIER 3: Explicitly Skipped

The following are explicitly excluded from this plan to maintain scope:
- Mixed effects models, nested ANOVA, Poisson regression, GLMs, Deming regression
- Differential equation fitting, implicit equations, global regression (multiple datasets simultaneously)
- Hierarchical clustering, dendrograms, confidence ellipses for PCA
- Family cloning (Prism's template system), analysis checklists, 8 table output types

---

## Summary: Equation Audit

| # | Equation Name | Existing fit_curve() | New Infrastructure? | Category |
|---|---|---|---|---|
| 1 | 4PL (Dose-Response) | Yes (existing) | No | Dose-Response |
| 2 | Michaelis-Menten | Yes (existing) | No | Enzyme Kinetics |
| 3 | Hill Equation | Yes (existing) | No | Cooperativity |
| 4 | Exponential Decay | Yes (existing) | No | Decay |
| 5 | Linear | Yes (existing) | No | Polynomial |
| 6 | Polynomial deg 2 | Yes (existing) | No | Polynomial |
| 7 | Polynomial deg 3 | Yes (existing) | No | Polynomial |
| 8 | Polynomial deg 4 | Yes (existing) | No | Polynomial |
| 9 | One-Site Specific Binding | Yes (dict entry only) | No | Binding |
| 10 | Two-Site Binding | Yes (dict entry only) | No | Binding |
| 11 | Competitive Binding | Yes (dict entry only) | Partial: needs fixed-param UI | Binding |
| 12 | Saturation Binding (with NSB) | Yes (dict entry only) | No | Binding |
| 13 | Substrate Inhibition | Yes (dict entry only) | No | Enzyme Kinetics |
| 14 | Allosteric Sigmoidal | Yes (dict entry only) | No | Enzyme Kinetics |
| 15 | Competitive Inhibition | Yes (dict entry only) | Partial: needs fixed-param UI | Enzyme Kinetics |
| 16 | Uncompetitive Inhibition | Yes (dict entry only) | Partial: needs fixed-param UI | Enzyme Kinetics |
| 17 | Noncompetitive Inhibition | Yes (dict entry only) | Partial: needs fixed-param UI | Enzyme Kinetics |
| 18 | Exponential Growth | Yes (dict entry only) | No | Growth |
| 19 | Logistic Growth | Yes (dict entry only) | No | Growth |
| 20 | Gompertz Growth | Yes (dict entry only) | No | Growth |
| 21 | One-Compartment IV Bolus | Yes (dict entry only) | No | Pharmacokinetics |
| 22 | One-Compartment Oral | Yes (dict entry only) | No | Pharmacokinetics |
| 23 | Two-Compartment IV | Yes (dict entry only) | No | Pharmacokinetics |
| 24 | Two-Phase Decay | Yes (dict entry only) | No | Decay |
| 25 | Plateau Then Decay | Yes (dict entry only) | No (np.where works in curve_fit) | Decay |

**"Partial: needs fixed-param UI"** = 4 equations that include a fixed parameter (inhibitor concentration `I`). These need a `st.number_input` in the UI that creates a partial function wrapping the equation. This is approximately 15 lines of shared logic in `components/statistics_tab.py`, not a new infrastructure function.

---

## Implementation Sequence (Addendum Only)

**Phase A: Equation expansion (30 min)** -- Add 17 new equation dict entries to `BUILTIN_EQUATIONS` in `src/statistics_engine.py`. Add the category-based selectbox UI in `components/statistics_tab.py`. Add the fixed-parameter input logic (4 equations). This is purely additive and touches only the existing curve fitting section.

**Phase B: New statistical tests (45 min)** -- Add `run_two_way_anova`, `run_fisher_exact`, `run_welch_anova`, `run_logistic_regression`, `compute_roc_curve`, `compute_bland_altman` to `src/statistics_engine.py`. Update the test category selectbox in `components/statistics_tab.py` to include the new categories ("Classifier Performance", "Method Comparison") and tests.

**Phase C: New chart builders (30 min)** -- Add `build_interaction_plot`, `build_contingency_chart`, `build_violin_chart`, `build_volcano_plot`, `build_correlation_heatmap`, `build_slopegraph`, `build_odds_ratio_forest`, `build_roc_chart`, `build_bland_altman_chart` to `src/statistics_charts.py`.

**Phase D: TIER 2 features (45 min, if time permits)** -- Add `run_pca`, `run_kmeans`, `run_multiple_regression`, `run_repeated_measures_anova` to `src/statistics_engine.py`. Add `build_pca_biplot`, `build_scree_plot`, `build_elbow_plot` to `src/statistics_charts.py`. Add "Dimensionality Reduction" and "Clustering" modes to the statistics tab radio.

**Phase E: Integration wiring (15 min)** -- Update the `compute_correlation_matrix` function to use the pairwise approach with p-values. Ensure volcano plot auto-detects appropriate column names. Wire ROC to appear automatically after logistic regression.

---

## Dependencies Impact

No new dependencies beyond what the existing plan already specifies. `pingouin>=0.5.5` transitively brings `statsmodels` and `scikit-learn`, which provide everything needed for TIER 1 and TIER 2:

| Feature | Library | Already a dependency of pingouin? |
|---|---|---|
| Two-way ANOVA, Welch's ANOVA, rm-ANOVA | pingouin | Direct |
| Fisher's exact | scipy | Already in env |
| Logistic regression, Multiple regression | statsmodels | Transitive via pingouin |
| ROC curve, PCA, K-means | scikit-learn | Transitive via pingouin |
| Bland-Altman | scipy (linregress) | Already in env |
| All curve equations | scipy (curve_fit) | Already in env |

---

### Critical Files for Implementation
- `/Users/qubitmac/Documents/BioxYC/src/statistics_engine.py` - Core computation layer: add 6 new test functions, 17 new equation dicts, and 4 TIER 2 analysis functions (PCA, K-means, multiple regression, rm-ANOVA)
- `/Users/qubitmac/Documents/BioxYC/src/statistics_charts.py` - Chart builders: add 9 new Plotly figure functions (interaction plot, contingency chart, violin, volcano, correlation heatmap, slopegraph, odds ratio forest, ROC, Bland-Altman, PCA biplot, scree plot)
- `/Users/qubitmac/Documents/BioxYC/components/statistics_tab.py` - Tab UI: expand test category selectbox, add equation category browser, add fixed-parameter input logic, add new analysis modes for TIER 2
- `/Users/qubitmac/Documents/BioxYC/PLAN_statistics.md` - Existing plan to cross-reference: contains the fit_curve(), CB_PALETTE, _BASE_LAYOUT, and 8 existing test implementations that all new code must be consistent with
- `/Users/qubitmac/Documents/BioxYC/components/variant_landscape.py` - Pattern reference: scatter plot construction with grouped traces, colorblind-safe markers, and hover templates that the new chart builders should match
