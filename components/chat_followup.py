from __future__ import annotations

import streamlit as st

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit


def render_chat_followup():
    """Tab 7: Conversational AI follow-up — ask Lumi anything about the loaded protein."""
    if not st.session_state.get("query_parsed"):
        _render_welcome_empty()
        return

    query: ProteinQuery | None = st.session_state.get("parsed_query")
    if query is None:
        _render_welcome_empty()
        return
    trust_audit: TrustAudit | None = st.session_state.get("trust_audit")
    bio_context: BioContext | None = st.session_state.get("bio_context")
    interpretation: str | None = st.session_state.get("interpretation")
    prediction: PredictionResult | None = st.session_state.get("prediction_result")

    # Agent Mode toggle
    header_col, toggle_col = st.columns([3, 1])
    with header_col:
        st.markdown(
            f"### Ask Lumi about {query.protein_name}"
        )
    with toggle_col:
        if "agent_mode_toggle" not in st.session_state:
            st.session_state["agent_mode_toggle"] = True
        agent_mode = st.toggle(
            "Agent Mode",
            key="agent_mode_toggle",
            help="Agent mode lets Lumi autonomously call analysis tools to answer your question.",
        )

    # Show available tools when agent mode is on
    if agent_mode:
        _render_tool_badges()

    # Initialize chat history
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Suggestion pills (Judge UI style)
    suggestions = _get_suggestions(query, trust_audit)
    if not st.session_state["chat_messages"]:
        pills_html = "".join(
            f'<span class="lumi-pill" style="cursor:default">{s}</span>'
            for s in suggestions[:4]
        )
        st.markdown(
            f'<div style="display:flex;flex-wrap:wrap;gap:8px;justify-content:center;'
            f'margin:12px 0 16px">{pills_html}</div>',
            unsafe_allow_html=True,
        )
        cols = st.columns(min(len(suggestions), 4))
        for i, (col, suggestion) in enumerate(zip(cols, suggestions[:4])):
            if col.button(
                suggestion[:40] + ("..." if len(suggestion) > 40 else ""),
                key=f"chat_suggest_{i}",
                use_container_width=True,
            ):
                st.session_state["chat_messages"].append(
                    {"role": "user", "content": suggestion}
                )
                if agent_mode:
                    _generate_agent_response(query, prediction, trust_audit, bio_context)
                else:
                    _generate_response(query, trust_audit, bio_context, interpretation)
                st.rerun()

    # Render chat history as iMessage-style bubbles
    if st.session_state["chat_messages"]:
        _render_chat_bubbles(st.session_state["chat_messages"])

    # Chat input (Streamlit's built-in, pinned to bottom)
    if prompt := st.chat_input(f"Ask Lumi about {query.protein_name}..."):
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})

        # Show typing indicator then generate response
        if agent_mode:
            with st.spinner("Lumi is thinking..."):
                _generate_agent_response(
                    query, prediction, trust_audit, bio_context
                )
        else:
            with st.spinner("Lumi is thinking..."):
                _generate_response(
                    query, trust_audit, bio_context, interpretation
                )
        st.rerun()


