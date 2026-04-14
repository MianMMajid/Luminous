from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path

import streamlit as st

from src.services import ProjectService
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
        width="stretch",
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
            width="stretch",
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
                if st.button("Load Project", key=f"load_recent_{pf.name}", width="stretch"):
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
    return ProjectService.serialize(st.session_state)


def _deserialize_session(data: dict):
    """Restore session state from a project dict.

    Clears ALL analysis state first so that no stale artifacts from the
    current session survive into the loaded project.
    """
    ProjectService.restore(st.session_state, data)


def _project_filename(data: dict) -> str:
    """Generate a project filename from query data."""
    return ProjectService.filename(data)
