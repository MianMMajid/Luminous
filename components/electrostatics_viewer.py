"""Electrostatic surface potential viewer.

Uses Tamarind Bio's PEP-Patch tool to compute per-residue electrostatic
potential, then overlays it on the 3D structure via molviewspec coloring.
"""
from __future__ import annotations

import re
import uuid

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.config import TAMARIND_API_KEY
from src.models import ProteinQuery
from src.utils import run_async

# ────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────


def render_electrostatics_panel(pdb_content: str, query: ProteinQuery):
    """Render the electrostatic surface potential panel.

    Parameters
    ----------
    pdb_content:
        PDB file content as a string.
    query:
        The current protein query.
    """
    st.markdown("#### Electrostatic Surface Potential")
    st.caption(
        "Per-residue electrostatic potential computed by Tamarind Bio's "
        "PEP-Patch tool. Red = negative charge, blue = positive charge, "
        "white = neutral."
    )

    if not TAMARIND_API_KEY:
        st.info(
            "Tamarind Bio API key required. "
            "Add `TAMARIND_API_KEY=your_key` to your `.env` file in the project root. "
            "Get a free key at [tamarind.bio](https://tamarind.bio).",
            icon="🔑",
        )
        return

    if not pdb_content:
        st.warning("No structure data available for electrostatic analysis.")
        return

    # Session state key for this protein
    state_key = f"electrostatics_data_{query.protein_name}"
    electrostatics_data = st.session_state.get(state_key)

    if electrostatics_data is None:
        # Show compute button
        st.markdown(
            "PEP-Patch computes the electrostatic potential at each solvent-"
            "accessible surface point and maps it back to residues. This "
            "reveals charged patches that drive binding, solubility, and "
            "druggability."
        )
        if st.button(
            "Compute Electrostatic Surface",
            type="primary",
            key=f"compute_electrostatics_{query.protein_name}",
        ):
            _run_peppatch(pdb_content, query, state_key)
        return

    # Results are available — render them
    _render_electrostatics_results(electrostatics_data, query)


# ────────────────────────────────────────────────────────
# Tamarind PEP-Patch submission
# ────────────────────────────────────────────────────────


def _run_peppatch(pdb_content: str, query: ProteinQuery, state_key: str):
    """Submit a PEP-Patch job to Tamarind and store results."""
    from src.tamarind_client import run_dynamic_tool

    job_name = f"luminous_peppatch_{query.protein_name}_{uuid.uuid4().hex[:6]}"

    with st.status(
        "Computing electrostatic surface via Tamarind PEP-Patch...",
        expanded=True,
    ) as status:
        try:
            st.write("Submitting PEP-Patch job...")

            async def _submit():
                return await run_dynamic_tool(
                    tool_type="peppatch",
                    settings={"structure": pdb_content},
                    job_name=job_name,
                    timeout=300,
                )

            result = run_async(_submit())

            # Parse the PEP-Patch results
            parsed = _parse_peppatch_result(result)
            st.session_state[state_key] = parsed
            status.update(label="Electrostatic surface computed!", state="complete")

        except Exception as e:
            status.update(label="PEP-Patch computation failed", state="error")
            st.error(f"Tamarind PEP-Patch error: {e}")


