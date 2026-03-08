"""Structural Insights — surfaces insights a scientist couldn't see otherwise.

Computes and visualizes properties from 3D coordinates that raw pLDDT
or sequence data alone cannot reveal: solvent accessibility (buried vs
exposed), mutation-to-binding-pocket distances, 3D spatial clustering
of pathogenic variants, secondary structure context, and confidence
distribution analysis.

Hackathon category: Scientific Data Visualization
"""
from __future__ import annotations

import re

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.models import PredictionResult, ProteinQuery


def render_structural_insights(
    query: ProteinQuery,
    prediction: PredictionResult,
):
    """Render the structural insights panel with computed 3D properties."""
    if not prediction.pdb_content:
        return

    st.markdown("### Structural Insights from 3D Coordinates")
    _INSIGHT_CAPTIONS = {
        "structure": "How the protein folds — buried vs. exposed residues, "
                     "secondary structure, and backbone geometry.",
        "mutation_impact": f"Structural context for **{query.mutation or 'this mutation'}** — "
                           "burial, packing, 3D proximity to other pathogenic variants.",
        "druggability": "Binding pocket accessibility, surface exposure, and "
                        "structural features relevant to drug design.",
        "binding": "Interface properties — surface exposure, packing density, "
                   "and contact networks at the binding interface.",
    }
    st.caption(_INSIGHT_CAPTIONS.get(
        query.question_type,
        "Properties computed directly from atomic coordinates — "
        "revealing buried vs. exposed residues and structural context.",
    ))

    # Get variant and pocket data
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    pathogenic_positions = {}
    if variant_data and variant_data.get("pathogenic_positions"):
        for pos_key, names in variant_data["pathogenic_positions"].items():
            try:
                pathogenic_positions[int(pos_key)] = names
            except (ValueError, TypeError):
                pass

    # Get pocket residues from resistance DB
    pocket_residues = _get_pocket_residues(query.protein_name)

    # Parse mutation position
    mutation_pos = None
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mutation_pos = int(m.group(1))

    # Run structural analysis (use precomputed if available)
    cache_key = f"struct_analysis_{query.protein_name}_{query.mutation}"
    analysis = st.session_state.get(cache_key)
    if analysis is None:
        try:
            from src.structure_analysis import analyze_structure
            first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
            analysis = analyze_structure(
                prediction.pdb_content,
                mutation_pos=mutation_pos,
                variant_positions=pathogenic_positions or None,
                pocket_residues=pocket_residues,
                first_chain=first_chain,
            )
            st.session_state[cache_key] = analysis
            # Also store for residue dashboard
            st.session_state["structure_analysis"] = analysis
        except Exception as e:
            st.warning(f"Structural analysis failed: {e}")
            return

    # ── Render insights with progressive disclosure ──
    # Always visible: key metrics + primary visualizations
    _render_mutation_structural_context(analysis, query, prediction)

    # Primary: SASA + confidence (always relevant)
    col1, col2 = st.columns(2)
    with col1:
        _render_sasa_profile(analysis, query, mutation_pos)
    with col2:
        _render_confidence_distribution(prediction)

    # Primary: 3D distances (when mutation present — directly answers "how close?")
    if mutation_pos:
        _render_3d_distance_analysis(analysis, query)

    if pathogenic_positions and len(pathogenic_positions) >= 2:
        _render_3d_clustering(analysis)

    # Primary: Multi-Track Protein Map (the showpiece, always visible)
    _render_multi_track_map(analysis, prediction, mutation_pos, pathogenic_positions)

    # Cross-Insight Analysis (progressively disclosed)
    with st.expander("Conservation × Depth Analysis", expanded=bool(mutation_pos)):
        _render_conservation_depth_scatter(
            prediction, query, mutation_pos, pathogenic_positions, pocket_residues,
        )
        if mutation_pos and pocket_residues:
            _render_communication_path(prediction, query, mutation_pos, pocket_residues)

    # Contact & Packing (detail on demand)
    has_contact = "contact_map" in analysis
    has_packing = "packing_density" in analysis
    if has_contact or has_packing:
        with st.expander("Contact Map & Packing Density"):
            col1, col2 = st.columns(2)
            with col1:
                if has_contact:
                    _render_contact_map(analysis, pathogenic_positions, mutation_pos)
            with col2:
                if has_packing:
                    _render_packing_density(analysis, mutation_pos, pathogenic_positions)

    # Backbone Geometry & Network (detail on demand)
    has_rama = "ramachandran" in analysis
    has_network = "network_centrality" in analysis
    if has_rama or has_network:
        with st.expander("Backbone Geometry & Network Centrality"):
            col1, col2 = st.columns(2)
            with col1:
                if has_rama:
                    _render_ramachandran(analysis, mutation_pos, pathogenic_positions)
            with col2:
                if has_network:
                    _render_network_centrality(analysis, mutation_pos, pathogenic_positions)

    # Surface Properties (detail on demand, query-relevant)
    if query.question_type in ("druggability", "binding", "structure"):
        with st.expander("Surface Hydrophobic Patches"):
            _render_hydrophobic_patches(prediction, query, mutation_pos, pocket_residues)


def _get_pocket_residues(protein_name: str) -> list[int]:
    """Get binding pocket residues from resistance DB if available."""
    try:
        from components.drug_resistance import _RESISTANCE_DB
        data = _RESISTANCE_DB.get(protein_name.upper(), {})
        return data.get("binding_pocket_residues", [])
    except ImportError:
        return []


