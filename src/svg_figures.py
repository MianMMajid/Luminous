"""Data-driven scientific SVG figure generation using Claude.

Gathers computed data from session_state, pre-computes layout coordinates
in Python, and sends structured JSON to Claude so every number in the
resulting SVG is real — not hallucinated.
"""
from __future__ import annotations

import json
import re

import streamlit as st
from anthropic import Anthropic

from src.bioicons_client import get_icon_catalog_for_prompt, postprocess_svg_with_icons
from src.config import ANTHROPIC_API_KEY, CLAUDE_FAST_MODEL
from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit

# ── viewBox constants ──
_W, _H = 800, 520


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Data Gathering
# ═══════════════════════════════════════════════════════════════════════════════


def gather_figure_data(
    query: ProteinQuery,
    prediction: PredictionResult | None,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
) -> dict:
    """Read all computed data from session_state into a flat dict."""
    protein = query.protein_name
    mutation = query.mutation

    sa = st.session_state.get("structure_analysis") or {}
    variant_data = st.session_state.get(f"variant_data_{protein}")
    interpretation = st.session_state.get("interpretation", "")

    # Residue counts
    residue_ids = sa.get("residue_ids", [])
    n_residues = len(residue_ids) or (len(prediction.residue_ids) if prediction else 0)
    first_res = residue_ids[0] if residue_ids else (prediction.residue_ids[0] if prediction and prediction.residue_ids else 1)
    last_res = residue_ids[-1] if residue_ids else (prediction.residue_ids[-1] if prediction and prediction.residue_ids else n_residues)

    # SSE composition
    sse_counts = sa.get("sse_counts", {})
    total_sse = sum(sse_counts.values()) or 1
    helix_pct = round(100 * sse_counts.get("a", 0) / total_sse, 1)
    sheet_pct = round(100 * sse_counts.get("b", 0) / total_sse, 1)
    coil_pct = round(100 * sse_counts.get("c", 0) / total_sse, 1)

    # Mutation-specific
    mut_sasa = sa.get("mutation_sasa")
    mut_buried = sa.get("mutation_is_buried")
    mut_sse = sa.get("mutation_sse")
    mut_centrality = sa.get("mutation_centrality")
    mut_centrality_pct = sa.get("mutation_centrality_percentile")
    mut_in_pocket = sa.get("mutation_in_pocket")
    mut_to_pocket = sa.get("mutation_to_pocket_min_distance")

    # Network
    hub_residues = sa.get("hub_residues", [])[:8]

    # Pockets
    pockets_key = f"pockets_{protein}_{mutation}"
    pockets_data = st.session_state.get(pockets_key, {})
    pockets = pockets_data.get("pockets", [])[:3] if isinstance(pockets_data, dict) else []

    # Variants
    variant_info = {}
    if variant_data and isinstance(variant_data, dict):
        pathogenic_count = variant_data.get("pathogenic_count", 0)
        total_variants = variant_data.get("total", 0)
        raw_positions = variant_data.get("pathogenic_positions", {})
        if isinstance(raw_positions, dict):
            pathogenic_positions = sorted(
                (
                    int(pos) if isinstance(pos, str) and pos.isdigit() else pos
                    for pos in raw_positions.keys()
                ),
                key=lambda pos: (isinstance(pos, str), pos),
            )[:10]
        elif isinstance(raw_positions, list):
            pathogenic_positions = raw_positions[:10]
        else:
            pathogenic_positions = []
        variant_info = {
            "total": total_variants,
            "pathogenic_count": pathogenic_count,
            "pathogenic_positions": pathogenic_positions,
        }

    # Hidden spatial clusters
    hidden_clusters = sa.get("hidden_spatial_clusters", [])[:5]

    # Drugs from bio context
    drugs = []
    if bio_context and bio_context.drugs:
        for d in bio_context.drugs[:6]:
            drugs.append({
                "name": d.name,
                "phase": d.phase or "Unknown",
                "mechanism": d.mechanism or "",
            })

    # Disease associations
    diseases = []
    if bio_context and bio_context.disease_associations:
        for d in bio_context.disease_associations[:4]:
            diseases.append({
                "disease": d.disease,
                "score": round(d.score, 2) if d.score else None,
            })

    # Pathways
    pathways = (bio_context.pathways[:6] if bio_context else [])

    # Drug resistance
    resistance = _get_resistance_data(protein, mutation)

    # Confidence
    confidence_score = trust_audit.confidence_score if trust_audit else None
    overall_confidence = trust_audit.overall_confidence if trust_audit else None

    # pLDDT stats
    plddt_stats = {}
    if prediction and prediction.plddt_per_residue:
        plddt = prediction.plddt_per_residue
        plddt_stats = {
            "mean": round(sum(plddt) / len(plddt), 1),
            "min": round(min(plddt), 1),
            "max": round(max(plddt), 1),
        }

    return {
        "protein_name": protein,
        "mutation": mutation,
        "question_type": query.question_type,
        "n_residues": n_residues,
        "first_residue": first_res,
        "last_residue": last_res,
        "sse": {"helix_pct": helix_pct, "sheet_pct": sheet_pct, "coil_pct": coil_pct},
        "mutation_data": {
            "sasa": round(mut_sasa, 1) if mut_sasa is not None else None,
            "is_buried": mut_buried,
            "sse": _sse_label(mut_sse),
            "centrality": round(mut_centrality, 4) if mut_centrality else None,
            "centrality_percentile": round(mut_centrality_pct, 1) if mut_centrality_pct else None,
            "in_pocket": mut_in_pocket,
            "distance_to_pocket": round(mut_to_pocket, 1) if mut_to_pocket is not None else None,
        } if mutation else None,
        "hub_residues": hub_residues,
        "pockets": [
            {"rank": p.get("rank", i + 1), "score": round(p.get("score", 0), 1),
             "residues": p.get("residues", [])[:5]}
            for i, p in enumerate(pockets)
        ],
        "variants": variant_info,
        "hidden_spatial_clusters": hidden_clusters,
        "drugs": drugs,
        "diseases": diseases,
        "pathways": pathways,
        "resistance": resistance,
        "confidence": {
            "score": round(confidence_score, 3) if confidence_score else None,
            "level": overall_confidence,
        },
        "plddt": plddt_stats,
        "interpretation_summary": (interpretation or "")[:400],
    }


