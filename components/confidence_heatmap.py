from __future__ import annotations

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.models import PredictionResult


def render_confidence_heatmap(prediction: PredictionResult):
    """Render a PAE-style pairwise confidence heatmap.

    Since Boltz-2 doesn't always provide a full PAE matrix, we generate
    a distance-weighted confidence map from per-residue pLDDT scores.
    This gives a visual similar to AlphaFold's PAE plot, showing which
    inter-residue relationships are trustworthy.
    """
    plddt = prediction.plddt_per_residue
    residue_ids = prediction.residue_ids
    chain_ids = prediction.chain_ids

    if not plddt or len(plddt) < 5:
        return

    # Check if actual PAE data is in confidence JSON
    pae_matrix = (prediction.confidence_json or {}).get("pae")

    if pae_matrix is not None:
        _render_true_pae(pae_matrix, residue_ids)
    else:
        _render_estimated_pae(plddt, residue_ids, chain_ids)


def _render_true_pae(pae_matrix: list[list[float]], residue_ids: list[int]):
    """Render actual PAE matrix if available."""
    st.markdown("#### Predicted Aligned Error (PAE)")
    st.caption(
        "Lower values (darker) indicate higher confidence in the relative "
        "position of residue pairs. Off-diagonal blocks suggest domain boundaries."
    )

    arr = np.array(pae_matrix)
    n = min(len(residue_ids), arr.shape[0])
    labels = [str(r) for r in residue_ids[:n]]

    # Subsample for performance if too large
    step = max(1, n // 200)
    arr_sub = arr[:n:step, :n:step]
    labels_sub = labels[:n:step]

    fig = go.Figure(go.Heatmap(
        z=arr_sub,
        x=labels_sub,
        y=labels_sub,
        colorscale="Greens_r",
        zmin=0,
        zmax=30,
        colorbar=dict(title="Expected Error (A)"),
        hovertemplate="Res %{x} vs Res %{y}<br>PAE: %{z:.1f} A<extra></extra>",
    ))
    fig.update_layout(
        xaxis_title="Scored Residue",
        yaxis_title="Aligned Residue",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(t=10, b=50, l=50, r=20),
        yaxis=dict(autorange="reversed"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_estimated_pae(
    plddt: list[float],
    residue_ids: list[int],
    chain_ids: list[str],
):
    """Generate an estimated pairwise confidence map from pLDDT scores.

    For each pair (i, j), the estimated confidence is:
        min(plddt[i], plddt[j]) / 100
    This approximates how reliable the relative positioning is.
    """
    st.markdown("#### Estimated Pairwise Confidence")
    st.caption(
        "Approximated from per-residue pLDDT scores. Darker = higher confidence "
        "in relative positioning. Useful for identifying domain boundaries and "
        "flexible linkers."
    )

    n = len(plddt)

    # Subsample for performance
    step = max(1, n // 150)
    plddt_sub = plddt[::step]
    resids_sub = residue_ids[::step]
    chains_sub = chain_ids[::step]
    m = len(plddt_sub)

    # Build pairwise confidence matrix
    arr = np.zeros((m, m))
    for i in range(m):
        for j in range(m):
            arr[i, j] = min(plddt_sub[i], plddt_sub[j])

    labels = [str(r) for r in resids_sub]

    # Mark chain boundaries
    chain_boundaries = []
    for i in range(1, m):
        if chains_sub[i] != chains_sub[i - 1]:
            chain_boundaries.append(i)

    fig = go.Figure(go.Heatmap(
        z=arr,
        x=labels,
        y=labels,
        colorscale=[
            [0, "#FF7D45"],
            [0.5, "#FFDB13"],
            [0.7, "#65CBF3"],
            [0.9, "#0053D6"],
            [1.0, "#002080"],
        ],
        zmin=0,
        zmax=100,
        colorbar=dict(title="Min pLDDT"),
        hovertemplate="Res %{x} vs Res %{y}<br>Confidence: %{z:.1f}<extra></extra>",
    ))

    # Add chain boundary lines
    shapes = []
    for b in chain_boundaries:
        for axis_key in ["x", "y"]:
            x0 = b - 0.5 if axis_key == "x" else -0.5
            x1 = b - 0.5 if axis_key == "x" else m - 0.5
            y0 = -0.5 if axis_key == "x" else b - 0.5
            y1 = m - 0.5 if axis_key == "x" else b - 0.5
            shapes.append(dict(
                type="line", x0=x0, x1=x1, y0=y0, y1=y1,
                line=dict(color="rgba(0,0,0,0.2)", width=1.5, dash="dash"),
            ))

    fig.update_layout(
        xaxis_title="Residue",
        yaxis_title="Residue",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(t=10, b=50, l=50, r=20),
        yaxis=dict(autorange="reversed"),
        shapes=shapes,
    )
    st.plotly_chart(fig, use_container_width=True)
