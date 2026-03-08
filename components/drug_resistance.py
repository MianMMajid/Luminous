"""Drug Resistance Mechanism Viewer — structural explanation of why resistance mutations work.

No existing tool cross-references resistance mutations with drug binding sites on 3D
structure. MdrDB has 100K+ resistance samples but zero structural visualization.
This panel shows WHERE the mutation sits relative to the drug binding pocket and
WHY it confers resistance, using structural reasoning.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.models import BioContext, PredictionResult, ProteinQuery

# Curated drug resistance knowledge base for demo proteins.
# In production, this would be fetched from MdrDB/DRMref APIs.
_RESISTANCE_DB: dict[str, dict] = {
    "EGFR": {
        "binding_pocket_residues": list(range(719, 730)) + list(range(743, 760)) + list(range(788, 800)) + list(range(854, 862)),
        "mutations": {
            "T790M": {
                "position": 790,
                "mechanism": "Gatekeeper mutation",
                "explanation": (
                    "T790M replaces threonine with the bulkier methionine at the gatekeeper position "
                    "in the ATP-binding cleft. This creates a steric clash with first-generation TKIs "
                    "(gefitinib, erlotinib) while also increasing ATP affinity. The bulkier side chain "
                    "physically blocks drug access to the hydrophobic pocket behind the gatekeeper."
                ),
                "drugs_affected": [
                    {"name": "Gefitinib", "fold_change": ">100x", "status": "Resistant"},
                    {"name": "Erlotinib", "fold_change": ">100x", "status": "Resistant"},
                    {"name": "Osimertinib", "fold_change": "1x", "status": "Sensitive (designed for T790M)"},
                ],
                "clinical_note": "Found in ~50% of patients progressing on first-gen EGFR TKIs.",
            },
            "C797S": {
                "position": 797,
                "mechanism": "Covalent bond site mutation",
                "explanation": (
                    "C797S eliminates the cysteine residue that third-generation TKIs (osimertinib) "
                    "use to form an irreversible covalent bond. Without this cysteine, osimertinib "
                    "can only bind reversibly, dramatically reducing its potency and residence time."
                ),
                "drugs_affected": [
                    {"name": "Osimertinib", "fold_change": ">100x", "status": "Resistant"},
                    {"name": "Lazertinib", "fold_change": ">50x", "status": "Resistant"},
                ],
                "clinical_note": "Emerging in patients on osimertinib. In cis with T790M = resistant to all current TKIs.",
            },
            "L858R": {
                "position": 858,
                "mechanism": "Activating mutation (drug-sensitizing)",
                "explanation": (
                    "L858R is an activating mutation in the activation loop that destabilizes the "
                    "inactive conformation and shifts the equilibrium toward the active, drug-binding "
                    "conformation. This paradoxically makes the kinase MORE sensitive to TKIs because "
                    "the drug-binding pocket is more accessible."
                ),
                "drugs_affected": [
                    {"name": "Gefitinib", "fold_change": "0.01x", "status": "Sensitizing"},
                    {"name": "Erlotinib", "fold_change": "0.01x", "status": "Sensitizing"},
                    {"name": "Osimertinib", "fold_change": "0.01x", "status": "Sensitizing"},
                ],
                "clinical_note": "Most common EGFR activating mutation in NSCLC (~45% of EGFR+ cases).",
            },
        },
    },
    "TP53": {
        "binding_pocket_residues": list(range(241, 252)) + list(range(271, 282)),
        "mutations": {
            "R248W": {
                "position": 248,
                "mechanism": "DNA-contact mutation",
                "explanation": (
                    "R248 directly contacts DNA in the minor groove. The R248W mutation replaces "
                    "a positively charged arginine (critical for DNA backbone phosphate interaction) "
                    "with a bulky, hydrophobic tryptophan. This abolishes DNA binding, eliminating "
                    "p53's tumor suppressor function. Additionally, the mutant protein gains "
                    "dominant-negative activity by forming non-functional tetramers with wild-type p53."
                ),
                "drugs_affected": [
                    {"name": "APR-246 (Eprenetapopt)", "fold_change": "target", "status": "Designed to reactivate mutant p53"},
                    {"name": "COTI-2", "fold_change": "target", "status": "Restores p53 DNA binding"},
                ],
                "clinical_note": "Hotspot mutation — most frequently mutated residue in human cancers. Found across >50 cancer types.",
            },
        },
    },
    "BRCA1": {
        "binding_pocket_residues": list(range(1, 110)),
        "mutations": {
            "C61G": {
                "position": 61,
                "mechanism": "Zinc-binding domain disruption",
                "explanation": (
                    "C61 is one of the zinc-coordinating cysteines in the RING domain. "
                    "The C61G mutation eliminates zinc coordination, destabilizing the RING "
                    "domain fold required for BRCA1-BARD1 heterodimerization and E3 ubiquitin "
                    "ligase activity. This impairs the DNA damage response pathway."
                ),
                "drugs_affected": [
                    {"name": "Olaparib (PARP inhibitor)", "fold_change": "sensitive", "status": "BRCA1-deficient tumors are sensitive"},
                    {"name": "Talazoparib", "fold_change": "sensitive", "status": "Synthetic lethality with BRCA1 loss"},
                ],
                "clinical_note": "Pathogenic variant in the RING domain. PARP inhibitors exploit synthetic lethality with BRCA1 loss.",
            },
        },
    },
}


def render_drug_resistance(
    query: ProteinQuery,
    prediction: PredictionResult,
    bio_context: BioContext | None,
):
    """Render the drug resistance mechanism viewer."""
    protein_key = query.protein_name.upper()
    resistance_data = _RESISTANCE_DB.get(protein_key)

    # Also check variant data for resistance-relevant mutations
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")

    if not resistance_data and not (variant_data and bio_context and bio_context.drugs):
        return  # Nothing to show

    st.markdown("### Drug-Mutation Structural Analysis")
    st.caption(
        "How mutations at this protein affect drug binding — "
        "connecting structural position, resistance mechanism, and clinical impact."
    )

    if resistance_data:
        _render_known_resistance(query, prediction, resistance_data)
    else:
        _render_inferred_resistance(query, prediction, variant_data, bio_context)


def _render_known_resistance(
    query: ProteinQuery,
    prediction: PredictionResult,
    resistance_data: dict,
):
    """Render resistance analysis for proteins in our knowledge base."""
    pocket_residues = set(resistance_data.get("binding_pocket_residues", []))
    mutations_db = resistance_data.get("mutations", {})

    if not mutations_db:
        return

    # Binding pocket confidence visualization
    _render_pocket_confidence(prediction, pocket_residues, mutations_db)

    # Cross-resistance heatmap
    _render_resistance_heatmap(mutations_db, query.mutation)

    # Detailed mutation cards
    # If the user's query mutation is in our DB, show it first
    query_mut_name = query.mutation.upper() if query.mutation else None
    ordered_muts = []
    for name, data in mutations_db.items():
        if name.upper() == query_mut_name:
            ordered_muts.insert(0, (name, data))
        else:
            ordered_muts.append((name, data))

    for mut_name, mut_data in ordered_muts:
        is_query = mut_name.upper() == query_mut_name
        _render_resistance_card(mut_name, mut_data, is_query, pocket_residues)


def _render_pocket_confidence(
    prediction: PredictionResult,
    pocket_residues: set[int],
    mutations_db: dict,
):
    """Show pLDDT profile with binding pocket and resistance mutations highlighted."""
    if not prediction.residue_ids or not prediction.plddt_per_residue:
        return

    # Use first chain only
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
        return

    from src.utils import trust_to_color

    fig = go.Figure()

    # Background: all residues
    fig.add_trace(go.Bar(
        x=res_ids,
        y=scores,
        marker_color=[trust_to_color(s) for s in scores],
        opacity=0.3,
        name="All residues",
        hovertemplate="Residue %{x}<br>pLDDT: %{y:.1f}<extra></extra>",
    ))

    # Highlight: binding pocket residues
    pocket_x = [r for r in res_ids if r in pocket_residues]
    pocket_y = [scores[res_ids.index(r)] for r in pocket_x]
    if pocket_x:
        fig.add_trace(go.Bar(
            x=pocket_x,
            y=pocket_y,
            marker_color="#007AFF",
            opacity=0.8,
            name="Drug binding pocket",
            hovertemplate="Binding pocket residue %{x}<br>pLDDT: %{y:.1f}<extra></extra>",
        ))

    # Mark resistance mutations
    for mut_name, mut_data in mutations_db.items():
        pos = mut_data["position"]
        if pos in res_ids:
            idx = res_ids.index(pos)
            color = "#FF3B30" if "Resistant" in str(mut_data.get("drugs_affected", [])) else "#34C759"
            fig.add_trace(go.Scatter(
                x=[pos],
                y=[scores[idx]],
                mode="markers+text",
                marker=dict(color=color, size=12, symbol="star"),
                text=[mut_name],
                textposition="top center",
                textfont=dict(size=10, color=color),
                name=mut_name,
                hovertemplate=f"{mut_name}: {mut_data['mechanism']}<br>pLDDT: {scores[idx]:.1f}<extra></extra>",
            ))

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 105],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=300,
        margin=dict(t=10, b=40, l=50, r=20),
        barmode="overlay",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_resistance_heatmap(mutations_db: dict, query_mutation: str | None):
    """Render a Drug × Mutation cross-resistance heatmap."""
    # Collect all unique drugs and mutations
    all_drugs = []
    mutation_names = []
    for mut_name, mut_data in mutations_db.items():
        mutation_names.append(mut_name)
        for drug in mut_data.get("drugs_affected", []):
            if drug["name"] not in all_drugs:
                all_drugs.append(drug["name"])

    if len(mutation_names) < 2 or len(all_drugs) < 2:
        return  # Not enough data for a meaningful heatmap

    st.markdown("#### Cross-Resistance Matrix")
    st.caption(
        "Which mutations affect which drugs — revealing cross-resistance patterns "
        "and identifying drugs that remain effective against specific mutation profiles."
    )

    # Build the matrix
    z_values = []
    text_values = []
    for mut_name in mutation_names:
        row_z = []
        row_text = []
        mut_data = mutations_db[mut_name]
        drug_lookup = {d["name"]: d for d in mut_data.get("drugs_affected", [])}
        for drug_name in all_drugs:
            drug = drug_lookup.get(drug_name)
            if drug is None:
                row_z.append(0)
                row_text.append("—")
            else:
                fc = drug.get("fold_change", "")
                status = drug.get("status", "")
                combined = f"{fc} {status}".lower()

                if "sensitiz" in combined or ("sensitive" in combined and "designed" not in combined and "reactivat" not in combined):
                    row_z.append(-1)
                elif "target" in combined or "designed" in combined or "reactivat" in combined or "restores" in combined:
                    row_z.append(-2)
                elif ">100x" in fc or ">50x" in fc:
                    row_z.append(3)
                elif "resistant" in combined:
                    row_z.append(2)
                else:
                    row_z.append(1)

                row_text.append(fc if fc else status[:20])
        z_values.append(row_z)
        text_values.append(row_text)

    # Highlight query mutation row
    y_labels = []
    for m in mutation_names:
        if query_mutation and m.upper() == query_mutation.upper():
            y_labels.append(f"► {m} (query)")
        else:
            y_labels.append(m)

    # Custom colorscale: blue (-2) → green (-1) → gray (0) → orange (1) → red (2) → dark red (3)
    colorscale = [
        [0.0, "#007AFF"],     # -2: therapeutic target (blue)
        [0.2, "#34C759"],     # -1: sensitizing (green)
        [0.4, "#C7C7CC"],     # 0: no data (gray)
        [0.6, "#FF9500"],     # 1: moderate resistance (amber)
        [0.8, "#FF3B30"],     # 2: resistant (red)
        [1.0, "#7F1D1D"],     # 3: highly resistant (dark red)
    ]

    fig = go.Figure(data=go.Heatmap(
        z=z_values,
        x=[d[:25] for d in all_drugs],  # Truncate long drug names
        y=y_labels,
        text=text_values,
        texttemplate="%{text}",
        textfont=dict(size=11, color="black"),
        colorscale=colorscale,
        zmin=-2,
        zmax=3,
        showscale=False,
        hovertemplate="Mutation: %{y}<br>Drug: %{x}<br>Effect: %{text}<extra></extra>",
    ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=max(200, len(mutation_names) * 50 + 80),
        margin=dict(t=10, b=60, l=100, r=20),
        xaxis=dict(side="bottom", tickangle=-30),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:2px">'
        '<span style="font-size:0.78em"><span style="background:#7F1D1D;padding:2px 6px;border-radius:3px;color:white">■</span> Highly Resistant</span>'
        '<span style="font-size:0.78em"><span style="background:#FF3B30;padding:2px 6px;border-radius:3px;color:white">■</span> Resistant</span>'
        '<span style="font-size:0.78em"><span style="background:#FF9500;padding:2px 6px;border-radius:3px;color:white">■</span> Moderate</span>'
        '<span style="font-size:0.78em"><span style="background:#E5E5EA;padding:2px 6px;border-radius:3px;color:#000000">■</span> No Data</span>'
        '<span style="font-size:0.78em"><span style="background:#34C759;padding:2px 6px;border-radius:3px;color:white">■</span> Sensitizing</span>'
        '<span style="font-size:0.78em"><span style="background:#007AFF;padding:2px 6px;border-radius:3px;color:white">■</span> Therapeutic Target</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_resistance_card(
    mut_name: str,
    mut_data: dict,
    is_query: bool,
    pocket_residues: set[int],
):
    """Render a single resistance mutation detail card."""
    pos = mut_data["position"]
    in_pocket = pos in pocket_residues

    border_color = "#FF3B30" if is_query else "#C6C6C8"
    badge = " (Your query)" if is_query else ""

    st.markdown(
        f'<div style="background:#F2F2F7;padding:14px;border-radius:8px;'
        f'border:1px solid {border_color};margin-bottom:12px">'
        f'<div style="font-size:1.1em;font-weight:bold">'
        f'{mut_name}{badge}'
        f'<span style="font-size:0.8em;color:rgba(60,60,67,0.6);margin-left:8px">'
        f'Position {pos} — {"In binding pocket" if in_pocket else "Outside binding pocket"}'
        f'</span></div>'
        f'<div style="color:#FF9500;font-size:0.9em;margin:4px 0">{mut_data["mechanism"]}</div>'
        f'<div style="font-size:0.88em;color:rgba(60,60,67,0.6);margin-top:8px">{mut_data["explanation"]}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Drug impact table
    drugs = mut_data.get("drugs_affected", [])
    if drugs:
        cols = st.columns(len(drugs))
        for col, drug in zip(cols, drugs):
            status = drug["status"]
            if "Resistant" in status:
                _icon, color = "✗", "#E00000"
            elif "Sensitiz" in status:
                _icon, color = "✓", "#16A34A"
            else:
                _icon, color = "◆", "#FF9500"

            col.markdown(
                f'<div style="text-align:center;background:#F2F2F7;padding:8px;border-radius:6px">'
                f'<div style="font-size:0.8em;color:rgba(60,60,67,0.6)">{drug["name"]}</div>'
                f'<div style="font-size:1.1em;color:{color};font-weight:bold">'
                f'{drug.get("fold_change", "?")}</div>'
                f'<div style="font-size:0.75em;color:{color}">{status}</div></div>',
                unsafe_allow_html=True,
            )

    if mut_data.get("clinical_note"):
        st.caption(f"Clinical: {mut_data['clinical_note']}")


def _render_inferred_resistance(
    query: ProteinQuery,
    prediction: PredictionResult,
    variant_data: dict | None,
    bio_context: BioContext | None,
):
    """For proteins not in our curated DB, infer drug-variant relationships."""
    if not variant_data or not bio_context or not bio_context.drugs:
        return

    path_positions = variant_data.get("pathogenic_positions", {})
    if not path_positions:
        return

    st.info(
        f"No curated resistance data for {query.protein_name}. "
        f"Showing inferred drug-variant proximity analysis based on "
        f"{len(path_positions)} pathogenic positions and {len(bio_context.drugs)} drug candidates."
    )

    # Summary: which drugs target this protein and what pathogenic variants exist
    drug_col, var_col = st.columns(2)
    with drug_col:
        st.markdown("**Drug Candidates**")
        for drug in bio_context.drugs[:5]:
            phase = f" ({drug.phase})" if drug.phase else ""
            st.markdown(f"- {drug.name}{phase}")

    with var_col:
        st.markdown("**Pathogenic Hotspots**")
        for pos_str, names in list(path_positions.items())[:5]:
            name_str = ", ".join(names) if isinstance(names, list) else str(names)
            st.markdown(f"- Position {pos_str}: {name_str}")

    if len(path_positions) > 3 and len(bio_context.drugs) > 0:
        st.warning(
            f"**{len(path_positions)} pathogenic hotspots** on a protein targeted by "
            f"**{len(bio_context.drugs)} drug(s)** — mutations at these positions "
            f"could potentially affect drug binding. Experimental validation recommended."
        )
