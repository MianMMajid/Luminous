from __future__ import annotations

import streamlit as st

from src.models import PredictionResult, ProteinQuery, TrustAudit
from src.utils import trust_to_color, trust_to_label


def render_sequence_viewer(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render an interactive amino acid sequence viewer with pLDDT coloring."""
    if not prediction.plddt_per_residue or not prediction.residue_ids:
        return

    st.markdown("#### Sequence Confidence Map")

    # Extract single-letter amino acid codes from PDB if available
    aa_codes = _extract_aa_from_pdb(prediction.pdb_content)

    # Build the color-coded sequence HTML
    html = _build_sequence_html(
        query,
        prediction.residue_ids,
        prediction.plddt_per_residue,
        prediction.chain_ids,
        aa_codes,
    )
    st.markdown(html, unsafe_allow_html=True)

    # Statistics summary
    _render_confidence_stats(prediction.plddt_per_residue, query)


def _extract_aa_from_pdb(pdb_content: str) -> dict[tuple[str, int], str]:
    """Extract amino acid single-letter codes from PDB ATOM records."""
    three_to_one = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    }
    aa_map: dict[tuple[str, int], str] = {}
    seen = set()
    for line in pdb_content.splitlines():
        if not line.startswith(("ATOM  ", "HETATM")):
            continue
        atom_name = line[12:16].strip()
        if atom_name != "CA":
            continue
        res_name = line[17:20].strip()
        chain = line[21]
        try:
            res_id = int(line[22:26].strip())
        except ValueError:
            continue
        key = (chain, res_id)
        if key not in seen:
            seen.add(key)
            aa_map[key] = three_to_one.get(res_name, "X")
    return aa_map


def _build_sequence_html(
    query: ProteinQuery,
    residue_ids: list[int],
    plddt_scores: list[float],
    chain_ids: list[str],
    aa_codes: dict[tuple[str, int], str],
) -> str:
    """Build HTML for the sequence viewer with per-residue coloring."""
    # Find mutation position
    mut_pos = None
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))

    spans = []
    for i, (res_id, score, chain) in enumerate(
        zip(residue_ids, plddt_scores, chain_ids)
    ):
        aa = aa_codes.get((chain, res_id), "?")
        color = trust_to_color(score)
        label = trust_to_label(score)

        # Mutation site gets a special border
        border = ""
        extra_title = ""
        if mut_pos is not None and res_id == mut_pos:
            border = "border: 2px solid #FF3B30; border-radius: 3px;"
            extra_title = f" | MUTATION SITE ({query.mutation})"

        # Number markers every 10 residues
        number_marker = ""
        if res_id % 10 == 0:
            number_marker = (
                f'<span style="position:absolute;top:-14px;left:50%;'
                f'transform:translateX(-50%);font-size:9px;color:#636366;">'
                f"{res_id}</span>"
            )

        spans.append(
            f'<span style="position:relative;display:inline-block;'
            f"background:{color};color:#000;padding:1px 2px;"
            f"margin:0.5px;font-family:'Geist Mono','SF Mono',monospace;font-size:12px;"
            f'font-weight:bold;cursor:pointer;{border}"'
            f' title="Res {res_id} ({aa}): pLDDT {score:.1f} ({label}){extra_title}">'
            f"{number_marker}{aa}</span>"
        )

    # Wrap in a scrollable container that handles long sequences
    # without dual scrollbars — vertical wraps, horizontal scrolls only if needed
    n_residues = len(residue_ids)
    # Dynamic max-height: short sequences don't need scroll, long ones do
    max_h = "none" if n_residues < 200 else "240px"
    html = (
        f'<div class="lumi-seq-scroll" style="line-height:28px;padding:8px 10px;'
        f"background:#F2F2F7;border-radius:8px;border:1px solid rgba(0,0,0,0.12);"
        f'max-height:{max_h};overflow-y:auto;overflow-x:auto;'
        f'-webkit-overflow-scrolling:touch;">'
        + "".join(spans)
        + "</div>"
    )
    return html


def _render_confidence_stats(plddt_scores: list[float], query: ProteinQuery):
    """Show confidence distribution statistics."""
    total = len(plddt_scores)
    if total == 0:
        return

    very_high = sum(1 for s in plddt_scores if s >= 90)
    high = sum(1 for s in plddt_scores if 70 <= s < 90)
    low = sum(1 for s in plddt_scores if 50 <= s < 70)
    very_low = sum(1 for s in plddt_scores if s < 50)
    avg = sum(plddt_scores) / total

    cols = st.columns(5)
    cols[0].metric("Avg pLDDT", f"{avg:.1f}")
    cols[1].metric("Very High (>90)", f"{very_high}/{total}", delta=f"{very_high/total:.0%}")
    cols[2].metric("High (70-90)", f"{high}/{total}")
    cols[3].metric("Low (50-70)", f"{low}/{total}")
    cols[4].metric("Very Low (<50)", f"{very_low}/{total}",
                   delta=f"-{very_low/total:.0%}" if very_low > 0 else "0%",
                   delta_color="inverse")