def _render_welcome_empty():
    """Show welcome state when no query is parsed — DNA Pixar animation + chat intro."""
    # DNA character SVG (animated version for this welcome screen)
    _dna_svg = (
        '<svg class="dna-char" viewBox="0 0 36 56" width="72" height="107"'
        ' style="width:72px!important;height:107px!important;min-width:72px;min-height:107px;max-width:none!important;max-height:none!important"'
        ' xmlns="http://www.w3.org/2000/svg">'
        '<ellipse class="dna-shadow" cx="18" cy="54" rx="8" ry="2"/>'
        '<g class="dna-body-group">'
        '<line class="dna-rung" x1="8" y1="18" x2="28" y2="18"/>'
        '<line class="dna-rung" x1="13" y1="24" x2="23" y2="24"/>'
        '<line class="dna-rung" x1="8" y1="30" x2="28" y2="30"/>'
        '<line class="dna-rung" x1="13" y1="36" x2="23" y2="36"/>'
        '<line class="dna-rung" x1="8" y1="42" x2="28" y2="42"/>'
        '<line class="dna-rung" x1="13" y1="48" x2="23" y2="48"/>'
        '<path class="dna-strand-blue" '
        'd="M8,15 C8,19 28,21 28,25 C28,29 8,31 8,35 C8,39 28,41 28,45 C28,49 13,50 13,52"/>'
        '<path class="dna-strand-green" '
        'd="M28,15 C28,19 8,21 8,25 C8,29 28,31 28,35 C28,39 8,41 8,45 C8,49 23,50 23,52"/>'
        '<circle cx="8" cy="18" r="2.2" fill="#007AFF"/>'
        '<circle cx="28" cy="18" r="2.2" fill="#34C759"/>'
        '<circle cx="28" cy="30" r="2.2" fill="#007AFF"/>'
        '<circle cx="8" cy="30" r="2.2" fill="#34C759"/>'
        '<circle cx="8" cy="42" r="2.2" fill="#007AFF"/>'
        '<circle cx="28" cy="42" r="2.2" fill="#34C759"/>'
        '</g>'
        '<defs>'
        '<clipPath id="eyeL"><circle cx="12" cy="9" r="5.5"/></clipPath>'
        '<clipPath id="eyeR"><circle cx="24" cy="9" r="5.5"/></clipPath>'
        '</defs>'
        '<circle class="dna-eye-white" cx="12" cy="9" r="5.5"/>'
        '<circle class="dna-pupil" cx="12.8" cy="9.2" r="2.8"/>'
        '<circle class="dna-eye-white" cx="24" cy="9" r="5.5"/>'
        '<circle class="dna-pupil" cx="24.8" cy="9.2" r="2.8"/>'
        '<circle cx="10.5" cy="7.5" r="1.2" fill="white" opacity="0.9"/>'
        '<circle cx="22.5" cy="7.5" r="1.2" fill="white" opacity="0.9"/>'
        '<rect class="dna-eyelid" x="6.5" y="3.5" width="11" height="11"'
        ' clip-path="url(#eyeL)" fill="#E8E8ED"/>'
        '<rect class="dna-eyelid dna-eyelid-r" x="18.5" y="3.5" width="11" height="11"'
        ' clip-path="url(#eyeR)" fill="#E8E8ED"/>'
        '</svg>'
    )

    st.markdown(
        '<div class="lumi-welcome">'
        # DNA Pixar title: "Lum[DNA]nous"
        '<div class="lumi-title">'
        'Lum'
        '<span class="lumi-i-wrapper">'
        '<span class="lumi-letter-i">i</span>'
        '<span class="dna-slot">' + _dna_svg + '</span>'
        '</span>'
        'nous'
        '</div>'
        '<p class="lumi-welcome-sub">'
        "I'm Lumi, your assistant scientist. Load a protein in the <b>Query</b> tab "
        "for full structural analysis, or ask me anything below — I can query UniProt, "
        "AlphaFold, gnomAD, PubChem, STRING, and more in real time."
        "</p>"
        '<div class="lumi-welcome-pills">'
        '<span class="lumi-pill">Tell me about TP53 and its role in cancer</span>'
        '<span class="lumi-pill">What drugs target EGFR?</span>'
        '<span class="lumi-pill">Is KRAS G12C druggable?</span>'
        '<span class="lumi-pill">Find recent papers on BRCA1 structure</span>'
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )

    # Allow chat even without loaded protein (agent mode with online tools)
    _render_standalone_chat()