def _sse_label(sse_code: str | None) -> str:
    if sse_code == "a":
        return "α-helix"
    if sse_code == "b":
        return "β-sheet"
    return "coil/loop"


def _get_resistance_data(protein: str, mutation: str | None) -> dict | None:
    """Try to get resistance data from the drug_resistance component."""
    try:
        from components.drug_resistance import _RESISTANCE_DB
        rdb = _RESISTANCE_DB.get(protein.upper(), {})
        if not rdb or not mutation:
            return None
        muts = rdb.get("mutations", {})
        mut_data = muts.get(mutation)
        if not mut_data:
            return None
        drugs_affected = mut_data.get("drugs_affected", [])[:4]
        # Extract top fold change from nested drug list
        top_fc = None
        if isinstance(drugs_affected, list) and drugs_affected:
            if isinstance(drugs_affected[0], dict):
                for da in drugs_affected:
                    fc_str = da.get("fold_change", "")
                    if fc_str and fc_str != "1x":
                        top_fc = fc_str
                        break
        if not top_fc:
            top_fc = mut_data.get("fold_change")
        return {
            "drugs_affected": drugs_affected,
            "fold_change": top_fc,
            "mechanism": mut_data.get("mechanism", ""),
            "clinical_note": mut_data.get("clinical_note", ""),
        }
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 2. System Prompts (figure-type-specific)
# ═══════════════════════════════════════════════════════════════════════════════

_BASE_RULES = f"""\
STRICT SVG RULES:
1. Output ONLY valid SVG code — no markdown fences, no explanation.
2. viewBox="0 0 {_W} {_H}", white background rect.
3. Color palette:
   - Proteins: #4A90D9 (blue)   - Mutations/damage: #E74C3C (red)
   - Drugs: #50C878 (green)     - Pathways: #7B68EE (purple)
   - Arrows: #555 (gray)        - Labels: #333, font-family="Arial, Helvetica, sans-serif"
   - Confidence high: #4A90D9   - Confidence low: #E74C3C
   - α-helix: #4A90D9   - β-sheet: #50C878   - Coil: #D1D1D6
4. Use rounded rectangles (rx=8), circles, lines, text, path with <marker> arrowheads.
5. DO NOT use <image>, <foreignObject>, or external references.
6. Keep text readable: font-size ≥ 10, max ~15 labeled entities.
7. Include a concise title (font-size 16, bold) and a small legend.
8. CRITICAL: Use ONLY the real values from the JSON data. Never invent numbers.
9. Every data label must come from the JSON — if a value is null, omit it.
"""

_MECHANISM_SYSTEM = f"""\
You are a scientific SVG illustrator specializing in drug mechanism-of-action diagrams.

Given a JSON payload of real computed data, generate a publication-quality SVG showing:
- Central protein entity (rounded rect, blue) with the mutation site (red star) if present
- Drug molecules arranged around the protein (green circles with name + phase labels)
- Arrows from drugs to protein showing inhibition (flat head) or binding
- If resistance data exists, show fold-change values and resistance mechanism
- Binding pocket annotation (labeled with pocket score)
- Downstream pathway cascade (purple boxes, vertical flow below protein)
- Disease associations (red text at bottom)
- Small metrics box in corner: confidence score, residue count

{_BASE_RULES}
"""

