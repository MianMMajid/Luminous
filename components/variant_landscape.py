"""Variant pathogenicity landscape visualization.

Maps ClinVar/OncoKB variant data onto the protein structure,
bridging the gap that AlphaFold DB 2025 started but didn't complete:
connecting structure prediction to clinical variant interpretation.
"""
from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.models import PredictionResult, ProteinQuery


def _enrich_variants_background(protein_name: str, positions: list[int]) -> dict:
    """Run variant enrichment in a background thread (no st.* calls)."""
    from src.variant_enrichment import enrich_variants
    return enrich_variants(protein_name, positions)


def render_variant_landscape(query: ProteinQuery, prediction: PredictionResult):
    """Render the variant pathogenicity landscape panel."""
    st.markdown("#### Variant Pathogenicity Landscape")
    # Query-aware caption explaining WHY variants matter for this question
    if query.question_type == "druggability" and query.mutation:
        caption = (
            f"Known pathogenic variants near **{query.mutation}** — resistance mutations "
            "at drug-binding positions can alter therapeutic response."
        )
    elif query.mutation:
        caption = (
            f"How does **{query.mutation}** compare to other known pathogenic variants? "
            "ClinVar/OncoKB data mapped onto the predicted structure."
        )
    else:
        caption = (
            "Known pathogenic variants from ClinVar/OncoKB mapped onto the structure. "
            "Connects AI structure prediction to clinical variant interpretation."
        )
    st.caption(caption)

    cache_key = f"variant_data_{query.protein_name}"
    variant_data = st.session_state.get(cache_key)

    attempt_key = f"_variant_fetch_attempted_{query.protein_name}"

    if variant_data is None and not st.session_state.get(attempt_key, False):
        st.session_state[attempt_key] = True
        from src.task_manager import task_manager
        from src.variant_analyzer import fetch_variant_landscape

        def _fetch(q):
            return {"variant_data": fetch_variant_landscape(q), "cache_key": cache_key}

        task_manager.submit(
            "variant_landscape",
            _fetch,
            args=(query,),
            label="Querying ClinVar & OncoKB",
        )

    # Check if background task is running
    from src.task_manager import task_manager as _tm
    vl_status = _tm.status("variant_landscape")
    if vl_status and vl_status.value == "running":
        st.info("Querying ClinVar & OncoKB in the background...")
        return

    # Pick up completed result
    vl_result = _tm.get_result("variant_landscape")
    if vl_result and variant_data is None:
        variant_data = vl_result.get("variant_data")
        ck = vl_result.get("cache_key", cache_key)
        st.session_state[ck] = variant_data

    if variant_data is None:
        if st.button("Retry Variant Analysis", key="var_fetch", type="primary"):
            st.session_state[attempt_key] = False
        else:
            st.info(
                f"Auto-fetch for {query.protein_name} variants did not return data. "
                "Click above to retry."
            )
            return

    if not isinstance(variant_data, dict) or not variant_data.get("variants"):
        st.info(variant_data.get("summary", "No variant data found."))
        return

    # Enrich variants with myvariant.info (CADD, gnomAD, SIFT, PolyPhen-2, etc.)
    # Runs in background to avoid blocking render with paginated HTTP calls
    enrichment_key = f"variant_enrichment_{query.protein_name}"
    if st.session_state.get(enrichment_key) is None:
        from src.task_manager import task_manager

        enrich_task_id = f"variant_enrichment_{query.protein_name}"
        enrich_status = task_manager.status(enrich_task_id)
        if not enrich_status or enrich_status.value not in ("pending", "running"):
            positions = [v.get("position") for v in variant_data.get("variants", []) if v.get("position")]
            positions = [int(p) for p in positions if p is not None]
            if positions:
                task_manager.submit(
                    task_id=enrich_task_id,
                    fn=_enrich_variants_background,
                    args=(query.protein_name, positions),
                    label="Enriching variants (CADD, gnomAD, SIFT)",
                    target_keys={"__direct__": enrichment_key},
                )
    else:
        # Merge enrichment data into variants if available
        enrichment = st.session_state.get(enrichment_key)
        if isinstance(enrichment, dict):
            enriched = enrichment.get("enriched", {})
            if enriched:
                for v in variant_data.get("variants", []):
                    pos = v.get("position")
                    if pos and int(pos) in enriched:
                        edata = enriched[int(pos)]
                        for src_key, dst_key in [
                            ("cadd_phred", "cadd_score"),
                            ("gnomad_af", "frequency"),
                            ("clinvar_significance", "significance"),
                            ("sift_pred", "sift_pred"),
                            ("polyphen2_pred", "polyphen2_pred"),
                            ("revel_score", "revel_score"),
                            ("cosmic_id", "cosmic_id"),
                        ]:
                            if src_key in edata and not v.get(dst_key):
                                v[dst_key] = edata[src_key]

    # Summary metrics
    _render_variant_summary(variant_data)

    # Severity scatter (CADD vs frequency "money chart")
    _render_variant_severity_scatter(variant_data)

    # --- Interactive filters ---
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        sig_options = ["All", "Pathogenic", "Likely Pathogenic"]
        sig_filter = st.selectbox(
            "Filter by significance",
            sig_options,
            index=0,
            key="variant_sig_filter",
            help="ClinVar clinical significance categories. 'Pathogenic' variants are confirmed disease-causing.",
        )
    with filter_col2:
        plddt_range = st.slider(
            "pLDDT range to highlight",
            min_value=0, max_value=100, value=(0, 100), step=5,
            key="variant_plddt_range",
            help="pLDDT is per-residue confidence (0-100). Filter to show only variants in regions with this confidence range. >70 is generally reliable.",
        )

    # Apply filters
    filtered_data = _apply_variant_filters(variant_data, sig_filter, plddt_range, prediction)

    # Variant-structure overlay chart
    _render_variant_structure_chart(query, prediction, filtered_data, plddt_range)

    # Lollipop variant plot (ProteinPaint-style)
    _render_lollipop_plot(query, prediction, filtered_data)

    # Variant table
    _render_variant_table(filtered_data)

    # Enrichment source badge
    enrichment = st.session_state.get(f"variant_enrichment_{query.protein_name}")
    if enrichment and enrichment.get("sources"):
        sources = enrichment["sources"]
        n_enriched = enrichment.get("n_enriched", 0)
        badge_parts = " ".join(
            f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);'
            f'padding:1px 6px;border-radius:10px;font-size:0.7em;'
            f'color:rgba(60,60,67,0.55)">{s}</span>'
            for s in sources
        )
        st.markdown(
            f'<div style="margin-top:4px">'
            f'<span style="font-size:0.75em;color:rgba(60,60,67,0.45)">'
            f'Enriched {n_enriched} positions via myvariant.info: </span>{badge_parts}</div>',
            unsafe_allow_html=True,
        )

    # Store for hypothesis engine
    return variant_data


