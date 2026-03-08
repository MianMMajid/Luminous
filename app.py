from __future__ import annotations

from pathlib import Path

import streamlit as st

st.set_page_config(
    page_title="Luminous - The AI Structure Interpreter",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Load Custom CSS ---
_css_path = Path(__file__).parent / "assets" / "style.css"
if _css_path.exists():
    st.markdown(f"<style>{_css_path.read_text()}</style>", unsafe_allow_html=True)


# --- Session State Initialization ---
DEFAULTS = {
    "query_input": "",
    "query_parsed": False,
    "parsed_query": None,
    "raw_query": "",
    "prediction_result": None,
    "trust_audit": None,
    "bio_context": None,
    "interpretation": None,
    "active_tab": 0,
    "pipeline_running": False,
    "chat_messages": [],
    "tamarind_results": {},
    "playground_pinned": [],
    "playground_plan": None,
    "stats_data": None,
    "stats_results": None,
    "stats_survival_data": None,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val


def reset_results():
    """Clear all downstream results when a new query is submitted."""
    for key in [
        "prediction_result", "trust_audit", "bio_context",
        "interpretation", "stats_data", "stats_results",
        "stats_survival_data", "structure_analysis",
        "generated_hypotheses", "panel_figure_data",
        "graphical_abstract_svg", "figure_checklist_state",
        "experiment_tracker", "sketch_image_bytes",
        "sketch_interpretation", "comparison_data",
        "playground_inspiration", "esmfold_pdb",
        "docked_complex_pdb",
    ]:
        st.session_state[key] = None
    st.session_state["chat_messages"] = []
    # Clear dynamic caches keyed by protein name or uniprot ID
    _dynamic_prefixes = (
        "variant_data_", "alphamissense_", "domains_",
        "flexibility_", "pockets_", "struct_analysis_",
        "alphafold_", "biorender_results_", "tamarind_results_",
        "svg_diagram_", "_dashboard_",
    )
    for k in list(st.session_state.keys()):
        if k.startswith(_dynamic_prefixes):
            del st.session_state[k]


# --- DNA Character SVG (shared between welcome + compact header) ---
# Stylized double helix with googly eyes — the Pixar lamp of Luminous
_DNA_SVG_ANIMATED = (
    '<svg class="dna-char" viewBox="0 0 36 56" width="72" height="107"'
    ' style="width:72px!important;height:107px!important;min-width:72px;min-height:107px;max-width:none!important;max-height:none!important"'
    ' xmlns="http://www.w3.org/2000/svg">'
    # ── Shadow ellipse on ground ──
    '<ellipse class="dna-shadow" cx="18" cy="54" rx="8" ry="2"/>'
    # ── Helix body ──
    '<g class="dna-body-group">'
    # Base pair rungs (horizontal connectors)
    '<line class="dna-rung" x1="8" y1="18" x2="28" y2="18"/>'
    '<line class="dna-rung" x1="13" y1="24" x2="23" y2="24"/>'
    '<line class="dna-rung" x1="8" y1="30" x2="28" y2="30"/>'
    '<line class="dna-rung" x1="13" y1="36" x2="23" y2="36"/>'
    '<line class="dna-rung" x1="8" y1="42" x2="28" y2="42"/>'
    '<line class="dna-rung" x1="13" y1="48" x2="23" y2="48"/>'
    # Backbone strand 1 (blue) — sinusoidal curve
    '<path class="dna-strand-blue" '
    'd="M8,15 C8,19 28,21 28,25 C28,29 8,31 8,35 C8,39 28,41 28,45 C28,49 13,50 13,52"/>'
    # Backbone strand 2 (green) — complementary sinusoidal
    '<path class="dna-strand-green" '
    'd="M28,15 C28,19 8,21 8,25 C8,29 28,31 28,35 C28,39 8,41 8,45 C8,49 23,50 23,52"/>'
    # Nucleotide dots at crossover points
    '<circle cx="8" cy="18" r="2.2" fill="#007AFF"/>'
    '<circle cx="28" cy="18" r="2.2" fill="#34C759"/>'
    '<circle cx="28" cy="30" r="2.2" fill="#007AFF"/>'
    '<circle cx="8" cy="30" r="2.2" fill="#34C759"/>'
    '<circle cx="8" cy="42" r="2.2" fill="#007AFF"/>'
    '<circle cx="28" cy="42" r="2.2" fill="#34C759"/>'
    '</g>'
    # ── Eyes (on top of helix) ──
    '<defs>'
    '<clipPath id="eyeL"><circle cx="12" cy="9" r="5.5"/></clipPath>'
    '<clipPath id="eyeR"><circle cx="24" cy="9" r="5.5"/></clipPath>'
    '</defs>'
    # Left eye
    '<circle class="dna-eye-white" cx="12" cy="9" r="5.5"/>'
    '<circle class="dna-pupil" cx="12.8" cy="9.2" r="2.8"/>'
    # Right eye
    '<circle class="dna-eye-white" cx="24" cy="9" r="5.5"/>'
    '<circle class="dna-pupil" cx="24.8" cy="9.2" r="2.8"/>'
    # Tiny highlight in each eye for Pixar-style life
    '<circle cx="10.5" cy="7.5" r="1.2" fill="white" opacity="0.9"/>'
    '<circle cx="22.5" cy="7.5" r="1.2" fill="white" opacity="0.9"/>'
    # Eyelids — clipped to eye circles for natural blink
    '<rect class="dna-eyelid" x="6.5" y="3.5" width="11" height="11"'
    ' clip-path="url(#eyeL)" fill="#E8E8ED"/>'
    '<rect class="dna-eyelid dna-eyelid-r" x="18.5" y="3.5" width="11" height="11"'
    ' clip-path="url(#eyeR)" fill="#E8E8ED"/>'
    '</svg>'
)

# Static (non-animated) version for compact header
_DNA_SVG_STATIC = (
    '<svg class="dna-char-static" viewBox="0 0 36 56" xmlns="http://www.w3.org/2000/svg">'
    '<g>'
    '<line stroke="rgba(0,0,0,0.10)" stroke-width="1.6" stroke-linecap="round" '
    'x1="8" y1="18" x2="28" y2="18"/>'
    '<line stroke="rgba(0,0,0,0.10)" stroke-width="1.6" stroke-linecap="round" '
    'x1="13" y1="24" x2="23" y2="24"/>'
    '<line stroke="rgba(0,0,0,0.10)" stroke-width="1.6" stroke-linecap="round" '
    'x1="8" y1="30" x2="28" y2="30"/>'
    '<line stroke="rgba(0,0,0,0.10)" stroke-width="1.6" stroke-linecap="round" '
    'x1="13" y1="36" x2="23" y2="36"/>'
    '<line stroke="rgba(0,0,0,0.10)" stroke-width="1.6" stroke-linecap="round" '
    'x1="8" y1="42" x2="28" y2="42"/>'
    '<path stroke="#007AFF" fill="none" stroke-width="2.8" stroke-linecap="round" '
    'd="M8,15 C8,19 28,21 28,25 C28,29 8,31 8,35 C8,39 28,41 28,45 C28,49 13,50 13,52"/>'
    '<path stroke="#34C759" fill="none" stroke-width="2.8" stroke-linecap="round" '
    'd="M28,15 C28,19 8,21 8,25 C8,29 28,31 28,35 C28,39 8,41 8,45 C8,49 23,50 23,52"/>'
    '<circle cx="8" cy="18" r="2" fill="#007AFF"/>'
    '<circle cx="28" cy="18" r="2" fill="#34C759"/>'
    '<circle cx="28" cy="30" r="2" fill="#007AFF"/>'
    '<circle cx="8" cy="30" r="2" fill="#34C759"/>'
    '</g>'
    '<circle fill="#fff" stroke="rgba(0,0,0,0.15)" stroke-width="0.4" cx="12" cy="9" r="5"/>'
    '<circle fill="#1a1a1a" cx="12" cy="9.2" r="2.5"/>'
    '<circle fill="#fff" stroke="rgba(0,0,0,0.15)" stroke-width="0.4" cx="24" cy="9" r="5"/>'
    '<circle fill="#1a1a1a" cx="24" cy="9.2" r="2.5"/>'
    '<circle cx="10.5" cy="7.5" r="1" fill="white" opacity="0.9"/>'
    '<circle cx="22.5" cy="7.5" r="1" fill="white" opacity="0.9"/>'
    '</svg>'
)

# --- Header ---
# Compact header when query is loaded; no header when empty (Ask Lumi tab has the big welcome)
if st.session_state.get("query_parsed"):
    st.markdown(
        '<div class="luminous-header" style="padding:0.6rem 0 0.5rem;margin-bottom:0.6rem">'
        '<div class="lumi-title-compact">'
        'Lum'
        '<span class="lumi-i-wrapper">' + _DNA_SVG_STATIC + '</span>'
        'nous'
        '</div>'
        "</div>",
        unsafe_allow_html=True,
    )

# --- Tab Router (Ask Lumi is default/first) ---
tab_chat, tab_query, tab_structure, tab_context, tab_report, tab_stats, tab_playground, tab_sketch = st.tabs([
    "Ask Lumi",
    "Query",
    "Structure & Trust",
    "Biological Context",
    "Report & Export",
    "Statistics",
    "Playground",
    "Sketch Hypothesis",
])

with tab_query:
    from components.query_input import render_query_input
    render_query_input()

with tab_structure:
    from components.structure_viewer import render_structure_viewer
    render_structure_viewer()

with tab_context:
    from components.context_panel import render_context_panel
    render_context_panel()

with tab_report:
    from components.report_export import render_report_export
    render_report_export()

with tab_stats:
    from components.statistics_tab import render_statistics
    render_statistics()

with tab_playground:
    from components.playground import render_playground
    render_playground()

with tab_sketch:
    from components.sketch_hypothesis import render_sketch_hypothesis
    render_sketch_hypothesis()

with tab_chat:
    from components.chat_followup import render_chat_followup
    render_chat_followup()

def _is_modal_ready() -> bool:
    """Check if Modal is installed and has credentials."""
    try:
        from src.modal_client import is_modal_available
        return is_modal_available()
    except Exception:
        return False


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_tamarind_tools() -> list[str]:
    """Fetch available tools from Tamarind Bio API."""
    import os
    key = os.getenv("TAMARIND_API_KEY", "")
    if not key:
        return []
    try:
        import httpx
        resp = httpx.get(
            "https://app.tamarind.bio/api/tools",
            headers={"x-api-key": key},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                return [t.get("name", t) if isinstance(t, dict) else str(t) for t in data]
        return []
    except Exception:
        return []


def _render_tamarind_tools():
    """Show Tamarind Bio available tools in sidebar."""
    tools = _fetch_tamarind_tools()
    if tools:
        with st.expander(f"Tamarind Bio Tools ({len(tools)})"):
            for tool in tools[:15]:
                st.markdown(
                    f'<span style="font-size:0.8em;color:#34C759">▸</span> '
                    f'<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">{tool}</span>',
                    unsafe_allow_html=True,
                )
            if len(tools) > 15:
                st.caption(f"... and {len(tools) - 15} more tools")


# --- Sidebar: Pipeline Status ---
with st.sidebar:
    st.markdown("### Analysis Pipeline")
    from components.pipeline_flow import render_text_pipeline
    render_text_pipeline()

    # Recompute completed count for Lottie animation check
    _pipeline_keys = [
        ("query_parsed", True),
        ("prediction_result", False),
        ("trust_audit", False),
        ("bio_context", False),
        ("interpretation", False),
    ]
    completed = sum(
        1 for key, is_bool in _pipeline_keys
        if (st.session_state.get(key, False) if is_bool else st.session_state.get(key) is not None)
    )
    total = len(_pipeline_keys)

    # Loading animation only when pipeline is actively running (not idle/waiting)
    if st.session_state.get("pipeline_running"):
        try:
            import json

            from streamlit_lottie import st_lottie

            lottie_path = Path(__file__).parent / "assets" / "dna_lottie.json"
            if lottie_path.exists():
                lottie_data = json.loads(lottie_path.read_text())
                st_lottie(lottie_data, height=80, key="sidebar_dna")
        except ImportError:
            pass  # Lottie not installed — skip gracefully

    # ── Compute Backend Selector ──
    st.divider()
    st.markdown("### Compute Backend")
    if "compute_backend" not in st.session_state:
        st.session_state["compute_backend"] = "auto"
    st.selectbox(
        "Structure prediction engine",
        options=["auto", "tamarind", "modal", "rcsb"],
        format_func=lambda x: {
            "auto": "Auto (fastest available)",
            "tamarind": "Tamarind Bio Cloud",
            "modal": "Modal GPU (H100)",
            "rcsb": "RCSB PDB (experimental)",
        }[x],
        key="compute_backend",
        help="Choose which compute backend to use for live predictions.",
    )

    # ── Connected Services ──
    st.divider()

    def _check_key(env_var: str) -> bool:
        import os
        return bool(os.getenv(env_var, ""))

    sponsors = [
        ("Tamarind Bio", "200+ tools: structure, docking, design, properties", _check_key("TAMARIND_API_KEY")),
        ("Anthropic Claude", "AI interpretation + MCP", _check_key("ANTHROPIC_API_KEY")),
        ("BioRender", "Scientific illustration via MCP", _check_key("BIORENDER_TOKEN")),
        ("Wiley Scholar Gateway", "Full-text journal articles via MCP", True),
        ("Modal", "Boltz-2 on H100 GPUs (serverless)", _is_modal_ready()),
        ("MolViewSpec", "Mol* 3D visualization engine", True),
        ("BioMCP", "15+ bio databases (PubMed, ChEMBL, ClinVar)", True),
    ]
    with st.expander("Connected Services", expanded=False):
        for name, desc, connected in sponsors:
            status = "Connected" if connected else "Not configured"
            status_color = "#34C759" if connected else "#8E8E93"
            st.markdown(
                f'<div style="margin-bottom:6px;display:flex;align-items:center;justify-content:space-between">'
                f'<span style="font-weight:500;font-size:0.88em">{name}</span>'
                f'<span style="color:{status_color};font-size:0.78em;font-weight:600">{status}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        _render_tamarind_tools()

    # ── Project Manager ──
    st.divider()
    from components.project_manager import render_project_manager

    render_project_manager()

    # Quick stats when data is loaded
    prediction = st.session_state.get("prediction_result")
    trust = st.session_state.get("trust_audit")
    if prediction and trust:
        st.divider()
        st.markdown("### Quick Stats")
        st.metric("Confidence", f"{trust.confidence_score:.1%}")
        st.metric("Residues", len(prediction.residue_ids))
        flagged = sum(1 for r in trust.regions if r.flag)
        if flagged:
            st.metric("Flagged Regions", flagged)

# --- Footer ---
st.markdown(
    '<div class="sponsor-footer">'
    "Luminous &mdash; YC Bio x AI Hackathon 2026 &nbsp;|&nbsp; "
    "Tamarind Bio &bull; Anthropic &bull; BioRender &bull; Wiley &bull; Modal"
    "</div>",
    unsafe_allow_html=True,
)
