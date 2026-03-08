"""Reusable empty-state placeholder for tabs that need a loaded query."""
from __future__ import annotations

import streamlit as st

# (icon, title, description, hint)
_TAB_EMPTY = {
    "structure": (
        "Structure",
        "Predict and visualize the 3D structure of any protein with "
        "per-residue confidence coloring, trust audit, and binding pocket detection.",
    ),
    "biology": (
        "Biology",
        "Explore disease associations, drug interactions, variant landscapes, "
        "and AI-generated hypotheses from PubMed, UniProt, and ClinVar.",
    ),
    "report": (
        "Report",
        "Generate publication-ready figures, PDF reports, and data exports "
        "once your analysis is complete.",
    ),
    "workspace": (
        "Workspace",
        "Pin insights from other tabs, compare results side-by-side, "
        "and plan follow-up experiments.",
    ),
    "sketch": (
        "Sketch",
        "Draw a biological mechanism on the canvas and let Lumi "
        "interpret it into a structured pathway diagram.",
    ),
}

# Small inline SVG of the static DNA character (no animation, lightweight)
_MINI_DNA_SVG = (
    '<svg viewBox="0 0 36 56" width="44" height="64" '
    'style="opacity:0.55;margin-bottom:4px" xmlns="http://www.w3.org/2000/svg">'
    '<line stroke="rgba(0,0,0,0.08)" stroke-width="1.6" stroke-linecap="round" '
    'x1="8" y1="18" x2="28" y2="18"/>'
    '<line stroke="rgba(0,0,0,0.08)" stroke-width="1.6" stroke-linecap="round" '
    'x1="13" y1="24" x2="23" y2="24"/>'
    '<line stroke="rgba(0,0,0,0.08)" stroke-width="1.6" stroke-linecap="round" '
    'x1="8" y1="30" x2="28" y2="30"/>'
    '<path stroke="#007AFF" fill="none" stroke-width="2.4" stroke-linecap="round" '
    'd="M8,15 C8,19 28,21 28,25 C28,29 8,31 8,35 C8,39 28,41 28,45"/>'
    '<path stroke="#34C759" fill="none" stroke-width="2.4" stroke-linecap="round" '
    'd="M28,15 C28,19 8,21 8,25 C8,29 28,31 28,35 C28,39 8,41 8,45"/>'
    '<circle cx="8" cy="18" r="1.8" fill="#007AFF"/>'
    '<circle cx="28" cy="18" r="1.8" fill="#34C759"/>'
    '<circle cx="28" cy="30" r="1.8" fill="#007AFF"/>'
    '<circle cx="8" cy="30" r="1.8" fill="#34C759"/>'
    '<circle fill="#fff" stroke="rgba(0,0,0,0.12)" stroke-width="0.4" cx="12" cy="9" r="4.5"/>'
    '<circle fill="#1a1a1a" cx="12" cy="9.2" r="2.2"/>'
    '<circle fill="#fff" stroke="rgba(0,0,0,0.12)" stroke-width="0.4" cx="24" cy="9" r="4.5"/>'
    '<circle fill="#1a1a1a" cx="24" cy="9.2" r="2.2"/>'
    '<circle cx="10.5" cy="7.5" r="0.9" fill="white" opacity="0.85"/>'
    '<circle cx="22.5" cy="7.5" r="0.9" fill="white" opacity="0.85"/>'
    '</svg>'
)


def render_empty_state(tab_key: str) -> None:
    """Render a professional empty-state placeholder for a tab.

    Parameters
    ----------
    tab_key:
        One of "structure", "biology", "report", "workspace", "sketch".
    """
    title, desc = _TAB_EMPTY.get(tab_key, ("Analysis", "Load a protein to get started."))

    st.markdown(
        '<div class="lumi-empty-state">'
        f'{_MINI_DNA_SVG}'
        f'<p class="empty-title">{title}</p>'
        f'<p class="empty-desc">{desc}</p>'
        '<div class="empty-hint">'
        'Go to <b>Search</b> and enter a protein name to begin'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
