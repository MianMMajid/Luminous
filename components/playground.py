"""Playground tab — interactive workspace for comparing, overlaying, and exploring insights.

Features:
1. **Pin system** — collect insights from other tabs into the workspace
2. **Compare mode** — side-by-side view of two pinned visualizations
3. **Overlay mode** — superimpose compatible data tracks
4. **Inspire Me** — Claude finds unexpected connections between pinned insights
5. **Experiment Planner** — generates actionable experiment plans from collected insights
"""
from __future__ import annotations

import json

import plotly.graph_objects as go
import streamlit as st

from src.models import ProteinQuery

# ── Session state keys ──

_PINNED_KEY = "playground_pinned"
_PLAN_KEY = "playground_plan"


def _init_playground_state():
    """Ensure playground session state exists."""
    if _PINNED_KEY not in st.session_state:
        st.session_state[_PINNED_KEY] = []
    if _PLAN_KEY not in st.session_state:
        st.session_state[_PLAN_KEY] = None


# ── Public "pin" API — called from other components ──


def pin_insight(
    title: str,
    summary: str,
    insight_type: str = "observation",
    data: dict | None = None,
    chart_json: str | None = None,
) -> None:
    """Pin an insight to the Playground workspace.

    Parameters
    ----------
    title : str
        Short name (e.g. "pLDDT Distribution", "PAE Domain Map").
    summary : str
        1-2 sentence description of what this insight shows.
    insight_type : str
        Category: "chart", "metric", "finding", "warning", "observation".
    data : dict | None
        Structured data that can be re-rendered (residue scores, etc.).
    chart_json : str | None
        Plotly figure JSON string for re-rendering charts.
    """
    _init_playground_state()
    # Avoid duplicates by title
    existing_titles = {p["title"] for p in st.session_state[_PINNED_KEY]}
    if title in existing_titles:
        return

    st.session_state[_PINNED_KEY].append({
        "title": title,
        "summary": summary,
        "type": insight_type,
        "data": data or {},
        "chart_json": chart_json,
    })


def pin_button(
    title: str,
    summary: str,
    insight_type: str = "observation",
    data: dict | None = None,
    chart_json: str | None = None,
    key: str | None = None,
) -> bool:
    """Render a "Pin to Workspace" button. Returns True if clicked."""
    _init_playground_state()
    existing_titles = {p["title"] for p in st.session_state[_PINNED_KEY]}
    already_pinned = title in existing_titles

    btn_key = key or f"pin_{title.replace(' ', '_')[:30]}"

    # Bookmark SVG icon (Notion/Linear style)
    _bk = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" '
        'stroke-linejoin="round" style="vertical-align:-1px;margin-right:3px">'
        '<path d="M17 3a2 2 0 0 1 2 2v15a1 1 0 0 1-1.496.868l-4.512-2.578a2 2 0 0 0-1.984 '
        '0l-4.512 2.578A1 1 0 0 1 5 20V5a2 2 0 0 1 2-2z"/></svg>'
    )

    if already_pinned:
        st.markdown(
            f'<div style="display:inline-flex;align-items:center;padding:2px 10px;'
            f'border-radius:8px;background:rgba(0,0,0,0.03);border:1px solid rgba(0,0,0,0.06);'
            f'font-size:0.76rem;color:rgba(60,60,67,0.4)">'
            f'{_bk} Saved</div>',
            unsafe_allow_html=True,
        )
        return False

    if st.button(f"\u2606 Save", key=btn_key, help="Save this insight to the Playground"):
        pin_insight(title, summary, insight_type, data, chart_json)
        return True
    return False


# ── Main render function ──


def render_playground():
    """Render the Playground tab."""
    _init_playground_state()

    query: ProteinQuery | None = st.session_state.get("parsed_query")

    st.markdown(
        '<div style="margin-bottom:16px">'
        '<span style="font-size:1.4rem;font-weight:700">Playground</span>'
        '<span style="font-size:0.9rem;color:rgba(60,60,67,0.5);margin-left:10px">'
        "Compare, overlay, and explore your collected insights"
        "</span></div>",
        unsafe_allow_html=True,
    )

    pinned = st.session_state[_PINNED_KEY]

    if not pinned:
        _render_empty_state()
        return

    # ── Toolbar ──
    tool_cols = st.columns([2, 2, 2, 2, 2])
    with tool_cols[0]:
        st.markdown(f"**{len(pinned)} insights pinned**")
    with tool_cols[1]:
        view_mode = st.selectbox(
            "View",
            ["Grid", "Compare", "Overlay"],
            key="playground_view_mode",
            label_visibility="collapsed",
        )
    with tool_cols[2]:
        if st.button("Inspire Me", key="playground_inspire", help="Find unexpected connections"):
            _run_inspire(query, pinned)
    with tool_cols[3]:
        if st.button("Generate Plan", key="playground_gen_plan", type="primary"):
            _run_plan_generation(query, pinned)
    with tool_cols[4]:
        if st.button("Clear All", key="playground_clear", type="secondary"):
            st.session_state[_PINNED_KEY] = []
            st.session_state[_PLAN_KEY] = None
            st.rerun()

    st.divider()

    # ── View modes ──
    if view_mode == "Grid":
        _render_grid_view(pinned)
    elif view_mode == "Compare":
        _render_compare_view(pinned)
    elif view_mode == "Overlay":
        _render_overlay_view(pinned)

    # ── Inspiration result ──
    if st.session_state.get("playground_inspiration"):
        st.divider()
        st.markdown("### Unexpected Connections")
        st.markdown(st.session_state["playground_inspiration"])

    # ── Experiment Plan ──
    plan = st.session_state.get(_PLAN_KEY)
    if plan:
        st.divider()
        from components.experiment_planner import render_experiment_plan

        render_experiment_plan(plan)


