from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.models import (
    BioContext,
    DiseaseAssociation,
    DrugCandidate,
    LiteratureSummary,
    PredictionResult,
    ProteinQuery,
    RegionConfidence,
    TrustAudit,
)
from src.utils import safe_json_dumps, safe_json_loads

_PROJECTS_DIR = Path("data/projects")


def render_project_manager():
    """Sidebar widget: Save / Load / Recent projects."""
    st.markdown("### Projects")

    # --- Save Project ---
    _render_save_button()

    # --- Load Project ---
    _render_load_uploader()

    # --- Recent Projects ---
    _render_recent_projects()


# ── Save ──────────────────────────────────────────────────────────────────────


def _render_save_button():
    """Save all current session state to a JSON project file."""
    has_data = st.session_state.get("query_parsed") and st.session_state.get(
        "prediction_result"
    )
    if st.button(
        "Save Project",
        use_container_width=True,
        disabled=not has_data,
        key="save_project_btn",
    ):
        try:
            project_data = _serialize_session()
            filename = _project_filename(project_data)
            _PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
            filepath = _PROJECTS_DIR / filename
            filepath.write_text(safe_json_dumps(project_data, indent=2))
            st.success(f"Saved: {filename}")

            # Also provide a download button for the saved file
            st.session_state["_last_saved_project"] = (filename, project_data)
        except Exception as e:
            st.error(f"Save failed: {e}")

    # Download button if we just saved
    last = st.session_state.get("_last_saved_project")
    if last:
        filename, data = last
        st.download_button(
            "Download Project File",
            safe_json_dumps(data, indent=2),
            filename,
            mime="application/json",
            use_container_width=True,
            key="download_project_btn",
        )


# ── Load ──────────────────────────────────────────────────────────────────────


def _render_load_uploader():
    """File uploader to restore a saved project."""
    uploaded = st.file_uploader(
        "Load Project",
        type=["json"],
        key="load_project_file",
        label_visibility="collapsed",
        help="Upload a .json project file to restore a previous analysis",
    )
    if uploaded is not None:
        try:
            project_data = safe_json_loads(uploaded.read().decode("utf-8"))
            _deserialize_session(project_data)
            st.success(f"Loaded project: {uploaded.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Load failed: {e}")


# ── Recent Projects ──────────────────────────────────────────────────────────


def _render_recent_projects():
    """Show the 5 most recent saved projects on disk."""
    if not _PROJECTS_DIR.exists():
        return

    project_files = sorted(
        _PROJECTS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True
    )[:5]

    if not project_files:
        return

    with st.expander(f"Recent Projects ({len(project_files)})", expanded=False):
        for pf in project_files:
            col_name, col_load = st.columns([3, 1])
            with col_name:
                # Parse metadata from filename
                stem = pf.stem
                size_kb = pf.stat().st_size / 1024
                mtime = datetime.fromtimestamp(pf.stat().st_mtime)
                st.markdown(
                    f'<div style="font-size:0.85rem;color:#000000;font-weight:600">'
                    f"{stem}</div>"
                    f'<div style="font-size:0.75rem;color:rgba(60,60,67,0.55)">'
                    f"{mtime:%Y-%m-%d %H:%M} | {size_kb:.0f} KB</div>",
                    unsafe_allow_html=True,
                )
            with col_load:
                if st.button("Load Project", key=f"load_recent_{pf.name}", use_container_width=True):
                    try:
                        data = safe_json_loads(pf.read_text())
                        _deserialize_session(data)
                        st.success(f"Loaded: {pf.name}")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Load failed: {e}")


# ── Serialization helpers ─────────────────────────────────────────────────────


def _serialize_session() -> dict:
    """Serialize all relevant session state into a JSON-safe dict."""
    data: dict = {
        "luminous_project_version": "1.1",
        "saved_at": datetime.now().isoformat(),
    }

    # Pydantic-model keys (use model_dump when available)
    for state_key in ("parsed_query", "prediction_result", "trust_audit", "bio_context"):
        obj = st.session_state.get(state_key)
        if obj is not None:
            if hasattr(obj, "model_dump"):
                data[state_key] = obj.model_dump()
            elif isinstance(obj, dict):
                data[state_key] = obj
            else:
                try:
                    data[state_key] = str(obj)
                except Exception:
                    pass
    data["raw_query"] = st.session_state.get("raw_query", "")
    data["query_parsed"] = st.session_state.get("query_parsed", False)

    # Plain-value keys — store anything that is JSON-safe
    _PLAIN_KEYS = [
        "interpretation", "chat_messages", "experiment_tracker",
        "stats_data", "stats_results", "stats_survival_data",
        "structure_analysis", "generated_hypotheses",
        "panel_figure_data", "graphical_abstract_svg",
        "figure_checklist_state", "sketch_interpretation",
        "comparison_data", "playground_pinned", "playground_plan",
        "playground_inspiration",
        # Bytes values — SafeJSONEncoder encodes them as base64
        "sketch_image_bytes", "generated_video", "esmfold_pdb",
    ]
    for key in _PLAIN_KEYS:
        val = st.session_state.get(key)
        if val is not None:
            try:
                # Use safe_json_dumps so bytes → base64 dict (not str())
                safe_json_dumps(val)
                data[key] = val
            except (TypeError, ValueError):
                pass

    # Dynamic per-protein caches (variant_data_*, etc.)
    # Must include all prefixes from reset_results() / _deserialize_session()
    _DYN_PREFIXES = (
        "variant_data_", "variant_enrichment_",
        "alphamissense_", "domains_", "flexibility_",
        "pockets_", "struct_analysis_", "alphafold_",
        "biorender_results_", "tamarind_results_",
        "svg_diagram_", "svg_",
        "pdf_bytes_", "html_report_", "figure_kit_",
        "rcsb_pdb_id_", "cex_",
        "biorender_prompt_", "electrostatics_data_",
        "nma_traj_", "morph_traj_", "charge_", "struct_diff_",
    )
    dyn: dict = {}
    for k, v in st.session_state.items():
        if isinstance(k, str) and k.startswith(_DYN_PREFIXES):
            try:
                safe_json_dumps(v)
                dyn[k] = v
            except (TypeError, ValueError):
                pass
    if dyn:
        data["_dynamic_caches"] = dyn

    return data


