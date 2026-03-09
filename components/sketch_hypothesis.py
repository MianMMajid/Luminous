"""Sketch Your Hypothesis — draw a mechanism, Claude Vision interprets it.

Researchers sketch rough pathway diagrams on a canvas. Claude Vision
identifies biological entities, interactions, and outputs a clean
Mermaid diagram + interactive Plotly network + testable prediction.

Uses a custom bidirectional Streamlit component (st.components.v1.declare_component)
for the drawing canvas — no third-party dependencies needed.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import ProteinQuery

# Register the custom canvas component (bidirectional — returns data to Python)
_CANVAS_DIR = Path(__file__).parent / "sketch_canvas"
_sketch_component = components.declare_component("sketch_canvas", path=str(_CANVAS_DIR))

SKETCH_SYSTEM_PROMPT = """You are Lumi, a structural biology expert working inside the Luminous platform.
A researcher has drawn a rough sketch of a biological mechanism or pathway on a digital canvas.
Interpret the sketch in the context of the loaded protein ({protein_name}{mutation_ctx}).

Identify:
1. Biological entities (proteins, drugs, metabolites, pathways, organelles)
2. Interactions (arrows = activation, flat-head = inhibition, dotted = indirect)
3. The scientific hypothesis being proposed

Return ONLY a JSON object (no markdown fences) with these keys:
{{
  "title": "Short title of the proposed mechanism",
  "description": "2-3 sentence scientific interpretation of what the sketch shows",
  "elements": [
    {{"label": "ProteinName", "type": "protein|drug|metabolite|pathway|organelle", "role": "brief role"}}
  ],
  "interactions": [
    {{"from": "Entity1", "to": "Entity2", "type": "activation|inhibition|binding|phosphorylation|ubiquitination|transport", "label": "short label"}}
  ],
  "mermaid": "graph TD\\n  A[Entity1] -->|activates| B[Entity2]\\n  ...",
  "testable_prediction": "If X, then Y should be measurable by Z",
  "confidence_note": "How well the sketch matches known biology for this protein"
}}

