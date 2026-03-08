Good -- scipy 1.17.1, numpy 2.4.2, and pandas 2.3.3 are already available. pingouin, lifelines, and statsmodels are not installed. Now I have the full picture. Here is the comprehensive implementation plan.

---

# Statistics Tab Implementation Plan for Luminous

## 0. ARCHITECTURAL CONTEXT

The Luminous app (`/Users/qubitmac/Documents/BioxYC/app.py`) uses a tab-router pattern where each tab is a `with tab_xxx:` block that lazy-imports a `render_*` function from `components/`. Session state is initialized via a `DEFAULTS` dict at app startup. The existing 7 tabs are: Query, Structure & Trust, Biological Context, Report & Export, Playground, Sketch Hypothesis, Ask Lumi. The Statistics tab will be the 8th.

Key conventions observed across all existing components:
- Every render function starts with a dependency guard (`if not st.session_state.get("query_parsed"): st.info(...); return`)
- Widget keys use a tab-specific prefix to avoid collisions (e.g. `var_fetch`, `compare_left`)
- Plotly charts always use `template="plotly_white"`, `paper_bgcolor="rgba(0,0,0,0)"`, `plot_bgcolor="rgba(0,0,0,0)"`, `font=dict(color="rgba(60,60,67,0.6)")` -- the Apple Light Mode palette
- The `pin_button` function from `components/playground.py` is the integration point for sending data to the Playground
- The `_build_report_json` function in report_export collects data from `st.session_state` for export
- The CSS classes `glow-card`, `glass-card`, `glass-panel`, `metric-card`, `status-badge` are available
- `@st.cache_data` is used for expensive computations; all data flows through `st.session_state`

---

## 1. DEPENDENCIES

### Add to `pyproject.toml`

```
"pingouin>=0.5.5",
"lifelines>=0.30",
```

**Version constraints and rationale:**

| Package | Version | Why |
|---------|---------|-----|
| `pingouin>=0.5.5` | Latest is 0.5.5 | Wraps scipy statistical tests with effect sizes, CI, and Bayesian factors. Much richer output than raw scipy. Brings statsmodels as a transitive dependency (needed for multiple comparison correction). |
| `lifelines>=0.30` | Latest is 0.30.x | Kaplan-Meier, Cox regression, log-rank test. Pure Python, no C extensions. |

**Already available (no action needed):**
- `scipy==1.17.1` -- core statistical functions (curve_fit, optimize)
- `numpy==2.4.2` -- numerical computation
- `pandas==2.3.3` -- DataFrame operations for `st.data_editor`
- `plotly>=6.0` -- already in pyproject.toml

**Transitive dependency notes:**
- `pingouin` pulls `statsmodels`, `scikit-learn`, `matplotlib`, `outdated`. All are compatible with the existing environment (matplotlib is already used by `fpdf2`/`pdf_report.py`).
- `lifelines` pulls `autograd`, `formulaic`, `scipy`, `matplotlib`. The scipy and matplotlib versions are compatible.
- Neither conflicts with the existing `biotite>=1.6` or `anthropic>=0.84` stacks.
- `pingouin` and `lifelines` both depend on `pandas>=1.5`, which is satisfied by `pandas>=2.2` already specified.

---

## 2. FILE STRUCTURE

### New files to create

| File | Purpose |
|------|---------|
| `components/statistics_tab.py` | Main render function `render_statistics()` -- the tab entry point. Contains the 4-section layout, session state management, and orchestration. |
| `src/statistics_engine.py` | Pure computation layer: all statistical tests, curve fitting, survival analysis. No Streamlit imports. All functions accept and return plain Python types / DataFrames. This separation enables `@st.cache_data` caching and unit testing. |
| `src/statistics_charts.py` | Plotly figure builders for every chart type in the statistics tab. No Streamlit imports. Returns `go.Figure` objects. |

### Existing files to modify

| File | Change |
|------|--------|
| `app.py` | (1) Add `"stats_data"`, `"stats_results"`, `"stats_survival_data"` to `DEFAULTS`. (2) Add `tab_stats` to the `st.tabs()` call. (3) Add `with tab_stats: from components.statistics_tab import render_statistics; render_statistics()` block. |
| `pyproject.toml` | Add `"pingouin>=0.5.5"` and `"lifelines>=0.30"` to `dependencies`. |
| `components/report_export.py` | Add a stats results section to `_build_report_json()` and `_render_pdf_download()`. |
| `components/structure_viewer.py` | Add a "Send to Stats" button (near existing "Pin to Workspace" buttons) that pushes pLDDT data to `st.session_state["stats_data"]`. |
| `components/context_panel.py` | Add a "Send to Stats" button that pushes disease scores to `st.session_state["stats_data"]`. |

### Import paths

```python
# From statistics_tab.py:
from src.statistics_engine import (
    run_ttest, run_mannwhitney, run_paired_ttest, run_wilcoxon,
    run_one_way_anova, run_kruskal, run_chi_square,
    run_pearson_correlation, run_spearman_correlation,
    check_normality, check_equal_variance,
    fit_curve, BUILTIN_EQUATIONS,
    run_kaplan_meier, run_logrank, run_cox_regression,
    apply_multiple_comparison_correction,
)
from src.statistics_charts import (
    build_distribution_chart, build_comparison_chart,
    build_scatter_with_fit, build_residual_plot,
    build_qq_plot, build_survival_chart,
    build_significance_bracket,
)
from components.playground import pin_button
```

---

## 3. SESSION STATE

### New keys to add to `DEFAULTS` in `app.py`

```python
DEFAULTS = {
    # ... existing keys ...
    "stats_data": None,           # pd.DataFrame or None
    "stats_results": None,        # dict or None -- last test/fit results
    "stats_survival_data": None,  # pd.DataFrame or None -- time/event/group
}
```

### Data format for each key

**`stats_data`** -- `pd.DataFrame | None`
- The primary working dataset for the statistics tab
- Columns are user-defined or auto-populated from other tabs
- Maximum 50,000 rows (enforced on upload)
- Column dtypes: float64, int64, object, category
- This is the source for all Section 2 (tests) and Section 3 (curve fitting) operations

**`stats_results`** -- `dict | None`
```python
{
    "test_name": str,           # e.g. "Independent t-test"
    "timestamp": str,           # ISO 8601
    "input_columns": list[str], # which columns were used
    "result_df": dict,          # pd.DataFrame.to_dict("records")
    "interpretation": str,      # human-readable summary
    "assumptions": dict,        # {"normality": {...}, "equal_variance": {...}}
    "chart_json": str | None,   # Plotly figure JSON
    "effect_size": float | None,
    "effect_size_type": str | None,  # "Cohen's d", "eta-squared", etc.
}
```

**`stats_survival_data`** -- `pd.DataFrame | None`
- Required columns: `time` (float), `event` (int 0/1), optionally `group` (str/category)
- Used only by Section 4 (survival analysis)
- Separate from `stats_data` because survival data has a distinct schema

### Data flow to/from other tabs

| Source tab | Direction | Data |
|-----------|-----------|------|
| Structure & Trust | -> stats_data | pLDDT per residue as a column, region confidence scores |
| Biological Context | -> stats_data | Disease association scores, drug phase values |
| Playground | <- stats_results | Pin test results, chart JSON, and summary via `pin_button` |
| Report & Export | <- stats_results | Include latest stats_results dict in JSON/PDF export |
| Query tab | -> (triggers clear) | When `reset_results()` runs, it should also clear `stats_data` and `stats_results` |

The `reset_results()` function in `app.py` (line 42-46) must be extended to also clear the three new keys.

---

## 4. DATA ENTRY (Section 1 of the Statistics Tab)

### 4.1 Layout

The data entry section occupies the full width at the top of the Statistics tab, organized as:

```
[Data Source Selector] -- radio: "Enter/Paste Data" | "Upload CSV/TSV" | "From Analysis"
```

Followed by the appropriate input widget.

### 4.2 `st.data_editor` Configuration

```python
st.data_editor(
    st.session_state["stats_data"],
    num_rows="dynamic",
    use_container_width=True,
    key="stats_data_editor",
    column_config={
        # Dynamically built based on detected dtypes:
        # For float columns:
        col_name: st.column_config.NumberColumn(
            col_name,
            format="%.4f",
            min_value=None,  # no bounds by default
            max_value=None,
        ),
        # For integer columns:
        col_name: st.column_config.NumberColumn(
            col_name,
            format="%d",
        ),
        # For text/category columns:
        col_name: st.column_config.TextColumn(
            col_name,
            max_chars=200,
        ),
    },
)
```

**Critical Streamlit pattern:** The `st.data_editor` returns the edited DataFrame. The return value must be captured and written back to session state:

```python
edited = st.data_editor(st.session_state["stats_data"], ...)
if edited is not None:
    st.session_state["stats_data"] = edited
```

**Widget key:** `"stats_data_editor"` -- the `stats_` prefix prevents collision with all other tabs.

### 4.3 CSV/TSV Upload

```python
uploaded = st.file_uploader(
    "Upload CSV or TSV",
    type=["csv", "tsv", "txt"],
    key="stats_file_uploader",
    help="Tab-separated or comma-separated files. Max 50,000 rows.",
)
```