def _deserialize_session(data: dict):
    """Restore session state from a project dict.

    Clears ALL analysis state first so that no stale artifacts from the
    current session survive into the loaded project.
    """
    # ── Wipe ALL existing analysis state before loading ──
    try:
        from src.task_manager import task_manager
        task_manager.clear()
    except Exception:
        pass
    _RESET_KEYS = [
        "parsed_query", "query_parsed", "raw_query",
        "prediction_result", "trust_audit", "bio_context",
        "interpretation", "stats_data", "stats_results",
        "stats_survival_data", "structure_analysis",
        "generated_hypotheses", "panel_figure_data",
        "graphical_abstract_svg", "figure_checklist_state",
        "experiment_tracker", "sketch_image_bytes",
        "sketch_interpretation", "comparison_data",
        "playground_inspiration", "playground_pinned",
        "playground_plan", "esmfold_pdb", "docked_complex_pdb",
        "generated_video", "_interpretation_attempted",
        "_prediction_raw",
    ]
    for key in _RESET_KEYS:
        st.session_state[key] = None
    st.session_state["query_parsed"] = False
    st.session_state["raw_query"] = ""
    st.session_state["chat_messages"] = []
    st.session_state["playground_pinned"] = []
    st.session_state["_chat_thinking"] = False
    _dyn_prefixes = (
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
        if isinstance(k, str) and k.startswith(_dyn_prefixes):
            del st.session_state[k]

    # Query
    if "parsed_query" in data:
        try:
            st.session_state["parsed_query"] = ProteinQuery(**data["parsed_query"])
        except Exception:
            pass  # Skip if data doesn't match model
    if "raw_query" in data:
        st.session_state["raw_query"] = data["raw_query"]
    if "query_parsed" in data:
        st.session_state["query_parsed"] = data["query_parsed"]

    # Prediction result
    if "prediction_result" in data:
        try:
            st.session_state["prediction_result"] = PredictionResult(
                **data["prediction_result"]
            )
        except Exception:
            pass

    # Trust audit
    if "trust_audit" in data:
        try:
            ta = data["trust_audit"].copy()
            # Reconstruct RegionConfidence objects
            if "regions" in ta:
                regions = []
                for r in ta["regions"]:
                    try:
                        regions.append(RegionConfidence(**r))
                    except Exception:
                        pass
                ta["regions"] = regions
            st.session_state["trust_audit"] = TrustAudit(**ta)
        except Exception:
            pass

    # Bio context
    if "bio_context" in data:
        try:
            bc = data["bio_context"].copy()
            if "disease_associations" in bc:
                bc["disease_associations"] = [
                    DiseaseAssociation(**d) for d in bc["disease_associations"]
                    if isinstance(d, dict)
                ]
            if "drugs" in bc:
                bc["drugs"] = [
                    DrugCandidate(**d) for d in bc["drugs"]
                    if isinstance(d, dict)
                ]
            if "literature" in bc:
                try:
                    bc["literature"] = LiteratureSummary(**bc["literature"])
                except Exception:
                    bc["literature"] = LiteratureSummary()
            st.session_state["bio_context"] = BioContext(**bc)
        except Exception:
            pass

    # Interpretation
    if "interpretation" in data:
        st.session_state["interpretation"] = data["interpretation"]

    # Chat messages
    if "chat_messages" in data:
        st.session_state["chat_messages"] = data["chat_messages"]

    # Experiment tracker
    if "experiment_tracker" in data:
        st.session_state["experiment_tracker"] = data["experiment_tracker"]

    # Restore plain-value keys saved by _serialize_session
    # Must match _serialize_session._PLAIN_KEYS (including byte fields)
    _PLAIN_KEYS = [
        "stats_data", "stats_results", "stats_survival_data",
        "structure_analysis", "generated_hypotheses",
        "panel_figure_data", "graphical_abstract_svg",
        "figure_checklist_state", "sketch_interpretation",
        "comparison_data", "playground_pinned", "playground_plan",
        "playground_inspiration",
        # Bytes values (restored via safe_json_loads → base64 decode)
        "sketch_image_bytes", "generated_video", "esmfold_pdb",
    ]
    for key in _PLAIN_KEYS:
        if key in data:
            st.session_state[key] = data[key]

    # Restore dynamic per-protein caches
    dyn = data.get("_dynamic_caches")
    if isinstance(dyn, dict):
        for k, v in dyn.items():
            st.session_state[k] = v


def _project_filename(data: dict) -> str:
    """Generate a project filename from query data."""
    protein = "unknown"
    mutation = ""
    if "parsed_query" in data:
        q = data["parsed_query"]
        protein = q.get("protein_name", "unknown") if isinstance(q, dict) else "unknown"
        mut = q.get("mutation", "") if isinstance(q, dict) else ""
        if mut:
            mutation = f"_{mut}"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    # Sanitize filename
    safe_protein = "".join(c if c.isalnum() else "_" for c in protein)
    safe_mutation = "".join(c if c.isalnum() else "_" for c in mutation)
    return f"{safe_protein}{safe_mutation}_{timestamp}.json"