# ── Empty state ──


def _render_empty_state():
    """Show instructions when no insights are pinned."""
    st.markdown(
        '<div style="text-align:center;padding:60px 20px;color:rgba(60,60,67,0.55)">'
        '<div style="font-size:3rem;margin-bottom:16px">&#128204;</div>'
        '<div style="font-size:1.1rem;font-weight:600;margin-bottom:8px">'
        "Your workspace is empty</div>"
        '<div style="font-size:0.9rem;max-width:400px;margin:0 auto">'
        "Pin insights from the <b>Structure & Trust</b>, <b>Biological Context</b>, "
        "and <b>Report</b> tabs using the <em>Pin to Workspace</em> buttons. "
        "Then come back here to compare, overlay, and build experiment plans."
        "</div></div>",
        unsafe_allow_html=True,
    )

    # Quick-pin from existing data
    _offer_auto_pins()


def _offer_auto_pins():
    """Offer to auto-pin available data from the current analysis."""
    prediction = st.session_state.get("prediction_result")
    trust_audit = st.session_state.get("trust_audit")
    bio_context = st.session_state.get("bio_context")
    query = st.session_state.get("parsed_query")

    if not prediction:
        return

    st.markdown("---")
    st.markdown("#### Quick Pin from Current Analysis")

    cols = st.columns(3)

    with cols[0]:
        if trust_audit and st.button(
            "Pin Confidence Overview", key="auto_pin_confidence"
        ):
            pin_insight(
                "Confidence Overview",
                f"Overall: {trust_audit.overall_confidence} ({trust_audit.confidence_score:.1%})",
                "metric",
                {
                    "confidence_score": trust_audit.confidence_score,
                    "overall": trust_audit.overall_confidence,
                    "flagged_regions": len([r for r in trust_audit.regions if r.flag]),
                },
            )
            st.rerun()

    with cols[1]:
        if prediction.plddt_per_residue and st.button(
            "Pin pLDDT Distribution", key="auto_pin_plddt"
        ):
            pin_insight(
                "pLDDT Distribution",
                f"{len(prediction.plddt_per_residue)} residues, "
                f"mean pLDDT {sum(prediction.plddt_per_residue) / len(prediction.plddt_per_residue):.1f}",
                "chart",
                {"plddt": prediction.plddt_per_residue, "residue_ids": prediction.residue_ids},
                _build_plddt_chart_json(prediction.plddt_per_residue, prediction.residue_ids),
            )
            st.rerun()

    with cols[2]:
        if bio_context and bio_context.disease_associations and st.button(
            "Pin Disease Associations", key="auto_pin_diseases"
        ):
            diseases = [
                {"disease": d.disease, "score": d.score}
                for d in bio_context.disease_associations[:10]
            ]
            pin_insight(
                "Disease Associations",
                f"{len(bio_context.disease_associations)} diseases linked to {query.protein_name if query else 'protein'}",
                "finding",
                {"diseases": diseases},
            )
            st.rerun()


# ── Grid View ──


def _render_grid_view(pinned: list[dict]):
    """Render pinned insights as a 2-column grid of cards."""
    for row_start in range(0, len(pinned), 2):
        cols = st.columns(2)
        for col_idx, item_idx in enumerate(range(row_start, min(row_start + 2, len(pinned)))):
            item = pinned[item_idx]
            with cols[col_idx]:
                _render_insight_card(item, item_idx)


