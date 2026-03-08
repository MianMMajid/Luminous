"""Multi-layer residue dashboard -- genome-browser-style strip chart.

Shows all per-residue properties in aligned horizontal tracks:
1. pLDDT confidence (blue gradient)
2. SASA -- solvent accessibility (orange)
3. Secondary structure (categorical color blocks)
4. Packing density (purple)
5. Network centrality (green)
6. Known variants (red dots from ClinVar)
7. B-factor / flexibility (if available)

All tracks share the same X axis (residue number) with synchronized zoom/pan.
Mutation site highlighted with a vertical line across all tracks.
"""
from __future__ import annotations

import re

import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from src.models import ProteinQuery

# ---------------------------------------------------------------------------
# Track metadata: name, color scheme, y-axis label
# ---------------------------------------------------------------------------
_TRACK_DEFS: list[dict] = [
    {"key": "plddt", "label": "pLDDT Confidence",
     "yaxis": "pLDDT", "color": "#007AFF"},
    {"key": "alphamissense", "label": "AlphaMissense",
     "yaxis": "AM Score", "color": "#DC3232"},
    {"key": "domains", "label": "Domain Architecture",
     "yaxis": "Domain", "color": "#457B9D"},
    {"key": "sasa", "label": "SASA (Accessibility)",
     "yaxis": "SASA (A^2)", "color": "#FF9500"},
    {"key": "secondary_structure", "label": "Secondary Structure",
     "yaxis": "SS", "color": "#FFC800"},
    {"key": "packing", "label": "Packing Density",
     "yaxis": "Neighbors", "color": "#AF52DE"},
    {"key": "centrality", "label": "Network Centrality",
     "yaxis": "Centrality", "color": "#32D74B"},
    {"key": "variants", "label": "Pathogenic Variants",
     "yaxis": "Variant", "color": "#E00000"},
    {"key": "bfactor", "label": "B-factor / Flexibility",
     "yaxis": "B-factor", "color": "#AC8E68"},
    # ── New hidden-insight tracks ──
    {"key": "hydrophobicity", "label": "Hydrophobicity",
     "yaxis": "KD Score", "color": "#E67E22"},
    {"key": "charge", "label": "Charge (pH 7.4)",
     "yaxis": "Charge", "color": "#3498DB"},
    {"key": "disorder", "label": "Disorder Prediction",
     "yaxis": "Disorder", "color": "#8E8E93"},
    {"key": "conservation", "label": "Conservation (1-9)",
     "yaxis": "ConSurf", "color": "#9B59B6"},
    {"key": "pocket_score", "label": "Pocket / Druggability",
     "yaxis": "Pocket", "color": "#2ECC71"},
    {"key": "residue_depth", "label": "Residue Depth",
     "yaxis": "Depth (Å)", "color": "#1ABC9C"},
    {"key": "ramachandran", "label": "Ramachandran Outliers",
     "yaxis": "Rama", "color": "#E74C3C"},
]

# Secondary structure color map (Mol* standard)
_SS_COLORS = {"a": "#FF0080", "b": "#FFC800", "c": "#808080"}
_SS_LABELS = {"a": "α-Helix", "b": "β-Sheet", "c": "Coil"}


def render_residue_dashboard(
    structure_analysis: dict,
    plddt_scores: list,
    query: ProteinQuery,
    variant_data: dict | None = None,
) -> None:
    """Render a genome-browser-style multi-track residue dashboard.

    Parameters
    ----------
    structure_analysis : dict
        Output of ``analyze_structure()`` -- per-residue SASA, SSE, packing,
        centrality, contact maps, etc.
    plddt_scores : list
        Per-residue pLDDT confidence scores (0-100).
    query : ProteinQuery
        Parsed protein query with optional mutation field.
    variant_data : dict | None
        ClinVar / pathogenic variant data.  Expected shape:
        ``{"pathogenic_positions": {pos_int: [variant_names]}}``
    """
    st.markdown("### Residue Property Dashboard")
    _DASH_CAPTIONS = {
        "structure": "Per-residue structural properties — confidence, accessibility, "
                     "secondary structure, and backbone geometry.",
        "mutation_impact": "Per-residue properties around the mutation site — "
                           "conservation, pathogenicity, and structural context.",
        "druggability": "Per-residue druggability signals — pocket scores, "
                        "surface properties, and network centrality.",
        "binding": "Per-residue binding interface properties — accessibility, "
                   "hydrophobicity, charge, and contact density.",
    }
    st.caption(_DASH_CAPTIONS.get(
        query.question_type,
        "Genome-browser-style multi-track view of per-residue properties. "
        "All tracks share a synchronized x-axis — zoom or pan to explore.",
    ))

    residue_ids: list[int] = structure_analysis.get("residue_ids", [])
    if not residue_ids:
        st.info("No residue data available for the dashboard.")
        return

    # Parse mutation position
    mutation_pos: int | None = _parse_mutation_pos(query.mutation)

    # Normalize variant data
    pathogenic_positions: dict[int, list[str]] = {}
    if variant_data and variant_data.get("pathogenic_positions"):
        for pos_key, names in variant_data["pathogenic_positions"].items():
            try:
                pathogenic_positions[int(pos_key)] = (
                    names if isinstance(names, list) else [str(names)]
                )
            except (ValueError, TypeError):
                pass

    # ---- Track selector ----
    available_tracks = _detect_available_tracks(
        structure_analysis, plddt_scores, pathogenic_positions
    )
    all_labels = [t["label"] for t in _TRACK_DEFS if t["key"] in available_tracks]

    # Smart defaults: show 4-5 essential tracks to avoid overwhelming users.
    # Additional tracks are still selectable via the multiselect widget.
    _REC: dict[str, set[str]] = {
        "structure": {"plddt", "sasa", "secondary_structure", "packing"},
        "mutation_impact": {"plddt", "variants", "sasa", "centrality",
                            "conservation"},
        "druggability": {"plddt", "pocket_score", "sasa", "centrality"},
        "binding": {"plddt", "sasa", "packing", "hydrophobicity"},
    }
    rec_keys = _REC.get(query.question_type, set())
    if rec_keys:
        default_labels = [
            t["label"] for t in _TRACK_DEFS
            if t["key"] in available_tracks and t["key"] in rec_keys
        ]
    else:
        default_labels = all_labels
    label_pri = {t["label"]: (0 if t["key"] in rec_keys else 1) for t in _TRACK_DEFS}
    all_labels_sorted = sorted(all_labels, key=lambda lb: label_pri.get(lb, 1))
    qtype_label = query.question_type.replace("_", " ")

    selected_labels = st.multiselect(
        "Tracks to display",
        options=all_labels_sorted,
        default=default_labels or all_labels_sorted,
        key="residue_dashboard_tracks",
        help=f"Showing tracks recommended for **{qtype_label}** analysis. "
             "Add more tracks to explore additional properties.",
    )

    # Map selected labels back to keys
    label_to_key = {t["label"]: t["key"] for t in _TRACK_DEFS}
    selected_keys = [label_to_key[lbl] for lbl in selected_labels if lbl in label_to_key]

    if not selected_keys:
        st.info("Select at least one track to display.")
        return

    # ---- Build figure ----
    fig = _build_dashboard_figure(
        residue_ids=residue_ids,
        plddt_scores=plddt_scores,
        structure_analysis=structure_analysis,
        selected_keys=selected_keys,
        mutation_pos=mutation_pos,
        pathogenic_positions=pathogenic_positions,
    )

    selection = st.plotly_chart(
        fig, use_container_width=True, key="residue_dashboard_chart",
        on_select="rerun",
    )

    # Cross-filtering: capture selected residues from dashboard click/selection
    if selection and selection.get("selection", {}).get("points"):
        selected_points = selection["selection"]["points"]
        selected_residues = []
        for pt in selected_points:
            x_val = pt.get("x")
            if x_val is not None:
                try:
                    selected_residues.append(int(x_val))
                except (ValueError, TypeError):
                    pass
        if selected_residues:
            st.session_state["selected_residues"] = selected_residues
            st.caption(
                f"Selected {len(selected_residues)} residue(s): "
                f"{', '.join(map(str, selected_residues[:10]))}"
                f"{'...' if len(selected_residues) > 10 else ''}"
            )

    # ---- Residue Insights callout ----
    _render_residue_insights(
        residue_ids=residue_ids,
        plddt_scores=plddt_scores,
        structure_analysis=structure_analysis,
        mutation_pos=mutation_pos,
        pathogenic_positions=pathogenic_positions,
    )


