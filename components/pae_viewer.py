"""PAE (Predicted Aligned Error) inter-domain confidence viewer.

Renders a 2D heatmap showing per-residue-pair position confidence.
- Diagonal blocks = well-defined domains
- Off-diagonal blocks = inter-domain confidence
- Dark green = low error (high confidence), white = high error
"""
from __future__ import annotations

import re

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from src.models import ProteinQuery

# ────────────────────────────────────────────────────────
# Public entry point
# ────────────────────────────────────────────────────────


def render_pae_viewer(confidence_data: dict, query: ProteinQuery):
    """Render the PAE inter-domain confidence heatmap.

    Parameters
    ----------
    confidence_data:
        The full confidence JSON from a Boltz-2 / AlphaFold prediction.
        Expected key: ``"pae"`` — a list of lists (NxN floats, 0-30 A).
    query:
        The current protein query (used to mark mutation position).
    """
    pae_raw = confidence_data.get("pae")

    if pae_raw is None:
        st.info(
            "No PAE (Predicted Aligned Error) matrix is available for this "
            "structure. PAE data is produced by Boltz-2 and AlphaFold "
            "predictions — it is not available for experimental structures "
            "downloaded from the PDB."
        )
        return

    # Validate shape
    try:
        pae_matrix = np.array(pae_raw, dtype=np.float64)
        if pae_matrix.ndim != 2 or pae_matrix.shape[0] != pae_matrix.shape[1]:
            st.warning("The predicted alignment error (PAE) data has an unexpected format and cannot be displayed. Try re-running the structure prediction.")
            return
    except (ValueError, TypeError):
        st.warning("The PAE data could not be read. Try re-running the structure prediction to generate fresh results.")
        return

    n = pae_matrix.shape[0]
    if n < 5:
        st.warning("PAE matrix is too small to visualise meaningfully.")
        return

    st.markdown("#### Predicted Aligned Error (PAE)")
    st.caption(
        "The PAE measures the expected position error (in Angstroms) between "
        "every pair of residues. Dark blocks on the diagonal indicate "
        "well-defined domains; off-diagonal dark blocks reveal confident "
        "inter-domain packing. White regions are unreliable."
    )

    # Parse mutation position (if any)
    mut_pos: int | None = None
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))

    # Auto-detect domains
    domains = _detect_domains(pae_matrix)

    # Build the figure (cached on the matrix hash)
    fig = _build_pae_figure(pae_matrix, domains, mut_pos)
    st.plotly_chart(fig, use_container_width=True)

    # Domain summary
    if domains and len(domains) == 1:
        st.markdown(
            "**1 domain detected** — the protein appears to be a single "
            "compact domain with uniformly confident internal packing."
        )
    elif domains and len(domains) > 1:
        sizes = [end - start + 1 for start, end in domains]
        sizes_str = ", ".join(str(s) for s in sizes)
        st.markdown(
            f"**{len(domains)} domains detected** — sizes: {sizes_str} residues"
        )

        # Domain detail table
        cols = st.columns(min(len(domains), 5))
        for i, (start, end) in enumerate(domains[: len(cols)]):
            size = end - start + 1
            # Mean intra-domain PAE
            block = pae_matrix[start : end + 1, start : end + 1]
            mean_pae = float(np.mean(block))
            col = cols[i]
            col.metric(
                f"Domain {i + 1}",
                f"{size} res",
                delta=f"PAE {mean_pae:.1f} A",
                delta_color="inverse",
            )
    else:
        st.markdown(
            "Domain detection was inconclusive. The protein may be a single "
            "domain or the PAE signal is too noisy for automatic segmentation."
        )


# ────────────────────────────────────────────────────────
# Domain detection via hierarchical clustering
# ────────────────────────────────────────────────────────


