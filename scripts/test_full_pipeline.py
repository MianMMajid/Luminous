#!/usr/bin/env python3
"""Comprehensive test suite for the Luminous pipeline.

Tests cover:
  1. Data models & serialization
  2. Precomputed data loading & integrity
  3. Query parser (fallback)
  4. Trust auditor (build audit from PDB)
  5. Interpreter (fallback mode)
  6. Statistics engine (14 tests + curve fitting + survival + tier-2)
  7. Statistics charts (19 chart builders)
  8. Statistics tab edge cases (all guards we added)
  9. Utility functions (pLDDT parsing, region confidence, JSON encoder)
 10. Component import smoke test (all 31 components import without error)
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0
SKIP = 0


def _run(name: str, func):
    global PASS, FAIL, SKIP
    try:
        result = func()
        if result == "SKIP":
            print(f"  SKIP  {name}")
            SKIP += 1
        else:
            print(f"  PASS  {name}")
            PASS += 1
    except Exception as e:
        print(f"  FAIL  {name}")
        print(f"        {e}")
        traceback.print_exc()
        FAIL += 1


# ===================================================================
# 1. DATA MODELS & SERIALIZATION
# ===================================================================

def test_models_create():
    from src.models import (
        ProteinQuery, TrustAudit, RegionConfidence, BioContext,
        DiseaseAssociation, DrugCandidate, LiteratureSummary,
        PredictionResult,
    )
    q = ProteinQuery(protein_name="TP53", mutation="R248W", question_type="druggability")
    assert q.protein_name == "TP53"
    assert q.mutation == "R248W"

    region = RegionConfidence(chain="A", start_residue=1, end_residue=20, avg_plddt=85.0, flag=None)
    ta = TrustAudit(
        overall_confidence="high", confidence_score=0.85,
        regions=[region], known_limitations=["test"],
    )
    assert ta.confidence_score == 0.85
    assert len(ta.regions) == 1

    da = DiseaseAssociation(disease="Cancer", score=0.9, evidence="Strong")
    drug = DrugCandidate(name="Imatinib", phase="Phase 3", mechanism="TKI")
    lit = LiteratureSummary(total_papers=100, recent_papers=10, key_findings=["finding1"])
    ctx = BioContext(
        narrative="test", disease_associations=[da], drugs=[drug],
        literature=lit, pathways=["MAPK"], suggested_experiments=["Exp1"],
    )
    assert len(ctx.disease_associations) == 1
    assert ctx.drugs[0].name == "Imatinib"

    pred = PredictionResult(
        pdb_content="ATOM...", confidence_json={"ptm": 0.8},
        plddt_per_residue=[90.0, 85.0], chain_ids=["A", "A"],
        residue_ids=[1, 2], compute_source="precomputed",
    )
    assert pred.compute_source == "precomputed"


def test_models_serialize():
    from src.models import ProteinQuery, BioContext, DiseaseAssociation
    q = ProteinQuery(protein_name="BRCA1", mutation="C61G")
    d = q.model_dump()
    assert d["protein_name"] == "BRCA1"
    j = q.model_dump_json()
    assert "BRCA1" in j

    ctx = BioContext(disease_associations=[
        DiseaseAssociation(disease="Breast cancer", score=0.95),
    ])
    d = ctx.model_dump()
    assert d["disease_associations"][0]["disease"] == "Breast cancer"


# ===================================================================
# 2. PRECOMPUTED DATA LOADING & INTEGRITY
# ===================================================================

EXPECTED_EXAMPLES = ["p53_r248w", "brca1_c61g", "egfr_t790m",
                     "spike_rbd", "hba1_hemoglobin", "insulin"]

def test_precomputed_all_present():
    from src.utils import load_precomputed
    for name in EXPECTED_EXAMPLES:
        data = load_precomputed(name)
        assert data is not None, f"Missing precomputed data for {name}"
        assert "pdb" in data, f"{name}: missing PDB"
        assert "confidence" in data, f"{name}: missing confidence"
        assert "context" in data, f"{name}: missing context"


def test_precomputed_pdb_has_atoms():
    from src.utils import load_precomputed
    for name in EXPECTED_EXAMPLES:
        data = load_precomputed(name)
        pdb_text = data["pdb"]
        atom_lines = [l for l in pdb_text.split("\n") if l.startswith("ATOM")]
        assert len(atom_lines) > 50, f"{name}: PDB has only {len(atom_lines)} ATOM lines"


def test_precomputed_confidence_keys():
    from src.utils import load_precomputed
    for name in EXPECTED_EXAMPLES:
        data = load_precomputed(name)
        conf = data["confidence"]
        assert isinstance(conf, dict), f"{name}: confidence is not a dict"
        assert "confidence_score" in conf or "ptm" in conf or "plddt_per_residue" in conf, \
            f"{name}: confidence has no known keys: {list(conf.keys())}"


def test_precomputed_context_structure():
    from src.utils import load_precomputed
    for name in EXPECTED_EXAMPLES:
        data = load_precomputed(name)
        ctx = data["context"]
        assert isinstance(ctx, dict), f"{name}: context is not a dict"
        # Should have at least disease or narrative or drugs
        has_content = any(k in ctx for k in (
            "disease_associations", "narrative", "drugs", "pathways",
            "literature", "suggested_experiments",
        ))
        assert has_content, f"{name}: context has no expected keys: {list(ctx.keys())}"


def test_precomputed_extended_data():
    """At least p53 should have extended precomputed data."""
    from src.utils import load_precomputed
    data = load_precomputed("p53_r248w")
    assert data is not None
    for key in ("structure_analysis", "flexibility", "pockets", "interpretation"):
        assert key in data, f"p53_r248w: missing extended key '{key}'"


# ===================================================================
# 3. QUERY PARSER
# ===================================================================

def test_fallback_parser_p53():
    from src.query_parser import _fallback_parse
    q = _fallback_parse("P53 R248W mutation - is it druggable?")
    assert q.protein_name == "TP53"
    assert q.mutation == "R248W"
    assert q.question_type == "druggability"


def test_fallback_parser_egfr():
    from src.query_parser import _fallback_parse
    q = _fallback_parse("EGFR T790M resistance mutation structure")
    assert "EGFR" in q.protein_name.upper()
    assert q.mutation == "T790M"


def test_fallback_parser_plain():
    from src.query_parser import _fallback_parse
    q = _fallback_parse("insulin structure")
    assert q.protein_name.upper() in ("INSULIN", "INS")


# ===================================================================
# 4. TRUST AUDITOR
# ===================================================================

def test_trust_audit_from_precomputed():
    from src.utils import load_precomputed
    from src.trust_auditor import build_trust_audit
    from src.models import ProteinQuery

    data = load_precomputed("p53_r248w")
    q = ProteinQuery(protein_name="TP53", mutation="R248W", question_type="druggability")
    ta = build_trust_audit(q, data["pdb"], data["confidence"])
    assert ta.confidence_score >= 0
    assert len(ta.regions) > 0
    assert len(ta.known_limitations) > 0


def test_residue_flags():
    from src.models import ProteinQuery
    from src.trust_auditor import get_residue_flags
    q = ProteinQuery(protein_name="TP53", mutation="R248W")
    flags = get_residue_flags(q, [247, 248, 249], [85.0, 45.0, 75.0])
    assert 248 in flags, "Mutation site R248 should be flagged"


def test_trust_annotations():
    from src.utils import build_trust_annotations
    annotations = build_trust_annotations(
        ["A", "A", "A"], [1, 2, 3], [95.0, 45.0, 75.0], {2: "Low confidence"},
    )
    assert len(annotations) == 3
    assert annotations[0]["color"] == "#0053D6"  # Very high
    assert annotations[1]["color"] == "#FF7D45"  # Very low
    assert "Low confidence" in annotations[1]["tooltip"]


# ===================================================================
# 5. INTERPRETER (fallback)
# ===================================================================

def test_fallback_interpretation():
    from src.interpreter import _fallback_interpretation
    from src.models import (
        ProteinQuery, TrustAudit, BioContext, RegionConfidence,
        DiseaseAssociation, DrugCandidate, LiteratureSummary,
    )
    q = ProteinQuery(protein_name="TP53", mutation="R248W", question_type="druggability")
    ta = TrustAudit(
        overall_confidence="medium", confidence_score=0.65,
        regions=[RegionConfidence(chain="A", start_residue=240, end_residue=260, avg_plddt=55.0,
                                  flag="Low confidence")],
        known_limitations=["IDRs not modeled"],
    )
    ctx = BioContext(
        disease_associations=[DiseaseAssociation(disease="Li-Fraumeni", score=0.95)],
        drugs=[DrugCandidate(name="APR-246", phase="Phase 3")],
        literature=LiteratureSummary(total_papers=5000, key_findings=["TP53 is tumor suppressor"]),
    )
    interp = _fallback_interpretation(q, ta, ctx)
    assert len(interp) > 100, f"Interpretation too short ({len(interp)} chars)"
    assert "TP53" in interp or "p53" in interp.lower()


# ===================================================================
# 6. STATISTICS ENGINE
# ===================================================================

def test_stat_ttest():
    from src.statistics_engine import run_ttest
    r = run_ttest([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert "error" not in r, r.get("error")
    assert r["p_val"] < 0.01
    assert "cohen_d" in r


def test_stat_paired_ttest():
    from src.statistics_engine import run_paired_ttest
    # Differences must have non-zero variance (not all identical)
    r = run_paired_ttest([1, 2, 3, 4, 5], [2.5, 3.1, 4.8, 5.2, 7.0])
    assert "error" not in r, r.get("error")
    assert "T" in r


def test_stat_mannwhitney():
    from src.statistics_engine import run_mannwhitney
    r = run_mannwhitney([1, 2, 3, 4, 5], [6, 7, 8, 9, 10])
    assert "error" not in r, r.get("error")
    assert "U" in r


def test_stat_wilcoxon():
    from src.statistics_engine import run_wilcoxon
    r = run_wilcoxon([1, 2, 3, 4, 5, 6], [2, 3, 4, 5, 6, 7])
    assert "error" not in r, r.get("error")
    assert "W" in r


def test_stat_anova():
    from src.statistics_engine import run_one_way_anova
    df = pd.DataFrame({
        "val": [1, 2, 3, 10, 11, 12, 20, 21, 22],
        "grp": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
    })
    r = run_one_way_anova(df, "val", "grp")
    assert "error" not in r, r.get("error")
    assert r["p_val"] < 0.01
    assert "eta_squared" in r
    assert r["posthoc_df"] is not None  # Significant → has post-hoc


def test_stat_kruskal():
    from src.statistics_engine import run_kruskal
    df = pd.DataFrame({
        "val": [1, 2, 3, 10, 11, 12, 20, 21, 22],
        "grp": ["A"] * 3 + ["B"] * 3 + ["C"] * 3,
    })
    r = run_kruskal(df, "val", "grp")
    assert "error" not in r, r.get("error")
    assert "H" in r


def test_stat_welch_anova_has_eta():
    from src.statistics_engine import run_welch_anova
    df = pd.DataFrame({
        "val": [1, 2, 3, 4, 10, 11, 12, 13],
        "grp": ["A"] * 4 + ["B"] * 4,
    })
    r = run_welch_anova(df, "val", "grp")
    assert "error" not in r, r.get("error")
    assert "eta_squared" in r, "Welch ANOVA must return eta_squared"
    assert r["eta_squared"] is not None
    assert r["eta_squared"] > 0


def test_stat_two_way_anova():
    from src.statistics_engine import run_two_way_anova
    df = pd.DataFrame({
        "val": np.random.randn(24),
        "fA": (["X"] * 6 + ["Y"] * 6) * 2,
        "fB": ["M"] * 12 + ["F"] * 12,
    })
    r = run_two_way_anova(df, "val", "fA", "fB")
    assert "error" not in r, r.get("error")
    assert "main_effect_a" in r
    assert "interaction" in r


def test_stat_pearson():
    from src.statistics_engine import run_pearson
    x = np.arange(20, dtype=float)
    y = x * 2 + np.random.normal(0, 0.5, 20)
    r = run_pearson(x, y)
    assert "error" not in r, r.get("error")
    assert r["r"] > 0.9


def test_stat_spearman():
    from src.statistics_engine import run_spearman
    r = run_spearman([1, 2, 3, 4, 5], [5, 4, 3, 2, 1])
    assert "error" not in r, r.get("error")
    assert r["r"] < -0.9


def test_stat_chi_square():
    from src.statistics_engine import run_chi_square
    df = pd.DataFrame({
        "a": ["yes"] * 30 + ["no"] * 70,
        "b": (["success"] * 20 + ["fail"] * 10 +
              ["success"] * 10 + ["fail"] * 60),
    })
    r = run_chi_square(df, "a", "b")
    assert "error" not in r, r.get("error")
    assert "chi2" in r
    assert "cramers_v" in r


def test_stat_fisher_exact():
    from src.statistics_engine import run_fisher_exact
    r = run_fisher_exact([[10, 2], [1, 9]])
    assert "error" not in r, r.get("error")
    assert "odds_ratio" in r
    assert "CI95_odds_ratio" in r


def test_stat_logistic_regression():
    from src.statistics_engine import run_logistic_regression
    np.random.seed(42)
    n = 100
    x1 = np.random.randn(n)
    x2 = np.random.randn(n)
    p = 1 / (1 + np.exp(-(0.5 + 1.5 * x1 - 0.8 * x2)))
    y = (np.random.rand(n) < p).astype(int)
    df = pd.DataFrame({"target": y, "x1": x1, "x2": x2})
    r = run_logistic_regression(df, "target", ["x1", "x2"])
    assert "error" not in r, r.get("error")
    assert "odds_ratios" in r
    assert "y_true" in r
    assert "y_pred_proba" in r


def test_stat_roc_curve():
    from src.statistics_engine import compute_roc_curve
    np.random.seed(42)
    y_true = np.array([0] * 50 + [1] * 50)
    y_scores = np.concatenate([
        np.random.normal(0.3, 0.2, 50),
        np.random.normal(0.7, 0.2, 50),
    ])
    r = compute_roc_curve(y_true, y_scores)
    assert "error" not in r, r.get("error")
    assert r["auc"] > 0.7
    assert "optimal_threshold" in r


def test_stat_bland_altman():
    from src.statistics_engine import compute_bland_altman
    np.random.seed(42)
    m1 = np.random.normal(100, 10, 50)
    m2 = m1 + np.random.normal(2, 3, 50)
    r = compute_bland_altman(m1, m2)
    assert "error" not in r, r.get("error")
    assert "mean_diff" in r
    assert "upper_loa" in r
    assert "lower_loa" in r
    assert "means" in r
    assert "diffs" in r


# --- Edge cases ---

def test_stat_ttest_zero_variance():
    from src.statistics_engine import run_ttest
    r = run_ttest([5, 5, 5], [5, 5, 5])
    assert "error" in r


def test_stat_ttest_too_few():
    from src.statistics_engine import run_ttest
    r = run_ttest([1, 2], [3, 4])
    assert "error" in r


def test_stat_multiple_correction_empty():
    from src.statistics_engine import apply_multiple_comparison_correction
    r = apply_multiple_comparison_correction([])
    assert r == [], f"Expected empty list, got {r}"


def test_stat_multiple_correction_normal():
    from src.statistics_engine import apply_multiple_comparison_correction
    r = apply_multiple_comparison_correction([0.01, 0.04, 0.06])
    assert len(r) == 3
    assert all(isinstance(v, float) for v in r)


def test_detect_column_types_boundary():
    from src.statistics_engine import detect_column_types
    # 80% numeric (4 out of 5) should classify as numeric
    df = pd.DataFrame({"col": [1, 2, 3, 4, "x"]})
    ct = detect_column_types(df)
    assert ct["col"] == "numeric", f"80% numeric should classify as numeric, got {ct['col']}"


def test_detect_column_types_below_boundary():
    from src.statistics_engine import detect_column_types
    # 60% numeric should NOT classify as numeric
    df = pd.DataFrame({"col": [1, 2, 3, "a", "b"]})
    ct = detect_column_types(df)
    assert ct["col"] != "numeric", f"60% numeric should not classify as numeric, got {ct['col']}"


def test_detect_column_types_empty():
    from src.statistics_engine import detect_column_types
    df = pd.DataFrame({"a": [None, None], "b": [1, 2]})
    ct = detect_column_types(df)
    assert ct["a"] == "empty"
    assert ct["b"] == "numeric"


# --- Curve fitting ---

def test_fit_michaelis_menten():
    from src.statistics_engine import fit_curve
    x = np.array([0.5, 1, 2, 5, 10, 20, 50, 100])
    y = 10 * x / (5 + x) + np.random.normal(0, 0.1, len(x))
    r = fit_curve(x, y, "Michaelis-Menten")
    assert r["converged"], r.get("message")
    assert r["r_squared"] > 0.95
    assert "Vmax" in r["params"]
    assert "Km" in r["params"]


def test_fit_4pl():
    from src.statistics_engine import fit_curve
    x = np.linspace(-3, 3, 20)
    y = 0 + (100 - 0) / (1 + 10 ** ((0 - x) * 1)) + np.random.normal(0, 2, 20)
    r = fit_curve(x, y, "4PL (Dose-Response)")
    assert r["converged"], r.get("message")
    assert r["r_squared"] > 0.9


def test_fit_linear():
    from src.statistics_engine import fit_curve
    x = np.arange(10, dtype=float)
    y = 2 * x + 3 + np.random.normal(0, 0.1, 10)
    r = fit_curve(x, y, "Linear")
    assert r["converged"], r.get("message")
    assert r["r_squared"] > 0.99


def test_fit_bands_finite():
    """Confidence/prediction bands must never be NaN or Inf."""
    from src.statistics_engine import fit_curve
    x = np.linspace(0.1, 10, 20)
    y = 5 * x / (1 + x) + np.random.normal(0, 0.1, 20)
    r = fit_curve(x, y, "Michaelis-Menten")
    assert r["converged"]
    for key in ("ci_lower", "ci_upper", "pi_lower", "pi_upper"):
        arr = np.array(r[key])
        assert np.all(np.isfinite(arr)), f"{key} has NaN/Inf values"


def test_fit_too_few_points():
    from src.statistics_engine import fit_curve
    r = fit_curve([1], [1], "Michaelis-Menten")
    assert not r["converged"]


def test_fit_all_25_equations():
    """Verify all 25 built-in equations can at least be invoked."""
    from src.statistics_engine import BUILTIN_EQUATIONS, fit_curve
    x = np.linspace(0.1, 10, 30)
    y = np.random.normal(5, 1, 30)
    for eq_name in BUILTIN_EQUATIONS:
        r = fit_curve(x, y, eq_name)
        assert "converged" in r or "error" in r, f"{eq_name}: returned {r.keys()}"


def test_fit_with_fixed_params():
    from src.statistics_engine import fit_curve
    x = np.linspace(0.1, 10, 20)
    y = 5 * x / (x + 2 * (1 + 1.0 / 3)) + np.random.normal(0, 0.2, 20)
    r = fit_curve(x, y, "Competitive Inhibition", fixed_param_values={"I_conc": 1.0})
    assert "converged" in r


# --- Survival ---

def test_kaplan_meier():
    from src.statistics_engine import run_kaplan_meier
    time = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    event = [1, 1, 0, 1, 0, 1, 1, 0, 1, 0]
    group = ["A", "A", "A", "A", "A", "B", "B", "B", "B", "B"]
    r = run_kaplan_meier(time, event, group)
    assert "error" not in r, r.get("error")
    assert "curves" in r
    assert "A" in r["curves"]
    assert "B" in r["curves"]
    assert "median_survival" in r


def test_logrank():
    from src.statistics_engine import run_logrank
    time = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    event = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    group = ["A", "A", "A", "A", "A", "B", "B", "B", "B", "B"]
    r = run_logrank(time, event, group)
    assert "error" not in r, r.get("error")
    assert "p_val" in r


def test_cox_regression():
    from src.statistics_engine import run_cox_regression
    np.random.seed(42)
    df = pd.DataFrame({
        "time": np.random.exponential(5, 50),
        "event": np.random.binomial(1, 0.7, 50),
        "age": np.random.normal(60, 10, 50),
        "biomarker": np.random.normal(0, 1, 50),
    })
    r = run_cox_regression(df, "time", "event", covariates=["age", "biomarker"])
    assert "error" not in r, r.get("error")
    assert "concordance" in r
    assert "hazard_ratios" in r


# --- Tier 2 ---

def test_pca():
    from src.statistics_engine import run_pca
    df = pd.DataFrame(np.random.randn(50, 5), columns=[f"f{i}" for i in range(5)])
    r = run_pca(df, n_components=2)
    assert "error" not in r, r.get("error")
    assert len(r["explained_variance_ratio"]) == 2
    assert "scores" in r


def test_kmeans():
    from src.statistics_engine import run_kmeans
    df = pd.DataFrame(np.random.randn(50, 3), columns=["a", "b", "c"])
    r = run_kmeans(df, max_k=5)
    assert "error" not in r, r.get("error")
    assert "chosen_k" in r
    assert "labels" in r


def test_multiple_regression():
    from src.statistics_engine import run_multiple_regression
    np.random.seed(42)
    x1 = np.random.randn(50)
    x2 = np.random.randn(50)
    y = 2 * x1 - 3 * x2 + np.random.normal(0, 0.5, 50)
    df = pd.DataFrame({"y": y, "x1": x1, "x2": x2})
    r = run_multiple_regression(df, "y", ["x1", "x2"])
    assert "error" not in r, r.get("error")
    assert r["r_squared"] > 0.8
    assert "y_true" in r
    assert "y_pred" in r
    assert "f_pvalue" in r


# ===================================================================
# 7. STATISTICS CHARTS
# ===================================================================

def test_chart_distribution():
    from src.statistics_charts import build_distribution_chart
    fig = build_distribution_chart(np.random.randn(100), "Test")
    assert fig is not None
    assert len(fig.data) >= 1


def test_chart_comparison():
    from src.statistics_charts import build_comparison_chart
    groups = {"A": np.random.randn(20), "B": np.random.randn(20) + 1}
    fig = build_comparison_chart(groups, "Value", p_value=0.03)
    assert fig is not None


def test_chart_scatter_fit():
    from src.statistics_charts import build_scatter_with_fit
    from src.statistics_engine import fit_curve
    x = np.linspace(0.1, 10, 20)
    y = 5 * x / (1 + x) + np.random.normal(0, 0.1, 20)
    result = fit_curve(x, y, "Michaelis-Menten")
    fig = build_scatter_with_fit(x, y, result, "X", "Y", "MM")
    assert fig is not None


def test_chart_residual():
    from src.statistics_charts import build_residual_plot
    fig = build_residual_plot(np.arange(20), np.random.randn(20))
    assert fig is not None


def test_chart_qq():
    from src.statistics_charts import build_qq_plot
    fig = build_qq_plot(np.random.randn(50))
    assert fig is not None


def test_chart_survival():
    from src.statistics_charts import build_survival_chart
    km = {
        "curves": {
            "A": {
                "timeline": [0, 1, 2, 3],
                "survival": [1.0, 0.9, 0.7, 0.5],
                "ci_lower": [1.0, 0.8, 0.5, 0.3],
                "ci_upper": [1.0, 1.0, 0.9, 0.7],
            },
        },
        "median_survival": {"A": 3.0},
    }
    fig = build_survival_chart(km)
    assert fig is not None


def test_chart_violin():
    from src.statistics_charts import build_violin_chart
    groups = {"X": np.random.randn(30), "Y": np.random.randn(30) + 2}
    fig = build_violin_chart(groups, "Score", p_value=0.001)
    assert fig is not None


def test_chart_correlation_heatmap():
    from src.statistics_charts import build_correlation_heatmap
    corr = pd.DataFrame([[1.0, 0.5], [0.5, 1.0]], columns=["a", "b"], index=["a", "b"])
    fig = build_correlation_heatmap(corr)
    assert fig is not None


def test_chart_slopegraph_normal():
    from src.statistics_charts import build_slopegraph
    fig = build_slopegraph(np.array([1, 2, 3]), np.array([2, 3, 4]), p_value=0.02)
    assert fig is not None
    assert len(fig.data) >= 3  # 3 individual + 1 mean


def test_chart_slopegraph_unequal():
    from src.statistics_charts import build_slopegraph
    fig = build_slopegraph(np.array([1, 2, 3]), np.array([4, 5]))
    assert fig is not None  # Should truncate, not crash


def test_chart_slopegraph_empty():
    from src.statistics_charts import build_slopegraph
    fig = build_slopegraph(np.array([]), np.array([]))
    assert fig is not None  # Should return placeholder


def test_chart_roc():
    from src.statistics_charts import build_roc_chart
    fig = build_roc_chart([0, 0.2, 0.5, 1.0], [0, 0.5, 0.8, 1.0], 0.85,
                          thresholds=[1.0, 0.6, 0.3, 0.0])
    assert fig is not None


def test_chart_roc_empty():
    from src.statistics_charts import build_roc_chart
    fig = build_roc_chart([], [], 0.5)
    assert fig is not None  # Should not crash


def test_chart_bland_altman():
    from src.statistics_charts import build_bland_altman_chart
    fig = build_bland_altman_chart({
        "means": [5, 6, 7], "diffs": [0.1, -0.2, 0.3],
        "mean_diff": 0.067, "upper_loa": 0.5, "lower_loa": -0.4,
    })
    assert fig is not None


def test_chart_bland_altman_missing_keys():
    from src.statistics_charts import build_bland_altman_chart
    fig = build_bland_altman_chart({"some_key": 1})
    assert fig is not None  # Should return placeholder, not crash


def test_chart_contingency():
    from src.statistics_charts import build_contingency_chart
    ct = pd.DataFrame({"yes": [10, 5], "no": [3, 12]}, index=["A", "B"])
    fig = build_contingency_chart(ct)
    assert fig is not None


def test_chart_interaction():
    from src.statistics_charts import build_interaction_plot
    df = pd.DataFrame({
        "y": np.random.randn(20),
        "fA": ["X"] * 10 + ["Y"] * 10,
        "fB": (["M"] * 5 + ["F"] * 5) * 2,
    })
    fig = build_interaction_plot(df, "y", "fA", "fB")
    assert fig is not None


def test_chart_pca_biplot():
    from src.statistics_charts import build_pca_biplot
    scores = [{"PC1": 1.0, "PC2": 0.5}, {"PC1": -1.0, "PC2": -0.5}]
    loadings = {"f1": [0.8, 0.1], "f2": [0.1, 0.9]}
    fig = build_pca_biplot(scores, loadings, ["f1", "f2"], [0.6, 0.3])
    assert fig is not None


def test_chart_scree():
    from src.statistics_charts import build_scree_plot
    fig = build_scree_plot([0.5, 0.3, 0.15, 0.05])
    assert fig is not None


def test_chart_elbow():
    from src.statistics_charts import build_elbow_plot
    fig = build_elbow_plot([2, 3, 4, 5], [100, 60, 40, 35])
    assert fig is not None


def test_chart_regression_diagnostics():
    from src.statistics_charts import build_regression_diagnostics
    y_true = np.array([1, 2, 3, 4, 5])
    y_pred = np.array([1.1, 2.0, 2.9, 4.1, 5.0])
    residuals = y_true - y_pred
    fig = build_regression_diagnostics(y_true, y_pred, residuals)
    assert fig is not None


# ===================================================================
# 8. UTILITY FUNCTIONS
# ===================================================================

def test_pdb_plddt_parsing():
    from src.utils import load_precomputed, parse_pdb_plddt
    data = load_precomputed("p53_r248w")
    chains, residues, scores = parse_pdb_plddt(data["pdb"])
    assert len(chains) > 0
    assert len(chains) == len(residues) == len(scores)
    assert all(0 <= s <= 100 for s in scores)


def test_region_confidence():
    from src.utils import compute_region_confidence
    chains = ["A"] * 40
    residues = list(range(1, 41))
    scores = [90.0] * 20 + [40.0] * 20
    regions = compute_region_confidence(chains, residues, scores)
    assert len(regions) >= 2
    high_region = next(r for r in regions if r["avg_plddt"] > 70)
    low_region = next(r for r in regions if r["avg_plddt"] < 50)
    assert high_region["flag"] is None
    assert low_region["flag"] is not None


def test_safe_json_encoder():
    from src.utils import safe_json_dumps
    data = {
        "int": np.int64(42),
        "float": np.float64(3.14),
        "array": np.array([1, 2, 3]),
        "bool": np.bool_(True),
    }
    j = safe_json_dumps(data)
    parsed = json.loads(j)
    assert parsed["int"] == 42
    assert abs(parsed["float"] - 3.14) < 0.001
    assert parsed["array"] == [1, 2, 3]
    assert parsed["bool"] is True


def test_trust_color_mapping():
    from src.utils import trust_to_color, trust_to_label
    assert trust_to_color(95) == "#0053D6"
    assert trust_to_color(80) == "#65CBF3"
    assert trust_to_color(55) == "#FFDB13"
    assert trust_to_color(30) == "#FF7D45"
    assert trust_to_label(95) == "Very High"
    assert trust_to_label(30) == "Very Low"


def test_svg_gather_data_pathogenic_positions_dict():
    from unittest.mock import patch

    from src.models import PredictionResult, ProteinQuery
    from src.svg_figures import gather_figure_data

    query = ProteinQuery(
        protein_name="TP53",
        mutation="R248W",
        question_type="druggability",
    )
    prediction = PredictionResult(
        pdb_content="ATOM",
        confidence_json={},
        plddt_per_residue=[90.0, 80.0, 70.0],
        chain_ids=["A", "A", "A"],
        residue_ids=[1, 2, 3],
        compute_source="precomputed",
    )
    fake_state = {
        "structure_analysis": {"residue_ids": [1, 2, 3], "sse_counts": {"a": 1, "b": 1, "c": 1}},
        "variant_data_TP53": {
            "total": 42,
            "pathogenic_count": 2,
            "pathogenic_positions": {248: ["R248W"], 249: ["R249S"]},
        },
        "interpretation": "test",
    }

    with patch("src.svg_figures.st.session_state", fake_state):
        gathered = gather_figure_data(query, prediction, trust_audit=None, bio_context=None)

    assert gathered["variants"]["total"] == 42
    assert gathered["variants"]["pathogenic_count"] == 2
    assert gathered["variants"]["pathogenic_positions"] == [248, 249]


def test_svg_gather_data_handles_none_structure_analysis():
    from unittest.mock import patch

    from src.models import PredictionResult, ProteinQuery
    from src.svg_figures import gather_figure_data

    query = ProteinQuery(
        protein_name="SPIKE",
        mutation=None,
        question_type="binding",
    )
    prediction = PredictionResult(
        pdb_content="ATOM",
        confidence_json={},
        plddt_per_residue=[82.0, 77.0],
        chain_ids=["A", "A"],
        residue_ids=[1, 2],
        compute_source="precomputed",
    )
    fake_state = {
        "structure_analysis": None,
        "variant_data_SPIKE": {},
        "interpretation": "",
    }

    with patch("src.svg_figures.st.session_state", fake_state):
        gathered = gather_figure_data(query, prediction, trust_audit=None, bio_context=None)

    assert gathered["n_residues"] == 2
    assert gathered["variants"] in (
        {},
        {"total": 0, "pathogenic_count": 0, "pathogenic_positions": []},
    )


def test_pdf_report_returns_bytes():
    from src.models import PredictionResult, ProteinQuery
    from src.pdf_report import generate_pdf_report

    query = ProteinQuery(
        protein_name="TP53",
        mutation="R248W",
        question_type="druggability",
    )
    prediction = PredictionResult(
        pdb_content=(
            "ATOM      1  CA  ALA A   1      11.104  13.207   9.173  1.00 90.00           C\n"
            "END\n"
        ),
        confidence_json={},
        plddt_per_residue=[90.0],
        chain_ids=["A"],
        residue_ids=[1],
        compute_source="precomputed",
    )

    pdf_bytes = generate_pdf_report(
        query=query,
        prediction=prediction,
        trust_audit=None,
        bio_context=None,
        interpretation="test",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000


# ===================================================================
# 9. COMPONENT IMPORT SMOKE TEST
# ===================================================================

def test_all_components_import():
    """Every component file should import without error."""
    import importlib
    component_dir = ROOT / "components"
    failures = []
    for pyfile in sorted(component_dir.glob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        module_name = f"components.{pyfile.stem}"
        try:
            importlib.import_module(module_name)
        except Exception as e:
            failures.append(f"{module_name}: {e}")
    assert not failures, f"Component import failures:\n" + "\n".join(failures)


def test_all_src_modules_import():
    """Every src/ module should import without error."""
    import importlib
    src_dir = ROOT / "src"
    failures = []
    for pyfile in sorted(src_dir.glob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        module_name = f"src.{pyfile.stem}"
        try:
            importlib.import_module(module_name)
        except ImportError as e:
            # Allow missing optional dependencies
            if "modal" in str(e).lower() or "dotenv" in str(e).lower():
                continue
            failures.append(f"{module_name}: {e}")
        except Exception as e:
            failures.append(f"{module_name}: {e}")
    assert not failures, f"Source import failures:\n" + "\n".join(failures)


# ===================================================================
# RUNNER
# ===================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("  LUMINOUS — Full Pipeline Test Suite")
    print("=" * 70)

    sections = [
        ("1. DATA MODELS & SERIALIZATION", [
            ("Create all models", test_models_create),
            ("Serialize / deserialize", test_models_serialize),
        ]),
        ("2. PRECOMPUTED DATA LOADING", [
            ("All 6 examples present", test_precomputed_all_present),
            ("PDB files have ATOM lines", test_precomputed_pdb_has_atoms),
            ("Confidence JSON keys", test_precomputed_confidence_keys),
            ("Context structure", test_precomputed_context_structure),
            ("Extended data (p53)", test_precomputed_extended_data),
        ]),
        ("3. QUERY PARSER", [
            ("Parse P53 R248W", test_fallback_parser_p53),
            ("Parse EGFR T790M", test_fallback_parser_egfr),
            ("Parse 'insulin'", test_fallback_parser_plain),
        ]),
        ("4. TRUST AUDITOR", [
            ("Build audit from precomputed", test_trust_audit_from_precomputed),
            ("Residue flags (mutation site)", test_residue_flags),
            ("Trust annotations", test_trust_annotations),
        ]),
        ("5. INTERPRETER (fallback)", [
            ("Fallback interpretation", test_fallback_interpretation),
        ]),
        ("6. STATISTICS ENGINE — Tests", [
            ("Independent t-test", test_stat_ttest),
            ("Paired t-test", test_stat_paired_ttest),
            ("Mann-Whitney U", test_stat_mannwhitney),
            ("Wilcoxon signed-rank", test_stat_wilcoxon),
            ("One-way ANOVA + post-hoc", test_stat_anova),
            ("Kruskal-Wallis", test_stat_kruskal),
            ("Welch's ANOVA (eta_squared)", test_stat_welch_anova_has_eta),
            ("Two-way ANOVA", test_stat_two_way_anova),
            ("Pearson correlation", test_stat_pearson),
            ("Spearman correlation", test_stat_spearman),
            ("Chi-square", test_stat_chi_square),
            ("Fisher's exact", test_stat_fisher_exact),
            ("Logistic regression", test_stat_logistic_regression),
            ("ROC curve + AUC", test_stat_roc_curve),
            ("Bland-Altman", test_stat_bland_altman),
        ]),
        ("6b. STATISTICS ENGINE — Edge Cases", [
            ("Zero variance → error", test_stat_ttest_zero_variance),
            ("Too few obs → error", test_stat_ttest_too_few),
            ("Empty p-value correction", test_stat_multiple_correction_empty),
            ("Normal p-value correction", test_stat_multiple_correction_normal),
            ("Column type 80% boundary", test_detect_column_types_boundary),
            ("Column type below boundary", test_detect_column_types_below_boundary),
            ("Column type empty col", test_detect_column_types_empty),
        ]),
        ("6c. STATISTICS ENGINE — Curve Fitting", [
            ("Michaelis-Menten fit", test_fit_michaelis_menten),
            ("4PL dose-response fit", test_fit_4pl),
            ("Linear fit", test_fit_linear),
            ("Bands always finite", test_fit_bands_finite),
            ("Too few points → no converge", test_fit_too_few_points),
            ("All 25 equations callable", test_fit_all_25_equations),
            ("Fixed params (Comp. Inhib.)", test_fit_with_fixed_params),
        ]),
        ("6d. STATISTICS ENGINE — Survival", [
            ("Kaplan-Meier", test_kaplan_meier),
            ("Log-rank test", test_logrank),
            ("Cox regression", test_cox_regression),
        ]),
        ("6e. STATISTICS ENGINE — Tier 2", [
            ("PCA", test_pca),
            ("K-means", test_kmeans),
            ("Multiple regression", test_multiple_regression),
        ]),
        ("7. STATISTICS CHARTS", [
            ("Distribution", test_chart_distribution),
            ("Comparison (box+bracket)", test_chart_comparison),
            ("Scatter + fit", test_chart_scatter_fit),
            ("Residual plot", test_chart_residual),
            ("Q-Q plot", test_chart_qq),
            ("Survival (KM)", test_chart_survival),
            ("Violin", test_chart_violin),
            ("Correlation heatmap", test_chart_correlation_heatmap),
            ("Slopegraph (normal)", test_chart_slopegraph_normal),
            ("Slopegraph (unequal)", test_chart_slopegraph_unequal),
            ("Slopegraph (empty)", test_chart_slopegraph_empty),
            ("ROC chart", test_chart_roc),
            ("ROC chart (empty)", test_chart_roc_empty),
            ("Bland-Altman chart", test_chart_bland_altman),
            ("Bland-Altman (missing keys)", test_chart_bland_altman_missing_keys),
            ("Contingency chart", test_chart_contingency),
            ("Interaction plot", test_chart_interaction),
            ("PCA biplot", test_chart_pca_biplot),
            ("Scree plot", test_chart_scree),
            ("Elbow plot", test_chart_elbow),
            ("Regression diagnostics", test_chart_regression_diagnostics),
        ]),
        ("8. UTILITY FUNCTIONS", [
            ("PDB pLDDT parsing", test_pdb_plddt_parsing),
            ("Region confidence", test_region_confidence),
            ("Safe JSON encoder", test_safe_json_encoder),
            ("Trust color mapping", test_trust_color_mapping),
            ("SVG gather data (pathogenic dict)", test_svg_gather_data_pathogenic_positions_dict),
            ("SVG gather data (None structure_analysis)", test_svg_gather_data_handles_none_structure_analysis),
            ("PDF report output type", test_pdf_report_returns_bytes),
        ]),
        ("9. IMPORT SMOKE TEST", [
            ("All components/ import", test_all_components_import),
            ("All src/ import", test_all_src_modules_import),
        ]),
    ]

    for section_name, tests in sections:
        print(f"\n  {section_name}")
        print("  " + "-" * 50)
        for name, func in tests:
            _run(name, func)

    print("\n" + "=" * 70)
    total = PASS + FAIL + SKIP
    print(f"  RESULTS: {PASS} passed, {FAIL} failed, {SKIP} skipped (of {total})")
    if FAIL:
        print(f"  STATUS: FAILED")
        sys.exit(1)
    else:
        print(f"  STATUS: ALL PASSING")
    print("=" * 70)
