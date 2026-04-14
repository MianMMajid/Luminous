"""Fragment-based notification poller for background tasks.

Runs as a @st.fragment(run_every=2) in the sidebar.
Checks the task manager for completed tasks and:
  - Writes results into st.session_state
  - Fires st.toast() notifications from Lumi
  - Updates pipeline status
  - Triggers full rerun when critical tasks complete
"""
from __future__ import annotations

import time

import streamlit as st

from src.task_manager import TaskStatus, task_manager


# Map task IDs to friendly notification messages
_TASK_MESSAGES = {
    "prediction": ("Structure prediction complete!", "Check the **Structure** tab."),
    "bio_context": ("Biological context gathered!", "Check the **Biology** tab."),
    "interpretation": ("AI interpretation ready!", "Check the **Biology** tab."),
    "variant_landscape": ("Variant landscape loaded!", "Check the **Structure** tab overlays."),
    "tamarind_analysis": ("Tamarind analysis complete!", "Results ready in **Workspace**."),
    "video_generation": ("Video generated!", "Check the **Report** tab to preview."),
    "chat_response": ("Lumi responded!", "Check the **Lumi** tab."),
}

# Tasks that should trigger a full rerun when complete
_CRITICAL_TASKS = {"prediction", "bio_context", "interpretation", "video_generation", "variant_landscape", "hypothesis_generation", "chat_response"}
# Prefixes that also trigger rerun (for dynamic task IDs like variant_enrichment_TP53)
_CRITICAL_PREFIXES = ("variant_enrichment_",)


@st.fragment(run_every=2)
def render_notification_poller():
    """Poll for completed background tasks and notify the user.

    This fragment reruns every 2 seconds independently of the main app.
    It checks the task manager for finished tasks and processes them.
    """
    # Show active tasks
    active = task_manager.active_tasks()
    if active:
        st.session_state["pipeline_running"] = True
        for task in active:
            elapsed = time.time() - task.submitted_at
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:8px;padding:6px 10px;'
                f'margin-bottom:4px;border-radius:8px;background:rgba(255,149,0,0.06);'
                f'border:1px solid rgba(255,149,0,0.2);font-size:0.82rem">'
                f'<span style="display:inline-block;width:8px;height:8px;border-radius:50%;'
                f'background:#FF9500;animation:lumi-pulse-bg 1.5s ease-in-out infinite"></span>'
                f'<span style="color:#000;font-weight:500">{task.label}</span>'
                f'<span style="color:rgba(60,60,67,0.5);margin-left:auto">{elapsed:.0f}s</span>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.session_state["pipeline_running"] = False

    # Process completed tasks
    finished = task_manager.pop_completed()
    needs_rerun = False

    for task in finished:
        if task.status == TaskStatus.COMPLETE:
            # Write result into session state via task-specific handler
            _apply_task_result(task)

            # Show toast notification
            msg_parts = _TASK_MESSAGES.get(
                task.task_id,
                (f"{task.label} complete!", ""),
            )
            elapsed = (task.completed_at or 0) - task.submitted_at
            st.toast(
                f"**Lumi:** {msg_parts[0]}\n\n"
                f"{msg_parts[1]} ({elapsed:.0f}s)",
                icon="🧬",
            )

            # Check if this warrants a full rerun
            if task.task_id in _CRITICAL_TASKS or task.task_id.startswith(_CRITICAL_PREFIXES):
                needs_rerun = True

        elif task.status == TaskStatus.FAILED:
            # Clear thinking flag on chat failure so bubble doesn't get stuck
            if task.task_id == "chat_response":
                st.session_state["_chat_thinking"] = False
            st.toast(
                f"**Lumi:** {task.label} failed.\n\n{task.error or 'Unknown error'}",
                icon="⚠️",
            )
            # Also trigger rerun on failure so the UI can show retry options
            if task.task_id in _CRITICAL_TASKS or task.task_id.startswith(_CRITICAL_PREFIXES):
                needs_rerun = True

    # Trigger full rerun if critical tasks completed
    if needs_rerun:
        st.rerun()


