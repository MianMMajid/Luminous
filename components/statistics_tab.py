"""Statistics tab -- statistical tests, curve fitting, and survival analysis.

Standalone tab that works independently of the protein pipeline.
Users can upload CSV data, paste values, or import from other tabs.
All widget keys use the ``stats_`` prefix to avoid collisions.
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st

from components.playground import pin_button

# ---------------------------------------------------------------------------
# Lazy imports -- these may not be installed
# ---------------------------------------------------------------------------

_HAS_PINGOUIN = True
_HAS_LIFELINES = True

try:
    import pingouin  # noqa: F401
except ImportError:
    _HAS_PINGOUIN = False

try:
    import lifelines  # noqa: F401
except ImportError:
    _HAS_LIFELINES = False


# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------

_STATS_DEFAULTS: dict[str, Any] = {
    "stats_data": None,
    "stats_data_source": "Enter / Paste",
    "stats_test_category": "Compare Two Groups",
    "stats_analysis_mode": "Statistical Tests",
    "stats_results": None,
    "stats_survival_data": None,
    "stats_col_types": None,
}


def _init_stats_state():
    """Ensure all stats-specific keys exist in session state."""
    for key, val in _STATS_DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = val


# ===================================================================
# PUBLIC ENTRY POINT
# ===================================================================


def render_statistics():
    """Tab: Statistical analysis -- tests, curve fitting, and survival analysis."""
    _init_stats_state()

    # Header
    st.markdown(
        '<div style="margin-bottom:16px">'
        '<span style="font-size:1.4rem;font-weight:700">Statistics</span>'
        '<span style="font-size:0.9rem;color:rgba(60,60,67,0.5);margin-left:10px">'
        "Hypothesis testing, curve fitting, and survival analysis"
        "</span></div>",
        unsafe_allow_html=True,
    )

    # Guard: required packages
    if not _HAS_PINGOUIN:
        st.warning(
            "**pingouin** is not installed. Statistical tests require it.  \n"
            "Run `uv pip install pingouin` and restart the app."
        )
    if not _HAS_LIFELINES:
        st.info(
            "**lifelines** is not installed. Survival analysis will be unavailable.  \n"
            "Run `uv pip install lifelines` to enable it."
        )

    # Section 1 -- Data entry
    _render_data_entry_section()

    df: pd.DataFrame | None = st.session_state.get("stats_data")
    if df is None or len(df) == 0:
        st.info("Load or enter data above to begin statistical analysis.")
        return

    st.divider()

    # Section 2 -- Analysis mode selector
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

    # Section 6 -- Advanced (PCA, K-means, Multiple regression)
    st.divider()
    _render_advanced_section(df)


# ===================================================================
# SECTION 1: DATA ENTRY
# ===================================================================


def _render_data_entry_section():
    """Three-mode data entry: paste, upload CSV, or import from analysis."""
    source = st.radio(
        "Data source",
        ["Enter / Paste", "Upload CSV", "From Analysis"],
        horizontal=True,
        key="stats_data_source",
    )

    if source == "Enter / Paste":
        _render_paste_entry()
    elif source == "Upload CSV":
        _render_upload_entry()
    elif source == "From Analysis":
        _render_from_analysis_entry()

    # Preview loaded data
    df: pd.DataFrame | None = st.session_state.get("stats_data")
    if df is not None and len(df) > 0:
        _render_data_preview(df)


def _render_paste_entry():
    """Manual data entry via st.data_editor."""
    df = st.session_state.get("stats_data")
    if df is None or len(df) == 0:
        df = pd.DataFrame(
            {f"Col_{i+1}": pd.Series([None] * 5, dtype="float64") for i in range(3)}
        )
        st.session_state["stats_data"] = df

    edited = st.data_editor(
        df,
        num_rows="dynamic",
        use_container_width=True,
        key="stats_data_editor",
    )
    if edited is not None:
        st.session_state["stats_data"] = edited


def _render_upload_entry():
    """CSV / TSV / TXT upload with encoding and delimiter detection."""
    uploaded = st.file_uploader(
        "Upload CSV or TSV",
        type=["csv", "tsv", "txt"],
        key="stats_file_uploader",
        help="Tab-separated or comma-separated files. Max 50,000 rows.",
    )
    if uploaded is None:
        return
    if uploaded.size == 0:
        st.error("File is empty.")
        return
    if uploaded.size > 10 * 1024 * 1024:
        st.error("File exceeds 10 MB limit.")
        return

    raw = uploaded.read()
    text = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        st.error("Could not detect file encoding. Save as UTF-8 and re-upload.")
        return

    # Delimiter detection
    first_line = text.split("\n")[0] if text else ""
    sep = "\t" if "\t" in first_line else ","

    try:
        df = pd.read_csv(
            io.StringIO(text),
            sep=sep,
            na_values=["", "NA", "N/A", "nan", "NaN", "."],
        )
    except pd.errors.ParserError as e:
        st.error(f"Malformed file: {e}")
        return

    # Row / column limits
    if len(df) > 50_000:
        st.warning("Truncated to 50,000 rows.")
        df = df.head(50_000)
    if len(df.columns) > 100:
        st.warning("Truncated to 100 columns.")
        df = df.iloc[:, :100]

    # Duplicate column names
    dupes = df.columns[df.columns.duplicated()].tolist()
    if dupes:
        st.warning(f"Duplicate columns renamed: {dupes}")
        cols = list(df.columns)
        seen: dict[str, int] = {}
        for i, c in enumerate(cols):
            if cols.count(c) > 1:
                count = seen.get(c, 0)
                if count > 0:
                    cols[i] = f"{c}_{count}"
                seen[c] = count + 1
        df.columns = pd.Index(cols)

    st.session_state["stats_data"] = df
    st.success(f"Loaded {len(df)} rows x {len(df.columns)} columns.")


def _render_from_analysis_entry():
    """Import data from the protein analysis pipeline."""
    prediction = st.session_state.get("prediction_result")
    trust_audit = st.session_state.get("trust_audit")
    bio_context = st.session_state.get("bio_context")

    if not prediction and not trust_audit and not bio_context:
        st.info(
            "No analysis data available. Run a protein query in the **Search** tab first, "
            "or use one of the other data entry modes."
        )
        return

    cols = st.columns(4)

    with cols[0]:
        has_plddt = prediction and prediction.plddt_per_residue
        if st.button(
            "pLDDT per Residue",
            key="stats_import_plddt",
            disabled=not has_plddt,
            help="Import per-residue pLDDT confidence scores" if has_plddt else "No pLDDT data available",
        ):
            df = pd.DataFrame({
                "residue_id": prediction.residue_ids,
                "chain": prediction.chain_ids,
                "plddt": prediction.plddt_per_residue,
            })
            st.session_state["stats_data"] = df
            st.rerun()

    with cols[1]:
        has_regions = trust_audit and trust_audit.regions
        if st.button(
            "Region Confidence",
            key="stats_import_regions",
            disabled=not has_regions,
            help="Import region-level confidence data" if has_regions else "No region data available",
        ):
            df = pd.DataFrame([{
                "chain": r.chain,
                "start": r.start_residue,
                "end": r.end_residue,
                "avg_plddt": r.avg_plddt,
                "flagged": bool(r.flag),
            } for r in trust_audit.regions])
            st.session_state["stats_data"] = df
            st.rerun()

    with cols[2]:
        has_disease = bio_context and bio_context.disease_associations
        if st.button(
            "Disease Scores",
            key="stats_import_disease",
            disabled=not has_disease,
            help="Import disease association scores" if has_disease else "No disease data available",
        ):
            df = pd.DataFrame([{
                "disease": d.disease,
                "score": d.score,
                "evidence": d.evidence,
            } for d in bio_context.disease_associations])
            st.session_state["stats_data"] = df
            st.rerun()

    with cols[3]:
        has_affinity = (
            prediction
            and prediction.affinity_json
            and prediction.affinity_json.get("poses")
        )
        if st.button(
            "Binding Affinity",
            key="stats_import_affinity",
            disabled=not has_affinity,
            help="Import binding affinity pose data" if has_affinity else "No affinity data available",
        ):
            df = pd.DataFrame(prediction.affinity_json["poses"])
            st.session_state["stats_data"] = df
            st.rerun()

    # Row 2: Additional analysis data
    query = st.session_state.get("parsed_query")
    query_name = query.protein_name if query else ""

    cols2 = st.columns(4)

    with cols2[0]:
        flex_key = f"flexibility_{query_name}"
        flex_data = st.session_state.get(flex_key)
        has_flex = flex_data and flex_data.get("residue_ids")
        if st.button(
            "Flexibility (ANM)",
            key="stats_import_flex",
            disabled=not has_flex,
            help="Import per-residue flexibility scores" if has_flex else "Run flexibility analysis first",
        ):
            df = pd.DataFrame({
                "residue_id": flex_data["residue_ids"],
                "flexibility": flex_data["flexibility"],
            })
            st.session_state["stats_data"] = df
            st.rerun()

    with cols2[1]:
        pocket_key = f"pockets_{query_name}"
        pocket_data = st.session_state.get(pocket_key)
        has_pockets = pocket_data and pocket_data.get("residue_pocket_scores")
        if st.button(
            "Pocket Scores",
            key="stats_import_pockets",
            disabled=not has_pockets,
            help="Import binding pocket scores" if has_pockets else "Run pocket analysis first",
        ):
            scores = pocket_data["residue_pocket_scores"]
            df = pd.DataFrame({
                "residue_id": list(scores.keys()),
                "pocket_score": list(scores.values()),
            })
            st.session_state["stats_data"] = df
            st.rerun()

    with cols2[2]:
        # Combined multi-track export
        has_any = has_plddt or has_flex or has_pockets
        if st.button(
            "All Residue Data",
            key="stats_import_all",
            disabled=not has_any,
            help="Import all available per-residue data as one table",
        ):
            _import_combined_residue_data(prediction, query_name)


def _import_combined_residue_data(prediction, query_name: str):
    """Combine all per-residue data into a single DataFrame."""
    if not prediction or not prediction.residue_ids:
        return
    data = {"residue_id": prediction.residue_ids}
    if prediction.plddt_per_residue:
        n = min(len(prediction.residue_ids), len(prediction.plddt_per_residue))
        data["plddt"] = prediction.plddt_per_residue[:n]
        data["residue_id"] = prediction.residue_ids[:n]

    flex_data = st.session_state.get(f"flexibility_{query_name}")
    if flex_data and flex_data.get("flexibility"):
        flex_map = dict(zip(flex_data["residue_ids"], flex_data["flexibility"]))
        data["flexibility"] = [flex_map.get(r, None) for r in data["residue_id"]]

    pocket_data = st.session_state.get(f"pockets_{query_name}")
    if pocket_data and pocket_data.get("residue_pocket_scores"):
        scores = pocket_data["residue_pocket_scores"]
        data["pocket_score"] = [scores.get(r, 0.0) for r in data["residue_id"]]

    df = pd.DataFrame(data)
    st.session_state["stats_data"] = df
    st.rerun()


def _render_data_preview(df: pd.DataFrame):
    """Show data preview, column types, and summary metrics."""
    from src.statistics_engine import detect_column_types

    col_types = detect_column_types(df.copy())
    st.session_state["stats_col_types"] = col_types

    # Metrics row
    m1, m2, m3 = st.columns(3)
    m1.metric("Rows", len(df))
    m2.metric("Columns", len(df.columns))
    m3.metric("Missing values", int(df.isna().sum().sum()))

    # Column type badges
    badge_colors = {
        "numeric": "#007AFF",
        "categorical": "#34C759",
        "text": "#8E8E93",
        "datetime": "#AF52DE",
        "empty": "#FF3B30",
    }
    badges_html = " ".join(
        f'<span style="display:inline-block;padding:2px 10px;border-radius:12px;'
        f'font-size:0.78rem;margin:2px;color:#fff;background:{badge_colors.get(dtype, "#8E8E93")}">'
        f"{col}: {dtype}</span>"
        for col, dtype in col_types.items()
    )
    st.markdown(badges_html, unsafe_allow_html=True)

    # DataFrame preview
    with st.expander("Data preview (first 20 rows)", expanded=False):
        st.dataframe(df.head(20), use_container_width=True)


# ===================================================================
# SECTION 3: STATISTICAL TESTS
# ===================================================================

_TEST_CATALOG: dict[str, list[str]] = {
    "Compare Two Groups": [
        "Independent t-test",
        "Paired t-test",
        "Mann-Whitney U",
        "Wilcoxon Signed-Rank",
    ],
    "Compare Multiple Groups": [
        "One-way ANOVA",
        "Kruskal-Wallis",
        "Welch's ANOVA",
        "Two-way ANOVA",
    ],
    "Correlation": [
        "Pearson",
        "Spearman",
    ],
    "Contingency": [
        "Chi-square",
        "Fisher's exact",
    ],
    "Classifier Performance": [
        "Logistic Regression",
        "ROC Curve",
    ],
    "Method Comparison": [
        "Bland-Altman",
    ],
}


def _render_tests_section(df: pd.DataFrame):
    """Render the statistical tests UI."""
    if not _HAS_PINGOUIN:
        st.warning("Statistical tests require **pingouin**. Install it first.")
        return

    col_types = st.session_state.get("stats_col_types") or {}
    numeric_cols = [c for c, t in col_types.items() if t == "numeric"]
    categorical_cols = [c for c, t in col_types.items() if t in ("categorical", "text")]

    # Test selection
    sel1, sel2 = st.columns(2)
    with sel1:
        category = st.selectbox(
            "Test category",
            list(_TEST_CATALOG.keys()),
            key="stats_test_category",
        )
    with sel2:
        test_name = st.selectbox(
            "Specific test",
            _TEST_CATALOG.get(category, []),
            key="stats_test_selector",
        )

    st.markdown("---")

    # Column selectors -- adapt by test type
    col_selections = _render_column_selectors(
        test_name, df, numeric_cols, categorical_cols
    )
    if col_selections is None:
        return

    # Run button
    if st.button("Run Test", key="stats_run_test", type="primary"):
        _execute_test(test_name, df, col_selections)


def _render_column_selectors(
    test_name: str,
    df: pd.DataFrame,
    numeric_cols: list[str],
    categorical_cols: list[str],
) -> dict | None:
    """Draw column selectors appropriate for the chosen test. Returns selection dict or None."""
    all_cols = list(df.columns)

    if test_name in ("Independent t-test", "Mann-Whitney U"):
        c1, c2 = st.columns(2)
        with c1:
            num_col = st.selectbox("Numeric column (values)", numeric_cols or all_cols, key="stats_col_dv")
        with c2:
            grp_col = st.selectbox("Grouping column (2 groups)", categorical_cols or all_cols, key="stats_col_group")
        if not num_col or not grp_col:
            st.info("Select a numeric column and a grouping column.")
            return None
        return {"type": "two_group", "dv": num_col, "group": grp_col}

    if test_name in ("Paired t-test", "Wilcoxon Signed-Rank"):
        c1, c2 = st.columns(2)
        with c1:
            col_x = st.selectbox("Column X (before / method 1)", numeric_cols or all_cols, key="stats_col_x")
        with c2:
            default_idx = min(1, len(numeric_cols) - 1) if len(numeric_cols) > 1 else 0
            col_y = st.selectbox(
                "Column Y (after / method 2)",
                numeric_cols or all_cols,
                key="stats_col_y",
                index=default_idx,
            )
        if not col_x or not col_y:
            st.info("Select two numeric columns.")
            return None
        if col_x == col_y:
            st.warning("Column X and Column Y are the same. Select two different columns for a paired test.")
            return None
        return {"type": "paired", "x": col_x, "y": col_y}

    if test_name in ("One-way ANOVA", "Kruskal-Wallis", "Welch's ANOVA"):
        c1, c2 = st.columns(2)
        with c1:
            dv = st.selectbox("Dependent variable (numeric)", numeric_cols or all_cols, key="stats_col_dv_anova")
        with c2:
            between = st.selectbox("Between factor (groups)", categorical_cols or all_cols, key="stats_col_between")
        if not dv or not between:
            st.info("Select a numeric column and a grouping column.")
            return None
        return {"type": "anova", "dv": dv, "between": between}

    if test_name == "Two-way ANOVA":
        c1, c2, c3 = st.columns(3)
        with c1:
            dv = st.selectbox("Dependent variable (numeric)", numeric_cols or all_cols, key="stats_col_dv_2way")
        with c2:
            fa = st.selectbox("Factor A", categorical_cols or all_cols, key="stats_col_factor_a")
        with c3:
            fb_opts = [c for c in (categorical_cols or all_cols) if c != fa]
            if not fb_opts:
                st.warning("Need at least 2 categorical columns for Two-way ANOVA.")
                return None
            fb = st.selectbox("Factor B", fb_opts, key="stats_col_factor_b")
        if not dv or not fa or not fb:
            st.info("Select a DV and two factors.")
            return None
        if fa == fb:
            st.warning("Factor A and Factor B must be different columns.")
            return None
        return {"type": "two_way_anova", "dv": dv, "factor_a": fa, "factor_b": fb}

    if test_name in ("Pearson", "Spearman"):
        c1, c2 = st.columns(2)
        with c1:
            col_x = st.selectbox("Column X", numeric_cols or all_cols, key="stats_col_corr_x")
        with c2:
            default_idx = min(1, len(numeric_cols) - 1) if len(numeric_cols) > 1 else 0
            col_y = st.selectbox("Column Y", numeric_cols or all_cols, key="stats_col_corr_y", index=default_idx)
        if not col_x or not col_y:
            st.info("Select two numeric columns.")
            return None
        if col_x == col_y:
            st.warning("Column X and Column Y are the same. Correlation with itself is always 1.")
            return None
        return {"type": "correlation", "x": col_x, "y": col_y, "method": test_name.lower()}

    if test_name in ("Chi-square", "Fisher's exact"):
        c1, c2 = st.columns(2)
        with c1:
            col1 = st.selectbox("Variable 1", categorical_cols or all_cols, key="stats_col_chi_1")
        with c2:
            col2_opts = [c for c in (categorical_cols or all_cols) if c != col1]
            if not col2_opts:
                st.warning("Need at least 2 categorical columns for contingency tests.")
                return None
            col2 = st.selectbox("Variable 2", col2_opts, key="stats_col_chi_2")
        if not col1 or not col2:
            st.info("Select two categorical columns.")
            return None
        if col1 == col2:
            st.warning("Variable 1 and Variable 2 must be different columns.")
            return None
        return {"type": "contingency", "col1": col1, "col2": col2, "test": test_name}

    if test_name == "Logistic Regression":
        c1, c2 = st.columns(2)
        with c1:
            target = st.selectbox("Binary target column", categorical_cols or all_cols, key="stats_col_logreg_target")
        with c2:
            feature_opts = [c for c in (numeric_cols or all_cols) if c != target]
            features = st.multiselect("Predictor columns (numeric)", feature_opts, key="stats_col_logreg_features")
        if not target or not features:
            st.info("Select a binary target and at least one numeric predictor.")
            return None
        return {"type": "logistic", "target": target, "features": features}

    if test_name == "ROC Curve":
        c1, c2 = st.columns(2)
        with c1:
            target = st.selectbox("Binary target (0/1)", all_cols, key="stats_col_roc_target")
        with c2:
            score = st.selectbox("Score / probability column", numeric_cols or all_cols, key="stats_col_roc_score")
        if not target or not score:
            st.info("Select a binary target column and a score column.")
            return None
        return {"type": "roc", "target": target, "score": score}

    if test_name == "Bland-Altman":
        c1, c2 = st.columns(2)
        with c1:
            m1 = st.selectbox("Method 1", numeric_cols or all_cols, key="stats_col_ba_m1")
        with c2:
            default_idx = min(1, len(numeric_cols) - 1) if len(numeric_cols) > 1 else 0
            m2 = st.selectbox("Method 2", numeric_cols or all_cols, key="stats_col_ba_m2", index=default_idx)
        if not m1 or not m2:
            st.info("Select two numeric columns representing two methods.")
            return None
        if m1 == m2:
            st.warning("Method 1 and Method 2 are the same column. Select two different methods.")
            return None
        return {"type": "bland_altman", "m1": m1, "m2": m2}

    st.warning(f"Unknown test: {test_name}")
    return None


def _execute_test(test_name: str, df: pd.DataFrame, sel: dict):
    """Run the selected test and display results."""
    from src.statistics_engine import (
        run_ttest,
        run_paired_ttest,
        run_mannwhitney,
        run_wilcoxon,
        run_one_way_anova,
        run_kruskal,
        run_welch_anova,
        run_two_way_anova,
        run_pearson,
        run_spearman,
        run_chi_square,
        run_fisher_exact,
        run_logistic_regression,
        compute_roc_curve,
        compute_bland_altman,
        check_normality,
        check_equal_variance,
    )

    with st.spinner(f"Running {test_name}..."):
        try:
            result = _dispatch_test(
                test_name, df, sel,
                run_ttest=run_ttest,
                run_paired_ttest=run_paired_ttest,
                run_mannwhitney=run_mannwhitney,
                run_wilcoxon=run_wilcoxon,
                run_one_way_anova=run_one_way_anova,
                run_kruskal=run_kruskal,
                run_welch_anova=run_welch_anova,
                run_two_way_anova=run_two_way_anova,
                run_pearson=run_pearson,
                run_spearman=run_spearman,
                run_chi_square=run_chi_square,
                run_fisher_exact=run_fisher_exact,
                run_logistic_regression=run_logistic_regression,
                compute_roc_curve=compute_roc_curve,
                compute_bland_altman=compute_bland_altman,
            )
        except Exception as e:
            st.error(f"Test execution failed: {e}")
            return

    if result is None:
        return

    if "error" in result:
        st.error(result["error"])
        return

    st.session_state["stats_results"] = result

    # -- Assumption checks (for applicable tests) --
    _show_assumption_checks(test_name, df, sel, check_normality, check_equal_variance)

    # -- Results display --
    _display_test_results(test_name, result, df, sel)


def _dispatch_test(test_name: str, df: pd.DataFrame, sel: dict, **funcs) -> dict | None:
    """Call the right engine function based on test_name."""
    t = sel.get("type")

    if test_name == "Independent t-test" and t == "two_group":
        groups = df.groupby(sel["group"])[sel["dv"]]
        group_names = list(groups.groups.keys())
        if len(group_names) < 2:
            return {"error": f"Need at least 2 groups, found {len(group_names)}."}
        g1 = groups.get_group(group_names[0]).dropna().values
        g2 = groups.get_group(group_names[1]).dropna().values
        result = funcs["run_ttest"](g1, g2)
        result["_groups"] = {str(group_names[0]): g1, str(group_names[1]): g2}
        result["_dv_label"] = sel["dv"]
        return result

    if test_name == "Paired t-test" and t == "paired":
        return funcs["run_paired_ttest"](
            df[sel["x"]].values, df[sel["y"]].values
        )

    if test_name == "Mann-Whitney U" and t == "two_group":
        groups = df.groupby(sel["group"])[sel["dv"]]
        group_names = list(groups.groups.keys())
        if len(group_names) < 2:
            return {"error": f"Need at least 2 groups, found {len(group_names)}."}
        g1 = groups.get_group(group_names[0]).dropna().values
        g2 = groups.get_group(group_names[1]).dropna().values
        result = funcs["run_mannwhitney"](g1, g2)
        result["_groups"] = {str(group_names[0]): g1, str(group_names[1]): g2}
        result["_dv_label"] = sel["dv"]
        return result

    if test_name == "Wilcoxon Signed-Rank" and t == "paired":
        return funcs["run_wilcoxon"](
            df[sel["x"]].values, df[sel["y"]].values
        )

    if test_name == "One-way ANOVA" and t == "anova":
        return funcs["run_one_way_anova"](df, sel["dv"], sel["between"])

    if test_name == "Kruskal-Wallis" and t == "anova":
        return funcs["run_kruskal"](df, sel["dv"], sel["between"])

    if test_name == "Welch's ANOVA" and t == "anova":
        return funcs["run_welch_anova"](df, sel["dv"], sel["between"])

    if test_name == "Two-way ANOVA" and t == "two_way_anova":
        return funcs["run_two_way_anova"](
            df, sel["dv"], sel["factor_a"], sel["factor_b"]
        )

    if test_name == "Pearson" and t == "correlation":
        return funcs["run_pearson"](
            df[sel["x"]].values, df[sel["y"]].values
        )

    if test_name == "Spearman" and t == "correlation":
        return funcs["run_spearman"](
            df[sel["x"]].values, df[sel["y"]].values
        )

    if test_name == "Chi-square" and t == "contingency":
        return funcs["run_chi_square"](df, sel["col1"], sel["col2"])

    if test_name == "Fisher's exact" and t == "contingency":
        ct = pd.crosstab(df[sel["col1"]].dropna(), df[sel["col2"]].dropna())
        return funcs["run_fisher_exact"](ct)

    if test_name == "Logistic Regression" and t == "logistic":
        return funcs["run_logistic_regression"](df, sel["target"], sel["features"])

    if test_name == "ROC Curve" and t == "roc":
        y_true = pd.to_numeric(df[sel["target"]], errors="coerce").values
        y_scores = pd.to_numeric(df[sel["score"]], errors="coerce").values
        return funcs["compute_roc_curve"](y_true, y_scores)

    if test_name == "Bland-Altman" and t == "bland_altman":
        return funcs["compute_bland_altman"](
            df[sel["m1"]].values, df[sel["m2"]].values,
            method1_name=sel["m1"], method2_name=sel["m2"],
        )

    return {"error": f"Could not dispatch test '{test_name}' with selection type '{t}'."}


def _show_assumption_checks(test_name, df, sel, check_normality_fn, check_equal_variance_fn):
    """Show assumption checks in an expander for applicable tests."""
    applicable = {
        "Independent t-test", "Paired t-test", "One-way ANOVA",
        "Welch's ANOVA", "Two-way ANOVA",
    }
    if test_name not in applicable:
        return

    with st.expander("Assumption checks", expanded=False):
        try:
            if sel.get("type") == "two_group":
                groups = df.groupby(sel["group"])[sel["dv"]]
                group_names = list(groups.groups.keys())
                for gn in group_names[:2]:
                    vals = groups.get_group(gn).dropna().values
                    norm = check_normality_fn(vals, label=str(gn))
                    st.markdown(f"- {norm.get('message', 'N/A')}")
                if len(group_names) >= 2:
                    g1 = groups.get_group(group_names[0]).dropna().values
                    g2 = groups.get_group(group_names[1]).dropna().values
                    eqvar = check_equal_variance_fn(g1, g2)
                    st.markdown(f"- {eqvar.get('message', 'N/A')}")
            elif sel.get("type") == "paired":
                for col_key in ("x", "y"):
                    vals = df[sel[col_key]].dropna().values
                    norm = check_normality_fn(vals, label=sel[col_key])
                    st.markdown(f"- {norm.get('message', 'N/A')}")
            elif sel.get("type") in ("anova", "two_way_anova"):
                groups = df.groupby(sel["between"] if "between" in sel else sel["factor_a"])[
                    sel["dv"]
                ]
                for gn in list(groups.groups.keys())[:5]:
                    vals = groups.get_group(gn).dropna().values
                    norm = check_normality_fn(vals, label=str(gn))
                    st.markdown(f"- {norm.get('message', 'N/A')}")
        except Exception as e:
            st.caption(f"Could not run assumption checks: {e}")


def _display_test_results(test_name: str, result: dict, df: pd.DataFrame, sel: dict):
    """Display test results: table, interpretation, chart, pin button."""
    from src.statistics_charts import (
        build_comparison_chart,
        build_violin_chart,
        build_scatter_with_fit,
        build_contingency_chart,
        build_roc_chart,
        build_bland_altman_chart,
        build_interaction_plot,
        build_odds_ratio_forest,
    )

    # Result table
    result_df = result.get("result_df")
    if result_df:
        if isinstance(result_df, list):
            st.dataframe(pd.DataFrame(result_df), use_container_width=True)
        elif isinstance(result_df, dict):
            st.dataframe(pd.DataFrame(result_df), use_container_width=True)

    # Post-hoc table
    posthoc_df = result.get("posthoc_df")
    if posthoc_df:
        with st.expander("Post-hoc pairwise comparisons", expanded=False):
            st.dataframe(pd.DataFrame(posthoc_df), use_container_width=True)

    # NaN removal notice
    nan_removed = result.get("nan_removed", 0)
    if nan_removed:
        st.caption(f"{nan_removed} row(s) with missing values were excluded.")

    # Warning
    if result.get("warning"):
        st.warning(result["warning"])

    # Interpretation
    interp = _interpret_result(result)
    if interp:
        st.markdown(
            f'<div class="glow-card" style="padding:12px;margin:8px 0">'
            f'<span style="font-weight:600">Interpretation:</span> {interp}'
            f"</div>",
            unsafe_allow_html=True,
        )

    # Charts
    fig = None
    chart_title = test_name

    try:
        if test_name in ("Independent t-test", "Mann-Whitney U") and "_groups" in result:
            fig = build_comparison_chart(
                result["_groups"],
                result.get("_dv_label", "Value"),
                p_value=result.get("p_val"),
            )
        elif test_name in ("One-way ANOVA", "Kruskal-Wallis", "Welch's ANOVA"):
            groups_dict = {}
            for gn, gdf in df.groupby(sel["between"]):
                groups_dict[str(gn)] = gdf[sel["dv"]].dropna().values
            fig = build_violin_chart(
                groups_dict,
                sel["dv"],
                p_value=result.get("p_val"),
            )
        elif test_name == "Two-way ANOVA":
            fig = build_interaction_plot(df, sel["dv"], sel["factor_a"], sel["factor_b"])
        elif test_name in ("Pearson", "Spearman"):
            from src.statistics_charts import build_scatter_with_fit as _scatter
            # Simple scatter without fit
            x_vals = df[sel["x"]].dropna().values
            y_vals = df[sel["y"]].dropna().values
            import plotly.graph_objects as go
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=x_vals, y=y_vals, mode="markers",
                marker=dict(color="#648FFF", size=8),
                name="Data",
            ))
            r_val = result.get("r", 0)
            fig.update_layout(
                template="plotly_white",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title=sel["x"],
                yaxis_title=sel["y"],
                height=400,
                annotations=[dict(
                    text=f"r = {r_val:.3f}",
                    xref="paper", yref="paper",
                    x=0.98, y=0.98,
                    showarrow=False,
                    font=dict(size=13, color="rgba(60,60,67,0.6)"),
                )],
            )
        elif test_name in ("Chi-square", "Fisher's exact"):
            ct = result.get("contingency_table")
            if ct:
                fig = build_contingency_chart(ct)
        elif test_name == "ROC Curve":
            fig = build_roc_chart(
                result["fpr"], result["tpr"], result["auc"],
                thresholds=result.get("thresholds"),
            )
        elif test_name == "Bland-Altman":
            fig = build_bland_altman_chart(result)
        elif test_name == "Logistic Regression":
            # Show ROC if y_pred_proba is available
            if result.get("y_pred_proba") and result.get("y_true"):
                from src.statistics_engine import compute_roc_curve
                roc = compute_roc_curve(result["y_true"], result["y_pred_proba"])
                if "error" not in roc:
                    fig = build_roc_chart(roc["fpr"], roc["tpr"], roc["auc"])
                    chart_title = "Logistic Regression ROC"
    except Exception as e:
        st.caption(f"Chart could not be rendered: {e}")

    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)

        # Pin button
        summary = _interpret_result(result) or f"{test_name} result"
        pin_button(
            title=f"Stats: {chart_title}",
            summary=summary[:200],
            insight_type="chart",
            data={
                "test_name": result.get("test_name", test_name),
                "p_val": result.get("p_val"),
            },
            chart_json=fig.to_json(),
            key="pin_stats_" + test_name.replace(" ", "_").replace("'", ""),
        )


def _interpret_result(result: dict) -> str:
    """Generate a plain English interpretation from test result dict."""
    parts = []
    test_name = result.get("test_name", "Test")

    p = result.get("p_val")
    if p is not None:
        if p < 0.001:
            sig = "highly significant (p < 0.001)"
        elif p < 0.01:
            sig = f"significant (p = {p:.4f})"
        elif p < 0.05:
            sig = f"marginally significant (p = {p:.4f})"
        else:
            sig = f"not statistically significant (p = {p:.4f})"
        parts.append(f"The {test_name} result is {sig}.")

    # Effect sizes
    cohen_d = result.get("cohen_d")
    if cohen_d is not None:
        magnitude = "negligible"
        d = abs(cohen_d)
        if d >= 0.8:
            magnitude = "large"
        elif d >= 0.5:
            magnitude = "medium"
        elif d >= 0.2:
            magnitude = "small"
        parts.append(f"Cohen's d = {cohen_d:.3f} ({magnitude} effect).")

    eta_sq = result.get("eta_squared")
    if eta_sq is not None:
        magnitude = "small"
        if eta_sq >= 0.14:
            magnitude = "large"
        elif eta_sq >= 0.06:
            magnitude = "medium"
        parts.append(f"Eta-squared = {eta_sq:.3f} ({magnitude} effect).")

    cramers_v = result.get("cramers_v")
    if cramers_v is not None:
        parts.append(f"Cramer's V = {cramers_v:.3f}.")

    r = result.get("r")
    if r is not None:
        direction = "positive" if r > 0 else "negative"
        strength = "weak"
        if abs(r) >= 0.7:
            strength = "strong"
        elif abs(r) >= 0.4:
            strength = "moderate"
        parts.append(f"r = {r:.3f} ({strength} {direction} correlation).")

    auc = result.get("auc")
    if auc is not None:
        quality = "poor"
        if auc >= 0.9:
            quality = "excellent"
        elif auc >= 0.8:
            quality = "good"
        elif auc >= 0.7:
            quality = "fair"
        parts.append(f"AUC = {auc:.3f} ({quality} discrimination).")

    return " ".join(parts) if parts else ""


# ===================================================================
# SECTION 4: CURVE FITTING
# ===================================================================


def _render_fitting_section(df: pd.DataFrame):
    """Render the curve fitting UI."""
    from src.statistics_engine import BUILTIN_EQUATIONS, fit_curve

    col_types = st.session_state.get("stats_col_types") or {}
    numeric_cols = [c for c, t in col_types.items() if t == "numeric"]
    if len(numeric_cols) < 2:
        st.info("Curve fitting requires at least 2 numeric columns (X and Y).")
        return

    # Column selectors
    c1, c2 = st.columns(2)
    with c1:
        x_col = st.selectbox("X column", numeric_cols, key="stats_fit_col_x")
    with c2:
        y_default = min(1, len(numeric_cols) - 1)
        y_col = st.selectbox("Y column", numeric_cols, key="stats_fit_col_y", index=y_default)

    # Equation selection grouped by category
    categories = sorted(set(eq["category"] for eq in BUILTIN_EQUATIONS.values()))

    eq_c1, eq_c2 = st.columns(2)
    with eq_c1:
        eq_category = st.selectbox("Equation category", categories, key="stats_eq_category")
    with eq_c2:
        eqs_in_cat = [
            name for name, eq in BUILTIN_EQUATIONS.items()
            if eq["category"] == eq_category
        ]
        eq_name = st.selectbox("Equation", eqs_in_cat, key="stats_eq_selector")

    if eq_name:
        eq_info = BUILTIN_EQUATIONS[eq_name]
        st.caption(
            f"**{eq_info['formula_display']}**  \n"
            f"{eq_info['description']}  \n"
            f"Parameters: {', '.join(eq_info['param_names'])} | Min data points: {eq_info['min_points']}"
        )

        # Fixed parameter inputs
        fixed_params: dict[str, float] = {}
        if eq_info.get("fixed_params"):
            st.markdown("**Fixed parameters:**")
            fp_cols = st.columns(len(eq_info["fixed_params"]))
            for i, fp_name in enumerate(eq_info["fixed_params"]):
                with fp_cols[i]:
                    fp_val = st.number_input(
                        fp_name,
                        value=1.0,
                        format="%.4f",
                        key=f"stats_fp_{fp_name}",
                    )
                    fixed_params[fp_name] = fp_val

    # Fit button
    if st.button("Fit Curve", key="stats_run_fit", type="primary"):
        if not eq_name:
            st.warning("Select an equation first.")
            return

        x_data = pd.to_numeric(df[x_col], errors="coerce").dropna().values
        y_data = pd.to_numeric(df[y_col], errors="coerce").dropna().values
        min_len = min(len(x_data), len(y_data))
        x_data = x_data[:min_len]
        y_data = y_data[:min_len]

        with st.spinner("Fitting curve..."):
            try:
                result = fit_curve(
                    x_data, y_data, eq_name,
                    fixed_param_values=fixed_params if fixed_params else None,
                )
            except Exception as e:
                st.error(f"Curve fitting failed: {e}")
                return

        if not result.get("converged"):
            st.error(result.get("message", "Fit did not converge."))
            return

        _display_fit_results(result, x_data, y_data, x_col, y_col, eq_name)


def _display_fit_results(
    result: dict,
    x_data: np.ndarray,
    y_data: np.ndarray,
    x_label: str,
    y_label: str,
    eq_name: str,
):
    """Display curve fitting results: parameters, GOF metrics, charts."""
    from src.statistics_charts import (
        build_scatter_with_fit,
        build_residual_plot,
        build_qq_plot,
    )

    # Goodness of fit metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("R\u00b2", f"{result['r_squared']:.4f}")
    m2.metric("Adj R\u00b2", f"{result['adj_r_squared']:.4f}")
    m3.metric("AIC", f"{result['aic']:.1f}")
    m4.metric("BIC", f"{result['bic']:.1f}")

    # Parameter table
    param_data = []
    for name in result["params"]:
        param_data.append({
            "Parameter": name,
            "Value": result["params"][name],
            "Std Error": result["param_errors"].get(name, float("nan")),
            "CI Lower": result["param_ci95"].get(name, (None, None))[0],
            "CI Upper": result["param_ci95"].get(name, (None, None))[1],
        })
    st.dataframe(pd.DataFrame(param_data), use_container_width=True)

    if result.get("nan_removed", 0) > 0:
        st.caption(f"{result['nan_removed']} row(s) with missing values were excluded.")

    # Charts: scatter+fit, residuals, Q-Q
    fig_fit = build_scatter_with_fit(
        x_data, y_data, result,
        x_label=x_label, y_label=y_label, equation_name=eq_name,
    )
    st.plotly_chart(fig_fit, use_container_width=True)

    res_col, qq_col = st.columns(2)
    with res_col:
        fig_res = build_residual_plot(
            x_data[:len(result["residuals"])],
            np.array(result["residuals"]),
        )
        st.plotly_chart(fig_res, use_container_width=True)

    with qq_col:
        fig_qq = build_qq_plot(np.array(result["residuals"]))
        st.plotly_chart(fig_qq, use_container_width=True)

    # Pin button
    pin_button(
        title=f"Fit: {eq_name}",
        summary=f"R\u00b2 = {result['r_squared']:.4f}, {len(result['params'])} params",
        insight_type="chart",
        data={
            "equation": eq_name,
            "r_squared": result["r_squared"],
            "params": result["params"],
        },
        chart_json=fig_fit.to_json(),
        key=f"pin_stats_fit_{eq_name.replace(' ', '_')[:25]}",
    )


# ===================================================================
# SECTION 5: SURVIVAL ANALYSIS
# ===================================================================


def _render_survival_section():
    """Render survival analysis UI with separate data entry."""
    if not _HAS_LIFELINES:
        st.warning(
            "Survival analysis requires **lifelines**.  \n"
            "Run `uv pip install lifelines` and restart the app."
        )
        return

    st.markdown("#### Survival Data")
    st.caption(
        "Survival analysis requires columns: **time** (numeric, >= 0), "
        "**event** (0 = censored, 1 = event), and optionally **group**."
    )

    # Template download
    template_df = pd.DataFrame({
        "time": [1.0, 2.5, 3.0, 4.2, 5.0, 6.1, 7.3, 8.0, 9.5, 10.0],
        "event": [1, 1, 0, 1, 0, 1, 1, 0, 1, 0],
        "group": ["A", "A", "A", "B", "B", "A", "B", "B", "A", "B"],
    })
    csv_bytes = template_df.to_csv(index=False).encode()
    st.download_button(
        "Download template CSV",
        csv_bytes,
        "survival_template.csv",
        mime="text/csv",
        key="stats_surv_template_dl",
    )

    # Data entry modes
    surv_source = st.radio(
        "Survival data source",
        ["Upload CSV", "Enter / Paste"],
        horizontal=True,
        key="stats_surv_source",
    )

    if surv_source == "Upload CSV":
        uploaded = st.file_uploader(
            "Upload survival data",
            type=["csv", "tsv", "txt"],
            key="stats_surv_uploader",
        )
        if uploaded is not None:
            try:
                raw = uploaded.read()
                text = None
                for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
                    try:
                        text = raw.decode(encoding)
                        break
                    except UnicodeDecodeError:
                        continue
                if text is None:
                    text = raw.decode("utf-8", errors="replace")
                sep = "\t" if "\t" in text.split("\n")[0] else ","
                surv_df = pd.read_csv(io.StringIO(text), sep=sep)
                st.session_state["stats_survival_data"] = surv_df
            except Exception as e:
                st.error(f"Failed to read survival data: {e}")
    else:
        surv_df = st.session_state.get("stats_survival_data")
        if surv_df is None:
            surv_df = template_df.copy()
            st.session_state["stats_survival_data"] = surv_df

        edited = st.data_editor(
            surv_df,
            num_rows="dynamic",
            use_container_width=True,
            key="stats_surv_editor",
        )
        if edited is not None:
            st.session_state["stats_survival_data"] = edited

    surv_df = st.session_state.get("stats_survival_data")
    if surv_df is None or len(surv_df) == 0:
        st.info("Load survival data to continue.")
        return

    # Validate required columns
    required_cols = {"time", "event"}
    missing = required_cols - set(surv_df.columns)
    if missing:
        st.error(
            f"Missing required column(s): **{', '.join(missing)}**. "
            "Rename your columns to 'time' and 'event'."
        )
        return

    # Validate time and event values
    time_numeric = pd.to_numeric(surv_df["time"], errors="coerce")
    if time_numeric.isna().all():
        st.error("The **time** column contains no valid numeric values.")
        return
    if (time_numeric.dropna() < 0).any():
        st.warning("The **time** column contains negative values. Survival analysis requires non-negative times.")

    event_numeric = pd.to_numeric(surv_df["event"], errors="coerce")
    if event_numeric.isna().all():
        st.error("The **event** column contains no valid numeric values.")
        return
    valid_events = event_numeric.dropna()
    if not valid_events.isin([0, 1]).all():
        st.warning("The **event** column should contain only 0 (censored) and 1 (event). Non-{0,1} values detected.")

    st.dataframe(surv_df.head(10), use_container_width=True)

    has_group = "group" in surv_df.columns

    # Analysis buttons
    btn_cols = st.columns(3)

    with btn_cols[0]:
        run_km = st.button("Kaplan-Meier Plot", key="stats_surv_km", type="primary")
    with btn_cols[1]:
        run_lr = st.button(
            "Log-rank Test",
            key="stats_surv_logrank",
            disabled=not has_group,
            help="Requires a 'group' column" if not has_group else "Compare survival between groups",
        )
    with btn_cols[2]:
        covariate_cols = [c for c in surv_df.columns if c not in ("time", "event")]
        run_cox = st.button(
            "Cox Regression",
            key="stats_surv_cox",
            disabled=len(covariate_cols) == 0,
            help="Requires covariate columns besides time/event" if not covariate_cols else "Fit Cox PH model",
        )

    from src.statistics_engine import run_kaplan_meier, run_logrank, run_cox_regression
    from src.statistics_charts import build_survival_chart

    if run_km:
        with st.spinner("Running Kaplan-Meier estimation..."):
            try:
                group_arr = surv_df["group"].values if has_group else None
                km_result = run_kaplan_meier(
                    surv_df["time"].values,
                    surv_df["event"].values,
                    group=group_arr,
                )
            except Exception as e:
                st.error(f"Kaplan-Meier failed: {e}")
                return

        if "error" in km_result:
            st.error(km_result["error"])
            return

        fig = build_survival_chart(km_result)
        st.plotly_chart(fig, use_container_width=True)

        # Median survival
        medians = km_result.get("median_survival", {})
        if medians:
            st.markdown("**Median survival time:**")
            for grp, med in medians.items():
                display = f"{med:.2f}" if med is not None else "not reached"
                st.markdown(f"- {grp}: {display}")

        pin_button(
            title="KM Survival Curve",
            summary=f"{len(surv_df)} subjects, {int(surv_df['event'].sum())} events",
            insight_type="chart",
            chart_json=fig.to_json(),
            key="pin_stats_km_survival",
        )

    if run_lr and has_group:
        with st.spinner("Running log-rank test..."):
            try:
                lr_result = run_logrank(
                    surv_df["time"].values,
                    surv_df["event"].values,
                    surv_df["group"].values,
                )
            except Exception as e:
                st.error(f"Log-rank test failed: {e}")
                return

        if "error" in lr_result:
            st.error(lr_result["error"])
        else:
            p = lr_result.get("p_val", 1.0)
            sig = "significant" if p < 0.05 else "not significant"
            st.markdown(
                f'<div class="glow-card" style="padding:12px;margin:8px 0">'
                f'<span style="font-weight:600">Log-rank test:</span> '
                f'test statistic = {lr_result.get("test_statistic", 0):.3f}, '
                f"p = {p:.4f} ({sig})"
                f"</div>",
                unsafe_allow_html=True,
            )

    if run_cox and covariate_cols:
        with st.spinner("Fitting Cox PH model..."):
            try:
                cox_result = run_cox_regression(
                    surv_df,
                    duration_col="time",
                    event_col="event",
                    covariates=covariate_cols,
                )
            except Exception as e:
                st.error(f"Cox regression failed: {e}")
                return

        if "error" in cox_result:
            st.error(cox_result["error"])
        else:
            # Summary table
            summary_df = cox_result.get("summary_df")
            if summary_df:
                st.dataframe(pd.DataFrame(summary_df), use_container_width=True)

            # Concordance
            conc = cox_result.get("concordance")
            if conc is not None:
                st.metric("Concordance index", f"{conc:.3f}")

            # Hazard ratios
            hrs = cox_result.get("hazard_ratios", {})
            if hrs:
                st.markdown("**Hazard ratios:**")
                for cov, hr in hrs.items():
                    st.markdown(f"- {cov}: HR = {hr:.3f}")


# ===================================================================
# SECTION 6: ADVANCED (Tier 2)
# ===================================================================


def _render_advanced_section(df: pd.DataFrame):
    """PCA, K-means, and multiple regression -- shown only if data is rich enough."""
    col_types = st.session_state.get("stats_col_types") or {}
    numeric_cols = [c for c, t in col_types.items() if t == "numeric"]

    if len(numeric_cols) < 2:
        return

    st.markdown("#### Advanced Analysis")

    adv_tabs = []
    if len(numeric_cols) >= 3:
        adv_tabs.append("PCA")
    if len(numeric_cols) >= 2:
        adv_tabs.append("K-means Clustering")
    if len(numeric_cols) >= 3:
        adv_tabs.append("Multiple Regression")

    if not adv_tabs:
        return

    tabs = st.tabs(adv_tabs)

    tab_idx = 0

    # PCA
    if "PCA" in adv_tabs:
        with tabs[tab_idx]:
            _render_pca(df, numeric_cols)
        tab_idx += 1

    # K-means
    if "K-means Clustering" in adv_tabs:
        with tabs[tab_idx]:
            _render_kmeans(df, numeric_cols)
        tab_idx += 1

    # Multiple regression
    if "Multiple Regression" in adv_tabs:
        with tabs[tab_idx]:
            _render_multiple_regression(df, numeric_cols)
        tab_idx += 1


def _render_pca(df: pd.DataFrame, numeric_cols: list[str]):
    """PCA biplot and scree plot."""
    from src.statistics_engine import run_pca
    from src.statistics_charts import build_pca_biplot, build_scree_plot

    n_comp = st.slider(
        "Number of components",
        min_value=2,
        max_value=min(10, len(numeric_cols)),
        value=min(2, len(numeric_cols)),
        key="stats_pca_n_components",
    )

    if st.button("Run PCA", key="stats_run_pca"):
        with st.spinner("Running PCA..."):
            try:
                result = run_pca(df[numeric_cols], n_components=n_comp)
            except Exception as e:
                st.error(f"PCA failed: {e}")
                return

        if "error" in result:
            st.error(result["error"])
            return

        # Scree plot
        fig_scree = build_scree_plot(result["explained_variance_ratio"])
        st.plotly_chart(fig_scree, use_container_width=True)

        # Biplot
        fig_biplot = build_pca_biplot(
            result["scores"],
            result["loadings"],
            result["columns_used"],
            result["explained_variance_ratio"],
        )
        st.plotly_chart(fig_biplot, use_container_width=True)

        # Variance explained
        total_var = sum(result["explained_variance_ratio"]) * 100
        st.caption(f"Total variance explained by {n_comp} components: {total_var:.1f}%")

        pin_button(
            title="PCA Biplot",
            summary=f"{n_comp} components, {total_var:.1f}% variance explained",
            insight_type="chart",
            chart_json=fig_biplot.to_json(),
            key="pin_stats_pca",
        )


def _render_kmeans(df: pd.DataFrame, numeric_cols: list[str]):
    """K-means with elbow plot."""
    from src.statistics_engine import run_kmeans
    from src.statistics_charts import build_elbow_plot

    max_k = st.slider(
        "Maximum K to evaluate",
        min_value=2,
        max_value=min(15, len(df) - 1),
        value=min(10, len(df) - 1),
        key="stats_kmeans_max_k",
    )

    if st.button("Run K-means", key="stats_run_kmeans"):
        with st.spinner("Running K-means clustering..."):
            try:
                result = run_kmeans(df[numeric_cols], max_k=max_k)
            except Exception as e:
                st.error(f"K-means failed: {e}")
                return

        if "error" in result:
            st.error(result["error"])
            return

        # Elbow plot
        fig_elbow = build_elbow_plot(result["k_values"], result["inertias"])
        st.plotly_chart(fig_elbow, use_container_width=True)

        # Results
        optimal_k = result.get("chosen_k", 2)
        sil = result.get("silhouette")
        st.metric("Optimal K", optimal_k)
        if sil is not None:
            st.metric("Silhouette score", f"{sil:.3f}")

        # Show cluster labels
        if result.get("labels"):
            st.caption(f"Cluster labels assigned for K = {optimal_k}.")
            cluster_df = df[numeric_cols].copy()
            cluster_df["cluster"] = result["labels"]
            with st.expander("Clustered data", expanded=False):
                st.dataframe(cluster_df.head(50), use_container_width=True)

        pin_button(
            title="K-means Elbow",
            summary=f"Optimal K = {optimal_k}, silhouette = {sil:.3f}" if sil else f"Optimal K = {optimal_k}",
            insight_type="chart",
            chart_json=fig_elbow.to_json(),
            key="pin_stats_kmeans",
        )


def _render_multiple_regression(df: pd.DataFrame, numeric_cols: list[str]):
    """Multiple linear regression with diagnostics."""
    from src.statistics_engine import run_multiple_regression
    from src.statistics_charts import build_regression_diagnostics

    c1, c2 = st.columns(2)
    with c1:
        target = st.selectbox("Target (Y)", numeric_cols, key="stats_multreg_target")
    with c2:
        predictors = st.multiselect(
            "Predictors (X)",
            [c for c in numeric_cols if c != target],
            key="stats_multreg_features",
        )

    if not predictors:
        st.info("Select at least one predictor.")
        return

    if st.button("Run Regression", key="stats_run_multreg"):
        with st.spinner("Fitting multiple regression..."):
            try:
                result = run_multiple_regression(df, target, predictors)
            except Exception as e:
                st.error(f"Multiple regression failed: {e}")
                return

        if "error" in result:
            st.error(result["error"])
            return

        # Summary metrics
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("R\u00b2", f"{result.get('r_squared', 0):.4f}")
        m2.metric("Adj R\u00b2", f"{result.get('adj_r_squared', 0):.4f}")
        m3.metric("F-statistic", f"{result.get('f_statistic', 0):.2f}")
        m4.metric("p-value (F)", f"{result.get('f_pvalue', 1):.4f}")

        # Coefficient table
        coef_df = result.get("coefficients_df") or result.get("result_df")
        if coef_df:
            if isinstance(coef_df, list):
                st.dataframe(pd.DataFrame(coef_df), use_container_width=True)
            elif isinstance(coef_df, dict):
                st.dataframe(pd.DataFrame(coef_df), use_container_width=True)

        # VIF
        vif = result.get("vif")
        if vif:
            st.markdown("**Variance Inflation Factors (VIF):**")
            vif_items = []
            for name, val in vif.items():
                flag = " (high multicollinearity)" if val > 5 else ""
                vif_items.append(f"- {name}: {val:.2f}{flag}")
            st.markdown("\n".join(vif_items))

        # Diagnostics plot
        if result.get("y_true") and result.get("y_pred") and result.get("residuals"):
            fig_diag = build_regression_diagnostics(
                np.array(result["y_true"]),
                np.array(result["y_pred"]),
                np.array(result["residuals"]),
            )
            st.plotly_chart(fig_diag, use_container_width=True)

            pin_button(
                title="Multiple Regression Diagnostics",
                summary=f"R\u00b2 = {result.get('r_squared', 0):.4f}, {len(predictors)} predictors",
                insight_type="chart",
                chart_json=fig_diag.to_json(),
                key="pin_stats_multreg",
            )