# ---------------------------------------------------------------------------
# Figure construction
# ---------------------------------------------------------------------------


def _build_dashboard_figure(
    residue_ids: list[int],
    plddt_scores: list,
    structure_analysis: dict,
    selected_keys: list[str],
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
) -> go.Figure:
    """Construct the multi-track Plotly figure."""
    n_tracks = len(selected_keys)
    track_defs = [t for t in _TRACK_DEFS if t["key"] in selected_keys]

    # Compute row heights: give secondary structure + variant tracks less height
    row_heights = []
    for td in track_defs:
        if td["key"] in ("secondary_structure", "variants", "domains", "ramachandran"):
            row_heights.append(0.6)
        else:
            row_heights.append(1.0)

    fig = make_subplots(
        rows=n_tracks,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.02,
        row_heights=row_heights,
        subplot_titles=[td["label"] for td in track_defs],
    )

    # Precompute a hover-text array that combines ALL properties per residue
    hover_map = _build_hover_map(
        residue_ids, plddt_scores,
        structure_analysis, pathogenic_positions,
    )

    for row_idx, td in enumerate(track_defs, start=1):
        key = td["key"]

        if key == "plddt":
            _add_plddt_track(fig, row_idx, residue_ids, plddt_scores, hover_map)
        elif key == "alphamissense":
            _add_alphamissense_track(fig, row_idx, residue_ids, hover_map)
        elif key == "domains":
            _add_domain_track(fig, row_idx, residue_ids, hover_map)
        elif key == "sasa":
            _add_sasa_track(fig, row_idx, residue_ids, structure_analysis, hover_map)
        elif key == "secondary_structure":
            _add_ss_track(fig, row_idx, residue_ids, structure_analysis, hover_map)
        elif key == "packing":
            _add_packing_track(fig, row_idx, residue_ids, structure_analysis, hover_map)
        elif key == "centrality":
            _add_centrality_track(fig, row_idx, residue_ids, structure_analysis, hover_map)
        elif key == "variants":
            _add_variant_track(fig, row_idx, residue_ids, pathogenic_positions, hover_map)
        elif key == "bfactor":
            _add_bfactor_track(fig, row_idx, residue_ids, structure_analysis, hover_map)
        elif key == "hydrophobicity":
            _add_hydrophobicity_track(fig, row_idx, residue_ids, hover_map)
        elif key == "charge":
            _add_charge_track(fig, row_idx, residue_ids, hover_map)
        elif key == "disorder":
            _add_disorder_track(fig, row_idx, residue_ids, hover_map)
        elif key == "conservation":
            _add_conservation_track(fig, row_idx, residue_ids, hover_map)
        elif key == "pocket_score":
            _add_pocket_track(fig, row_idx, residue_ids, hover_map)
        elif key == "residue_depth":
            _add_depth_track(fig, row_idx, residue_ids, hover_map)
        elif key == "ramachandran":
            _add_ramachandran_track(fig, row_idx, residue_ids, structure_analysis, hover_map)

        # Y-axis label
        fig.update_yaxes(
            title_text=td["yaxis"],
            row=row_idx,
            col=1,
            title_font=dict(size=10, color="rgba(60,60,67,0.6)"),
            tickfont=dict(size=9, color="rgba(60,60,67,0.4)"),
            gridcolor="rgba(0,0,0,0.08)",
            zeroline=False,
        )

    # ---- Mutation site vertical line across ALL tracks ----
    if mutation_pos is not None and mutation_pos in residue_ids:
        for row_idx in range(1, n_tracks + 1):
            fig.add_vline(
                x=mutation_pos,
                line_width=2,
                line_dash="dash",
                line_color="#FF3B30",
                opacity=0.7,
                row=row_idx,
                col=1,
                annotation=dict(text="") if row_idx > 1 else None,
            )
        # Add a single annotation at the top
        fig.add_annotation(
            x=mutation_pos,
            y=1.0,
            yref="y domain",
            xref="x",
            text=f"Pos {mutation_pos}",
            showarrow=True,
            arrowhead=2,
            arrowcolor="#FF3B30",
            font=dict(color="#FF3B30", size=11, family="monospace"),
            bgcolor="rgba(255,69,58,0.15)",
            bordercolor="#FF3B30",
            borderwidth=1,
            borderpad=3,
        )

    # ---- Global layout ----
    total_height = max(400, int(120 * n_tracks + 80))
    total_height = min(total_height, 900)

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=total_height,
        margin=dict(t=30, b=40, l=60, r=20),
        showlegend=False,
        font=dict(family="Inter, system-ui, sans-serif"),
    )

    # X-axis on the bottom-most subplot only
    fig.update_xaxes(
        title_text="Residue Number",
        row=n_tracks,
        col=1,
        title_font=dict(size=11, color="rgba(60,60,67,0.6)"),
        tickfont=dict(size=9, color="rgba(60,60,67,0.4)"),
        gridcolor="rgba(0,0,0,0.08)",
    )

    # Style only subplot title annotations (first n_tracks annotations from make_subplots)
    for i, ann in enumerate(fig.layout.annotations):
        if i < n_tracks:
            ann.update(font=dict(size=11, color="rgba(60,60,67,0.5)"), x=0.01, xanchor="left")

    return fig