def _detect_domains(pae: np.ndarray, max_pae_within: float = 10.0) -> list[tuple[int, int]]:
    """Auto-detect domain blocks from the PAE matrix.

    Uses scipy hierarchical clustering on the PAE distance matrix.
    Returns a list of (start_idx, end_idx) tuples (0-based, inclusive).
    """
    try:
        from scipy.cluster.hierarchy import fcluster, linkage
        from scipy.spatial.distance import squareform
    except ImportError:
        # Fallback: no scipy — return whole protein as one domain
        return [(0, pae.shape[0] - 1)]

    n = pae.shape[0]

    # Symmetrise the PAE matrix (Boltz-2 PAE can be asymmetric)
    sym_pae = (pae + pae.T) / 2.0
    np.fill_diagonal(sym_pae, 0.0)

    # Subsample if very large (>800 residues) for performance
    step = 1
    if n > 800:
        step = max(1, n // 400)
        sym_pae = sym_pae[::step, ::step]

    m = sym_pae.shape[0]
    if m < 4:
        return [(0, n - 1)]

    # Clip to [0, 30] and convert to condensed distance
    sym_pae = np.clip(sym_pae, 0.0, 30.0)

    try:
        condensed = squareform(sym_pae, checks=False)
        Z = linkage(condensed, method="average")
    except Exception:
        return [(0, n - 1)]

    # Cut tree at a threshold that separates domains
    # Use 12 A as boundary — residue pairs within a domain typically < 10 A PAE
    labels = fcluster(Z, t=12.0, criterion="distance")

    # Map subsampled labels back to full residue indices
    full_labels = np.zeros(n, dtype=int)
    for i in range(m):
        orig_start = i * step
        orig_end = min((i + 1) * step, n)
        full_labels[orig_start:orig_end] = labels[i]

    # Extract contiguous domain segments
    domains: list[tuple[int, int]] = []
    unique_labels = sorted(set(full_labels))

    for lbl in unique_labels:
        indices = np.where(full_labels == lbl)[0]
        if len(indices) == 0:
            continue

        # Find contiguous stretches within this cluster
        breaks = np.where(np.diff(indices) > 5)[0]  # gap > 5 residues = separate
        segments = np.split(indices, breaks + 1)
        for seg in segments:
            if len(seg) >= 10:  # Minimum domain size: 10 residues
                domains.append((int(seg[0]), int(seg[-1])))

    # Sort by start position
    domains.sort(key=lambda d: d[0])

    # If no domains found, treat whole protein as one
    if not domains:
        domains = [(0, n - 1)]

    return domains


# ────────────────────────────────────────────────────────
# Plotly figure builder (cached)
# ────────────────────────────────────────────────────────


@st.cache_data(show_spinner=False)
def _build_pae_figure(
    pae_matrix: np.ndarray,
    domains: list[tuple[int, int]],
    mut_pos: int | None,
) -> go.Figure:
    """Build the Plotly heatmap figure for the PAE matrix.

    Cached on matrix content + domain boundaries + mutation position.
    """
    n = pae_matrix.shape[0]

    # Subsample for rendering if very large
    step = max(1, n // 500)
    pae_sub = pae_matrix[::step, ::step]
    m = pae_sub.shape[0]

    # Build tick labels (residue numbers, 1-based)
    tick_vals = list(range(0, m, max(1, m // 10)))
    tick_text = [str(i * step + 1) for i in tick_vals]

    # Green-white colorscale matching AlphaFold convention
    # 0 A (low error) = dark green, 30 A (high error) = white
    colorscale = [
        [0.0, "#004529"],   # dark green — very low error
        [0.1, "#006837"],
        [0.25, "#31a354"],
        [0.5, "#addd8e"],
        [0.75, "#d9f0a3"],
        [1.0, "#ffffff"],   # white — high error
    ]

    fig = go.Figure(
        go.Heatmap(
            z=pae_sub,
            colorscale=colorscale,
            zmin=0,
            zmax=30,
            colorbar=dict(
                title=dict(text="Expected Error (A)", font=dict(size=12)),
                tickvals=[0, 5, 10, 15, 20, 25, 30],
                ticktext=["0", "5", "10", "15", "20", "25", "30"],
                len=0.8,
            ),
            hovertemplate=(
                "Scored residue: %{x}<br>"
                "Aligned residue: %{y}<br>"
                "PAE: %{z:.1f} A<extra></extra>"
            ),
            x=list(range(m)),
            y=list(range(m)),
        )
    )

    shapes = []

    # Domain boundary rectangles
    domain_colors = ["#34C759", "#AF52DE", "#FF9500", "#FF2D55", "#5AC8FA"]
    for i, (start, end) in enumerate(domains):
        # Convert to subsampled coordinates
        s = start / step
        e = end / step
        color = domain_colors[i % len(domain_colors)]
        shapes.append(
            dict(
                type="rect",
                x0=s - 0.5,
                y0=s - 0.5,
                x1=e + 0.5,
                y1=e + 0.5,
                line=dict(color=color, width=2, dash="solid"),
                fillcolor="rgba(0,0,0,0)",
            )
        )

    # Mutation crosshair lines
    if mut_pos is not None and 1 <= mut_pos <= n:
        mut_idx = (mut_pos - 1) / step  # convert 1-based position to subsampled index
        crosshair_style = dict(color="#FFCC00", width=1.5, dash="dash")
        # Vertical line
        shapes.append(
            dict(
                type="line",
                x0=mut_idx, x1=mut_idx,
                y0=-0.5, y1=m - 0.5,
                line=crosshair_style,
            )
        )
        # Horizontal line
        shapes.append(
            dict(
                type="line",
                x0=-0.5, x1=m - 0.5,
                y0=mut_idx, y1=mut_idx,
                line=crosshair_style,
            )
        )

    # Mutation annotation
    annotations = []
    if mut_pos is not None and 1 <= mut_pos <= n:
        mut_idx = (mut_pos - 1) / step
        annotations.append(
            dict(
                x=mut_idx,
                y=-0.05,
                yref="paper",
                text=f"Mutation ({mut_pos})",
                showarrow=False,
                font=dict(color="#FFCC00", size=11),
            )
        )

    fig.update_layout(
        xaxis=dict(
            title="Scored Residue",
            tickvals=tick_vals,
            ticktext=tick_text,
            gridcolor="rgba(0,0,0,0.08)",
        ),
        yaxis=dict(
            title="Aligned Residue",
            tickvals=tick_vals,
            ticktext=tick_text,
            autorange="reversed",
            gridcolor="rgba(0,0,0,0.08)",
        ),
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=600,
        margin=dict(t=30, b=60, l=60, r=30),
        shapes=shapes,
        annotations=annotations,
    )

    return fig
