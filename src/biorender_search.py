from __future__ import annotations

import streamlit as st
from anthropic import Anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    BIORENDER_MCP_URL,
    BIORENDER_TOKEN,
    CLAUDE_FAST_MODEL,
    MCP_BETA_HEADER,
)
from src.models import ProteinQuery

# ---------------------------------------------------------------------------
# Real BioRender URLs (verified working, public-facing)
# ---------------------------------------------------------------------------

_BR = "https://www.biorender.com"

# Real template slugs on biorender.com/template/{slug}
_TEMPLATE_URLS: dict[str, str] = {
    "protein_structure": f"{_BR}/template/protein-structure",
    "protein_interaction": f"{_BR}/template/protein-protein-interaction-ppi-network",
    "protein_ligand": f"{_BR}/template/protein-ligand-binding",
    "protein_interaction_workflow": f"{_BR}/template/protein-interaction-workflow",
    "drug_discovery": f"{_BR}/template/drug-discovery-development-funnel",
    "drug_targeting": f"{_BR}/template/drug-targeting-in-cytokine-receptor-pathways",
    "drug_pipeline": f"{_BR}/template/drug-pipeline",
    "drug_delivery": (
        f"{_BR}/template/nanotechnology-based-targeted-drug-delivery"
        "-in-cardiovascular-diseases"
    ),
    "mechanism_daptomycin": f"{_BR}/template/daptomycin-mechanism-of-action",
    "mechanism_bispecific": f"{_BR}/template/bispecific-antibody-mechanism-of-action",
    "mechanism_mrna": f"{_BR}/template/mrna-vaccine-structure-and-mechanism-of-action",
    "mechanism_diphtheria": f"{_BR}/template/mechanism-of-action-diphtheria-toxin",
    "mutagenesis": f"{_BR}/template/site-directed-mutagenesis",
    "mutation_breeding": f"{_BR}/template/integrated-mutation-breeding",
    "virus_mutation": f"{_BR}/template/virus-mutation",
    "msa": f"{_BR}/template/multiple-sequence-alignment-protein",
    "mapk_pathway": f"{_BR}/template/mapk-signaling-pathway",
    "mtor_pathway": f"{_BR}/template/mtor-signaling-pathway",
    "jak_stat": f"{_BR}/template/cytokine-signaling-through-the-jak-stat-pathway",
    "tgf_beta": f"{_BR}/template/tgf-beta-signaling-pathway",
    "tlr_pathway": f"{_BR}/template/tlr-signaling-pathway",
}

# Icon search via library (public, Algolia-powered search)
_ICON_SEARCH = f"{_BR}/library?q="

# Icon category pages
_ICON_CATEGORIES: dict[str, str] = {
    "proteins": f"{_BR}/categories/proteins",
    "receptors": f"{_BR}/sub-categories/receptors-and-ligands",
    "antibodies": f"{_BR}/sub-categories/antibodies",
    "enzymes": f"{_BR}/sub-categories/enzymes",
    "transporters": f"{_BR}/sub-categories/transporters",
    "chemistry": f"{_BR}/categories/chemistry",
    "cell_types": f"{_BR}/categories/cell-types",
    "nucleic_acids": f"{_BR}/categories/nucleic-acids",
}

# Template gallery (public)
_TEMPLATE_GALLERY = f"{_BR}/templates"

# Question type to figure context mapping
_QUESTION_FIGURE_CONTEXT = {
    "druggability": (
        "drug-target interaction figures, mechanism of action diagrams, "
        "pharmacological binding illustrations, drug discovery pipeline visuals"
    ),
    "mutation_impact": (
        "structural comparison figures showing wild-type vs mutant, "
        "mutation impact pathway diagrams, residue-level annotation figures"
    ),
    "binding": (
        "protein-protein interaction diagrams, binding interface illustrations, "
        "complex assembly figures, contact residue maps"
    ),
    "structure": (
        "protein domain architecture diagrams, secondary structure illustrations, "
        "3D structure annotation figures, structural feature highlights"
    ),
}

# ---------------------------------------------------------------------------
# AI SVG Diagram Generator (Claude generates vector scientific illustrations)
# ---------------------------------------------------------------------------

