"""Interactive protein knowledge graph using streamlit-agraph.

Visualizes the protein's relationship network: diseases, drugs, pathways,
and interaction partners as an interactive force-directed graph.
"""
from __future__ import annotations

import streamlit as st

from src.models import BioContext, ProteinQuery, TrustAudit

# Check availability at module level
try:
    from streamlit_agraph import Config, Edge, Node, agraph

    AGRAPH_AVAILABLE = True
except ImportError:
    AGRAPH_AVAILABLE = False


def _truncate(text: str, max_len: int = 25) -> str:
    """Truncate a label to max_len characters, adding ellipsis if needed."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def render_protein_network(
    query: ProteinQuery,
    bio_context: BioContext,
    trust_audit: TrustAudit | None,
) -> None:
    """Render an interactive protein knowledge graph.

    Shows the protein at the center with edges to diseases, drugs, pathways,
    mutation, and interaction partners drawn from the BioContext data.
    """
    if not AGRAPH_AVAILABLE:
        st.info(
            "Install streamlit-agraph for interactive network visualization."
        )
        return

    # Check for empty context
    has_diseases = bool(bio_context.disease_associations)
    has_drugs = bool(bio_context.drugs)
    has_pathways = bool(bio_context.pathways)
    has_mutation = bool(query.mutation)
    has_partner = bool(query.interaction_partner)

    if not any([has_diseases, has_drugs, has_pathways, has_mutation, has_partner]):
        st.info("No biological context data available for network visualization.")
        return

    st.markdown("### Protein Knowledge Graph")
    st.caption(
        "Interactive network showing relationships between the query protein "
        "and its associated diseases, drugs, pathways, and interaction partners. "
        "Click a node to see details."
    )

    nodes: list[Node] = []
    edges: list[Edge] = []
    node_details: dict[str, str] = {}

    # --- Central protein node ---
    protein_label = _truncate(query.protein_name)
    nodes.append(
        Node(
            id=query.protein_name,
            label=protein_label,
            size=35,
            color="#007AFF",
            shape="dot",
            font={"color": "#000000", "size": 14},
        )
    )
    node_details[query.protein_name] = (
        f"**Protein:** {query.protein_name}"
        + (f"  \n**UniProt:** {query.uniprot_id}" if query.uniprot_id else "")
    )

    # --- Mutation node ---
    if has_mutation:
        mut_id = f"mut_{query.mutation}"
        nodes.append(
            Node(
                id=mut_id,
                label=_truncate(query.mutation),  # type: ignore[arg-type]
                size=20,
                color="#FFCC00",
                shape="dot",
                font={"color": "#000000", "size": 12},
            )
        )
        edges.append(
            Edge(
                source=query.protein_name,
                target=mut_id,
                label="mutation",
                color="#FFCC00",
            )
        )
        node_details[mut_id] = f"**Mutation:** {query.mutation}"

    # --- Interaction partner node ---
    if has_partner:
        partner_id = f"partner_{query.interaction_partner}"
        nodes.append(
            Node(
                id=partner_id,
                label=_truncate(query.interaction_partner),  # type: ignore[arg-type]
                size=25,
                color="#007AFF",
                shape="dot",
                font={"color": "#000000", "size": 13},
            )
        )
        edges.append(
            Edge(
                source=query.protein_name,
                target=partner_id,
                label="interacts",
                color="#007AFF",
            )
        )
        node_details[partner_id] = (
            f"**Interaction Partner:** {query.interaction_partner}"
        )

    # --- Disease nodes ---
    truncation_notes: list[str] = []
    diseases = bio_context.disease_associations
    if len(diseases) > 8:
        truncation_notes.append(
            f"Showing top 8 of {len(diseases)} disease associations"
        )
        diseases = diseases[:8]

    for da in diseases:
        disease_id = f"disease_{da.disease}"
        score = da.score if da.score is not None else 0.5
        node_size = 15 + int(score * 10)  # scale 15-25
        nodes.append(
            Node(
                id=disease_id,
                label=_truncate(da.disease),
                size=node_size,
                color="#FF3B30",
                shape="diamond",
                font={"color": "#000000", "size": 11},
            )
        )
        edges.append(
            Edge(
                source=query.protein_name,
                target=disease_id,
                label="associated",
                color="rgba(255, 59, 48, 0.6)",
            )
        )
        detail = f"**Disease:** {da.disease}"
        if da.score is not None:
            detail += f"  \n**Score:** {da.score:.2f}"
        if da.evidence:
            detail += f"  \n**Evidence:** {da.evidence}"
        node_details[disease_id] = detail

    # --- Drug nodes ---
    drugs = bio_context.drugs
    if len(drugs) > 8:
        truncation_notes.append(f"Showing top 8 of {len(drugs)} drug candidates")
        drugs = drugs[:8]

    for drug in drugs:
        drug_id = f"drug_{drug.name}"
        nodes.append(
            Node(
                id=drug_id,
                label=_truncate(drug.name),
                size=20,
                color="#34C759",
                shape="triangle",
                font={"color": "#000000", "size": 11},
            )
        )
        edge_label = (
            _truncate(drug.mechanism, 20) if drug.mechanism else "targets"
        )
        edges.append(
            Edge(
                source=query.protein_name,
                target=drug_id,
                label=edge_label,
                color="#34C759",
            )
        )
        detail = f"**Drug:** {drug.name}"
        if drug.phase:
            detail += f"  \n**Phase:** {drug.phase}"
        if drug.mechanism:
            detail += f"  \n**Mechanism:** {drug.mechanism}"
        if drug.source:
            detail += f"  \n**Source:** {drug.source}"
        node_details[drug_id] = detail

    # --- Pathway nodes ---
    pathways = bio_context.pathways
    if len(pathways) > 6:
        truncation_notes.append(f"Showing top 6 of {len(pathways)} pathways")
        pathways = pathways[:6]

    for pathway in pathways:
        pathway_id = f"pathway_{pathway}"
        nodes.append(
            Node(
                id=pathway_id,
                label=_truncate(pathway),
                size=18,
                color="#AF52DE",
                shape="square",
                font={"color": "#000000", "size": 11},
            )
        )
        edges.append(
            Edge(
                source=query.protein_name,
                target=pathway_id,
                label="in pathway",
                color="#AF52DE",
            )
        )
        node_details[pathway_id] = f"**Pathway:** {pathway}"

    # --- Check for very large networks (>50 nodes) ---
    if len(nodes) > 50:
        # Already truncated per-category above; add a general note
        truncation_notes.append(
            f"Network truncated to {len(nodes)} nodes for performance"
        )

    # --- Config ---
    config = Config(
        width=700,
        height=500,
        directed=True,
        physics=True,
        hierarchical=False,
        nodeHighlightBehavior=True,
        highlightColor="#007AFF",
        collapsible=False,
        node={"labelProperty": "label", "renderLabel": True},
        link={"labelProperty": "label", "renderLabel": True},
    )

    # --- Center the graph via CSS ---
    # streamlit-agraph renders a fixed-width canvas inside a Streamlit component
    # container. Center it by targeting the component's iframe wrapper.
    st.markdown(
        """<style>
        .element-container iframe[title="streamlit_agraph.agraph"],
        .element-container iframe[title*="agraph"] {
            display: block !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }
        </style>""",
        unsafe_allow_html=True,
    )
    selected_node = agraph(nodes=nodes, edges=edges, config=config)

    # --- Truncation notes ---
    for note in truncation_notes:
        st.caption(note)

    # --- Legend ---
    legend_items = [
        ("#007AFF", "Protein / Partner"),
        ("#FF3B30", "Disease"),
        ("#34C759", "Drug"),
        ("#AF52DE", "Pathway"),
    ]
    if has_mutation:
        legend_items.insert(1, ("#FFCC00", "Mutation"))

    legend_html = (
        '<div style="display:flex;flex-wrap:wrap;gap:12px;margin-top:8px;'
        'margin-bottom:8px">'
    )
    for color, label in legend_items:
        legend_html += (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'font-size:0.82em;color:rgba(60,60,67,0.6)">'
            f'<span style="display:inline-block;width:10px;height:10px;'
            f'border-radius:50%;background:{color}"></span>'
            f"{label}</span>"
        )
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)

    # --- Show details for selected node ---
    if selected_node and selected_node in node_details:
        with st.expander(f"Details: {selected_node}", expanded=True):
            st.markdown(node_details[selected_node])