def _apply_task_result(task):
    """Write a completed task's result into st.session_state.

    Handles special cases like prediction (needs PDB parsing).
    """
    result = task.result
    if result is None:
        return

    # ── Special handler: prediction result needs PDB parsing ──
    if task.task_id == "prediction" and isinstance(result, dict):
        _apply_prediction_result(result)
        return

    # ── Special handler: bio_context returns a BioContext object ──
    if task.task_id == "bio_context" and isinstance(result, dict):
        ctx = result.get("bio_context")
        if ctx is not None:
            st.session_state["bio_context"] = ctx
        return

    # ── Special handler: interpretation returns a string ──
    if task.task_id == "interpretation" and isinstance(result, dict):
        interp = result.get("interpretation")
        if interp is not None:
            st.session_state["interpretation"] = interp
        return

    # ── Special handler: variant landscape ──
    if task.task_id == "variant_landscape" and isinstance(result, dict):
        vd = result.get("variant_data")
        ck = result.get("cache_key")
        if vd is not None and ck:
            st.session_state[ck] = vd
        return

    # ── Special handler: hypothesis generation ──
    if task.task_id == "hypothesis_generation" and isinstance(result, dict):
        hyp = result.get("hypotheses")
        if hyp is not None:
            st.session_state["generated_hypotheses"] = hyp
        return

    # ── Special handler: chat response (from background agent) ──
    if task.task_id == "chat_response" and isinstance(result, dict):
        assistant_text = result.get("assistant_text", "")
        tool_calls = result.get("tool_calls", [])

        if "chat_messages" not in st.session_state:
            st.session_state["chat_messages"] = []

        # Append tool calls for display
        if tool_calls:
            st.session_state["chat_messages"].append({
                "role": "tool_calls",
                "calls": tool_calls,
            })

        # Auto-append BioRender suggestions
        from components.chat_followup import _get_biorender_suggestion_for_tools
        biorender_suggestion = _get_biorender_suggestion_for_tools(tool_calls)
        if biorender_suggestion:
            assistant_text += biorender_suggestion

        # Append attribution
        attribution = (
            "\n\n---\n"
            "*Powered by Anthropic Claude Agent SDK "
            "| Structure via Tamarind Bio / Modal "
            "| Context via BioMCP | Figures via BioRender*"
        )
        st.session_state["chat_messages"].append(
            {"role": "assistant", "content": assistant_text + attribution}
        )
        st.session_state["_chat_thinking"] = False
        return

    # ── Special handler: video generation returns bytes ──
    if task.task_id == "video_generation" and isinstance(result, dict):
        video_bytes = result.get("video_bytes")
        if video_bytes is not None:
            st.session_state["generated_video"] = video_bytes
        return

    # ── Generic handler ──
    target_keys = task.target_keys

    if "__direct__" in target_keys:
        st.session_state[target_keys["__direct__"]] = result
        return

    if isinstance(result, dict) and target_keys:
        for result_key, state_key in target_keys.items():
            if result_key in result:
                st.session_state[state_key] = result[result_key]
    elif target_keys:
        first_key = next(iter(target_keys.values()))
        st.session_state[first_key] = result


def _apply_prediction_result(result: dict):
    """Parse PDB content and store as PredictionResult in session state."""
    from src.services import AnalysisSessionService

    pdb_content = result.get("pdb", "")
    confidence = result.get("confidence", {})
    affinity = result.get("affinity")
    source = result.get("source", "unknown")
    skip_plddt = result.get("skip_plddt", False)
    AnalysisSessionService.store_prediction(
        st.session_state,
        pdb_content=pdb_content,
        confidence=confidence,
        affinity=affinity,
        source=source,
        skip_plddt=skip_plddt,
    )
