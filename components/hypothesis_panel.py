"""Hypothesis generation panel — the "so what?" engine.

This is what makes Luminous agentic: it doesn't just display data,
it generates actionable scientific hypotheses that connect
structure → variants → drugs → experiments.
"""
from __future__ import annotations

import streamlit as st

from src.models import BioContext, ProteinQuery, TrustAudit


def render_hypothesis_panel(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    """Render the hypothesis generation panel."""
    st.markdown("### AI-Generated Hypotheses")
    st.caption(
        "Claude analyzes the structure prediction, trust audit, variant landscape, "
        "and biological context to generate testable scientific hypotheses. "
        "This is the 'so what?' that turns predictions into action."
    )

    cache_key = "generated_hypotheses"
    hypotheses = st.session_state.get(cache_key)

    # Get variant data if available
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")

    if hypotheses is None:
        if st.button("Generate Hypotheses", type="primary", key="gen_hyp"):
            with st.spinner("Claude is reasoning over all available data..."):
                from src.hypothesis_engine import generate_hypotheses

                hypotheses = generate_hypotheses(
                    query, trust_audit, bio_context, variant_data
                )
                st.session_state[cache_key] = hypotheses
                st.rerun()
        else:
            # Show what data is available for hypothesis generation
            data_sources = ["Structure prediction", "Trust audit"]
            if bio_context and (bio_context.disease_associations or bio_context.drugs):
                data_sources.append("Biological context")
            if variant_data and variant_data.get("variants"):
                data_sources.append(f"Variant landscape ({variant_data['total']} variants)")

            st.info(
                "Click **Generate Hypotheses** to have Claude analyze your data and suggest "
                "testable scientific hypotheses based on the structure prediction, trust audit, "
                "and biological context.",
                icon="💡",
            )
            return

    st.markdown(hypotheses)

    # Next steps callout
    st.divider()
    _render_next_steps(query, trust_audit)


def _render_next_steps(query: ProteinQuery, trust_audit: TrustAudit):
    """Show actionable next steps with sponsor tool integration."""
    st.markdown("### What to Do Next")

    # Tamarind tools section — context-aware recommendations
    _render_tamarind_next_steps(query)

    st.markdown("---")
    cols = st.columns(3)

    with cols[0]:
        st.markdown(
            "**Validate Experimentally**  \n"
            "Key experiments to confirm computational findings:"
        )
        suggestions = trust_audit.suggested_validation[:3] if trust_audit.suggested_validation else [
            "X-ray crystallography or cryo-EM",
            "Thermal shift assay (DSF)",
            "Surface plasmon resonance (SPR)",
        ]
        for s in suggestions:
            st.markdown(f"- {s}")

    with cols[1]:
        st.markdown(
            "**Create Figures**  \n"
            "Use BioRender to create publication-ready figures "
            "for your findings."
        )
        st.link_button(
            "Open BioRender",
            "https://biorender.com",
            use_container_width=True,
        )

    with cols[2]:
        st.markdown(
            "**Run More Tools**  \n"
            "Scroll up to the **Tamarind Bio Computational Suite** "
            "to run docking, design, or property analyses."
        )


def _render_tamarind_next_steps(query: ProteinQuery):
    """Recommend specific Tamarind Bio tools based on query type."""
    st.markdown("**Tamarind Bio — Recommended Next Analyses:**")

    recs: list[tuple[str, str, str]] = []

    if query.question_type == "druggability":
        recs = [
            ("AutoDock Vina / GNINA", "Dock known drugs to the predicted structure", "https://app.tamarind.bio"),
            ("REINVENT 4", "Generate novel small molecules targeting this protein", "https://app.tamarind.bio"),
            ("MaSIF", "Map druggable surface patches", "https://app.tamarind.bio"),
        ]
    elif query.question_type == "mutation_impact":
        recs = [
            ("ProteinMPNN-ddG", "Quantify mutation stability impact (ddG)", "https://app.tamarind.bio"),
            ("ThermoMPNN", "Scan all possible mutations for stabilizing substitutions", "https://app.tamarind.bio"),
            ("CamSol", "Check if mutation affects protein solubility", "https://app.tamarind.bio"),
        ]
    elif query.question_type == "binding":
        recs = [
            ("BoltzGen", "Design de novo protein binders (60-70% hit rate)", "https://app.tamarind.bio"),
            ("PRODIGY", "Predict binding free energy and dissociation constant", "https://app.tamarind.bio"),
            ("RFdiffusion", "Design backbone scaffolds targeting binding interface", "https://app.tamarind.bio"),
        ]
    else:
        recs = [
            ("ESMFold", "Cross-validate with fast single-sequence prediction", "https://app.tamarind.bio"),
            ("Aggrescan3D", "Identify aggregation-prone regions", "https://app.tamarind.bio"),
            ("TemStaPro", "Predict protein thermostability", "https://app.tamarind.bio"),
        ]

    cols = st.columns(len(recs))
    for col, (tool, desc, url) in zip(cols, recs):
        with col:
            st.markdown(f"**{tool}**\n\n{desc}")
            st.link_button(
                f"Open {tool}",
                url,
                use_container_width=True,
            )