def _render_insight_card(item: dict, display_key: int, *, actual_idx: int | None = None):
    """Render a single pinned insight as a card.

    Args:
        item: The insight dict.
        display_key: Unique key for Streamlit widgets (avoids duplicate keys).
        actual_idx: The real index in the pinned list for unpin operations.
                    If None, display_key is used as the index.
    """
    real_idx = actual_idx if actual_idx is not None else display_key

    type_icons = {
        "chart": "&#128200;",
        "metric": "&#128202;",
        "finding": "&#128218;",
        "warning": "&#9888;&#65039;",
        "observation": "&#128161;",
    }
    item_type = item.get("type", "observation")
    title = item.get("title", "Untitled")
    summary = item.get("summary", "")
    icon = type_icons.get(item_type, "&#128204;")
    type_label = item_type.replace("_", " ").title()

    st.markdown(
        f'<div class="glow-card" style="padding:14px;margin-bottom:10px;min-height:120px">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
        f'<span style="font-weight:700;font-size:0.95rem">{icon} {title}</span>'
        f'<span style="font-size:0.82rem;color:rgba(60,60,67,0.55);'
        f'background:#F2F2F7;padding:2px 8px;border-radius:8px">{type_label}</span>'
        f"</div>"
        f'<div style="font-size:0.85rem;color:rgba(60,60,67,0.6);margin-bottom:8px">'
        f"{summary}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # Render chart if available
    if item.get("chart_json"):
        try:
            fig = go.Figure(json.loads(item["chart_json"]))
            fig.update_layout(height=250, margin=dict(t=10, b=30, l=40, r=10))
            st.plotly_chart(fig, use_container_width=True, key=f"pinned_chart_{display_key}")
        except Exception:
            pass

    # Render data metrics if available
    data = item.get("data", {})
    if data and not item.get("chart_json"):
        _render_data_preview(data, display_key)

    # Remove button — always uses the real list index
    if st.button("Unpin", key=f"unpin_{display_key}", help="Remove from workspace"):
        pinned_list = st.session_state.get(_PINNED_KEY, [])
        if 0 <= real_idx < len(pinned_list):
            pinned_list.pop(real_idx)
        st.rerun()


def _render_data_preview(data: dict, idx: int):
    """Render a compact preview of structured data."""
    preview_cols = st.columns(min(len(data), 3))
    for i, (key, value) in enumerate(list(data.items())[:3]):
        with preview_cols[i]:
            if isinstance(value, (int, float)):
                display = f"{value:.2f}" if isinstance(value, float) else str(value)
                st.metric(key.replace("_", " ").title(), display)
            elif isinstance(value, list) and len(value) <= 5:
                st.markdown(f"**{key.replace('_', ' ').title()}**")
                for v in value:
                    if isinstance(v, dict):
                        st.markdown(f"- {v.get('disease', v.get('name', str(v)))}")
                    else:
                        st.markdown(f"- {v}")
            elif isinstance(value, str):
                st.markdown(f"**{key.replace('_', ' ').title()}:** {value}")


# ── Compare View ──


def _render_compare_view(pinned: list[dict]):
    """Side-by-side comparison of two selected insights."""
    titles = [p["title"] for p in pinned]

    if len(pinned) < 2:
        st.info("Pin at least 2 insights to use Compare mode.")
        _render_grid_view(pinned)
        return

    compare_cols = st.columns(2)
    with compare_cols[0]:
        left_idx = st.selectbox("Left Panel", range(len(titles)), format_func=lambda i: titles[i], key="compare_left")
    with compare_cols[1]:
        right_default = 1 if len(pinned) > 1 else 0
        right_idx = st.selectbox("Right Panel", range(len(titles)), format_func=lambda i: titles[i], key="compare_right", index=right_default)

    st.divider()

    left_col, divider_col, right_col = st.columns([5, 0.2, 5])

    with left_col:
        _render_insight_card(pinned[left_idx], left_idx * 100, actual_idx=left_idx)

    with divider_col:
        st.markdown(
            '<div style="width:2px;background:rgba(0,0,0,0.1);height:400px;margin:0 auto"></div>',
            unsafe_allow_html=True,
        )

    with right_col:
        _render_insight_card(pinned[right_idx], right_idx * 100 + 50, actual_idx=right_idx)

    # Comparison summary
    left_data = pinned[left_idx].get("data", {})
    right_data = pinned[right_idx].get("data", {})
    common_keys = set(left_data.keys()) & set(right_data.keys())

    if common_keys:
        st.markdown("#### Comparison")
        for key in sorted(common_keys):
            lv, rv = left_data[key], right_data[key]
            if isinstance(lv, (int, float)) and isinstance(rv, (int, float)):
                delta = rv - lv
                delta_str = f"+{delta:.2f}" if delta > 0 else f"{delta:.2f}"
                st.markdown(
                    f"**{key.replace('_', ' ').title()}:** "
                    f"{lv:.2f} vs {rv:.2f} ({delta_str})"
                )


# ── Overlay View ──


def _render_overlay_view(pinned: list[dict]):
    """Overlay compatible charts on a single axis."""
    chart_items = [
        (i, p) for i, p in enumerate(pinned)
        if p.get("chart_json") or (p.get("data", {}).get("plddt"))
    ]

    if len(chart_items) < 1:
        st.info(
            "Overlay mode works with chart-type insights. "
            "Pin some pLDDT distributions or residue analysis charts first."
        )
        _render_grid_view(pinned)
        return

    # Let user select which to overlay
    titles = [p["title"] for _, p in chart_items]
    selected = st.multiselect(
        "Select insights to overlay",
        titles,
        default=titles[:2],
        key="overlay_selection",
    )

    if not selected:
        return

    # Build combined figure
    fig = go.Figure()
    colors = ["#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE", "#5AC8FA"]

    for sel_idx, title in enumerate(selected):
        item = next(p for _, p in chart_items if p["title"] == title)
        color = colors[sel_idx % len(colors)]

        # Try to use chart_json traces
        if item.get("chart_json"):
            try:
                source_fig = go.Figure(json.loads(item["chart_json"]))
                for trace in source_fig.data:
                    trace.name = title
                    trace.line = dict(color=color, width=2)
                    trace.opacity = 0.8
                    fig.add_trace(trace)
                continue
            except Exception:
                pass

        # Fall back to data-based rendering
        data = item.get("data", {})
        if "plddt" in data:
            plddt = data["plddt"]
            rids = data.get("residue_ids", list(range(1, len(plddt) + 1)))
            fig.add_trace(go.Scatter(
                x=rids,
                y=plddt,
                mode="lines",
                name=title,
                line=dict(color=color, width=2),
                opacity=0.8,
            ))

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=500,
        margin=dict(t=30, b=50, l=60, r=20),
        xaxis_title="Residue Number",
        yaxis_title="Value",
        legend=dict(orientation="h", y=-0.15),
        font=dict(family="'Plus Jakarta Sans', Inter, system-ui, sans-serif"),
    )

    st.plotly_chart(fig, use_container_width=True, key="overlay_chart")