_SVG_DIAGRAM_SYSTEM = """\
You are an expert scientific illustrator who creates publication-quality SVG \
diagrams for molecular biology. Given a protein analysis, generate a clean, \
informative SVG pathway or mechanism diagram.

STRICT RULES:
1. Output ONLY valid SVG code — no markdown fences, no explanation, no text \
before or after the SVG.
2. Use a viewBox of "0 0 800 500" with white background.
3. Use a professional color palette:
   - Proteins: #4A90D9 (blue), #7B68EE (purple)
   - DNA/RNA: #F5A623 (amber)
   - Drugs/small molecules: #50C878 (green)
   - Mutations/damage: #E74C3C (red)
   - Arrows/connections: #555555 (dark gray)
   - Labels: #333333, font-family="Arial, Helvetica, sans-serif"
4. Include:
   - A title at the top (font-size 18, bold)
   - Rounded rectangles for entities (rx=8)
   - Labeled arrows showing interactions (use <marker> for arrowheads)
   - A subtle legend in the bottom-right corner
5. Keep it clean — max 8-10 entities. White space is good.
6. Use <text> elements for all labels (font-size 12-14).
7. Do NOT use <image>, <foreignObject>, or external references.
8. Ensure all elements are visible within the viewBox."""


@st.cache_data(ttl=3600, show_spinner=False)
def generate_svg_diagram(
    protein_name: str,
    mutation: str | None,
    question_type: str,
    interaction_partner: str | None = None,
    interpretation: str | None = None,
) -> str | None:
    """Use Claude to generate an SVG scientific diagram.

    Returns SVG string or None if generation fails.
    """
    if not ANTHROPIC_API_KEY:
        return None

    parts = [f"Protein: {protein_name}"]
    if mutation:
        parts.append(f"Mutation: {mutation}")
    if interaction_partner:
        parts.append(f"Interaction partner: {interaction_partner}")
    parts.append(f"Analysis type: {question_type}")

    if interpretation:
        parts.append(f"Key findings: {interpretation[:600]}")

    # Add question-type-specific guidance
    if question_type == "druggability":
        parts.append(
            "Show: protein target with binding pocket, drug molecules "
            "approaching, downstream pathway affected, resistance mechanism"
        )
    elif question_type == "binding":
        partner = interaction_partner or "binding partner"
        parts.append(
            f"Show: {protein_name} and {partner} as distinct entities, "
            "binding interface between them, key residues at interface, "
            "downstream signaling"
        )
    elif question_type == "mutation_impact":
        parts.append(
            "Show: wild-type protein on left, mutant on right, "
            "mutation site highlighted in red, functional consequences "
            "shown as diverging pathways below"
        )
    else:
        parts.append(
            "Show: protein domains as colored segments, key functional "
            "sites labeled, relevant pathway context"
        )

    user_msg = "\n".join(parts)

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=4096,
            system=_SVG_DIAGRAM_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                svg = block.text.strip()
                # Strip markdown fences if present
                if svg.startswith("```"):
                    svg = svg.split("\n", 1)[-1]
                    svg = svg.rsplit("```", 1)[0].strip()
                # Validate it's actual SVG
                if "<svg" in svg and "</svg>" in svg:
                    return svg
    except Exception:
        pass

    return None


# ---------------------------------------------------------------------------
# AI Figure Prompt Generator (uses Claude to create BioRender-ready prompts)
# ---------------------------------------------------------------------------

_FIGURE_PROMPT_SYSTEM = """You are a scientific illustration expert. Given a protein analysis,
generate a concise, specific text prompt that a researcher can paste directly into BioRender's
AI text-to-figure tool to create a publication-quality diagram.

The prompt should:
1. Describe the biological mechanism clearly and specifically
2. Name all entities (proteins, drugs, mutations, partners) with correct nomenclature
3. Specify the figure type (protocol, timeline, flowchart, pathway diagram)
4. Include spatial layout hints (left-to-right, top-to-bottom, etc.)
5. Be 3-6 sentences — enough detail to generate a useful figure, not so much it confuses the AI

Return ONLY the prompt text, no explanations or formatting."""