# ---------------------------------------------------------------------------
# Individual track builders
# ---------------------------------------------------------------------------


def _add_plddt_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    plddt_scores: list,
    hover_map: dict[int, str],
) -> None:
    if not plddt_scores:
        return
    # Ensure alignment and numeric types (paired filter to avoid misalignment)
    paired = [
        (r, float(s))
        for r, s in zip(residue_ids, plddt_scores)
        if isinstance(s, (int, float))
    ]
    if not paired:
        return
    rids, scores = zip(*paired)
    rids, scores = list(rids), list(scores)
    if not rids:
        return

    # Color-code each point by pLDDT tier
    colors = []
    for s in scores:
        if s >= 90:
            colors.append("#0053D6")
        elif s >= 70:
            colors.append("#65CBF3")
        elif s >= 50:
            colors.append("#FFDB13")
        else:
            colors.append("#FF7D45")

    fig.add_trace(
        go.Bar(
            x=rids,
            y=scores,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in rids],
            hoverinfo="text",
            name="pLDDT",
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(range=[0, 100], row=row, col=1)


def _add_alphamissense_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    hover_map: dict[int, str],
) -> None:
    """AlphaMissense pathogenicity scores as a colored bar chart."""
    am_data = _get_current_am_data()
    if not am_data:
        return

    from src.alphamissense import get_pathogenicity_color

    residue_scores = am_data.get("residue_scores", {})
    vals = [residue_scores.get(r, 0.0) for r in residue_ids]
    colors = [get_pathogenicity_color(v) for v in vals]

    fig.add_trace(
        go.Bar(
            x=residue_ids,
            y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="AlphaMissense",
        ),
        row=row,
        col=1,
    )
    # Threshold lines
    fig.add_hline(
        y=0.564, line_dash="dot", line_color="rgba(220,50,50,0.4)",
        row=row, col=1,
        annotation_text="pathogenic",
        annotation_font=dict(size=8, color="rgba(220,50,50,0.5)"),
        annotation_position="top right",
    )
    fig.add_hline(
        y=0.34, line_dash="dot", line_color="rgba(69,123,157,0.4)",
        row=row, col=1,
        annotation_text="benign",
        annotation_font=dict(size=8, color="rgba(69,123,157,0.5)"),
        annotation_position="top right",
    )
    fig.update_yaxes(range=[0, 1.05], row=row, col=1)