@st.cache_data(show_spinner=False)
def _parse_peppatch_result(result: dict) -> dict:
    """Parse PEP-Patch output into a structured dict.

    PEP-Patch returns per-residue electrostatic potential values.
    We normalise and extract:
    - residue_ids: list[int]
    - potentials: list[float] (in kT/e or mV, depending on version)
    - charges: list[str] ("positive", "negative", "neutral")
    - patches: list of charged patch clusters
    """
    # PEP-Patch output format varies — handle multiple schemas
    potentials_raw = (
        result.get("potentials")
        or result.get("residue_potentials")
        or result.get("per_residue_potential")
        or result.get("results", {}).get("potentials")
        or []
    )

    # If raw result has a different structure, try to extract
    if not potentials_raw and isinstance(result, dict):
        # Try nested results key
        for key in ("output", "data", "peppatch"):
            nested = result.get(key)
            if isinstance(nested, dict):
                potentials_raw = (
                    nested.get("potentials")
                    or nested.get("residue_potentials")
                    or []
                )
                if potentials_raw:
                    break
            elif isinstance(nested, list):
                potentials_raw = nested
                break

    # Parse into structured data
    residue_ids: list[int] = []
    potentials: list[float] = []

    if isinstance(potentials_raw, list):
        for entry in potentials_raw:
            if isinstance(entry, dict):
                res_id = entry.get("residue_id", entry.get("resid", entry.get("position")))
                pot = entry.get("potential", entry.get("value", entry.get("charge")))
                if res_id is not None and pot is not None:
                    try:
                        residue_ids.append(int(res_id))
                        potentials.append(float(pot))
                    except (ValueError, TypeError):
                        continue
            elif isinstance(entry, (int, float)):
                residue_ids.append(len(residue_ids) + 1)
                potentials.append(float(entry))

    # If we still have no data, create a synthetic demonstration
    # (the API schema may have changed — fail gracefully)
    if not potentials:
        return {
            "residue_ids": [],
            "potentials": [],
            "charges": [],
            "patches": [],
            "summary": {},
            "raw": result,
        }

    pot_arr = np.array(potentials, dtype=np.float64)

    # Classify each residue
    threshold = 1.0  # kT/e threshold for charge classification
    charges = []
    for p in potentials:
        if p > threshold:
            charges.append("positive")
        elif p < -threshold:
            charges.append("negative")
        else:
            charges.append("neutral")

    # Detect charged patches (clusters of 3+ same-sign consecutive residues)
    patches = _detect_charged_patches(residue_ids, charges, potentials)

    # Summary statistics
    n_pos = charges.count("positive")
    n_neg = charges.count("negative")
    n_neut = charges.count("neutral")
    total = len(charges) or 1

    summary = {
        "pct_positive": n_pos / total,
        "pct_negative": n_neg / total,
        "pct_neutral": n_neut / total,
        "mean_potential": float(np.mean(pot_arr)),
        "std_potential": float(np.std(pot_arr)),
        "min_potential": float(np.min(pot_arr)),
        "max_potential": float(np.max(pot_arr)),
        "n_residues": total,
    }

    return {
        "residue_ids": residue_ids,
        "potentials": potentials,
        "charges": charges,
        "patches": patches,
        "summary": summary,
        "raw": result,
    }


def _detect_charged_patches(
    residue_ids: list[int],
    charges: list[str],
    potentials: list[float],
    min_size: int = 3,
) -> list[dict]:
    """Find clusters of consecutive same-sign charged residues.

    A "patch" is min_size or more consecutive residues with the same
    charge sign. Returns a list of patch dicts.
    """
    patches: list[dict] = []
    if not charges:
        return patches

    current_sign = charges[0]
    current_start = 0

    for i in range(1, len(charges)):
        is_last = i == len(charges) - 1
        sign_changed = charges[i] != current_sign

        if sign_changed or is_last:
            # End of current patch: include last element if sign matches
            end = i if sign_changed else i + 1
            length = end - current_start

            if length >= min_size and current_sign != "neutral":
                patch_pots = potentials[current_start:end]
                patches.append({
                    "type": current_sign,
                    "start_residue": residue_ids[current_start],
                    "end_residue": residue_ids[min(end - 1, len(residue_ids) - 1)],
                    "size": length,
                    "mean_potential": float(np.mean(patch_pots)),
                    "max_abs_potential": float(np.max(np.abs(patch_pots))),
                })

            # If sign changed, also flush a final single-element patch on last iteration
            if sign_changed and is_last:
                # The last element starts a new "patch" of size 1
                # Only emit if it meets min_size (unlikely for size=1)
                if 1 >= min_size and charges[i] != "neutral":
                    patches.append({
                        "type": charges[i],
                        "start_residue": residue_ids[i],
                        "end_residue": residue_ids[i],
                        "size": 1,
                        "mean_potential": float(potentials[i]),
                        "max_abs_potential": float(abs(potentials[i])),
                    })

            current_sign = charges[i]
            current_start = i

    return patches


# ────────────────────────────────────────────────────────
# Results rendering
# ────────────────────────────────────────────────────────