def _render_chat_bubbles(messages: list[dict]):
    """Render chat history as iMessage-style bubbles with scroll safety."""
    import html as html_mod

    bubble_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool_calls":
            for tc in msg.get("calls", []):
                tool_name = html_mod.escape(tc.get("tool", "unknown"))
                output_text = html_mod.escape(tc.get("output", "")[:300])
                bubble_parts.append(
                    f'<details class="lumi-tool-call">'
                    f"<summary>Called: {tool_name}</summary>"
                    f"<pre>{output_text}</pre>"
                    f"</details>"
                )
        elif role == "user":
            content = html_mod.escape(msg.get("content", ""))
            bubble_parts.append(
                f'<div class="lumi-bubble user">{content}</div>'
            )
            bubble_parts.append('<div class="lumi-delivered">Delivered</div>')
        elif role == "assistant":
            # Allow markdown rendering in assistant bubbles
            content = msg.get("content", "")
            # Basic markdown: bold, italic, links, code
            import re

            safe = html_mod.escape(content)
            # Restore markdown bold
            safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
            # Restore markdown italic
            safe = re.sub(r"\*(.+?)\*", r"<i>\1</i>", safe)
            # Restore inline code
            safe = re.sub(r"`(.+?)`", r"<code>\1</code>", safe)
            # Restore line breaks
            safe = safe.replace("\n", "<br>")
            bubble_parts.append(
                f'<div class="lumi-bubble assistant">{safe}</div>'
            )

    all_bubbles = "\n".join(bubble_parts)
    st.markdown(
        f'<div class="lumi-chat-container">{all_bubbles}</div>',
        unsafe_allow_html=True,
    )
    # Auto-scroll hint via invisible anchor
    st.markdown(
        '<div id="lumi-chat-bottom"></div>'
        "<script>document.getElementById('lumi-chat-bottom')?.scrollIntoView({behavior:'smooth'})</script>",
        unsafe_allow_html=True,
    )


def _render_tool_badges():
    """Show available agent tools as a compact dropdown with descriptions."""
    try:
        from src.bio_agent import get_tool_schemas
        tools = get_tool_schemas()
    except ImportError:
        return

    if not tools:
        return

    local_tools = {
        "analyze_structure", "build_trust_audit", "predict_pockets",
        "compute_flexibility", "generate_hypotheses", "search_variants",
        "fetch_bio_context", "compute_surface_properties", "predict_ptm_sites",
        "compute_conservation", "predict_disorder", "compare_structures",
        "auto_investigate", "build_protein_network", "find_communication_path",
        "compute_residue_depth",
    }
    biorender_tools = {
        "search_biorender_templates", "search_biorender_icons",
        "generate_figure_prompt",
    }

    # Split into categories
    local = [t for t in tools if t["name"] in local_tools]
    biorender = [t for t in tools if t["name"] in biorender_tools]
    online = [t for t in tools if t["name"] not in local_tools and t["name"] not in biorender_tools]

    def _tool_row(t: dict, icon: str, color: str) -> str:
        desc = t["description"][:80] + ("..." if len(t["description"]) > 80 else "")
        return (
            f'<div style="display:flex;align-items:baseline;gap:6px;padding:3px 0;'
            f'border-bottom:1px solid rgba(0,0,0,0.04)">'
            f'<span style="font-size:0.82rem;font-weight:600;color:{color};'
            f'white-space:nowrap">{icon} {t["name"]}</span>'
            f'<span style="font-size:0.75rem;color:rgba(60,60,67,0.5)">{desc}</span></div>'
        )

    def _section_header(title: str) -> str:
        return (
            f'<div style="font-size:0.78rem;font-weight:600;color:rgba(60,60,67,0.5);'
            f'text-transform:uppercase;letter-spacing:0.5px;margin:8px 0 4px">{title}</div>'
        )

    with st.expander(f"Lumi's Tools ({len(tools)})"):
        if local:
            st.markdown(_section_header("Local Analysis"), unsafe_allow_html=True)
            for t in local:
                st.markdown(_tool_row(t, "&#128300;", "#000"), unsafe_allow_html=True)

        if online:
            st.markdown(_section_header("Online Databases"), unsafe_allow_html=True)
            for t in online:
                st.markdown(_tool_row(t, "&#127760;", "#2563EB"), unsafe_allow_html=True)

        if biorender:
            st.markdown(_section_header("BioRender Illustrations"), unsafe_allow_html=True)
            for t in biorender:
                st.markdown(_tool_row(t, "&#127912;", "#FF6B35"), unsafe_allow_html=True)