def _add_domain_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    hover_map: dict[int, str],
) -> None:
    """Domain architecture as colored blocks (like secondary structure)."""
    dom_data = _get_current_domain_data()
    if not dom_data:
        return

    domains = dom_data.get("domains", [])

    # Build residue→color map
    res_colors: dict[int, str] = {}
    for d in domains:
        for pos in range(d.get("start", 0), d.get("end", 0) + 1):
            res_colors[pos] = d.get("color", "#CCCCCC")

    colors = [
        res_colors.get(r, "rgba(0,0,0,0.05)")
        for r in residue_ids
    ]

    fig.add_trace(
        go.Bar(
            x=residue_ids,
            y=[1] * len(residue_ids),
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="Domains",
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(
        range=[0, 1.2], showticklabels=False,
        row=row, col=1,
    )


def _add_sasa_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    analysis: dict,
    hover_map: dict[int, str],
) -> None:
    sasa = analysis.get("sasa_per_residue", {})
    if not sasa:
        return

    vals = [sasa.get(r, 0.0) for r in residue_ids]

    fig.add_trace(
        go.Scatter(
            x=residue_ids,
            y=vals,
            mode="lines",
            line=dict(color="#FF9500", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(255,149,0,0.15)",
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="SASA",
        ),
        row=row,
        col=1,
    )
    # Add buried threshold line
    fig.add_hline(
        y=25.0,
        line_dash="dot",
        line_color="rgba(255,149,0,0.3)",
        row=row,
        col=1,
        annotation_text="buried/exposed",
        annotation_font=dict(size=8, color="rgba(255,149,0,0.4)"),
        annotation_position="top right",
    )


def _add_ss_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    analysis: dict,
    hover_map: dict[int, str],
) -> None:
    """Secondary structure as colored blocks (helix / sheet / coil)."""
    sse = analysis.get("sse_per_residue", {})
    if not sse:
        return

    # Encode as numeric: helix=2, sheet=1, coil=0
    ss_map = {"a": 2, "b": 1, "c": 0}
    y_vals = []
    colors = []
    labels = []
    for r in residue_ids:
        ss = str(sse.get(r, "c")).strip()
        if ss not in ss_map:
            ss = "c"
        y_vals.append(ss_map[ss])
        colors.append(_SS_COLORS[ss])
        labels.append(_SS_LABELS[ss])

    fig.add_trace(
        go.Bar(
            x=residue_ids,
            y=[1] * len(residue_ids),  # uniform height
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="SS",
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(
        range=[0, 1.2],
        showticklabels=False,
        row=row,
        col=1,
    )


def _add_packing_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    analysis: dict,
    hover_map: dict[int, str],
) -> None:
    packing = analysis.get("packing_density", {})
    if not packing:
        return
    vals = [packing.get(r, 0) for r in residue_ids]

    fig.add_trace(
        go.Scatter(
            x=residue_ids,
            y=vals,
            mode="lines",
            line=dict(color="#AF52DE", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(175,82,222,0.12)",
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="Packing",
        ),
        row=row,
        col=1,
    )


def _add_centrality_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    analysis: dict,
    hover_map: dict[int, str],
) -> None:
    centrality = analysis.get("network_centrality", {})
    if not centrality:
        return
    vals = [centrality.get(r, 0.0) for r in residue_ids]

    fig.add_trace(
        go.Scatter(
            x=residue_ids,
            y=vals,
            mode="lines",
            line=dict(color="#32D74B", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(50,215,75,0.12)",
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="Centrality",
        ),
        row=row,
        col=1,
    )

    # Mark hub residues
    hubs = analysis.get("hub_residues", [])
    if hubs:
        rid_set = set(residue_ids)
        hub_x = [h.get("residue") for h in hubs if isinstance(h, dict) and h.get("residue") in rid_set]
        hub_y = [centrality.get(r, 0) for r in hub_x]
        fig.add_trace(
            go.Scatter(
                x=hub_x,
                y=hub_y,
                mode="markers",
                marker=dict(
                    symbol="diamond",
                    size=7,
                    color="#32D74B",
                    line=dict(width=1, color="#000000"),
                ),
                hovertext=[f"Hub residue {x}" for x in hub_x],
                hoverinfo="text",
                name="Hub",
            ),
            row=row,
            col=1,
        )


def _add_variant_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    pathogenic_positions: dict[int, list[str]],
    hover_map: dict[int, str],
) -> None:
    """Show pathogenic variant positions as red triangles on a flat baseline."""
    # Baseline: zero line for all residues
    fig.add_trace(
        go.Scatter(
            x=[residue_ids[0], residue_ids[-1]] if residue_ids else [],
            y=[0, 0],
            mode="lines",
            line=dict(color="rgba(0,0,0,0.08)", width=1),
            hoverinfo="skip",
            name="_baseline",
            showlegend=False,
        ),
        row=row,
        col=1,
    )

    if pathogenic_positions:
        var_x = sorted(p for p in pathogenic_positions if p in set(residue_ids))
        var_y = [1] * len(var_x)
        hover_texts = []
        for p in var_x:
            names = pathogenic_positions[p]
            name_str = ", ".join(names) if isinstance(names, list) else str(names)
            hover_texts.append(
                f"Residue {p}<br>Pathogenic: {name_str}"
            )

        fig.add_trace(
            go.Scatter(
                x=var_x,
                y=var_y,
                mode="markers",
                marker=dict(
                    symbol="triangle-up",
                    size=10,
                    color="#E00000",
                    line=dict(width=1, color="#FF6961"),
                ),
                hovertext=hover_texts,
                hoverinfo="text",
                name="Pathogenic",
            ),
            row=row,
            col=1,
        )

    fig.update_yaxes(range=[-0.3, 1.5], showticklabels=False, row=row, col=1)


def _add_bfactor_track(
    fig: go.Figure,
    row: int,
    residue_ids: list[int],
    analysis: dict,
    hover_map: dict[int, str],
) -> None:
    """B-factor / flexibility track.

    Uses contacts_per_residue as a proxy for rigidity (inverse flexibility)
    since actual B-factors may not be available from predicted structures.
    """
    contacts = analysis.get("contacts_per_residue", {})
    if not contacts:
        return

    # Inverse: more contacts = more rigid = lower flexibility
    max_contacts = max(contacts.values()) or 1
    vals = []
    for r in residue_ids:
        c = contacts.get(r, 0)
        flexibility = 1.0 - (c / max_contacts)
        vals.append(round(flexibility, 3))

    fig.add_trace(
        go.Scatter(
            x=residue_ids,
            y=vals,
            mode="lines",
            line=dict(color="#AC8E68", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(172,142,104,0.12)",
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text",
            name="Flexibility",
        ),
        row=row,
        col=1,
    )
    fig.update_yaxes(range=[0, 1.1], row=row, col=1)


# ---------------------------------------------------------------------------
# New insight track builders (Phase 1: computed-but-invisible data)
# ---------------------------------------------------------------------------


# --- Cached compute helpers (persist across reruns for same PDB content) ---

@st.cache_data(show_spinner=False, ttl=3600)
def _cached_surface(pdb_content: str) -> dict | None:
    try:
        from src.surface_properties import compute_surface_properties
        return compute_surface_properties(pdb_content)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_disorder(pdb_content: str, plddt_tuple: tuple | None) -> dict | None:
    try:
        from src.disorder_prediction import predict_disorder
        plddt = list(plddt_tuple) if plddt_tuple else None
        return predict_disorder(pdb_content, plddt)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_conservation(pdb_content: str) -> dict | None:
    try:
        from src.conservation import compute_conservation_scores
        return compute_conservation_scores(pdb_content)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_pockets(pdb_content: str) -> dict | None:
    try:
        from src.pocket_prediction import predict_pockets
        return predict_pockets(pdb_content)
    except Exception:
        return None


@st.cache_data(show_spinner=False, ttl=3600)
def _cached_depth(pdb_content: str) -> dict | None:
    try:
        from src.residue_depth import compute_residue_depth
        return compute_residue_depth(pdb_content)
    except Exception:
        return None


def _get_surface_data() -> dict | None:
    """Get surface property data (st.cache_data backed)."""
    prediction = st.session_state.get("prediction_result")
    if prediction and hasattr(prediction, "pdb_content") and prediction.pdb_content:
        return _cached_surface(prediction.pdb_content)
    return None


def _get_disorder_data() -> dict | None:
    prediction = st.session_state.get("prediction_result")
    if prediction and hasattr(prediction, "pdb_content") and prediction.pdb_content:
        plddt = None
        if hasattr(prediction, "plddt_per_residue") and prediction.plddt_per_residue:
            plddt = tuple(prediction.plddt_per_residue)
        return _cached_disorder(prediction.pdb_content, plddt)
    return None


def _get_conservation_data() -> dict | None:
    prediction = st.session_state.get("prediction_result")
    if prediction and hasattr(prediction, "pdb_content") and prediction.pdb_content:
        return _cached_conservation(prediction.pdb_content)
    return None


def _get_pocket_data() -> dict | None:
    prediction = st.session_state.get("prediction_result")
    if prediction and hasattr(prediction, "pdb_content") and prediction.pdb_content:
        return _cached_pockets(prediction.pdb_content)
    return None


def _get_depth_data() -> dict | None:
    prediction = st.session_state.get("prediction_result")
    if prediction and hasattr(prediction, "pdb_content") and prediction.pdb_content:
        return _cached_depth(prediction.pdb_content)
    return None


def _add_hydrophobicity_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """Kyte-Doolittle hydrophobicity profile with hydrophobic patches highlighted."""
    data = _get_surface_data()
    if not data:
        return
    smoothed = data.get("hydrophobicity_smoothed", {})
    if not smoothed:
        return

    vals = [smoothed.get(r, 0.0) for r in residue_ids]

    # Color: hydrophobic = orange, hydrophilic = blue
    colors = [
        "#E67E22" if v > 0 else "#3498DB" for v in vals
    ]

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Hydrophobicity",
        ),
        row=row, col=1,
    )
    fig.add_hline(
        y=0, line_dash="dot", line_color="rgba(0,0,0,0.2)",
        row=row, col=1,
    )


def _add_charge_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """Per-residue charge at pH 7.4 (positive = blue, negative = red)."""
    data = _get_surface_data()
    if not data:
        return
    charge = data.get("charge", {})
    if not charge:
        return

    vals = [charge.get(r, 0.0) for r in residue_ids]
    colors = []
    for v in vals:
        if v > 0.5:
            colors.append("#3498DB")   # positive (K, R)
        elif v < -0.5:
            colors.append("#E74C3C")   # negative (D, E)
        else:
            colors.append("#BDC3C7")   # neutral

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Charge",
        ),
        row=row, col=1,
    )
    fig.update_yaxes(range=[-1.2, 1.2], row=row, col=1)


