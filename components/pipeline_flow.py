"""Interactive pipeline flow visualization using streamlit-flow-component.

Shows the analysis pipeline as an interactive node graph with status indicators.
Falls back to text-based display if package not available.
"""
from __future__ import annotations

import streamlit as st

try:
    from streamlit_flow import streamlit_flow
    from streamlit_flow.elements import StreamlitFlowEdge, StreamlitFlowNode
    from streamlit_flow.state import StreamlitFlowState

    FLOW_AVAILABLE = True
except ImportError:
    FLOW_AVAILABLE = False

# (id, label, state_key, is_bool)
STEPS = [
    ("parse", "Query Parsed", "query_parsed", True),
    ("predict", "Structure Predicted", "prediction_result", False),
    ("trust", "Trust Audited", "trust_audit", False),
    ("context", "Context Gathered", "bio_context", False),
    ("interpret", "AI Interpreted", "interpretation", False),
]

# --- Styling constants ---
_STYLE_COMPLETE = {
    "background": "rgba(52,199,89,0.06)",
    "border": "3px solid #34C759",
    "color": "#000000",
    "borderRadius": "8px",
    "padding": "8px",
    "fontSize": "11px",
    "width": 160,
}
_STYLE_IN_PROGRESS = {
    "background": "rgba(255,149,0,0.06)",
    "border": "3px solid #FF9500",
    "color": "#000000",
    "borderRadius": "8px",
    "padding": "8px",
    "fontSize": "11px",
    "width": 160,
}
_STYLE_PENDING = {
    "background": "#F2F2F7",
    "border": "1px solid #C6C6C8",
    "color": "#8E8E93",
    "borderRadius": "8px",
    "padding": "8px",
    "fontSize": "11px",
    "width": 160,
}


def _step_done(state_key: str, is_bool: bool) -> bool:
    """Check whether a pipeline step is complete."""
    if is_bool:
        return bool(st.session_state.get(state_key, False))
    return st.session_state.get(state_key) is not None


def render_pipeline_flow() -> None:
    """Render the pipeline as an interactive node-based flow diagram."""
    if not FLOW_AVAILABLE:
        render_text_pipeline()
        return

    statuses: list[bool] = [_step_done(sk, ib) for _, _, sk, ib in STEPS]
    completed = sum(statuses)
    total = len(STEPS)

    # Find the index of the first incomplete step (used for "in progress" highlight)
    first_incomplete = next((i for i, done in enumerate(statuses) if not done), None)

    # --- Build nodes ---
    nodes: list[StreamlitFlowNode] = []
    for i, (step_id, label, _sk, _ib) in enumerate(STEPS):
        done = statuses[i]
        if done:
            style = _STYLE_COMPLETE
            emoji = "\u2705"  # checkmark
        elif i == first_incomplete and completed > 0:
            style = _STYLE_IN_PROGRESS
            emoji = "\u23f3"  # hourglass
        else:
            style = _STYLE_PENDING
            emoji = "\u2b1c"  # white square
        nodes.append(
            StreamlitFlowNode(
                id=step_id,
                pos=(0, i * 80),
                data={"label": f"{emoji} {label}"},
                node_type="default",
                draggable=False,
                connectable=False,
                style=style,
            )
        )

    # --- Build edges ---
    edges: list[StreamlitFlowEdge] = []
    for i in range(len(STEPS) - 1):
        src_id = STEPS[i][0]
        tgt_id = STEPS[i + 1][0]
        src_done = statuses[i]
        tgt_done = statuses[i + 1]

        if src_done and tgt_done:
            # Both ends complete
            color = "#34C759"
            animated = False
        elif src_done and not tgt_done:
            # Active transition
            color = "#FF9500"
            animated = True
        else:
            # Pending
            color = "#C6C6C8"
            animated = False

        edges.append(
            StreamlitFlowEdge(
                id=f"{src_id}-{tgt_id}",
                source=src_id,
                target=tgt_id,
                animated=animated,
                style={"stroke": color},
            )
        )

    # --- Render flow ---
    streamlit_flow(
        "pipeline_flow",
        StreamlitFlowState(nodes, edges),
        fit_view=True,
        hide_watermark=True,
        height=380,
        pan_on_drag=False,
        allow_zoom=False,
    )

    st.caption(f"{completed}/{total} steps complete")


def render_text_pipeline() -> None:
    """Fallback text-based pipeline status display.

    This is the original HTML-based pipeline rendering, used when
    streamlit-flow-component is not installed or fails to render.
    """
    steps = [
        ("Query Parsed", "query_parsed", "Parse natural language query"),
        ("Structure Predicted", "prediction_result", "Boltz-2 via Tamarind Bio"),
        ("Trust Audited", "trust_audit", "pLDDT + known limitations"),
        ("Context Gathered", "bio_context", "PubMed, OpenTargets via MCP"),
        ("AI Interpreted", "interpretation", "Claude narrative synthesis"),
    ]

    completed = sum(
        1
        for _, key, _ in steps
        if (
            st.session_state.get(key, False)
            if key == "query_parsed"
            else st.session_state.get(key) is not None
        )
    )
    total = len(steps)

    st.progress(completed / total, text=f"{completed}/{total} steps complete")

    # Find the first incomplete step index (only that one is "in progress")
    first_incomplete_idx = None
    for i, (_, key, _) in enumerate(steps):
        done = (
            st.session_state.get(key, False)
            if key == "query_parsed"
            else st.session_state.get(key) is not None
        )
        if not done and first_incomplete_idx is None:
            first_incomplete_idx = i

    for i, (label, key, desc) in enumerate(steps):
        done = (
            st.session_state.get(key, False)
            if key == "query_parsed"
            else st.session_state.get(key) is not None
        )
        css_class = "done" if done else "pending"
        if done:
            icon = "\u2705"
        elif i == first_incomplete_idx and completed > 0:
            icon = "\u23f3"
        else:
            icon = "\u2b1c"
        st.markdown(
            f'<div class="pipeline-step {css_class}">'
            f'<span class="step-label">{icon} {label}</span><br>'
            f'<span class="step-desc">{desc}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