**Error handling pipeline (sequential, stop on first error):**

1. **Null check:** `if uploaded is None: return`
2. **Size check:** `if uploaded.size > 10 * 1024 * 1024: st.error("File exceeds 10 MB limit."); return`
3. **Empty file:** `if uploaded.size == 0: st.error("File is empty."); return`
4. **Encoding detection:**
   ```python
   import io
   raw = uploaded.read()
   for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
       try:
           text = raw.decode(encoding)
           break
       except UnicodeDecodeError:
           continue
   else:
       st.error("Could not detect file encoding. Save as UTF-8 and re-upload.")
       return
   ```
5. **Delimiter detection:** Check if `\t` appears in the first line. If yes, use `sep="\t"`. Otherwise `sep=","`.
6. **Parse with pandas:**
   ```python
   try:
       df = pd.read_csv(io.StringIO(text), sep=sep, na_values=["", "NA", "N/A", "nan", "NaN", "."])
   except pd.errors.ParserError as e:
       st.error(f"Malformed file: {e}")
       return
   ```
7. **Row limit:** `if len(df) > 50_000: st.warning("Truncated to 50,000 rows."); df = df.head(50_000)`
8. **Column limit:** `if len(df.columns) > 100: st.warning("Truncated to 100 columns."); df = df.iloc[:, :100]`
9. **Duplicate column names:**
   ```python
   dupes = df.columns[df.columns.duplicated()].tolist()
   if dupes:
       st.warning(f"Duplicate columns renamed: {dupes}")
       df.columns = pd.io.common.dedup_names(df.columns, is_potential_multiindex=False)
   ```
10. **Store:** `st.session_state["stats_data"] = df`

### 4.4 Pre-population from Session State ("From Analysis")

When the user selects "From Analysis", show buttons to import data from the current pipeline:

```python
available_sources = []
prediction = st.session_state.get("prediction_result")
trust_audit = st.session_state.get("trust_audit")
bio_context = st.session_state.get("bio_context")

if prediction and prediction.plddt_per_residue:
    available_sources.append(("pLDDT per Residue", _make_plddt_df))
if trust_audit and trust_audit.regions:
    available_sources.append(("Region Confidence", _make_region_df))
if bio_context and bio_context.disease_associations:
    available_sources.append(("Disease Scores", _make_disease_df))
if prediction and prediction.affinity_json and prediction.affinity_json.get("poses"):
    available_sources.append(("Binding Affinity Poses", _make_affinity_df))
```

**Builder functions:**

```python
def _make_plddt_df() -> pd.DataFrame:
    p = st.session_state["prediction_result"]
    return pd.DataFrame({
        "residue_id": p.residue_ids,
        "chain": p.chain_ids,
        "plddt": p.plddt_per_residue,
    })

def _make_region_df() -> pd.DataFrame:
    t = st.session_state["trust_audit"]
    return pd.DataFrame([{
        "chain": r.chain,
        "start": r.start_residue,
        "end": r.end_residue,
        "avg_plddt": r.avg_plddt,
        "flagged": bool(r.flag),
    } for r in t.regions])

def _make_disease_df() -> pd.DataFrame:
    bc = st.session_state["bio_context"]
    return pd.DataFrame([{
        "disease": d.disease,
        "score": d.score,
        "evidence": d.evidence,
    } for d in bc.disease_associations])

def _make_affinity_df() -> pd.DataFrame:
    aff = st.session_state["prediction_result"].affinity_json
    return pd.DataFrame(aff.get("poses", []))
```

### 4.5 Data Type Auto-Detection Algorithm

After data is loaded (from any source), run:

```python
def detect_column_types(df: pd.DataFrame) -> dict[str, str]:
    """Returns {col_name: "numeric" | "categorical" | "text" | "datetime" | "empty"}."""
    result = {}
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            result[col] = "empty"
            continue
        # Try numeric
        numeric = pd.to_numeric(series, errors="coerce")
        if numeric.notna().sum() / len(series) > 0.8:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            result[col] = "numeric"
            continue
        # Try datetime
        try:
            pd.to_datetime(series, infer_datetime_format=True, errors="raise")
            result[col] = "datetime"
            continue
        except (ValueError, TypeError):
            pass
        # Categorical vs text: if fewer than 20 unique values or <5% cardinality
        if series.nunique() / len(series) < 0.05 or series.nunique() <= 20:
            result[col] = "categorical"
        else:
            result[col] = "text"
    return result
```

This is shown to the user as a summary row of badges below the data editor:

```python
for col, dtype in col_types.items():
    badge_color = {"numeric": "#007AFF", "categorical": "#34C759",
                   "text": "#8E8E93", "datetime": "#AF52DE", "empty": "#FF3B30"}[dtype]
    # render as status-badge
```

### 4.6 Edge Cases

| Edge case | Detection | Handling |
|-----------|-----------|----------|
| Empty dataset (0 rows) | `len(df) == 0` | Show `st.info("Dataset is empty. Add rows or upload data.")` -- disable all analysis sections |
| Single row | `len(df) == 1` | Show warning: "Only 1 row. Most tests require at least 3 samples." Allow descriptive stats only. |
| Single column | `len(df.columns) == 1` | Allow univariate stats only. Disable all two-sample tests and correlation. |
| All-NaN column | `df[col].isna().all()` | Mark as "empty" type. Exclude from test column selectors. Show warning badge. |
| Mixed types in column | `pd.to_numeric(df[col], errors="coerce").isna().sum() > 0 and df[col].notna().sum() > 0` | Coerce to numeric with NaN for non-parseable values. Show warning: "N values could not be converted to numbers." |
| >10k rows | `len(df) > 10_000` | Show `st.warning("Large dataset. Some visualizations may be slow.")`. Use `@st.cache_data` for all computations. Down-sample scatter plots to 5000 points with `df.sample(5000)`. |
| Duplicate column names | `df.columns.duplicated().any()` | Auto-rename with suffix `_1`, `_2` etc. Show warning. |
| Non-numeric in numeric column | Detected by auto-detection | Coerce, show count of NaN-coerced values |

---

## 5. STATISTICAL TESTS (Section 2)

### 5.1 Test Selection UI

```python
test_category = st.selectbox(
    "Test category",
    ["Compare Two Groups", "Compare Multiple Groups", "Correlation", "Contingency"],
    key="stats_test_category",
)
```

Then a second selectbox within each category for the specific test.

### 5.2 Full Test Catalog

#### 5.2.1 Compare Two Groups

**Independent Samples t-test**
- Requirements: 2 numeric columns OR 1 numeric + 1 binary grouping column. n >= 3 per group.
- Assumptions checked: (a) Normality via Shapiro-Wilk/D'Agostino. (b) Equal variance via Levene's test.
- When assumptions violated: If normality fails, suggest Mann-Whitney U. If equal variance fails, automatically use Welch's t-test (default behavior in pingouin).
- Function:
  ```python
  def run_ttest(group1: np.ndarray, group2: np.ndarray) -> dict:
      """Returns dict with keys: T, dof, p_val, CI95, cohen_d, BF10, power, alternative, result_df."""
      import pingouin as pg
      result = pg.ttest(group1, group2, paired=False, alternative="two-sided")
      return {
          "test_name": "Independent Samples t-test (Welch's)",
          "T": float(result["T"].iloc[0]),
          "dof": float(result["dof"].iloc[0]),
          "p_val": float(result["p-val"].iloc[0]),
          "CI95": result["CI95%"].iloc[0],
          "cohen_d": float(result["cohen-d"].iloc[0]),
          "BF10": str(result["BF10"].iloc[0]),
          "power": float(result["power"].iloc[0]),
          "result_df": result.to_dict("records"),
      }
  ```
- Display format: DataFrame with all stats, plus interpretation text:
  ```
  "t(dof) = T, p = p_val. Effect size: Cohen's d = cohen_d (small/medium/large).
   Bayes Factor BF10 = X (strong/moderate/anecdotal evidence)."
  ```

**Paired Samples t-test**
- Requirements: 2 numeric columns of equal length. n >= 3.
- Assumptions checked: Normality of differences.
- When normality violated: Suggest Wilcoxon signed-rank.
- Function: `pg.ttest(x, y, paired=True)`

**Mann-Whitney U test**
- Requirements: Same as t-test but no normality assumption.
- Function:
  ```python
  def run_mannwhitney(group1: np.ndarray, group2: np.ndarray) -> dict:
      import pingouin as pg
      result = pg.mwu(group1, group2, alternative="two-sided")
      return {
          "test_name": "Mann-Whitney U test",
          "U": float(result["U-val"].iloc[0]),
          "p_val": float(result["p-val"].iloc[0]),
          "RBC": float(result["RBC"].iloc[0]),
          "CLES": float(result["CLES"].iloc[0]),
          "result_df": result.to_dict("records"),
      }
  ```

**Wilcoxon Signed-Rank test**
- Requirements: 2 paired numeric columns. n >= 6 (Wilcoxon is unreliable below 6).
- Function: `pg.wilcoxon(x, y, alternative="two-sided")`