def _add_disorder_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """Multi-signal disorder prediction (>0.5 = disordered)."""
    data = _get_disorder_data()
    if not data:
        return
    scores = data.get("disorder_scores", {})
    if not scores:
        return

    vals = [scores.get(r, 0.0) for r in residue_ids]
    colors = ["#FF6B6B" if v > 0.5 else "#95A5A6" for v in vals]

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Disorder",
        ),
        row=row, col=1,
    )
    fig.add_hline(
        y=0.5, line_dash="dot", line_color="rgba(255,107,107,0.5)",
        row=row, col=1,
        annotation_text="disordered",
        annotation_font=dict(size=8, color="rgba(255,107,107,0.6)"),
        annotation_position="top right",
    )
    fig.update_yaxes(range=[0, 1.05], row=row, col=1)


def _add_conservation_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """ConSurf-like conservation (1-9 scale, 9=most conserved)."""
    data = _get_conservation_data()
    if not data:
        return
    scores = data.get("conservation_scores", {})
    if not scores:
        return

    vals = [scores.get(r, 5) for r in residue_ids]

    # ConSurf color scheme: variable=cyan → conserved=magenta
    def _consurf_color(s: int) -> str:
        palette = {
            1: "#00D4FF", 2: "#16B8DE", 3: "#2C9CBD",
            4: "#438199", 5: "#596675", 6: "#704B54",
            7: "#873033", 8: "#9D1512", 9: "#B40000",
        }
        return palette.get(s, "#596675")

    colors = [_consurf_color(int(v)) for v in vals]

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Conservation",
        ),
        row=row, col=1,
    )
    fig.add_hline(
        y=7, line_dash="dot", line_color="rgba(180,0,0,0.3)",
        row=row, col=1,
        annotation_text="highly conserved",
        annotation_font=dict(size=8, color="rgba(180,0,0,0.4)"),
        annotation_position="top right",
    )
    fig.update_yaxes(range=[0, 10], row=row, col=1)


def _add_pocket_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """Per-residue pocket/druggability score."""
    data = _get_pocket_data()
    if not data:
        return
    raw_scores = data.get("residue_pocket_scores", {})
    if not raw_scores:
        return
    # Ensure int keys (JSON roundtrip may leave string keys)
    scores = {
        int(k) if isinstance(k, str) and k.isdigit() else k: v
        for k, v in raw_scores.items()
    }

    vals = [scores.get(r, 0.0) for r in residue_ids]

    # Highlight pocket residues in green
    colors = ["#2ECC71" if v > 0.5 else "rgba(46,204,113,0.25)" for v in vals]

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Pocket Score",
        ),
        row=row, col=1,
    )
    fig.add_hline(
        y=0.5, line_dash="dot", line_color="rgba(46,204,113,0.4)",
        row=row, col=1,
        annotation_text="pocket threshold",
        annotation_font=dict(size=8, color="rgba(46,204,113,0.5)"),
        annotation_position="top right",
    )
    fig.update_yaxes(range=[0, 1.05], row=row, col=1)


def _add_depth_track(
    fig: go.Figure, row: int, residue_ids: list[int], hover_map: dict[int, str],
) -> None:
    """Residue depth (distance to nearest surface atom in Å)."""
    data = _get_depth_data()
    if not data:
        return
    depth = data.get("depth", {})
    if not depth:
        return

    vals = [depth.get(r, 0.0) for r in residue_ids]

    # Gradient: shallow=light teal, deep=dark teal
    max_d = max(vals) if vals else 1
    colors = [
        f"rgba(26,188,156,{min(1, 0.2 + 0.8 * v / max_d)})" if max_d > 0
        else "rgba(26,188,156,0.3)"
        for v in vals
    ]

    fig.add_trace(
        go.Scatter(
            x=residue_ids, y=vals,
            mode="lines",
            line=dict(color="#1ABC9C", width=1.5),
            fill="tozeroy",
            fillcolor="rgba(26,188,156,0.15)",
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Depth",
        ),
        row=row, col=1,
    )
    # Depth zone lines
    fig.add_hline(
        y=4.0, line_dash="dot", line_color="rgba(26,188,156,0.3)",
        row=row, col=1,
        annotation_text="surface",
        annotation_font=dict(size=8, color="rgba(26,188,156,0.5)"),
        annotation_position="top right",
    )
    fig.add_hline(
        y=8.0, line_dash="dot", line_color="rgba(26,188,156,0.5)",
        row=row, col=1,
        annotation_text="deep core",
        annotation_font=dict(size=8, color="rgba(26,188,156,0.7)"),
        annotation_position="top right",
    )


