from __future__ import annotations

import streamlit as st

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit


# ---------------------------------------------------------------------------
# Background chat helpers (run agent calls off the main thread)
# ---------------------------------------------------------------------------

def _run_agent_in_thread(
    messages: list[dict],
    session_context: dict,
    protein_name: str = "",
) -> dict:
    """Run agent turn in a background thread. Returns result dict."""
    try:
        from src.bio_agent import run_agent_turn
    except ImportError:
        return {"assistant_text": _fallback_text(), "tool_calls": []}

    try:
        assistant_text, tool_calls = run_agent_turn(messages, session_context)
    except Exception as e:
        assistant_text = f"I encountered an error: {e}"
        tool_calls = []

    return {"assistant_text": assistant_text, "tool_calls": tool_calls,
            "protein_name": protein_name}


def _fallback_text() -> str:
    return (
        "I need an Anthropic API key to answer follow-up questions. "
        "Please set `ANTHROPIC_API_KEY` in your `.env` file."
    )


def _submit_chat_background(messages, session_context, query=None):
    """Submit a chat agent call as a background task (non-blocking)."""
    from src.task_manager import task_manager

    task_manager.submit(
        task_id="chat_response",
        fn=_run_agent_in_thread,
        kwargs={"messages": messages, "session_context": session_context,
                "protein_name": query.protein_name if query else ""},
        label="Lumi is thinking",
    )


def _kick_chat_agent(query, prediction, trust_audit, bio_context):
    """Build context and submit agent call to background."""
    import re

    if not ANTHROPIC_API_KEY:
        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": _fallback_text()}
        )
        return

    mutation_pos = None
    if query and query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mutation_pos = int(m.group(1))

    session_context = {
        "query": query,
        "protein_name": query.protein_name if query else "",
        "mutation": query.mutation if query else None,
        "mutation_pos": mutation_pos,
        "pdb_content": prediction.pdb_content if prediction else "",
        "trust_audit": trust_audit,
        "bio_context": bio_context,
        "confidence_json": {},
        "variant_data": st.session_state.get(
            f"variant_data_{query.protein_name}" if query else "", None
        ),
    }

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state.get("chat_messages", [])
        if msg["role"] in ("user", "assistant")
    ]

    st.session_state["_chat_thinking"] = True
    _submit_chat_background(messages, session_context, query)


def _try_auto_parse(text: str):
    """Try to parse the user's text into a ProteinQuery and populate session state.

    This bridges the Lumi tab → Search/Structure/Biology tabs: if the user
    enters a protein query in the chat, we parse it so downstream tabs
    (Structure, Biology, Report) can render results immediately.
    """
    if st.session_state.get("query_parsed"):
        return  # already parsed — don't overwrite

    try:
        from src.query_parser import parse_query

        parsed = parse_query(text)
        if parsed and parsed.protein_name and parsed.protein_name.lower() != "unknown":
            st.session_state["parsed_query"] = parsed
            st.session_state["raw_query"] = text
            st.session_state["query_parsed"] = True
    except Exception:
        pass  # parsing failed — that's fine, chat still works


def _kick_standalone_agent():
    """Build context and submit standalone agent call to background.

    Even without a parsed query, pull any available session state
    so the agent has whatever context exists.
    """
    if not ANTHROPIC_API_KEY:
        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": _fallback_text()}
        )
        return

    # Pull whatever context is available from session state
    query = st.session_state.get("parsed_query")
    prediction = st.session_state.get("prediction_result")
    trust_audit = st.session_state.get("trust_audit")
    bio_context = st.session_state.get("bio_context")
    protein_name = query.protein_name if query else ""

    import re
    mutation_pos = None
    if query and query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mutation_pos = int(m.group(1))

    session_context = {
        "query": query,
        "protein_name": protein_name,
        "mutation": query.mutation if query else None,
        "mutation_pos": mutation_pos,
        "pdb_content": prediction.pdb_content if prediction else "",
        "trust_audit": trust_audit,
        "bio_context": bio_context,
        "confidence_json": prediction.confidence_json if prediction else {},
        "variant_data": st.session_state.get(
            f"variant_data_{protein_name}" if protein_name else "", None
        ),
    }

    messages = [
        {"role": msg["role"], "content": msg["content"]}
        for msg in st.session_state.get("chat_messages", [])
        if msg["role"] in ("user", "assistant")
    ]

    st.session_state["_chat_thinking"] = True
    _submit_chat_background(messages, session_context)