def _render_electrostatics_results(data: dict, query: ProteinQuery):
    """Render the electrostatics analysis results."""
    residue_ids = data.get("residue_ids", [])
    potentials = data.get("potentials", [])
    patches = data.get("patches", [])
    summary = data.get("summary", {})

    if not residue_ids:
        st.warning(
            "PEP-Patch returned results but no per-residue potentials could "
            "be extracted. The raw output is shown below for inspection."
        )
        raw = data.get("raw", {})
        if raw:
            with st.expander("Raw PEP-Patch Output"):
                st.json(raw)
        return

    # ── 1. Summary metrics ──────────────────────────────
    mcols = st.columns(4)
    mcols[0].metric(
        "Positive Surface",
        f"{summary.get('pct_positive', 0):.0%}",
        help="Fraction of residues with positive electrostatic potential",
    )
    mcols[1].metric(
        "Negative Surface",
        f"{summary.get('pct_negative', 0):.0%}",
        help="Fraction of residues with negative electrostatic potential",
    )
    mcols[2].metric(
        "Neutral Surface",
        f"{summary.get('pct_neutral', 0):.0%}",
        help="Fraction of residues with near-zero potential",
    )
    mcols[3].metric(
        "Charged Patches",
        str(len(patches)),
        help="Clusters of 3+ consecutive same-sign charged residues",
    )

    # ── 2. Strip chart ──────────────────────────────────
    fig = _build_strip_chart(residue_ids, potentials, query)
    st.plotly_chart(fig, use_container_width=True)

    # ── 3. Charged patches ──────────────────────────────
    if patches:
        st.markdown("##### Charged Patches")
        st.caption(
            "Clusters of consecutive same-sign charged residues. These patches "
            "often correspond to protein-protein interaction interfaces, "
            "membrane-binding regions, or allosteric sites."
        )

        pos_patches = [p for p in patches if p["type"] == "positive"]
        neg_patches = [p for p in patches if p["type"] == "negative"]

        if pos_patches:
            st.markdown(
                f"**{len(pos_patches)} positive patch{'es' if len(pos_patches) != 1 else ''}**"
            )
            for p in sorted(pos_patches, key=lambda x: -x["size"])[:5]:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0">'
                    f'<div style="width:12px;height:12px;background:#4A90D9;'
                    f'border-radius:2px"></div>'
                    f'<span style="font-size:0.88em">'
                    f'Residues {p["start_residue"]}-{p["end_residue"]} '
                    f'({p["size"]} res, mean {p["mean_potential"]:+.2f} kT/e)'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )

        if neg_patches:
            st.markdown(
                f"**{len(neg_patches)} negative patch{'es' if len(neg_patches) != 1 else ''}**"
            )
            for p in sorted(neg_patches, key=lambda x: -x["size"])[:5]:
                st.markdown(
                    f'<div style="display:flex;align-items:center;gap:8px;margin:2px 0">'
                    f'<div style="width:12px;height:12px;background:#D94A4A;'
                    f'border-radius:2px"></div>'
                    f'<span style="font-size:0.88em">'
                    f'Residues {p["start_residue"]}-{p["end_residue"]} '
                    f'({p["size"]} res, mean {p["mean_potential"]:+.2f} kT/e)'
                    f'</span></div>',
                    unsafe_allow_html=True,
                )

    # ── 4. Druggability note ────────────────────────────
    _render_druggability_note(summary, patches, query)

    # ── 5. Raw output expander ──────────────────────────
    raw = data.get("raw", {})
    if raw:
        with st.expander("Raw PEP-Patch Output"):
            st.json(raw)

    # Provenance
    st.caption("Computed via Tamarind Bio PEP-Patch | Electrostatic potential in kT/e")


# ────────────────────────────────────────────────────────
# Strip chart builder (cached)
# ────────────────────────────────────────────────────────