def _add_ramachandran_track(
    fig: go.Figure, row: int, residue_ids: list[int],
    analysis: dict, hover_map: dict[int, str],
) -> None:
    """Ramachandran outlier indicators (red = outlier, yellow = allowed, hidden = favored)."""
    rama = analysis.get("ramachandran", [])
    if not rama:
        return

    # Build residue → classification map
    rama_class: dict[int, str] = {}
    for r in rama:
        rid = r.get("residue")
        phi, psi = r.get("phi"), r.get("psi")
        if rid is None or phi is None or psi is None:
            continue
        if _rama_is_favored(phi, psi):
            rama_class[rid] = "favored"
        elif _rama_is_allowed(phi, psi):
            rama_class[rid] = "allowed"
        else:
            rama_class[rid] = "outlier"

    # Only show allowed + outlier residues (favored = baseline)
    y_vals = []
    colors = []
    for r in residue_ids:
        cls = rama_class.get(r, "favored")
        if cls == "outlier":
            y_vals.append(1.0)
            colors.append("#E74C3C")
        elif cls == "allowed":
            y_vals.append(0.5)
            colors.append("#F39C12")
        else:
            y_vals.append(0.0)
            colors.append("rgba(0,0,0,0.03)")

    fig.add_trace(
        go.Bar(
            x=residue_ids, y=y_vals,
            marker=dict(color=colors, line=dict(width=0)),
            hovertext=[hover_map.get(r, "") for r in residue_ids],
            hoverinfo="text", name="Rama",
        ),
        row=row, col=1,
    )
    fig.update_yaxes(range=[0, 1.2], showticklabels=False, row=row, col=1)


def _rama_is_favored(phi: float, psi: float) -> bool:
    if -160 <= phi <= -20 and -120 <= psi <= 20:
        return True
    if -180 <= phi <= -40 and 80 <= psi <= 180:
        return True
    if -180 <= phi <= -40 and -180 <= psi <= -120:
        return True
    return False


def _rama_is_allowed(phi: float, psi: float) -> bool:
    if _rama_is_favored(phi, psi):
        return False
    if -180 <= phi <= 0 and -180 <= psi <= 180:
        return True
    if 20 <= phi <= 120 and -20 <= psi <= 80:
        return True
    return False


# ---------------------------------------------------------------------------
# Hover text builder
# ---------------------------------------------------------------------------


def _build_hover_map(
    residue_ids: list[int],
    plddt_scores: list,
    analysis: dict,
    pathogenic_positions: dict[int, list[str]],
) -> dict[int, str]:
    """Build a combined hover text for each residue showing ALL properties."""
    sasa = analysis.get("sasa_per_residue", {})
    sse = analysis.get("sse_per_residue", {})
    packing = analysis.get("packing_density", {})
    centrality = analysis.get("network_centrality", {})
    contacts = analysis.get("contacts_per_residue", {})

    plddt_lookup: dict[int, float] = {}
    if plddt_scores:
        for i, rid in enumerate(residue_ids):
            if i < len(plddt_scores):
                plddt_lookup[rid] = plddt_scores[i]

    # Gather AlphaMissense data if available (query-specific)
    am_scores: dict[int, float] = {}
    am_class: dict[int, str] = {}
    _am = _get_current_am_data()
    if _am:
        am_scores = _am.get("residue_scores", {})
        am_class = _am.get("classification", {})

    # Gather domain data if available (query-specific)
    domain_map: dict[int, str] = {}
    _dom = _get_current_domain_data()
    if _dom:
        domain_map = _dom.get("domain_map", {})

    # Gather new insight data
    _surface = _get_surface_data()
    hydrophobicity = _surface.get("hydrophobicity_smoothed", {}) if _surface else {}
    charge_data = _surface.get("charge", {}) if _surface else {}

    _disorder = _get_disorder_data()
    disorder_scores = _disorder.get("disorder_scores", {}) if _disorder else {}

    _conservation = _get_conservation_data()
    conservation_scores = _conservation.get("conservation_scores", {}) if _conservation else {}

    _pocket = _get_pocket_data()
    pocket_scores = _pocket.get("residue_pocket_scores", {}) if _pocket else {}

    _depth = _get_depth_data()
    depth_vals = _depth.get("depth", {}) if _depth else {}

    hover_map: dict[int, str] = {}
    for r in residue_ids:
        lines = [f"<b>Residue {r}</b>"]

        if r in plddt_lookup:
            lines.append(f"pLDDT: {plddt_lookup[r]:.1f}")

        if r in am_scores:
            cls = am_class.get(r, "")
            cls_str = f" ({cls})" if cls else ""
            lines.append(f"AM: {am_scores[r]:.3f}{cls_str}")

        if r in domain_map:
            lines.append(f"Domain: {domain_map[r]}")

        if r in sasa:
            exposure = "exposed" if sasa[r] >= 25.0 else "buried"
            lines.append(f"SASA: {sasa[r]:.1f} A^2 ({exposure})")

        ss_code = str(sse.get(r, "")).strip()
        if ss_code in _SS_LABELS:
            lines.append(f"SS: {_SS_LABELS[ss_code]}")

        if r in packing:
            lines.append(f"Packing: {packing[r]} neighbors")

        if r in centrality:
            lines.append(f"Centrality: {centrality[r]:.4f}")

        if r in contacts:
            lines.append(f"Contacts: {contacts[r]}")

        # New insight data in hover
        if r in hydrophobicity:
            label = "hydrophobic" if hydrophobicity[r] > 0 else "hydrophilic"
            lines.append(f"Hydro: {hydrophobicity[r]:+.2f} ({label})")

        if r in charge_data and charge_data[r] != 0:
            sign = "+" if charge_data[r] > 0 else ""
            lines.append(f"Charge: {sign}{charge_data[r]:.1f}")

        if r in disorder_scores:
            is_dis = "DISORDERED" if disorder_scores[r] > 0.5 else "ordered"
            lines.append(f"Disorder: {disorder_scores[r]:.2f} ({is_dis})")

        if r in conservation_scores:
            lines.append(f"Conservation: {conservation_scores[r]}/9")

        if r in pocket_scores and pocket_scores[r] > 0.3:
            lines.append(f"Pocket: {pocket_scores[r]:.2f}")

        if r in depth_vals:
            lines.append(f"Depth: {depth_vals[r]:.1f} Å")

        if r in pathogenic_positions:
            names = pathogenic_positions[r]
            name_str = ", ".join(names) if isinstance(names, list) else str(names)
            lines.append(f"<span style='color:#E00000'>PATHOGENIC: {name_str}</span>")

        hover_map[r] = "<br>".join(lines)

    return hover_map