@st.cache_data(ttl=3600, show_spinner=False)
def generate_figure_prompt(
    protein_name: str,
    mutation: str | None,
    question_type: str,
    interaction_partner: str | None = None,
    interpretation: str | None = None,
) -> str | None:
    """Use Claude to generate a BioRender text-to-figure prompt.

    Returns a ready-to-paste prompt string, or None if generation fails.
    """
    if not ANTHROPIC_API_KEY:
        return _fallback_figure_prompt(protein_name, mutation, question_type, interaction_partner)

    parts = [f"Protein: {protein_name}"]
    if mutation:
        parts.append(f"Mutation: {mutation}")
    if interaction_partner:
        parts.append(f"Interaction partner: {interaction_partner}")
    parts.append(f"Question type: {question_type}")
    if interpretation:
        # Truncate to avoid blowing context
        parts.append(f"Analysis summary: {interpretation[:500]}")

    user_msg = "\n".join(parts)

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=300,
            system=_FIGURE_PROMPT_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        for block in response.content:
            if hasattr(block, "text") and block.text.strip():
                return block.text.strip()
    except Exception:
        pass

    return _fallback_figure_prompt(protein_name, mutation, question_type, interaction_partner)


def _fallback_figure_prompt(
    protein_name: str,
    mutation: str | None,
    question_type: str,
    interaction_partner: str | None,
) -> str:
    """Generate a reasonable figure prompt without Claude."""
    if question_type == "druggability":
        mut = f" {mutation} mutant" if mutation else ""
        return (
            f"Create a drug-target interaction pathway diagram showing {protein_name}{mut} "
            f"protein structure with its active binding site highlighted. "
            f"Show small molecule drug candidates approaching the binding pocket "
            f"with labeled arrows indicating inhibition or activation. "
            f"Include a side panel showing the drug discovery pipeline stages "
            f"from target identification to clinical trials."
        )
    if question_type == "binding":
        partner = interaction_partner or "binding partner"
        return (
            f"Create a protein-protein interaction diagram showing {protein_name} "
            f"binding to {partner}. Highlight the binding interface residues "
            f"with contact points labeled. Show the complex from two views: "
            f"the full assembly and a zoomed-in view of the interface. "
            f"Use arrows to indicate key hydrogen bonds and hydrophobic contacts."
        )
    if question_type == "mutation_impact" and mutation:
        return (
            f"Create a side-by-side comparison figure showing wild-type {protein_name} "
            f"versus the {mutation} mutant. Highlight the mutation site with a star marker. "
            f"Show structural changes at the mutation site with before/after insets. "
            f"Include a downstream pathway flowchart showing how this mutation "
            f"affects protein function and disease progression."
        )
    # Default: structure
    return (
        f"Create a protein domain architecture diagram for {protein_name}. "
        f"Show the primary structure as a horizontal bar with functional domains "
        f"color-coded and labeled. Below, show the 3D structure with key "
        f"structural features annotated: active sites, binding regions, and "
        f"post-translational modification sites."
    )


# ---------------------------------------------------------------------------
# Publication Figure Checklist Generator
# ---------------------------------------------------------------------------

def generate_figure_checklist(
    protein_name: str,
    mutation: str | None,
    question_type: str,
    confidence_score: float | None = None,
) -> list[dict]:
    """Generate a publication-ready figure checklist based on the analysis.

    Returns list of dicts with keys: item, category, required.
    """
    _i = "item"
    _c = "category"
    _r = "required"
    items = [
        {_i: "Scale bar or residue numbering on structure views",
         _c: "Accuracy", _r: True},
        {_i: "Colorblind-safe palette (avoid pure red/green)",
         _c: "Accessibility", _r: True},
        {_i: "Font size >= 8pt for all labels",
         _c: "Readability", _r: True},
        {_i: f"Protein name ({protein_name}) in figure title",
         _c: "Clarity", _r: True},
        {_i: "Resolution >= 300 DPI for publication",
         _c: "Technical", _r: True},
        {_i: "Color legend for all color-coded elements",
         _c: "Clarity", _r: True},
    ]

    if mutation:
        items.extend([
            {_i: f"Mutation {mutation} clearly labeled on structure",
             _c: "Accuracy", _r: True},
            {_i: "Wild-type vs mutant comparison if applicable",
             _c: "Completeness", _r: False},
        ])

    if confidence_score is not None:
        items.append({
            _i: f"Prediction confidence noted ({confidence_score:.0%})",
            _c: "Transparency", _r: True,
        })

    if question_type == "druggability":
        items.extend([
            {_i: "Drug binding site highlighted and labeled",
             _c: "Accuracy", _r: True},
            {_i: "IC50/Ki values cited if available",
             _c: "Completeness", _r: False},
        ])
    elif question_type == "binding":
        items.extend([
            {_i: "Interface residues labeled on both partners",
             _c: "Accuracy", _r: True},
            {_i: "Binding affinity (Kd) noted if known",
             _c: "Completeness", _r: False},
        ])

    items.extend([
        {_i: "Source data/PDB ID cited",
         _c: "Reproducibility", _r: True},
        {_i: "BioRender attribution (if using BioRender assets)",
         _c: "Licensing", _r: True},
    ])

    return items