# ---------------------------------------------------------------------------
# Main render
# ---------------------------------------------------------------------------

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

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Suggestion pills (native Streamlit pills — compact, clickable)
    if not st.session_state["chat_messages"] and not st.session_state.get("_chat_thinking"):
        suggestions = _get_suggestions(query, trust_audit)
        short = [s[:55] + "..." if len(s) > 55 else s for s in suggestions[:4]]
        _lp, _cp, _rp = st.columns([1, 4, 1])
        with _cp:
            picked = st.pills(
                "Suggestions", short,
                key="chat_suggest_pills",
                label_visibility="collapsed",
            )
        if picked:
            idx = short.index(picked)
            full = suggestions[idx]
            st.session_state["chat_messages"].append({"role": "user", "content": full})
            _kick_chat_agent(query, prediction, trust_audit, bio_context)
            st.rerun()

    # Chat history (includes thinking bubble if agent is working)
    if st.session_state["chat_messages"] or st.session_state.get("_chat_thinking"):
        _render_chat_bubbles(
            st.session_state["chat_messages"],
            thinking=st.session_state.get("_chat_thinking", False),
        )

    # Compact toolbar + input
    _render_composer_toolbar()
    if prompt := st.chat_input(
        f"Ask about {query.protein_name}...",
        accept_file="multiple",
        file_type=["pdb", "cif", "fasta", "fa", "csv", "tsv", "png", "jpg", "jpeg", "txt"],
    ):
        text = prompt.text if hasattr(prompt, "text") else str(prompt)
        if hasattr(prompt, "files") and prompt.files:
            _handle_uploaded_files(prompt.files)
        if text.strip():
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            _kick_chat_agent(query, prediction, trust_audit, bio_context)
            st.rerun()


