from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.models import PredictionResult, ProteinQuery


def render_alphafold_comparison(query: ProteinQuery, prediction: PredictionResult):
    """Compare Boltz-2 prediction against AlphaFold DB entry."""
    if not query.uniprot_id:
        return

    st.markdown("#### Boltz-2 vs AlphaFold Comparison")

    # Check session cache first
    cache_key = f"alphafold_{query.uniprot_id}"
    af_data = st.session_state.get(cache_key)

    if af_data is None:
        if st.button("Fetch AlphaFold Prediction", key="af_fetch"):
            af_data = _fetch_alphafold(query.uniprot_id)
            st.session_state[cache_key] = af_data if af_data else "not_found"
        else:
            st.caption(
                f"Click to fetch AlphaFold's prediction for {query.uniprot_id} "
                "and compare per-residue confidence with Boltz-2."
            )
            return

    if af_data == "not_found":
        st.info(f"No AlphaFold prediction found for {query.uniprot_id}.")
        return

    # Display comparison
    _render_comparison_chart(prediction, af_data)
    _render_comparison_summary(prediction, af_data)


def _fetch_alphafold(uniprot_id: str) -> dict | None:
    """Fetch AlphaFold prediction and pLDDT scores from AlphaFold DB."""
    import httpx

    try:
        # Fetch PDB from AlphaFold DB
        pdb_url = f"https://alphafold.ebi.ac.uk/files/AF-{uniprot_id}-F1-model_v4.pdb"
        resp = httpx.get(pdb_url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return None

        pdb_content = resp.text

        # Parse pLDDT from AlphaFold PDB B-factor column
        from src.utils import parse_pdb_plddt

        chain_ids, residue_ids, plddt_scores = parse_pdb_plddt(pdb_content)

        return {
            "pdb_content": pdb_content,
            "chain_ids": chain_ids,
            "residue_ids": residue_ids,
            "plddt_scores": plddt_scores,
        }
    except Exception as e:
        st.warning(f"Failed to fetch AlphaFold data: {e}")
        return None


def _render_comparison_chart(prediction: PredictionResult, af_data: dict):
    """Overlay Boltz-2 and AlphaFold pLDDT profiles."""
    boltz_res = prediction.residue_ids
    boltz_plddt = prediction.plddt_per_residue
    af_res = af_data.get("residue_ids", [])
    af_plddt = af_data.get("plddt_scores", [])

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=boltz_res,
        y=boltz_plddt,
        mode="lines",
        name="Boltz-2 (Tamarind Bio)",
        line=dict(color="#007AFF", width=2),
        hovertemplate="Res %{x}<br>Boltz-2 pLDDT: %{y:.1f}<extra></extra>",
    ))

    fig.add_trace(go.Scatter(
        x=af_res,
        y=af_plddt,
        mode="lines",
        name="AlphaFold",
        line=dict(color="#34D399", width=2, dash="dot"),
        hovertemplate="Res %{x}<br>AlphaFold pLDDT: %{y:.1f}<extra></extra>",
    ))

    # Threshold lines
    for threshold, color, label in [
        (90, "#0053D6", "Very High"),
        (70, "#65CBF3", "High"),
        (50, "#FFDB13", "Low"),
    ]:
        fig.add_hline(
            y=threshold, line_dash="dash", line_color=color,
            annotation_text=label, annotation_position="right",
        )

    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 100],
        template="plotly_white",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin=dict(t=30, b=50, l=50, r=80),
        legend=dict(yanchor="bottom", y=0.02, xanchor="left", x=0.02),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_comparison_summary(prediction: PredictionResult, af_data: dict):
    """Show summary statistics comparing the two predictions."""
    boltz_plddt = prediction.plddt_per_residue
    af_plddt = af_data["plddt_scores"]

    boltz_avg = sum(boltz_plddt) / max(len(boltz_plddt), 1)
    af_avg = sum(af_plddt) / max(len(af_plddt), 1)

    boltz_high = sum(1 for s in boltz_plddt if s >= 70) / max(len(boltz_plddt), 1)
    af_high = sum(1 for s in af_plddt if s >= 70) / max(len(af_plddt), 1)

    cols = st.columns(4)
    cols[0].metric("Boltz-2 Avg pLDDT", f"{boltz_avg:.1f}")
    cols[1].metric("AlphaFold Avg pLDDT", f"{af_avg:.1f}")
    cols[2].metric(
        "Boltz-2 High Conf %",
        f"{boltz_high:.0%}",
    )
    cols[3].metric(
        "AlphaFold High Conf %",
        f"{af_high:.0%}",
    )

    # Find regions where they disagree
    _find_disagreements(prediction, af_data)


def _find_disagreements(prediction: PredictionResult, af_data: dict):
    """Identify residues where Boltz-2 and AlphaFold significantly disagree."""
    boltz_map = dict(zip(prediction.residue_ids, prediction.plddt_per_residue))
    af_map = dict(zip(af_data["residue_ids"], af_data["plddt_scores"]))

    shared_residues = set(boltz_map.keys()) & set(af_map.keys())
    if not shared_residues:
        st.info("No overlapping residues found for comparison.")
        return

    disagreements = []
    for res in sorted(shared_residues):
        diff = abs(boltz_map[res] - af_map[res])
        if diff > 20:
            disagreements.append({
                "residue": res,
                "boltz": boltz_map[res],
                "alphafold": af_map[res],
                "diff": diff,
            })

    if disagreements:
        with st.expander(f"Significant Disagreements ({len(disagreements)} residues)"):
            st.caption(
                "Residues where Boltz-2 and AlphaFold pLDDT differ by >20 points. "
                "These regions warrant extra scrutiny and experimental validation."
            )
            for d in disagreements[:10]:
                higher = "Boltz-2" if d["boltz"] > d["alphafold"] else "AlphaFold"
                st.markdown(
                    f"- **Residue {d['residue']}**: Boltz-2 = {d['boltz']:.1f}, "
                    f"AlphaFold = {d['alphafold']:.1f} ({higher} more confident)"
                )
    else:
        st.success(
            "Boltz-2 and AlphaFold agree closely across all residues. "
            "This increases overall prediction confidence."
        )
