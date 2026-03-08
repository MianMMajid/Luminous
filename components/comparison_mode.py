from __future__ import annotations

import json
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from src.models import (
    PredictionResult,
    ProteinQuery,
    RegionConfidence,
    TrustAudit,
)

_PROJECTS_DIR = Path("data/projects")


def render_comparison_mode(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Expander for comparing two protein variants side-by-side."""
    with st.expander("Compare Variants", expanded=False):
        st.markdown(
            '<div style="font-size:0.88rem;color:rgba(60,60,67,0.6);margin-bottom:12px">'
            "Load a second variant to compare pLDDT profiles, trust scores, "
            "and key metrics side-by-side."
            "</div>",
            unsafe_allow_html=True,
        )

        # Source selector
        source = st.radio(
            "Load comparison from:",
            ["Saved Project", "Precomputed Example"],
            horizontal=True,
            key="compare_source",
        )

        comparison = st.session_state.get("comparison_data")

        if source == "Saved Project":
            _load_from_project()
        else:
            _load_from_precomputed()

        comparison = st.session_state.get("comparison_data")
        if comparison is None:
            return

        # Side-by-side comparison
        st.divider()
        _render_side_by_side(query, prediction, trust_audit, comparison)


def _load_from_project():
    """Load comparison data from an uploaded or recent project file."""
    uploaded = st.file_uploader(
        "Upload project file for comparison",
        type=["json"],
        key="compare_upload",
        label_visibility="collapsed",
    )
    if uploaded is not None:
        try:
            data = json.loads(uploaded.read().decode("utf-8"))
            st.session_state["comparison_data"] = _parse_comparison(data)
            st.rerun()
        except Exception as e:
            st.error(f"Failed to load comparison: {e}")
            return

    # Also show recent projects
    if _PROJECTS_DIR.exists():
        project_files = sorted(
            _PROJECTS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True
        )[:5]
        if project_files:
            st.markdown("**Or select a recent project:**")
            for pf in project_files:
                if st.button(
                    pf.stem,
                    key=f"compare_recent_{pf.name}",
                    use_container_width=True,
                ):
                    try:
                        data = json.loads(pf.read_text())
                        st.session_state["comparison_data"] = _parse_comparison(data)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Failed to load: {e}")


def _load_from_precomputed():
    """Load comparison from precomputed examples."""
    examples = {
        "TP53 R248W": "p53_r248w",
        "BRCA1 C61G": "brca1_c61g",
        "EGFR T790M": "egfr_t790m",
        "Insulin": "insulin",
    }

    selected = st.selectbox(
        "Select example for comparison",
        options=list(examples.keys()),
        key="compare_example_select",
    )

    if st.button("Load Comparison", key="load_compare_btn", use_container_width=True):
        from src.utils import load_precomputed, parse_pdb_plddt

        example_key = examples[selected]
        precomputed = load_precomputed(example_key)
        if precomputed and precomputed.get("pdb"):
            confidence = precomputed.get("confidence", {})
            plddt_override = confidence.pop("plddt_per_residue", None)
            chain_override = confidence.pop("chain_ids", None)
            resid_override = confidence.pop("residue_ids", None)

            if plddt_override and chain_override and resid_override:
                pred = PredictionResult(
                    pdb_content=precomputed["pdb"],
                    confidence_json=confidence,
                    plddt_per_residue=plddt_override,
                    chain_ids=chain_override,
                    residue_ids=resid_override,
                    compute_source="precomputed",
                )
            else:
                chain_ids, residue_ids, plddt_scores = [], [], []
                try:
                    chain_ids, residue_ids, plddt_scores = parse_pdb_plddt(
                        precomputed["pdb"]
                    )
                except Exception:
                    pass
                pred = PredictionResult(
                    pdb_content=precomputed["pdb"],
                    confidence_json=confidence,
                    plddt_per_residue=plddt_scores,
                    chain_ids=chain_ids,
                    residue_ids=residue_ids,
                    compute_source="precomputed",
                )

            # Build trust audit for comparison
            from src.trust_auditor import build_trust_audit

            try:
                ta = build_trust_audit(
                    ProteinQuery(protein_name=selected.split()[0]),
                    pred.pdb_content,
                    pred.confidence_json,
                    chain_ids=pred.chain_ids or None,
                    residue_ids=pred.residue_ids or None,
                    plddt_scores=pred.plddt_per_residue or None,
                )
            except Exception:
                ta = None

            st.session_state["comparison_data"] = {
                "label": selected,
                "prediction": pred,
                "trust_audit": ta,
            }
            st.rerun()
        else:
            st.warning(
                f"No precomputed data found for {selected}. "
                f"Run a prediction for this variant in the **Search** tab first, "
                f"or try one of the example queries."
            )


def _parse_comparison(data: dict) -> dict:
    """Parse a project JSON file into comparison data."""
    result: dict = {"label": "Loaded Project"}

    # Extract label from query
    if "parsed_query" in data:
        q = data["parsed_query"]
        protein = q.get("protein_name", "Unknown")
        mutation = q.get("mutation", "")
        result["label"] = f"{protein} {mutation}".strip()

    # Prediction
    if "prediction_result" in data:
        result["prediction"] = PredictionResult(**data["prediction_result"])

    # Trust audit
    if "trust_audit" in data:
        ta = data["trust_audit"]
        if "regions" in ta:
            ta["regions"] = [RegionConfidence(**r) for r in ta["regions"]]
        result["trust_audit"] = TrustAudit(**ta)

    return result


def _render_side_by_side(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    comparison: dict,
):
    """Render side-by-side comparison of two variants."""
    comp_prediction: PredictionResult | None = comparison.get("prediction")
    comp_trust: TrustAudit | None = comparison.get("trust_audit")
    comp_label: str = comparison.get("label", "Comparison")

    current_label = f"{query.protein_name}"
    if query.mutation:
        current_label += f" {query.mutation}"

    st.markdown(
        f'<div style="text-align:center;font-size:1.1rem;font-weight:700;'
        f'margin-bottom:12px;color:#000000">'
        f'{current_label} &nbsp; vs &nbsp; {comp_label}</div>',
        unsafe_allow_html=True,
    )

    # Key metrics comparison
    if trust_audit and comp_trust:
        st.markdown("#### Key Metrics")
        cols = st.columns([1, 1])
        with cols[0]:
            st.markdown(
                f'<div class="glow-card" style="text-align:center">'
                f'<div style="font-weight:700;color:#007AFF;margin-bottom:6px">'
                f"{current_label}</div>"
                f'<div style="font-size:2rem;font-weight:800">'
                f"{trust_audit.confidence_score:.1%}</div>"
                f'<div style="color:rgba(60,60,67,0.6);font-size:0.85rem">Confidence</div>'
                f"</div>",
                unsafe_allow_html=True,
            )
        with cols[1]:
            st.markdown(
                f'<div class="glow-card" style="text-align:center">'
                f'<div style="font-weight:700;color:#34C759;margin-bottom:6px">'
                f"{comp_label}</div>"
                f'<div style="font-size:2rem;font-weight:800">'
                f"{comp_trust.confidence_score:.1%}</div>"
                f'<div style="color:rgba(60,60,67,0.6);font-size:0.85rem">Confidence</div>'
                f"</div>",
                unsafe_allow_html=True,
            )

        # Detailed metric comparison table
        metrics = [
            ("Overall Confidence", trust_audit.overall_confidence, comp_trust.overall_confidence),
            ("Score", f"{trust_audit.confidence_score:.1%}", f"{comp_trust.confidence_score:.1%}"),
            ("Residues", len(prediction.residue_ids), len(comp_prediction.residue_ids) if comp_prediction else "N/A"),
        ]
        if trust_audit.ptm is not None or (comp_trust and comp_trust.ptm is not None):
            metrics.append((
                "pTM",
                f"{trust_audit.ptm:.3f}" if trust_audit.ptm is not None else "N/A",
                f"{comp_trust.ptm:.3f}" if comp_trust.ptm is not None else "N/A",
            ))
        if trust_audit.iptm is not None or (comp_trust and comp_trust.iptm is not None):
            metrics.append((
                "ipTM",
                f"{trust_audit.iptm:.3f}" if trust_audit.iptm is not None else "N/A",
                f"{comp_trust.iptm:.3f}" if comp_trust.iptm is not None else "N/A",
            ))

        flagged_a = sum(1 for r in trust_audit.regions if r.flag)
        flagged_b = sum(1 for r in comp_trust.regions if r.flag) if comp_trust else 0
        metrics.append(("Flagged Regions", flagged_a, flagged_b))

        st.markdown("#### Comparison Table")
        header = f"| Metric | {current_label} | {comp_label} |\n|--------|--------|--------|\n"
        rows = "\n".join(
            f"| {m[0]} | {m[1]} | {m[2]} |" for m in metrics
        )
        st.markdown(header + rows)

    # Overlaid pLDDT chart
    st.markdown("#### pLDDT Profile Overlay")
    _render_plddt_overlay(
        prediction, comp_prediction, current_label, comp_label
    )

    # Difference highlighting
    if comp_prediction and prediction.plddt_per_residue and comp_prediction.plddt_per_residue:
        st.markdown("#### Confidence Difference")
        _render_difference_chart(
            prediction, comp_prediction, current_label, comp_label
        )

    # Clear comparison button
    if st.button("Clear Comparison", key="clear_compare", use_container_width=True):
        st.session_state.pop("comparison_data", None)
        st.rerun()


def _render_plddt_overlay(
    pred_a: PredictionResult,
    pred_b: PredictionResult | None,
    label_a: str,
    label_b: str,
):
    """Overlaid pLDDT line chart for two variants."""
    fig = go.Figure()

    if pred_a.plddt_per_residue and pred_a.residue_ids:
        fig.add_trace(
            go.Scatter(
                x=pred_a.residue_ids,
                y=pred_a.plddt_per_residue,
                mode="lines",
                name=label_a,
                line=dict(color="#007AFF", width=2),
                hovertemplate=f"{label_a}<br>Residue %{{x}}<br>pLDDT: %{{y:.1f}}<extra></extra>",
            )
        )

    if pred_b and pred_b.plddt_per_residue and pred_b.residue_ids:
        fig.add_trace(
            go.Scatter(
                x=pred_b.residue_ids,
                y=pred_b.plddt_per_residue,
                mode="lines",
                name=label_b,
                line=dict(color="#34C759", width=2),
                hovertemplate=f"{label_b}<br>Residue %{{x}}<br>pLDDT: %{{y:.1f}}<extra></extra>",
            )
        )

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 100],
        template="plotly_white",
        height=350,
        margin=dict(t=10, b=40, l=50, r=20),
        legend=dict(orientation="h", y=1.1),
        shapes=[
            dict(
                type="line",
                y0=t,
                y1=t,
                x0=0,
                x1=1,
                xref="paper",
                line=dict(color=c, width=1, dash="dash"),
            )
            for t, c in [(90, "#007AFF"), (70, "#5AC8FA"), (50, "#FFCC00")]
        ],
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_difference_chart(
    pred_a: PredictionResult,
    pred_b: PredictionResult,
    label_a: str,
    label_b: str,
):
    """Show per-residue pLDDT difference between two variants."""
    # Align by residue IDs (use the intersection)
    set_a = dict(zip(pred_a.residue_ids, pred_a.plddt_per_residue))
    set_b = dict(zip(pred_b.residue_ids, pred_b.plddt_per_residue))
    common = sorted(set(set_a.keys()) & set(set_b.keys()))

    if not common:
        st.info("No overlapping residues to compare.")
        return

    diffs = [set_a[r] - set_b[r] for r in common]
    colors = ["#FF3B30" if abs(d) > 15 else "#FF9500" if abs(d) > 5 else "#D1D1D6" for d in diffs]

    fig = go.Figure(
        go.Bar(
            x=common,
            y=diffs,
            marker_color=colors,
            hovertemplate=(
                "Residue %{x}<br>"
                f"pLDDT diff ({label_a} - {label_b}): %{{y:.1f}}<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title=f"pLDDT Difference ({label_a} - {label_b})",
        template="plotly_white",
        height=250,
        margin=dict(t=10, b=40, l=50, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Summary of biggest differences
    abs_diffs = [(r, d) for r, d in zip(common, diffs)]
    abs_diffs.sort(key=lambda x: abs(x[1]), reverse=True)
    top_diffs = abs_diffs[:5]

    if top_diffs and abs(top_diffs[0][1]) > 5:
        st.markdown("**Largest divergences:**")
        for res, diff in top_diffs:
            direction = "higher" if diff > 0 else "lower"
            color = "#FF3B30" if abs(diff) > 15 else "#FF9500"
            st.markdown(
                f'<span style="color:{color};font-weight:600">Residue {res}:</span> '
                f'{label_a} is {abs(diff):.1f} points {direction} than {label_b}',
                unsafe_allow_html=True,
            )
