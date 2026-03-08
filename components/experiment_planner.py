"""Experiment Planner — generates structured experimental plans from pinned insights.

Uses Claude to analyze the user's collected insights (pinned charts, findings,
annotations) and generates a concrete experiment plan rendered as a flow diagram.
"""
from __future__ import annotations

import json
import re

import streamlit as st

from src.models import ProteinQuery

# ── Prompt for Claude ──

PLAN_SYSTEM = """You are a senior structural biologist designing an experimental plan.

Given the user's collected insights about a protein (structural observations,
confidence warnings, literature findings, computational predictions), produce
a concrete experimental plan.

Return ONLY a JSON object with this exact schema:
{
  "title": "short plan title",
  "rationale": "1-2 sentence summary of why this plan addresses the key question",
  "steps": [
    {
      "id": "step_1",
      "label": "short step name (max 6 words)",
      "description": "1-2 sentence detail",
      "method": "technique/tool name",
      "duration": "estimated time",
      "depends_on": []
    },
    {
      "id": "step_2",
      "label": "...",
      "description": "...",
      "method": "...",
      "duration": "...",
      "depends_on": ["step_1"]
    }
  ],
  "expected_outcome": "what success looks like",
  "risk_factors": ["risk 1", "risk 2"]
}

Design 4-8 steps. Mix computational (Tamarind Bio tools, docking, MD simulation)
and wet-lab experiments. Make it realistic and actionable."""


def generate_experiment_plan(
    query: ProteinQuery,
    pinned_insights: list[dict],
) -> dict | None:
    """Generate a structured experiment plan from pinned insights using Claude."""
    from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL

    if not ANTHROPIC_API_KEY:
        return _fallback_plan(query, pinned_insights)

    from anthropic import Anthropic

    prompt_parts = [
        f"## Protein: {query.protein_name}",
        f"Question: {query.question_type}",
    ]
    if query.mutation:
        prompt_parts.append(f"Mutation: {query.mutation}")
    if query.interaction_partner:
        prompt_parts.append(f"Interaction partner: {query.interaction_partner}")

    prompt_parts.append("\n## Collected Insights:")
    for i, insight in enumerate(pinned_insights, 1):
        prompt_parts.append(
            f"{i}. [{insight.get('type', 'observation')}] "
            f"{insight.get('title', 'Untitled')}: {insight.get('summary', '')}"
        )

    prompt_parts.append("\nDesign an experimental plan based on these insights.")

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        msg = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=PLAN_SYSTEM,
            messages=[{"role": "user", "content": "\n".join(prompt_parts)}],
        )
        text = msg.content[0].text
        # Extract JSON from response
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            return json.loads(json_match.group())
    except Exception as e:
        st.warning(f"Plan generation failed: {e}")

    return _fallback_plan(query, pinned_insights)


def _fallback_plan(query: ProteinQuery, pinned_insights: list[dict]) -> dict:
    """Generate a basic plan without Claude."""
    steps = [
        {
            "id": "step_1",
            "label": "Validate structure prediction",
            "description": f"Run multi-engine comparison for {query.protein_name} using Boltz-2, ESMFold, and AlphaFold3.",
            "method": "Tamarind Bio (multi-engine)",
            "duration": "~10 min",
            "depends_on": [],
        },
        {
            "id": "step_2",
            "label": "Analyze confidence regions",
            "description": "Identify low-confidence regions and compare across engines.",
            "method": "pLDDT + PAE analysis",
            "duration": "~5 min",
            "depends_on": ["step_1"],
        },
    ]

    if query.mutation:
        steps.append({
            "id": "step_3",
            "label": f"Assess {query.mutation} impact",
            "description": f"Compute ddG for mutation {query.mutation} using ProteinMPNN-ddG.",
            "method": "Tamarind Bio (proteinmpnn-ddg)",
            "duration": "~5 min",
            "depends_on": ["step_1"],
        })
        steps.append({
            "id": "step_4",
            "label": "Validate experimentally",
            "description": "Express and purify mutant protein, measure thermal stability by DSF.",
            "method": "DSF / Thermal shift assay",
            "duration": "~2 weeks",
            "depends_on": ["step_3"],
        })
    else:
        steps.append({
            "id": "step_3",
            "label": "Screen for drug binding",
            "description": f"Run molecular docking against {query.protein_name} active site.",
            "method": "Tamarind Bio (autodock-vina)",
            "duration": "~15 min",
            "depends_on": ["step_1"],
        })
        steps.append({
            "id": "step_4",
            "label": "Validate binding",
            "description": "Run SPR or ITC to confirm top docking hits.",
            "method": "SPR / ITC",
            "duration": "~3 weeks",
            "depends_on": ["step_3"],
        })

    return {
        "title": f"Experimental Plan for {query.protein_name}",
        "rationale": f"Based on {len(pinned_insights)} insights collected during analysis.",
        "steps": steps,
        "expected_outcome": "Validated structure with experimental confirmation of key predictions.",
        "risk_factors": [
            "Predicted structure may differ from experimental",
            "Expression/purification may fail",
        ],
    }