def _apply_variant_filters(
    variant_data: dict,
    sig_filter: str,
    plddt_range: tuple[int, int],
    prediction: PredictionResult,
) -> dict:
    """Apply user-selected filters to variant data, returning a filtered copy."""
    if sig_filter == "All" and plddt_range == (0, 100):
        return variant_data  # No filtering needed

    variants = variant_data.get("variants", [])
    filtered_variants = []

    # Build residue->plddt lookup (first chain only)
    plddt_map: dict[int, float] = {}
    if prediction.residue_ids and prediction.plddt_per_residue:
        chain_ids = prediction.chain_ids or []
        first_chain = chain_ids[0] if chain_ids else None
        for i, (rid, sc) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
            if chain_ids and i >= len(chain_ids):
                break
            if first_chain is None or (i < len(chain_ids) and chain_ids[i] == first_chain):
                plddt_map[rid] = sc

    for v in variants:
        # Significance filter
        sig = v.get("significance", "").lower().replace(" ", "_")
        if sig_filter == "Pathogenic" and sig != "pathogenic":
            continue
        if sig_filter == "Likely Pathogenic" and sig not in ("pathogenic", "likely_pathogenic"):
            continue

        # pLDDT range filter
        pos = v.get("position")
        if pos is not None and pos in plddt_map:
            sc = plddt_map[pos]
            if not (plddt_range[0] <= sc <= plddt_range[1]):
                continue

        filtered_variants.append(v)

    # Rebuild pathogenic_positions from filtered variants
    filtered_positions: dict[str, list[str]] = {}
    for v in filtered_variants:
        sig = v.get("significance", "").lower().replace(" ", "_")
        if sig in ("pathogenic", "likely_pathogenic"):
            pos_key = str(v.get("position", ""))
            if pos_key:
                filtered_positions.setdefault(pos_key, []).append(v.get("name", "?"))

    return {
        "variants": filtered_variants,
        "pathogenic_positions": filtered_positions,
        "total": len(filtered_variants),
        "pathogenic_count": sum(1 for v in filtered_variants if v.get("significance", "").lower() == "pathogenic"),
        "likely_pathogenic_count": sum(1 for v in filtered_variants if "likely_pathogenic" in v.get("significance", "").lower().replace(" ", "_")),
        "summary": variant_data.get("summary", ""),
    }