# ---------------------------------------------------------------------------
# Template search (curated with real URLs)
# ---------------------------------------------------------------------------

SEARCH_SYSTEM = """You are a scientific illustration assistant integrated with BioRender.
Given a protein analysis query, use the BioRender MCP tools to search for relevant
templates and icons that would help researchers create publication-quality figures.

IMPORTANT INSTRUCTIONS:
1. Use the BioRender search tools to find REAL templates and icons.
2. Return URLs from the actual MCP tool results — do NOT fabricate URLs.
3. Match results to the specific analysis context (e.g., drug-target for druggability queries).
4. Prioritize templates that directly relate to the protein's biological function.

Return a JSON array of results, each with:
- "name": exact template or icon name from BioRender search results
- "type": "template" or "icon"
- "description": brief description of how it's relevant to this specific protein analysis
- "url": the URL returned by BioRender MCP (or null if not available)

Return at most 8 results. Rank by relevance to the specific protein and question."""


@st.cache_data(ttl=3600, show_spinner=False)
def search_biorender_templates(
    protein_name: str,
    mutation: str | None,
    question_type: str,
    trust_summary: str | None = None,
) -> list[dict]:
    """Search BioRender for relevant templates and icons.

    Tries MCP if token available, otherwise returns curated suggestions
    with real, verified BioRender URLs.
    """
    query = ProteinQuery(
        protein_name=protein_name,
        mutation=mutation,
        question_type=question_type,
    )

    if ANTHROPIC_API_KEY and BIORENDER_TOKEN:
        try:
            return _search_via_mcp(query, trust_summary)
        except Exception:
            pass

    return _curated_suggestions(query)


def search_biorender_for_sketch(
    sketch_interpretation: dict,
    query: ProteinQuery | None,
) -> list[dict]:
    """Search BioRender for templates matching a sketch interpretation."""
    title = sketch_interpretation.get("title", "")
    description = sketch_interpretation.get("description", "")
    elements = sketch_interpretation.get("elements", [])

    element_types = [el.get("type", "") for el in elements]
    element_labels = [el.get("label", "") for el in elements]

    protein_name = query.protein_name if query else "protein"
    mutation = query.mutation if query else None
    question_type = query.question_type if query else "structure"

    if any(t == "drug" for t in element_types):
        question_type = "druggability"
    elif any(
        "bind" in (el.get("type", "") or "")
        for el in sketch_interpretation.get("interactions", [])
    ):
        question_type = "binding"

    sketch_context = f"Sketch: {title}. {description}. Elements: {', '.join(element_labels[:5])}"

    return search_biorender_templates(
        protein_name=protein_name,
        mutation=mutation,
        question_type=question_type,
        trust_summary=sketch_context,
    )


