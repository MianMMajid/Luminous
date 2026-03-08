from __future__ import annotations

import streamlit as st

from src.models import BioContext, ProteinQuery, TrustAudit


def render_context_panel():
    """Tab 3: Biological context and AI interpretation."""
    if not st.session_state.get("query_parsed"):
        st.info(
            "No query loaded yet. Go to the **Search** tab to enter a protein name, "
            "mutation, or paste a sequence. Try one of the example queries to get started."
        )
        return

    query: ProteinQuery | None = st.session_state.get("parsed_query")
    if query is None:
        st.info("No parsed query found. Go to the **Search** tab to get started.")
        return
    bio_context: BioContext | None = st.session_state.get("bio_context")
    interpretation: str | None = st.session_state.get("interpretation")
    trust_audit: TrustAudit | None = st.session_state.get("trust_audit")

    # Fetch context if not already done
    if bio_context is None:
        st.markdown(
            "### Gather biological context\n"
            "Query PubMed, Open Targets, Wiley, and ChEMBL to understand the "
            "clinical significance of your protein."
        )
        if st.button("Fetch Biological Context", type="primary"):
            _fetch_and_interpret(query, trust_audit)
            st.rerun()
        return

    # Auto-generate interpretation if context exists but interpretation doesn't
    # Guard with a flag to prevent re-triggering on every rerun
    if interpretation is None and trust_audit is not None and not st.session_state.get("_interpretation_attempted"):
        st.session_state["_interpretation_attempted"] = True
        try:
            from src.interpreter import generate_interpretation
            interpretation = generate_interpretation(query, trust_audit, bio_context)
        except Exception:
            from src.interpreter import _fallback_interpretation
            interpretation = _fallback_interpretation(query, trust_audit, bio_context)
        st.session_state["interpretation"] = interpretation

    # --- Display results ---

    # AI Interpretation (the headline)
    if interpretation:
        st.markdown("### AI Interpretation")
        st.markdown(interpretation)
        st.markdown(
            '<div style="text-align:right;font-size:0.75rem;color:rgba(60,60,67,0.55);margin-top:4px">'
            '<span style="color:#007AFF">&#9679;</span> '
            'Interpretation powered by <strong>Anthropic Claude</strong> '
            '&mdash; context via <strong>BioMCP</strong> (PubMed, Open Targets, Wiley, ChEMBL)'
            '</div>',
            unsafe_allow_html=True,
        )
        st.divider()

    # Scroll safety: limit expander content height in columns so many items
    # don't push adjacent content off-screen
    st.markdown(
        "<style>"
        ".context-cols details[data-testid='stExpander'][open] "
        "[data-testid='stExpanderDetails'] "
        "{ max-height: 50vh; overflow-y: auto; -webkit-overflow-scrolling: touch; "
        "overscroll-behavior-y: contain; padding-right: 4px; }"
        "</style>"
        '<div class="context-cols"></div>',
        unsafe_allow_html=True,
    )

    # Query-aware context summary — connect data to the scientist's question
    _CONTEXT_FOCUS = {
        "structure": "Showing biological context for structural interpretation.",
        "mutation_impact": "Focusing on disease associations and clinical significance of this mutation.",
        "druggability": "Focusing on drug candidates, binding mechanisms, and therapeutic context.",
        "binding": "Focusing on interaction partners, binding pathways, and interface biology.",
    }
    focus_msg = _CONTEXT_FOCUS.get(query.question_type, "")
    if focus_msg:
        st.caption(focus_msg)

    # Two-column layout for structured data
    left, right = st.columns(2)

    with left:
        # Disease Associations — prioritize by query type
        if bio_context.disease_associations:
            diseases = bio_context.disease_associations
            # For druggability: only show high-confidence drug-actionable diseases
            if query.question_type == "druggability":
                diseases = [d for d in diseases if d.score is None or d.score > 0.4]
            with st.expander(
                f"Disease Associations ({len(diseases)})",
            ):
                for da in diseases:
                    score_pct = f"{da.score:.0%}" if da.score is not None else ""
                    score_color = (
                        "#FF3B30" if da.score and da.score > 0.7
                        else "#FF9500" if da.score and da.score > 0.4
                        else "#16A34A"
                    ) if da.score is not None else "#16A34A"
                    st.markdown(
                        f'<div class="glow-card" style="padding:8px 12px;margin-bottom:6px">'
                        f'<span style="font-weight:600">{da.disease}</span>'
                        f'{f" <span style=&quot;float:right;color:{score_color};font-weight:700&quot;>{score_pct}</span>" if score_pct else ""}'
                        f'{"<br><span style=&quot;font-size:0.82em;color:rgba(60,60,67,0.6)&quot;>" + da.evidence + "</span>" if da.evidence else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Pathways
        if bio_context.pathways:
            with st.expander(f"Pathways ({len(bio_context.pathways)})"):
                for pathway in bio_context.pathways:
                    st.markdown(f"- {pathway}")

    with right:
        # Drug Candidates
        if bio_context.drugs:
            with st.expander(
                f"Drug Candidates ({len(bio_context.drugs)})",
            ):
                for drug in bio_context.drugs:
                    phase = drug.phase or ""
                    phase_color = (
                        "#34C759" if "approved" in phase.lower()
                        else "#007AFF" if "phase" in phase.lower()
                        else "#8E8E93"
                    )
                    st.markdown(
                        f'<div class="glow-card" style="padding:8px 12px;margin-bottom:6px">'
                        f'<span style="font-weight:600">{drug.name}</span>'
                        f'{f" <span style=&quot;float:right;color:{phase_color};font-size:0.82em;font-weight:600&quot;>{phase}</span>" if phase else ""}'
                        f'{"<br><span style=&quot;font-size:0.82em;color:rgba(60,60,67,0.6)&quot;>" + drug.mechanism + "</span>" if drug.mechanism else ""}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

        # Literature
        if bio_context.literature.key_findings:
            with st.expander(
                f"Recent Literature ({bio_context.literature.total_papers} papers)",
            ):
                if bio_context.literature.recent_papers:
                    st.metric(
                        "Recent Papers",
                        bio_context.literature.recent_papers,
                    )
                for finding in bio_context.literature.key_findings:
                    st.markdown(f"- {finding}")

                # Paper titles with DOI links
                if bio_context.literature.paper_titles:
                    st.markdown("---")
                    st.markdown("**Referenced Papers**")
                    for idx, title in enumerate(bio_context.literature.paper_titles):
                        doi = (
                            bio_context.literature.dois[idx]
                            if idx < len(bio_context.literature.dois)
                            else None
                        )
                        if doi:
                            doi_url = (
                                f"https://doi.org/{doi}"
                                if not doi.startswith("http")
                                else doi
                            )
                            st.markdown(
                                f'<div style="margin-bottom:4px;font-size:0.88em">'
                                f'<a href="{doi_url}" target="_blank" '
                                f'style="color:#007AFF;text-decoration:none">'
                                f'{title}</a> '
                                f'<span style="color:rgba(60,60,67,0.55);font-size:0.85em">'
                                f'DOI: {doi}</span>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                        else:
                            st.markdown(
                                f'<div style="margin-bottom:4px;font-size:0.88em">'
                                f'{title}</div>',
                                unsafe_allow_html=True,
                            )

    # Pin buttons for Playground
    from components.playground import pin_button

    pin_cols = st.columns(3)
    with pin_cols[0]:
        if bio_context.disease_associations:
            diseases = [
                {"disease": d.disease, "score": d.score}
                for d in bio_context.disease_associations[:10]
            ]
            pin_button(
                "Disease Associations",
                f"{len(bio_context.disease_associations)} diseases linked",
                "finding",
                {"diseases": diseases},
                key="pin_diseases",
            )
    with pin_cols[1]:
        if bio_context.drugs:
            pin_button(
                "Drug Candidates",
                f"{len(bio_context.drugs)} drugs/candidates identified",
                "finding",
                {"drugs": [{"name": d.name, "phase": d.phase} for d in bio_context.drugs[:10]]},
                key="pin_drugs",
            )
    with pin_cols[2]:
        if interpretation:
            pin_button(
                "AI Interpretation",
                interpretation[:100] + "..." if len(interpretation) > 100 else interpretation,
                "observation",
                {"text": interpretation},
                key="pin_interpretation",
            )

    # Send disease association scores to Statistics tab
    if bio_context.disease_associations:
        import pandas as pd

        if st.button("Analyze in Statistics", key="ctx_send_stats",
                     help="Send disease association scores to the Statistics tab"):
            df = pd.DataFrame([{
                "disease": d.disease,
                "score": d.score,
                "evidence": d.evidence or "",
            } for d in bio_context.disease_associations])
            st.session_state["stats_data"] = df
            st.toast("Disease scores sent to Statistics tab!")

    # Sources badge bar
    _render_source_badges(bio_context)

    # Suggested Experiments (full width)
    suggestions = list(bio_context.suggested_experiments)
    if trust_audit and trust_audit.suggested_validation:
        suggestions.extend(trust_audit.suggested_validation)

    if suggestions:
        with st.expander("Suggested Experiments & Validation"):
            for exp in suggestions:
                st.markdown(f"- {exp}")

    # Hypothesis Generation Panel
    st.divider()
    if trust_audit:
        from components.hypothesis_panel import render_hypothesis_panel

        render_hypothesis_panel(query, trust_audit, bio_context)

    # Protein Knowledge Graph
    st.divider()
    try:
        from components.network_graph import render_protein_network

        render_protein_network(query, bio_context, trust_audit)
    except ImportError:
        pass


def _render_source_badges(bio_context: BioContext):
    """Show which MCP data sources were queried."""
    # Determine which sources are available — from literature metadata or defaults
    queried = bio_context.literature.sources if bio_context.literature.sources else []

    # Always show the canonical source list; highlight those actually queried
    all_sources = ["PubMed", "Open Targets", "Wiley", "BioRender"]
    badge_html_parts = []
    for src in all_sources:
        active = any(src.lower() in s.lower() for s in queried) if queried else False
        if active:
            badge_html_parts.append(
                f'<span style="display:inline-block;padding:2px 10px;margin:2px 4px;'
                f'border-radius:12px;font-size:0.78em;font-weight:600;'
                f'background:rgba(0,122,255,0.08);color:#007AFF;border:1px solid #007AFF">'
                f'{src}</span>'
            )
        else:
            badge_html_parts.append(
                f'<span style="display:inline-block;padding:2px 10px;margin:2px 4px;'
                f'border-radius:12px;font-size:0.78em;font-weight:600;'
                f'background:#F2F2F7;color:#8E8E93;border:1px solid #C6C6C8">'
                f'{src}</span>'
            )

    if badge_html_parts:
        st.markdown(
            '<div style="margin-top:12px;margin-bottom:8px">'
            '<span style="font-size:0.8em;color:rgba(60,60,67,0.6);margin-right:6px">Data Sources:</span>'
            + "".join(badge_html_parts)
            + "</div>",
            unsafe_allow_html=True,
        )


def _fetch_and_interpret(query: ProteinQuery, trust_audit: TrustAudit | None):
    """Fetch bio context and generate interpretation."""
    st.session_state["pipeline_running"] = True
    with st.status("Gathering biological context...", expanded=True) as status:
        bio_context = _fetch_context(query, status)
        st.session_state["bio_context"] = bio_context

        # Generate interpretation if we have a trust audit
        if trust_audit:
            st.write("Generating AI interpretation...")
            try:
                from src.interpreter import generate_interpretation

                interpretation = generate_interpretation(
                    query, trust_audit, bio_context
                )
                st.session_state["interpretation"] = interpretation
                st.write("Interpretation ready.")
            except Exception as e:
                st.write(f"Interpretation generation failed: {e}")
                # Generate fallback interpretation
                from src.interpreter import _fallback_interpretation

                st.session_state["interpretation"] = _fallback_interpretation(
                    query, trust_audit, bio_context
                )
        else:
            st.write("No trust audit available yet — skipping interpretation.")
            st.session_state["interpretation"] = None

        status.update(label="Context gathered!", state="complete")
    st.session_state["pipeline_running"] = False


def _fetch_context(query: ProteinQuery, status) -> BioContext:
    """Try MCP connector, then BioMCP CLI, then empty context."""
    # Path A: Anthropic MCP connector
    st.write("Querying PubMed, Open Targets, Wiley via Claude MCP...")
    try:
        from src.bio_context import fetch_bio_context_mcp

        ctx = fetch_bio_context_mcp(query)
        if ctx.narrative or ctx.disease_associations or ctx.drugs:
            st.write("MCP context retrieved.")
            return ctx
        st.write("MCP returned empty results, trying BioMCP...")
    except Exception as e:
        st.write(f"MCP failed: {e}. Trying BioMCP CLI...")

    # Path B: BioMCP direct
    try:
        from src.bio_context_direct import fetch_bio_context_direct

        ctx = fetch_bio_context_direct(query)
        st.write("BioMCP context retrieved.")
        return ctx
    except Exception as e:
        st.write(f"BioMCP also failed: {e}. Using minimal context.")

    return BioContext()
