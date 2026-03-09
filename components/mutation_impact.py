"""Mutation Structural Impact Panel — answers 'What does this mutation do to the protein?'

No existing tool automates this: given a mutation, show its structural context,
amino acid property changes, proximity to pathogenic hotspots, and confidence
at that position — all in one view. Structural evidence reclassifies 73% of VUS
(Iqbal et al., Genome Medicine 2022), yet no tool provides this automatically.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st

from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit

# Amino acid properties for impact analysis
_AA_PROPERTIES: dict[str, dict] = {
    "G": {"name": "Glycine",       "charge": 0, "hydrophobicity": -0.4, "size": "tiny",   "mw": 57},
    "A": {"name": "Alanine",       "charge": 0, "hydrophobicity":  1.8, "size": "small",  "mw": 71},
    "V": {"name": "Valine",        "charge": 0, "hydrophobicity":  4.2, "size": "medium", "mw": 99},
    "L": {"name": "Leucine",       "charge": 0, "hydrophobicity":  3.8, "size": "large",  "mw": 113},
    "I": {"name": "Isoleucine",    "charge": 0, "hydrophobicity":  4.5, "size": "large",  "mw": 113},
    "P": {"name": "Proline",       "charge": 0, "hydrophobicity": -1.6, "size": "small",  "mw": 97},
    "F": {"name": "Phenylalanine", "charge": 0, "hydrophobicity":  2.8, "size": "large",  "mw": 147},
    "W": {"name": "Tryptophan",    "charge": 0, "hydrophobicity": -0.9, "size": "large",  "mw": 186},
    "M": {"name": "Methionine",    "charge": 0, "hydrophobicity":  1.9, "size": "large",  "mw": 131},
    "S": {"name": "Serine",        "charge": 0, "hydrophobicity": -0.8, "size": "small",  "mw": 87},
    "T": {"name": "Threonine",     "charge": 0, "hydrophobicity": -0.7, "size": "medium", "mw": 101},
    "C": {"name": "Cysteine",      "charge": 0, "hydrophobicity":  2.5, "size": "small",  "mw": 103},
    "Y": {"name": "Tyrosine",      "charge": 0, "hydrophobicity": -1.3, "size": "large",  "mw": 163},
    "H": {"name": "Histidine",     "charge": 1, "hydrophobicity": -3.2, "size": "medium", "mw": 137},
    "D": {"name": "Aspartate",     "charge":-1, "hydrophobicity": -3.5, "size": "medium", "mw": 115},
    "E": {"name": "Glutamate",     "charge":-1, "hydrophobicity": -3.5, "size": "large",  "mw": 129},
    "N": {"name": "Asparagine",    "charge": 0, "hydrophobicity": -3.5, "size": "medium", "mw": 114},
    "Q": {"name": "Glutamine",     "charge": 0, "hydrophobicity": -3.5, "size": "large",  "mw": 128},
    "K": {"name": "Lysine",        "charge": 1, "hydrophobicity": -3.9, "size": "large",  "mw": 128},
    "R": {"name": "Arginine",      "charge": 1, "hydrophobicity": -4.5, "size": "large",  "mw": 156},
}

_SIZE_ORDER = {"tiny": 0, "small": 1, "medium": 2, "large": 3}


def render_mutation_impact(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    """Render the mutation structural impact panel."""
    if not query.mutation:
        return  # Nothing to show if no mutation

    st.markdown("### Mutation Structural Impact")
    st.caption(
        "Structural analysis of how this mutation affects the protein — "
        "combining prediction confidence, amino acid chemistry, and clinical context."
    )

    # Parse mutation
    parsed = _parse_mutation(query.mutation)
    if not parsed:
        st.warning(f"Could not parse mutation format: {query.mutation}")
        return

    wt_aa, mut_pos, mut_aa = parsed

    # Find position in prediction data
    plddt_at_site = _get_plddt_at_position(prediction, mut_pos)

    col1, col2 = st.columns([2, 3])

    with col1:
        _render_impact_card(wt_aa, mut_pos, mut_aa, plddt_at_site, query, bio_context)

    with col2:
        _render_neighborhood_chart(prediction, mut_pos, query)

    # Pathogenic proximity analysis
    _render_pathogenic_proximity(prediction, mut_pos, query)


def _parse_mutation(mutation: str) -> tuple[str, int, str] | None:
    """Parse mutation string like 'R248W' into (wt_aa, position, mut_aa)."""
    m = re.match(r"([A-Z])(\d+)([A-Z])", mutation.strip().upper())
    if m:
        return m.group(1), int(m.group(2)), m.group(3)
    # Try three-letter codes: Arg248Trp
    m3 = re.match(r"([A-Za-z]{3})(\d+)([A-Za-z]{3})", mutation.strip())
    if m3:
        three_to_one = {
            "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
            "GLU": "E", "GLN": "Q", "GLY": "G", "HIS": "H", "ILE": "I",
            "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
            "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
        }
        wt = three_to_one.get(m3.group(1).upper())
        mt = three_to_one.get(m3.group(3).upper())
        if wt and mt:
            return wt, int(m3.group(2)), mt
    return None


def _get_plddt_at_position(prediction: PredictionResult, pos: int) -> float | None:
    """Get pLDDT score at a specific residue position (first chain match)."""
    if not prediction.residue_ids or not prediction.plddt_per_residue:
        return None
    for i, rid in enumerate(prediction.residue_ids):
        if rid == pos:
            return prediction.plddt_per_residue[i]
    return None


def _render_impact_card(
    wt_aa: str,
    mut_pos: int,
    mut_aa: str,
    plddt: float | None,
    query: ProteinQuery,
    bio_context: BioContext | None,
):
    """Render the mutation impact summary card."""
    wt_props = _AA_PROPERTIES.get(wt_aa)
    mt_props = _AA_PROPERTIES.get(mut_aa)

    if not wt_props or not mt_props:
        st.info(f"Unknown amino acid in mutation {wt_aa}{mut_pos}{mut_aa}.")
        return

    # Confidence at site
    if plddt is not None:
        if plddt >= 90:
            conf_label, conf_color = "Very High", "#0053D6"
        elif plddt >= 70:
            conf_label, conf_color = "High", "#65CBF3"
        elif plddt >= 50:
            conf_label, conf_color = "Low", "#FFDB13"
        else:
            conf_label, conf_color = "Very Low", "#FF7D45"

        st.markdown(
            f'<div style="background:#F2F2F7;padding:12px;border-radius:8px;'
            f'border-left:4px solid {conf_color};margin-bottom:12px">'
            f'<div style="font-size:0.85em;color:rgba(60,60,67,0.6)">Prediction Confidence at Position {mut_pos}</div>'
            f'<div style="font-size:1.4em;font-weight:bold;color:{conf_color}">'
            f'pLDDT {plddt:.0f} — {conf_label}</div></div>',
            unsafe_allow_html=True,
        )
        if plddt < 70:
            st.warning(
                "Low structural confidence at this position. "
                "The predicted impact may not reflect the true conformation."
            )
    else:
        st.info(f"Position {mut_pos} is outside the predicted residue range.")

    # Amino acid property changes
    st.markdown("**Amino Acid Change**")

    charge_change = mt_props["charge"] - wt_props["charge"]
    hydro_change = mt_props["hydrophobicity"] - wt_props["hydrophobicity"]
    size_change = _SIZE_ORDER[mt_props["size"]] - _SIZE_ORDER[wt_props["size"]]
    mw_change = mt_props["mw"] - wt_props["mw"]

    # Build impact items
    impacts = []

    if charge_change != 0:
        direction = "gained" if charge_change > 0 else "lost"
        impacts.append(("Charge", f"{direction} charge ({wt_props['charge']:+d} -> {mt_props['charge']:+d})", "high"))
    else:
        impacts.append(("Charge", "No change", "low"))

    if abs(hydro_change) > 3:
        direction = "more hydrophobic" if hydro_change > 0 else "more hydrophilic"
        impacts.append(("Hydrophobicity", f"Major shift — {direction} ({hydro_change:+.1f})", "high"))
    elif abs(hydro_change) > 1.5:
        direction = "more hydrophobic" if hydro_change > 0 else "more hydrophilic"
        impacts.append(("Hydrophobicity", f"Moderate shift — {direction} ({hydro_change:+.1f})", "medium"))
    else:
        impacts.append(("Hydrophobicity", f"Minor change ({hydro_change:+.1f})", "low"))

    if abs(size_change) >= 2:
        direction = "much larger" if size_change > 0 else "much smaller"
        impacts.append(("Size", f"{wt_props['size']} -> {mt_props['size']} ({direction}, {mw_change:+d} Da)", "high"))
    elif abs(size_change) == 1:
        direction = "larger" if size_change > 0 else "smaller"
        impacts.append(("Size", f"{wt_props['size']} -> {mt_props['size']} ({direction}, {mw_change:+d} Da)", "medium"))
    else:
        impacts.append(("Size", f"Similar size ({mw_change:+d} Da)", "low"))

    # Special cases
    if wt_aa == "P" or mut_aa == "P":
        impacts.append(("Backbone", "Proline involved — affects backbone flexibility", "high"))
    if wt_aa == "G" or mut_aa == "G":
        impacts.append(("Backbone", "Glycine involved — affects backbone flexibility", "medium"))
    if (wt_aa == "C" and mut_aa != "C") or (mut_aa == "C" and wt_aa != "C"):
        impacts.append(("Disulfide", "Cysteine change — may affect disulfide bonds", "high"))

    # Distinct shapes + colors for colorblind accessibility
    _severity_style = {
        "high":   ("▲", "#FF3B30"),   # Triangle = danger
        "medium": ("◆", "#FF9500"),   # Diamond = warning
        "low":    ("●", "#16A34A"),   # Circle = ok
    }
    for label, desc, severity in impacts:
        shape, color = _severity_style.get(severity, ("●", "#888"))
        st.markdown(
            f'<div style="display:flex;align-items:center;gap:8px;margin:4px 0">'
            f'<span style="color:{color};font-size:0.9em;line-height:1">{shape}</span>'
            f'<span style="font-size:0.9em"><strong>{label}:</strong> {desc}</span></div>',
            unsafe_allow_html=True,
        )

    # Overall severity assessment
    high_count = sum(1 for _, _, s in impacts if s == "high")
    med_count = sum(1 for _, _, s in impacts if s == "medium")

    st.markdown("---")
    if high_count >= 2:
        st.error(
            f"**{wt_props['name']} -> {mt_props['name']}**: Multiple major property changes. "
            f"This substitution is likely structurally disruptive."
        )
    elif high_count == 1 or med_count >= 2:
        st.warning(
            f"**{wt_props['name']} -> {mt_props['name']}**: Significant property change. "
            f"This substitution may affect protein stability or function."
        )
    else:
        st.success(
            f"**{wt_props['name']} -> {mt_props['name']}**: Conservative substitution. "
            f"Limited structural impact expected, though functional effects are possible."
        )

    # Drug context
    if bio_context and bio_context.drugs:
        drug_names = [d.name for d in bio_context.drugs[:3]]
        st.markdown(
            f"**Drug relevance:** {len(bio_context.drugs)} drug(s) target {query.protein_name} "
            f"({', '.join(drug_names)}{'...' if len(bio_context.drugs) > 3 else ''}). "
            f"This mutation may affect drug binding or efficacy."
        )


def _render_neighborhood_chart(
    prediction: PredictionResult,
    mut_pos: int,
    query: ProteinQuery,
):
    """Render pLDDT neighborhood chart centered on the mutation site."""
    if not prediction.residue_ids or not prediction.plddt_per_residue:
        st.info("No per-residue confidence data available.")
        return

    st.markdown("**Structural Neighborhood**")

    # Get first chain data only to avoid duplicates
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
    res_ids = []
    scores = []
    for i, rid in enumerate(prediction.residue_ids):
        if i >= len(prediction.chain_ids) or i >= len(prediction.plddt_per_residue):
            break
        if first_chain is None or prediction.chain_ids[i] == first_chain:
            res_ids.append(rid)
            scores.append(prediction.plddt_per_residue[i])

    if not res_ids:
        st.info("No residue data for the first chain.")
        return

    # Window around mutation: +/- 25 residues
    window = 25
    start = mut_pos - window
    end = mut_pos + window

    win_ids = []
    win_scores = []
    for rid, sc in zip(res_ids, scores):
        if start <= rid <= end:
            win_ids.append(rid)
            win_scores.append(sc)

    if not win_ids:
        # Mutation position is outside predicted range — show full protein
        win_ids = res_ids
        win_scores = scores

    # Color by confidence
    from src.utils import trust_to_color
    colors = [trust_to_color(s) for s in win_scores]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=win_ids,
        y=win_scores,
        marker_color=colors,
        hovertemplate="Residue %{x}<br>pLDDT: %{y:.1f}<extra></extra>",
    ))

    # Mark mutation position
    if mut_pos in win_ids:
        idx = win_ids.index(mut_pos)
        fig.add_trace(go.Scatter(
            x=[mut_pos],
            y=[win_scores[idx]],
            mode="markers+text",
            marker=dict(color="#FF3B30", size=14, symbol="star"),
            text=[query.mutation],
            textposition="top center",
            textfont=dict(size=11, color="#FF3B30"),
            name="Mutation site",
            hovertemplate=f"{query.mutation}<br>pLDDT: {win_scores[idx]:.1f}<extra></extra>",
        ))

    # Mark nearby pathogenic variants
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    if variant_data and variant_data.get("pathogenic_positions"):
        for pos_str, names in variant_data["pathogenic_positions"].items():
            try:
                vpos = int(pos_str)
            except (ValueError, TypeError):
                continue
            if vpos == mut_pos:
                continue  # Already marked
            if vpos in win_ids:
                vidx = win_ids.index(vpos)
                fig.add_trace(go.Scatter(
                    x=[vpos],
                    y=[win_scores[vidx]],
                    mode="markers",
                    marker=dict(color="#FFCC00", size=10, symbol="diamond"),
                    name=", ".join(names) if isinstance(names, list) else str(names),
                    hovertemplate=(
                        f"Pos {vpos}: {', '.join(names) if isinstance(names, list) else names}"
                        f"<br>pLDDT: {win_scores[vidx]:.1f}<extra></extra>"
                    ),
                ))

    # Confidence thresholds
    for y_val, color, dash in [(90, "#0053D6", "dash"), (70, "#65CBF3", "dash"), (50, "#FFDB13", "dot")]:
        fig.add_hline(y=y_val, line_color=color, line_dash=dash, opacity=0.4)

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 105],
        template="plotly_white",
        height=320,
        margin=dict(t=10, b=40, l=50, r=20),
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, width="stretch")


def _render_pathogenic_proximity(
    prediction: PredictionResult,
    mut_pos: int,
    query: ProteinQuery,
):
    """Analyze proximity to other known pathogenic variants."""
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    if not variant_data or not variant_data.get("pathogenic_positions"):
        return

    path_positions = []
    for pos_str, names in variant_data["pathogenic_positions"].items():
        try:
            path_positions.append((int(pos_str), names))
        except (ValueError, TypeError):
            pass

    if not path_positions:
        return

    # Find nearby pathogenic positions (within 10 residues in sequence)
    nearby = [(pos, names) for pos, names in path_positions if abs(pos - mut_pos) <= 10 and pos != mut_pos]
    at_same = [(pos, names) for pos, names in path_positions if pos == mut_pos]

    if at_same or nearby:
        st.markdown("**Pathogenic Variant Hotspot Analysis**")

    if at_same:
        names = at_same[0][1]
        name_str = ", ".join(names) if isinstance(names, list) else str(names)
        st.error(
            f"Position {mut_pos} is a **known pathogenic hotspot** "
            f"with {len(names) if isinstance(names, list) else 1} known pathogenic variant(s): {name_str}. "
            f"This strongly supports pathogenicity (ACMG PM1/PM5)."
        )

    if nearby:
        positions_str = ", ".join(
            f"{pos} ({', '.join(n) if isinstance(n, list) else n})"
            for pos, n in sorted(nearby, key=lambda x: abs(x[0] - mut_pos))
        )
        st.warning(
            f"**{len(nearby)} pathogenic variant(s)** within 10 residues: {positions_str}. "
            f"Clustering of pathogenic variants suggests this region is functionally critical."
        )