_MUTATION_IMPACT_SYSTEM = f"""\
You are a scientific SVG illustrator specializing in mutation impact diagrams.

Given a JSON payload of real computed data, generate a publication-quality SVG showing:
- Horizontal protein domain bar (top third, ~60px tall) spanning first_residue to last_residue
  - Color segments by SSE composition: blue=helix, green=sheet, gray=coil (use % widths)
- Mutation site marked with a red diamond on the domain bar, with a callout box showing:
  SASA value, burial status, SSE type, centrality percentile
- Pathogenic variant positions as orange triangles below the domain bar
- If hidden_spatial_clusters exist, draw dashed arcs between seq-distant but 3D-close residues
- Hub residues marked as blue stars above the domain bar
- Binding pocket regions highlighted in yellow on the domain bar
- Drug sensitivity section below: affected drugs with fold-change arrows
- Metrics corner: confidence score, total variants, pathogenic count

{_BASE_RULES}
"""

_OVERVIEW_SYSTEM = f"""\
You are a scientific SVG illustrator specializing in protein overview diagrams.

Given a JSON payload of real computed data, generate a publication-quality SVG showing:
- Horizontal protein architecture bar (center, ~50px tall) with SSE coloring:
  - α-helix segments: #4A90D9, β-sheet: #50C878, coil: #D1D1D6
  - Width proportional to SSE percentages from data
- Residue numbering at start and end of bar
- Hub residues marked as labeled stars above the bar
- Binding pocket regions as highlighted yellow bands on the bar
- Confidence ribbon below the bar (color bands from pLDDT stats)
- Key metrics panel (right side): residue count, confidence, SSE composition pie
- If drugs exist, show them as labeled green nodes connected to the protein
- If diseases exist, list them below with scores
- Title includes protein name

{_BASE_RULES}
"""

# ═══════════════════════════════════════════════════════════════════════════════
# 3. SVG Generation Functions
# ═══════════════════════════════════════════════════════════════════════════════


def _call_claude_svg(system_prompt: str, data: dict) -> str | None:
    """Send structured data to Claude and get SVG back."""
    if not ANTHROPIC_API_KEY:
        return None

    icon_catalog = get_icon_catalog_for_prompt()

    user_msg = (
        f"Generate an SVG diagram using this real computed data:\n\n"
        f"```json\n{json.dumps(data, indent=2, default=str)}\n```\n\n"
        f"{icon_catalog}\n\n"
        f"Use the exact values from the JSON. Every number must be real."
    )

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=6000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                svg = block.text.strip()
                # Strip markdown fences if present
                if svg.startswith("```"):
                    svg = svg.split("\n", 1)[-1]
                    svg = svg.rsplit("```", 1)[0].strip()
                if "<svg" in svg and "</svg>" in svg:
                    # Post-process: inject bioicons for any placeholders
                    svg = postprocess_svg_with_icons(svg)
                    return svg
    except Exception:
        pass
    return None


@st.cache_data(ttl=3600, show_spinner=False)
def generate_mechanism_svg(data_json: str) -> str | None:
    """Generate a Mechanism of Action SVG from structured data."""
    data = json.loads(data_json)
    return _call_claude_svg(_MECHANISM_SYSTEM, data)


@st.cache_data(ttl=3600, show_spinner=False)
def generate_mutation_impact_svg(data_json: str) -> str | None:
    """Generate a Mutation Impact Map SVG from structured data."""
    data = json.loads(data_json)
    return _call_claude_svg(_MUTATION_IMPACT_SYSTEM, data)


@st.cache_data(ttl=3600, show_spinner=False)
def generate_overview_svg(data_json: str) -> str | None:
    """Generate a Protein Overview SVG from structured data."""
    data = json.loads(data_json)
    return _call_claude_svg(_OVERVIEW_SYSTEM, data)


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Mermaid Pathway Export
# ═══════════════════════════════════════════════════════════════════════════════


