"""Disorder Region Detector — flags where AlphaFold may be hallucinating structure.

AlphaFold predicts 'spurious structural order' in intrinsically disordered regions.
~30% of human proteins have significant disorder. No tool flags this distinction:
low pLDDT can mean (a) genuine disorder, (b) prediction failure, or (c) flexible
but structured region. This panel detects likely disorder and warns users.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.models import PredictionResult, ProteinQuery, TrustAudit


def render_disorder_detection(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render the disorder region detection panel."""
    if not prediction.plddt_per_residue or not prediction.residue_ids:
        return

    # Use first chain only to avoid duplicates in multi-chain complexes
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
    res_ids = []
    scores = []
    chains = []
    for i, rid in enumerate(prediction.residue_ids):
        if i >= len(prediction.chain_ids) or i >= len(prediction.plddt_per_residue):
            break
        if first_chain is None or prediction.chain_ids[i] == first_chain:
            res_ids.append(rid)
            scores.append(prediction.plddt_per_residue[i])
            chains.append(prediction.chain_ids[i])

    if len(res_ids) < 5:
        return  # Too few residues for meaningful analysis

    # Detect disorder regions
    disorder_regions = _detect_disorder_regions(res_ids, scores)
    low_conf_regions = _detect_low_confidence_regions(res_ids, scores)

    # Only show if there's something interesting to report
    if not disorder_regions and not low_conf_regions:
        return

    st.markdown("### Structure Confidence Audit")
    st.caption(
        "Identifying regions where the prediction may be unreliable — "
        "distinguishing genuine intrinsic disorder from prediction failures."
    )

    # Summary metrics
    total = len(scores)
    disorder_residues = set()
    for r in disorder_regions:
        disorder_residues.update(range(r["start"], r["end"] + 1))
    low_conf_residues = set()
    for r in low_conf_regions:
        low_conf_residues.update(range(r["start"], r["end"] + 1))

    # Residues actually in our data that fall in these ranges
    disorder_count = sum(1 for r in res_ids if r in disorder_residues)
    low_conf_count = sum(1 for r in res_ids if r in low_conf_residues and r not in disorder_residues)
    high_conf_count = total - disorder_count - low_conf_count

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Residues", total)
    col2.metric("High Confidence", high_conf_count, delta=f"{high_conf_count/total:.0%}")
    col3.metric("Likely Disordered", disorder_count,
                delta=f"{disorder_count/total:.0%}" if disorder_count > 0 else None,
                delta_color="off")
    col4.metric("Low Confidence", low_conf_count,
                delta=f"{low_conf_count/total:.0%}" if low_conf_count > 0 else None,
                delta_color="inverse")

    # Confidence classification chart
    _render_classification_chart(res_ids, scores, disorder_regions, low_conf_regions, query)

    # Region details
    if disorder_regions:
        _render_disorder_details(disorder_regions, trust_audit)

    if low_conf_regions:
        _render_low_confidence_details(low_conf_regions)


