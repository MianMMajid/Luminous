"""AI-powered insight visualizations — surfaces patterns a scientist couldn't see otherwise.

This is the "Scientific Data Visualization" hackathon category answer:
using AI + multi-source data to reveal hidden correlations between
structure confidence, pathogenicity, druggability, and clinical significance.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st

from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit


def render_insight_visualizations(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    """Render the AI-powered insight visualizations section."""
    st.markdown("### AI-Surfaced Insights")
    st.caption(
        "Cross-referencing structure prediction, variant pathogenicity, drug data, "
        "and literature to surface patterns a scientist couldn't see from any single source."
    )

    col1, col2 = st.columns(2)

    with col1:
        _render_risk_radar(query, trust_audit, bio_context)

    with col2:
        variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
        _render_confidence_pathogenicity_correlation(
            query, prediction, variant_data
        )

    # Disease association strength distribution
    if bio_context and bio_context.disease_associations:
        _render_disease_score_distribution(bio_context)

    # AI-narrated insight
    _render_ai_insight_narrative(query, prediction, trust_audit, bio_context)


def _render_risk_radar(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    """Protein Risk Radar — single-glance multi-dimensional risk assessment.

    No existing tool provides this: a radar chart showing how the protein
    scores across 6 dimensions that combine structural and clinical data.
    """
    st.markdown("#### Protein Risk Radar")

    # Compute dimension scores (0-100)
    # 1. Structural Confidence (from trust audit)
    structural_conf = trust_audit.confidence_score * 100

    # 2. Prediction Reliability (based on limitations count)
    lim_count = len(trust_audit.known_limitations)
    reliability = max(0, 100 - lim_count * 15)

    # 3. Clinical Significance (from disease associations)
    clinical_sig = 0
    if bio_context and bio_context.disease_associations:
        scores = [d.score for d in bio_context.disease_associations if d.score is not None]
        clinical_sig = min(100, (sum(scores) / max(len(scores), 1)) * 100) if scores else min(100, len(bio_context.disease_associations) * 20)

    # 4. Druggability (from drugs in pipeline)
    druggability = 0
    if bio_context and bio_context.drugs:
        phase_scores = {"approved": 100, "phase iii": 85, "phase ii": 65, "phase i": 45, "preclinical": 25}
        for drug in bio_context.drugs:
            phase = (drug.phase or "").lower()
            for key, score in phase_scores.items():
                if key in phase:
                    druggability = max(druggability, score)
                    break
            else:
                druggability = max(druggability, 20)

    # 5. Mutation Burden (from variant data)
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    mutation_burden = 0
    if variant_data:
        path_count = variant_data.get("pathogenic_count", 0)
        mutation_burden = min(100, path_count * 12)

    # 6. Literature Coverage (from literature data)
    lit_coverage = 0
    if bio_context and bio_context.literature.total_papers > 0:
        lit_coverage = min(100, bio_context.literature.total_papers * 0.7)

    categories = [
        "Structural\nConfidence",
        "Prediction\nReliability",
        "Clinical\nSignificance",
        "Druggability",
        "Mutation\nBurden",
        "Literature\nCoverage",
    ]
    values = [
        structural_conf,
        reliability,
        clinical_sig,
        druggability,
        mutation_burden,
        lit_coverage,
    ]

    fig = go.Figure()

    fig.add_trace(go.Scatterpolar(
        r=values + [values[0]],  # close the polygon
        theta=categories + [categories[0]],
        fill="toself",
        fillcolor="rgba(10, 132, 255, 0.2)",
        line=dict(color="#007AFF", width=2),
        marker=dict(size=6),
        hovertemplate="%{theta}: %{r:.0f}/100<extra></extra>",
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(visible=True, range=[0, 100], showticklabels=True,
                           tickfont=dict(size=9, color="rgba(60,60,67,0.6)"), gridcolor="rgba(0,0,0,0.08)"),
            angularaxis=dict(gridcolor="rgba(0,0,0,0.08)", tickfont=dict(size=10, color="rgba(60,60,67,0.6)")),
            bgcolor="rgba(0,0,0,0)",
        ),
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=350,
        margin=dict(t=30, b=30, l=60, r=60),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # Quick interpretation
    high_dims = [c.replace("\n", " ") for c, v in zip(categories, values) if v >= 70]
    low_dims = [c.replace("\n", " ") for c, v in zip(categories, values) if v < 40]
    if high_dims:
        st.caption(f"Strong: {', '.join(high_dims)}")
    if low_dims:
        st.caption(f"Gaps: {', '.join(low_dims)}")

    # Data provenance for each dimension
    sources_map = {
        "Structural Confidence": "Boltz-2 pTM score",
        "Prediction Reliability": "Boltz-2 limitation analysis",
        "Clinical Significance": "Open Targets / Disease associations",
        "Druggability": "ChEMBL / Open Targets drug pipeline",
        "Mutation Burden": "ClinVar pathogenic variant count",
        "Literature Coverage": "PubMed article count",
    }
    source_badges = " ".join(
        f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);'
        f'padding:1px 6px;border-radius:10px;font-size:0.82em;color:rgba(60,60,67,0.55)">'
        f'{dim}: {src}</span>'
        for dim, src in sources_map.items()
    )
    st.markdown(
        f'<div style="margin-top:4px">{source_badges}</div>',
        unsafe_allow_html=True,
    )


def _render_disease_score_distribution(bio_context: BioContext):
    """Horizontal bar chart of disease association scores — shows gradient of evidence strength."""
    diseases_with_scores = [
        d for d in bio_context.disease_associations if d.score is not None
    ]
    if not diseases_with_scores:
        return

    st.markdown("#### Disease Association Strength")
    st.caption(
        "Association scores from Open Targets — higher scores indicate stronger "
        "genetic and experimental evidence linking this protein to each disease."
    )

    # Sort by score descending
    diseases_with_scores.sort(key=lambda d: d.score, reverse=True)
    display = diseases_with_scores[:12]

    names = [d.disease for d in display]
    scores = [d.score for d in display]
    evidence = [d.evidence or "" for d in display]

    colors = []
    for s in scores:
        if s >= 0.8:
            colors.append("#FF3B30")
        elif s >= 0.6:
            colors.append("#FF9500")
        elif s >= 0.4:
            colors.append("#FF9500")
        elif s >= 0.2:
            colors.append("#FFCC00")
        else:
            colors.append("#8E8E93")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names,
        x=scores,
        orientation="h",
        marker_color=colors,
        text=[f"{s:.0%}" for s in scores],
        textposition="auto",
        hovertemplate="%{y}<br>Score: %{x:.2f}<br>%{customdata}<extra></extra>",
        customdata=evidence,
    ))

    fig.update_layout(
        xaxis_title="Association Score",
        xaxis_range=[0, 1.05],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=max(200, len(display) * 35 + 60),
        margin=dict(t=10, b=40, l=180, r=20),
        yaxis=dict(autorange="reversed"),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Data provenance
    st.markdown(
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);'
        'padding:1px 6px;border-radius:10px;font-size:0.82em;color:rgba(60,60,67,0.55)">'
        'Source: Open Targets Platform — genetic & experimental evidence</span>',
        unsafe_allow_html=True,
    )


def _render_confidence_pathogenicity_correlation(
    query: ProteinQuery,
    prediction: PredictionResult,
    variant_data: dict | None,
):
    """Confidence vs Pathogenicity correlation — the hidden insight.

    This visualization answers: "Are the clinically important residues
    in regions where we can trust the prediction?" Nobody shows this.
    Interactive threshold lets users test hypotheses in real time.
    """
    st.markdown("#### Confidence at Pathogenic Sites")

    if not variant_data or not variant_data.get("pathogenic_positions"):
        st.info("Load variant data to see this insight.")
        return

    if not prediction.plddt_per_residue or not prediction.residue_ids:
        st.info("No per-residue confidence data.")
        return

    # --- Interactive threshold control ---
    confidence_threshold = st.slider(
        "Confidence threshold (pLDDT)",
        min_value=30, max_value=95, value=70, step=5,
        help="Adjust the threshold to filter which risks are highlighted on the radar chart. Lower values show more potential risks.",
        key="insight_plddt_threshold",
    )

    pathogenic_pos = variant_data.get("pathogenic_positions", {})

    # Categorize residues (first chain only to avoid double-counting)
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
    path_confidences = []
    nonpath_confidences = []
    path_labels = []

    path_positions_int = set()
    for pos_key in pathogenic_pos:
        try:
            path_positions_int.add(int(pos_key))
        except (ValueError, TypeError):
            pass

    for i, (res_id, plddt) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
        if i >= len(prediction.chain_ids):
            break
        if first_chain is not None and prediction.chain_ids[i] != first_chain:
            continue
        if res_id in path_positions_int:
            path_confidences.append(plddt)
            names = pathogenic_pos.get(str(res_id), pathogenic_pos.get(res_id, []))
            path_labels.append(f"Pos {res_id}: {', '.join(names) if isinstance(names, list) else names}")
        else:
            nonpath_confidences.append(plddt)

    if not path_confidences:
        st.info("No pathogenic variant positions overlap with predicted residues.")
        return

    # Box plot comparison
    fig = go.Figure()

    fig.add_trace(go.Box(
        y=nonpath_confidences,
        name="Non-pathogenic<br>residues",
        marker_color="#007AFF",
        boxmean=True,
    ))

    fig.add_trace(go.Box(
        y=path_confidences,
        name="Pathogenic<br>variant sites",
        marker_color="#FF3B30",
        boxmean=True,
    ))

    # Add individual pathogenic points
    fig.add_trace(go.Scatter(
        x=["Pathogenic<br>variant sites"] * len(path_confidences),
        y=path_confidences,
        mode="markers+text",
        marker=dict(color="#FFCC00", size=8, symbol="diamond"),
        text=[lbl.split(":")[0] for lbl in path_labels],
        textposition="top center",
        textfont=dict(size=8),
        name="Individual sites",
        hovertext=path_labels,
        hovertemplate="%{hovertext}<br>pLDDT: %{y:.1f}<extra></extra>",
    ))

    # Dynamic threshold line
    fig.add_hline(
        y=confidence_threshold,
        line_dash="dash", line_color="#FF3B30", line_width=2,
        annotation_text=f"Threshold: {confidence_threshold}",
        annotation_position="top right",
        annotation_font_color="#FF3B30",
    )

    fig.update_layout(
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 105],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=350,
        margin=dict(t=30, b=50, l=50, r=20),
        showlegend=False,
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # --- Real-time recalculated stats based on threshold ---
    at_risk = [p for p in path_confidences if p < confidence_threshold]
    at_risk_pct = len(at_risk) / len(path_confidences) * 100 if path_confidences else 0
    nonpath_below = [p for p in nonpath_confidences if p < confidence_threshold]
    nonpath_pct = len(nonpath_below) / len(nonpath_confidences) * 100 if nonpath_confidences else 0

    stat_cols = st.columns(3)
    stat_cols[0].metric(
        "Pathogenic sites below threshold",
        f"{len(at_risk)}/{len(path_confidences)}",
        delta=f"{at_risk_pct:.0f}%",
        delta_color="inverse",
    )
    stat_cols[1].metric(
        "Non-pathogenic below threshold",
        f"{len(nonpath_below)}/{len(nonpath_confidences)}",
        delta=f"{nonpath_pct:.0f}%",
        delta_color="inverse",
    )
    enrichment = (at_risk_pct / nonpath_pct) if nonpath_pct > 0 else float("inf") if at_risk_pct > 0 else 1.0
    stat_cols[2].metric(
        "Risk enrichment",
        f"{enrichment:.1f}x" if enrichment < 100 else ">100x",
        help="How much more likely pathogenic sites are to fall below the threshold vs. non-pathogenic residues.",
    )

    # Dynamic insight narrative
    avg_path = sum(path_confidences) / len(path_confidences)
    avg_nonpath = sum(nonpath_confidences) / max(len(nonpath_confidences), 1)

    if at_risk_pct > 50:
        st.error(
            f"**{at_risk_pct:.0f}% of pathogenic sites** fall below pLDDT {confidence_threshold}. "
            f"Structural predictions at clinically critical positions are unreliable — "
            f"experimental validation is essential before clinical interpretation."
        )
    elif avg_path < avg_nonpath - 10:
        st.warning(
            f"Pathogenic sites have lower confidence "
            f"(avg {avg_path:.0f}) than non-pathogenic residues (avg {avg_nonpath:.0f}). "
            f"Clinical interpretations at these positions should be treated with extra caution."
        )
    elif avg_path > avg_nonpath + 5:
        st.success(
            f"Pathogenic sites are well-predicted "
            f"(avg pLDDT {avg_path:.0f} vs {avg_nonpath:.0f} overall). "
            f"Structural predictions at these clinically important positions are reliable."
        )
    else:
        st.info(
            f"Prediction confidence at pathogenic sites ({avg_path:.0f}) is comparable "
            f"to non-pathogenic residues ({avg_nonpath:.0f})."
        )


def _render_ai_insight_narrative(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    """Generate AI-narrated insight with actionable recommendations and data provenance."""
    st.markdown("#### Key Insights & Recommended Actions")

    insights = []
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")

    # Insight 1: Confidence distribution with action
    if prediction.plddt_per_residue:
        scores = prediction.plddt_per_residue
        very_low = sum(1 for s in scores if s < 50) / len(scores)
        high = sum(1 for s in scores if s >= 90) / len(scores)
        if very_low > 0.2:
            insights.append({
                "text": (
                    f"**{very_low:.0%} of residues** have very low confidence (pLDDT < 50). "
                    f"These regions may be intrinsically disordered or prediction failures."
                ),
                "action": "Validate with HDX-MS or NMR relaxation experiments to distinguish disorder from error.",
                "sources": ["Boltz-2 pLDDT scores"],
                "severity": "warning",
            })
        elif high > 0.7:
            insights.append({
                "text": (
                    f"**{high:.0%} of residues** have very high confidence (pLDDT > 90). "
                    f"This is a well-predicted structure suitable for computational analysis."
                ),
                "action": "Proceed with structure-based drug design or docking studies.",
                "sources": ["Boltz-2 pLDDT scores"],
                "severity": "success",
            })

    # Insight 2: Mutation at critical position
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in prediction.residue_ids:
                idx = prediction.residue_ids.index(mut_pos)
                score = prediction.plddt_per_residue[idx]

                # Check if at a known pathogenic position
                is_hotspot = False
                if variant_data and variant_data.get("pathogenic_positions"):
                    pp = variant_data["pathogenic_positions"]
                    is_hotspot = mut_pos in pp or str(mut_pos) in pp

                if score > 80:
                    text = (
                        f"Mutation {query.mutation} (position {mut_pos}) has "
                        f"**high confidence** (pLDDT {score:.0f})."
                    )
                    if is_hotspot:
                        text += " This is a **known pathogenic hotspot**."
                    insights.append({
                        "text": text,
                        "action": (
                            "Structural predictions here are reliable. "
                            "Use for binding site analysis or stability calculations (FoldX/Rosetta)."
                        ),
                        "sources": ["Boltz-2 pLDDT"] + (["ClinVar"] if is_hotspot else []),
                        "severity": "success" if not is_hotspot else "warning",
                    })
                elif score < 60:
                    insights.append({
                        "text": (
                            f"Mutation {query.mutation} (position {mut_pos}) has "
                            f"**low confidence** (pLDDT {score:.0f}). "
                            f"The predicted structure here may be inaccurate."
                        ),
                        "action": (
                            "Do NOT rely on this prediction for clinical decisions. "
                            "Obtain experimental structure (cryo-EM/X-ray) before interpreting."
                        ),
                        "sources": ["Boltz-2 pLDDT"],
                        "severity": "error",
                    })

    # Insight 3: Drug-structure connection
    if bio_context and bio_context.drugs and trust_audit.confidence_score > 0.7:
        approved = [d for d in bio_context.drugs if d.phase and "approved" in d.phase.lower()]
        trials = [d for d in bio_context.drugs if d.phase and "phase" in d.phase.lower()]
        if approved:
            drug_names = ", ".join(d.name for d in approved[:3])
            insights.append({
                "text": (
                    f"**{len(approved)} approved drug(s)** target {query.protein_name} ({drug_names}). "
                    f"Confidence ({trust_audit.confidence_score:.0%}) supports structural analysis."
                ),
                "action": (
                    "Use this structure for binding pose analysis. "
                    "Cross-reference mutation position with drug binding pocket residues."
                ),
                "sources": ["Open Targets", "ChEMBL", "Boltz-2"],
                "severity": "info",
            })
        elif trials:
            insights.append({
                "text": (
                    f"**{len(trials)} drug(s) in trials** target {query.protein_name}. "
                    f"Structure-guided optimization could leverage this prediction."
                ),
                "action": "Submit to BoltzGen (Tamarind Bio) for de novo binder design against this target.",
                "sources": ["Open Targets", "ChEMBL"],
                "severity": "info",
            })

    # Insight 4: Variant-drug therapeutic opportunity
    if variant_data and bio_context and bio_context.drugs:
        path_count = variant_data.get("pathogenic_count", 0)
        drug_count = len(bio_context.drugs)
        if path_count > 3 and drug_count > 0:
            insights.append({
                "text": (
                    f"**{path_count} pathogenic variants** + **{drug_count} drug candidates** "
                    f"= high-value therapeutic target with well-characterized genetic basis."
                ),
                "action": (
                    "Cross-reference variant positions with drug binding sites. "
                    "Resistance mutations near binding pockets are priority candidates for next-gen drug design."
                ),
                "sources": ["ClinVar", "Open Targets", "ChEMBL"],
                "severity": "info",
            })

    # Insight 5: Confidence-pathogenicity gap (cross-domain, unique to Luminous)
    if variant_data and variant_data.get("pathogenic_positions") and prediction.plddt_per_residue:
        path_plddts = []
        for pos_str in variant_data["pathogenic_positions"]:
            try:
                pos = int(pos_str)
                if pos in prediction.residue_ids:
                    idx = prediction.residue_ids.index(pos)
                    path_plddts.append(prediction.plddt_per_residue[idx])
            except (ValueError, TypeError):
                pass
        if path_plddts:
            below_70 = sum(1 for p in path_plddts if p < 70)
            if below_70 > len(path_plddts) * 0.5:
                insights.append({
                    "text": (
                        f"**{below_70}/{len(path_plddts)} pathogenic sites** have pLDDT < 70. "
                        f"The clinically important regions of this protein are the least well-predicted."
                    ),
                    "action": (
                        "This is a critical finding. Prioritize experimental structure determination "
                        "for the region around these pathogenic sites before using predictions clinically."
                    ),
                    "sources": ["Boltz-2 pLDDT", "ClinVar"],
                    "severity": "error",
                })

    # Render insights with provenance badges
    if insights:
        for ins in insights:
            severity = ins.get("severity", "info")
            render_fn = {"error": st.error, "warning": st.warning, "success": st.success, "info": st.info}.get(severity, st.info)

            render_fn(f"{ins['text']}\n\n**Next step:** {ins['action']}")

            # Data provenance badges
            sources = ins.get("sources", [])
            if sources:
                badges = " ".join(
                    f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);'
                    f'padding:2px 8px;border-radius:12px;font-size:0.82em;color:rgba(60,60,67,0.6)">'
                    f'{src}</span>'
                    for src in sources
                )
                st.markdown(f"Data sources: {badges}", unsafe_allow_html=True)
    else:
        st.info("Load more data (variants, biological context) to generate cross-domain insights.")