# ---------------------------------------------------------------------------
# Detect available tracks
# ---------------------------------------------------------------------------


def _get_current_am_data() -> dict | None:
    """Get AlphaMissense data for the current query."""
    query = st.session_state.get("parsed_query")
    if query and query.uniprot_id:
        key = f"alphamissense_{query.uniprot_id}"
        am = st.session_state.get(key)
        if am and am.get("available"):
            return am
    return None


def _get_current_domain_data() -> dict | None:
    """Get domain annotation data for the current query."""
    query = st.session_state.get("parsed_query")
    if query and query.uniprot_id:
        key = f"domains_{query.uniprot_id}"
        dom = st.session_state.get(key)
        if dom and dom.get("available"):
            return dom
    return None


def _detect_available_tracks(
    analysis: dict,
    plddt_scores: list,
    pathogenic_positions: dict[int, list[str]],
) -> set[str]:
    """Return set of track keys that have actual data."""
    available: set[str] = set()

    if plddt_scores:
        available.add("plddt")
    if analysis.get("sasa_per_residue"):
        available.add("sasa")
    if analysis.get("sse_per_residue"):
        available.add("secondary_structure")
    if analysis.get("packing_density"):
        available.add("packing")
    if analysis.get("network_centrality"):
        available.add("centrality")
    if pathogenic_positions:
        available.add("variants")
    if analysis.get("contacts_per_residue"):
        available.add("bfactor")

    # Check for AlphaMissense data (current query only)
    if _get_current_am_data():
        available.add("alphamissense")

    # Check for domain data (current query only)
    if _get_current_domain_data():
        available.add("domains")

    # New hidden-insight tracks — detected lazily from session state or computable
    if _get_surface_data():
        available.add("hydrophobicity")
        available.add("charge")
    if _get_disorder_data():
        available.add("disorder")
    if _get_conservation_data():
        available.add("conservation")
    if _get_pocket_data():
        available.add("pocket_score")
    if _get_depth_data():
        available.add("residue_depth")
    if analysis.get("ramachandran"):
        available.add("ramachandran")

    return available


# ---------------------------------------------------------------------------
# Insight generation
# ---------------------------------------------------------------------------