def _render_welcome_empty():
    """Show welcome state when no query is parsed — DNA Pixar animation + chat intro."""
    # DNA character SVG (animated version for this welcome screen)
    _dna_svg = (
        '<svg class="dna-char" viewBox="0 0 36 56" width="80" height="120"'
        ' style="width:80px!important;height:120px!important;min-width:80px;min-height:120px;max-width:none!important;max-height:none!important"'
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
        '<div class="lumi-welcome-page">'
        '<div class="lumi-welcome">'
        '<div class="lumi-title">'
        'Lum'
        '<span class="lumi-i-wrapper">'
        '<span class="lumi-letter-i">i</span>'
        '<span class="dna-slot">' + _dna_svg + '</span>'
        '</span>'
        'nous'
        '</div>'
        '<p class="lumi-welcome-sub">'
        "Shed light on the data"
        '</p>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Claude Analysis tip
    st.markdown(
        '<div style="text-align:center;margin:4px 0 8px;font-size:0.82rem;'
        'color:rgba(60,60,67,0.5);padding:0 16px;max-width:520px;margin-left:auto;margin-right:auto">'
        'Have CSV data? Head to the <b>Stats</b> tab for '
        '<span style="color:#648FFF;font-weight:600">Claude Analysis</span> '
        '— describe any statistical test in plain English.'
        '</div>',
        unsafe_allow_html=True,
    )

    # Centered suggestions — use equal columns so pills sit in the true center
    if not st.session_state.get("_chat_thinking"):
        _welcome_suggestions = [
            "Tell me about TP53 and its role in cancer",
            "What drugs target EGFR?",
            "Is KRAS G12C druggable?",
        ]
        _lpad, _pcol, _rpad = st.columns([1, 4, 1])
        with _pcol:
            picked = st.pills(
                "Suggestions", _welcome_suggestions,
                key="welcome_suggest_pills",
                label_visibility="collapsed",
            )
        if picked:
            st.session_state["chat_messages"] = [{"role": "user", "content": picked}]
            _try_auto_parse(picked)
            _kick_standalone_agent()
            st.rerun()

    # Show thinking indicator if agent is working
    if st.session_state.get("_chat_thinking"):
        _render_chat_bubbles(
            st.session_state.get("chat_messages", []),
            thinking=True,
        )

    # Chat input
    _render_standalone_chat_input_only()


def _render_chat_bubbles(messages: list[dict], *, thinking: bool = False):
    """Render chat history as iMessage-style bubbles with scroll safety."""
    import html as html_mod

    bubble_parts: list[str] = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "tool_calls":
            for tc in msg.get("calls", []):
                tool_name = html_mod.escape(tc.get("tool", "unknown"))
                raw_output = tc.get("output", "")
                # Show full output (up to 2000 chars) with nice formatting
                output_text = html_mod.escape(raw_output[:2000])
                if len(raw_output) > 2000:
                    output_text += "\n… (truncated)"
                # Format tool input params as compact summary
                tool_input = tc.get("input", {})
                input_summary = ""
                if isinstance(tool_input, dict) and tool_input:
                    params = [
                        f"<span style='color:#007AFF'>{html_mod.escape(str(k))}</span>="
                        f"<span style='color:#333'>{html_mod.escape(str(v)[:60])}</span>"
                        for k, v in list(tool_input.items())[:4]
                    ]
                    input_summary = (
                        f'<div style="font-size:0.78rem;color:rgba(60,60,67,0.6);'
                        f'padding:4px 8px;margin-bottom:4px">'
                        f'{", ".join(params)}</div>'
                    )
                bubble_parts.append(
                    f'<details class="lumi-tool-call" open>'
                    f'<summary style="font-weight:600;font-size:0.85rem">'
                    f'<span style="color:#007AFF">⚡</span> {tool_name}</summary>'
                    f'{input_summary}'
                    f'<pre style="max-height:300px;overflow-y:auto;'
                    f'font-size:0.78rem;white-space:pre-wrap;word-break:break-word">'
                    f'{output_text}</pre>'
                    f"</details>"
                )
        elif role == "user":
            content = html_mod.escape(msg.get("content", ""))
            bubble_parts.append(
                f'<div class="lumi-bubble user">{content}</div>'
            )
            bubble_parts.append('<div class="lumi-delivered">Delivered</div>')
        elif role == "assistant":
            # Render assistant messages with rich markdown support
            content = msg.get("content", "")
            import re

            safe = html_mod.escape(content)
            # Code blocks (triple backtick) — must be before inline code
            safe = re.sub(
                r"```(\w*)\n(.*?)```",
                r'<pre style="background:rgba(0,0,0,0.04);padding:8px 10px;'
                r'border-radius:6px;font-size:0.8rem;overflow-x:auto;'
                r'margin:6px 0"><code>\2</code></pre>',
                safe, flags=re.DOTALL,
            )
            # Markdown bold
            safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
            # Markdown italic
            safe = re.sub(r"\*(.+?)\*", r"<i>\1</i>", safe)
            # Inline code
            safe = re.sub(r"`(.+?)`", r"<code>\1</code>", safe)
            # Headers (### → h4, ## → h3, # → h3)
            safe = re.sub(r"^### (.+)$", r'<div style="font-weight:700;font-size:0.95rem;margin:8px 0 4px">\1</div>', safe, flags=re.MULTILINE)
            safe = re.sub(r"^## (.+)$", r'<div style="font-weight:700;font-size:1rem;margin:10px 0 4px">\1</div>', safe, flags=re.MULTILINE)
            # Horizontal rules
            safe = safe.replace("---", '<hr style="border:none;border-top:1px solid rgba(0,0,0,0.1);margin:8px 0">')
            # Bullet lists
            safe = re.sub(r"^- (.+)$", r'<div style="padding-left:12px">• \1</div>', safe, flags=re.MULTILINE)
            # Line breaks (for non-list, non-pre content)
            safe = safe.replace("\n", "<br>")
            bubble_parts.append(
                f'<div class="lumi-bubble assistant">{safe}</div>'
            )

    # Animated thinking bubble when agent is working in background
    if thinking:
        bubble_parts.append(
            '<div class="lumi-bubble assistant lumi-thinking">'
            '<span class="lumi-thinking-dots">'
            '<span></span><span></span><span></span>'
            '</span>'
            '</div>'
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


def _handle_uploaded_files(files):
    """Store uploaded files from chat_input into session state."""
    for f in files:
        name = f.name.lower()
        data = f.read()
        if name.endswith((".pdb", ".cif", ".mmcif")):
            st.session_state["_uploaded_pdb"] = data.decode(errors="replace")
        elif name.endswith((".fasta", ".fa")):
            st.session_state["_uploaded_sequence"] = data.decode(errors="replace")
        elif name.endswith((".csv", ".tsv")):
            import pandas as pd
            sep = "\t" if name.endswith(".tsv") else ","
            import io
            st.session_state["_uploaded_data"] = pd.read_csv(io.BytesIO(data), sep=sep)
        elif name.endswith((".png", ".jpg", ".jpeg")):
            st.session_state["_uploaded_image"] = data


# ── MCP-style tool categories ──────────────────────────────────────────
# Each tool: (id, display_name, short_description)
_TOOL_CATEGORIES = {
    "Structure": {
        "color": "#34C759",
        "tools": [
            ("analyze_structure", "Structural Analysis", "SASA, contacts, packing, Ramachandran"),
            ("build_trust_audit", "Trust Audit", "pLDDT confidence, flagged regions"),
            ("predict_pockets", "Binding Pockets", "Druggable site detection"),
            ("compute_flexibility", "Flexibility", "ANM normal-mode dynamics"),
            ("compute_surface_properties", "Surface Properties", "Hydrophobicity, charge"),
            ("compute_conservation", "Conservation", "Evolutionary residue scores"),
            ("compute_residue_depth", "Residue Depth", "Distance from surface"),
            ("predict_disorder", "Disorder Regions", "Intrinsically disordered segments"),
            ("predict_ptm_sites", "PTM Sites", "Post-translational modification prediction"),
        ],
    },
    "Databases": {
        "color": "#007AFF",
        "tools": [
            ("get_protein_info", "UniProt", "Function, domains, GO terms"),
            ("lookup_alphafold", "AlphaFold DB", "Pre-computed structure + pLDDT"),
            ("predict_variant_effect", "Ensembl VEP", "SIFT, PolyPhen pathogenicity"),
            ("check_population_frequency", "gnomAD", "Allele frequency, gene constraint"),
            ("get_interaction_network", "STRING", "Protein-protein interactions"),
            ("classify_domains", "InterPro", "Domain architecture, families"),
            ("lookup_compound", "PubChem", "Drug properties, Lipinski rules"),
            ("get_pharmacogenomics", "PharmGKB", "Drug-gene clinical annotations"),
            ("search_pdb_structures", "RCSB PDB", "Experimental structures"),
        ],
    },
    "Literature": {
        "color": "#5856D6",
        "tools": [
            ("search_literature", "Semantic Scholar", "Papers with citation metrics"),
            ("search_open_access_literature", "Europe PMC", "Open-access full-text"),
            ("fetch_bio_context", "BioMCP Context", "PubMed + Open Targets + ChEMBL"),
        ],
    },
    "AI & Design": {
        "color": "#FF9500",
        "tools": [
            ("fold_sequence", "ESMFold", "Predict structure from sequence"),
            ("generate_hypotheses", "Hypothesis Engine", "Testable scientific claims"),
            ("search_variants", "Variant Search", "ClinVar pathogenic variants"),
            ("compare_structures", "Structure Compare", "RMSD, per-residue deviation"),
            ("auto_investigate", "Auto-Investigate", "Multi-step deep analysis"),
        ],
    },
    "Illustration": {
        "color": "#FF6B35",
        "tools": [
            ("search_biorender_templates", "BioRender Templates", "Scientific figure templates"),
            ("search_biorender_icons", "BioRender Icons", "Molecular illustration assets"),
            ("generate_figure_prompt", "Figure Prompt", "AI figure composition"),
        ],
    },
}


def _render_composer_toolbar():
    """MCP-style categorized tool browser + file attach."""
    # Count total tools
    total = sum(len(cat["tools"]) for cat in _TOOL_CATEGORIES.values())

    with st.expander(f"Lumi's Tools ({total}) — Claude Agent SDK + Tool Use", expanded=False):
        for cat_name, cat_data in _TOOL_CATEGORIES.items():
            color = cat_data["color"]
            tools = cat_data["tools"]

            # Category header
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:6px;'
                f'margin:12px 0 6px;padding-bottom:4px;'
                f'border-bottom:1px solid rgba(0,0,0,0.05)">'
                f'<span style="width:8px;height:8px;border-radius:50%;'
                f'background:{color};display:inline-block;flex-shrink:0"></span>'
                f'<span style="font-size:0.78rem;font-weight:700;'
                f'color:rgba(60,60,67,0.6);text-transform:uppercase;'
                f'letter-spacing:0.4px">{cat_name}</span>'
                f'<span style="font-size:0.72rem;color:rgba(60,60,67,0.35);'
                f'margin-left:auto">{len(tools)}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Tool rows — 2-column grid for compact layout
            for i in range(0, len(tools), 2):
                cols = st.columns(2, gap="small")
                for j, col in enumerate(cols):
                    idx = i + j
                    if idx >= len(tools):
                        break
                    _tid, name, desc = tools[idx]
                    col.markdown(
                        f'<div style="display:flex;align-items:baseline;gap:5px;'
                        f'padding:4px 0">'
                        f'<span style="font-size:0.84rem;font-weight:600;'
                        f'color:{color};white-space:nowrap">{name}</span>'
                        f'<span style="font-size:0.75rem;color:rgba(60,60,67,0.45);'
                        f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap">'
                        f'{desc}</span></div>',
                        unsafe_allow_html=True,
                    )

    # ── Attach files ──
    with st.expander("Attach files", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            pdb_file = st.file_uploader(
                "Structure (PDB/CIF)", type=["pdb", "cif", "mmcif"],
                key="_attach_pdb",
            )
            if pdb_file:
                st.session_state["_uploaded_pdb"] = pdb_file.getvalue().decode(errors="replace")
                st.success(f"Loaded {pdb_file.name}")
            csv_file = st.file_uploader(
                "Data (CSV/TSV)", type=["csv", "tsv"],
                key="_attach_csv",
            )
            if csv_file:
                import pandas as pd
                try:
                    sep = "\t" if csv_file.name.endswith(".tsv") else ","
                    st.session_state["_uploaded_data"] = pd.read_csv(csv_file, sep=sep)
                    st.success(f"Loaded {csv_file.name}")
                except Exception as e:
                    st.error(f"Could not parse: {e}")
        with c2:
            seq_file = st.file_uploader(
                "Sequence (FASTA)", type=["fasta", "fa", "txt"],
                key="_attach_seq",
            )
            if seq_file:
                st.session_state["_uploaded_sequence"] = seq_file.getvalue().decode(errors="replace")
                st.success(f"Loaded {seq_file.name}")
            img_file = st.file_uploader(
                "Image (PNG/JPG)", type=["png", "jpg", "jpeg"],
                key="_attach_img",
            )
            if img_file:
                st.session_state["_uploaded_image"] = img_file.getvalue()
                st.success(f"Loaded {img_file.name}")


def _render_tool_badges():
    """MCP-style tool browser."""
    _render_composer_toolbar()


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


def _get_biorender_suggestion_for_tools(
    tool_calls: list[dict],
    query: ProteinQuery | None = None,
) -> str:
    """Generate contextual BioRender template suggestion based on agent tool usage."""
    if not tool_calls:
        return ""

    tools_used = {tc.get("tool", "") for tc in tool_calls}
    if tools_used & {"search_biorender_templates", "search_biorender_icons", "generate_figure_prompt"}:
        return ""

    _BR = "https://www.biorender.com"
    suggestions: list[tuple[str, str]] = []

    if "lookup_compound" in tools_used or "get_pharmacogenomics" in tools_used:
        suggestions.append(("Drug Mechanism of Action", f"{_BR}/template/daptomycin-mechanism-of-action"))
        suggestions.append(("Drug Discovery Pipeline", f"{_BR}/template/drug-discovery-development-funnel"))
    if "get_interaction_network" in tools_used:
        suggestions.append(("Protein-Protein Interaction Network", f"{_BR}/template/protein-protein-interaction-ppi-network"))
    if "predict_variant_effect" in tools_used or "check_population_frequency" in tools_used:
        suggestions.append(("Site-Directed Mutagenesis", f"{_BR}/template/site-directed-mutagenesis"))
    if "predict_pockets" in tools_used:
        suggestions.append(("Protein-Ligand Binding", f"{_BR}/template/protein-ligand-binding"))
    if "get_protein_info" in tools_used or "classify_domains" in tools_used:
        suggestions.append(("Protein Structure", f"{_BR}/template/protein-structure"))

    if not suggestions:
        return ""

    links = " | ".join(f"[{name}]({url})" for name, url in suggestions[:3])
    return f"\n\n**Create a figure:** {links} (BioRender)"


def _fallback_response() -> str:
    msg = _fallback_text()
    st.session_state["chat_messages"].append(
        {"role": "assistant", "content": msg}
    )
    return msg


def _render_standalone_chat_input_only():
    """Render just the chat input + history — no duplicate suggestions or tool badges."""
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Show chat history
    if st.session_state["chat_messages"] and not st.session_state.get("_chat_thinking"):
        _render_chat_bubbles(st.session_state["chat_messages"])

    # Chat input with attach button
    if prompt := st.chat_input(
        "Ask anything about proteins, drugs, variants...",
        accept_file="multiple",
        file_type=["pdb", "cif", "fasta", "fa", "csv", "tsv", "png", "jpg", "jpeg", "txt"],
    ):
        text = prompt.text if hasattr(prompt, "text") else str(prompt)
        if hasattr(prompt, "files") and prompt.files:
            _handle_uploaded_files(prompt.files)
        if text.strip():
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            _try_auto_parse(text)
            _kick_standalone_agent()
            st.rerun()


def _render_standalone_chat():
    """Render chat interface when no protein is loaded — uses online tools only."""
    _render_tool_badges()

    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    # Suggestion buttons for empty state
    if not st.session_state["chat_messages"] and not st.session_state.get("_chat_thinking"):
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
                width="stretch",
            ):
                st.session_state["chat_messages"].append(
                    {"role": "user", "content": suggestion}
                )
                _try_auto_parse(suggestion)
                _kick_standalone_agent()
                st.rerun()

    # Show chat history (with thinking bubble if active)
    if st.session_state["chat_messages"] or st.session_state.get("_chat_thinking"):
        _render_chat_bubbles(
            st.session_state["chat_messages"],
            thinking=st.session_state.get("_chat_thinking", False),
        )

    # Chat input with attach button
    if prompt := st.chat_input(
        "Ask anything about proteins, drugs, variants...",
        accept_file="multiple",
        file_type=["pdb", "cif", "fasta", "fa", "csv", "tsv", "png", "jpg", "jpeg", "txt"],
    ):
        text = prompt.text if hasattr(prompt, "text") else str(prompt)
        if hasattr(prompt, "files") and prompt.files:
            _handle_uploaded_files(prompt.files)
        if text.strip():
            st.session_state["chat_messages"].append({"role": "user", "content": text})
            _try_auto_parse(text)
            _kick_standalone_agent()
            st.rerun()


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