def _get_suggestions(
    query: ProteinQuery, trust_audit: TrustAudit | None
) -> list[str]:
    p = query.protein_name
    suggestions: list[str] = []

    # Mutation-specific suggestions (highest priority)
    if query.mutation:
        suggestions.append(
            f"What is the clinical significance of {query.mutation} in {p}? "
            "Check VEP, gnomAD, and literature."
        )
        suggestions.append(
            f"How does {query.mutation} affect {p} structure and function?"
        )

    # Question-type-specific
    if query.question_type == "druggability":
        suggestions.append(
            f"What drugs target {p}? Look up compounds and clinical annotations."
        )
    elif query.question_type == "binding":
        suggestions.append(
            f"What are {p}'s top interaction partners and binding pockets?"
        )

    # General protein investigation (always useful)
    suggestions.extend([
        f"Give me a full research briefing on {p} — function, domains, disease links.",
        f"What proteins interact with {p} and what pathways are involved?",
        f"Are there experimental structures for {p}? How do they compare to the prediction?",
    ])

    # Confidence-specific
    if trust_audit and trust_audit.overall_confidence == "low":
        suggestions.insert(1, f"Which regions of {p} are unreliable and why?")

    return suggestions[:6]


def _generate_agent_response(
    query: ProteinQuery,
    prediction: PredictionResult | None,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
) -> str:
    """Generate response using Claude Agent SDK with tool use."""
    if not ANTHROPIC_API_KEY:
        return _fallback_response()

    try:
        from src.bio_agent import run_agent_turn
    except ImportError:
        # Fall back to simple chat if agent SDK not available
        return _generate_response(query, trust_audit, bio_context, None)

    import re

    # Build session context from loaded data
    mutation_pos = None
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mutation_pos = int(m.group(1))

    session_context = {
        "query": query,
        "protein_name": query.protein_name,
        "mutation": query.mutation,
        "mutation_pos": mutation_pos,
        "pdb_content": prediction.pdb_content if prediction else "",
        "trust_audit": trust_audit,
        "bio_context": bio_context,
        "confidence_json": {},
        "variant_data": st.session_state.get(f"variant_data_{query.protein_name}"),
    }

    # Build messages (only user/assistant, skip tool_calls entries)
    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state["chat_messages"]
        if msg["role"] in ("user", "assistant")
    ]

    try:
        assistant_text, tool_calls = run_agent_turn(messages, session_context)
    except Exception as e:
        assistant_text = f"Agent encountered an error: {e}. Falling back to simple mode."
        tool_calls = []

    # Record tool calls in chat history for display
    if tool_calls:
        st.session_state["chat_messages"].append({
            "role": "tool_calls",
            "calls": tool_calls,
        })

    # Auto-append BioRender suggestions if relevant tools were called
    biorender_suggestion = _get_biorender_suggestion_for_tools(tool_calls, query)
    if biorender_suggestion:
        assistant_text += biorender_suggestion

    # Append attribution
    attribution = (
        "\n\n---\n"
        "*Powered by Anthropic Claude Agent SDK "
        "| Structure via Tamarind Bio / Modal "
        "| Context via BioMCP | Figures via BioRender*"
    )
    display_text = assistant_text + attribution
    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": display_text}
    )
    return display_text