def generate_biorender_figure(
    interpretation: dict,
    query: ProteinQuery | None,
) -> dict | None:
    """Use BioRender MCP to generate a figure from sketch interpretation.

    Returns dict with keys: figure_url, figure_description, or None if failed.
    """
    if not ANTHROPIC_API_KEY or not BIORENDER_TOKEN:
        return None

    import json as _json

    title = interpretation.get("title", "Biological mechanism")
    description = interpretation.get("description", "")
    elements = interpretation.get("elements", [])
    interactions = interpretation.get("interactions", [])

    protein_name = query.protein_name if query else "protein"
    mutation_ctx = f" (mutation {query.mutation})" if query and query.mutation else ""

    prompt_parts = [
        f"Create a pathway diagram for: {title}.",
        f"Context: {protein_name}{mutation_ctx}.",
    ]
    if description:
        prompt_parts.append(f"Description: {description}")

    if elements:
        entity_lines = []
        for el in elements:
            label = el.get("label", "unknown")
            etype = el.get("type", "entity")
            role = el.get("role", "")
            entity_lines.append(f"- {label} ({etype}){': ' + role if role else ''}")
        prompt_parts.append("Entities:\n" + "\n".join(entity_lines))

    if interactions:
        interaction_lines = []
        for ix in interactions:
            src = ix.get("from", "?")
            tgt = ix.get("to", "?")
            itype = ix.get("type", "interacts with")
            label = ix.get("label", "")
            interaction_lines.append(
                f"- {src} --[{itype}]--> {tgt}" + (f" ({label})" if label else "")
            )
        prompt_parts.append("Interactions:\n" + "\n".join(interaction_lines))

    prompt_parts.append(
        "Generate a clean, publication-quality pathway diagram showing these "
        "entities and their interactions. Use a clear layout with labeled arrows."
    )

    user_prompt = "\n\n".join(prompt_parts)

    try:
        client = Anthropic(api_key=ANTHROPIC_API_KEY)
        response = client.beta.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=2048,
            system=(
                "You are a scientific illustration assistant integrated with BioRender. "
                "Use BioRender's figure generation tool to create a pathway diagram. "
                "Return ONLY a JSON object: "
                '{"figure_url": "...", "figure_description": "..."}'
            ),
            messages=[{"role": "user", "content": user_prompt}],
            mcp_servers=[
                {
                    "type": "url",
                    "url": BIORENDER_MCP_URL,
                    "name": "biorender",
                    "authorization_token": BIORENDER_TOKEN,
                }
            ],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "biorender"}],
            betas=[MCP_BETA_HEADER],
        )

        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text = block.text
                break

        if not text:
            return None

        if "```" in text:
            text = (
                text.split("```json")[-1]
                if "```json" in text
                else text.split("```")[-2]
            )
            text = text.strip().rstrip("`")

        result = _json.loads(text)
        if isinstance(result, dict) and (
            result.get("figure_url") or result.get("figure_description")
        ):
            return result

    except Exception:
        pass

    return None


