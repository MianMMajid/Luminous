"""Publication-quality figure generation using Claude's Code Execution Tool.

Sends structured biological data to Claude, which writes and executes
matplotlib/seaborn code in a sandboxed environment. Returns actual rendered
PNG images — not LLM-hallucinated SVG.

Uses the code_execution_20250825 tool type + files-api-2025-04-14 beta.
"""
from __future__ import annotations

import json
from typing import Any

import streamlit as st
from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_FAST_MODEL


# ═══════════════════════════════════════════════════════════════════════════════
# Figure type definitions — each has a prompt that tells Claude what to plot
# ═══════════════════════════════════════════════════════════════════════════════

_FIGURE_TYPES: dict[str, dict[str, str]] = {
    "confidence_landscape": {
        "label": "Confidence Landscape",
        "description": (
            "A publication-quality multi-panel figure with:\n"
            "- Top panel: per-residue pLDDT line plot with colored confidence bands "
            "(very high >90 blue, confident 70-90 cyan, low 50-70 yellow, very low <50 orange)\n"
            "- Highlight mutation position with a red vertical line + annotation\n"
            "- Mark hub residues with star markers\n"
            "- Mark pocket residues with shaded vertical spans\n"
            "- Bottom panel: SSE strip (helix=blue, sheet=green, coil=gray) as colored bars\n"
            "- Use matplotlib with seaborn style 'whitegrid'. Title with protein name."
        ),
    },
    "variant_heatmap": {
        "label": "Variant Impact Heatmap",
        "description": (
            "A clustered heatmap of variant impact scores:\n"
            "- Rows = variant positions (use position numbers as labels)\n"
            "- Columns = data sources (CADD, SIFT, PolyPhen-2, REVEL, gnomAD AF) — "
            "only include columns where data exists\n"
            "- Normalize each column to 0-1 range for consistent coloring\n"
            "- For SIFT: D=1.0, T=0.0. For PolyPhen-2: D=1.0, P=0.5, B=0.0\n"
            "- Use seaborn clustermap with 'YlOrRd' colormap\n"
            "- Annotate cells with original values\n"
            "- If fewer than 3 positions have data, use a simple heatmap instead of clustermap\n"
            "- Title: '{protein_name} Variant Impact Assessment'"
        ),
    },
    "structure_quality": {
        "label": "Structure Quality Dashboard",
        "description": (
            "A 2x2 multi-panel dashboard:\n"
            "- Panel A (top-left): pLDDT distribution histogram with KDE overlay, "
            "colored by confidence bands, vertical lines for mean/median\n"
            "- Panel B (top-right): SSE composition donut chart (helix/sheet/coil) "
            "with percentages, nice pastel colors\n"
            "- Panel C (bottom-left): Residue centrality scatter — if hub_residues exist, "
            "show a bar chart of hub residue positions vs centrality, colored by whether "
            "they're near the mutation\n"
            "- Panel D (bottom-right): Pocket summary — horizontal bar chart of pocket "
            "scores with pocket ranks labeled\n"
            "- Use matplotlib GridSpec, tight_layout. Title: '{protein_name} Structure Quality'.\n"
            "- If a panel's data is missing, show a text annotation 'No data available'"
        ),
    },
    "drug_landscape": {
        "label": "Drug–Target Landscape",
        "description": (
            "A publication figure showing drug-target relationships:\n"
            "- Main: scatter or bubble chart with drugs. X-axis = clinical phase "
            "(Preclinical=0, Phase I=1, Phase II=2, Phase III=3, Approved=4), "
            "Y-axis can be an index or mechanism category\n"
            "- Bubble size proportional to number of drugs in that phase\n"
            "- Color by mechanism of action category\n"
            "- If resistance data exists, annotate resistant drugs with red edges "
            "and fold-change labels\n"
            "- If disease associations exist, add a side panel or annotation showing "
            "disease-drug connections\n"
            "- Use seaborn style. Title: '{protein_name} Drug Landscape'"
        ),
    },
    "mutation_context": {
        "label": "Mutation in Context",
        "description": (
            "A composite figure centered on the mutation:\n"
            "- Top: linear protein map (horizontal bar) with SSE coloring, "
            "mutation position marked with red triangle, pocket regions in yellow\n"
            "- Middle: radial/polar plot or bar chart showing mutation properties "
            "(SASA, centrality percentile, burial status, distance to pocket) "
            "as a spider/radar chart with labeled axes\n"
            "- Bottom: if pathogenic positions exist, show a density/histogram of "
            "known pathogenic variants along the protein with the query mutation highlighted\n"
            "- Use tight_layout and consistent color scheme. "
            "Title: '{protein_name} {mutation} Structural Context'"
        ),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Core API interaction
# ═══════════════════════════════════════════════════════════════════════════════


def _build_system_prompt() -> str:
    return (
        "You are a scientific data visualization expert. You write Python code "
        "that produces publication-quality figures using matplotlib and seaborn.\n\n"
        "RULES:\n"
        "1. Use ONLY the data provided in the JSON — never invent numbers.\n"
        "2. Save figures to files using plt.savefig('figure.png', dpi=150, "
        "bbox_inches='tight', facecolor='white').\n"
        "3. Use seaborn style: sns.set_theme(style='whitegrid', font_scale=1.1)\n"
        "4. Use a clean, professional color palette.\n"
        "5. Always include axis labels, title, and legend where appropriate.\n"
        "6. Handle missing/None data gracefully — skip panels or show 'N/A'.\n"
        "7. Import only: matplotlib, seaborn, numpy, pandas, scipy.\n"
        "8. The figure must be self-contained in a single script.\n"
        "9. Print a confirmation message when done."
    )


@st.cache_data(ttl=3600, show_spinner=False)
def generate_code_execution_figure(
    figure_type: str,
    data_json: str,
) -> dict[str, Any] | None:
    """Generate a figure using Claude's Code Execution Tool.

    Returns dict with:
        - "image_bytes": PNG bytes of the generated figure
        - "code": the Python code that was executed
        - "stdout": execution stdout
    Or None if generation fails.
    """
    if not ANTHROPIC_API_KEY:
        return None

    figure_def = _FIGURE_TYPES.get(figure_type)
    if not figure_def:
        return None

    data = json.loads(data_json)
    protein_name = data.get("protein_name", "Protein")
    mutation = data.get("mutation", "")

    # Format the description with protein/mutation names
    description = figure_def["description"].format(
        protein_name=protein_name,
        mutation=mutation or "N/A",
    )

    user_message = (
        f"Generate a {figure_def['label']} figure.\n\n"
        f"FIGURE SPECIFICATION:\n{description}\n\n"
        f"DATA (use these exact values):\n"
        f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n\n"
        f"Write Python code to create this figure and save it as 'figure.png'. "
        f"Use only matplotlib, seaborn, numpy, and pandas."
    )

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.beta.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=4096,
            system=_build_system_prompt(),
            tools=[{"type": "code_execution_20250825", "name": "code_execution"}],
            messages=[{"role": "user", "content": user_message}],
            betas=["files-api-2025-04-14"],
        )

        return _extract_results(client, response)

    except Exception as e:
        import traceback
        return {"error": str(e), "traceback": traceback.format_exc()}


def _extract_results(
    client: Anthropic,
    response,
) -> dict[str, Any] | None:
    """Extract image bytes, code, and stdout from the API response.

    Actual response structure (code_execution_20250825):
      - server_tool_use (name=text_editor_code_execution): creates .py file
        → input has 'file_text' with the Python code
      - text_editor_code_execution_tool_result: confirms file creation
      - server_tool_use (name=bash_code_execution): runs the script
        → input has 'command' string
      - bash_code_execution_tool_result: contains execution results
        → .content is BashCodeExecutionResultBlock with:
          .stdout, .stderr, .return_code,
          .content = List[BashCodeExecutionOutputBlock] each with .file_id
    """
    result: dict[str, Any] = {
        "image_bytes": None,
        "code": None,
        "stdout": None,
    }

    for block in response.content:
        # Capture the Python code from the text editor tool
        if block.type == "server_tool_use":
            if getattr(block, "name", "") == "text_editor_code_execution":
                inp = getattr(block, "input", {}) or {}
                file_text = inp.get("file_text", "")
                if file_text:
                    result["code"] = file_text

        # Capture bash execution results (contains generated files)
        if block.type == "bash_code_execution_tool_result":
            inner = block.content
            if hasattr(inner, "stdout"):
                result["stdout"] = inner.stdout or ""
            if hasattr(inner, "stderr") and inner.stderr:
                result["stderr"] = inner.stderr
            # inner.content = List[BashCodeExecutionOutputBlock]
            for output in getattr(inner, "content", []) or []:
                if hasattr(output, "file_id") and output.file_id:
                    try:
                        file_response = client.beta.files.download(
                            output.file_id
                        )
                        result["image_bytes"] = file_response.read()
                    except Exception:
                        pass

    if result["image_bytes"]:
        return result
    return result if result.get("error") else None


# ═══════════════════════════════════════════════════════════════════════════════
# Public helpers
# ═══════════════════════════════════════════════════════════════════════════════


def get_available_figure_types(data: dict) -> list[tuple[str, str]]:
    """Return (type_key, label) pairs for figures that make sense given the data."""
    available = []

    # Confidence landscape — needs pLDDT data
    if data.get("plddt") and data["plddt"].get("mean"):
        available.append(("confidence_landscape", "Confidence Landscape"))

    # Variant heatmap — needs variant data
    variants = data.get("variants", {})
    if variants.get("pathogenic_count", 0) > 0 or variants.get("total", 0) > 0:
        available.append(("variant_heatmap", "Variant Impact Heatmap"))

    # Structure quality — always available if we have basic data
    if data.get("n_residues", 0) > 0:
        available.append(("structure_quality", "Structure Quality Dashboard"))

    # Drug landscape — needs drug data
    if data.get("drugs"):
        available.append(("drug_landscape", "Drug–Target Landscape"))

    # Mutation context — needs mutation data
    if data.get("mutation_data"):
        available.append(("mutation_context", "Mutation in Context"))

    return available