def _generate_response(
    query: ProteinQuery,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
) -> str:
    """Generate Claude response with citations and streaming."""
    if not ANTHROPIC_API_KEY:
        return _fallback_response()

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    system = _build_system_prompt(query, trust_audit, bio_context, interpretation)

    # Build user content with citation documents
    documents = _build_chat_documents(bio_context, interpretation)

    # Build messages — inject documents into the latest user message
    raw_messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state["chat_messages"]
        if msg["role"] in ("user", "assistant")
    ]

    if raw_messages and documents:
        # Add documents to the last user message
        last_user_text = raw_messages[-1]["content"]
        raw_messages[-1]["content"] = [
            *documents,
            {"type": "text", "text": last_user_text},
        ]

    # Stream the response for real-time UX
    try:
        assistant_text = ""
        sources: list[str] = []
        source_map: dict[str, int] = {}

        with client.messages.stream(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=system,
            messages=raw_messages,
        ) as stream:
            for event in stream:
                pass  # consume stream
            response = stream.get_final_message()

        # Format response with citation footnotes
        for block in response.content:
            if not hasattr(block, "text"):
                continue
            citations = getattr(block, "citations", None) or []
            if citations:
                refs = []
                for cite in citations:
                    doc_title = getattr(
                        cite, "document_title", None
                    ) or "Source"
                    cited_text = getattr(
                        cite, "cited_text", None
                    ) or ""
                    key = f"{doc_title}:{cited_text[:80]}"
                    if key not in source_map:
                        source_map[key] = len(sources) + 1
                        excerpt = (
                            cited_text[:100] + "..."
                            if len(cited_text) > 100
                            else cited_text
                        )
                        sources.append(
                            f"**[{source_map[key]}]** "
                            f"*{doc_title}* — \"{excerpt}\""
                        )
                    refs.append(str(source_map[key]))
                ref_str = ",".join(refs)
                assistant_text += f"{block.text} [{ref_str}]"
            else:
                assistant_text += block.text

        if sources:
            assistant_text += "\n\n---\n**Sources:** "
            assistant_text += " | ".join(
                f"[{i+1}] *{s.split('*')[1]}*"
                if '*' in s else f"[{i+1}]"
                for i, s in enumerate(sources)
            )
    except Exception as e:
        # Fallback to non-streaming, non-citation call
        err = str(e)
        if "credit balance" in err.lower() or "billing" in err.lower():
            assistant_text = (
                "Anthropic API credits exhausted. "
                "Please add credits at [console.anthropic.com](https://console.anthropic.com)."
            )
        else:
            try:
                response = client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=2048,
                    system=system,
                    messages=[
                        {"role": msg["role"], "content": msg["content"]}
                        for msg in st.session_state["chat_messages"]
                        if msg["role"] in ("user", "assistant")
                    ],
                )
                assistant_text = response.content[0].text if response.content else "No response generated."
            except Exception as e2:
                err2 = str(e2)
                if "credit balance" in err2.lower() or "billing" in err2.lower():
                    assistant_text = (
                        "Anthropic API credits exhausted. "
                        "Please add credits at [console.anthropic.com](https://console.anthropic.com)."
                    )
                else:
                    assistant_text = f"I encountered an error: {err2[:200]}"

    attribution = (
        "\n\n---\n"
        "*Powered by Anthropic Claude (Citations API) "
        "| Structure via Tamarind Bio / Modal "
        "| Context via BioMCP*"
    )
    display_text = assistant_text + attribution
    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": display_text}
    )
    return display_text


def _build_chat_documents(
    bio_context: BioContext | None,
    interpretation: str | None,
) -> list[dict]:
    """Build citation document blocks from bio_context for chat."""
    documents = []
    if not bio_context:
        return documents

    if bio_context.narrative:
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": bio_context.narrative[:3000],
            },
            "title": "Biological Context",
            "citations": {"enabled": True},
        })

    if bio_context.disease_associations:
        disease_text = "\n".join(
            f"{d.disease}"
            + (f" (score: {d.score})" if d.score else "")
            for d in bio_context.disease_associations[:8]
        )
        if disease_text:
            documents.append({
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": disease_text,
                },
                "title": "Disease Associations",
                "citations": {"enabled": True},
            })

    if bio_context.drugs:
        drug_text = "\n".join(
            f"{d.name}"
            + (f" ({d.phase})" if d.phase else "")
            + (f" — {d.mechanism}" if d.mechanism else "")
            for d in bio_context.drugs[:8]
        )
        if drug_text:
            documents.append({
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": drug_text,
                },
                "title": "Drug Candidates",
                "citations": {"enabled": True},
            })

    if bio_context.literature.key_findings:
        lit_text = "\n".join(
            bio_context.literature.key_findings[:8]
        )
        if lit_text:
            documents.append({
                "type": "document",
                "source": {
                    "type": "text",
                    "media_type": "text/plain",
                    "data": lit_text,
                },
                "title": "Recent Literature",
                "citations": {"enabled": True},
            })

    if interpretation:
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": interpretation[:2000],
            },
            "title": "AI Interpretation",
            "citations": {"enabled": True},
        })

    return documents


