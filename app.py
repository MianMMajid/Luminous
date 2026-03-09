from __future__ import annotations

import os
from pathlib import Path

# Set MPLCONFIGDIR early — prevents matplotlib from rebuilding its font cache
# on every cold start (~12s → <0.5s).
os.environ.setdefault("MPLCONFIGDIR", "/tmp/bioxyc-mpl")

import streamlit as st

st.set_page_config(
    page_title="Luminous - The AI Structure Interpreter",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# --- Load Custom CSS (cached to avoid re-reading 56KB file every rerun) ---
@st.cache_data(show_spinner=False)
def _load_css() -> str:
    p = Path(__file__).parent / "assets" / "style.css"
    return p.read_text() if p.exists() else ""

_css = _load_css()
if _css:
    st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Authentication Gate — Google OAuth via Streamlit native auth (st.login)
# Hero landing page is shown to unauthenticated users; the full app requires
# sign-in so we can persist user data across sessions.
# ═══════════════════════════════════════════════════════════════════════════════

def _auth_configured() -> bool:
    """Check if Google OAuth credentials are configured in secrets."""
    try:
        auth = st.secrets.get("auth", {})
        cid = auth.get("client_id", "")
        return bool(cid) and "YOUR_GOOGLE" not in cid
    except Exception:
        return False


def _render_login_hero():
    """Render the hero landing page with sign-in button for unauthenticated users."""
    # DNA character SVG (inline — same as chat_followup.py)
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

    # Vertically center the welcome page content.
    # Streamlit sanitizes each st.markdown independently, so we can't wrap
    # native widgets in a custom flexbox div. Instead, style the parent
    # Streamlit block-container directly. This only applies on this page
    # because st.stop() prevents the rest of the app from rendering.
    st.markdown(
        '<style>'
        '[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]'
        '{ display:flex; flex-direction:column; align-items:center;'
        '  justify-content:center; min-height:calc(100vh - 60px); }'
        '</style>',
        unsafe_allow_html=True,
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

    # Sign-in section
    st.markdown(
        '<div style="text-align:center;margin-top:24px">'
        '<p style="font-size:0.95rem;color:rgba(60,60,67,0.6);margin-bottom:16px">'
        'Sign in with Google to start analyzing proteins</p>'
        '</div>',
        unsafe_allow_html=True,
    )
    _cta_col1, _cta_col2, _cta_col3 = st.columns([2, 1, 2])
    with _cta_col2:
        if _auth_configured():
            st.button(
                "Sign in with Google",
                on_click=st.login,
                type="primary",
                use_container_width=True,
            )
        else:
            st.info(
                "Auth not configured. Set Google OAuth credentials in "
                "`.streamlit/secrets.toml` to enable sign-in. "
                "The app runs without auth for local development."
            )
            # Allow bypass for local dev without OAuth
            if st.button("Continue without sign-in", use_container_width=True):
                st.session_state["_auth_bypass"] = True
                st.rerun()


# Check authentication
_is_authed = False
if _auth_configured():
    try:
        _is_authed = st.user.is_logged_in
    except Exception:
        _is_authed = False
else:
    # Auth not configured — allow through for local development
    _is_authed = st.session_state.get("_auth_bypass", False)

# Local dev bypass: skip auth gate when running on localhost
try:
    _host = st.context.headers.get("Host", "")
    if "localhost" in _host or "127.0.0.1" in _host:
        _is_authed = True
except Exception:
    pass

if not _is_authed:
    _render_login_hero()
    st.stop()

# ── User profile persistence (runs on every authenticated page load) ──
try:
    if _auth_configured() and st.user.is_logged_in:
        from src.user_store import upsert_user
        _user_profile = upsert_user(
            email=st.user.email,
            name=st.user.name,
            picture=getattr(st.user, "picture", None),
        )
        st.session_state["user_profile"] = _user_profile
except Exception:
    pass  # User store is non-critical


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
    "active_tab": "Lumi",
    "pipeline_running": False,
    "chat_messages": [],
    "tamarind_results": {},
    "playground_pinned": [],
    "playground_plan": None,
    "stats_data": None,
    "stats_results": None,
    "stats_survival_data": None,
    "_chat_thinking": False,
    "_interpretation_attempted": False,
    "experiment_tracker": {},
    "generated_hypotheses": None,
    "playground_inspiration": None,
    "structure_analysis": None,
}
for key, val in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = val

# --- API Key Validation (show once per session) ---
if not st.session_state.get("_api_warning_shown"):
    import os as _os
    _missing = []
    if not _os.getenv("ANTHROPIC_API_KEY"):
        _missing.append("ANTHROPIC_API_KEY (required for AI interpretation)")
    if not _os.getenv("TAMARIND_API_KEY"):
        _missing.append("TAMARIND_API_KEY (required for live structure prediction)")
    if _missing:
        st.warning(
            "**Missing API keys:** " + ", ".join(_missing) + ". "
            "Set them in `.env` or Railway environment variables."
        )
    st.session_state["_api_warning_shown"] = True


def reset_results():
    """Clear all downstream results when a new query is submitted."""
    # Cancel any running background tasks
    try:
        from src.task_manager import task_manager
        task_manager.clear()
    except Exception:
        pass

    for key in [
        "prediction_result", "trust_audit", "bio_context",
        "interpretation", "stats_data", "stats_results",
        "stats_survival_data", "structure_analysis",
        "generated_hypotheses", "panel_figure_data",
        "graphical_abstract_svg", "figure_checklist_state",
        "experiment_tracker", "sketch_image_bytes",
        "sketch_interpretation", "comparison_data",
        "playground_inspiration", "playground_pinned",
        "playground_plan", "esmfold_pdb",
        "docked_complex_pdb", "generated_video",
        "_interpretation_attempted", "_prediction_raw",
    ]:
        st.session_state[key] = None
    st.session_state["chat_messages"] = []
    st.session_state["playground_pinned"] = []
    st.session_state["_chat_thinking"] = False
    st.session_state["_interpretation_attempted"] = False
    # Clear dynamic caches keyed by protein name or uniprot ID
    _dynamic_prefixes = (
        "variant_data_", "alphamissense_", "domains_",
        "flexibility_", "pockets_", "struct_analysis_",
        "alphafold_", "biorender_results_", "tamarind_results_",
        "svg_diagram_", "svg_", "_dashboard_",
        "_variant_fetch_attempted_", "variant_enrichment_",
        "pdf_bytes_", "nma_traj_", "morph_traj_",
        "charge_", "struct_diff_", "electrostatics_data_",
        "html_report_", "figure_kit_", "cex_",
        "rcsb_pdb_id_", "biorender_prompt_",
    )
    for k in list(st.session_state.keys()):
        if k.startswith(_dynamic_prefixes):
            del st.session_state[k]


# --- DNA Character SVG (shared between welcome + compact header) ---
# Stylized double helix with googly eyes — the Pixar lamp of Luminous
_DNA_SVG_ANIMATED = (
    '<svg class="dna-char" viewBox="0 0 36 56" width="80" height="120"'
    ' style="width:80px!important;height:120px!important;min-width:80px;min-height:120px;max-width:none!important;max-height:none!important"'
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
# Always render a stable header slot so the DOM above tabs never shifts.
_header_slot = st.empty()
if st.session_state.get("query_parsed"):
    with _header_slot.container():
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

# --- Tab Router (Lumi is default/first) ---
_TAB_LABELS = ["Lumi", "Search", "Structure", "Biology", "Report", "Stats", "Workspace", "Sketch"]
_saved_tab = st.session_state.get("active_tab", "Lumi")
tab_chat, tab_query, tab_structure, tab_context, tab_report, tab_stats, tab_playground, tab_sketch = st.tabs(
    _TAB_LABELS,
    default=_saved_tab if _saved_tab in _TAB_LABELS else None,
)

# ── Fragment-wrapped tab renderers ──────────────────────────────────────────
# @st.fragment() makes each tab an independent re-run scope: a widget change
# inside one tab only re-executes THAT tab's fragment, not the entire app.
# This eliminates the eager fan-out where every rerun recomputes all 8 tabs.

@st.fragment()
def _frag_query():
    from components.query_input import render_query_input
    render_query_input()

@st.fragment()
def _frag_structure():
    from components.structure_viewer import render_structure_viewer
    render_structure_viewer()

@st.fragment()
def _frag_context():
    from components.context_panel import render_context_panel
    render_context_panel()

@st.fragment()
def _frag_report():
    from components.report_export import render_report_export
    render_report_export()

@st.fragment()
def _frag_stats():
    from components.statistics_tab import render_statistics
    render_statistics()

@st.fragment()
def _frag_playground():
    from components.playground import render_playground
    render_playground()

@st.fragment()
def _frag_sketch():
    from components.sketch_hypothesis import render_sketch_hypothesis
    render_sketch_hypothesis()

@st.fragment()
def _frag_chat():
    from components.chat_followup import render_chat_followup
    render_chat_followup()

with tab_query:
    _frag_query()
with tab_structure:
    _frag_structure()
with tab_context:
    _frag_context()
with tab_report:
    _frag_report()
with tab_stats:
    _frag_stats()
with tab_playground:
    _frag_playground()
with tab_sketch:
    _frag_sketch()
with tab_chat:
    _frag_chat()

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
            timeout=3,
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
                    f'<span style="font-size:0.8em;color:#047857">▸</span> '
                    f'<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">{tool}</span>',
                    unsafe_allow_html=True,
                )
            if len(tools) > 15:
                st.caption(f"... and {len(tools) - 15} more tools")


# --- Sidebar: User Profile + Pipeline Status ---
with st.sidebar:
    # ── User Profile ──
    try:
        if _auth_configured() and st.user.is_logged_in:
            _u_name = st.user.name or "User"
            _u_email = st.user.email or ""
            _u_pic = getattr(st.user, "picture", None)
            _pic_html = (
                f'<img src="{_u_pic}" '
                f'style="width:32px;height:32px;border-radius:50%;margin-right:10px">'
                if _u_pic else
                '<div style="width:32px;height:32px;border-radius:50%;'
                'background:#007AFF;color:white;display:flex;align-items:center;'
                f'justify-content:center;font-weight:700;margin-right:10px">'
                f'{_u_name[0].upper()}</div>'
            )
            st.markdown(
                f'<div style="display:flex;align-items:center;padding:8px 0 12px">'
                f'{_pic_html}'
                f'<div>'
                f'<div style="font-weight:600;font-size:0.9rem;line-height:1.2">{_u_name}</div>'
                f'<div style="font-size:0.78rem;color:rgba(60,60,67,0.55)">{_u_email}</div>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            st.button("Sign out", on_click=st.logout, key="sidebar_logout")
            st.divider()
    except Exception:
        pass

    st.markdown("### Analysis Pipeline")
    from components.pipeline_flow import render_text_pipeline
    render_text_pipeline()

    # ── Background Task Poller (runs every 2s as a fragment) ──
    from components.notification_poller import render_notification_poller
    render_notification_poller()

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
            from streamlit_lottie import st_lottie

            @st.cache_data(show_spinner=False)
            def _load_lottie() -> dict | None:
                import json as _json
                p = Path(__file__).parent / "assets" / "dna_lottie.json"
                return _json.loads(p.read_text()) if p.exists() else None

            lottie_data = _load_lottie()
            if lottie_data:
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
        ("Anthropic Claude", "Agent SDK · Tool Use · Vision · Citations · Code Execution · Extended Thinking · MCP", _check_key("ANTHROPIC_API_KEY")),
        ("BioRender", "Scientific illustration via MCP", _check_key("BIORENDER_TOKEN")),
        ("Wiley Scholar Gateway", "Full-text journal articles via MCP", True),
        ("Gemini Veo", "AI protein animation videos", _check_key("GEMINI_API_KEY")),
        ("Modal", "Boltz-2 on H100 GPUs (serverless)", _is_modal_ready()),
        ("MolViewSpec", "Mol* 3D visualization engine", True),
        ("BioMCP", "15+ bio databases (PubMed, ChEMBL, ClinVar)", True),
    ]
    with st.expander("Connected Services", expanded=False):
        for name, desc, connected in sponsors:
            status = "Connected" if connected else "Not configured"
            status_color = "#047857" if connected else "#8E8E93"
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