def _detect_disorder_regions(
    res_ids: list[int],
    scores: list[float],
    min_run: int = 5,
    plddt_threshold: float = 50.0,
) -> list[dict]:
    """Detect likely intrinsically disordered regions.

    Criteria for likely disorder (not just low confidence):
    - Run of >= min_run consecutive residues with pLDDT < threshold
    - Located at N/C terminus OR has very low average pLDDT (< 40)
    """
    if not res_ids:
        return []

    regions = []
    min_res = min(res_ids)
    max_res = max(res_ids)

    run_start = None
    run_scores: list[float] = []

    for i, (rid, score) in enumerate(zip(res_ids, scores)):
        if score < plddt_threshold:
            if run_start is None:
                run_start = rid
                run_scores = []
            run_scores.append(score)
        else:
            if run_start is not None and len(run_scores) >= min_run:
                avg = sum(run_scores) / len(run_scores)
                run_end = res_ids[i - 1]

                # Determine if likely disorder vs. just low confidence
                is_terminal = (run_start <= min_res + 20) or (run_end >= max_res - 20)
                is_very_low = avg < 40

                if is_terminal or is_very_low:
                    regions.append({
                        "start": run_start,
                        "end": run_end,
                        "length": len(run_scores),
                        "avg_plddt": round(avg, 1),
                        "classification": "likely_disorder",
                        "reason": (
                            "Terminal region with very low confidence"
                            if is_terminal
                            else "Extended region with very low confidence (avg pLDDT < 40)"
                        ),
                    })

            run_start = None
            run_scores = []

    # Handle run at end of sequence
    if run_start is not None and len(run_scores) >= min_run:
        avg = sum(run_scores) / len(run_scores)
        run_end = res_ids[-1]
        is_terminal = (run_start <= min_res + 20) or (run_end >= max_res - 20)
        is_very_low = avg < 40

        if is_terminal or is_very_low:
            regions.append({
                "start": run_start,
                "end": run_end,
                "length": len(run_scores),
                "avg_plddt": round(avg, 1),
                "classification": "likely_disorder",
                "reason": (
                    "Terminal region with very low confidence"
                    if is_terminal
                    else "Extended region with very low confidence (avg pLDDT < 40)"
                ),
            })

    return regions


def _detect_low_confidence_regions(
    res_ids: list[int],
    scores: list[float],
    min_run: int = 3,
    plddt_threshold: float = 60.0,
) -> list[dict]:
    """Detect regions with low confidence that are NOT classified as disorder."""
    if not res_ids:
        return []

    regions = []
    run_start = None
    run_scores: list[float] = []

    for i, (rid, score) in enumerate(zip(res_ids, scores)):
        if score < plddt_threshold:
            if run_start is None:
                run_start = rid
                run_scores = []
            run_scores.append(score)
        else:
            if run_start is not None and len(run_scores) >= min_run:
                avg = sum(run_scores) / len(run_scores)
                run_end = res_ids[i - 1]
                regions.append({
                    "start": run_start,
                    "end": run_end,
                    "length": len(run_scores),
                    "avg_plddt": round(avg, 1),
                    "classification": "low_confidence",
                    "reason": "Internal low-confidence region — may be flexible loop or prediction uncertainty",
                })
            run_start = None
            run_scores = []

    if run_start is not None and len(run_scores) >= min_run:
        avg = sum(run_scores) / len(run_scores)
        run_end = res_ids[-1]
        regions.append({
            "start": run_start,
            "end": run_end,
            "length": len(run_scores),
            "avg_plddt": round(avg, 1),
            "classification": "low_confidence",
            "reason": "Low-confidence region — may be flexible loop or prediction uncertainty",
        })

    return regions