def _search_via_mcp(query: ProteinQuery, trust_summary: str | None = None) -> list[dict]:
    """Search BioRender using Anthropic's MCP connector."""
    import json

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    search_parts = [
        f"Search BioRender for templates and icons relevant to {query.protein_name}"
    ]
    if query.mutation:
        search_parts.append(f"with mutation {query.mutation}")

    figure_context = _QUESTION_FIGURE_CONTEXT.get(query.question_type, "")
    if figure_context:
        search_parts.append(f"I need: {figure_context}")
    if trust_summary:
        search_parts.append(f"Analysis context: {trust_summary}")

    search_query = ". ".join(search_parts)

    response = client.beta.messages.create(
        model=CLAUDE_FAST_MODEL,
        max_tokens=2048,
        system=SEARCH_SYSTEM,
        messages=[{"role": "user", "content": search_query}],
        mcp_servers=[
            {
                "type": "url",
                "url": BIORENDER_MCP_URL,
                "name": "biorender",
                "authorization_token": BIORENDER_TOKEN,
            }
        ],
        tools=[{"type": "mcp_toolset", "mcp_server_name": "biorender"}],
        betas=[MCP_BETA_HEADER],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    if not text:
        return _curated_suggestions(query)

    if "```" in text:
        text = text.split("```json")[-1] if "```json" in text else text.split("```")[-2]
        text = text.strip().rstrip("`")

    try:
        results = json.loads(text)
        if isinstance(results, list):
            for r in results:
                if not r.get("url"):
                    r["url"] = _best_url_for_result(r, query)
            return results[:8]
    except (json.JSONDecodeError, TypeError):
        pass

    return _curated_suggestions(query)


def _best_url_for_result(result: dict, query: ProteinQuery) -> str:
    """Find the best real URL for a BioRender result that lacks one."""
    name_lower = (result.get("name", "") or "").lower()
    result_type = result.get("type", "template")

    if result_type == "icon":
        search_term = name_lower.replace(" ", "+")
        return f"{_ICON_SEARCH}{search_term}"

    # Match to known real templates
    if "drug" in name_lower and "discover" in name_lower:
        return _TEMPLATE_URLS["drug_discovery"]
    if "drug" in name_lower or "pharmacol" in name_lower:
        return _TEMPLATE_URLS["drug_targeting"]
    if "mechanism" in name_lower or "action" in name_lower:
        return _TEMPLATE_URLS["mechanism_daptomycin"]
    if "mutation" in name_lower or "mutagen" in name_lower:
        return _TEMPLATE_URLS["mutagenesis"]
    if "interaction" in name_lower or "binding" in name_lower or "complex" in name_lower:
        return _TEMPLATE_URLS["protein_interaction"]
    if "pathway" in name_lower or "signal" in name_lower:
        return _TEMPLATE_URLS["mapk_pathway"]
    if "pipeline" in name_lower:
        return _TEMPLATE_URLS["drug_pipeline"]
    if "alignment" in name_lower or "sequence" in name_lower:
        return _TEMPLATE_URLS["msa"]

    # Fallback: search BioRender library
    return f"{_ICON_SEARCH}{name_lower.replace(' ', '+')}"


def _curated_suggestions(query: ProteinQuery) -> list[dict]:
    """Return curated BioRender template suggestions with real, verified URLs."""
    templates: list[dict] = [
        {
            "name": "Protein Structure",
            "type": "template",
            "description": f"3D protein structure template for presenting {query.protein_name}",
            "url": _TEMPLATE_URLS["protein_structure"],
        },
    ]

    if query.mutation:
        templates.extend([
            {
                "name": "Site-Directed Mutagenesis",
                "type": "template",
                "description": (
                    f"Show {query.mutation} mutation site and "
                    f"structural impact on {query.protein_name}"
                ),
                "url": _TEMPLATE_URLS["mutagenesis"],
            },
            {
                "name": "Mutation Icons",
                "type": "icon",
                "description": "Search mutation-related icons (stars, markers, annotations)",
                "url": f"{_ICON_SEARCH}mutation",
            },
        ])

    if query.question_type == "druggability":
        templates.extend([
            {
                "name": "Drug-Target Interaction",
                "type": "template",
                "description": (
                    f"Cytokine receptor drug targeting "
                    f"— adaptable for {query.protein_name}"
                ),
                "url": _TEMPLATE_URLS["drug_targeting"],
            },
            {
                "name": "Drug Discovery Pipeline",
                "type": "template",
                "description": "Development funnel from target ID to clinical trials",
                "url": _TEMPLATE_URLS["drug_discovery"],
            },
            {
                "name": "Mechanism of Action",
                "type": "template",
                "description": "Drug mechanism of action diagram template",
                "url": _TEMPLATE_URLS["mechanism_daptomycin"],
            },
            {
                "name": "Drug & Small Molecule Icons",
                "type": "icon",
                "description": "Pharmacology and small molecule icon library",
                "url": f"{_ICON_SEARCH}small+molecule+drug",
            },
        ])

    if query.question_type == "binding":
        templates.extend([
            {
                "name": "Protein-Protein Interaction Network",
                "type": "template",
                "description": f"PPI network diagram for {query.protein_name} interactions",
                "url": _TEMPLATE_URLS["protein_interaction"],
            },
            {
                "name": "Protein-Ligand Binding",
                "type": "template",
                "description": "Ligand binding and interaction interface template",
                "url": _TEMPLATE_URLS["protein_ligand"],
            },
            {
                "name": "Receptor & Ligand Icons",
                "type": "icon",
                "description": "Receptor, ligand, and binding partner icons",
                "url": _ICON_CATEGORIES["receptors"],
            },
        ])

    if query.question_type == "structure":
        templates.extend([
            {
                "name": "Multiple Sequence Alignment",
                "type": "template",
                "description": f"MSA visualization for {query.protein_name} conservation analysis",
                "url": _TEMPLATE_URLS["msa"],
            },
            {
                "name": "Protein Icons",
                "type": "icon",
                "description": "Full protein icon library — structures, domains, modifications",
                "url": _ICON_CATEGORIES["proteins"],
            },
        ])

    if query.question_type == "mutation_impact" and not query.mutation:
        templates.append({
            "name": "Virus Mutation Analysis",
            "type": "template",
            "description": "Mutation impact visualization template",
            "url": _TEMPLATE_URLS["virus_mutation"],
        })

    # Always include a pathway template
    templates.append({
        "name": "Signaling Pathway (MAPK)",
        "type": "template",
        "description": "Adaptable signaling pathway diagram — customize for your pathway",
        "url": _TEMPLATE_URLS["mapk_pathway"],
    })

    return templates
