"""Bioicons.com integration — free MIT/CC0 SVG scientific icons.

Provides curated icon snippets for embedding in Claude-generated SVG diagrams.
Icons are fetched from the bioicons GitHub repo and cached.
"""
from __future__ import annotations

import httpx
import streamlit as st

# Curated bioicon raw GitHub URLs (MIT / CC0 / CC-BY licensed)
_BASE = "https://raw.githubusercontent.com/duerrsimon/bioicons/main/static/icons"

BIOICON_URLS: dict[str, str] = {
    # Proteins
    "protein_generic": f"{_BASE}/cc-0/Servier/proteins/protein.svg",
    "protein_complex": f"{_BASE}/cc-0/Servier/proteins/protein_complex.svg",
    "receptor": f"{_BASE}/cc-0/Servier/proteins/receptor.svg",
    "enzyme": f"{_BASE}/cc-0/Servier/proteins/enzyme.svg",
    "antibody": f"{_BASE}/cc-0/Servier/proteins/antibody.svg",
    # Drugs / Chemistry
    "drug_molecule": f"{_BASE}/cc-0/Servier/chemistry/molecule.svg",
    "pill": f"{_BASE}/cc-0/Servier/chemistry/pill.svg",
    # Nucleic acids
    "dna": f"{_BASE}/cc-0/Servier/nucleic_acids/dna.svg",
    "rna": f"{_BASE}/cc-0/Servier/nucleic_acids/rna.svg",
    # Cell structures
    "cell": f"{_BASE}/cc-0/Servier/cell_types/cell.svg",
    "membrane": f"{_BASE}/cc-0/Servier/cell_parts/cell_membrane.svg",
    "nucleus": f"{_BASE}/cc-0/Servier/cell_parts/nucleus.svg",
    # Signaling
    "kinase": f"{_BASE}/cc-0/Servier/proteins/kinase.svg",
    "phosphorylation": f"{_BASE}/cc-0/Servier/post_translational_modifications/phosphorylation.svg",
}

# Fallback: simplified SVG shapes for icons that fail to load
_FALLBACK_SHAPES: dict[str, str] = {
    "protein_generic": (
        '<ellipse rx="18" ry="12" fill="#4A90D9" opacity="0.85"/>'
        '<text y="4" text-anchor="middle" fill="white" font-size="8" '
        'font-family="Arial">P</text>'
    ),
    "drug_molecule": (
        '<circle r="10" fill="#50C878" opacity="0.85"/>'
        '<text y="4" text-anchor="middle" fill="white" font-size="9" '
        'font-family="Arial">D</text>'
    ),
    "receptor": (
        '<rect x="-12" y="-16" width="24" height="32" rx="4" '
        'fill="#7B68EE" opacity="0.85"/>'
        '<text y="4" text-anchor="middle" fill="white" font-size="8" '
        'font-family="Arial">R</text>'
    ),
    "dna": (
        '<rect x="-6" y="-14" width="12" height="28" rx="3" '
        'fill="#F5A623" opacity="0.85"/>'
        '<text y="4" text-anchor="middle" fill="white" font-size="8" '
        'font-family="Arial">DNA</text>'
    ),
}


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_bioicon_svg(icon_key: str) -> str | None:
    """Fetch a bioicon SVG and extract inner content (no outer <svg> wrapper).

    Returns the SVG inner markup suitable for embedding in a <g> element,
    or None if fetch fails.
    """
    url = BIOICON_URLS.get(icon_key)
    if not url:
        return _FALLBACK_SHAPES.get(icon_key)

    try:
        resp = httpx.get(url, timeout=10.0, follow_redirects=True)
        resp.raise_for_status()
        svg_text = resp.text.strip()

        # Strip outer <svg ...> and </svg> to get just the inner content
        import re
        inner = re.sub(r"<\?xml[^>]*\?>", "", svg_text).strip()
        inner = re.sub(r"<svg[^>]*>", "", inner, count=1).strip()
        inner = re.sub(r"</svg>\s*$", "", inner).strip()
        return inner
    except Exception:
        return _FALLBACK_SHAPES.get(icon_key)


def get_bioicon_snippet(
    icon_key: str,
    x: float,
    y: float,
    scale: float = 0.15,
) -> str:
    """Get a positioned SVG snippet for embedding in a larger diagram.

    Returns a <g> element with translate + scale transform.
    """
    inner = fetch_bioicon_svg(icon_key)
    if not inner:
        inner = _FALLBACK_SHAPES.get(
            icon_key,
            '<circle r="8" fill="#999"/>',
        )
    return (
        f'<g transform="translate({x},{y}) scale({scale})">'
        f"{inner}</g>"
    )


def get_icon_catalog_for_prompt() -> str:
    """Return a compact text catalog of available icons for inclusion in Claude prompts.

    Instead of embedding full SVG paths (too many tokens), we tell Claude
    which icons are available and let it use placeholder comments.
    """
    lines = ["Available scientific icons (use <!-- BIOICON:key x y scale --> placeholder):"]
    for key in BIOICON_URLS:
        lines.append(f"  - {key}")
    return "\n".join(lines)


def postprocess_svg_with_icons(svg_content: str) -> str:
    """Replace <!-- BIOICON:key x y scale --> placeholders with actual icon SVGs."""
    import re

    pattern = r"<!--\s*BIOICON:(\w+)\s+([\d.]+)\s+([\d.]+)\s*([\d.]*)\s*-->"

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        x = float(match.group(2))
        y = float(match.group(3))
        scale = float(match.group(4)) if match.group(4) else 0.15
        return get_bioicon_snippet(key, x, y, scale)

    return re.sub(pattern, replacer, svg_content)
