"""Enhanced Nivo charts with draggable dashboard layout.

Uses streamlit-elements to provide:
- Nivo Radar: multi-dimensional protein risk assessment
- Nivo HeatMap: residue confidence matrix
- Nivo Bar: Tamarind pipeline completion status

Falls back gracefully if streamlit-elements is not installed.
"""
from __future__ import annotations

import streamlit as st

from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit

try:
    from streamlit_elements import dashboard, elements, mui, nivo

    NIVO_AVAILABLE = True
except ImportError:
    NIVO_AVAILABLE = False


# ---------------------------------------------------------------------------
# Dark theme applied to every Nivo chart
# ---------------------------------------------------------------------------

NIVO_LIGHT_THEME = {
    "background": "#F2F2F7",
    "textColor": "rgba(60,60,67,0.6)",
    "fontSize": 11,
    "axis": {
        "domain": {"line": {"stroke": "#C6C6C8", "strokeWidth": 1}},
        "ticks": {"line": {"stroke": "#C6C6C8"}},
        "legend": {"text": {"fill": "rgba(60,60,67,0.6)"}},
    },
    "grid": {"line": {"stroke": "#E5E5EA", "strokeWidth": 1}},
    "tooltip": {
        "container": {
            "background": "#F2F2F7",
            "color": "#000000",
            "fontSize": 12,
            "borderRadius": "12px",
            "border": "1px solid rgba(0,0,0,0.06)",
        }
    },
}


# ---------------------------------------------------------------------------
# Dimension computation — mirrors insight_visualizations._render_risk_radar
# ---------------------------------------------------------------------------


def _compute_radar_dimensions(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
) -> list[dict]:
    """Return the 6 radar-chart dimensions as a list of dicts.

    Calculation logic is identical to
    ``components/insight_visualizations._render_risk_radar`` (lines 49-169).
    """

    # 1. Structural Confidence (from trust audit)
    structural_conf = trust_audit.confidence_score * 100

    # 2. Prediction Reliability (based on limitations count)
    lim_count = len(trust_audit.known_limitations)
    reliability = max(0, 100 - lim_count * 15)

    # 3. Clinical Significance (from disease associations)
    clinical_sig = 0.0
    if bio_context and bio_context.disease_associations:
        scores = [
            d.score
            for d in bio_context.disease_associations
            if d.score is not None
        ]
        if scores:
            clinical_sig = min(100, (sum(scores) / max(len(scores), 1)) * 100)
        else:
            clinical_sig = min(100, len(bio_context.disease_associations) * 20)

    # 4. Druggability (from drugs in pipeline)
    druggability = 0.0
    if bio_context and bio_context.drugs:
        phase_scores = {
            "approved": 100,
            "phase iii": 85,
            "phase ii": 65,
            "phase i": 45,
            "preclinical": 25,
        }
        for drug in bio_context.drugs:
            phase = (drug.phase or "").lower()
            matched = False
            for key, score in phase_scores.items():
                if key in phase:
                    druggability = max(druggability, score)
                    matched = True
                    break
            if not matched:
                druggability = max(druggability, 20)

    # 5. Mutation Burden (from variant data)
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    mutation_burden = 0.0
    if variant_data:
        path_count = variant_data.get("pathogenic_count", 0)
        mutation_burden = min(100, path_count * 12)

    # 6. Literature Coverage (from literature data)
    lit_coverage = 0.0
    if bio_context and bio_context.literature.total_papers > 0:
        lit_coverage = min(100, bio_context.literature.total_papers * 0.7)

    return [
        {"dimension": "Structural Confidence", "score": round(structural_conf, 1)},
        {"dimension": "Prediction Reliability", "score": round(reliability, 1)},
        {"dimension": "Clinical Significance", "score": round(clinical_sig, 1)},
        {"dimension": "Druggability", "score": round(druggability, 1)},
        {"dimension": "Mutation Burden", "score": round(mutation_burden, 1)},
        {"dimension": "Literature Coverage", "score": round(lit_coverage, 1)},
    ]