def generate_mermaid_pathway(gathered: dict) -> str | None:
    """Generate Mermaid flowchart notation from real pathway/interaction data.

    Produces deterministic output — no LLM call needed.
    """
    protein = gathered["protein_name"]
    mutation = gathered.get("mutation")
    drugs = gathered.get("drugs", [])
    pathways = gathered.get("pathways", [])
    diseases = gathered.get("diseases", [])
    resistance = gathered.get("resistance")

    if not drugs and not pathways and not diseases:
        return None

    lines = ["graph TD"]

    # Protein node
    protein_id = _mermaid_id(protein)
    lines.append(f"    {protein_id}[{protein}]")

    # Mutation modifier
    if mutation:
        mut_id = _mermaid_id(mutation)
        burial = ""
        md = gathered.get("mutation_data")
        if md:
            if md.get("is_buried"):
                burial = ", buried"
            elif md.get("sasa") is not None:
                burial = f", SASA {md['sasa']}Å²"
        lines.append(f'    {mut_id}{{{{{mutation}{burial}}}}}')
        lines.append(f"    {mut_id} -.->|modifies| {protein_id}")

    # Drugs
    # Build resistance lookup: drug_name -> fold_change
    resistance_lookup: dict[str, str] = {}
    if resistance:
        for da in resistance.get("drugs_affected", []):
            if isinstance(da, dict):
                resistance_lookup[da.get("name", "")] = da.get("fold_change", "?")
            elif isinstance(da, str):
                resistance_lookup[da] = resistance.get("fold_change") or "?"

    for i, drug in enumerate(drugs):
        d_id = _mermaid_id(drug["name"]) + f"_{i}"
        phase = drug.get("phase", "")
        mech = drug.get("mechanism", "inhibits")
        fc = resistance_lookup.get(drug["name"])
        if fc and fc != "1x":
            lines.append(f"    {d_id}([{drug['name']} — {phase}])")
            lines.append(f"    {d_id} -->|{mech}| {protein_id}")
            lines.append(f'    {d_id} -. "{fc} resistance" .-> {mut_id if mutation else protein_id}')
        else:
            lines.append(f"    {d_id}([{drug['name']} — {phase}])")
            lines.append(f"    {d_id} -->|{mech}| {protein_id}")

    # Pathways
    prev_id = protein_id
    for j, pw in enumerate(pathways):
        pw_id = _mermaid_id(pw) + f"_p{j}"
        lines.append(f"    {pw_id}[/{pw}/]")
        edge_label = "activates" if j == 0 else "signals"
        lines.append(f"    {prev_id} -->|{edge_label}| {pw_id}")
        prev_id = pw_id

    # Diseases
    for k, dis in enumerate(diseases):
        dis_id = _mermaid_id(dis["disease"]) + f"_d{k}"
        score_label = f" ({dis['score']})" if dis.get("score") else ""
        lines.append(f"    {dis_id}({dis['disease']}{score_label})")
        lines.append(f"    {prev_id} -->|associated| {dis_id}")

    # Styling
    lines.append("")
    lines.append(f"    style {protein_id} fill:#4A90D9,color:#fff,stroke:#2c5ea0")
    if mutation:
        lines.append(f"    style {mut_id} fill:#E74C3C,color:#fff,stroke:#c0392b")
    for i, drug in enumerate(drugs):
        d_id = _mermaid_id(drug["name"]) + f"_{i}"
        lines.append(f"    style {d_id} fill:#50C878,color:#fff,stroke:#3a9d5c")

    return "\n".join(lines)


def _mermaid_id(name: str) -> str:
    """Convert a name to a valid Mermaid node ID."""
    return re.sub(r"[^a-zA-Z0-9]", "_", name).strip("_")[:30]


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Convenience: choose best figure types for query
# ═══════════════════════════════════════════════════════════════════════════════


def get_figure_types(query: ProteinQuery) -> list[tuple[str, str, callable]]:
    """Return (tab_label, cache_suffix, generate_fn) tuples for this query type."""
    types = []

    if query.question_type == "druggability":
        types.append(("Mechanism of Action", "mechanism", generate_mechanism_svg))
        if query.mutation:
            types.append(("Mutation Impact", "mutation_impact", generate_mutation_impact_svg))
        types.append(("Protein Overview", "overview", generate_overview_svg))

    elif query.question_type == "mutation_impact":
        types.append(("Mutation Impact", "mutation_impact", generate_mutation_impact_svg))
        types.append(("Mechanism of Action", "mechanism", generate_mechanism_svg))
        types.append(("Protein Overview", "overview", generate_overview_svg))

    elif query.question_type == "binding":
        types.append(("Mechanism of Action", "mechanism", generate_mechanism_svg))
        if query.mutation:
            types.append(("Mutation Impact", "mutation_impact", generate_mutation_impact_svg))
        types.append(("Protein Overview", "overview", generate_overview_svg))

    else:  # structure
        types.append(("Protein Overview", "overview", generate_overview_svg))
        if query.mutation:
            types.append(("Mutation Impact", "mutation_impact", generate_mutation_impact_svg))

    return types