#### 5.2.2 Compare Multiple Groups

**One-way ANOVA**
- Requirements: 1 numeric (dependent) + 1 categorical (grouping) column. At least 3 groups, n >= 2 per group.
- Assumptions: Normality per group, equal variance (Levene).
- When violated: Suggest Kruskal-Wallis (non-normality) or Welch's ANOVA (unequal variance).
- Function:
  ```python
  def run_one_way_anova(df: pd.DataFrame, dv: str, between: str) -> dict:
      import pingouin as pg
      result = pg.anova(data=df, dv=dv, between=between, detailed=True)
      posthoc = pg.pairwise_tukey(data=df, dv=dv, between=between) if float(result["p-unc"].iloc[0]) < 0.05 else None
      return {
          "test_name": "One-way ANOVA",
          "F": float(result["F"].iloc[0]),
          "p_val": float(result["p-unc"].iloc[0]),
          "eta_squared": float(result["np2"].iloc[0]),
          "df_between": int(result["ddof1"].iloc[0]),
          "df_within": int(result["ddof2"].iloc[0]),
          "result_df": result.to_dict("records"),
          "posthoc_df": posthoc.to_dict("records") if posthoc is not None else None,
      }
  ```
- Post-hoc: Tukey HSD if main effect is significant (p < 0.05).

**Kruskal-Wallis H test**
- Requirements: Same as ANOVA but no normality assumption.
- Function: `pg.kruskal(data=df, dv=dv, between=between)`
- Post-hoc: Dunn's test with Bonferroni correction via `pg.pairwise_tests(data=df, dv=dv, between=between, parametric=False, padjust="bonf")`

#### 5.2.3 Correlation

**Pearson correlation**
- Requirements: 2 numeric columns. n >= 3.
- Function:
  ```python
  def run_pearson_correlation(x: np.ndarray, y: np.ndarray) -> dict:
      import pingouin as pg
      result = pg.corr(x, y, method="pearson")
      return {
          "test_name": "Pearson Correlation",
          "r": float(result["r"].iloc[0]),
          "p_val": float(result["p-val"].iloc[0]),
          "CI95": result["CI95%"].iloc[0],
          "r_squared": float(result["r"].iloc[0]) ** 2,
          "power": float(result["power"].iloc[0]),
          "n": int(result["n"].iloc[0]),
          "result_df": result.to_dict("records"),
      }
  ```

**Spearman rank correlation**
- Requirements: 2 numeric or ordinal columns. n >= 3.
- Function: `pg.corr(x, y, method="spearman")`

#### 5.2.4 Contingency