# ---------------------------------------------------------------------------
# Heatmap data builder
# ---------------------------------------------------------------------------


def _build_heatmap_data(
    prediction: PredictionResult,
) -> list[dict] | None:
    """Build a confidence proximity heatmap from pLDDT scores.

    Subsamples to max 30 residues for rendering performance.
    Returns ``None`` when there is insufficient data.
    """
    plddt = prediction.plddt_per_residue
    res_ids = prediction.residue_ids

    if not plddt or not res_ids or len(plddt) < 5:
        return None

    # Subsample to at most 30 residues
    step = max(1, len(plddt) // 30)
    sampled_idx = list(range(0, len(plddt), step))[:30]

    data = []
    for i in sampled_idx:
        row: dict = {"id": f"R{res_ids[i]}"}
        row_data = []
        for j in sampled_idx:
            # Confidence correlation: min of both residues' pLDDT
            val = min(plddt[i], plddt[j])
            row_data.append({"x": f"R{res_ids[j]}", "y": round(val, 1)})
        row["data"] = row_data
        data.append(row)
    return data


# ---------------------------------------------------------------------------
# Pipeline bar chart data builder
# ---------------------------------------------------------------------------


def _build_pipeline_data() -> list[dict] | None:
    """Build horizontal bar data from Tamarind pipeline results in session state."""
    results = st.session_state.get("tamarind_results", {})
    if not results:
        return None

    data = []
    for tool_name, result in results.items():
        status = "error" if isinstance(result, dict) and result.get("type") == "error" else "complete"
        data.append(
            {
                "tool": tool_name,
                "complete": 100 if status == "complete" else 0,
                "error": 100 if status == "error" else 0,
            }
        )
    return data if data else None


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------


def render_nivo_dashboard(
    query: ProteinQuery,
    prediction: PredictionResult | None,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
) -> None:
    """Render the draggable Nivo dashboard with Radar, HeatMap, and Pipeline charts.

    Degrades gracefully:
    - If ``streamlit-elements`` is not installed, returns immediately.
    - Individual chart sections are skipped when their data is unavailable.
    - Runtime errors are caught so the rest of the app is unaffected.
    """
    if not NIVO_AVAILABLE:
        return

    if not trust_audit or not prediction:
        return

    try:
        _render_dashboard_inner(query, prediction, trust_audit, bio_context)
    except Exception:
        # Nivo / streamlit-elements runtime error — fall back silently
        pass


def _render_dashboard_inner(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
) -> None:
    """Inner implementation — separated so the outer function can catch errors."""

    # Pre-compute data for each panel
    radar_data = _compute_radar_dimensions(query, trust_audit, bio_context)
    heatmap_data = _build_heatmap_data(prediction)
    pipeline_data = _build_pipeline_data()

    # Build dashboard layout
    layout = [
        dashboard.Item("radar", 0, 0, 6, 4),
    ]
    if heatmap_data is not None:
        layout.append(dashboard.Item("heatmap", 6, 0, 6, 4))
    if pipeline_data is not None:
        layout.append(dashboard.Item("pipeline", 0, 4, 12, 3))

    with elements("nivo_dashboard"):
        with dashboard.Grid(layout, draggableHandle=".drag-handle"):
            # ---- Radar Chart ----
            with mui.Card(
                key="radar",
                sx={
                    "background": "#F2F2F7",
                    "border": "1px solid rgba(0,0,0,0.08)",
                    "borderRadius": "12px",
                    "display": "flex",
                    "flexDirection": "column",
                    "height": "100%",
                },
            ):
                mui.CardHeader(
                    title="Protein Risk Radar",
                    className="drag-handle",
                    sx={
                        "color": "#000000",
                        "cursor": "grab",
                        "padding": "8px 16px",
                        "& .MuiCardHeader-title": {"fontSize": "0.95rem"},
                    },
                )
                with mui.CardContent(
                    sx={"flex": 1, "padding": "0 8px", "&:last-child": {"paddingBottom": "8px"}}
                ):
                    nivo.Radar(
                        data=radar_data,
                        keys=["score"],
                        indexBy="dimension",
                        maxValue=100,
                        margin={"top": 40, "right": 60, "bottom": 40, "left": 60},
                        borderColor={"from": "color"},
                        gridLabelOffset=16,
                        dotSize=8,
                        dotColor={"theme": "background"},
                        dotBorderWidth=2,
                        colors=["#007AFF"],
                        fillOpacity=0.25,
                        blendMode="normal",
                        theme=NIVO_LIGHT_THEME,
                    )

            # ---- HeatMap Chart ----
            if heatmap_data is not None:
                with mui.Card(
                    key="heatmap",
                    sx={
                        "background": "#F2F2F7",
                        "border": "1px solid rgba(0,0,0,0.08)",
                        "borderRadius": "12px",
                        "display": "flex",
                        "flexDirection": "column",
                        "height": "100%",
                    },
                ):
                    mui.CardHeader(
                        title="Confidence Proximity Matrix",
                        className="drag-handle",
                        sx={
                            "color": "#000000",
                            "cursor": "grab",
                            "padding": "8px 16px",
                            "& .MuiCardHeader-title": {"fontSize": "0.95rem"},
                        },
                    )
                    with mui.CardContent(
                        sx={"flex": 1, "padding": "0 8px", "&:last-child": {"paddingBottom": "8px"}}
                    ):
                        nivo.HeatMap(
                            data=heatmap_data,
                            margin={"top": 40, "right": 20, "bottom": 40, "left": 60},
                            axisTop={
                                "tickSize": 0,
                                "tickPadding": 5,
                                "tickRotation": -45,
                            },
                            axisLeft={
                                "tickSize": 0,
                                "tickPadding": 5,
                            },
                            colors={
                                "type": "diverging",
                                "scheme": "blue_green",
                                "minValue": 0,
                                "maxValue": 100,
                            },
                            emptyColor="#F2F2F7",
                            borderWidth=1,
                            borderColor="#E5E5EA",
                            theme=NIVO_LIGHT_THEME,
                            hoverTarget="cell",
                            cellOpacity=1,
                            cellHoverOthersOpacity=0.5,
                        )

            # ---- Pipeline Bar Chart ----
            if pipeline_data is not None:
                with mui.Card(
                    key="pipeline",
                    sx={
                        "background": "#F2F2F7",
                        "border": "1px solid rgba(0,0,0,0.08)",
                        "borderRadius": "12px",
                        "display": "flex",
                        "flexDirection": "column",
                        "height": "100%",
                    },
                ):
                    mui.CardHeader(
                        title="Tamarind Pipeline Status",
                        className="drag-handle",
                        sx={
                            "color": "#000000",
                            "cursor": "grab",
                            "padding": "8px 16px",
                            "& .MuiCardHeader-title": {"fontSize": "0.95rem"},
                        },
                    )
                    with mui.CardContent(
                        sx={"flex": 1, "padding": "0 8px", "&:last-child": {"paddingBottom": "8px"}}
                    ):
                        nivo.Bar(
                            data=pipeline_data,
                            keys=["complete", "error"],
                            indexBy="tool",
                            layout="horizontal",
                            margin={"top": 10, "right": 40, "bottom": 30, "left": 140},
                            padding=0.3,
                            colors=["#34C759", "#FF3B30"],
                            borderRadius=4,
                            axisLeft={
                                "tickSize": 0,
                                "tickPadding": 8,
                            },
                            axisBottom={
                                "tickSize": 0,
                                "tickPadding": 5,
                                "legend": "Completion %",
                                "legendPosition": "middle",
                                "legendOffset": 24,
                            },
                            enableLabel=False,
                            theme=NIVO_LIGHT_THEME,
                        )