def _render_variant_severity_scatter(variant_data: dict):
    """Scatter plot of CADD pathogenicity score vs allele frequency — the 'money chart'."""
    variants = variant_data.get("variants", [])
    if not variants:
        return

    st.markdown("#### Variant Severity Landscape")

    # Gather pLDDT data from prediction result if available
    plddt_map: dict[int, float] = {}
    pred = st.session_state.get("prediction_result")
    if pred and hasattr(pred, "residue_ids") and hasattr(pred, "plddt_per_residue"):
        if pred.residue_ids and pred.plddt_per_residue:
            first_chain = pred.chain_ids[0] if getattr(pred, "chain_ids", None) else None
            for i, (rid, sc) in enumerate(zip(pred.residue_ids, pred.plddt_per_residue)):
                if i >= len(pred.chain_ids):
                    break
                if first_chain is None or pred.chain_ids[i] == first_chain:
                    plddt_map[rid] = sc

    # ClinVar standard: red=pathogenic, orange=likely path, blue=VUS, green=benign
    _SIG_COLORS = {
        "pathogenic": "#E00000",
        "likely_pathogenic": "#E07000",
        "uncertain_significance": "#2563EB",
        "likely_benign": "#4ADE80",
        "benign": "#16A34A",
    }
    # Distinct marker shapes for colorblind accessibility
    _SIG_SHAPES = {
        "pathogenic": "circle",
        "likely_pathogenic": "diamond",
        "uncertain_significance": "square",
        "likely_benign": "triangle-up",
        "benign": "pentagon",
    }

    xs, ys, sizes, colors, hovers, sigs_seen = [], [], [], [], [], []
    freq_defaulted_count = 0

    for v in variants:
        cadd = v.get("cadd_score")
        freq = v.get("frequency")
        pos = v.get("position")
        sig = v.get("significance", "unknown")
        name = v.get("name", "?")

        # Need at least one of CADD or frequency
        if cadd is None and freq is None:
            continue
        # Must have CADD score to appear on scatter
        if cadd is None:
            continue

        if freq is None:
            freq = 1e-5
            freq_defaulted_count += 1

        sig_key = sig.lower().replace(" ", "_")
        color = _SIG_COLORS.get(sig_key, "#888888")

        # Bubble size from pLDDT
        if pos is not None and pos in plddt_map:
            bubble = max(5, plddt_map[pos] / 10)
        else:
            bubble = 10

        freq_display = f"{freq:.2e}" if freq < 0.001 else f"{freq:.4f}"
        hover = (
            f"<b>{name}</b><br>"
            f"Position: {pos}<br>"
            f"CADD: {cadd:.1f}<br>"
            f"Frequency: {freq_display}<br>"
            f"Significance: {sig.replace('_', ' ').title()}"
        )

        xs.append(freq)
        ys.append(cadd)
        sizes.append(bubble)
        colors.append(color)
        hovers.append(hover)
        sigs_seen.append(sig_key)

    if not xs:
        st.info(
            "No CADD pathogenicity scores available for these variants. "
            "CADD scores quantify variant deleteriousness on a 0-40 scale."
        )
        return

    fig = go.Figure()

    # Group by significance so legend shows each category
    unique_sigs = list(dict.fromkeys(sigs_seen))  # preserve order, dedupe
    for sig_key in unique_sigs:
        idx = [i for i, s in enumerate(sigs_seen) if s == sig_key]
        fig.add_trace(go.Scatter(
            x=[xs[i] for i in idx],
            y=[ys[i] for i in idx],
            mode="markers",
            name=sig_key.replace("_", " ").title(),
            marker=dict(
                color=_SIG_COLORS.get(sig_key, "#888888"),
                symbol=_SIG_SHAPES.get(sig_key, "circle"),
                size=[sizes[i] for i in idx],
                line=dict(color="rgba(0,0,0,0.15)", width=0.5),
                opacity=0.85,
            ),
            text=[hovers[i] for i in idx],
            hovertemplate="%{text}<extra></extra>",
        ))

    # Reference lines
    fig.add_hline(y=20, line_dash="dash", line_color="#FF6B6B",
                  annotation_text="Likely deleterious", annotation_position="right",
                  annotation_font_color="#FF6B6B")
    fig.add_hline(y=15, line_dash="dash", line_color="#FF9500",
                  annotation_text="Possibly deleterious", annotation_position="right",
                  annotation_font_color="#FF9500")
    fig.add_vline(x=0.01, line_dash="dash", line_color="#888",
                  annotation_text="Common (>1%)", annotation_position="top",
                  annotation_font_color="#888")

    fig.update_layout(
        xaxis_title="Allele Frequency (gnomAD)",
        yaxis_title="CADD Pathogenicity Score",
        xaxis_type="log",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=400,
        margin=dict(t=30, b=50, l=50, r=80),
        legend=dict(yanchor="bottom", y=0.02, xanchor="left", x=0.02,
                    bgcolor="rgba(242,242,247,0.95)"),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    selection = st.plotly_chart(
        fig, width="stretch", key="variant_severity_scatter",
        on_select="rerun",
    )

    # Capture selected points for cross-filtering
    if selection and selection.get("selection", {}).get("points"):
        sel_points = selection["selection"]["points"]
        # Store selected variant positions
        sel_positions = set()
        for pt in sel_points:
            hover = pt.get("text", "")
            if "Position:" in hover:
                import re
                pos_match = re.search(r"Position:\s*(\d+)", hover)
                if pos_match:
                    sel_positions.add(int(pos_match.group(1)))
        if sel_positions:
            st.session_state["selected_residues"] = sorted(sel_positions)

    st.caption(
        "CADD pathogenicity score vs population frequency — ultra-rare + high CADD "
        "= strongest pathogenic signal. Bubble size reflects structural prediction "
        "confidence (pLDDT). Select points to cross-filter with other panels."
    )

    if freq_defaulted_count:
        st.caption(
            f"Note: {freq_defaulted_count} variant(s) had no gnomAD frequency data "
            "and were plotted at AF=1e-5."
        )

    st.markdown(
        '<div style="margin-top:2px">'
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">CADD: Phred-scaled pathogenicity</span> '
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">gnomAD: Population frequency</span> '
        '<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:1px 6px;border-radius:10px;font-size:0.7em;color:rgba(60,60,67,0.55)">Boltz-2: Structural confidence (bubble size)</span>'
        '</div>',
        unsafe_allow_html=True,
    )


def _render_variant_summary(variant_data: dict):
    """Show summary metrics for variants."""
    cols = st.columns(4)
    cols[0].metric("Total Variants", variant_data.get("total", 0))
    cols[1].metric("Pathogenic", variant_data.get("pathogenic_count", 0))
    cols[2].metric("Likely Pathogenic", variant_data.get("likely_pathogenic_count", 0))
    cols[3].metric(
        "Hotspot Positions",
        len(variant_data.get("pathogenic_positions", {})),
    )
    st.markdown(variant_data.get("summary", ""))


def _render_variant_structure_chart(
    query: ProteinQuery,
    prediction: PredictionResult,
    variant_data: dict,
    plddt_range: tuple[int, int] = (0, 100),
):
    """Overlay variant pathogenicity onto pLDDT confidence profile."""
    if not prediction.plddt_per_residue or not prediction.residue_ids:
        return

    pathogenic_pos = variant_data.get("pathogenic_positions", {})

    # Use first chain only
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
    res_ids = []
    scores = []
    for i, (rid, sc) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
        if i >= len(prediction.chain_ids):
            break
        if first_chain is None or prediction.chain_ids[i] == first_chain:
            res_ids.append(rid)
            scores.append(sc)

    if not res_ids:
        return

    fig = go.Figure()

    # Highlight the active pLDDT range with shading
    if plddt_range != (0, 100):
        fig.add_hrect(
            y0=plddt_range[0], y1=plddt_range[1],
            fillcolor="rgba(10, 132, 255, 0.08)",
            line_width=0,
        )

    # pLDDT trace (dim residues outside the range)
    in_range_colors = [
        "#007AFF" if plddt_range[0] <= sc <= plddt_range[1] else "rgba(10,132,255,0.2)"
        for sc in scores
    ]
    fig.add_trace(go.Bar(
        x=res_ids,
        y=scores,
        marker_color=in_range_colors,
        name="pLDDT Confidence",
        hovertemplate="Res %{x}<br>pLDDT: %{y:.1f}<extra></extra>",
    ))

    # Pathogenic variant markers (only filtered ones)
    path_x, path_y, path_text = [], [], []
    for pos_str, names in pathogenic_pos.items():
        try:
            pos = int(pos_str)
        except (ValueError, TypeError):
            continue
        if pos in res_ids:
            idx = res_ids.index(pos)
            path_x.append(pos)
            path_y.append(scores[idx])
            path_text.append(f"Pathogenic: {', '.join(names) if isinstance(names, list) else names}")

    if path_x:
        fig.add_trace(go.Scatter(
            x=path_x,
            y=path_y,
            mode="markers",
            name="Pathogenic Variants",
            marker=dict(
                color="#E00000",
                size=10,
                symbol="diamond",
                line=dict(color="white", width=1),
            ),
            text=path_text,
            hovertemplate="Res %{x}<br>pLDDT: %{y:.1f}<br>%{text}<extra></extra>",
        ))

    # Mark the queried mutation
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in res_ids:
                idx = res_ids.index(mut_pos)
                fig.add_trace(go.Scatter(
                    x=[mut_pos],
                    y=[scores[idx]],
                    mode="markers",
                    name=f"Query: {query.mutation}",
                    marker=dict(
                        color="#FFCC00",
                        size=14,
                        symbol="star",
                        line=dict(color="#FF3B30", width=2),
                    ),
                    hovertemplate=f"{query.mutation}<br>Res %{{x}}<br>pLDDT: %{{y:.1f}}<extra></extra>",
                ))

    # Threshold lines
    fig.add_hline(y=70, line_dash="dash", line_color="#65CBF3",
                  annotation_text="High confidence", annotation_position="right")
    fig.add_hline(y=50, line_dash="dash", line_color="#FFDB13",
                  annotation_text="Low confidence", annotation_position="right")

    fig.update_layout(
        xaxis_title="Residue Position",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 105],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin=dict(t=30, b=50, l=50, r=80),
        legend=dict(yanchor="bottom", y=0.02, xanchor="left", x=0.02,
                    bgcolor="rgba(242,242,247,0.95)"),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, width="stretch", key="variant_structure_chart")

    # Dynamic summary
    if path_x:
        below_70 = sum(1 for y in path_y if y < 70)
        if below_70 > 0:
            st.caption(
                f"{below_70}/{len(path_x)} filtered pathogenic sites have pLDDT < 70 "
                f"— predictions at these clinically important positions may be unreliable."
            )