def _render_residue_insights(
    residue_ids: list[int],
    plddt_scores: list,
    structure_analysis: dict,
    mutation_pos: int | None,
    pathogenic_positions: dict[int, list[str]],
) -> None:
    """Auto-identify and display interesting per-residue patterns."""
    insights: list[str] = []

    sasa = structure_analysis.get("sasa_per_residue", {})
    sse = structure_analysis.get("sse_per_residue", {})
    packing = structure_analysis.get("packing_density", {})
    centrality = structure_analysis.get("network_centrality", {})
    hub_residues = structure_analysis.get("hub_residues", [])

    plddt_lookup: dict[int, float] = {}
    if plddt_scores:
        for i, rid in enumerate(residue_ids):
            if i < len(plddt_scores):
                plddt_lookup[rid] = plddt_scores[i]

    # --- Pattern 1: Disordered loops (low pLDDT + high SASA) ---
    disordered_runs = _find_runs(
        residue_ids,
        lambda r: plddt_lookup.get(r, 100) < 60 and sasa.get(r, 0) > 40,
        min_length=3,
    )
    for start, end in disordered_runs:
        avg_plddt = _avg([plddt_lookup.get(r, 0) for r in range(start, end + 1) if r in plddt_lookup])
        insights.append(
            f"**Residues {start}-{end}**: low pLDDT ({avg_plddt:.0f}) + high SASA "
            f"= likely **disordered loop**. Interpret structure with caution."
        )

    # --- Pattern 2: Buried mutation (low SASA at mutation site) ---
    if mutation_pos is not None and mutation_pos in sasa:
        mut_sasa_val = sasa[mutation_pos]
        mut_plddt_val = plddt_lookup.get(mutation_pos)
        ss_code = str(sse.get(mutation_pos, "c")).strip()
        ss_name = _SS_LABELS.get(ss_code, "coil")

        if mut_sasa_val < 15.0:
            insights.append(
                f"**Mutation site (res {mutation_pos})**: deeply buried "
                f"(SASA={mut_sasa_val:.1f} A^2) in {ss_name}. "
                "Mutations here likely destabilize the protein fold."
            )
        elif mut_sasa_val > 80.0:
            insights.append(
                f"**Mutation site (res {mutation_pos})**: highly exposed "
                f"(SASA={mut_sasa_val:.1f} A^2) in {ss_name}. "
                "May affect protein-protein interactions or surface binding."
            )

        if mut_plddt_val is not None and mut_plddt_val < 60:
            insights.append(
                f"**Mutation site (res {mutation_pos})**: low confidence "
                f"(pLDDT={mut_plddt_val:.1f}). The local structure prediction "
                "may not be reliable here."
            )

    # --- Pattern 3: Hub residue coincides with mutation or variant ---
    hub_set = {h["residue"] for h in hub_residues}
    if mutation_pos is not None and mutation_pos in hub_set:
        cent_val = centrality.get(mutation_pos, 0)
        insights.append(
            f"**Mutation site (res {mutation_pos})** is a **network hub** "
            f"(centrality={cent_val:.4f}). Disrupting this residue may propagate "
            "structural effects throughout the protein."
        )

    variant_hub_hits = [p for p in pathogenic_positions if p in hub_set]
    if variant_hub_hits:
        pos_str = ", ".join(str(p) for p in sorted(variant_hub_hits)[:5])
        insights.append(
            f"**{len(variant_hub_hits)} pathogenic variant(s)** coincide with network hub "
            f"residues ({pos_str}). These positions are structurally critical."
        )

    # --- Pattern 4: Dense packing near mutation ---
    if mutation_pos is not None and packing:
        mut_packing = packing.get(mutation_pos, 0)
        all_packing = list(packing.values())
        if all_packing:
            packing_pctile = sum(1 for v in all_packing if v <= mut_packing) / len(all_packing)
            if packing_pctile > 0.9:
                insights.append(
                    f"**Mutation site (res {mutation_pos})**: very densely packed "
                    f"({mut_packing} neighbors, top {100 - packing_pctile * 100:.0f}th percentile). "
                    "Limited space for side-chain changes -- conservative substitutions only."
                )

    # --- Pattern 5: Pathogenic variant clusters in low-confidence regions ---
    low_conf_variants = [
        p for p in pathogenic_positions
        if plddt_lookup.get(p, 100) < 60
    ]
    if low_conf_variants:
        pos_str = ", ".join(str(p) for p in sorted(low_conf_variants)[:5])
        insights.append(
            f"**{len(low_conf_variants)} pathogenic variant(s)** fall in low-confidence "
            f"regions (pLDDT < 60): {pos_str}. Structural impact assessment is uncertain."
        )

    # --- Pattern 6: Helix-to-coil transition near mutation ---
    if mutation_pos is not None and sse:
        nearby_ss = [
            str(sse.get(r, "c")).strip()
            for r in range(mutation_pos - 3, mutation_pos + 4)
            if r in sse
        ]
        unique_ss = set(nearby_ss)
        if len(unique_ss) >= 2 and "c" in unique_ss:
            ss_names = [_SS_LABELS.get(s, s) for s in unique_ss]
            insights.append(
                f"**Mutation site (res {mutation_pos})**: at a secondary structure "
                f"transition ({' / '.join(ss_names)}). Boundary residues are often "
                "sensitive to mutation."
            )

    # --- Pattern 7: PTM sites at key positions ---
    try:
        from src.ptm_analysis import predict_ptm_sites
        prediction = st.session_state.get("prediction_result")
        if prediction and prediction.pdb_content:
            ptm_sites = predict_ptm_sites(prediction.pdb_content)
            if ptm_sites:
                accessible = [p for p in ptm_sites if p.get("accessible", False)]
                ptm_at_mutation = [p for p in ptm_sites if mutation_pos and p.get("residue") == mutation_pos]
                if ptm_at_mutation:
                    ptm_type = ptm_at_mutation[0].get("type", "PTM")
                    insights.append(
                        f"**Mutation site (res {mutation_pos})** is a predicted **{ptm_type} site**. "
                        f"Mutation may abolish this post-translational modification."
                    )
                elif accessible:
                    types = set(p.get("type", "PTM") for p in accessible)
                    insights.append(
                        f"**{len(accessible)} accessible PTM site(s)** predicted "
                        f"({', '.join(types)}). These modifications regulate protein function "
                        f"and may be disrupted by nearby mutations."
                    )
    except (ImportError, Exception):
        pass

    # --- Pattern 8: High flexibility at conserved positions ---
    try:
        flexibility = structure_analysis.get("flexibility", {})
        if flexibility:
            _conservation = _get_conservation_data()
            cons_scores = _conservation.get("conservation_scores", {}) if _conservation else {}
            flex_conserved = [
                r for r in residue_ids
                if flexibility.get(r, 0) > 0.7 and cons_scores.get(r, 5) >= 7
            ]
            if flex_conserved:
                pos_str = ", ".join(str(r) for r in sorted(flex_conserved)[:5])
                insights.append(
                    f"**{len(flex_conserved)} residue(s)** are both highly flexible (ANM) "
                    f"and highly conserved ({pos_str}). These likely represent "
                    f"**functionally important dynamics** — conformational changes required for activity."
                )
    except Exception:
        pass

    # ---- Render ----
    if insights:
        st.markdown("#### Residue Insights")
        for insight in insights:
            st.info(insight)
    else:
        st.caption("No notable per-residue patterns detected.")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_mutation_pos(mutation: str | None) -> int | None:
    """Extract the numeric position from a mutation string like 'R248W'."""
    if not mutation:
        return None
    m = re.match(r"[A-Za-z](\d+)[A-Za-z]", mutation)
    if m:
        return int(m.group(1))
    # Try plain number
    m2 = re.match(r"(\d+)", mutation)
    if m2:
        return int(m2.group(1))
    return None


def _find_runs(
    residue_ids: list[int],
    predicate,
    min_length: int = 3,
) -> list[tuple[int, int]]:
    """Find contiguous runs of residues satisfying a predicate.

    Returns list of (start_resid, end_resid) tuples.
    """
    runs: list[tuple[int, int]] = []
    run_start: int | None = None
    prev_rid: int | None = None

    for rid in residue_ids:
        if predicate(rid):
            if run_start is None:
                run_start = rid
            elif prev_rid is not None and rid - prev_rid > 1:
                # Gap in residue numbering -- close previous run
                if prev_rid - run_start + 1 >= min_length:
                    runs.append((run_start, prev_rid))
                run_start = rid
        else:
            if run_start is not None and prev_rid is not None:
                if prev_rid - run_start + 1 >= min_length:
                    runs.append((run_start, prev_rid))
                run_start = None
        prev_rid = rid

    # Close last run
    if run_start is not None and prev_rid is not None:
        if prev_rid - run_start + 1 >= min_length:
            runs.append((run_start, prev_rid))

    return runs


def _avg(values: list[float]) -> float:
    """Mean of a list, returning 0.0 for empty lists."""
    return sum(values) / len(values) if values else 0.0