# ── Inspire Me ──


def _run_inspire(query: ProteinQuery | None, pinned: list[dict]):
    """Use Claude to find unexpected connections between pinned insights."""
    from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

    if not ANTHROPIC_API_KEY:
        st.session_state["playground_inspiration"] = (
            "**Inspiration (offline mode):** Consider how confidence patterns "
            "correlate with disease associations. Low-confidence regions often "
            "correspond to intrinsically disordered regions that may actually be "
            "functional — acting as molecular switches or binding interfaces."
        )
        st.rerun()
        return

    from anthropic import Anthropic

    prompt_parts = []
    if query:
        prompt_parts.append(f"Protein: {query.protein_name}")
        if query.mutation:
            prompt_parts.append(f"Mutation: {query.mutation}")

    prompt_parts.append("\nThe scientist has collected these insights:")
    for p in pinned:
        prompt_parts.append(f"- [{p['type']}] {p['title']}: {p['summary']}")

    prompt_parts.append(
        "\nFind 2-3 NON-OBVIOUS connections between these insights that the "
        "scientist might not have noticed. Think laterally — connect structural "
        "observations to disease mechanisms, or confidence patterns to druggability. "
        "Be specific and cite the pinned insights by name. Keep it to 150 words."
    )

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=512,
            messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
        )
        st.session_state["playground_inspiration"] = msg.content[0].text
    except Exception as e:
        st.session_state["playground_inspiration"] = (
            f"Could not generate inspiration: {e}"
        )
    st.rerun()


# ── Plan Generation ──


def _run_plan_generation(query: ProteinQuery | None, pinned: list[dict]):
    """Generate an experiment plan from pinned insights."""
    if not query:
        st.warning("Enter a query in the Query tab first.")
        return

    with st.spinner("Generating experiment plan..."):
        from components.experiment_planner import generate_experiment_plan

        plan = generate_experiment_plan(query, pinned)
        st.session_state[_PLAN_KEY] = plan
    st.rerun()


# ── Helpers ──


def _build_plddt_chart_json(plddt: list[float], residue_ids: list[int]) -> str:
    """Build a Plotly JSON string for a pLDDT distribution chart."""
    colors = []
    for s in plddt:
        if s >= 90:
            colors.append("#0053D6")
        elif s >= 70:
            colors.append("#65CBF3")
        elif s >= 50:
            colors.append("#FFDB13")
        else:
            colors.append("#FF7D45")

    fig = go.Figure(go.Bar(
        x=residue_ids[:len(plddt)],
        y=plddt[:len(residue_ids)],
        marker=dict(color=colors, line=dict(width=0)),
        name="pLDDT",
    ))
    fig.update_layout(
        template="plotly_white",
        xaxis_title="Residue",
        yaxis_title="pLDDT",
        yaxis_range=[0, 100],
    )
    return fig.to_json()