def _render_classification_chart(
    res_ids: list[int],
    scores: list[float],
    disorder_regions: list[dict],
    low_conf_regions: list[dict],
    query: ProteinQuery,
):
    """Render the confidence classification chart with disorder annotation."""
    disorder_set = set()
    for r in disorder_regions:
        disorder_set.update(range(r["start"], r["end"] + 1))
    low_conf_set = set()
    for r in low_conf_regions:
        low_conf_set.update(range(r["start"], r["end"] + 1))

    # Classify each residue
    colors = []
    categories = []
    for rid, score in zip(res_ids, scores):
        if rid in disorder_set:
            colors.append("#AF52DE")  # Purple for disorder
            categories.append("Likely Disordered")
        elif rid in low_conf_set:
            colors.append("#FF7D45")  # Orange for low confidence
            categories.append("Low Confidence")
        elif score >= 90:
            colors.append("#0053D6")
            categories.append("Very High")
        elif score >= 70:
            colors.append("#65CBF3")
            categories.append("High")
        elif score >= 50:
            colors.append("#FFDB13")
            categories.append("Moderate")
        else:
            colors.append("#FF7D45")
            categories.append("Low")

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=res_ids,
        y=scores,
        marker_color=colors,
        hovertemplate="Residue %{x}<br>pLDDT: %{y:.1f}<br>%{text}<extra></extra>",
        text=categories,
    ))

    # Add disorder region shading
    for r in disorder_regions:
        fig.add_vrect(
            x0=r["start"] - 0.5, x1=r["end"] + 0.5,
            fillcolor="rgba(175, 82, 222, 0.1)",
            line_width=0,
            annotation_text="Likely Disordered",
            annotation_position="top",
            annotation_font_size=9,
            annotation_font_color="#AF52DE",
        )

    # Mutation marker
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation.upper())
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in res_ids:
                idx = res_ids.index(mut_pos)
                fig.add_trace(go.Scatter(
                    x=[mut_pos],
                    y=[scores[idx]],
                    mode="markers",
                    marker=dict(color="#FF3B30", size=12, symbol="star"),
                    name=query.mutation,
                    hovertemplate=f"{query.mutation}<br>pLDDT: {scores[idx]:.1f}<extra></extra>",
                ))

    # Confidence thresholds
    fig.add_hline(y=70, line_color="#65CBF3", line_dash="dash", opacity=0.3)
    fig.add_hline(y=50, line_color="#FFDB13", line_dash="dot", opacity=0.3)

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 105],
        template="plotly_white",
        height=300,
        margin=dict(t=30, b=40, l=50, r=20),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Legend
    legend_items = [
        ("#0053D6", "Very High (>90)"),
        ("#65CBF3", "High (70-90)"),
        ("#FFDB13", "Moderate (50-70)"),
        ("#FF7D45", "Low (<50)"),
        ("#AF52DE", "Likely Disordered"),
    ]
    legend_cols = st.columns(len(legend_items))
    for col, (color, label) in zip(legend_cols, legend_items):
        col.markdown(
            f'<div style="display:flex;align-items:center;gap:4px">'
            f'<div style="width:12px;height:12px;background:{color};border-radius:2px"></div>'
            f'<span style="font-size:0.8em">{label}</span></div>',
            unsafe_allow_html=True,
        )


def _render_disorder_details(disorder_regions: list[dict], trust_audit: TrustAudit):
    """Render details about detected disorder regions."""
    st.markdown("**Likely Intrinsically Disordered Regions**")

    for r in disorder_regions:
        st.markdown(
            f'<div style="background:#F2F2F7;padding:10px;border-radius:6px;'
            f'border-left:3px solid #AF52DE;margin-bottom:8px">'
            f'<strong>Residues {r["start"]}-{r["end"]}</strong> '
            f'({r["length"]} residues, avg pLDDT {r["avg_plddt"]})<br>'
            f'<span style="font-size:0.88em;color:rgba(60,60,67,0.6)">{r["reason"]}</span></div>',
            unsafe_allow_html=True,
        )

    st.warning(
        "Disordered regions may represent genuine biological disorder (functional flexibility) "
        "rather than prediction failure. AlphaFold assigns low confidence to these regions "
        "but may still predict a specific 3D arrangement — this predicted structure should "
        "NOT be trusted in disordered segments. These regions may adopt structure only upon "
        "binding to partners."
    )


def _render_low_confidence_details(low_conf_regions: list[dict]):
    """Render details about low-confidence (non-disorder) regions."""
    with st.expander(f"Low Confidence Regions ({len(low_conf_regions)})"):
        for r in low_conf_regions:
            st.markdown(
                f"- **Residues {r['start']}-{r['end']}** "
                f"({r['length']} residues, avg pLDDT {r['avg_plddt']}) — "
                f"{r['reason']}"
            )
        st.info(
            "These internal low-confidence regions may represent flexible loops, "
            "hinge regions, or genuine prediction uncertainty. Consider experimental "
            "validation (HDX-MS, NMR relaxation) to distinguish flexibility from error."
        )