def _build_system_prompt(
    query: ProteinQuery,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
) -> str:
    parts = [
        "You are Lumi, Luminous's assistant scientist and structural biology expert. "
        "You help researchers interpret AI-predicted protein structures. You have access to "
        "the analysis results below for the current protein. Answer questions clearly and "
        "scientifically, always noting prediction confidence and limitations. Use markdown. "
        "In agent mode, you can query UniProt, AlphaFold DB, Ensembl VEP, gnomAD, STRING, "
        "InterPro, PubChem, PharmGKB, Semantic Scholar, Europe PMC, and RCSB PDB live. "
        "Suggest switching to agent mode when the user asks questions requiring database lookups.",
        "",
        "Luminous integrates with Tamarind Bio's 200+ computational biology tools including: "
        "Boltz-2 (structure+affinity), ESMFold (fast structure), AutoDock Vina/GNINA/DiffDock "
        "(molecular docking), ProteinMPNN-ddG/ThermoMPNN (mutation stability), BoltzGen "
        "(de novo binder design, 60-70% hit rate), RFdiffusion (protein backbone design), "
        "REINVENT 4 (small molecule design), Aggrescan3D (aggregation), CamSol (solubility), "
        "TemStaPro (thermostability), MaSIF (surface fingerprinting), PRODIGY (binding energy), "
        "RFantibody (antibody design), BioPhi (humanization), and many more. "
        "When relevant, suggest specific Tamarind tools the researcher should run next.",
        "",
        f"## Current Protein: {query.protein_name}",
        f"Question type: {query.question_type}",
    ]
    if query.mutation:
        parts.append(f"Mutation: {query.mutation}")
    if query.interaction_partner:
        parts.append(f"Interaction partner: {query.interaction_partner}")
    if query.uniprot_id:
        parts.append(f"UniProt ID: {query.uniprot_id}")

    if trust_audit:
        parts.append("\n## Trust Audit Results")
        parts.append(
            f"Overall confidence: {trust_audit.overall_confidence} "
            f"({trust_audit.confidence_score:.2%})"
        )
        if trust_audit.ptm is not None:
            parts.append(f"pTM: {trust_audit.ptm:.3f}")
        if trust_audit.iptm is not None:
            parts.append(f"ipTM: {trust_audit.iptm:.3f}")
        flagged = [r for r in trust_audit.regions if r.flag]
        if flagged:
            parts.append(f"Flagged regions: {len(flagged)}")
            for r in flagged[:5]:
                parts.append(
                    f"  - Chain {r.chain} {r.start_residue}-{r.end_residue}: "
                    f"avg pLDDT {r.avg_plddt}"
                )
        if trust_audit.known_limitations:
            parts.append("Known limitations:")
            for lim in trust_audit.known_limitations:
                parts.append(f"  - {lim}")
        if trust_audit.training_data_note:
            parts.append(f"Training data note: {trust_audit.training_data_note}")

    if bio_context:
        parts.append("\n## Biological Context")
        if bio_context.narrative:
            parts.append(bio_context.narrative)
        if bio_context.disease_associations:
            parts.append("Disease associations:")
            for d in bio_context.disease_associations[:5]:
                parts.append(f"  - {d.disease}" + (f" (score: {d.score})" if d.score else ""))
        if bio_context.drugs:
            parts.append("Known drugs:")
            for drug in bio_context.drugs[:5]:
                parts.append(f"  - {drug.name}" + (f" ({drug.phase})" if drug.phase else ""))

    if interpretation:
        parts.append("\n## AI Interpretation (already generated)")
        parts.append(interpretation[:1000])

    return "\n".join(parts)