If the sketch is too abstract to interpret, still try your best and note uncertainty.
Connect your interpretation to the loaded protein data when relevant."""


def render_sketch_hypothesis():
    """Tab 5: Drawable canvas for sketching biological hypotheses."""
    query: ProteinQuery | None = st.session_state.get("parsed_query")

    st.markdown(
        '<div class="lumi-tab-header">'
        '<div class="tab-title">Sketch Your Hypothesis</div>'
        '<div class="tab-subtitle">Draw a rough pathway or mechanism diagram. '
        'Click <b>Send to Lumi</b> &mdash; Claude Vision interprets your sketch, '
        'Extended Thinking generates testable hypotheses.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    if query:
        st.caption(
            f"Context: **{query.protein_name}**"
            + (f" ({query.mutation})" if query.mutation else "")
        )

    # ── Bidirectional canvas component ──
    canvas_data = _sketch_component(
        canvasWidth=900,
        canvasHeight=460,
        key="sketch_canvas",
        default=None,
    )

    # canvas_data is a data URL string when user clicks "Send to Lumi"
    image_bytes = None
    if canvas_data and isinstance(canvas_data, str) and canvas_data.startswith("data:"):
        # Decode the data URL → raw PNG bytes
        try:
            header, b64data = canvas_data.split(",", 1)
            image_bytes = base64.b64decode(b64data)
            st.session_state["sketch_image_bytes"] = image_bytes
        except Exception:
            pass

    # Also allow file upload as fallback
    with st.expander("Or upload a sketch image"):
        uploaded = st.file_uploader(
            "Upload sketch (PNG, JPG, photo of whiteboard)",
            type=["png", "jpg", "jpeg", "webp"],
            key="sketch_upload",
            label_visibility="collapsed",
        )
        if uploaded:
            image_bytes = uploaded.read()
            st.session_state["sketch_image_bytes"] = image_bytes
            st.image(image_bytes, caption="Uploaded sketch", width="stretch")

    # Use the most recent image source
    if image_bytes is None:
        image_bytes = st.session_state.get("sketch_image_bytes")

    # ── Interpret ──
    interpretation = st.session_state.get("sketch_interpretation")

    if image_bytes:
        if st.button("Interpret Sketch", type="primary", key="interpret_btn"):
            with st.status("Lumi is interpreting your sketch..."):
                interpretation = _interpret_sketch(image_bytes, query)
                st.session_state["sketch_interpretation"] = interpretation

    if interpretation:
        st.divider()
        _render_structured_output(interpretation, query)

    # Show hypothesis panel if protein data is available
    trust_audit = st.session_state.get("trust_audit")
    bio_context = st.session_state.get("bio_context")
    if trust_audit:
        st.divider()
        from components.hypothesis_panel import render_hypothesis_panel
        render_hypothesis_panel(query or ProteinQuery(protein_name="Unknown"), trust_audit, bio_context, key_suffix="_sketch")


def _interpret_sketch(image_bytes: bytes, query: ProteinQuery | None) -> dict | None:
    """Send canvas image to Claude Vision for interpretation."""
    if not ANTHROPIC_API_KEY:
        return _fallback_sketch_response()

    from anthropic import Anthropic

    protein_name = query.protein_name if query else "unknown protein"
    mutation_ctx = f", mutation {query.mutation}" if query and query.mutation else ""
    system = SKETCH_SYSTEM_PROMPT.format(
        protein_name=protein_name, mutation_ctx=mutation_ctx
    )

    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    media_type = "image/png"
    if image_bytes[:3] == b"\xff\xd8\xff":
        media_type = "image/jpeg"
    elif image_bytes[:4] == b"RIFF":
        media_type = "image/webp"

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=system,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64_image,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            f"Protein context: {protein_name}{mutation_ctx}. "
                            "Interpret this sketch as a biological mechanism diagram. "
                            "Return JSON only."
                        ),
                    },
                ],
            }],
        )
    except Exception as e:
        err = str(e)
        if "credit balance" in err.lower() or "billing" in err.lower():
            st.error(
                "Anthropic API credits exhausted. "
                "Please add credits at [console.anthropic.com](https://console.anthropic.com)."
            )
        else:
            st.error(f"Claude API error: {err[:200]}")
        return _fallback_sketch_response()

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "title": "Interpretation",
            "description": raw[:500],
            "elements": [],
            "interactions": [],
            "mermaid": "",
            "testable_prediction": "Could not parse structured output.",
            "confidence_note": "Raw text response — JSON parsing failed.",
        }


def _render_structured_output(interpretation: dict, query: ProteinQuery | None):
    """Display the interpreted sketch as structured output + actionable next steps."""
    st.markdown(f"#### {interpretation.get('title', 'Interpretation')}")
    st.markdown(interpretation.get("description", ""))

    # ── Visual outputs ──
    mermaid = interpretation.get("mermaid", "")
    if mermaid:
        with st.expander("Pathway Diagram (Mermaid)", expanded=True):
            st.markdown(f"```mermaid\n{mermaid}\n```")

    elements = interpretation.get("elements", [])
    interactions = interpretation.get("interactions", [])
    if elements and interactions:
        fig = _build_network_figure(elements, interactions)
        st.plotly_chart(fig, width="stretch")

    prediction = interpretation.get("testable_prediction", "")
    if prediction:
        st.success(f"**Testable Prediction:** {prediction}")

    note = interpretation.get("confidence_note", "")
    if note:
        st.caption(f"*{note}*")

    # ── Downloads ──
    st.markdown('<div class="download-btn-group">', unsafe_allow_html=True)
    col1, col2, col3 = st.columns(3, gap="small")
    with col1:
        st.download_button(
            "Download JSON",
            json.dumps(interpretation, indent=2),
            "sketch_interpretation.json",
            mime="application/json",
            width="stretch",
        )
    with col2:
        if mermaid:
            st.download_button(
                "Download Mermaid",
                mermaid,
                "sketch_diagram.mmd",
                mime="text/plain",
                width="stretch",
            )
    with col3:
        if elements:
            svg = _elements_to_simple_svg(elements, interactions)
            st.download_button(
                "Download SVG", svg, "sketch_diagram.svg", mime="image/svg+xml",
                width="stretch",
            )
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Actionable Next Steps (the "so what?" bridge) ──
    st.divider()
    st.markdown("### Turn This Hypothesis Into Action")

    _render_actionable_steps(interpretation, elements, interactions, query)

    # ── BioRender figures ──
    _render_sketch_biorender(interpretation, query)

    st.markdown(
        '<div style="text-align:right;font-size:0.82rem;color:rgba(60,60,67,0.55);margin-top:4px">'
        '<span style="color:#007AFF">&#9679;</span> '
        "Sketch interpreted by <strong>Anthropic Claude Vision</strong>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_actionable_steps(
    interpretation: dict,
    elements: list[dict],
    interactions: list[dict],
    query: ProteinQuery | None,
):
    """Render context-aware actionable steps derived from the sketch interpretation."""
    element_types = {el.get("type", "") for el in elements}
    interaction_types = {i.get("type", "") for i in interactions}
    protein_name = query.protein_name if query else "protein"

    # ── 1. Computational validation via Tamarind ──
    st.markdown("#### Validate Computationally")
    st.caption("Run these Tamarind Bio tools to test your sketched hypothesis:")

    tamarind_recs: list[tuple[str, str, str]] = []

    # Drug interactions in sketch → docking tools
    if "drug" in element_types or "binding" in interaction_types:
        tamarind_recs.extend([
            ("AutoDock Vina", "autodock-vina",
             f"Dock the sketched drug to {protein_name} — validate binding mode"),
            ("GNINA", "gnina",
             "Deep-learning docking to score the proposed interaction"),
            ("DiffDock", "diffdock",
             "Generative docking — find alternative binding poses"),
        ])

    # Protein-protein interactions → binding tools
    if interaction_types & {"binding", "phosphorylation", "ubiquitination"}:
        tamarind_recs.extend([
            ("PRODIGY", "prodigy",
             "Predict binding free energy for the sketched complex"),
            ("MaSIF", "masif",
             "Map interaction surfaces to confirm binding interface"),
        ])

    # Stability/mutation concerns → stability tools
    if "inhibition" in interaction_types or (query and query.mutation):
        tamarind_recs.extend([
            ("ProteinMPNN-ddG", "proteinmpnn-ddg",
             "Quantify stability impact of the proposed mechanism"),
            ("ThermoMPNN", "thermompnn",
             "Scan for stabilizing mutations to rescue function"),
        ])

    # Protein design suggested by sketch → design tools
    if len([e for e in elements if e.get("type") == "protein"]) > 1:
        tamarind_recs.extend([
            ("BoltzGen", "boltzgen",
             "Design de novo binders targeting the sketched interface"),
            ("RFdiffusion", "rfdiffusion",
             "Generate backbone scaffolds for the proposed complex"),
        ])

    # Always suggest structure validation
    tamarind_recs.append(
        ("ESMFold", "esmfold",
         f"Quick structure check — validate {protein_name} fold")
    )

    # Deduplicate by tool slug
    seen = set()
    unique_recs = []
    for name, slug, desc in tamarind_recs:
        if slug not in seen:
            seen.add(slug)
            unique_recs.append((name, slug, desc))
    tamarind_recs = unique_recs[:6]

    cols = st.columns(min(len(tamarind_recs), 3))
    for i, (name, slug, desc) in enumerate(tamarind_recs):
        with cols[i % min(len(tamarind_recs), 3)]:
            st.markdown(
                f'<div style="border:1px solid rgba(0,0,0,0.06);border-radius:8px;padding:10px;'
                f'margin-bottom:8px;min-height:100px">'
                f'<div style="color:#34C759;font-weight:600;font-size:0.9rem">{name}</div>'
                f'<div style="color:rgba(60,60,67,0.6);font-size:0.82rem;margin:4px 0">{desc}</div>'
                f'<div style="font-size:0.82rem;color:rgba(60,60,67,0.55)">Tool: {slug}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # ── 2. Experimental validation ──
    st.markdown("#### Validate Experimentally")
    st.caption("Key experiments to test the hypothesis in your sketch:")

    experiments: list[tuple[str, str]] = []

    if "drug" in element_types:
        experiments.extend([
            ("Surface Plasmon Resonance (SPR)",
             "Measure real binding kinetics for the drug-target interaction"),
            ("Isothermal Titration Calorimetry (ITC)",
             "Quantify thermodynamics of the proposed binding"),
        ])
    if "binding" in interaction_types or "phosphorylation" in interaction_types:
        experiments.extend([
            ("Co-immunoprecipitation (Co-IP)",
             "Confirm the protein-protein interaction exists in cells"),
            ("Crosslinking Mass Spec (XL-MS)",
             "Map the binding interface at residue resolution"),
        ])
    if "ubiquitination" in interaction_types:
        experiments.append((
            "Ubiquitination Assay",
            "In vitro ubiquitination to confirm the E3 ligase activity",
        ))
    if "inhibition" in interaction_types:
        experiments.append((
            "IC50 / Dose-Response Curve",
            "Quantify the inhibition potency",
        ))

    # Default experiments if nothing specific
    if not experiments:
        experiments = [
            ("Thermal Shift Assay (DSF)", "Quick stability check for all sketched proteins"),
            ("Size Exclusion Chromatography", "Confirm complex formation and stoichiometry"),
        ]

    exp_cols = st.columns(min(len(experiments), 3))
    for i, (exp_name, exp_desc) in enumerate(experiments[:6]):
        with exp_cols[i % min(len(experiments), 3)]:
            st.markdown(
                f"**{exp_name}**  \n"
                f'<span style="font-size:0.82rem;color:rgba(60,60,67,0.6)">{exp_desc}</span>',
                unsafe_allow_html=True,
            )

    # ── 3. Create publication figure ──
    st.markdown("#### Create Publication Figure")
    st.caption(
        "Use the clean diagram above as a starting point, "
        "or find matching BioRender templates below:"
    )


def _build_network_figure(elements: list[dict], interactions: list[dict]) -> go.Figure:
    """Build an interactive Plotly network graph from sketch interpretation."""
    import math

    n = len(elements)
    if n == 0:
        return go.Figure()
    positions = {}
    for i, el in enumerate(elements):
        angle = 2 * math.pi * i / n
        positions[el["label"]] = (math.cos(angle), math.sin(angle))

    type_colors = {
        "protein": "#007AFF", "drug": "#34C759", "metabolite": "#FF9500",
        "pathway": "#AF52DE", "organelle": "#FF375F",
    }

    edge_x, edge_y, edge_labels = [], [], []
    for inter in interactions:
        src, tgt = inter.get("from", ""), inter.get("to", "")
        if src in positions and tgt in positions:
            x0, y0 = positions[src]
            x1, y1 = positions[tgt]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])
            edge_labels.append(
                ((x0 + x1) / 2, (y0 + y1) / 2, inter.get("label", inter.get("type", "")))
            )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=edge_x, y=edge_y, mode="lines",
        line=dict(width=2, color="#C6C6C8"),
        hoverinfo="none", showlegend=False,
    ))
    if edge_labels:
        fig.add_trace(go.Scatter(
            x=[e[0] for e in edge_labels], y=[e[1] for e in edge_labels],
            mode="text", text=[e[2] for e in edge_labels],
            textfont=dict(size=10, color="rgba(60,60,67,0.55)"),
            hoverinfo="none", showlegend=False,
        ))

    visible = [el for el in elements if el["label"] in positions]
    fig.add_trace(go.Scatter(
        x=[positions[el["label"]][0] for el in visible],
        y=[positions[el["label"]][1] for el in visible],
        mode="markers+text",
        marker=dict(
            size=30,
            color=[type_colors.get(el.get("type", "protein"), "#007AFF") for el in visible],
            line=dict(width=2, color="#000000"),
        ),
        text=[el["label"] for el in visible], textposition="top center",
        textfont=dict(size=12, color="#000000"),
        hovertext=[
            f"{el['label']}<br>Type: {el.get('type', '?')}<br>Role: {el.get('role', '?')}"
            for el in visible
        ],
        hoverinfo="text", showlegend=False,
    ))

    fig.update_layout(
        template="plotly_white", height=400,
        margin=dict(t=10, b=10, l=10, r=10),
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    )
    return fig


def _elements_to_simple_svg(elements: list[dict], interactions: list[dict]) -> str:
    """Generate a simple SVG diagram from elements and interactions."""
    import math

    n = len(elements)
    if n == 0:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="400"><text x="250" y="200" text-anchor="middle">No elements found</text></svg>'
    cx, cy, r = 250, 200, 150
    positions = {}
    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="400" '
        'style="background:#F2F2F7">',
        '<defs><marker id="arrow" viewBox="0 0 10 10" refX="5" refY="5" '
        'markerWidth="6" markerHeight="6" orient="auto-start-reverse">'
        '<path d="M 0 0 L 10 5 L 0 10 z" fill="#C6C6C8"/></marker></defs>',
    ]

    for i, el in enumerate(elements):
        angle = 2 * math.pi * i / n
        positions[el["label"]] = (cx + r * math.cos(angle), cy + r * math.sin(angle))

    for inter in interactions:
        src, tgt = inter.get("from", ""), inter.get("to", "")
        if src in positions and tgt in positions:
            x1, y1 = positions[src]
            x2, y2 = positions[tgt]
            svg_parts.append(
                f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" '
                f'stroke="#C6C6C8" stroke-width="2" marker-end="url(#arrow)"/>'
            )

    for el in elements:
        if el["label"] in positions:
            x, y = positions[el["label"]]
            svg_parts.append(
                f'<circle cx="{x:.0f}" cy="{y:.0f}" r="20" fill="#007AFF" '
                f'stroke="rgba(0,0,0,0.15)" stroke-width="2"/>'
            )
            svg_parts.append(
                f'<text x="{x:.0f}" y="{y - 28:.0f}" text-anchor="middle" '
                f'fill="#000000" font-size="12" font-family="sans-serif">'
                f"{el['label']}</text>"
            )

    svg_parts.append("</svg>")
    return "\n".join(svg_parts)


def _fallback_sketch_response() -> dict:
    """Fallback response when no API key is available."""
    return {
        "title": "API Key Required",
        "description": (
            "Sketch interpretation requires an Anthropic API key with vision support."
        ),
        "elements": [],
        "interactions": [],
        "mermaid": "",
        "testable_prediction": (
            "Set ANTHROPIC_API_KEY in your .env file to enable this feature."
        ),
        "confidence_note": "No interpretation performed.",
    }


def _render_sketch_biorender(interpretation: dict, query: ProteinQuery | None):
    """Render BioRender figure generation + template suggestions for the sketch."""
    st.divider()

    # ── 1. AI Figure Generation (primary action) ──
    st.markdown("##### Generate Figure with BioRender")

    fig_cache_key = "sketch_biorender_figure"
    fig_result = st.session_state.get(fig_cache_key)

    if fig_result is None:
        if st.button(
            "Generate Figure with BioRender",
            type="primary",
            key="sketch_br_generate",
        ):
            with st.status("Generating pathway diagram via BioRender MCP..."):
                from src.biorender_search import generate_biorender_figure

                fig_result = generate_biorender_figure(interpretation, query)
                st.session_state[fig_cache_key] = fig_result or {"_failed": True}
    elif fig_result.get("_failed"):
        st.warning(
            "BioRender figure generation is not available. "
            "Check that both `BIORENDER_TOKEN` and `ANTHROPIC_API_KEY` are set in your `.env` file. "
            "You can still use the template search below."
        )
    else:
        # Show successful generation result
        fig_desc = fig_result.get("figure_description", "")
        fig_url = fig_result.get("figure_url")

        if fig_desc:
            st.info(f"**Generated:** {fig_desc}")
        if fig_url:
            st.markdown(
                f'<a href="{fig_url}" target="_blank" '
                f'style="display:inline-block;padding:8px 20px;background:#007AFF;'
                f'color:white;border-radius:6px;text-decoration:none;font-weight:600">'
                f"Open Figure in BioRender &rarr;</a>",
                unsafe_allow_html=True,
            )
        elif fig_desc:
            st.caption(
                "No direct URL was returned. The figure may be available "
                "in your BioRender workspace."
            )

    # ── 2. Template Search (secondary option) ──
    st.markdown("##### Or Find Similar Templates")

    br_cache_key = "sketch_biorender_results"
    br_results = st.session_state.get(br_cache_key)

    if br_results is None:
        if st.button(
            "Search BioRender Templates",
            type="secondary",
            key="sketch_br_search",
        ):
            with st.status("Searching BioRender for matching templates..."):
                from src.biorender_search import search_biorender_for_sketch

                br_results = search_biorender_for_sketch(interpretation, query)
                st.session_state[br_cache_key] = br_results
        return

    templates = [r for r in br_results if r.get("type") == "template"]
    icons = [r for r in br_results if r.get("type") == "icon"]

    if templates:
        cols = st.columns(min(len(templates), 3))
        for i, tmpl in enumerate(templates[:6]):
            with cols[i % min(len(templates), 3)]:
                url_btn = (
                    f'<a href="{tmpl["url"]}" target="_blank" '
                    f'style="color:#007AFF;font-size:0.8em;text-decoration:none">'
                    f"Open in BioRender &rarr;</a>"
                ) if tmpl.get("url") else ""
                st.markdown(
                    f'<div class="glow-card" style="min-height:90px">'
                    f'<div style="font-weight:600;font-size:0.9rem;color:#007AFF;'
                    f'margin-bottom:4px">{tmpl["name"]}</div>'
                    f'<div style="font-size:0.82rem;color:rgba(60,60,67,0.6);line-height:1.3">'
                    f'{tmpl.get("description", "")}</div>'
                    f"{url_btn}"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    if icons:
        icon_html = " ".join(
            f'<span style="display:inline-block;padding:4px 10px;margin:2px;'
            f'border:1px solid rgba(0,0,0,0.06);border-radius:6px;font-size:0.8rem">'
            f'<span style="color:#34C759;margin-right:4px">&#9679;</span>'
            f'{icon["name"]}</span>'
            for icon in icons
        )
        st.markdown(icon_html, unsafe_allow_html=True)

    st.caption("Templates matched to your sketch via BioRender.")