@st.cache_data(show_spinner=False)
def _build_strip_chart(
    residue_ids: list[int],
    potentials: list[float],
    query: ProteinQuery,
) -> go.Figure:
    """Build a 1D strip chart of per-residue electrostatic potential.

    Uses a diverging RdBu colorscale: red = negative, white = neutral,
    blue = positive.
    """
    pot_arr = np.array(potentials, dtype=np.float64)
    abs_max = max(abs(float(pot_arr.min())), abs(float(pot_arr.max())), 1.0)

    # Build bar colors using RdBu-like mapping
    colors = []
    for p in potentials:
        norm = p / abs_max  # -1 to +1
        if norm > 0:
            # Positive: white to blue
            r = int(255 * (1 - norm))
            g = int(255 * (1 - norm * 0.6))
            b = 255
        else:
            # Negative: white to red
            r = 255
            g = int(255 * (1 + norm * 0.6))
            b = int(255 * (1 + norm))
        colors.append(f"rgb({r},{g},{b})")

    fig = go.Figure()

    # Main bar trace
    fig.add_trace(
        go.Bar(
            x=residue_ids,
            y=potentials,
            marker=dict(color=colors, line=dict(width=0)),
            hovertemplate=(
                "Residue %{x}<br>"
                "Potential: %{y:+.2f} kT/e<extra></extra>"
            ),
            name="Electrostatic Potential",
        )
    )

    # Zero line
    fig.add_hline(
        y=0,
        line=dict(color="rgba(60,60,67,0.4)", width=1),
    )

    # Mark mutation position
    mut_pos: int | None = None
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))

    annotations = []
    shapes = []
    if mut_pos is not None and mut_pos in residue_ids:
        shapes.append(
            dict(
                type="line",
                x0=mut_pos,
                x1=mut_pos,
                y0=-abs_max * 1.1,
                y1=abs_max * 1.1,
                line=dict(color="#FFCC00", width=2, dash="dash"),
            )
        )
        annotations.append(
            dict(
                x=mut_pos,
                y=abs_max * 1.05,
                text=f"{query.mutation}",
                showarrow=False,
                font=dict(color="#FFCC00", size=11),
            )
        )

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=280,
        margin=dict(t=20, b=50, l=60, r=30),
        xaxis=dict(
            title="Residue Number",
            gridcolor="rgba(0,0,0,0.08)",
        ),
        yaxis=dict(
            title="Electrostatic Potential (kT/e)",
            gridcolor="rgba(0,0,0,0.08)",
            zeroline=False,
        ),
        bargap=0,
        showlegend=False,
        shapes=shapes,
        annotations=annotations,
    )

    return fig


# ────────────────────────────────────────────────────────
# Druggability interpretation
# ────────────────────────────────────────────────────────


def _render_druggability_note(
    summary: dict,
    patches: list[dict],
    query: ProteinQuery,
):
    """Show a note relating electrostatics to binding and druggability."""
    st.markdown("##### Implications for Binding & Druggability")

    notes: list[str] = []

    pct_neg = summary.get("pct_negative", 0)
    pct_pos = summary.get("pct_positive", 0)
    pct_neut = summary.get("pct_neutral", 0)

    # Overall surface character
    if pct_neg > 0.4:
        notes.append(
            "The surface is predominantly **negatively charged**. This may "
            "favour binding of cationic ligands, positively charged peptides, "
            "or metal ions (e.g. Zn2+, Ca2+)."
        )
    elif pct_pos > 0.4:
        notes.append(
            "The surface is predominantly **positively charged**. This is "
            "common in DNA/RNA-binding proteins and may favour anionic ligand "
            "binding or nucleotide interactions."
        )
    elif pct_neut > 0.5:
        notes.append(
            "The surface is largely **neutral/hydrophobic**. This is typical "
            "of well-folded globular proteins and may indicate good small-"
            "molecule druggability at hydrophobic pockets."
        )
    else:
        notes.append(
            "The surface has a **mixed charge distribution**, which is "
            "common in multi-domain or multi-function proteins."
        )

    # Patch insights
    large_patches = [p for p in patches if p["size"] >= 5]
    if large_patches:
        n_pos = sum(1 for p in large_patches if p["type"] == "positive")
        n_neg = sum(1 for p in large_patches if p["type"] == "negative")
        notes.append(
            f"Found **{len(large_patches)} large charged patch"
            f"{'es' if len(large_patches) != 1 else ''}** "
            f"({n_pos} positive, {n_neg} negative) with 5+ residues. "
            "Large charged patches are often protein-protein interaction "
            "hotspots or allosteric regulatory sites."
        )

    # Mutation context
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            in_patch = False
            for p in patches:
                if p["start_residue"] <= mut_pos <= p["end_residue"]:
                    notes.append(
                        f"Mutation **{query.mutation}** falls within a "
                        f"**{p['type']} charged patch** (residues "
                        f"{p['start_residue']}-{p['end_residue']}). "
                        "Mutations in charged patches can disrupt binding "
                        "interfaces or alter substrate specificity."
                    )
                    in_patch = True
                    break
            if not in_patch:
                notes.append(
                    f"Mutation **{query.mutation}** is not located within a "
                    "major charged patch. Its electrostatic effect may be local "
                    "rather than disrupting a binding interface."
                )

    for note in notes:
        st.markdown(note)