def _get_biorender_suggestion_for_tools(
    tool_calls: list[dict],
    query: ProteinQuery | None = None,
) -> str:
    """Generate contextual BioRender template suggestion based on agent tool usage.

    Returns markdown string to append to response, or empty string.
    """
    if not tool_calls:
        return ""

    # Don't suggest if BioRender tools were already called
    tools_used = {tc.get("tool", "") for tc in tool_calls}
    if tools_used & {"search_biorender_templates", "search_biorender_icons", "generate_figure_prompt"}:
        return ""

    _BR = "https://www.biorender.com"

    # Map tool usage to relevant BioRender templates
    suggestions: list[tuple[str, str]] = []

    if "lookup_compound" in tools_used or "get_pharmacogenomics" in tools_used:
        suggestions.append((
            "Drug Mechanism of Action",
            f"{_BR}/template/daptomycin-mechanism-of-action",
        ))
        suggestions.append((
            "Drug Discovery Pipeline",
            f"{_BR}/template/drug-discovery-development-funnel",
        ))

    if "get_interaction_network" in tools_used:
        suggestions.append((
            "Protein-Protein Interaction Network",
            f"{_BR}/template/protein-protein-interaction-ppi-network",
        ))

    if "predict_variant_effect" in tools_used or "check_population_frequency" in tools_used:
        suggestions.append((
            "Site-Directed Mutagenesis",
            f"{_BR}/template/site-directed-mutagenesis",
        ))

    if "predict_pockets" in tools_used:
        suggestions.append((
            "Protein-Ligand Binding",
            f"{_BR}/template/protein-ligand-binding",
        ))

    if "get_protein_info" in tools_used or "classify_domains" in tools_used:
        suggestions.append((
            "Protein Structure",
            f"{_BR}/template/protein-structure",
        ))

    if not suggestions:
        return ""

    # Format as compact markdown
    links = " | ".join(f"[{name}]({url})" for name, url in suggestions[:3])
    return f"\n\n**Create a figure:** {links} (BioRender)"


def _fallback_response() -> str:
    msg = (
        "I need an Anthropic API key to answer follow-up questions. "
        "Please set `ANTHROPIC_API_KEY` in your `.env` file."
    )
    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": msg}
    )
    return msg


def _render_standalone_chat():
    """Render chat interface when no protein is loaded — uses online tools only."""
    # Agent mode always on for standalone (online tools only)
    _render_tool_badges()

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Suggestion buttons for empty state
    if not st.session_state["chat_messages"]:
        standalone_suggestions = [
            "Tell me about TP53 — function, domains, and disease links",
            "What drugs target EGFR? Show me their properties and suggest a figure",
            "Is the KRAS G12C mutation clinically significant?",
            "Find BRCA1 interaction partners and suggest a pathway diagram",
        ]
        cols = st.columns(2)
        for i, suggestion in enumerate(standalone_suggestions):
            if cols[i % 2].button(
                suggestion[:50] + ("..." if len(suggestion) > 50 else ""),
                key=f"standalone_suggest_{i}",
                use_container_width=True,
            ):
                st.session_state["chat_messages"].append(
                    {"role": "user", "content": suggestion}
                )
                _generate_standalone_agent_response()
                st.rerun()

    # Show chat history
    if st.session_state["chat_messages"]:
        _render_chat_bubbles(st.session_state["chat_messages"])

    # Chat input
    if prompt := st.chat_input("Ask Lumi anything about proteins, drugs, variants..."):
        st.session_state["chat_messages"].append({"role": "user", "content": prompt})
        with st.spinner("Lumi is thinking..."):
            _generate_standalone_agent_response()
        st.rerun()


def _generate_standalone_agent_response() -> str:
    """Generate agent response without loaded protein (online tools only)."""
    if not ANTHROPIC_API_KEY:
        return _fallback_response()

    try:
        from src.bio_agent import run_agent_turn
    except ImportError:
        return _fallback_response()

    session_context = {
        "query": None,
        "protein_name": "",
        "mutation": None,
        "mutation_pos": None,
        "pdb_content": "",
        "trust_audit": None,
        "bio_context": None,
        "confidence_json": {},
        "variant_data": None,
    }

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state["chat_messages"]
        if msg["role"] in ("user", "assistant")
    ]

    try:
        assistant_text, tool_calls = run_agent_turn(messages, session_context)
    except Exception as e:
        assistant_text = f"I encountered an error: {e}"
        tool_calls = []

    if tool_calls:
        st.session_state["chat_messages"].append({
            "role": "tool_calls",
            "calls": tool_calls,
        })

    # Auto-append BioRender suggestions for standalone mode
    biorender_suggestion = _get_biorender_suggestion_for_tools(tool_calls)
    if biorender_suggestion:
        assistant_text += biorender_suggestion

    attribution = (
        "\n\n---\n"
        "*Powered by Anthropic Claude "
        "| Databases: UniProt, AlphaFold, gnomAD, STRING, PubChem, PharmGKB, "
        "Ensembl, InterPro, Semantic Scholar, RCSB PDB | Figures via BioRender*"
    )
    display_text = assistant_text + attribution
    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": display_text}
    )
    return display_text