**Chi-square test of independence**
- Requirements: 2 categorical columns. Expected frequency >= 5 in each cell (warn if not, suggest Fisher's exact for 2x2).
- Function:
  ```python
  def run_chi_square(df: pd.DataFrame, col1: str, col2: str) -> dict:
      from scipy.stats import chi2_contingency
      ct = pd.crosstab(df[col1], df[col2])
      chi2, p, dof, expected = chi2_contingency(ct)
      low_expected = (expected < 5).sum()
      cramers_v = np.sqrt(chi2 / (ct.values.sum() * (min(ct.shape) - 1)))
      return {
          "test_name": "Chi-square Test of Independence",
          "chi2": float(chi2),
          "p_val": float(p),
          "dof": int(dof),
          "cramers_v": float(cramers_v),
          "contingency_table": ct.to_dict(),
          "expected_frequencies": pd.DataFrame(expected, index=ct.index, columns=ct.columns).to_dict(),
          "low_expected_cells": int(low_expected),
          "warning": "Some expected frequencies < 5. Consider Fisher's exact test." if low_expected > 0 else None,
      }
  ```

### 5.3 Assumption Checking

Run automatically before each parametric test. Display results in an expander:

```python
def check_normality(x: np.ndarray, label: str = "sample") -> dict:
    """Check normality. Uses Shapiro-Wilk for n < 5000, D'Agostino-Pearson otherwise."""
    from scipy import stats
    n = len(x)
    if n < 3:
        return {"test": "n/a", "statistic": None, "p_val": None,
                "normal": None, "message": f"Too few observations (n={n}) to test normality."}
    if n < 5000:
        stat, p = stats.shapiro(x)
        test_name = "Shapiro-Wilk"
    else:
        stat, p = stats.normaltest(x)  # D'Agostino-Pearson
        test_name = "D'Agostino-Pearson"
    return {
        "test": test_name,
        "statistic": float(stat),
        "p_val": float(p),
        "normal": p > 0.05,
        "message": f"{label}: {test_name} W={stat:.4f}, p={p:.4f} — {'Normal' if p > 0.05 else 'Not normal'}"
    }

def check_equal_variance(*groups: np.ndarray) -> dict:
    """Levene's test for equal variance."""
    from scipy import stats
    stat, p = stats.levene(*groups)
    return {
        "test": "Levene's",
        "statistic": float(stat),
        "p_val": float(p),
        "equal": p > 0.05,
        "message": f"Levene's F={stat:.4f}, p={p:.4f} — {'Equal variance' if p > 0.05 else 'Unequal variance'}"
    }
```

**Display pattern:**

```python
with st.expander("Assumption Checks", expanded=False):
    for check in assumption_results:
        if check["normal"] is True or check.get("equal") is True:
            st.markdown(f'<span class="status-badge success">{check["message"]}</span>', ...)
        elif check["normal"] is False or check.get("equal") is False:
            st.markdown(f'<span class="status-badge warning">{check["message"]}</span>', ...)
            st.caption(f"Consider using a non-parametric alternative.")
```

### 5.4 Multiple Testing Correction

Applied when post-hoc tests produce multiple p-values:

```python
def apply_multiple_comparison_correction(
    p_values: list[float],
    method: str = "bonferroni",  # also: "holm", "fdr_bh"
) -> list[float]:
    """Apply multiple testing correction. Returns adjusted p-values."""
    import pingouin as pg
    reject, p_adj = pg.multicomp(p_values, method=method)
    return p_adj.tolist()
```

Show a selectbox for the method when post-hoc tests are displayed:

```python
correction = st.selectbox(
    "Multiple testing correction",
    ["bonferroni", "holm", "fdr_bh"],
    key="stats_mc_correction",
    help="Bonferroni: most conservative. Holm: step-down. FDR (Benjamini-Hochberg): least conservative.",
)
```

### 5.5 Edge Cases for Statistical Tests

| Edge case | Detection | Handling |
|-----------|-----------|----------|
| Identical values in both groups (zero variance) | `np.std(group) == 0` | `st.error("Group has zero variance (all identical values). Cannot compute test statistic.")` Return early. |
| Ties in rank tests | Automatic in scipy/pingouin | Show info: "Ties detected. Exact p-value may not be available; asymptotic approximation used." |
| Unbalanced groups in ANOVA | `group_sizes.std() / group_sizes.mean() > 0.5` | Show warning: "Highly unbalanced groups. Consider Welch's ANOVA or non-parametric alternative." |
| Very small n (< 3) | `len(group) < 3` | `st.error("Need at least 3 observations per group.")` Disable test button. |
| Very large p-values (> 0.999) | `p > 0.999` | Display as "p > 0.999" |
| Very small p-values (< 1e-300) | `p < 1e-300` | Display as "p < 1e-300" |
| Medium-small p-values (< 0.001) | `p < 0.001` | Display as "p < 0.001" with full value in tooltip |
| NaN in input | `np.isnan(x).any()` | Auto-drop NaN with warning: "Removed N missing values from [column]." |

---

## 6. CURVE FITTING (Section 3)

### 6.1 Built-in Equation Library

All equations stored as a constant dict in `src/statistics_engine.py`:

```python
BUILTIN_EQUATIONS = {
    "4PL (Dose-Response)": {
        "formula_display": "f(x) = Bottom + (Top - Bottom) / (1 + 10^((LogIC50 - x) * HillSlope))",
        "func": lambda x, bottom, top, log_ic50, hill: bottom + (top - bottom) / (1 + 10**((log_ic50 - x) * hill)),
        "param_names": ["Bottom", "Top", "LogIC50", "HillSlope"],
        "initial_guess": _guess_4pl,
        "bounds": ([-np.inf, -np.inf, -np.inf, -np.inf], [np.inf, np.inf, np.inf, np.inf]),
        "min_points": 5,
        "description": "4-Parameter Logistic for dose-response curves. X should be log10(concentration).",
    },
    "Michaelis-Menten": {
        "formula_display": "v = Vmax * [S] / (Km + [S])",
        "func": lambda x, vmax, km: vmax * x / (km + x),
        "param_names": ["Vmax", "Km"],
        "initial_guess": _guess_mm,
        "bounds": ([0, 0], [np.inf, np.inf]),
        "min_points": 4,
        "description": "Enzyme kinetics. X = substrate concentration, Y = reaction velocity.",
    },
    "Hill Equation": {
        "formula_display": "Y = Bmax * x^n / (Kd^n + x^n)",
        "func": lambda x, bmax, kd, n: bmax * x**n / (kd**n + x**n),
        "param_names": ["Bmax", "Kd", "n"],
        "initial_guess": _guess_hill,
        "bounds": ([0, 0, 0], [np.inf, np.inf, 20]),
        "min_points": 5,
        "description": "Cooperative binding. n > 1 = positive cooperativity, n < 1 = negative.",
    },
    "Exponential Decay": {
        "formula_display": "Y = (Y0 - Plateau) * exp(-K * x) + Plateau",
        "func": lambda x, y0, plateau, k: (y0 - plateau) * np.exp(-k * x) + plateau,
        "param_names": ["Y0", "Plateau", "K"],
        "initial_guess": _guess_exp_decay,
        "bounds": ([-np.inf, -np.inf, 0], [np.inf, np.inf, np.inf]),
        "min_points": 4,
        "description": "One-phase exponential decay (e.g., drug elimination, radioactive decay).",
    },
    "Linear": {
        "formula_display": "Y = m * x + b",
        "func": lambda x, m, b: m * x + b,
        "param_names": ["Slope (m)", "Intercept (b)"],
        "initial_guess": lambda x, y: [1.0, 0.0],
        "bounds": ([-np.inf, -np.inf], [np.inf, np.inf]),
        "min_points": 3,
        "description": "Simple linear regression.",
    },
    "Polynomial (degree 2)": {
        "formula_display": "Y = a*x^2 + b*x + c",
        "func": lambda x, a, b, c: a * x**2 + b * x + c,
        "param_names": ["a", "b", "c"],
        "initial_guess": lambda x, y: [0.0, 1.0, 0.0],
        "bounds": ([-np.inf]*3, [np.inf]*3),
        "min_points": 4,
        "description": "Quadratic polynomial.",
    },
    "Polynomial (degree 3)": {
        "formula_display": "Y = a*x^3 + b*x^2 + c*x + d",
        "func": lambda x, a, b, c, d: a * x**3 + b * x**2 + c * x + d,
        "param_names": ["a", "b", "c", "d"],
        "initial_guess": lambda x, y: [0.0, 0.0, 1.0, 0.0],
        "bounds": ([-np.inf]*4, [np.inf]*4),
        "min_points": 5,
        "description": "Cubic polynomial.",
    },
    "Polynomial (degree 4)": {
        "formula_display": "Y = a*x^4 + b*x^3 + c*x^2 + d*x + e",
        "func": lambda x, a, b, c, d, e: a * x**4 + b * x**3 + c * x**2 + d * x + e,
        "param_names": ["a", "b", "c", "d", "e"],
        "initial_guess": lambda x, y: [0.0, 0.0, 0.0, 1.0, 0.0],
        "bounds": ([-np.inf]*5, [np.inf]*5),
        "min_points": 6,
        "description": "Quartic polynomial.",
    },
}
```

### 6.2 Initial Parameter Guess Algorithms

```python
def _guess_4pl(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Heuristic: Bottom = min(y), Top = max(y), LogIC50 = median(x), Hill = 1."""
    return [float(np.nanmin(y)), float(np.nanmax(y)), float(np.nanmedian(x)), 1.0]

def _guess_mm(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Heuristic: Vmax = max(y)*1.1, Km = x at half-max-y."""
    vmax = float(np.nanmax(y)) * 1.1
    half = vmax / 2
    idx = np.argmin(np.abs(y - half))
    km = float(x[idx]) if len(x) > 0 else 1.0
    return [vmax, max(km, 1e-10)]

def _guess_hill(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Heuristic: Bmax = max(y)*1.1, Kd = x at half-max, n = 1."""
    bmax = float(np.nanmax(y)) * 1.1
    half = bmax / 2
    idx = np.argmin(np.abs(y - half))
    kd = float(x[idx]) if len(x) > 0 else 1.0
    return [bmax, max(kd, 1e-10), 1.0]

def _guess_exp_decay(x: np.ndarray, y: np.ndarray) -> list[float]:
    """Heuristic: Y0 = y at min(x), Plateau = y at max(x), K = rough estimate."""
    sort_idx = np.argsort(x)
    y0 = float(y[sort_idx[0]])
    plateau = float(y[sort_idx[-1]])
    k = 1.0 / (float(x[sort_idx[-1]] - x[sort_idx[0]]) + 1e-10)
    return [y0, plateau, abs(k)]
```

### 6.3 Core Fitting Function

```python
@st.cache_data(show_spinner=False)
def fit_curve(
    x: np.ndarray,
    y: np.ndarray,
    equation_name: str,
    custom_func: callable | None = None,
    custom_param_names: list[str] | None = None,
    max_iterations: int = 10_000,
) -> dict:
    """Fit a curve and return parameters, goodness of fit, and confidence bands.

    Returns dict with keys:
        params: dict[str, float]  -- fitted parameter values
        param_errors: dict[str, float]  -- standard errors from covariance matrix
        param_ci95: dict[str, tuple[float, float]]  -- 95% CI
        r_squared: float
        adj_r_squared: float
        aic: float
        bic: float
        residuals: np.ndarray
        y_fit: np.ndarray  -- model values at x points
        x_smooth: np.ndarray  -- fine grid for plotting
        y_smooth: np.ndarray  -- model values on fine grid
        ci_lower: np.ndarray  -- 95% confidence band lower (on x_smooth)
        ci_upper: np.ndarray  -- 95% confidence band upper (on x_smooth)
        pi_lower: np.ndarray  -- 95% prediction band lower
        pi_upper: np.ndarray  -- 95% prediction band upper
        converged: bool
        message: str
    """
    from scipy.optimize import curve_fit
    from scipy.stats import t as t_dist

    # Resolve equation
    if equation_name in BUILTIN_EQUATIONS:
        eq = BUILTIN_EQUATIONS[equation_name]
        func = eq["func"]
        p0 = eq["initial_guess"](x, y)
        bounds = eq["bounds"]
        param_names = eq["param_names"]
    elif custom_func is not None:
        func = custom_func
        p0 = [1.0] * len(custom_param_names)
        bounds = (-np.inf, np.inf)
        param_names = custom_param_names
    else:
        return {"converged": False, "message": f"Unknown equation: {equation_name}"}

    # Validate data points vs parameters
    n_params = len(param_names)
    if len(x) <= n_params:
        return {"converged": False,
                "message": f"Need at least {n_params + 1} data points for {n_params} parameters. Have {len(x)}."}

    # Remove NaN pairs
    mask = ~(np.isnan(x) | np.isnan(y))
    x_clean, y_clean = x[mask], y[mask]
    n = len(x_clean)

    try:
        popt, pcov = curve_fit(func, x_clean, y_clean, p0=p0, bounds=bounds,
                                maxfev=max_iterations, full_output=False)
    except RuntimeError as e:
        return {"converged": False, "message": f"Fit did not converge: {e}"}
    except ValueError as e:
        return {"converged": False, "message": f"Invalid input: {e}"}

    # Standard errors
    perr = np.sqrt(np.diag(pcov))

    # Confidence intervals (95%)
    alpha = 0.05
    tval = t_dist.ppf(1 - alpha / 2, n - n_params)
    param_ci = {name: (float(p - tval * e), float(p + tval * e))
                for name, p, e in zip(param_names, popt, perr)}

    # R-squared
    y_fit = func(x_clean, *popt)
    ss_res = np.sum((y_clean - y_fit) ** 2)
    ss_tot = np.sum((y_clean - np.mean(y_clean)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    adj_r_squared = 1 - (1 - r_squared) * (n - 1) / (n - n_params - 1) if n > n_params + 1 else r_squared

    # AIC / BIC
    mse = ss_res / n
    aic = n * np.log(mse + 1e-300) + 2 * n_params
    bic = n * np.log(mse + 1e-300) + n_params * np.log(n)

    # Smooth curve for plotting
    x_smooth = np.linspace(np.nanmin(x_clean), np.nanmax(x_clean), 200)
    y_smooth = func(x_smooth, *popt)

    # Confidence and prediction bands (delta method)
    residuals = y_clean - y_fit
    s = np.sqrt(ss_res / (n - n_params))  # residual standard error

    # Simplified confidence band using Jacobian
    from scipy.optimize import approx_fprime
    J = np.array([approx_fprime(popt, lambda p, xi=xi: func(xi, *p), 1e-8) for xi in x_smooth])
    ci_band = tval * s * np.sqrt(np.array([j @ pcov @ j for j in J]))
    pi_band = tval * s * np.sqrt(1 + np.array([j @ pcov @ j for j in J]))

    return {
        "params": dict(zip(param_names, [float(p) for p in popt])),
        "param_errors": dict(zip(param_names, [float(e) for e in perr])),
        "param_ci95": param_ci,
        "r_squared": float(r_squared),
        "adj_r_squared": float(adj_r_squared),
        "aic": float(aic),
        "bic": float(bic),
        "residuals": residuals.tolist(),
        "y_fit": y_fit.tolist(),
        "x_smooth": x_smooth.tolist(),
        "y_smooth": y_smooth.tolist(),
        "ci_lower": (y_smooth - ci_band).tolist(),
        "ci_upper": (y_smooth + ci_band).tolist(),
        "pi_lower": (y_smooth - pi_band).tolist(),
        "pi_upper": (y_smooth + pi_band).tolist(),
        "converged": True,
        "message": "Fit converged successfully.",
    }
```

### 6.4 Custom Equation Input

**Security model:** Use `ast.parse` to validate the expression is a safe mathematical expression. No `exec()` or `eval()` of raw strings.

```python
import ast
import math

_SAFE_NAMES = {
    "x", "exp", "log", "log10", "sqrt", "sin", "cos", "tan",
    "abs", "pi", "e", "inf",
}
_SAFE_FUNCS = {
    "exp": np.exp, "log": np.log, "log10": np.log10, "sqrt": np.sqrt,
    "sin": np.sin, "cos": np.cos, "tan": np.tan, "abs": np.abs,
    "pi": np.pi, "e": np.e,
}

def parse_custom_equation(expr: str) -> tuple[callable, list[str]]:
    """Parse a safe mathematical expression string into a callable and parameter names.

    Example: "a * exp(-b * x) + c" -> (func, ["a", "b", "c"])

    Raises ValueError if expression is unsafe or malformed.
    """
    tree = ast.parse(expr, mode="eval")

    # Walk AST to find all Name nodes (variables)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in _SAFE_FUNCS:
                raise ValueError(f"Unsupported function: {ast.dump(node.func)}")
        elif isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef,
                               ast.ClassDef, ast.AsyncFunctionDef, ast.Attribute)):
            raise ValueError("Unsafe expression: imports, classes, and attribute access are not allowed.")

    # Separate x (independent variable) from parameters
    param_names = sorted(names - _SAFE_NAMES - {"x"})
    if "x" not in names:
        raise ValueError("Expression must contain 'x' as the independent variable.")
    if not param_names:
        raise ValueError("Expression must contain at least one parameter besides 'x'.")

    # Compile to callable
    code = compile(tree, "<custom_equation>", "eval")

    def _func(x_val, *args):
        namespace = {**_SAFE_FUNCS, "x": x_val}
        for name, val in zip(param_names, args):
            namespace[name] = val
        return eval(code, {"__builtins__": {}}, namespace)

    return _func, param_names
```

**UI for custom equations:**

```python
custom_expr = st.text_input(
    "Custom equation (use 'x' for independent variable)",
    placeholder="a * exp(-b * x) + c",
    key="stats_custom_equation",
    help="Parameters are auto-detected. Allowed functions: exp, log, log10, sqrt, sin, cos, tan, abs. Constants: pi, e.",
)
```

### 6.5 Curve Fitting Edge Cases

| Edge case | Detection | Handling |
|-----------|-----------|----------|
| Fit doesn't converge | `RuntimeError` from `curve_fit` | Return `{"converged": False, "message": "..."}`. Show `st.warning("Fit did not converge after 10,000 iterations. Try different initial guesses or a simpler model.")` |
| Negative IC50 (log-scale) | `params["LogIC50"] < np.log10(min_positive_x)` | Show warning: "Fitted LogIC50 is outside the data range. The dose-response curve may be incomplete." |
| Zero/negative on log scale | `(x <= 0).any()` when equation expects log | `st.error("X contains zero or negative values. Use log-transformed data or choose a different model.")` |
| Insufficient points | `len(x) <= n_params` | `st.error(f"Need at least {n_params + 1} points. Have {len(x)}.")` |
| Overfitting | `n_params >= len(x) - 1` | Show warning: "Near-perfect fit with as many parameters as data points. Results may not generalize." Compare AIC/BIC with simpler models. |
| Collinear parameters | Very large values in `pcov` diagonal | `if np.any(perr > 1e10): st.warning("Parameter estimates are highly uncertain. Model may be overparameterized.")` |
| Data with outliers | User-toggled option | Provide a checkbox "Robust fitting (Huber loss)" that uses `scipy.optimize.least_squares(..., loss="huber")` instead of `curve_fit`. |

---

## 7. SURVIVAL ANALYSIS (Section 4)

### 7.1 Data Format Requirements

The survival section requires a separate DataFrame (`stats_survival_data`) with exactly these columns:
- `time` (float, >= 0) -- time to event or censoring
- `event` (int, 0 or 1) -- 1 = event occurred, 0 = censored
- `group` (str, optional) -- stratification variable

Show a data template and allow upload or manual entry with `st.data_editor`.

### 7.2 Kaplan-Meier Estimator

```python
def run_kaplan_meier(
    time: np.ndarray,
    event: np.ndarray,
    group: np.ndarray | None = None,
) -> dict:
    """Run Kaplan-Meier survival estimation.

    Returns dict with keys:
        curves: dict[str, dict] -- {group_name: {"timeline": [...], "survival": [...],
                                                   "ci_lower": [...], "ci_upper": [...],
                                                   "at_risk": [...]}}
        median_survival: dict[str, float | None]
    """
    from lifelines import KaplanMeierFitter

    results = {"curves": {}, "median_survival": {}}

    if group is None:
        group = np.array(["All"] * len(time))

    for grp_name in np.unique(group):
        mask = group == grp_name
        kmf = KaplanMeierFitter()
        kmf.fit(time[mask], event_observed=event[mask], label=str(grp_name))

        ci = kmf.confidence_interval_survival_function_
        results["curves"][str(grp_name)] = {
            "timeline": kmf.timeline.tolist(),
            "survival": kmf.survival_function_.iloc[:, 0].tolist(),
            "ci_lower": ci.iloc[:, 0].tolist(),
            "ci_upper": ci.iloc[:, 1].tolist(),
            "at_risk": kmf.event_table["at_risk"].tolist(),
        }
        results["median_survival"][str(grp_name)] = (
            float(kmf.median_survival_time_) if not np.isinf(kmf.median_survival_time_) else None
        )

    return results
```

### 7.3 Log-Rank Test

```python
def run_logrank(
    time: np.ndarray,
    event: np.ndarray,
    group: np.ndarray,
    weighted: bool = False,
) -> dict:
    """Log-rank test comparing survival between groups.

    Args:
        weighted: If True, use Wilcoxon (Gehan-Breslow) weighting which gives
                  more weight to early events.
    """
    from lifelines.statistics import logrank_test, multivariate_logrank_test

    groups = np.unique(group)
    if len(groups) == 2:
        mask1 = group == groups[0]
        mask2 = group == groups[1]
        result = logrank_test(
            time[mask1], time[mask2],
            event_observed_A=event[mask1], event_observed_B=event[mask2],
            weightings="wilcoxon" if weighted else None,
        )
        return {
            "test_name": "Wilcoxon (Gehan-Breslow)" if weighted else "Log-rank",
            "test_statistic": float(result.test_statistic),
            "p_val": float(result.p_value),
            "groups": groups.tolist(),
        }
    else:
        result = multivariate_logrank_test(time, group, event)
        return {
            "test_name": "Multivariate log-rank",
            "test_statistic": float(result.test_statistic),
            "p_val": float(result.p_value),
            "groups": groups.tolist(),
        }
```

### 7.4 Cox Proportional Hazards Regression

```python
def run_cox_regression(
    df: pd.DataFrame,
    duration_col: str = "time",
    event_col: str = "event",
    covariates: list[str] | None = None,
) -> dict:
    """Fit Cox PH model. Returns hazard ratios, CIs, p-values, and PH test results."""
    from lifelines import CoxPHFitter

    cph = CoxPHFitter()
    fit_cols = [duration_col, event_col] + (covariates or [])
    cph.fit(df[fit_cols], duration_col=duration_col, event_col=event_col)

    summary = cph.summary
    ph_test = cph.check_assumptions(df[fit_cols], p_value_threshold=0.05, show_plots=False)

    return {
        "test_name": "Cox Proportional Hazards",
        "summary_df": summary.to_dict("records"),
        "concordance": float(cph.concordance_index_),
        "log_likelihood": float(cph.log_likelihood_),
        "aic": float(cph.AIC_partial_),
        "hazard_ratios": {row: float(summary.loc[row, "exp(coef)"]) for row in summary.index},
        "ph_assumption": ph_test,  # lifelines returns list of violations or empty
    }
```

### 7.5 Survival Edge Cases

| Edge case | Detection | Handling |
|-----------|-----------|----------|
| All censored (no events) | `event.sum() == 0` | `st.error("No events observed. Cannot estimate survival.")` |
| No events in one group | `event[group == g].sum() == 0` for some g | `st.warning(f"Group '{g}' has no events. KM estimate is undefined for this group.")` Still plot flat line at 1.0. |
| Very few events (< 5 total) | `event.sum() < 5` | `st.warning("Very few events. Confidence intervals will be very wide.")` |
| Tied event times | Automatic in lifelines (Efron or Breslow method) | Show info note: "Tied event times handled via Efron approximation." |
| Negative time values | `(time < 0).any()` | `st.error("Time column contains negative values. Survival analysis requires non-negative times.")` |
| Missing event indicator | `event` contains NaN | Drop rows with NaN, show warning with count removed. |
| PH assumption violated (Cox) | `ph_test` returns violations | Display each violated covariate in a warning box with suggestion: "Consider stratified Cox model or time-varying covariates." |

---

## 8. VISUALIZATION

### 8.1 Global Plotly Configuration (Apple Light Mode Palette)

Every chart in the statistics tab must use this base layout (matching the rest of the app):

```python
_BASE_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", color="rgba(60,60,67,0.6)", size=12),
    margin=dict(t=30, b=50, l=60, r=20),
    xaxis=dict(gridcolor="rgba(0,0,0,0.08)", zeroline=False),
    yaxis=dict(gridcolor="rgba(0,0,0,0.08)", zeroline=False),
)
```

### 8.2 Color-blind Safe Palette

Use the IBM Design Language color-blind safe palette (passes deuteranopia, protanopia, tritanopia simulation):

```python
CB_PALETTE = [
    "#648FFF",  # blue
    "#DC267F",  # magenta
    "#FE6100",  # orange
    "#785EF0",  # purple
    "#FFB000",  # gold
    "#000000",  # black
    "#22A884",  # teal
]
```

This replaces the standard `["#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE", "#5AC8FA"]` for **statistics charts only** (other tabs keep their existing palettes to avoid visual regression).

### 8.3 Chart Specifications Per Analysis Type

#### 8.3.1 Distribution Chart (for data overview)

```python
def build_distribution_chart(
    data: pd.Series,
    label: str,
    show_rug: bool = True,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=data.dropna(),
        nbinsx=min(50, max(10, len(data) // 5)),
        marker_color="rgba(100, 143, 255, 0.6)",
        marker_line=dict(color="#648FFF", width=1),
        name="Distribution",
        hovertemplate="Bin: %{x}<br>Count: %{y}<extra></extra>",
    ))
    if show_rug and len(data) <= 500:
        fig.add_trace(go.Scatter(
            x=data.dropna(), y=[-0.02 * data.max()] * len(data.dropna()),
            mode="markers", marker=dict(symbol="line-ns-open", size=8, color="#648FFF"),
            name="Observations", hoverinfo="x",
        ))
    fig.update_layout(**_BASE_LAYOUT, xaxis_title=label, yaxis_title="Count", height=350)
    return fig
```

#### 8.3.2 Group Comparison Chart (box + strip)

```python
def build_comparison_chart(
    groups: dict[str, np.ndarray],  # {group_name: values}
    dv_label: str,
    p_value: float | None = None,
    test_name: str | None = None,
) -> go.Figure:
    fig = go.Figure()
    for i, (name, values) in enumerate(groups.items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Box(
            y=values, name=name, marker_color=color,
            boxmean="sd", jitter=0.3, pointpos=-1.5,
            hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(**_BASE_LAYOUT, yaxis_title=dv_label, height=400, showlegend=False)

    # Significance bracket
    if p_value is not None and len(groups) == 2:
        fig = _add_significance_bracket(fig, list(groups.keys()), p_value)
    return fig
```

#### 8.3.3 Significance Brackets (Programmatic)

```python
def _add_significance_bracket(
    fig: go.Figure,
    group_names: list[str],
    p_value: float,
    y_offset_frac: float = 0.05,
) -> go.Figure:
    """Add a significance bracket with p-value text between two groups on a box plot."""
    # Get max y from all traces
    all_y = []
    for trace in fig.data:
        if hasattr(trace, "y") and trace.y is not None:
            all_y.extend([v for v in trace.y if v is not None and not np.isnan(v)])
    if not all_y:
        return fig
    y_max = max(all_y)
    y_range = y_max - min(all_y)
    bracket_y = y_max + y_range * y_offset_frac
    text_y = bracket_y + y_range * 0.02

    # P-value annotation text
    if p_value < 0.001:
        p_text = "***"
    elif p_value < 0.01:
        p_text = "**"
    elif p_value < 0.05:
        p_text = "*"
    else:
        p_text = "ns"
    p_display = f"p = {p_value:.4f}" if p_value >= 0.001 else f"p < 0.001"

    # Bracket lines (horizontal line connecting two group positions)
    x0, x1 = 0, 1  # Plotly box plot positions for 2 groups
    fig.add_shape(type="line", x0=x0, x1=x0, y0=bracket_y - y_range * 0.01, y1=bracket_y,
                  line=dict(color="rgba(60,60,67,0.6)", width=1.5))
    fig.add_shape(type="line", x0=x0, x1=x1, y0=bracket_y, y1=bracket_y,
                  line=dict(color="rgba(60,60,67,0.6)", width=1.5))
    fig.add_shape(type="line", x0=x1, x1=x1, y0=bracket_y - y_range * 0.01, y1=bracket_y,
                  line=dict(color="rgba(60,60,67,0.6)", width=1.5))

    # Text annotation
    fig.add_annotation(
        x=(x0 + x1) / 2, y=text_y, text=f"{p_text}<br><sub>{p_display}</sub>",
        showarrow=False, font=dict(size=13, color="rgba(60,60,67,0.8)"),
    )

    # Extend y-axis to accommodate bracket
    fig.update_yaxes(range=[min(all_y) - y_range * 0.05, text_y + y_range * 0.08])
    return fig
```

#### 8.3.4 Scatter with Curve Fit

```python
def build_scatter_with_fit(
    x: np.ndarray,
    y: np.ndarray,
    fit_result: dict,
    x_label: str = "X",
    y_label: str = "Y",
    equation_name: str = "",
) -> go.Figure:
    fig = go.Figure()

    # Raw data points
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color="#648FFF", size=8, line=dict(color="white", width=1)),
        name="Data",
        hovertemplate=f"{x_label}: %{{x:.3f}}<br>{y_label}: %{{y:.3f}}<extra></extra>",
    ))

    if fit_result.get("converged"):
        x_s = np.array(fit_result["x_smooth"])
        y_s = np.array(fit_result["y_smooth"])
        ci_lo = np.array(fit_result["ci_lower"])
        ci_hi = np.array(fit_result["ci_upper"])
        pi_lo = np.array(fit_result["pi_lower"])
        pi_hi = np.array(fit_result["pi_upper"])

        # Prediction band (lighter)
        fig.add_trace(go.Scatter(
            x=np.concatenate([x_s, x_s[::-1]]),
            y=np.concatenate([pi_hi, pi_lo[::-1]]),
            fill="toself", fillcolor="rgba(100,143,255,0.08)",
            line=dict(color="rgba(0,0,0,0)"), name="95% Prediction",
            hoverinfo="skip", showlegend=True,
        ))

        # Confidence band (darker)
        fig.add_trace(go.Scatter(
            x=np.concatenate([x_s, x_s[::-1]]),
            y=np.concatenate([ci_hi, ci_lo[::-1]]),
            fill="toself", fillcolor="rgba(100,143,255,0.2)",
            line=dict(color="rgba(0,0,0,0)"), name="95% CI",
            hoverinfo="skip", showlegend=True,
        ))

        # Fit line
        fig.add_trace(go.Scatter(
            x=x_s, y=y_s, mode="lines",
            line=dict(color="#DC267F", width=2.5),
            name=equation_name or "Fit",
        ))

    r2 = fit_result.get("r_squared", 0)
    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=450,
        legend=dict(orientation="h", y=-0.2),
        annotations=[dict(
            text=f"R\u00b2 = {r2:.4f}", xref="paper", yref="paper",
            x=0.98, y=0.98, showarrow=False,
            font=dict(size=13, color="rgba(60,60,67,0.6)"),
        )] if fit_result.get("converged") else [],
    )
    return fig
```

#### 8.3.5 Residual Plot

```python
def build_residual_plot(x: np.ndarray, residuals: np.ndarray) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=residuals, mode="markers",
        marker=dict(color="#648FFF", size=6),
        hovertemplate="X: %{x:.3f}<br>Residual: %{y:.3f}<extra></extra>",
    ))
    fig.add_hline(y=0, line=dict(color="rgba(60,60,67,0.3)", width=1, dash="dash"))
    fig.update_layout(**_BASE_LAYOUT, xaxis_title="X", yaxis_title="Residual", height=250)
    return fig
```

#### 8.3.6 Q-Q Plot

```python
def build_qq_plot(residuals: np.ndarray) -> go.Figure:
    from scipy import stats
    theoretical = stats.probplot(residuals, dist="norm")[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=theoretical[0], y=theoretical[1], mode="markers",
        marker=dict(color="#648FFF", size=6), name="Residuals",
    ))
    # Reference line
    mn, mx = min(theoretical[0]), max(theoretical[0])
    fig.add_trace(go.Scatter(
        x=[mn, mx], y=[mn, mx], mode="lines",
        line=dict(color="#DC267F", width=1.5, dash="dash"), name="Normal",
    ))
    fig.update_layout(**_BASE_LAYOUT, xaxis_title="Theoretical Quantiles",
                      yaxis_title="Sample Quantiles", height=300, showlegend=False)
    return fig
```

#### 8.3.7 Survival Chart (Kaplan-Meier)

```python
def build_survival_chart(
    km_result: dict,
    show_ci: bool = True,
    show_at_risk: bool = True,
) -> go.Figure:
    fig = go.Figure()

    for i, (grp_name, curve) in enumerate(km_result["curves"].items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        timeline = curve["timeline"]
        survival = curve["survival"]

        # Step function
        fig.add_trace(go.Scatter(
            x=timeline, y=survival, mode="lines",
            line=dict(color=color, width=2.5, shape="hv"),
            name=grp_name,
            hovertemplate="Time: %{x:.1f}<br>Survival: %{y:.3f}<extra>%{fullData.name}</extra>",
        ))

        if show_ci:
            ci_lo = curve["ci_lower"]
            ci_hi = curve["ci_upper"]
            fig.add_trace(go.Scatter(
                x=timeline + timeline[::-1],
                y=ci_hi + ci_lo[::-1],
                fill="toself",
                fillcolor=color.replace(")", ",0.15)").replace("rgb", "rgba") if "rgb" in color
                          else f"rgba({int(color[1:3],16)},{int(color[3:5],16)},{int(color[5:7],16)},0.15)",
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False, hoverinfo="skip",
            ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Time",
        yaxis_title="Survival Probability",
        yaxis_range=[-0.05, 1.05],
        height=450,
        legend=dict(orientation="h", y=-0.15),
    )

    # Median survival annotation
    for grp_name, median in km_result["median_survival"].items():
        if median is not None:
            fig.add_hline(y=0.5, line=dict(color="rgba(60,60,67,0.2)", width=1, dash="dot"))
            fig.add_vline(x=median, line=dict(color="rgba(60,60,67,0.2)", width=1, dash="dot"))

    return fig
```

### 8.4 Export as PNG/SVG

Every chart section includes export buttons:

```python
col_png, col_svg = st.columns(2)
with col_png:
    img_bytes = fig.to_image(format="png", width=1200, height=600, scale=2)
    st.download_button("Download PNG", img_bytes, f"stats_{chart_name}.png",
                       mime="image/png", key=f"stats_dl_png_{chart_name}")
with col_svg:
    svg_str = fig.to_image(format="svg", width=1200, height=600)
    st.download_button("Download SVG", svg_str, f"stats_{chart_name}.svg",
                       mime="image/svg+xml", key=f"stats_dl_svg_{chart_name}")
```

Note: `fig.to_image` requires `kaleido`. Check if installed; if not, show the chart without download buttons and log a warning. Kaleido is already a transitive dependency of plotly in many environments -- but add a try/except:

```python
try:
    fig.to_image(format="png", width=100, height=100)
    _KALEIDO_AVAILABLE = True
except (ValueError, ImportError):
    _KALEIDO_AVAILABLE = False
```

---

## 9. INTEGRATION WITH EXISTING TABS

### 9.1 Structure Tab: "Compare Regions" Button

In `components/structure_viewer.py`, after the trust panel section (around line 79), add:

```python
if prediction.plddt_per_residue and len(trust_audit.regions) >= 2:
    if st.button("Send to Stats", key="struct_send_stats",
                 help="Send pLDDT data to the Statistics tab for analysis"):
        import pandas as pd
        df = pd.DataFrame({
            "residue_id": prediction.residue_ids,
            "chain": prediction.chain_ids,
            "plddt": prediction.plddt_per_residue,
        })
        # Add region labels
        region_labels = []
        for rid, cid in zip(prediction.residue_ids, prediction.chain_ids):
            label = "unassigned"
            for r in trust_audit.regions:
                if r.chain == cid and r.start_residue <= rid <= r.end_residue:
                    label = f"Region {r.start_residue}-{r.end_residue}"
                    break
            region_labels.append(label)
        df["region"] = region_labels
        st.session_state["stats_data"] = df
        st.toast("Data sent to Statistics tab!")
```

### 9.2 Context Tab: Effect Sizes on Disease Scores

In `components/context_panel.py`, when disease associations are displayed, add:

```python
if bio_context.disease_associations:
    if st.button("Send Disease Scores to Stats", key="ctx_send_stats"):
        import pandas as pd
        df = pd.DataFrame([{
            "disease": d.disease,
            "score": d.score,
            "evidence": d.evidence or "",
        } for d in bio_context.disease_associations])
        st.session_state["stats_data"] = df
        st.toast("Disease scores sent to Statistics tab!")
```

### 9.3 Playground: Pin Button Integration

In `components/statistics_tab.py`, after every test result display:

```python
from components.playground import pin_button

if results:
    chart_json = fig.to_json() if fig else None
    pin_button(
        title=f"Stats: {results['test_name']}",
        summary=f"p = {results['p_val']:.4f}, {results.get('effect_size_type', '')}: {results.get('effect_size', 'N/A')}",
        insight_type="metric",
        data={
            "test_name": results["test_name"],
            "p_value": results["p_val"],
            "effect_size": results.get("effect_size"),
            "columns_used": results.get("input_columns", []),
        },
        chart_json=chart_json,
        key=f"pin_stats_{results['test_name'].replace(' ', '_')}",
    )
```

The `data` dict uses the same format as other pinned insights (flat dict with primitive values and small lists), ensuring it renders correctly in the Playground grid/compare/overlay views.

### 9.4 Report Export Integration

In `components/report_export.py`:

1. In `_build_report_json()` (line ~397), add:
   ```python
   stats_results = st.session_state.get("stats_results")
   if stats_results:
       report["statistics"] = {
           "test_name": stats_results.get("test_name"),
           "p_value": stats_results.get("p_val"),
           "effect_size": stats_results.get("effect_size"),
           "interpretation": stats_results.get("interpretation"),
       }
   ```

2. In `_render_pdf_download()`, pass `stats_results` to `generate_pdf_report()` so the PDF can include a "Statistical Analysis" section.

### 9.5 Session State Contracts Between Tabs

| Key | Written by | Read by | Format |
|-----|-----------|---------|--------|
| `stats_data` | Statistics (data editor, upload), Structure ("Send to Stats"), Context ("Send to Stats") | Statistics (all sections) | `pd.DataFrame` |
| `stats_results` | Statistics (test/fit/survival execution) | Report Export, Playground (via pin) | `dict` (see Section 3 schema) |
| `stats_survival_data` | Statistics (survival data editor, upload) | Statistics (survival section only) | `pd.DataFrame` with `time`, `event`, `group` columns |

---

## 10. ERROR HANDLING STRATEGY

### 10.1 User-Facing Error Messages

All errors displayed via `st.error()` with clear language. Never expose tracebacks. Pattern:

```python
try:
    result = run_ttest(group1, group2)
except Exception as e:
    st.error(
        f"Could not complete the {test_name}. "
        f"Please check that your data meets the requirements.\n\n"
        f"Details: {type(e).__name__}: {e}"
    )
    return
```

### 10.2 Graceful Degradation if Library Missing

```python
# At top of statistics_tab.py
_PINGOUIN_AVAILABLE = True
_LIFELINES_AVAILABLE = True

try:
    import pingouin
except ImportError:
    _PINGOUIN_AVAILABLE = False

try:
    import lifelines
except ImportError:
    _LIFELINES_AVAILABLE = False
```

In the UI:

```python
if not _PINGOUIN_AVAILABLE:
    st.warning(
        "Statistical testing requires the `pingouin` library. "
        "Install with: `uv add pingouin`"
    )
    # Fall back to scipy-only tests (basic t-test, Mann-Whitney)
```

For survival analysis, if `lifelines` is missing, the entire Section 4 is replaced with an install instruction.

### 10.3 Loading States

```python
with st.spinner(f"Running {test_name}..."):
    result = run_ttest(group1, group2)
```

For curve fitting which can be slow:

```python
progress = st.progress(0, text="Fitting curve...")
# curve_fit is atomic (no progress callback), so just show spinner
with st.spinner("Fitting curve (this may take a moment for complex models)..."):
    result = fit_curve(x, y, equation_name)
```

### 10.4 Warning Messages for Assumption Violations

Assumption violations are **never errors** -- they are displayed as `st.warning()` with suggested alternatives. The test still runs. Pattern:

```python
normality = check_normality(group1, "Group 1")
if not normality["normal"]:
    st.warning(
        f"{normality['message']}\n\n"
        f"The data may not be normally distributed. Consider using the "
        f"**Mann-Whitney U test** (non-parametric alternative) for more reliable results."
    )
```

---

## 11. WIDGET KEY STRATEGY

### 11.1 Naming Convention

All widget keys in the Statistics tab use the prefix `stats_`:

```
stats_data_source          -- radio for data source
stats_file_uploader        -- CSV/TSV upload
stats_data_editor          -- main data editor
stats_test_category        -- test category selector
stats_test_selector        -- specific test selector
stats_col_x                -- X column selector
stats_col_y                -- Y column selector
stats_col_group            -- grouping column selector
stats_eq_selector          -- equation selector
stats_custom_equation      -- custom equation text input
stats_mc_correction        -- multiple comparison method
stats_run_test             -- run test button
stats_run_fit              -- run fit button
stats_surv_editor          -- survival data editor
stats_surv_group_col       -- survival group column selector
stats_surv_weighted        -- weighted logrank checkbox
stats_dl_png_{name}        -- PNG download buttons
stats_dl_svg_{name}        -- SVG download buttons
pin_stats_{name}           -- pin buttons for stats insights
```

### 11.2 No value= + key= Antipattern

Observed pattern from `query_input.py` (line 57-65): the `st.text_area` uses only `key=`, never `value=`. The same pattern applies here:

```python
# CORRECT:
if "stats_data_source" not in st.session_state:
    st.session_state["stats_data_source"] = "Enter/Paste Data"
st.radio("Data source", ["Enter/Paste Data", "Upload CSV/TSV", "From Analysis"],
         key="stats_data_source")

# WRONG (causes DuplicateWidgetID or resets):
st.radio("Data source", [...], value="Enter/Paste Data", key="stats_data_source")
```

### 11.3 Session State Initialization Pattern

At the top of `render_statistics()`:

```python
def render_statistics():
    _STATS_DEFAULTS = {
        "stats_data_source": "Enter/Paste Data",
        "stats_test_category": "Compare Two Groups",
    }
    for key, val in _STATS_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val
```

---

## 12. PERFORMANCE CONSIDERATIONS

### 12.1 `@st.cache_data` for Expensive Computations

Apply to all functions in `src/statistics_engine.py`:

```python
@st.cache_data(show_spinner=False)
def run_ttest(_group1_bytes: bytes, _group2_bytes: bytes) -> dict:
    group1 = np.frombuffer(_group1_bytes)
    group2 = np.frombuffer(_group2_bytes)
    # ... run test ...
```

However, `@st.cache_data` requires hashable arguments. Since numpy arrays are not hashable, convert them to bytes for the cache key:

```python
# In the UI layer (statistics_tab.py):
result = _cached_ttest(group1.tobytes(), group2.tobytes())

@st.cache_data(show_spinner=False)
def _cached_ttest(g1_bytes: bytes, g2_bytes: bytes) -> dict:
    from src.statistics_engine import run_ttest
    g1 = np.frombuffer(g1_bytes, dtype=np.float64)
    g2 = np.frombuffer(g2_bytes, dtype=np.float64)
    return run_ttest(g1, g2)
```

Alternatively, since the engine functions accept numpy arrays and return plain dicts, wrap them in the tab component with `@st.cache_data` using `hash_funcs`:

```python
@st.cache_data(hash_funcs={np.ndarray: lambda arr: hashlib.md5(arr.tobytes()).hexdigest()})
def _cached_run_ttest(g1: np.ndarray, g2: np.ndarray) -> dict:
    return run_ttest(g1, g2)
```

### 12.2 Maximum Dataset Size Limits

| Limit | Value | Rationale |
|-------|-------|-----------|
| Max rows | 50,000 | st.data_editor becomes unusable above ~50k |
| Max columns | 100 | column_config generation time |
| Scatter plot max points | 5,000 | Plotly rendering performance |
| Histogram max bins | 500 | |
| Curve fit max iterations | 10,000 | |

### 12.3 Progress Bars for Long-Running Fits

Curve fitting with scipy's `curve_fit` is atomic and does not support progress callbacks. Use a spinner instead:

```python
with st.spinner("Fitting curve..."):
    result = fit_curve(x, y, equation_name)
```

For ANOVA with large datasets or survival analysis:

```python
with st.spinner("Computing Kaplan-Meier estimates..."):
    km = run_kaplan_meier(time, event, group)
```

### 12.4 Debouncing st.data_editor Changes

`st.data_editor` triggers a full Streamlit rerun on every edit. To prevent re-running expensive downstream computations on every keystroke, gate analyses behind a button:

```python
# Do NOT auto-run stats when data changes. Require explicit "Run" button.
if st.button("Run Test", key="stats_run_test", type="primary"):
    with st.spinner(f"Running {test_name}..."):
        result = run_selected_test(...)
        st.session_state["stats_results"] = result
```

---

## 13. ACCESSIBILITY

### 13.1 Color-Blind Safe Palettes

As specified in Section 8.2, the `CB_PALETTE` passes all three major color vision deficiency simulations. Additionally:

- All chart traces include distinct `dash` patterns as a secondary encoding: solid, dash, dot, dashdot
- Box plots use pattern fills in addition to color when more than 3 groups

### 13.2 WCAG AA Text Contrast

All text in the statistics tab must meet WCAG 2.1 AA (4.5:1 contrast ratio for normal text, 3:1 for large text).

Current design tokens:
- Primary text: `#000000` on `#FFFFFF` -- 21:1 ratio (AAA pass)
- Secondary text: `rgba(60,60,67,0.6)` = approx `#9D9DA3` on white -- 3.1:1 (passes for large text). For result descriptions that are normal-size text, use `rgba(60,60,67,0.75)` = approx `#6D6D73` which gives 5.1:1 (AA pass).
- Error text: `#FF3B30` on white -- 3.7:1 (fails AA for normal text). Use `#D32F2F` instead -- 4.6:1 (AA pass).
- Success text: `#34C759` on white -- 2.3:1 (fails). Use `#1B7A32` instead -- 5.5:1 (AA pass).

Apply these overrides only within the statistics tab component via inline styles:

```python
_STATS_COLORS = {
    "text": "rgba(60,60,67,0.75)",
    "error": "#D32F2F",
    "success": "#1B7A32",
    "warning": "#A65F00",  # darker orange, 4.5:1
    "info": "#0056B3",     # darker blue, 4.6:1
}
```

### 13.3 Screen Reader-Friendly Alt Text

Every Plotly chart must include a descriptive `config` dict:

```python
st.plotly_chart(fig, use_container_width=True,
                config={"staticPlot": False,
                        "displayModeBar": True,
                        "modeBarButtonsToAdd": ["toImage"],
                        "toImageButtonOptions": {"format": "svg", "filename": chart_name}})
```

Additionally, below every chart, include a text summary:

```python
st.caption(
    f"Chart: {chart_description}. "
    f"Shows {n_data_points} data points across {n_groups} groups. "
    f"Key finding: p = {p_value:.4f}."
)
```

This ensures that screen readers can convey the chart's meaning even when the visual is inaccessible.

---

## 14. COMPONENT LAYOUT (render_statistics function skeleton)

```python
def render_statistics():
    """Tab N: Statistical analysis — tests, curve fitting, and survival analysis."""
    _init_stats_state()

    st.markdown(
        '<div style="margin-bottom:16px">'
        '<span style="font-size:1.4rem;font-weight:700">Statistics</span>'
        '<span style="font-size:0.9rem;color:rgba(60,60,67,0.5);margin-left:10px">'
        "Hypothesis testing, curve fitting, and survival analysis"
        "</span></div>",
        unsafe_allow_html=True,
    )

    # ── Section 1: Data Entry ──
    _render_data_entry_section()

    df = st.session_state.get("stats_data")
    if df is None or len(df) == 0:
        st.info("Load or enter data above to begin statistical analysis.")
        return

    # Show data summary
    _render_data_summary(df)

    st.divider()

    # ── Analysis Mode ──
    mode = st.radio(
        "Analysis type",
        ["Statistical Tests", "Curve Fitting", "Survival Analysis"],
        horizontal=True,
        key="stats_analysis_mode",
    )

    if mode == "Statistical Tests":
        _render_tests_section(df)
    elif mode == "Curve Fitting":
        _render_fitting_section(df)
    elif mode == "Survival Analysis":
        _render_survival_section()
```

---

## 15. IMPLEMENTATION SEQUENCE

1. **Phase 1: Foundation** -- Add dependencies to `pyproject.toml`, create `src/statistics_engine.py` with all pure-computation functions, create `src/statistics_charts.py` with all Plotly figure builders.
2. **Phase 2: Tab Shell** -- Create `components/statistics_tab.py` with the data entry section and data summary. Register in `app.py`.
3. **Phase 3: Statistical Tests** -- Implement Section 2 UI with assumption checks and result display.
4. **Phase 4: Curve Fitting** -- Implement Section 3 with built-in equations, custom equations, and confidence bands.
5. **Phase 5: Survival Analysis** -- Implement Section 4 with KM, log-rank, and Cox.
6. **Phase 6: Integration** -- Add "Send to Stats" buttons in Structure and Context tabs. Wire up Playground pins and Report export. Extend `reset_results()`.
7. **Phase 7: Polish** -- Accessibility fixes, edge case testing, performance optimization.

---

### Critical Files for Implementation
- `/Users/qubitmac/Documents/BioxYC/app.py` - Tab router: must add the new tab, session state defaults, and extend reset_results()
- `/Users/qubitmac/Documents/BioxYC/components/statistics_tab.py` - **New file**: main Statistics tab component with all UI sections (data entry, tests, fitting, survival)
- `/Users/qubitmac/Documents/BioxYC/src/statistics_engine.py` - **New file**: pure computation layer with all statistical tests, curve fitting, survival analysis functions (no Streamlit imports)
- `/Users/qubitmac/Documents/BioxYC/src/statistics_charts.py` - **New file**: all Plotly figure builders (comparison charts, scatter+fit, Q-Q, KM curves, significance brackets)
- `/Users/qubitmac/Documents/BioxYC/components/playground.py` - Pin system integration: `pin_button` and `pin_insight` are the API the stats tab calls to send results to the Playground workspace
