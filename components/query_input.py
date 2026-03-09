from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from src.models import ProteinQuery
from src.query_parser import parse_query

# Widget key for the text area
_TEXT_KEY = "query_text_area"


def render_query_input():
    """Tab 1: Natural language query input with example buttons."""
    st.markdown(
        '<div class="lumi-tab-header">'
        '<div class="tab-title">What protein do you want to investigate?</div>'
        '<div class="tab-subtitle">Ask any question about a protein — structure, mutations, drug targets, '
        'or binding interactions. We\'ll predict the structure, audit the confidence, and explain what it means.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Example buttons with styled cards
    examples = _load_examples()
    if examples:
        st.markdown("**Try an example:**")
        _EXAMPLE_ICONS = {
            "TP53": "🧬", "BRCA1": "🔬", "EGFR": "💊", "INS": "🧪",
            "SPIKE": "🦠", "HBA1": "🩸",
        }
        _EXAMPLE_DESCRIPTIONS = {
            "TP53": "Tumor suppressor — cancer hotspot",
            "BRCA1": "DNA repair — breast cancer risk",
            "EGFR": "Growth factor — drug resistance",
            "INS": "Hormone — diabetes & metabolism",
            "SPIKE": "SARS-CoV-2 — ACE2 binding",
            "HBA1": "Hemoglobin — thalassemia",
        }
        # Render in rows of 3 for clean layout
        per_row = 3
        for row_start in range(0, len(examples), per_row):
            row_examples = examples[row_start:row_start + per_row]
            cols = st.columns(per_row, gap="small")
            for col, ex in zip(cols, row_examples):
                protein = ex.get("protein_name", "")
                icon = _EXAMPLE_ICONS.get(protein.upper(), "🔹")
                mutation = ex.get("mutation", "")
                mut_str = f" ({mutation})" if mutation else ""
                desc = _EXAMPLE_DESCRIPTIONS.get(protein.upper(), "")
                col.markdown(
                    f'<div class="glow-card" style="text-align:center;margin-bottom:8px">'
                    f'<div style="font-size:1.6rem;margin-bottom:4px">{icon}</div>'
                    f'<div style="font-weight:600;font-size:0.95rem">{protein}{mut_str}</div>'
                    f'<div style="font-size:0.82rem;color:rgba(60,60,67,0.55);margin-top:2px">{desc}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if col.button(ex["label"], width="stretch", key=f"ex_{ex['label']}"):
                    st.session_state[_TEXT_KEY] = ex["query"]
                    st.session_state["_example_data"] = ex
                    _do_parse(ex["query"], ex)

    # Text input — use only `key=`, no `value=`
    if _TEXT_KEY not in st.session_state:
        st.session_state[_TEXT_KEY] = ""

    user_input = st.text_area(
        "Your question",
        height=100,
        placeholder="e.g., P53 R248W mutation - is it druggable?",
        key=_TEXT_KEY,
    )

    # Advanced Boltz-2 Settings
    with st.expander("Advanced Prediction Settings"):
        # Initialize defaults once
        if "boltz_recycling_steps" not in st.session_state:
            st.session_state["boltz_recycling_steps"] = 3
        if "boltz_use_msa" not in st.session_state:
            st.session_state["boltz_use_msa"] = True
        if "boltz_predict_affinity" not in st.session_state:
            st.session_state["boltz_predict_affinity"] = True

        adv_col1, adv_col2, adv_col3 = st.columns(3)
        with adv_col1:
            st.slider(
                "Recycling steps",
                min_value=1,
                max_value=10,
                help="Number of recycling iterations in Boltz-2. "
                     "More steps can improve accuracy but increase compute time.",
                key="boltz_recycling_steps",
            )
        with adv_col2:
            st.checkbox(
                "Use MSA server",
                help="Use multiple sequence alignment for better accuracy. "
                     "Disable for faster single-sequence predictions.",
                key="boltz_use_msa",
            )
        with adv_col3:
            st.checkbox(
                "Predict affinity",
                help="Predict binding affinity (requires interaction partner). "
                     "Uses Boltz-2's affinity head.",
                key="boltz_predict_affinity",
            )

    # Parse button
    col1, col2 = st.columns([1, 3], gap="small")
    with col1:
        parse_clicked = st.button(
            "Analyze", type="primary", width="stretch"
        )

    if parse_clicked and user_input.strip():
        example_data = st.session_state.pop("_example_data", None)
        _do_parse(user_input.strip(), example_data)

    # Display parsed query
    if st.session_state.get("query_parsed") and st.session_state.get("parsed_query"):
        _display_parsed_query(st.session_state["parsed_query"])


def _do_parse(text: str, example_data: dict | None = None):
    """Parse the query and store results in session state."""
    # Keep user on the Search tab after rerun
    st.session_state["active_tab"] = "Search"

    # Cancel any running background tasks
    try:
        from src.task_manager import task_manager
        task_manager.clear()
    except Exception:
        pass

    # Clear the parsed query up-front so a failed parse never leaves
    # the old protein active while downstream state is already wiped.
    st.session_state["parsed_query"] = None
    st.session_state["query_parsed"] = False

    # Reset downstream results
    for key in ["prediction_result", "trust_audit", "bio_context", "interpretation",
                "generated_hypotheses", "stats_data", "stats_results",
                "stats_survival_data", "structure_analysis",
                "panel_figure_data", "graphical_abstract_svg",
                "figure_checklist_state", "experiment_tracker",
                "sketch_image_bytes", "sketch_interpretation",
                "comparison_data", "playground_inspiration",
                "playground_pinned", "playground_plan",
                "esmfold_pdb", "docked_complex_pdb", "generated_video",
                "_interpretation_attempted", "_prediction_raw"]:
        st.session_state[key] = None
    st.session_state["chat_messages"] = []
    st.session_state["playground_pinned"] = []
    st.session_state["_chat_thinking"] = False
    # Clear dynamic caches keyed by protein name or uniprot ID
    for k in list(st.session_state.keys()):
        if k.startswith((
            "variant_data_", "alphamissense_", "domains_",
            "flexibility_", "pockets_", "struct_analysis_",
            "alphafold_", "biorender_results_",
            "tamarind_results_", "svg_diagram_", "svg_",
            "_dashboard_",
            "_variant_fetch_attempted_", "variant_enrichment_",
            "pdf_bytes_", "nma_traj_", "morph_traj_",
            "charge_", "struct_diff_", "electrostatics_data_",
            "html_report_", "figure_kit_", "cex_",
            "rcsb_pdb_id_", "biorender_prompt_",
        )):
            del st.session_state[k]

    try:
        if example_data and example_data.get("query") == text:
            parsed = ProteinQuery(
                protein_name=example_data.get("protein_name", "unknown"),
                uniprot_id=example_data.get("uniprot_id"),
                mutation=example_data.get("mutation"),
                interaction_partner=example_data.get("interaction_partner"),
                question_type=example_data.get("question_type", "structure"),
                sequence=example_data.get("sequence"),
            )
        else:
            parsed = parse_query(text)

        st.session_state["parsed_query"] = parsed
        st.session_state["raw_query"] = text
        st.session_state["query_parsed"] = True
    except Exception as e:
        st.error(
            f"Could not parse your query. Try a format like: "
            f"**'TP53 R248W mutation — is it druggable?'** or "
            f"**'Show me the structure of BRCA1'**\n\n"
            f"Details: {e}"
        )


def _display_parsed_query(query: ProteinQuery):
    """Show the parsed query fields in a styled card."""
    st.markdown(
        '<div class="glow-card" style="border-color:#34C759">'
        '<span style="color:#34C759;font-weight:600">Query parsed successfully</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Protein", query.protein_name)
    with col2:
        st.metric("UniProt ID", query.uniprot_id or "—")
    with col3:
        st.metric("Question Type", query.question_type.replace("_", " ").title())

    extra_cols = []
    if query.mutation:
        extra_cols.append(("Mutation", query.mutation))
    if query.interaction_partner:
        extra_cols.append(("Interaction Partner", query.interaction_partner))
    if query.sequence:
        extra_cols.append(("Sequence", f"{len(query.sequence)} aa"))

    if extra_cols:
        cols = st.columns(len(extra_cols))
        for col, (label, val) in zip(cols, extra_cols):
            col.metric(label, val)

    st.markdown(
        '<div style="display:inline-flex;align-items:center;gap:6px;padding:4px 12px;'
        'border-radius:8px;background:rgba(52,199,89,0.08);border:1px solid rgba(52,199,89,0.2);'
        'font-size:0.82rem;color:#16A34A;margin-top:8px">'
        '<span style="font-weight:600">&#10003; Parsed</span> '
        '<span style="color:rgba(60,60,67,0.55)">Proceed to Structure &amp; Trust tab</span>'
        '</div>',
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False)
def _load_examples() -> list[dict]:
    """Load example queries from data file (cached — no disk read on reruns)."""
    path = Path("data/example_queries.json")
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
    return []