def _render_mutation_structural_context(
    analysis: dict, query: ProteinQuery, prediction: PredictionResult,
):
    """Show key structural metrics for the mutation site."""
    if not query.mutation:
        # Show general structure summary
        sse = analysis.get("sse_counts", {})
        total_res = len(analysis.get("residue_ids", []))
        buried = len(analysis.get("buried_residues", []))
        exposed = len(analysis.get("exposed_residues", []))

        cols = st.columns(5)
        cols[0].metric("Total Residues", total_res)
        cols[1].metric("α-Helix", f"{sse.get('a', 0)} res",
                       delta=f"{sse.get('a', 0)/max(total_res,1):.0%}")
        cols[2].metric("β-Sheet", f"{sse.get('b', 0)} res",
                       delta=f"{sse.get('b', 0)/max(total_res,1):.0%}")
        cols[3].metric("Buried", f"{buried} res",
                       delta=f"{buried/max(total_res,1):.0%}")
        cols[4].metric("Exposed", f"{exposed} res",
                       delta=f"{exposed/max(total_res,1):.0%}")
        return

    # Mutation-specific context
    sasa = analysis.get("mutation_sasa")
    is_buried = analysis.get("mutation_is_buried")
    sse_code = analysis.get("mutation_sse", "c")
    pocket_dist = analysis.get("mutation_to_pocket_min_distance")
    in_pocket = analysis.get("mutation_in_pocket", False)

    sse_labels = {"a": "α-Helix", "b": "β-Sheet", "c": "Loop/Coil"}
    sse_label = sse_labels.get(sse_code, "Unknown")

    cols = st.columns(4)

    # 1. Buried vs Exposed
    if sasa is not None:
        burial_label = "BURIED" if is_buried else "EXPOSED"
        burial_color = "#FF3B30" if is_buried else "#34C759"
        cols[0].markdown(
            f'<div style="text-align:center;background:#F2F2F7;padding:10px;border-radius:8px;'
            f'border:2px solid {burial_color}">'
            f'<div style="font-size:0.78em;color:rgba(60,60,67,0.6)">Solvent Accessibility</div>'
            f'<div style="font-size:1.5em;font-weight:800;color:{burial_color}">{burial_label}</div>'
            f'<div style="font-size:0.82em;color:rgba(60,60,67,0.6)">SASA: {sasa:.1f} Å²</div></div>',
            unsafe_allow_html=True,
        )

    # 2. Secondary Structure
    # Mol* standard secondary structure colors
    sse_colors = {"α-Helix": "#FF0080", "β-Sheet": "#FFC800", "Loop/Coil": "#808080"}
    sse_color = sse_colors.get(sse_label, "#888")
    cols[1].markdown(
        f'<div style="text-align:center;background:#F2F2F7;padding:10px;border-radius:8px;'
        f'border:1px solid {sse_color}">'
        f'<div style="font-size:0.78em;color:rgba(60,60,67,0.6)">Local Structure</div>'
        f'<div style="font-size:1.5em;font-weight:800;color:{sse_color}">{sse_label}</div>'
        f'<div style="font-size:0.82em;color:rgba(60,60,67,0.6)">{query.mutation} at pos {analysis.get("residue_ids", [0])[-1] if not analysis.get("residue_ids") else ""}</div></div>',
        unsafe_allow_html=True,
    )

    # 3. Distance to binding pocket
    if pocket_dist is not None:
        pocket_color = "#FF3B30" if in_pocket else "#34C759" if pocket_dist > 15 else "#FF9500"
        pocket_label = f"{pocket_dist:.1f} Å"
        pocket_status = "IN POCKET" if in_pocket else "NEAR POCKET" if pocket_dist < 15 else "DISTANT"
        cols[2].markdown(
            f'<div style="text-align:center;background:#F2F2F7;padding:10px;border-radius:8px;'
            f'border:1px solid {pocket_color}">'
            f'<div style="font-size:0.78em;color:rgba(60,60,67,0.6)">Distance to Drug Pocket</div>'
            f'<div style="font-size:1.5em;font-weight:800;color:{pocket_color}">{pocket_label}</div>'
            f'<div style="font-size:0.82em;color:{pocket_color}">{pocket_status}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        cols[2].metric("Drug Pocket", "No data",
                       help="No curated binding pocket residues available for this protein.")

    # 4. Mechanism inference
    if sasa is not None:
        if is_buried:
            mechanism = "Destabilizing"
            mech_detail = "Buried mutation likely disrupts protein fold stability"
            mech_color = "#FF3B30"
        elif in_pocket if pocket_dist is not None else False:
            mechanism = "Drug Resistance"
            mech_detail = "Surface mutation in binding pocket may alter drug binding"
            mech_color = "#FF9500"
        else:
            mechanism = "Interaction"
            mech_detail = "Surface mutation may disrupt protein-protein or DNA interactions"
            mech_color = "#007AFF"
        cols[3].markdown(
            f'<div style="text-align:center;background:#F2F2F7;padding:10px;border-radius:8px;'
            f'border:1px solid {mech_color}">'
            f'<div style="font-size:0.78em;color:rgba(60,60,67,0.6)">Predicted Mechanism</div>'
            f'<div style="font-size:1.3em;font-weight:800;color:{mech_color}">{mechanism}</div>'
            f'<div style="font-size:0.75em;color:rgba(60,60,67,0.6)">{mech_detail}</div></div>',
            unsafe_allow_html=True,
        )

    # Interpretation callout
    if sasa is not None:
        if is_buried and sse_code == "a":
            st.error(
                f"**{query.mutation} is buried inside an α-helix** (SASA {sasa:.1f} Å²). "
                f"This is a high-impact structural position — mutations here typically "
                f"destabilize the protein fold. Predict ΔΔG with FoldX or Rosetta to quantify."
            )
        elif is_buried and sse_code == "b":
            st.error(
                f"**{query.mutation} is buried in a β-sheet** (SASA {sasa:.1f} Å²). "
                f"β-sheet core mutations often cause aggregation or misfolding."
            )
        elif is_buried:
            st.warning(
                f"**{query.mutation} is buried** (SASA {sasa:.1f} Å²) in a loop region. "
                f"May affect core packing. Validate with thermal stability assay (DSF)."
            )
        elif pocket_dist is not None and in_pocket:
            st.warning(
                f"**{query.mutation} is surface-exposed in the drug binding pocket** "
                f"({pocket_dist:.1f} Å from nearest pocket residue). "
                f"This position directly contacts drug molecules — likely affects drug sensitivity."
            )

    # Data provenance
    st.markdown(
        '<div style="margin-top:4px">'
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;'
        'border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">'
        'SASA: biotite Shrake-Rupley algorithm on Boltz-2 coordinates</span> '
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;'
        'border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">'
        'SSE: biotite DSSP-like annotation</span> '
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;'
        'border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">'
        'Distance: Cα-Cα Euclidean from PDB coordinates</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_sasa_profile(analysis: dict, query: ProteinQuery, mutation_pos: int | None):
    """Render per-residue SASA profile with buried/exposed coloring."""
    sasa_data = analysis.get("sasa_per_residue", {})
    if not sasa_data:
        return

    st.markdown("#### Solvent Accessibility Profile")
    st.caption("Buried residues (< 25 Å²) are shown in red. Mutations at buried sites disrupt fold stability.")

    res_ids = sorted(sasa_data.keys())
    sasa_vals = [sasa_data[r] for r in res_ids]

    colors = ["#FF3B30" if s < 25 else "#34C759" if s > 60 else "#FF9500" for s in sasa_vals]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=res_ids,
        y=sasa_vals,
        marker_color=colors,
        hovertemplate="Res %{x}<br>SASA: %{y:.1f} Å²<br>%{text}<extra></extra>",
        text=["Buried" if s < 25 else "Exposed" if s > 60 else "Partial" for s in sasa_vals],
    ))

    # Burial threshold
    fig.add_hline(y=25, line_dash="dash", line_color="#FF6B6B", line_width=1.5,
                  annotation_text="Buried threshold", annotation_position="right",
                  annotation_font_size=9)

    # Mark mutation
    if mutation_pos and mutation_pos in sasa_data:
        fig.add_trace(go.Scatter(
            x=[mutation_pos], y=[sasa_data[mutation_pos]],
            mode="markers+text",
            marker=dict(color="#FFCC00", size=14, symbol="star",
                        line=dict(color="#FF3B30", width=2)),
            text=[query.mutation or ""],
            textposition="top center",
            textfont=dict(size=10, color="#FFCC00"),
            name=query.mutation or "Mutation",
            hovertemplate=f"{query.mutation}<br>SASA: {sasa_data[mutation_pos]:.1f} Å²<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="SASA (Å²)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=300,
        margin=dict(t=10, b=40, l=50, r=20),
        showlegend=False,
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_confidence_distribution(prediction: PredictionResult):
    """Render pLDDT distribution histogram — reveals bimodal predictions."""
    if not prediction.plddt_per_residue:
        return

    st.markdown("#### Confidence Distribution")
    st.caption("Shape reveals prediction quality: bimodal = mixed domain quality, left-skewed = disorder.")

    scores = prediction.plddt_per_residue

    # Create histogram with AlphaFold color bins
    bins = [0, 50, 70, 90, 100]
    bin_colors = ["#FF7D45", "#FFDB13", "#65CBF3", "#0053D6"]
    bin_labels = ["Very Low\n(<50)", "Low\n(50-70)", "High\n(70-90)", "Very High\n(>90)"]

    counts = []
    for i in range(len(bins) - 1):
        count = sum(1 for s in scores if bins[i] <= s < bins[i + 1])
        if i == len(bins) - 2:  # include 100 in last bin
            count = sum(1 for s in scores if bins[i] <= s <= bins[i + 1])
        counts.append(count)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=bin_labels,
        y=counts,
        marker_color=bin_colors,
        text=[f"{c/len(scores):.0%}" for c in counts],
        textposition="auto",
        hovertemplate="%{x}<br>Count: %{y}<br>%{text}<extra></extra>",
    ))

    fig.update_layout(
        yaxis_title="Residue Count",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=300,
        margin=dict(t=10, b=40, l=50, r=20),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Interpretation
    very_low_frac = sum(1 for s in scores if s < 50) / len(scores)
    very_high_frac = sum(1 for s in scores if s >= 90) / len(scores)

    if very_low_frac > 0.3 and very_high_frac > 0.3:
        st.info(
            f"**Bimodal distribution** — {very_high_frac:.0%} very high + {very_low_frac:.0%} very low. "
            f"This protein has well-predicted domains alongside disordered or poorly predicted regions."
        )
    elif very_high_frac > 0.7:
        st.success(f"**High-quality prediction** — {very_high_frac:.0%} of residues have pLDDT > 90.")
    elif very_low_frac > 0.4:
        st.warning(
            f"**Low-confidence prediction** — {very_low_frac:.0%} of residues below pLDDT 50. "
            f"Structure may contain significant disorder or prediction errors."
        )


def _render_3d_distance_analysis(analysis: dict, query: ProteinQuery):
    """Render mutation-to-variant and mutation-to-pocket 3D distances."""
    var_dists = analysis.get("mutation_to_variant_distances", [])
    pocket_dists = analysis.get("mutation_to_pocket_distances", [])

    if not var_dists and not pocket_dists:
        return

    st.markdown("#### 3D Distance Analysis")
    st.caption(
        "Euclidean distances from mutation site to pathogenic variants and drug binding pocket "
        "— computed from 3D Cα coordinates. Variants far in sequence may be close in 3D space."
    )

    if var_dists:
        # Scatter: sequence distance vs 3D distance
        fig = go.Figure()

        seq_dists = [v["distance_seq"] for v in var_dists]
        d3d_dists = [v["distance_3d"] for v in var_dists]
        names = [v["name"] for v in var_dists]

        fig.add_trace(go.Scatter(
            x=seq_dists,
            y=d3d_dists,
            mode="markers+text",
            marker=dict(
                color=["#FF3B30" if d < 10 else "#FF9500" if d < 20 else "#007AFF"
                       for d in d3d_dists],
                size=12,
                symbol="diamond",
                line=dict(color="rgba(0,0,0,0.2)", width=1),
            ),
            text=names,
            textposition="top center",
            textfont=dict(size=9),
            hovertemplate=(
                "%{text}<br>"
                "Sequence distance: %{x} residues<br>"
                "3D distance: %{y:.1f} Å<extra></extra>"
            ),
        ))

        # Diagonal reference line (if 3D distance < sequence distance, variants are closer in space)
        max_val = max(max(seq_dists), max(d3d_dists)) if seq_dists else 100
        fig.add_trace(go.Scatter(
            x=[0, max_val], y=[0, max_val],
            mode="lines",
            line=dict(color="#555", dash="dot", width=1),
            showlegend=False,
            hoverinfo="skip",
        ))

        # Proximity zone
        fig.add_hrect(y0=0, y1=10, fillcolor="rgba(255,69,58,0.08)", line_width=0)

        fig.update_layout(
            xaxis_title="Sequence Distance (residues)",
            yaxis_title="3D Distance (Å)",
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            font_color="#000000",
            height=350,
            margin=dict(t=10, b=40, l=50, r=20),
            showlegend=False,
            xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
            yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Highlight hidden spatial clusters
        close_in_3d = [v for v in var_dists if v["distance_3d"] < 10]
        hidden = [v for v in var_dists if v["distance_seq"] > 20 and v["distance_3d"] < 10]

        if hidden:
            st.error(
                "**Hidden spatial proximity detected!** "
                + " | ".join(
                    f"{v['name']} is {v['distance_seq']} residues away in sequence "
                    f"but only **{v['distance_3d']} Å** away in 3D"
                    for v in hidden
                )
                + ". These variants cluster on the same structural surface despite being distant in sequence."
            )
        elif close_in_3d:
            st.warning(
                f"**{len(close_in_3d)} pathogenic variants** within 10 Å of {query.mutation} in 3D: "
                + ", ".join(f"{v['name']} ({v['distance_3d']} Å)" for v in close_in_3d)
            )

    # Pocket distance details
    if pocket_dists:
        st.markdown("**Nearest binding pocket residues:**")
        pocket_html = " → ".join(
            f'<span style="background:#F2F2F7;padding:2px 8px;border-radius:4px;'
            f'border:1px solid {"#FF3B30" if d < 8 else "#FF9500" if d < 15 else "rgba(0,0,0,0.06)"};'
            f'font-size:0.85em">'
            f'Res {r}: <b>{d:.1f} Å</b></span>'
            for r, d in pocket_dists
        )
        st.markdown(pocket_html, unsafe_allow_html=True)


def _render_3d_clustering(analysis: dict):
    """Render 3D spatial clustering of pathogenic variants."""
    pairwise = analysis.get("variant_pairwise_distances", [])
    hidden = analysis.get("hidden_spatial_clusters", [])

    if not pairwise:
        return

    st.markdown("#### Pathogenic Variant 3D Clustering")
    st.caption(
        "Pairwise 3D distances between all pathogenic variants. "
        "Variants close in 3D but far in sequence reveal functional surface hotspots."
    )

    # Build a distance matrix visualization
    positions = set()
    for p in pairwise:
        positions.add(p["pos1"])
        positions.add(p["pos2"])
    positions = sorted(positions)

    if len(positions) < 2:
        return

    # Create name lookup
    name_lookup = {}
    for p in pairwise:
        name_lookup[p["pos1"]] = p["name1"]
        name_lookup[p["pos2"]] = p["name2"]

    labels = [f"{name_lookup.get(p, '?')} ({p})" for p in positions]

    # Build distance matrix
    n = len(positions)
    matrix = [[0.0] * n for _ in range(n)]
    for p in pairwise:
        i = positions.index(p["pos1"])
        j = positions.index(p["pos2"])
        matrix[i][j] = p["distance_3d"]
        matrix[j][i] = p["distance_3d"]

    # Custom colorscale: close (red) → mid (yellow) → far (blue)
    fig = go.Figure(data=go.Heatmap(
        z=matrix,
        x=labels,
        y=labels,
        colorscale=[
            [0.0, "#FF3B30"],
            [0.15, "#FF7D45"],
            [0.3, "#FFDB13"],
            [0.6, "#65CBF3"],
            [1.0, "#0053D6"],
        ],
        text=[[f"{v:.1f} Å" for v in row] for row in matrix],
        texttemplate="%{text}",
        textfont=dict(size=10),
        hovertemplate="%{x} ↔ %{y}<br>3D Distance: %{z:.1f} Å<extra></extra>",
        colorbar=dict(title="Distance (Å)", tickfont=dict(size=10)),
    ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=max(250, n * 45 + 80),
        margin=dict(t=10, b=80, l=120, r=20),
        xaxis=dict(tickangle=-30),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Hidden clusters callout
    if hidden:
        st.error(
            f"**{len(hidden)} hidden spatial cluster(s) detected** — variant pairs "
            f"distant in sequence (>20 residues apart) but close in 3D (<10 Å). "
            f"These define a shared functional surface:"
        )
        for h in hidden:
            st.markdown(
                f'- **{h["name1"]}** (pos {h["pos1"]}) ↔ **{h["name2"]}** (pos {h["pos2"]}): '
                f'sequence distance = {h["distance_seq"]} residues, '
                f'3D distance = **{h["distance_3d"]} Å**'
            )


# ─── NEW: Multi-Track Protein Map ───────────────────────────────────

def _render_multi_track_map(
    analysis: dict,
    prediction: PredictionResult,
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
):
    """Genome-browser-style multi-track protein map (Mut-Map, BIB 2024)."""
    res_ids = analysis.get("residue_ids", [])
    if len(res_ids) < 3:
        return

    st.markdown("#### Multi-Track Protein Map")
    st.caption(
        "Genome-browser-style view combining secondary structure, prediction confidence, "
        "solvent accessibility, packing density, and variant positions along the protein sequence."
    )

    sse_data = analysis.get("sse_per_residue", {})
    sasa_data = analysis.get("sasa_per_residue", {})
    packing = analysis.get("packing_density", {})
    plddt_scores = prediction.plddt_per_residue or []
    plddt_res = prediction.residue_ids or []

    # Build pLDDT lookup
    plddt_map: dict[int, float] = {}
    if plddt_scores and plddt_res:
        for i, rid in enumerate(plddt_res):
            if i < len(plddt_scores):
                plddt_map[rid] = plddt_scores[i]

    n_tracks = 3  # SSE + pLDDT + SASA always
    if packing:
        n_tracks += 1
    heights = [0.12] + [0.28] * (n_tracks - 1)
    titles = ["Secondary Structure", "pLDDT Confidence", "Solvent Accessibility"]
    if packing:
        titles.append("Packing Density")

    fig = make_subplots(
        rows=n_tracks, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=heights,
        subplot_titles=titles,
    )

    # ── Track 1: SSE ribbon ──
    # Mol* standard secondary structure colors
    sse_colors = {"a": "#FF0080", "b": "#FFC800", "c": "#808080"}
    sse_labels = {"a": "α-Helix", "b": "β-Sheet", "c": "Coil"}
    for rid in res_ids:
        code = str(sse_data.get(rid, "c")).strip()
        if code not in sse_colors:
            code = "c"
        fig.add_trace(go.Bar(
            x=[rid], y=[1], marker_color=sse_colors[code],
            hovertemplate=f"Res {rid}: {sse_labels.get(code, 'Coil')}<extra></extra>",
            showlegend=False, width=1.0,
        ), row=1, col=1)
    fig.update_yaxes(visible=False, row=1, col=1)

    # ── Track 2: pLDDT ──
    plddt_vals = [plddt_map.get(r, 0) for r in res_ids]
    plddt_colors = [
        "#0053D6" if v >= 90 else "#65CBF3" if v >= 70 else "#FFDB13" if v >= 50 else "#FF7D45"
        for v in plddt_vals
    ]
    fig.add_trace(go.Bar(
        x=res_ids, y=plddt_vals, marker_color=plddt_colors,
        hovertemplate="Res %{x}<br>pLDDT: %{y:.1f}<extra></extra>",
        showlegend=False,
    ), row=2, col=1)
    fig.update_yaxes(title_text="pLDDT", range=[0, 100], row=2, col=1)

    # ── Track 3: SASA ──
    sasa_vals = [sasa_data.get(r, 0) for r in res_ids]
    sasa_colors = ["#FF3B30" if s < 25 else "#34C759" if s > 60 else "#FF9500" for s in sasa_vals]
    fig.add_trace(go.Bar(
        x=res_ids, y=sasa_vals, marker_color=sasa_colors,
        hovertemplate="Res %{x}<br>SASA: %{y:.1f} Å²<extra></extra>",
        showlegend=False,
    ), row=3, col=1)
    fig.update_yaxes(title_text="SASA (Å²)", row=3, col=1)

    # ── Track 4: Packing Density (if available) ──
    if packing:
        pack_vals = [packing.get(r, 0) for r in res_ids]
        max_pack = max(pack_vals) if pack_vals else 1
        pack_colors = [
            "#FF3B30" if v > max_pack * 0.8 else "#FF9500" if v > max_pack * 0.5
            else "#007AFF" for v in pack_vals
        ]
        fig.add_trace(go.Bar(
            x=res_ids, y=pack_vals, marker_color=pack_colors,
            hovertemplate="Res %{x}<br>Cβ neighbors (12Å): %{y}<extra></extra>",
            showlegend=False,
        ), row=4, col=1)
        fig.update_yaxes(title_text="Neighbors", row=4, col=1)

    # ── Variant markers (vertical lines on all tracks) ──
    if pathogenic_positions:
        for vpos in pathogenic_positions:
            if vpos in set(res_ids):
                for row in range(1, n_tracks + 1):
                    fig.add_vline(
                        x=vpos, line_dash="dot", line_color="#E00000",
                        line_width=1, opacity=0.6, row=row, col=1,
                    )

    # ── Mutation marker ──
    if mutation_pos and mutation_pos in set(res_ids):
        for row in range(1, n_tracks + 1):
            fig.add_vline(
                x=mutation_pos, line_dash="solid", line_color="#FFCC00",
                line_width=2, opacity=0.8, row=row, col=1,
            )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=120 + n_tracks * 110,
        margin=dict(t=30, b=40, l=60, r=20),
    )
    # Set x-axis title only on bottom track
    fig.update_xaxes(title_text="Residue Number", row=n_tracks, col=1)
    for row in range(1, n_tracks):
        fig.update_xaxes(title_text="", row=row, col=1)

    st.plotly_chart(fig, use_container_width=True)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:-8px">'
        '<span style="font-size:0.72em;color:#FF0080">■ α-Helix</span>'
        '<span style="font-size:0.72em;color:#FFC800">■ β-Sheet</span>'
        '<span style="font-size:0.72em;color:#808080">■ Coil</span>'
        '<span style="font-size:0.72em;color:#E00000">┆ Pathogenic variant</span>'
        '<span style="font-size:0.72em;color:#FFCC00">│ Query mutation</span>'
        '</div>',
        unsafe_allow_html=True,
    )


# ─── NEW: Contact Map ──────────────────────────────────────────────

def _render_contact_map(
    analysis: dict,
    pathogenic_positions: dict[int, list[str]],
    mutation_pos: int | None,
):
    """Cα–Cα contact map heatmap with pathogenic variant overlay (GoFold, Frontiers 2024)."""
    dist_matrix = analysis.get("contact_map")
    res_list = analysis.get("contact_map_residues", [])
    if dist_matrix is None or len(res_list) < 3:
        return

    st.markdown("#### Contact Map")
    st.caption(
        "Cα–Cα pairwise distance matrix. Dark regions show contacts (<8 Å). "
        "Pathogenic variants marked in red reveal which structural contacts a mutation disrupts."
    )

    # Subsample if too many residues for readable heatmap
    step = max(1, len(res_list) // 300)
    if step > 1:
        idx = list(range(0, len(res_list), step))
        sub_res = [res_list[i] for i in idx]
        sub_mat = dist_matrix[np.ix_(idx, idx)]
    else:
        sub_res = res_list
        sub_mat = dist_matrix

    # Cap distances for better color contrast
    display_mat = np.clip(sub_mat, 0, 40)

    labels = [str(r) for r in sub_res]

    fig = go.Figure(data=go.Heatmap(
        z=display_mat,
        x=labels,
        y=labels,
        colorscale=[
            [0.0, "#0053D6"],
            [0.2, "#65CBF3"],
            [0.4, "#FFDB13"],
            [0.7, "#FF7D45"],
            [1.0, "#F2F2F7"],
        ],
        zmin=0, zmax=40,
        hovertemplate="Res %{x} ↔ Res %{y}<br>Distance: %{z:.1f} Å<extra></extra>",
        colorbar=dict(title="Dist (Å)", tickfont=dict(size=9)),
    ))

    # Mark pathogenic variant positions
    sub_set = set(sub_res)
    path_in_map = [p for p in pathogenic_positions if p in sub_set]
    if path_in_map:
        path_labels = [str(p) for p in path_in_map]
        fig.add_trace(go.Scatter(
            x=path_labels, y=path_labels,
            mode="markers",
            marker=dict(color="#FF3B30", size=8, symbol="x",
                        line=dict(color="rgba(0,0,0,0.2)", width=1)),
            name="Pathogenic",
            hovertemplate="Pathogenic: Res %{x}<extra></extra>",
        ))

    # Mark mutation
    if mutation_pos and mutation_pos in sub_set:
        fig.add_trace(go.Scatter(
            x=[str(mutation_pos)], y=[str(mutation_pos)],
            mode="markers",
            marker=dict(color="#FFCC00", size=12, symbol="star",
                        line=dict(color="#FF3B30", width=1.5)),
            name="Mutation",
            hovertemplate=f"Mutation: Res {mutation_pos}<extra></extra>",
        ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=400,
        margin=dict(t=10, b=40, l=50, r=20),
        xaxis=dict(title="Residue", tickangle=-45,
                   nticks=min(20, len(sub_res))),
        yaxis=dict(title="Residue", autorange="reversed",
                   nticks=min(20, len(sub_res))),
    )
    st.plotly_chart(fig, use_container_width=True)


# ─── NEW: Packing Density ──────────────────────────────────────────

def _render_packing_density(
    analysis: dict,
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
):
    """Local packing density profile — Cβ neighbour count within 12 Å (PNAS)."""
    packing = analysis.get("packing_density", {})
    if len(packing) < 3:
        return

    st.markdown("#### Local Packing Density")
    st.caption(
        "Cβ neighbours within 12 Å per residue. Mutations at densely packed sites "
        "create voids or steric clashes. Glycine uses Cα."
    )

    res_ids = sorted(packing.keys())
    vals = [packing[r] for r in res_ids]
    mean_pack = sum(vals) / len(vals) if vals else 0

    colors = []
    for r in res_ids:
        if mutation_pos and r == mutation_pos:
            colors.append("#FFCC00")
        elif r in pathogenic_positions:
            colors.append("#FF3B30")
        else:
            v = packing[r]
            if v > mean_pack * 1.3:
                colors.append("#FF3B30")
            elif v > mean_pack * 0.7:
                colors.append("#007AFF")
            else:
                colors.append("#5AC8FA")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=res_ids, y=vals, marker_color=colors,
        hovertemplate="Res %{x}<br>Cβ neighbors: %{y}<extra></extra>",
    ))
    fig.add_hline(y=mean_pack, line_dash="dash", line_color="#888",
                  annotation_text=f"Mean: {mean_pack:.0f}",
                  annotation_position="right", annotation_font_size=9)

    if mutation_pos and mutation_pos in packing:
        fig.add_trace(go.Scatter(
            x=[mutation_pos], y=[packing[mutation_pos]],
            mode="markers", marker=dict(color="#FFCC00", size=14, symbol="star",
                                        line=dict(color="#FF3B30", width=2)),
            showlegend=False,
            hovertemplate=f"Mutation: {packing[mutation_pos]} neighbors<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="Cβ Neighbors (12 Å)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=300,
        margin=dict(t=10, b=40, l=50, r=20),
        showlegend=False,
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Interpretation
    if mutation_pos and mutation_pos in packing:
        mp = packing[mutation_pos]
        if mp > mean_pack * 1.3:
            st.warning(
                f"**Densely packed site** — {mp} Cβ neighbors (mean: {mean_pack:.0f}). "
                f"Mutations here are likely to cause steric clashes or cavity formation."
            )
        elif mp < mean_pack * 0.5:
            st.info(
                f"**Loosely packed site** — {mp} Cβ neighbors (mean: {mean_pack:.0f}). "
                f"This position has room for side-chain substitutions."
            )


# ─── NEW: Ramachandran Plot ────────────────────────────────────────

def _render_ramachandran(
    analysis: dict,
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
):
    """Ramachandran φ/ψ dihedral angle scatter (NAR 2024)."""
    rama = analysis.get("ramachandran", [])
    stats = analysis.get("rama_stats", {})
    if len(rama) < 3:
        return

    st.markdown("#### Ramachandran Plot")
    st.caption(
        "Backbone φ/ψ dihedral angles. Favored regions (blue shading) indicate "
        "well-modeled geometry. Outliers (red) may indicate structural strain."
    )

    phi_vals = [r["phi"] for r in rama]
    psi_vals = [r["psi"] for r in rama]
    rids = [r["residue"] for r in rama]

    path_set = set(pathogenic_positions.keys())
    rama_colors = []
    rama_sizes = []
    for r in rama:
        rid = r["residue"]
        if mutation_pos and rid == mutation_pos:
            rama_colors.append("#FFCC00")
            rama_sizes.append(14)
        elif rid in path_set:
            rama_colors.append("#FF3B30")
            rama_sizes.append(10)
        else:
            rama_colors.append("#007AFF")
            rama_sizes.append(5)

    fig = go.Figure()

    # Favored regions (background shading)
    # α-helix region
    fig.add_shape(type="rect", x0=-160, x1=-20, y0=-120, y1=20,
                  fillcolor="rgba(10,132,255,0.12)", line_width=0)
    # β-sheet region (upper-left)
    fig.add_shape(type="rect", x0=-180, x1=-40, y0=80, y1=180,
                  fillcolor="rgba(48,209,88,0.12)", line_width=0)
    # β-sheet region (wrapped)
    fig.add_shape(type="rect", x0=-180, x1=-40, y0=-180, y1=-120,
                  fillcolor="rgba(48,209,88,0.12)", line_width=0)
    # Left-handed α-helix
    fig.add_shape(type="rect", x0=20, x1=120, y0=-20, y1=80,
                  fillcolor="rgba(255,159,10,0.08)", line_width=0)

    # Region labels
    fig.add_annotation(x=-90, y=-50, text="α", font=dict(size=16, color="#007AFF"),
                       showarrow=False, opacity=0.4)
    fig.add_annotation(x=-120, y=130, text="β", font=dict(size=16, color="#34C759"),
                       showarrow=False, opacity=0.4)
    fig.add_annotation(x=60, y=30, text="Lα", font=dict(size=12, color="#FF9500"),
                       showarrow=False, opacity=0.4)

    # All residues
    fig.add_trace(go.Scatter(
        x=phi_vals, y=psi_vals,
        mode="markers",
        marker=dict(color=rama_colors, size=rama_sizes, opacity=0.7,
                    line=dict(color="rgba(0,0,0,0.2)", width=0.5)),
        text=[f"Res {r}" for r in rids],
        hovertemplate="%{text}<br>φ: %{x:.1f}°<br>ψ: %{y:.1f}°<extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        xaxis=dict(title="φ (degrees)", range=[-180, 180], dtick=60, gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(title="ψ (degrees)", range=[-180, 180], dtick=60, gridcolor="rgba(0,0,0,0.08)"),
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=380,
        margin=dict(t=10, b=40, l=50, r=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Quality stats
    if stats:
        fav = stats.get("favored_pct", 0)
        outlier = stats.get("outlier", 0)
        total = stats.get("total", 1)
        if fav >= 95:
            st.success(
                f"**Excellent backbone geometry** — {fav:.1f}% of residues in "
                f"favored regions ({stats.get('favored', 0)}/{total}). "
                f"{outlier} outlier(s)."
            )
        elif fav >= 85:
            st.info(
                f"**Good backbone geometry** — {fav:.1f}% favored, "
                f"{outlier} outlier(s) out of {total} residues."
            )
        else:
            st.warning(
                f"**Unusual backbone geometry** — only {fav:.1f}% in favored regions. "
                f"{outlier} outlier(s) may indicate modelling errors or genuine strain."
            )


# ─── NEW: Residue Interaction Network Centrality ───────────────────

def _render_network_centrality(
    analysis: dict,
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
):
    """Betweenness centrality profile from residue interaction network (npj Genomic Med 2024)."""
    centrality = analysis.get("network_centrality", {})
    hubs = analysis.get("hub_residues", [])
    if not centrality:
        return

    st.markdown("#### Residue Interaction Network")
    st.caption(
        "Betweenness centrality from the Cα contact graph (edges < 8 Å). "
        "Hub residues (high centrality) are structurally critical — mutations there "
        "disrupt many inter-residue communication paths."
    )

    res_ids = sorted(centrality.keys())
    cent_vals = [centrality[r] for r in res_ids]
    path_set = set(pathogenic_positions.keys())
    hub_set = {h["residue"] for h in hubs}

    colors = []
    for r in res_ids:
        if mutation_pos and r == mutation_pos:
            colors.append("#FFCC00")
        elif r in path_set:
            colors.append("#FF3B30")
        elif r in hub_set:
            colors.append("#FF9500")
        else:
            colors.append("#007AFF")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=res_ids, y=cent_vals, marker_color=colors,
        hovertemplate="Res %{x}<br>Centrality: %{y:.4f}<extra></extra>",
    ))

    # Mark mutation
    if mutation_pos and mutation_pos in centrality:
        fig.add_trace(go.Scatter(
            x=[mutation_pos], y=[centrality[mutation_pos]],
            mode="markers",
            marker=dict(color="#FFCC00", size=14, symbol="star",
                        line=dict(color="#FF3B30", width=2)),
            showlegend=False,
            hovertemplate=f"Mutation: centrality {centrality[mutation_pos]:.4f}<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="Betweenness Centrality",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=300,
        margin=dict(t=10, b=40, l=50, r=20),
        showlegend=False,
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Interpretation
    n_edges = analysis.get("network_edges", 0)
    n_nodes = analysis.get("network_nodes", 0)
    st.markdown(
        f'<span style="font-size:0.75em;color:rgba(60,60,67,0.55)">'
        f'Network: {n_nodes} nodes, {n_edges} edges (Cα contacts < 8 Å, |Δi| > 1)'
        f'</span>',
        unsafe_allow_html=True,
    )

    mut_cent = analysis.get("mutation_centrality")
    mut_pct = analysis.get("mutation_centrality_percentile")
    if mut_cent is not None and mut_pct is not None:
        if mut_pct >= 90:
            st.error(
                f"**Mutation at a network hub** — centrality {mut_cent:.4f} "
                f"(top {100-mut_pct:.0f}% of residues). This residue is a critical "
                f"communication node — mutation likely has widespread structural effects."
            )
        elif mut_pct >= 70:
            st.warning(
                f"**Moderately central** — centrality {mut_cent:.4f} "
                f"(top {100-mut_pct:.0f}%). Mutation may disrupt some inter-residue pathways."
            )

    # Variants at hub residues
    var_hubs = analysis.get("variants_at_hubs", [])
    if var_hubs:
        hub_names = ", ".join(f"{v['name']} (pos {v['position']})" for v in var_hubs)
        st.warning(f"**Pathogenic variants at hub residues:** {hub_names}")


def _render_conservation_depth_scatter(
    prediction: PredictionResult,
    query: ProteinQuery,
    mutation_pos: int | None,
    pathogenic_positions: dict,
    pocket_residues: list[int],
):
    """Conservation × Burial Depth scatter — reveals functionally constrained residues.

    This is a 2D cross-correlation plot that combines two independent data streams
    (sequence conservation and structural depth) to surface insights neither can
    show alone. Residues that are BOTH highly conserved AND deeply buried are the
    structural pillars of the protein — mutations here are most destabilizing.
    """
    if not prediction.pdb_content:
        return

    # Compute both data streams
    try:
        from src.conservation import compute_conservation_scores
        from src.residue_depth import compute_residue_depth

        cons_data = compute_conservation_scores(prediction.pdb_content)
        depth_data = compute_residue_depth(prediction.pdb_content)
    except Exception:
        return

    cons_scores = cons_data.get("conservation_scores", {})
    depth_vals = depth_data.get("depth", {})

    if not cons_scores or not depth_vals:
        return

    # Build per-residue dataset with shared keys
    residues = sorted(set(cons_scores.keys()) & set(depth_vals.keys()))
    if len(residues) < 10:
        return

    conservation = [cons_scores[r] for r in residues]
    depth = [depth_vals[r] for r in residues]

    # Classify each residue structurally
    pocket_set = set(pocket_residues) if pocket_residues else set()
    pathogenic_set = set()
    for pos_key in pathogenic_positions:
        try:
            pathogenic_set.add(int(pos_key))
        except (ValueError, TypeError):
            pass

    # Get SASA for surface/interface classification
    sasa_data = {}
    analysis = st.session_state.get(
        f"struct_analysis_{query.protein_name}_{query.mutation}"
    )
    if analysis:
        sasa_data = analysis.get("sasa_per_residue", {})

    categories = []
    for r in residues:
        if r == mutation_pos:
            categories.append("Mutation Site")
        elif r in pathogenic_set:
            categories.append("Pathogenic Variant")
        elif r in pocket_set:
            categories.append("Binding Pocket")
        elif sasa_data.get(r, 0) < 5:
            categories.append("Buried Core")
        else:
            categories.append("Other")

    _CAT_COLORS = {
        "Mutation Site": "#FF3B30",
        "Pathogenic Variant": "#FF9500",
        "Binding Pocket": "#AF52DE",
        "Buried Core": "#007AFF",
        "Other": "#C7C7CC",
    }
    _CAT_SIZES = {
        "Mutation Site": 14,
        "Pathogenic Variant": 10,
        "Binding Pocket": 9,
        "Buried Core": 5,
        "Other": 4,
    }
    _CAT_SYMBOLS = {
        "Mutation Site": "x",
        "Pathogenic Variant": "diamond",
        "Binding Pocket": "square",
        "Buried Core": "circle",
        "Other": "circle",
    }

    st.markdown("#### Conservation × Burial Depth")
    st.caption(
        "Residues that are both highly conserved and deeply buried are the structural "
        "pillars of the protein — mutations here carry the highest destabilization risk."
    )

    fig = go.Figure()

    # Plot each category as a separate trace for legend clarity
    for cat in ["Other", "Buried Core", "Binding Pocket", "Pathogenic Variant", "Mutation Site"]:
        mask = [i for i, c in enumerate(categories) if c == cat]
        if not mask:
            continue
        fig.add_trace(go.Scatter(
            x=[conservation[i] for i in mask],
            y=[depth[i] for i in mask],
            mode="markers",
            name=cat,
            marker=dict(
                size=_CAT_SIZES[cat],
                color=_CAT_COLORS[cat],
                symbol=_CAT_SYMBOLS[cat],
                line=dict(width=0.5, color="white") if cat != "Other" else dict(width=0),
                opacity=0.9 if cat != "Other" else 0.35,
            ),
            text=[f"Res {residues[i]}" for i in mask],
            hovertemplate=(
                "<b>Residue %{text}</b><br>"
                "Conservation: %{x}/9<br>"
                "Depth: %{y:.1f} Å<br>"
                f"<i>{cat}</i>"
                "<extra></extra>"
            ),
        ))

    # Add quadrant annotations
    max_depth = max(depth) if depth else 10
    fig.add_shape(
        type="rect", x0=7, x1=9.5, y0=max_depth * 0.6, y1=max_depth * 1.05,
        fillcolor="rgba(255,59,48,0.06)", line=dict(width=0),
        layer="below",
    )
    fig.add_annotation(
        x=8, y=max_depth * 0.95,
        text="<b>Structural pillars</b><br><span style='font-size:10px'>conserved + buried</span>",
        showarrow=False, font=dict(size=10, color="#FF3B30"),
        bgcolor="rgba(255,255,255,0.8)",
    )

    fig.add_shape(
        type="rect", x0=7, x1=9.5, y0=0, y1=max_depth * 0.3,
        fillcolor="rgba(52,199,89,0.06)", line=dict(width=0),
        layer="below",
    )
    fig.add_annotation(
        x=8, y=max_depth * 0.05,
        text="<b>Functional surface</b><br><span style='font-size:10px'>conserved + exposed</span>",
        showarrow=False, font=dict(size=10, color="#34C759"),
        bgcolor="rgba(255,255,255,0.8)",
    )

    fig.update_layout(
        xaxis_title="Conservation Score (1=variable → 9=conserved)",
        yaxis_title="Burial Depth (Å from surface)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=420,
        margin=dict(t=10, b=50, l=60, r=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=11),
        ),
        xaxis=dict(
            gridcolor="rgba(0,0,0,0.08)", range=[0.5, 9.5],
            dtick=1,
        ),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Summary insight
    # Count residues in the "danger zone" (conserved ≥7 AND deep ≥ 60% of max)
    depth_threshold = max_depth * 0.6 if max_depth > 0 else 5
    pillars = [
        r for r, c, d in zip(residues, conservation, depth)
        if c >= 7 and d >= depth_threshold
    ]
    if mutation_pos and mutation_pos in pillars:
        st.error(
            f"**{query.mutation or f'Residue {mutation_pos}'} sits in the structural pillar zone** "
            f"— both highly conserved (score ≥7) and deeply buried (≥{depth_threshold:.0f} Å). "
            f"This mutation carries very high destabilization risk."
        )
    elif pillars:
        pct = len(pillars) / len(residues) * 100
        st.info(
            f"**{len(pillars)} structural pillar residues** ({pct:.1f}% of protein) "
            f"identified — conserved ≥7 and buried ≥{depth_threshold:.0f} Å. "
            f"These positions are the most intolerant to mutation."
        )


def _render_communication_path(
    prediction: PredictionResult,
    query: ProteinQuery,
    mutation_pos: int,
    pocket_residues: list[int],
):
    """Show the shortest structural communication path from mutation to binding pocket.

    This reveals how a mutation's effect can propagate through the protein's
    contact network to reach a distant functional site — the structural basis
    for allosteric effects and long-range coupling.
    """
    if not prediction.pdb_content or not pocket_residues:
        return

    try:
        from src.protein_network import find_communication_path
    except ImportError:
        return

    # Find shortest path to each pocket residue, pick the shortest
    best_path = None
    for target in pocket_residues:
        if target == mutation_pos:
            continue
        result = find_communication_path(
            prediction.pdb_content, mutation_pos, target,
        )
        if result.get("error"):
            continue
        if best_path is None or result["path_length"] < best_path["path_length"]:
            best_path = result

    if best_path is None or not best_path.get("path"):
        return

    path = best_path["path"]
    steps = best_path["steps"]

    st.markdown("#### Structural Communication Path")
    st.caption(
        f"Shortest contact-network path from **{query.mutation or f'residue {mutation_pos}'}** "
        f"to the nearest binding pocket residue ({best_path['target']}). "
        f"Each hop is a Cα–Cα contact < 8 Å."
    )

    # Metrics row
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Path Hops", best_path["n_hops"])
    m2.metric("Network Distance", f"{best_path['path_length']} Å")
    m3.metric("Direct Distance", f"{best_path['direct_distance']} Å")
    m4.metric(
        "Path/Direct Ratio",
        f"{best_path['path_to_direct_ratio']}×",
        help="Ratio > 2 suggests a tortuous path — the effect must traverse "
             "significant structural distance to reach the pocket.",
    )

    # Visualization: pathway as a horizontal chain diagram
    fig = go.Figure()

    # Path residue positions along x
    x_pos = list(range(len(path)))

    # Get conservation and depth for path residues (if available)
    try:
        from src.conservation import compute_conservation_scores
        cons = compute_conservation_scores(prediction.pdb_content).get("conservation_scores", {})
    except Exception:
        cons = {}

    # Color nodes by role
    node_colors = []
    node_sizes = []
    node_labels = []
    for i, r in enumerate(path):
        if r == mutation_pos:
            node_colors.append("#FF3B30")
            node_sizes.append(18)
            node_labels.append(f"<b>{query.mutation or r}</b><br>Mutation")
        elif r == best_path["target"]:
            node_colors.append("#AF52DE")
            node_sizes.append(18)
            node_labels.append(f"<b>Res {r}</b><br>Pocket")
        else:
            c = cons.get(r, 5)
            node_colors.append("#007AFF" if c >= 7 else "#34C759" if c >= 4 else "#8E8E93")
            node_sizes.append(12)
            node_labels.append(f"Res {r}<br>Cons: {c}/9")

    # Draw edges (steps) as lines
    for i, step in enumerate(steps):
        fig.add_trace(go.Scatter(
            x=[x_pos[i], x_pos[i + 1]],
            y=[0, 0],
            mode="lines",
            line=dict(
                color="rgba(0,0,0,0.2)",
                width=max(1, 6 - step["distance"] / 2),
            ),
            hoverinfo="skip",
            showlegend=False,
        ))
        # Distance label on edge
        fig.add_annotation(
            x=(x_pos[i] + x_pos[i + 1]) / 2,
            y=0.15,
            text=f"{step['distance']}Å",
            showarrow=False,
            font=dict(size=9, color="rgba(60,60,67,0.55)"),
        )

    # Draw nodes
    fig.add_trace(go.Scatter(
        x=x_pos,
        y=[0] * len(path),
        mode="markers+text",
        marker=dict(
            size=node_sizes,
            color=node_colors,
            line=dict(width=2, color="white"),
        ),
        text=[str(r) for r in path],
        textposition="bottom center",
        textfont=dict(size=10),
        hovertext=node_labels,
        hoverinfo="text",
        showlegend=False,
    ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=160,
        margin=dict(t=20, b=40, l=20, r=20),
        xaxis=dict(showgrid=False, showticklabels=False, zeroline=False),
        yaxis=dict(showgrid=False, showticklabels=False, zeroline=False, range=[-0.5, 0.5]),
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Interpretation
    ratio = best_path["path_to_direct_ratio"]
    if ratio > 2.5:
        st.warning(
            f"**Tortuous communication path** — the network distance is {ratio}× the "
            f"direct distance, suggesting the mutation's effect must traverse a "
            f"complex structural route to reach the binding pocket."
        )
    elif best_path["n_hops"] <= 3:
        st.error(
            f"**Short-range coupling** — only {best_path['n_hops']} hops from mutation "
            f"to binding pocket. This mutation likely has direct impact on drug binding."
        )
    else:
        st.info(
            f"**{best_path['n_hops']}-hop structural pathway** from mutation to pocket — "
            f"the effect propagates through {best_path['n_hops'] - 1} relay residues."
        )


def _render_hydrophobic_patches(
    prediction: PredictionResult,
    query: ProteinQuery,
    mutation_pos: int | None,
    pocket_residues: list[int],
):
    """Surface hydrophobic patch map — identifies potential binding interfaces.

    Clusters surface-exposed hydrophobic residues into spatial patches.
    Large contiguous hydrophobic patches on the surface are strong indicators
    of protein-protein interaction sites or drug binding hotspots.
    """
    if not prediction.pdb_content:
        return

    try:
        import biotite.structure as struc
        import biotite.structure.io.pdb as pdbio
    except ImportError:
        return

    pdb_file = pdbio.PDBFile.read(__import__("io").StringIO(prediction.pdb_content))
    structure = pdb_file.get_structure(model=1)
    aa_mask = struc.filter_amino_acids(structure)
    protein = structure[aa_mask]
    ca = protein[protein.atom_name == "CA"]

    if len(ca) < 10:
        return

    res_ids = [int(r) for r in ca.res_id]
    res_names = list(ca.res_name)
    coords = ca.coord

    # Kyte-Doolittle scale
    KD = {
        "ILE": 4.5, "VAL": 4.2, "LEU": 3.8, "PHE": 2.8, "CYS": 2.5,
        "MET": 1.9, "ALA": 1.8, "GLY": -0.4, "THR": -0.7, "SER": -0.8,
        "TRP": -0.9, "TYR": -1.3, "PRO": -1.6, "HIS": -3.2, "GLU": -3.5,
        "GLN": -3.5, "ASP": -3.5, "ASN": -3.5, "LYS": -3.9, "ARG": -4.5,
    }

    # Compute SASA to find surface residues
    try:
        sasa = struc.sasa(protein, vdw_radii="ProtOr")
    except Exception:
        return

    # Per-residue SASA
    res_sasa = {}
    for r_id in set(res_ids):
        mask = protein.res_id == r_id
        res_sasa[r_id] = float(sasa[mask].sum()) if mask.any() else 0

    # Surface hydrophobic residues: SASA > 10 Å² and KD > 0.5
    surface_hydrophobic = []
    for i, (r, name) in enumerate(zip(res_ids, res_names)):
        if res_sasa.get(r, 0) > 10 and KD.get(name, 0) > 0.5:
            surface_hydrophobic.append((r, coords[i], KD.get(name, 0)))

    if len(surface_hydrophobic) < 3:
        return

    # Cluster into spatial patches (simple distance-based clustering)
    patches = []
    assigned = set()
    for i, (r1, c1, kd1) in enumerate(surface_hydrophobic):
        if r1 in assigned:
            continue
        patch = [(r1, c1, kd1)]
        assigned.add(r1)
        # Grow patch by adding nearby hydrophobic residues
        for j, (r2, c2, kd2) in enumerate(surface_hydrophobic):
            if r2 in assigned:
                continue
            # Check if close to any member of current patch
            for _, pc, _ in patch:
                if np.linalg.norm(c2 - pc) < 10.0:  # 10 Å cutoff
                    patch.append((r2, c2, kd2))
                    assigned.add(r2)
                    break
        if len(patch) >= 3:  # Only keep patches with ≥3 residues
            patches.append(patch)

    if not patches:
        return

    # Sort by size (largest first)
    patches.sort(key=len, reverse=True)

    st.markdown("#### Surface Hydrophobic Patches")
    st.caption(
        "Clusters of surface-exposed hydrophobic residues — potential protein-protein "
        "interaction sites or drug binding hotspots. Larger patches correlate with "
        "higher binding propensity."
    )

    pocket_set = set(pocket_residues) if pocket_residues else set()

    # Summary metrics
    total_hp = sum(len(p) for p in patches)
    m1, m2, m3 = st.columns(3)
    m1.metric("Hydrophobic Patches", len(patches))
    m2.metric("Largest Patch", f"{len(patches[0])} residues")
    m3.metric("Total Surface HP", f"{total_hp} residues")

    # Visualization: patches as colored blocks along sequence
    _PATCH_COLORS = [
        "#FF9500", "#007AFF", "#34C759", "#AF52DE", "#FF2D55",
        "#5856D6", "#FF6482", "#30B0C7",
    ]

    fig = go.Figure()

    for idx, patch in enumerate(patches[:8]):  # Show top 8
        color = _PATCH_COLORS[idx % len(_PATCH_COLORS)]
        residues_in_patch = [r for r, _, _ in patch]
        kd_vals = [kd for _, _, kd in patch]
        in_pocket = [r for r in residues_in_patch if r in pocket_set]

        fig.add_trace(go.Bar(
            x=residues_in_patch,
            y=kd_vals,
            name=f"Patch {idx + 1} ({len(patch)} res)",
            marker_color=color,
            opacity=0.85,
            hovertemplate=(
                "<b>Residue %{x}</b><br>"
                "Hydrophobicity: %{y:.1f}<br>"
                f"Patch {idx + 1}"
                "<extra></extra>"
            ),
        ))

        # Annotate pocket overlaps
        if in_pocket:
            for r in in_pocket:
                kd_val = next((kd for ri, _, kd in patch if ri == r), 0)
                fig.add_annotation(
                    x=r, y=kd_val + 0.3,
                    text="pocket",
                    showarrow=False,
                    font=dict(size=8, color="#AF52DE"),
                )

    # Mark mutation if present
    if mutation_pos:
        kd_at_mut = KD.get(
            next((n for r, n in zip(res_ids, res_names) if r == mutation_pos), ""), 0
        )
        fig.add_trace(go.Scatter(
            x=[mutation_pos], y=[kd_at_mut],
            mode="markers",
            marker=dict(size=12, color="#FF3B30", symbol="x", line=dict(width=2)),
            name=query.mutation or f"Mut {mutation_pos}",
            hovertemplate=f"<b>{query.mutation or mutation_pos}</b><br>KD: {kd_at_mut:.1f}<extra></extra>",
        ))

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="Hydrophobicity (KD scale)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=320,
        margin=dict(t=10, b=40, l=50, r=20),
        barmode="overlay",
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=10),
        ),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )

    st.plotly_chart(fig, use_container_width=True)

    # Insights
    for idx, patch in enumerate(patches[:3]):
        residues_in_patch = [r for r, _, _ in patch]
        in_pocket = [r for r in residues_in_patch if r in pocket_set]
        patch_range = f"{min(residues_in_patch)}-{max(residues_in_patch)}"

        if in_pocket:
            st.success(
                f"**Patch {idx + 1}** ({len(patch)} residues, {patch_range}) "
                f"overlaps with {len(in_pocket)} known binding pocket residues — "
                f"validated drug interaction surface."
            )
        elif mutation_pos and mutation_pos in residues_in_patch:
            st.warning(
                f"**Patch {idx + 1}** ({len(patch)} residues, {patch_range}) "
                f"contains the mutation site — mutation may alter surface "
                f"hydrophobicity and affect protein-protein interactions."
            )
        else:
            # Cross-reference with conservation
            try:
                from src.conservation import compute_conservation_scores
                cons_data = compute_conservation_scores(prediction.pdb_content)
                cons_scores = cons_data.get("conservation_scores", {})
                conserved_in_patch = [r for r in residues_in_patch if cons_scores.get(r, 5) >= 7]
                if len(conserved_in_patch) >= 2:
                    st.info(
                        f"**Patch {idx + 1}** ({len(patch)} residues, {patch_range}) — "
                        f"{len(conserved_in_patch)} residues are highly conserved (score ≥7). "
                        f"Conserved + hydrophobic + surface = strong interaction site signature."
                    )
            except Exception:
                pass