def render_experiment_plan(plan: dict) -> None:
    """Render an experiment plan as a flow diagram + detail cards."""
    st.markdown(f"### {plan.get('title', 'Experiment Plan')}")
    st.caption(plan.get("rationale", ""))

    steps = plan.get("steps", [])
    if not steps:
        st.info("No steps in the plan.")
        return

    # Render as flow diagram
    try:
        _render_flow_diagram(steps)
    except Exception:
        pass

    # Render step cards
    st.markdown("#### Steps")
    for step in steps:
        deps = step.get("depends_on", [])
        dep_str = f" (after: {', '.join(deps)})" if deps else ""
        with st.expander(f"{step['id']}: {step['label']}{dep_str}", expanded=False):
            st.markdown(step.get("description", ""))
            cols = st.columns(2)
            cols[0].markdown(f"**Method:** {step.get('method', 'N/A')}")
            cols[1].markdown(f"**Duration:** {step.get('duration', 'N/A')}")

    # Expected outcome and risks
    if plan.get("expected_outcome"):
        st.success(f"**Expected Outcome:** {plan['expected_outcome']}")
    risks = plan.get("risk_factors", [])
    if risks:
        with st.expander("Risk Factors"):
            for risk in risks:
                st.markdown(f"- {risk}")


def _render_flow_diagram(steps: list[dict]) -> None:
    """Render steps as a flow diagram using streamlit-flow-component."""
    from streamlit_flow import StreamlitFlowEdge, StreamlitFlowNode, streamlit_flow

    nodes = []
    edges = []

    # Position nodes in a grid: 2 columns
    for i, step in enumerate(steps):
        col = i % 2
        row = i // 2
        x = col * 300 + 50
        y = row * 120 + 50

        nodes.append(StreamlitFlowNode(
            id=step["id"],
            pos=(x, y),
            data={"content": f"**{step['label']}**\n{step.get('method', '')}"},
            node_type="default",
            source_position="right" if col == 0 else "bottom",
            target_position="left" if col == 1 else "top",
            style={
                "backgroundColor": "#F2F2F7",
                "border": "2px solid #007AFF",
                "borderRadius": "8px",
                "padding": "10px",
                "fontSize": "12px",
                "width": "220px",
            },
        ))

        # Add edges from dependencies
        for dep in step.get("depends_on", []):
            edges.append(StreamlitFlowEdge(
                id=f"{dep}->{step['id']}",
                source=dep,
                target=step["id"],
                animated=True,
                style={"stroke": "#007AFF", "strokeWidth": 2},
            ))

    streamlit_flow(
        key="experiment_plan_flow",
        nodes=nodes,
        edges=edges,
        fit_view=True,
        height=max(200, (len(steps) // 2 + 1) * 120 + 60),
        style={"backgroundColor": "transparent"},
        hide_watermark=True,
    )