def _render_variant_table(variant_data: dict):
    """Show variant details in an expandable table."""
    variants = variant_data.get("variants", [])
    if not variants:
        return

    # ClinVar standard: red=pathogenic, orange=likely path, blue=VUS, green=benign
    _SIG_COLORS = {
        "pathogenic": "#E00000",
        "likely_pathogenic": "#E07000",
        "uncertain_significance": "#2563EB",
        "likely_benign": "#4ADE80",
        "benign": "#16A34A",
    }
    _SIG_LABELS = {
        "pathogenic": "Pathogenic",
        "likely_pathogenic": "Likely Path.",
        "uncertain_significance": "VUS",
        "likely_benign": "Likely Benign",
        "benign": "Benign",
    }

    with st.expander(f"Variant Details ({len(variants)} variants)", expanded=False):
        for v in variants[:20]:
            sig = v.get("significance", "unknown")
            sig_color = _SIG_COLORS.get(sig, "#888")
            disease = v.get("disease", "")
            disease_str = f'<span style="color:rgba(60,60,67,0.6);font-size:0.82em"> | {disease}</span>' if disease else ""
            sig_label = _SIG_LABELS.get(sig, sig.replace("_", " ").title())

            cadd = v.get("cadd_score")
            cadd_str = f' <span style="background:#F2F2F7;border:1px solid rgba(255,159,10,0.3);padding:0 4px;border-radius:4px;font-size:0.78em;color:#FF9500">CADD: {cadd:.1f}</span>' if cadd is not None else ""
            freq = v.get("frequency")
            if freq is not None:
                if freq < 0.001:
                    freq_label = f"{freq:.2e}"
                else:
                    freq_label = f"{freq:.4f}"
                freq_str = f' <span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:0 4px;border-radius:4px;font-size:0.78em;color:rgba(60,60,67,0.55)">AF: {freq_label}</span>'
            else:
                freq_str = ""

            # Enrichment annotations (from myvariant.info)
            enrich_parts = []
            if v.get("sift_pred"):
                sift_color = "#E00000" if v["sift_pred"] == "D" else "#34C759"
                sift_label = "Damaging" if v["sift_pred"] == "D" else "Tolerated"
                enrich_parts.append(f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:0 4px;border-radius:4px;font-size:0.78em;color:{sift_color}">SIFT: {sift_label}</span>')
            if v.get("polyphen2_pred"):
                pp2_map = {"D": ("Damaging", "#E00000"), "P": ("Possibly Dam.", "#FF9500"), "B": ("Benign", "#34C759")}
                pp2_label, pp2_color = pp2_map.get(v["polyphen2_pred"], (v["polyphen2_pred"], "#888"))
                enrich_parts.append(f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:0 4px;border-radius:4px;font-size:0.78em;color:{pp2_color}">PP2: {pp2_label}</span>')
            if v.get("revel_score") is not None:
                revel_color = "#E00000" if v["revel_score"] > 0.5 else "#34C759"
                enrich_parts.append(f'<span style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.06);padding:0 4px;border-radius:4px;font-size:0.78em;color:{revel_color}">REVEL: {v["revel_score"]:.2f}</span>')
            if v.get("cosmic_id"):
                enrich_parts.append(f'<span style="background:#F2F2F7;border:1px solid rgba(175,82,222,0.3);padding:0 4px;border-radius:4px;font-size:0.78em;color:#AF52DE">COSMIC</span>')
            enrich_str = " ".join(enrich_parts)
            if enrich_str:
                enrich_str = " " + enrich_str

            st.markdown(
                f'<div style="padding:6px 10px;border-left:3px solid {sig_color};'
                f'background:rgba(242,242,247,0.6);border-radius:0 6px 6px 0;margin-bottom:4px">'
                f'<span style="font-weight:600">{v.get("name", "?")}</span>'
                f' <span style="color:rgba(60,60,67,0.6);font-size:0.85em">pos {v.get("position", "?")}</span>'
                f' <span style="color:{sig_color};font-size:0.82em;font-weight:600">'
                f'{sig_label}</span>{disease_str}{cadd_str}{freq_str}{enrich_str}</div>',
                unsafe_allow_html=True,
            )


def _render_lollipop_plot(
    query: ProteinQuery,
    prediction: PredictionResult,
    variant_data: dict,
):
    """ProteinPaint-style lollipop diagram — the gold standard for clinical variant visualization.

    Each variant is a circle on a stick at its protein position. Height = CADD score
    (severity), color = clinical significance, size = allele frequency (if available).
    Domain annotations run as colored bars underneath.
    """
    variants = variant_data.get("variants", [])
    if not variants:
        return

    # Parse positions and scores
    positions = []
    heights = []
    colors = []
    labels = []
    sizes = []

    _SIG_COLORS = {
        "pathogenic": "#FF3B30",
        "likely_pathogenic": "#FF9500",
        "uncertain_significance": "#8E8E93",
        "likely_benign": "#34C759",
        "benign": "#007AFF",
    }

    for v in variants:
        pos = v.get("position")
        if pos is None:
            continue
        try:
            pos = int(pos)
        except (ValueError, TypeError):
            continue

        cadd = v.get("cadd_score", v.get("score", 15))
        if cadd is None:
            cadd = 15
        try:
            cadd = float(cadd)
        except (ValueError, TypeError):
            cadd = 15

        sig = v.get("significance", "").lower().replace(" ", "_")
        color = _SIG_COLORS.get(sig, "#8E8E93")

        freq = v.get("allele_frequency", 0.01)
        try:
            freq = float(freq) if freq else 0.01
        except (ValueError, TypeError):
            freq = 0.01
        # Size: rarer variants = bigger dots (more noteworthy)
        import math
        dot_size = max(6, min(18, 8 + 3 * (-math.log10(freq + 1e-6) if freq > 0 else 5)))

        name = v.get("name", f"pos {pos}")
        positions.append(pos)
        heights.append(cadd)
        colors.append(color)
        sizes.append(dot_size)
        labels.append(name)

    if not positions:
        return

    st.markdown("##### Variant Lollipop Diagram")

    fig = go.Figure()

    # Domain bars at bottom (if we have domain data)
    domains = st.session_state.get(f"domains_{query.protein_name}", [])
    if domains and isinstance(domains, list):
        _DOMAIN_COLORS = [
            "#007AFF", "#34C759", "#FF9500", "#AF52DE",
            "#FF2D55", "#5856D6", "#30B0C7", "#FF6482",
        ]
        for idx, d in enumerate(domains):
            d_start = d.get("start", 0)
            d_end = d.get("end", 0)
            d_name = d.get("name", "")
            d_color = _DOMAIN_COLORS[idx % len(_DOMAIN_COLORS)]
            fig.add_trace(go.Bar(
                x=[d_end - d_start],
                y=[-2],
                base=d_start,
                orientation="h",
                marker_color=d_color,
                marker_line_color="white",
                marker_line_width=0.5,
                showlegend=False,
                hovertemplate=f"<b>{d_name}</b><br>Res {d_start}-{d_end}<extra></extra>",
                width=3,
            ))
            # Domain label
            mid = (d_start + d_end) / 2
            fig.add_annotation(
                x=mid, y=-2, text=d_name[:15],
                showarrow=False, font=dict(size=8, color="white"),
            )

    # Protein backbone line
    max_res = max(prediction.residue_ids) if prediction.residue_ids else max(positions)
    fig.add_trace(go.Scatter(
        x=[0, max_res],
        y=[0, 0],
        mode="lines",
        line=dict(color="rgba(0,0,0,0.3)", width=3),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Lollipop stems
    for pos, h in zip(positions, heights):
        fig.add_trace(go.Scatter(
            x=[pos, pos],
            y=[0, h],
            mode="lines",
            line=dict(color="rgba(0,0,0,0.15)", width=1),
            showlegend=False,
            hoverinfo="skip",
        ))

    # Lollipop heads — group by significance for legend
    sig_groups = {}
    for i, (pos, h, col, sz, lbl) in enumerate(zip(positions, heights, colors, sizes, labels)):
        sig = next((k for k, v in _SIG_COLORS.items() if v == col), "other")
        if sig not in sig_groups:
            sig_groups[sig] = {"x": [], "y": [], "sizes": [], "labels": [], "color": col}
        sig_groups[sig]["x"].append(pos)
        sig_groups[sig]["y"].append(h)
        sig_groups[sig]["sizes"].append(sz)
        sig_groups[sig]["labels"].append(lbl)

    for sig, grp in sig_groups.items():
        fig.add_trace(go.Scatter(
            x=grp["x"],
            y=grp["y"],
            mode="markers",
            name=sig.replace("_", " ").title(),
            marker=dict(
                size=grp["sizes"],
                color=grp["color"],
                line=dict(color="white", width=1),
            ),
            text=grp["labels"],
            hovertemplate="<b>%{text}</b><br>Position: %{x}<br>CADD: %{y:.1f}<extra></extra>",
        ))

    # Mark queried mutation
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            mut_cadd = next((h for p, h in zip(positions, heights) if p == mut_pos), 20)
            fig.add_trace(go.Scatter(
                x=[mut_pos],
                y=[mut_cadd],
                mode="markers+text",
                marker=dict(size=16, color="#FF3B30", symbol="star", line=dict(width=2, color="white")),
                text=[query.mutation],
                textposition="top center",
                textfont=dict(size=11, color="#FF3B30"),
                name=f"Query: {query.mutation}",
                hovertemplate=f"<b>{query.mutation}</b><br>CADD: {mut_cadd:.1f}<extra></extra>",
            ))

    # CADD significance threshold line
    fig.add_hline(
        y=20, line_dash="dash", line_color="rgba(255,59,48,0.3)",
        annotation_text="CADD ≥20 (top 1% deleterious)",
        annotation_font_color="rgba(255,59,48,0.6)",
        annotation_font_size=10,
    )

    fig.update_layout(
        xaxis_title="Protein Position",
        yaxis_title="CADD Score (pathogenicity)",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font_color="#000000",
        height=320,
        margin=dict(t=10, b=40, l=50, r=20),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="right", x=1, font=dict(size=10),
        ),
        xaxis=dict(gridcolor="rgba(0,0,0,0.06)", range=[0, max_res]),
        yaxis=dict(gridcolor="rgba(0,0,0,0.06)"),
    )

    # Cross-filtering: highlight residues selected from other panels
    selected_residues = st.session_state.get("selected_residues", [])
    if selected_residues:
        sel_x = [p for p in positions if p in selected_residues]
        sel_y = [h for p, h in zip(positions, heights) if p in selected_residues]
        if sel_x:
            fig.add_trace(go.Scatter(
                x=sel_x, y=sel_y,
                mode="markers",
                name="Selected",
                marker=dict(
                    size=18, color="rgba(255,149,0,0.3)",
                    line=dict(color="#FF9500", width=2),
                    symbol="circle",
                ),
                hoverinfo="skip",
                showlegend=True,
            ))

    st.plotly_chart(fig, width="stretch", key="variant_lollipop_chart")

    # Hotspot detection & interpretation
    pathogenic_pos = [p for p, c in zip(positions, colors) if c == "#FF3B30"]
    if len(pathogenic_pos) >= 3:
        from collections import Counter
        window = 30
        bins = Counter(p // window for p in pathogenic_pos)
        hotspots = [(b * window, (b + 1) * window, cnt) for b, cnt in bins.items() if cnt >= 2]
        hotspots.sort(key=lambda h: h[2], reverse=True)
        if hotspots:
            top = hotspots[0]
            pct_variants = top[2] / len(pathogenic_pos) * 100
            pct_protein = window / max_res * 100 if max_res > 0 else 0
            st.warning(
                f"**Variant hotspot**: {top[2]} pathogenic variants cluster in "
                f"residues {top[0]}–{top[1]} — {pct_variants:.0f}% of pathogenic "
                f"variants in {pct_protein:.0f}% of the protein."
            )

    severe = sum(1 for h in heights if h >= 20)
    if severe:
        st.info(
            f"**{severe} variant(s)** with CADD ≥ 20 (top 1% deleterious genome-wide) — "
            f"highest-confidence pathogenic positions."
        )
