from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit
from src.utils import confidence_emoji, safe_json_dumps, trust_to_color, trust_to_label


def render_report_export():
    """Tab 4: Report generation, Plotly figures, and downloads."""
    if not st.session_state.get("query_parsed") or not st.session_state.get("prediction_result"):
        st.info(
            "Complete **Search** → **Structure** → **Biology** first, "
            "then come back here to export your results."
        )
        return

    query: ProteinQuery | None = st.session_state.get("parsed_query")
    if query is None:
        st.warning("No query data. Go to the Search tab first.")
        return
    prediction: PredictionResult | None = st.session_state.get("prediction_result")
    trust_audit: TrustAudit | None = st.session_state.get("trust_audit")
    bio_context: BioContext | None = st.session_state.get("bio_context")
    interpretation: str | None = st.session_state.get("interpretation")

    # --- Summary Header ---
    mut_str = f" ({query.mutation})" if query.mutation else ""
    st.markdown(
        f'<div class="glow-card" style="margin-bottom:16px">'
        f'<div style="font-size:1.3rem;font-weight:700">'
        f'Report: {query.protein_name}{mut_str}</div>'
        f'<div style="color:rgba(60,60,67,0.6);font-size:0.88rem;margin-top:2px">'
        f'AI Structure Interpretation &amp; Trust Audit</div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    if trust_audit:
        emoji = confidence_emoji(trust_audit.overall_confidence)
        cols = st.columns(4)
        cols[0].metric("Confidence", f"{trust_audit.confidence_score:.1%}")
        cols[1].metric("Trust Level", f"{emoji} {trust_audit.overall_confidence.title()}")
        cols[2].metric("Residues", len(prediction.residue_ids) if prediction else "—")
        if trust_audit.ptm is not None:
            cols[3].metric("pTM", f"{trust_audit.ptm:.3f}")
        elif bio_context:
            cols[3].metric("Drugs Found", len(bio_context.drugs))

    st.divider()

    # --- Hero Download Section ---
    dl_col1, dl_col2, dl_col3 = st.columns([2, 1, 1])
    with dl_col1:
        st.markdown(
            '<div style="background:linear-gradient(135deg,#007AFF 0%,#5AC8FA 100%);'
            'border-radius:12px;padding:16px 20px;color:white">'
            '<div style="font-size:1.1rem;font-weight:700">Export Your Analysis</div>'
            '<div style="font-size:0.85rem;opacity:0.9;margin-top:4px">'
            'Download the complete report with structure, trust audit, biological context, '
            'and AI interpretation.</div></div>',
            unsafe_allow_html=True,
        )
    with dl_col2:
        _render_pdf_download(query, prediction, trust_audit, bio_context, interpretation)
    with dl_col3:
        if prediction.pdb_content:
            st.download_button(
                "Download PDB",
                prediction.pdb_content,
                f"{query.protein_name}_prediction.pdb",
                mime="chemical/x-pdb",
                use_container_width=True,
                type="primary",
            )

    st.divider()

    # --- AI-Surfaced Insights (cross-domain visualizations) ---
    if trust_audit and prediction:
        from components.insight_visualizations import render_insight_visualizations

        render_insight_visualizations(query, prediction, trust_audit, bio_context)
        st.divider()

    # --- Charts ---
    chart_col1, chart_col2 = st.columns(2)

    with chart_col1:
        # Confidence Profile Chart
        st.markdown("#### Per-Residue Confidence Profile")
        if prediction.plddt_per_residue and prediction.residue_ids:
            fig = _build_confidence_chart(
                prediction.residue_ids, prediction.plddt_per_residue
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No per-residue confidence data available.")

    with chart_col2:
        # Region confidence or drug pipeline
        if trust_audit and trust_audit.regions:
            st.markdown("#### Region Confidence Summary")
            fig_regions = _build_region_chart(trust_audit)
            st.plotly_chart(fig_regions, use_container_width=True)
        elif bio_context and bio_context.drugs:
            st.markdown("#### Drug Pipeline")
            fig_drugs = _build_drug_chart(bio_context)
            st.plotly_chart(fig_drugs, use_container_width=True)

    # Drug pipeline (if region chart already shown and drugs exist)
    if trust_audit and trust_audit.regions and bio_context and bio_context.drugs:
        st.markdown("#### Drug Pipeline")
        fig_drugs = _build_drug_chart(bio_context)
        st.plotly_chart(fig_drugs, use_container_width=True)

    st.divider()

    # --- Enhanced Interactive Dashboard (Nivo) ---
    try:
        from components.nivo_dashboard import NIVO_AVAILABLE, render_nivo_dashboard

        if NIVO_AVAILABLE and prediction and trust_audit:
            with st.expander("Interactive Dashboard (drag to rearrange)", expanded=False):
                render_nivo_dashboard(query, prediction, trust_audit, bio_context)
    except Exception:
        pass  # Nivo dashboard not available or errored

    st.divider()

    # --- PDF Report (hero download) ---
    st.markdown("#### Download Full Report")
    _render_pdf_download(query, prediction, trust_audit, bio_context, interpretation, key_suffix="_full")

    st.divider()

    # --- Other Downloads ---
    st.markdown("#### Other Exports")
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        if prediction.pdb_content:
            st.download_button(
                "Download PDB",
                prediction.pdb_content,
                f"{query.protein_name}_prediction.pdb",
                mime="chemical/x-pdb",
                use_container_width=True,
            )

    with col2:
        report = _build_report_json(query, trust_audit, bio_context, interpretation)
        st.download_button(
            "Download Report (JSON)",
            safe_json_dumps(report, indent=2),
            f"{query.protein_name}_report.json",
            mime="application/json",
            use_container_width=True,
        )

    with col3:
        if prediction.plddt_per_residue:
            csv = _build_confidence_csv(prediction)
            st.download_button(
                "Download Confidence (CSV)",
                csv,
                f"{query.protein_name}_confidence.csv",
                mime="text/csv",
                use_container_width=True,
            )

    with col4:
        md_report = _build_markdown_report(
            query, trust_audit, bio_context, interpretation
        )
        st.download_button(
            "Download Report (MD)",
            md_report,
            f"{query.protein_name}_report.md",
            mime="text/markdown",
            use_container_width=True,
        )

    # --- Export Figure Kit (ZIP) ---
    st.divider()
    _render_figure_kit_section(query, prediction, trust_audit, bio_context)

    # --- Figure Panel Composer ---
    st.divider()
    _render_panel_composer(query, prediction, trust_audit, bio_context)

    # --- Graphical Abstract Generator ---
    st.divider()
    _render_graphical_abstract(query, prediction, trust_audit, bio_context)

    # --- Experiment Tracker ---
    st.divider()
    _render_experiment_tracker(query, trust_audit, bio_context)

    # --- Standalone HTML Report ---
    st.divider()
    _render_html_export(query, prediction, trust_audit, bio_context, interpretation)

    # --- AI-Generated Scientific Diagram ---
    st.divider()
    _render_ai_diagram(query, interpretation)

    # --- BioRender Templates (Live MCP search) ---
    st.divider()
    _render_biorender_section(query)


def _render_pdf_download(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
    key_suffix: str = "",
):
    """Render the PDF download section with generate button."""
    pdf_key = f"pdf_bytes_{query.protein_name}"

    col_btn, col_dl = st.columns([1, 1], gap="small")

    with col_btn:
        if st.button(
            "Generate PDF Report",
            type="primary",
            use_container_width=True,
            key=f"gen_pdf{key_suffix}",
        ):
            with st.spinner("Generating PDF report..."):
                try:
                    from src.pdf_report import generate_pdf_report

                    # Gather variant data from session state
                    variant_data = st.session_state.get(
                        f"variant_data_{query.protein_name}"
                    )

                    # Gather drug resistance data
                    drug_resistance = _gather_drug_resistance(query)

                    pdf_bytes = generate_pdf_report(
                        query=query,
                        prediction=prediction,
                        trust_audit=trust_audit,
                        bio_context=bio_context,
                        interpretation=interpretation,
                        variant_data=variant_data,
                        drug_resistance_data=drug_resistance,
                    )
                    st.session_state[pdf_key] = pdf_bytes
                except Exception as e:
                    st.error(f"PDF generation failed: {e}")

    with col_dl:
        pdf_bytes = st.session_state.get(pdf_key)
        if pdf_bytes:
            mut_str = f"_{query.mutation}" if query.mutation else ""
            st.download_button(
                "Download PDF Report",
                pdf_bytes,
                f"Luminous_{query.protein_name}{mut_str}_report.pdf",
                mime="application/pdf",
                use_container_width=True,
                key=f"dl_pdf{key_suffix}",
            )
            size_kb = len(pdf_bytes) / 1024
            st.caption(f"Report ready ({size_kb:.0f} KB)")
        else:
            st.markdown(
                '<div style="padding:10px;text-align:center;color:rgba(60,60,67,0.55);'
                'font-size:0.88rem">Click Generate to create the PDF</div>',
                unsafe_allow_html=True,
            )


def _gather_drug_resistance(query: ProteinQuery) -> list[dict] | None:
    """Gather drug resistance data from the curated knowledge base."""
    try:
        from components.drug_resistance import _RESISTANCE_DB
    except ImportError:
        return None

    protein_key = query.protein_name.upper()
    resistance_data = _RESISTANCE_DB.get(protein_key)
    if not resistance_data:
        return None

    mutations_db = resistance_data.get("mutations", {})
    if not mutations_db:
        return None

    query_mut = query.mutation.upper() if query.mutation else None
    result = []
    for name, data in mutations_db.items():
        result.append({
            "name": name,
            "mechanism": data.get("mechanism", ""),
            "explanation": data.get("explanation", ""),
            "is_query": name.upper() == query_mut,
            "drugs": data.get("drugs_affected", []),
            "clinical_note": data.get("clinical_note", ""),
        })

    # Put query mutation first
    result.sort(key=lambda x: (not x["is_query"], x["name"]))
    return result if result else None


def _build_confidence_chart(
    residue_ids: list[int], plddt_scores: list[float]
) -> go.Figure:
    colors = [trust_to_color(s) for s in plddt_scores]
    fig = go.Figure(
        go.Bar(
            x=residue_ids,
            y=plddt_scores,
            marker_color=colors,
            hovertemplate="Residue %{x}<br>pLDDT: %{y:.1f}<br>%{text}<extra></extra>",
            text=[trust_to_label(s) for s in plddt_scores],
        )
    )
    fig.update_layout(
        xaxis_title="Residue Number",
        yaxis_title="pLDDT Score",
        yaxis_range=[0, 100],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=350,
        margin=dict(t=10, b=40, l=50, r=20),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        shapes=[
            dict(
                type="line", y0=t, y1=t, x0=0, x1=1, xref="paper",
                line=dict(color=c, width=1, dash="dash"),
            )
            for t, c in [(90, "#0053D6"), (70, "#65CBF3"), (50, "#FFDB13")]
        ],
    )
    return fig


def _build_region_chart(trust_audit: TrustAudit) -> go.Figure:
    regions = trust_audit.regions
    labels = [f"Ch {r.chain}: {r.start_residue}-{r.end_residue}" for r in regions]
    scores = [r.avg_plddt for r in regions]
    colors = [trust_to_color(s) for s in scores]
    flags = [r.flag or "OK" for r in regions]

    fig = go.Figure(
        go.Bar(
            x=labels,
            y=scores,
            marker_color=colors,
            hovertemplate="%{x}<br>Avg pLDDT: %{y:.1f}<br>%{text}<extra></extra>",
            text=flags,
        )
    )
    fig.update_layout(
        yaxis_title="Average pLDDT",
        yaxis_range=[0, 100],
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=350,
        margin=dict(t=10, b=40, l=50, r=20),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    return fig


def _build_drug_chart(bio_context: BioContext) -> go.Figure:
    phase_order = ["Identified", "Phase I", "Phase II", "Phase III", "Approved"]
    phase_counts = {p: 0 for p in phase_order}
    for drug in bio_context.drugs:
        phase = drug.phase or "Identified"
        matched = False
        for p in phase_order:
            if p.lower() in phase.lower():
                phase_counts[p] += 1
                matched = True
                break
        if not matched:
            phase_counts["Identified"] += 1

    fig = go.Figure(
        go.Funnel(
            y=phase_order,
            x=[phase_counts[p] for p in phase_order],
            textinfo="value+label",
            marker=dict(color=["#8E8E93", "#AF52DE", "#FF9500", "#007AFF", "#34C759"]),
        )
    )
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="rgba(60,60,67,0.6)"),
        height=300,
        margin=dict(t=10, b=20, l=20, r=20),
    )
    return fig


def _build_report_json(
    query: ProteinQuery,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
) -> dict:
    report = {
        "generated_by": "Luminous - The AI Structure Interpreter",
        "version": "1.0",
        "query": query.model_dump(),
    }
    if trust_audit:
        report["trust_audit"] = trust_audit.model_dump()
    if bio_context:
        report["bio_context"] = bio_context.model_dump()
    if interpretation:
        report["interpretation"] = interpretation

    # Include experiment tracker if present
    tracker = st.session_state.get("experiment_tracker")
    if tracker:
        report["experiment_tracker"] = tracker
        total = len(tracker)
        completed = sum(1 for v in tracker.values() if v)
        report["experiments_completed"] = f"{completed}/{total}"

    # Include statistical analysis results
    stats_results = st.session_state.get("stats_results")
    if stats_results:
        report["statistical_analysis"] = {
            "test_name": stats_results.get("test_name"),
            "p_value": stats_results.get("p_val"),
            "effect_size": stats_results.get("cohen_d") or stats_results.get("eta_squared") or stats_results.get("r"),
            "interpretation": stats_results.get("interpretation"),
        }

    return report


def _build_confidence_csv(prediction: PredictionResult) -> str:
    lines = ["chain_id,residue_id,plddt,confidence_level"]
    for chain, res, score in zip(
        prediction.chain_ids, prediction.residue_ids, prediction.plddt_per_residue
    ):
        lines.append(f"{chain},{res},{score:.1f},{trust_to_label(score)}")
    return "\n".join(lines)


def _build_markdown_report(
    query: ProteinQuery,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
) -> str:
    """Build a human-readable markdown report."""
    lines = [
        f"# Luminous Analysis Report: {query.protein_name}",
        "*Generated by Luminous - The AI Structure Interpreter*",
        "",
        "## Query",
        f"- **Protein:** {query.protein_name}",
        f"- **UniProt ID:** {query.uniprot_id or 'N/A'}",
        f"- **Question Type:** {query.question_type}",
    ]
    if query.mutation:
        lines.append(f"- **Mutation:** {query.mutation}")
    if query.interaction_partner:
        lines.append(f"- **Interaction Partner:** {query.interaction_partner}")

    if trust_audit:
        lines.extend([
            "",
            "## Trust Audit",
            f"- **Overall Confidence:** {trust_audit.overall_confidence} ({trust_audit.confidence_score:.1%})",
        ])
        if trust_audit.ptm is not None:
            lines.append(f"- **pTM:** {trust_audit.ptm:.3f}")
        if trust_audit.iptm is not None:
            lines.append(f"- **ipTM:** {trust_audit.iptm:.3f}")

        flagged = [r for r in trust_audit.regions if r.flag]
        if flagged:
            lines.append(f"\n### Flagged Regions ({len(flagged)})")
            for r in flagged:
                lines.append(
                    f"- Chain {r.chain} residues {r.start_residue}-{r.end_residue}: "
                    f"avg pLDDT {r.avg_plddt} - {r.flag}"
                )

        if trust_audit.known_limitations:
            lines.append("\n### Known Limitations")
            for lim in trust_audit.known_limitations:
                lines.append(f"- {lim}")

        if trust_audit.suggested_validation:
            lines.append("\n### Suggested Validation")
            for s in trust_audit.suggested_validation:
                lines.append(f"- {s}")

    # Experiment tracker
    tracker = st.session_state.get("experiment_tracker")
    if tracker:
        total = len(tracker)
        completed = sum(1 for v in tracker.values() if v)
        lines.extend(["", f"## Experiment Tracker ({completed}/{total} completed)"])
        for name, done in tracker.items():
            check = "[x]" if done else "[ ]"
            lines.append(f"- {check} {name}")

    if interpretation:
        lines.extend(["", "## AI Interpretation", interpretation])

    if bio_context:
        if bio_context.disease_associations:
            lines.extend(["", "## Disease Associations"])
            for d in bio_context.disease_associations:
                score = f" (score: {d.score:.2f})" if d.score is not None else ""
                lines.append(f"- **{d.disease}**{score}")
                if d.evidence:
                    lines.append(f"  - {d.evidence}")

        if bio_context.drugs:
            lines.extend(["", "## Drug Candidates"])
            for drug in bio_context.drugs:
                phase = f" ({drug.phase})" if drug.phase else ""
                lines.append(f"- **{drug.name}**{phase}")
                if drug.mechanism:
                    lines.append(f"  - Mechanism: {drug.mechanism}")

        if bio_context.literature.key_findings:
            lines.extend([
                "",
                f"## Literature ({bio_context.literature.total_papers} papers)",
            ])
            for f in bio_context.literature.key_findings:
                lines.append(f"- {f}")

    # Statistics
    stats_results = st.session_state.get("stats_results")
    if stats_results:
        lines.extend([
            "",
            "## Statistical Analysis",
            "",
            f"**Test:** {stats_results.get('test_name', 'N/A')}",
            f"**p-value:** {stats_results.get('p_val', 'N/A')}",
        ])
        if stats_results.get("cohen_d"):
            lines.append(f"**Effect size (Cohen's d):** {stats_results['cohen_d']:.3f}")
        if stats_results.get("eta_squared"):
            lines.append(f"**Effect size (\u03b7\u00b2):** {stats_results['eta_squared']:.3f}")
        if stats_results.get("r"):
            lines.append(f"**Correlation (r):** {stats_results['r']:.3f}")
        if stats_results.get("interpretation"):
            lines.extend(["", stats_results["interpretation"]])

    lines.extend([
        "",
        "---",
        "*Report generated by Luminous. Predictions should be validated experimentally.*",
        "*Powered by Tamarind Bio (Boltz-2), Anthropic Claude (MCP), BioRender, and Modal.*",
    ])

    return "\n".join(lines)


def _render_ai_diagram(
    query: ProteinQuery,
    interpretation: str | None,
):
    """Render AI-generated SVG scientific diagram via Claude."""
    st.markdown("#### AI-Generated Scientific Diagram")
    st.caption(
        "Claude generates a vector pathway diagram based on your "
        "protein analysis — editable, publication-ready SVG."
    )

    svg_key = f"svg_diagram_{query.protein_name}"

    if svg_key not in st.session_state:
        st.session_state[svg_key] = None

    col1, col2 = st.columns([1, 3])
    with col1:
        generate = st.button(
            "Generate Diagram",
            type="primary",
            use_container_width=True,
            key="gen_svg_btn",
        )

    if generate:
        from src.biorender_search import generate_svg_diagram

        with st.spinner("Claude is drawing your diagram..."):
            svg = generate_svg_diagram(
                protein_name=query.protein_name,
                mutation=query.mutation,
                question_type=query.question_type,
                interaction_partner=getattr(
                    query, "interaction_partner", None
                ),
                interpretation=interpretation,
            )
            st.session_state[svg_key] = svg

    svg_content = st.session_state.get(svg_key)
    if svg_content:
        # Render SVG inline
        st.markdown(
            f'<div style="background:white;border-radius:12px;'
            f'padding:16px;border:1px solid rgba(0,0,0,0.08);'
            f'text-align:center">{svg_content}</div>',
            unsafe_allow_html=True,
        )

        # Download button for SVG file
        mut_str = f"_{query.mutation}" if query.mutation else ""
        filename = f"{query.protein_name}{mut_str}_diagram.svg"
        st.download_button(
            "Download SVG",
            data=svg_content,
            file_name=filename,
            mime="image/svg+xml",
            key="dl_svg_btn",
        )
    elif not generate:
        st.info(
            "Click **Generate Diagram** to create an AI-powered "
            "scientific illustration of your protein analysis."
        )


def _load_precomputed_biorender(query: ProteinQuery) -> list[dict] | None:
    """Load pre-cached BioRender templates from data/precomputed/{key}/biorender.json."""
    from pathlib import Path

    # Build lookup key from protein name + mutation
    protein = query.protein_name.lower()
    mutation = (query.mutation or "").lower().replace(" ", "_")
    variant_key = f"{protein}_{mutation}" if mutation else protein

    # Try exact match first, then common aliases (e.g. TP53 -> p53)
    aliases = [variant_key]
    _PROTEIN_ALIASES = {"tp53": "p53", "p53": "tp53"}
    if protein in _PROTEIN_ALIASES:
        alt = _PROTEIN_ALIASES[protein]
        aliases.append(f"{alt}_{mutation}" if mutation else alt)

    for key in aliases:
        path = Path("data/precomputed") / key / "biorender.json"
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
    return None


def _render_biorender_section(query: ProteinQuery):
    """Render BioRender integration: templates, AI figure prompt, and checklist."""
    st.markdown("#### Publication Figures via BioRender")

    # --- Template Discovery ---
    cache_key = f"biorender_results_{query.protein_name}"
    results = st.session_state.get(cache_key)

    if results is None:
        precomputed = _load_precomputed_biorender(query)
        if precomputed:
            results = precomputed
            st.session_state[cache_key] = results

    if results is None:
        from src.biorender_search import search_biorender_templates

        trust_audit: TrustAudit | None = st.session_state.get("trust_audit")
        trust_summary = None
        if trust_audit:
            trust_summary = (
                f"Confidence: {trust_audit.overall_confidence} "
                f"({trust_audit.confidence_score:.0%})"
            )
            if trust_audit.known_limitations:
                trust_summary += f". Limitations: {'; '.join(trust_audit.known_limitations[:2])}"

        with st.spinner("Searching BioRender for relevant templates..."):
            results = search_biorender_templates(
                protein_name=query.protein_name,
                mutation=query.mutation,
                question_type=query.question_type,
                trust_summary=trust_summary,
            )
            st.session_state[cache_key] = results

    templates = [r for r in results if r.get("type") == "template"]
    icons = [r for r in results if r.get("type") == "icon"]
    other = [r for r in results if r.get("type") not in ("template", "icon")]

    if templates:
        st.markdown("**Recommended Templates:**")
        cols = st.columns(min(len(templates), 3))
        for i, tmpl in enumerate(templates):
            with cols[i % min(len(templates), 3)]:
                url = tmpl.get("url", "")
                url_btn = (
                    f'<a href="{url}" target="_blank" '
                    f'style="color:#007AFF;font-size:0.8em;text-decoration:none">'
                    f'Open in BioRender &rarr;</a>'
                ) if url else ""
                st.markdown(
                    f'<div class="glow-card" style="min-height:120px">'
                    f'<div style="font-weight:600;font-size:0.95rem;color:#007AFF;'
                    f'margin-bottom:6px">{tmpl["name"]}</div>'
                    f'<div style="font-size:0.82rem;color:rgba(60,60,67,0.6);line-height:1.4">'
                    f'{tmpl.get("description", "")}</div>'
                    f'{url_btn}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    if icons:
        st.markdown("**Icon Library:**")
        icon_cols = st.columns(min(len(icons), 4))
        for i, icon in enumerate(icons):
            with icon_cols[i % min(len(icons), 4)]:
                url = icon.get("url", "")
                st.markdown(
                    f'<a href="{url}" target="_blank" style="text-decoration:none">'
                    f'<div style="padding:8px 12px;margin:4px 0;'
                    f'border:1px solid rgba(0,122,255,0.15);border-radius:8px;'
                    f'font-size:0.85rem;text-align:center">'
                    f'<div style="font-weight:600;color:#007AFF">{icon["name"]}</div>'
                    f'<div style="font-size:0.75rem;color:rgba(60,60,67,0.55);margin-top:2px">'
                    f'{icon.get("description", "")}</div>'
                    f'</div></a>',
                    unsafe_allow_html=True,
                )

    if other:
        for item in other:
            st.markdown(f"- **{item.get('name', 'Unknown')}** — {item.get('description', '')}")

    # --- AI Figure Prompt Generator ---
    st.markdown("---")
    st.markdown("**AI Figure Prompt** — Copy into BioRender's text-to-figure tool")

    prompt_key = f"biorender_prompt_{query.protein_name}"
    if prompt_key not in st.session_state:
        from src.biorender_search import generate_figure_prompt

        interpretation_text = st.session_state.get("interpretation")
        with st.spinner("Generating figure prompt..."):
            prompt = generate_figure_prompt(
                protein_name=query.protein_name,
                mutation=query.mutation,
                question_type=query.question_type,
                interaction_partner=getattr(query, "interaction_partner", None),
                interpretation=interpretation_text,
            )
            st.session_state[prompt_key] = prompt or ""

    figure_prompt = st.session_state.get(prompt_key, "")
    if figure_prompt:
        st.code(figure_prompt, language=None)
        p_col1, p_col2 = st.columns([1, 1], gap="small")
        with p_col1:
            st.markdown(
                '<a href="https://app.biorender.com" target="_blank" '
                'style="display:inline-block;padding:8px 20px;background:#007AFF;'
                'color:white;border-radius:8px;text-decoration:none;font-weight:600;'
                'font-size:0.9rem">Open BioRender &rarr;</a>',
                unsafe_allow_html=True,
            )
        with p_col2:
            st.caption(
                "Copy the prompt above, open BioRender, "
                "and paste into the AI text-to-figure tool."
            )

    # --- Publication Figure Checklist ---
    st.markdown("---")
    st.markdown("**Publication Figure Checklist**")

    from src.biorender_search import generate_figure_checklist

    trust_audit_obj: TrustAudit | None = st.session_state.get("trust_audit")
    conf_score = trust_audit_obj.confidence_score if trust_audit_obj else None

    checklist = generate_figure_checklist(
        protein_name=query.protein_name,
        mutation=query.mutation,
        question_type=query.question_type,
        confidence_score=conf_score,
    )

    checklist_key = "figure_checklist_state"
    if not st.session_state.get(checklist_key):
        st.session_state[checklist_key] = {}
    check_state: dict[str, bool] = st.session_state[checklist_key] or {}

    # Group by category
    categories: dict[str, list[dict]] = {}
    for item in checklist:
        cat = item["category"]
        categories.setdefault(cat, []).append(item)

    total = len(checklist)
    checked = sum(1 for item in checklist if check_state.get(item["item"], False))
    progress = checked / max(total, 1)

    st.progress(progress, text=f"{checked}/{total} items complete")

    for cat, items in categories.items():
        st.markdown(f"**{cat}**")
        for item in items:
            import hashlib
            key = f"chk_{hashlib.md5(item['item'].encode()).hexdigest()[:10]}"
            req_badge = " *(required)*" if item["required"] else ""
            check_state[item["item"]] = st.checkbox(
                f"{item['item']}{req_badge}",
                value=check_state.get(item["item"], False),
                key=key,
            )

    st.caption(
        "Illustrations powered by [BioRender](https://www.biorender.com). "
        "All template links open real BioRender pages for customization."
    )


# ── Experiment Tracker ────────────────────────────────────────────────────────


def _render_experiment_tracker(
    query: ProteinQuery,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
):
    """Show checkboxes for suggested validation experiments with progress tracking."""
    st.markdown("#### Experiment Tracker")

    # Initialize experiment tracker in session state
    if not st.session_state.get("experiment_tracker"):
        st.session_state["experiment_tracker"] = {}

    tracker: dict[str, bool] = st.session_state["experiment_tracker"] or {}

    # Collect suggested experiments from trust audit and bio context
    suggested: list[str] = []
    if trust_audit and trust_audit.suggested_validation:
        suggested.extend(trust_audit.suggested_validation)
    if bio_context and bio_context.suggested_experiments:
        for exp in bio_context.suggested_experiments:
            if exp not in suggested:
                suggested.append(exp)

    # Ensure all suggested experiments are in the tracker
    for exp in suggested:
        if exp not in tracker:
            tracker[exp] = False

    if not tracker:
        st.info(
            "No experiments to track yet. Run the trust audit to get "
            "suggested validation experiments."
        )
        return

    # Progress bar
    total = len(tracker)
    completed = sum(1 for v in tracker.values() if v)
    st.progress(
        completed / total if total > 0 else 0,
        text=f"{completed}/{total} experiments completed",
    )

    # Experiment checkboxes
    st.markdown(
        '<div style="font-size:0.88rem;color:rgba(60,60,67,0.6);margin-bottom:8px">'
        "Track which validation experiments have been completed:</div>",
        unsafe_allow_html=True,
    )

    experiments_to_update: dict[str, bool] = {}
    for exp_name in list(tracker.keys()):
        is_suggested = exp_name in suggested
        prefix = "Suggested" if is_suggested else "Custom"
        checked = st.checkbox(
            f"[{prefix}] {exp_name}",
            value=tracker[exp_name],
            key=f"exp_check_{hash(exp_name)}",
        )
        experiments_to_update[exp_name] = checked

    # Batch update tracker
    st.session_state["experiment_tracker"] = experiments_to_update

    # Add custom experiment
    st.markdown("---")
    col_input, col_btn = st.columns([3, 1])
    with col_input:
        new_exp = st.text_input(
            "Add Custom Experiment",
            key="new_experiment_input",
            placeholder="e.g., Circular dichroism spectroscopy",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Add Experiment", key="add_experiment_btn", use_container_width=True):
            if new_exp and new_exp.strip():
                if st.session_state.get("experiment_tracker") is None:
                    st.session_state["experiment_tracker"] = {}
                st.session_state["experiment_tracker"][new_exp.strip()] = False
                st.rerun()

    # Summary
    if completed > 0:
        st.success(
            f"{completed} of {total} validation experiments completed. "
            f"{'All done!' if completed == total else f'{total - completed} remaining.'}"
        )


# ── Standalone HTML Report ────────────────────────────────────────────────────


def _render_html_export(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
):
    """Generate and download a self-contained HTML report."""
    st.markdown("#### Standalone HTML Report")
    st.markdown(
        '<div style="font-size:0.88rem;color:rgba(60,60,67,0.6);margin-bottom:8px">'
        "Generate a self-contained HTML file with interactive charts that "
        "anyone can open in a browser.</div>",
        unsafe_allow_html=True,
    )

    html_key = f"html_report_{query.protein_name}"

    col_gen, col_dl = st.columns([1, 1], gap="small")

    with col_gen:
        if st.button(
            "Generate HTML Report",
            type="secondary",
            use_container_width=True,
            key="gen_html",
        ):
            with st.spinner("Building HTML report..."):
                html_content = _build_html_report(
                    query, prediction, trust_audit, bio_context, interpretation
                )
                st.session_state[html_key] = html_content

    with col_dl:
        html_content = st.session_state.get(html_key)
        if html_content:
            mut_str = f"_{query.mutation}" if query.mutation else ""
            st.download_button(
                "Download HTML Report",
                html_content,
                f"Luminous_{query.protein_name}{mut_str}_report.html",
                mime="text/html",
                use_container_width=True,
                key="dl_html",
            )
            size_kb = len(html_content) / 1024
            st.caption(f"HTML report ready ({size_kb:.0f} KB)")
        else:
            st.markdown(
                '<div style="padding:10px;text-align:center;color:rgba(60,60,67,0.55);'
                'font-size:0.88rem">Click Generate to create the HTML report</div>',
                unsafe_allow_html=True,
            )


def _build_html_report(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
) -> str:
    """Build a self-contained HTML report with embedded Plotly charts."""
    mut_str = f" ({query.mutation})" if query.mutation else ""
    title = f"Luminous Report: {query.protein_name}{mut_str}"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build Plotly chart HTML fragments
    confidence_chart_html = ""
    if prediction.plddt_per_residue and prediction.residue_ids:
        fig = _build_confidence_chart(
            prediction.residue_ids, prediction.plddt_per_residue
        )
        fig.update_layout(template="plotly_white")
        confidence_chart_html = fig.to_html(
            include_plotlyjs=False, full_html=False
        )

    region_chart_html = ""
    if trust_audit and trust_audit.regions:
        fig = _build_region_chart(trust_audit)
        fig.update_layout(template="plotly_white")
        region_chart_html = fig.to_html(
            include_plotlyjs=False, full_html=False
        )

    drug_chart_html = ""
    if bio_context and bio_context.drugs:
        fig = _build_drug_chart(bio_context)
        fig.update_layout(template="plotly_white")
        drug_chart_html = fig.to_html(
            include_plotlyjs=False, full_html=False
        )

    # Trust audit summary table
    trust_table = ""
    if trust_audit:
        rows = [
            f"<tr><td>Overall Confidence</td><td>{trust_audit.overall_confidence.title()}</td></tr>",
            f"<tr><td>Confidence Score</td><td>{trust_audit.confidence_score:.1%}</td></tr>",
        ]
        if trust_audit.ptm is not None:
            rows.append(f"<tr><td>pTM</td><td>{trust_audit.ptm:.3f}</td></tr>")
        if trust_audit.iptm is not None:
            rows.append(f"<tr><td>ipTM</td><td>{trust_audit.iptm:.3f}</td></tr>")

        flagged = [r for r in trust_audit.regions if r.flag]
        if flagged:
            for r in flagged:
                rows.append(
                    f"<tr><td>Flagged: Chain {r.chain} {r.start_residue}-{r.end_residue}</td>"
                    f"<td>pLDDT {r.avg_plddt:.1f} &mdash; {r.flag}</td></tr>"
                )

        trust_table = (
            '<table class="metrics-table">'
            "<thead><tr><th>Metric</th><th>Value</th></tr></thead>"
            f"<tbody>{''.join(rows)}</tbody></table>"
        )

    # Limitations
    limitations_html = ""
    if trust_audit and trust_audit.known_limitations:
        items = "".join(f"<li>{lim}</li>" for lim in trust_audit.known_limitations)
        limitations_html = f"<h3>Known Limitations</h3><ul>{items}</ul>"

    # Suggested validation
    validation_html = ""
    if trust_audit and trust_audit.suggested_validation:
        items = "".join(f"<li>{s}</li>" for s in trust_audit.suggested_validation)
        validation_html = f"<h3>Suggested Validation</h3><ul>{items}</ul>"

    # Experiment tracker
    experiment_html = ""
    tracker = st.session_state.get("experiment_tracker", {})
    if tracker:
        items = []
        for name, done in tracker.items():
            check = "&#9745;" if done else "&#9744;"
            items.append(f"<li>{check} {name}</li>")
        total_exp = len(tracker)
        done_exp = sum(1 for v in tracker.values() if v)
        experiment_html = (
            f"<h3>Experiment Tracker ({done_exp}/{total_exp} completed)</h3>"
            f"<ul>{''.join(items)}</ul>"
        )

    # Bio context narrative
    context_html = ""
    if bio_context and bio_context.narrative:
        context_html = (
            f"<h2>Biological Context</h2>"
            f"<div class='narrative'>{bio_context.narrative}</div>"
        )

    # Disease associations
    disease_html = ""
    if bio_context and bio_context.disease_associations:
        items = []
        for d in bio_context.disease_associations:
            score = f" (score: {d.score:.2f})" if d.score is not None else ""
            evidence = f"<br><em>{d.evidence}</em>" if d.evidence else ""
            items.append(f"<li><strong>{d.disease}</strong>{score}{evidence}</li>")
        disease_html = f"<h3>Disease Associations</h3><ul>{''.join(items)}</ul>"

    # Drug candidates
    drugs_html = ""
    if bio_context and bio_context.drugs:
        items = []
        for drug in bio_context.drugs:
            phase = f" ({drug.phase})" if drug.phase else ""
            mech = f"<br>Mechanism: {drug.mechanism}" if drug.mechanism else ""
            items.append(f"<li><strong>{drug.name}</strong>{phase}{mech}</li>")
        drugs_html = f"<h3>Drug Candidates</h3><ul>{''.join(items)}</ul>"

    # Interpretation
    interp_html = ""
    if interpretation:
        # Convert markdown-ish text to basic HTML
        paragraphs = interpretation.split("\n\n")
        formatted = "".join(f"<p>{p.strip()}</p>" for p in paragraphs if p.strip())
        interp_html = f"<h2>AI Interpretation</h2><div class='narrative'>{formatted}</div>"

    # Literature
    lit_html = ""
    if bio_context and bio_context.literature.key_findings:
        items = "".join(f"<li>{f}</li>" for f in bio_context.literature.key_findings)
        lit_html = (
            f"<h3>Key Literature Findings "
            f"({bio_context.literature.total_papers} papers)</h3>"
            f"<ul>{items}</ul>"
        )

    # Assemble full HTML
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
  :root {{
    --primary: #007AFF;
    --success: #34C759;
    --warning: #d97706;
    --danger: #dc2626;
    --bg: #ffffff;
    --text: #000000;
    --muted: #8E8E93;
    --border: #E5E5EA;
    --card-bg: #f8fafc;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: 'Nunito', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: var(--bg);
    color: var(--text);
    line-height: 1.6;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 24px;
  }}
  h1 {{ font-size: 1.8rem; margin-bottom: 4px; color: var(--primary); }}
  h2 {{ font-size: 1.3rem; margin: 28px 0 12px; color: var(--text); border-bottom: 2px solid var(--border); padding-bottom: 6px; }}
  h3 {{ font-size: 1.05rem; margin: 20px 0 8px; color: var(--muted); }}
  .subtitle {{ color: var(--muted); font-size: 0.95rem; margin-bottom: 20px; }}
  .meta {{ font-size: 0.82rem; color: var(--muted); margin-bottom: 24px; }}
  .metrics-table {{
    width: 100%;
    border-collapse: collapse;
    margin: 12px 0;
  }}
  .metrics-table th, .metrics-table td {{
    text-align: left;
    padding: 8px 12px;
    border-bottom: 1px solid var(--border);
    font-size: 0.92rem;
  }}
  .metrics-table th {{
    background: var(--card-bg);
    font-weight: 600;
    color: var(--muted);
  }}
  .chart-container {{
    margin: 16px 0;
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 12px;
    background: var(--card-bg);
  }}
  .chart-container h3 {{ margin-top: 0; }}
  .narrative {{
    background: var(--card-bg);
    border-left: 3px solid var(--primary);
    padding: 14px 18px;
    border-radius: 0 8px 8px 0;
    margin: 12px 0;
    font-size: 0.95rem;
  }}
  ul {{ padding-left: 24px; margin: 8px 0; }}
  li {{ margin-bottom: 4px; font-size: 0.92rem; }}
  .footer {{
    margin-top: 40px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    text-align: center;
    font-size: 0.82rem;
    color: var(--muted);
  }}
  @media print {{
    body {{ max-width: 100%; padding: 20px; }}
    .chart-container {{ break-inside: avoid; }}
  }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="subtitle">AI Structure Interpretation &amp; Trust Audit</div>
<div class="meta">Generated by Luminous on {now} | Protein: {query.protein_name}
{f' | Mutation: {query.mutation}' if query.mutation else ''}
{f' | UniProt: {query.uniprot_id}' if query.uniprot_id else ''}</div>

<h2>Trust Audit</h2>
{trust_table}
{limitations_html}
{validation_html}
{experiment_html}

{'<div class="chart-container"><h3>Per-Residue Confidence Profile</h3>' + confidence_chart_html + '</div>' if confidence_chart_html else ''}
{'<div class="chart-container"><h3>Region Confidence Summary</h3>' + region_chart_html + '</div>' if region_chart_html else ''}

{interp_html}
{context_html}
{disease_html}
{drugs_html}
{lit_html}

{'<div class="chart-container"><h3>Drug Pipeline</h3>' + drug_chart_html + '</div>' if drug_chart_html else ''}

<div class="footer">
  Report generated by <strong>Luminous</strong> &mdash; The AI Structure Interpreter<br>
  Predictions should be validated experimentally.<br>
  Powered by Tamarind Bio (Boltz-2) &bull; Anthropic Claude (MCP) &bull; BioRender &bull; Modal
</div>
</body>
</html>"""

    return html


# ─── Export Figure Kit ─────────────────────────────────────────────


def _render_figure_kit_section(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
):
    """Render the Export Figure Kit section with one-click ZIP download."""
    st.markdown("#### Export Figure Kit")
    st.markdown(
        '<div style="color:rgba(60,60,67,0.6);font-size:0.88rem;margin-bottom:12px">'
        "Download all charts as publication-ready SVG files with auto-generated "
        "figure legends and LaTeX-ready captions in a single ZIP archive."
        "</div>",
        unsafe_allow_html=True,
    )

    col_btn, col_dl = st.columns([1, 1], gap="small")
    kit_key = f"figure_kit_{query.protein_name}"

    with col_btn:
        if st.button(
            "Generate Figure Kit",
            type="primary",
            use_container_width=True,
            key="gen_figure_kit",
        ):
            with st.spinner("Assembling figure kit..."):
                try:
                    kit_bytes = _build_figure_kit_zip(
                        query, prediction, trust_audit, bio_context
                    )
                    st.session_state[kit_key] = kit_bytes
                except Exception as e:
                    st.error(f"Figure kit generation failed: {e}")

    with col_dl:
        kit_bytes = st.session_state.get(kit_key)
        if kit_bytes:
            mut_str = f"_{query.mutation}" if query.mutation else ""
            st.download_button(
                "Download Figure Kit (ZIP)",
                kit_bytes,
                f"Luminous_{query.protein_name}{mut_str}_figures.zip",
                mime="application/zip",
                use_container_width=True,
                key="dl_figure_kit",
            )
            size_kb = len(kit_bytes) / 1024
            st.caption(f"Figure kit ready ({size_kb:.0f} KB)")
        else:
            st.markdown(
                '<div style="padding:10px;text-align:center;color:rgba(60,60,67,0.55);'
                'font-size:0.88rem">Click Generate to create the figure kit</div>',
                unsafe_allow_html=True,
            )


def _export_figure(fig: go.Figure, name: str) -> tuple[str, bytes, str]:
    """Export a Plotly figure. Returns (filename, content_bytes, format).

    Tries SVG via kaleido first, falls back to standalone HTML.
    """
    try:
        svg_bytes = fig.to_image(format="svg")
        return (f"{name}.svg", svg_bytes, "svg")
    except Exception:
        # kaleido not installed — fall back to HTML
        html_str = fig.to_html(include_plotlyjs="cdn", full_html=True)
        return (f"{name}.html", html_str.encode("utf-8"), "html")


def _build_figure_kit_zip(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
) -> bytes:
    """Build an in-memory ZIP containing all charts, legends, and LaTeX captions."""
    buf = io.BytesIO()
    figures: list[tuple[str, go.Figure, str]] = []  # (name, fig, description)

    # Confidence profile
    if prediction.plddt_per_residue and prediction.residue_ids:
        fig_conf = _build_confidence_chart(
            prediction.residue_ids, prediction.plddt_per_residue
        )
        n_res = len(prediction.residue_ids)
        avg_plddt = sum(prediction.plddt_per_residue) / n_res
        figures.append((
            "confidence_profile",
            fig_conf,
            f"Per-residue confidence (pLDDT) profile for {query.protein_name} "
            f"({n_res} residues, mean pLDDT = {avg_plddt:.1f}). "
            f"Colors follow AlphaFold convention: blue (>90, very high), "
            f"cyan (70-90, confident), yellow (50-70, low), orange (<50, very low).",
        ))

    # Region chart
    if trust_audit and trust_audit.regions:
        fig_reg = _build_region_chart(trust_audit)
        n_flagged = sum(1 for r in trust_audit.regions if r.flag)
        figures.append((
            "region_confidence",
            fig_reg,
            f"Regional confidence summary for {query.protein_name}. "
            f"{len(trust_audit.regions)} regions analyzed, {n_flagged} flagged "
            f"for low confidence.",
        ))

    # Drug pipeline
    if bio_context and bio_context.drugs:
        fig_drug = _build_drug_chart(bio_context)
        figures.append((
            "drug_pipeline",
            fig_drug,
            f"Drug development pipeline for {query.protein_name} target. "
            f"{len(bio_context.drugs)} candidates across clinical phases.",
        ))

    mut_str = f" ({query.mutation})" if query.mutation else ""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Export each figure
        exported_formats: dict[str, str] = {}
        for name, fig, _desc in figures:
            fname, content, fmt = _export_figure(fig, name)
            zf.writestr(fname, content)
            exported_formats[name] = fmt

        # Figure legends text file
        legends_lines = [
            f"FIGURE LEGENDS -- {query.protein_name}{mut_str}",
            f"Generated by Luminous on {timestamp}",
            "=" * 60,
            "",
        ]
        for i, (name, _fig, desc) in enumerate(figures, 1):
            ext = exported_formats.get(name, "svg")
            legends_lines.extend([
                f"Figure {i}: {_figure_title(name)}",
                f"File: {name}.{ext}",
                f"Legend: {desc}",
                "",
            ])
        zf.writestr("figure_legends.txt", "\n".join(legends_lines))

        # LaTeX captions
        latex_lines = [
            f"% LaTeX figure captions for {query.protein_name}{mut_str}",
            f"% Generated by Luminous on {timestamp}",
            "",
        ]
        for i, (name, _fig, desc) in enumerate(figures, 1):
            ext = exported_formats.get(name, "svg")
            label = name.replace("_", "-")
            latex_lines.extend([
                r"\begin{figure}[htbp]",
                r"  \centering",
                f"  \\includegraphics[width=\\textwidth]{{{name}.{ext}}}",
                f"  \\caption{{{desc}}}",
                f"  \\label{{fig:{label}}}",
                r"\end{figure}",
                "",
            ])
        zf.writestr("latex_captions.tex", "\n".join(latex_lines))

        # BioRender template links (if cached)
        br_key = f"biorender_results_{query.protein_name}"
        br_results = st.session_state.get(br_key)
        if br_results:
            br_lines = [
                f"BioRender Resources for {query.protein_name}{mut_str}",
                "=" * 50,
                "",
            ]
            for item in br_results:
                name_br = item.get("name", "Unknown")
                url = item.get("url", "")
                desc = item.get("description", "")
                kind = item.get("type", "resource")
                br_lines.append(
                    f"[{kind.upper()}] {name_br}\n  {desc}\n  URL: {url}\n"
                )
            zf.writestr("biorender_templates.txt", "\n".join(br_lines))

        # README
        readme_lines = [
            f"Luminous Figure Kit: {query.protein_name}{mut_str}",
            f"Generated: {timestamp}",
            "",
            "Contents:",
        ]
        for name, _fig, _desc in figures:
            ext = exported_formats.get(name, "svg")
            readme_lines.append(f"  - {name}.{ext}")
        readme_lines.extend([
            "  - figure_legends.txt",
            "  - latex_captions.tex",
        ])
        if br_results:
            readme_lines.append("  - biorender_templates.txt")
        readme_lines.extend([
            "",
            "Usage:",
            "  SVG files can be directly imported into Adobe Illustrator,",
            "  Inkscape, or BioRender for further editing.",
            "  HTML files (if SVG export unavailable) can be opened in any browser.",
            "  LaTeX captions are ready to paste into your manuscript.",
        ])
        zf.writestr("README.txt", "\n".join(readme_lines))

    buf.seek(0)
    return buf.getvalue()


def _figure_title(name: str) -> str:
    """Convert a snake_case figure name to a readable title."""
    return name.replace("_", " ").title()


# ─── Figure Panel Composer ────────────────────────────────────────


def _render_panel_composer(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
):
    """Render the multi-panel figure composer section."""
    with st.expander("Compose Multi-Panel Figure", expanded=False):
        st.markdown(
            '<div style="color:rgba(60,60,67,0.6);font-size:0.88rem;margin-bottom:12px">'
            "Select charts to compose into a labeled multi-panel figure "
            "(A, B, C, D) for publication."
            "</div>",
            unsafe_allow_html=True,
        )

        # Determine available charts
        available: dict[str, tuple[str, go.Figure | None]] = {}
        if prediction.plddt_per_residue and prediction.residue_ids:
            available["confidence"] = (
                "Per-Residue Confidence Profile",
                _build_confidence_chart(
                    prediction.residue_ids, prediction.plddt_per_residue
                ),
            )
        if trust_audit and trust_audit.regions:
            available["regions"] = (
                "Region Confidence Summary",
                _build_region_chart(trust_audit),
            )
        if bio_context and bio_context.drugs:
            available["drugs"] = (
                "Drug Pipeline",
                _build_drug_chart(bio_context),
            )

        if not available:
            st.info("No charts available. Run a prediction first.")
            return

        # Checkboxes for selection
        st.markdown("**Select panels to include:**")
        check_cols = st.columns(len(available))
        selected: list[tuple[str, str, go.Figure]] = []
        for i, (key, (title, fig)) in enumerate(available.items()):
            if f"panel_select_{key}" not in st.session_state:
                st.session_state[f"panel_select_{key}"] = True
            with check_cols[i]:
                if st.checkbox(title, key=f"panel_select_{key}"):
                    selected.append((key, title, fig))

        if not selected:
            st.info("Select at least one chart to compose a panel figure.")
            return

        # Preview layout
        panel_labels = [chr(65 + i) for i in range(len(selected))]  # A, B, C, D
        st.markdown("**Preview layout:**")

        # Determine grid: 1 chart = 1 col, 2+ = 2 cols x N rows
        n = len(selected)
        n_cols = 1 if n == 1 else min(n, 2)

        for row_start in range(0, n, n_cols):
            row_items = selected[row_start : row_start + n_cols]
            row_labels = panel_labels[row_start : row_start + n_cols]
            preview_cols = st.columns(len(row_items))
            for j, ((_key, title, fig), label) in enumerate(
                zip(row_items, row_labels)
            ):
                with preview_cols[j]:
                    st.markdown(
                        f'<div style="font-weight:700;font-size:1.1rem;'
                        f'color:#007AFF;margin-bottom:4px">{label}</div>',
                        unsafe_allow_html=True,
                    )
                    st.plotly_chart(
                        fig,
                        use_container_width=True,
                        key=f"panel_preview_{label}",
                    )

        # Generate combined output
        if st.button(
            "Export Multi-Panel Figure",
            type="primary",
            use_container_width=True,
            key="export_panel",
        ):
            with st.spinner("Generating multi-panel figure..."):
                try:
                    panel_content, panel_ext, panel_mime = _build_panel_figure(
                        selected, panel_labels, query
                    )
                    st.session_state["panel_figure_data"] = (
                        panel_content,
                        panel_ext,
                        panel_mime,
                    )
                except Exception as e:
                    st.error(f"Panel figure generation failed: {e}")

        panel_data = st.session_state.get("panel_figure_data")
        if panel_data:
            content, ext, mime = panel_data
            mut_str = f"_{query.mutation}" if query.mutation else ""
            st.download_button(
                f"Download Panel Figure (.{ext})",
                content,
                f"Luminous_{query.protein_name}{mut_str}_panels.{ext}",
                mime=mime,
                use_container_width=True,
                key="dl_panel_figure",
            )


def _build_panel_figure(
    selected: list[tuple[str, str, go.Figure]],
    labels: list[str],
    query: ProteinQuery,
) -> tuple[bytes, str, str]:
    """Build a combined multi-panel figure.

    Tries SVG first (via kaleido), falls back to combined HTML.
    Returns (content, extension, mime_type).
    """
    try:
        return _build_panel_svg(selected, labels, query), "svg", "image/svg+xml"
    except Exception:
        pass

    # Fallback: combined HTML
    return _build_panel_html(selected, labels, query), "html", "text/html"


def _build_panel_svg(
    selected: list[tuple[str, str, go.Figure]],
    labels: list[str],
    query: ProteinQuery,
) -> bytes:
    """Build a combined SVG by embedding individual chart SVGs into a grid."""
    import re as re_mod

    panel_width = 600
    panel_height = 400
    n = len(selected)
    n_cols = 1 if n == 1 else 2
    n_rows = (n + n_cols - 1) // n_cols

    total_width = panel_width * n_cols
    total_height = panel_height * n_rows + 40

    svg_parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{total_width}" height="{total_height}" '
        f'style="background:#F2F2F7">',
        f'<text x="{total_width // 2}" y="28" text-anchor="middle" '
        f'fill="#000000" font-size="18" font-family="Arial, sans-serif" '
        f'font-weight="bold">{_svg_escape(query.protein_name)}'
        f'{" (" + _svg_escape(query.mutation) + ")" if query.mutation else ""}'
        f"</text>",
    ]

    for i, ((_key, title, fig), label) in enumerate(zip(selected, labels)):
        row = i // n_cols
        col = i % n_cols
        x_offset = col * panel_width
        y_offset = row * panel_height + 40

        chart_svg = fig.to_image(format="svg").decode("utf-8")
        if "<?xml" in chart_svg:
            chart_svg = chart_svg.split("?>", 1)[1].strip()

        svg_parts.append(f'<g transform="translate({x_offset},{y_offset})">')
        svg_parts.append(
            f'<text x="12" y="22" fill="#007AFF" font-size="20" '
            f'font-family="Arial, sans-serif" font-weight="bold">{label}</text>'
        )

        inner_match = re_mod.search(
            r"<svg[^>]*>(.*)</svg>", chart_svg, re_mod.DOTALL
        )
        if inner_match:
            inner_content = inner_match.group(1)
            svg_parts.append(
                f'<svg x="0" y="28" width="{panel_width}" '
                f'height="{panel_height - 28}">'
            )
            svg_parts.append(inner_content)
            svg_parts.append("</svg>")
        else:
            svg_parts.append(
                f'<text x="{panel_width // 2}" y="{panel_height // 2}" '
                f'text-anchor="middle" fill="rgba(60,60,67,0.6)" font-size="14" '
                f'font-family="Arial, sans-serif">{_svg_escape(title)}</text>'
            )

        svg_parts.append("</g>")

    svg_parts.append("</svg>")
    return "\n".join(svg_parts).encode("utf-8")


def _build_panel_html(
    selected: list[tuple[str, str, go.Figure]],
    labels: list[str],
    query: ProteinQuery,
) -> bytes:
    """Build a combined HTML page with charts in a CSS grid layout."""
    n = len(selected)
    n_cols = 1 if n == 1 else 2

    mut_str = f" ({_svg_escape(query.mutation)})" if query.mutation else ""
    panels_html = []
    for (_key, title, fig), label in zip(selected, labels):
        chart_html = fig.to_html(include_plotlyjs=False, full_html=False)
        panels_html.append(
            f'<div style="border:1px solid rgba(0,0,0,0.12);border-radius:8px;'
            f'padding:12px;background:#F2F2F7">'
            f'<div style="font-weight:700;font-size:1.2rem;color:#007AFF;'
            f'margin-bottom:4px">{label}</div>'
            f'<div style="color:rgba(60,60,67,0.6);font-size:0.85rem;margin-bottom:8px">'
            f"{title}</div>"
            f"{chart_html}"
            f"</div>"
        )

    grid_html = "\n".join(panels_html)
    html = (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>Luminous - {_svg_escape(query.protein_name)}{mut_str}"
        f" - Multi-Panel Figure</title>\n"
        '<script src="https://cdn.plot.ly/plotly-latest.min.js"></script>\n'
        "<style>\n"
        "  body {\n"
        "    background: #F2F2F7;\n"
        "    color: #000000;\n"
        "    font-family: Arial, sans-serif;\n"
        "    margin: 20px;\n"
        "  }\n"
        "  h1 {\n"
        "    text-align: center;\n"
        "    color: #007AFF;\n"
        "    font-size: 1.5rem;\n"
        "  }\n"
        "  .panel-grid {\n"
        "    display: grid;\n"
        f"    grid-template-columns: repeat({n_cols}, 1fr);\n"
        "    gap: 16px;\n"
        "    max-width: 1200px;\n"
        "    margin: 0 auto;\n"
        "  }\n"
        "  .footer {\n"
        "    text-align: center;\n"
        "    color: rgba(60,60,67,0.55);\n"
        "    font-size: 0.8rem;\n"
        "    margin-top: 20px;\n"
        "  }\n"
        "</style>\n</head>\n<body>\n"
        f"<h1>{_svg_escape(query.protein_name)}{mut_str}</h1>\n"
        f'<div class="panel-grid">\n{grid_html}\n</div>\n'
        '<div class="footer">Generated by Luminous '
        "- The AI Structure Interpreter</div>\n"
        "</body>\n</html>"
    )
    return html.encode("utf-8")


# ─── Graphical Abstract Generator ─────────────────────────────────


def _render_graphical_abstract(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
):
    """Render the graphical abstract generator section."""
    st.markdown("#### Graphical Abstract Generator")
    st.markdown(
        '<div style="color:rgba(60,60,67,0.6);font-size:0.88rem;margin-bottom:12px">'
        "Create a clean, publication-ready graphical abstract summarizing "
        "your key finding. Enter a one-sentence finding below."
        "</div>",
        unsafe_allow_html=True,
    )

    # Auto-suggest a finding
    default_finding = _suggest_finding(query, prediction, trust_audit, bio_context)

    finding = st.text_input(
        "One-sentence finding",
        value=default_finding,
        placeholder=(
            "e.g., BRAF V600E destabilizes the kinase domain, "
            "reducing drug binding affinity"
        ),
        key="graphical_abstract_finding",
    )

    if st.button(
        "Generate Graphical Abstract",
        type="primary",
        use_container_width=True,
        key="gen_graphical_abstract",
    ):
        if not finding.strip():
            st.warning("Enter a finding to generate the abstract.")
        else:
            with st.spinner("Generating graphical abstract..."):
                svg_content = _build_graphical_abstract_svg(
                    query, prediction, trust_audit, bio_context, finding.strip()
                )
                st.session_state["graphical_abstract_svg"] = svg_content

    svg_data = st.session_state.get("graphical_abstract_svg")
    if svg_data:
        # Preview
        st.markdown(
            f'<div style="background:#F2F2F7;border:1px solid rgba(0,0,0,0.12);'
            f'border-radius:8px;padding:16px;text-align:center">'
            f"{svg_data}</div>",
            unsafe_allow_html=True,
        )
        mut_str = f"_{query.mutation}" if query.mutation else ""
        st.download_button(
            "Download Graphical Abstract (SVG)",
            svg_data,
            f"Luminous_{query.protein_name}{mut_str}_graphical_abstract.svg",
            mime="image/svg+xml",
            use_container_width=True,
            key="dl_graphical_abstract",
        )


def _suggest_finding(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
) -> str:
    """Auto-suggest a finding based on available data."""
    protein = query.protein_name
    mut = query.mutation

    if trust_audit and mut:
        conf = trust_audit.overall_confidence
        score_pct = f"{trust_audit.confidence_score:.0%}"
        flagged = [r for r in trust_audit.regions if r.flag]
        if flagged:
            region = flagged[0]
            return (
                f"{protein} {mut} shows {conf} confidence ({score_pct}) "
                f"with structural uncertainty in residues "
                f"{region.start_residue}-{region.end_residue}"
            )
        return (
            f"{protein} {mut} structure predicted with "
            f"{conf} confidence ({score_pct})"
        )

    if trust_audit:
        score_pct = f"{trust_audit.confidence_score:.0%}"
        return f"{protein} structure predicted with {score_pct} overall confidence"

    return f"Structural analysis of {protein}"


def _build_graphical_abstract_svg(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    finding: str,
) -> str:
    """Generate an SVG graphical abstract with protein info, metrics, and finding."""
    width, height = 800, 500
    mut_str = query.mutation or ""
    protein = query.protein_name

    # Compute metrics
    confidence_pct = ""
    confidence_color = "rgba(60,60,67,0.6)"
    n_residues = len(prediction.residue_ids) if prediction.residue_ids else 0
    n_drugs = 0
    avg_plddt = 0.0

    if trust_audit:
        confidence_pct = f"{trust_audit.confidence_score:.0%}"
        score_val = trust_audit.confidence_score
        if score_val >= 0.7:
            confidence_color = "#34C759"
        elif score_val >= 0.5:
            confidence_color = "#FF9500"
        else:
            confidence_color = "#FF3B30"

    if prediction.plddt_per_residue:
        avg_plddt = sum(prediction.plddt_per_residue) / len(
            prediction.plddt_per_residue
        )

    if bio_context and bio_context.drugs:
        n_drugs = len(bio_context.drugs)

    # Word-wrap the finding text
    finding_lines = _wrap_text(finding, max_chars=70)
    finding_box_height = 30 + len(finding_lines) * 22

    # Mutation subtitle
    mutation_line = ""
    if mut_str:
        mutation_line = (
            f'<text x="{width // 2}" y="115" text-anchor="middle" fill="#FF9500"'
            f' font-size="18" font-family="Arial, sans-serif"'
            f' font-weight="600">{_svg_escape(mut_str)}</text>'
        )

    # Finding text lines
    finding_text_svg = "".join(
        f'<text x="{width // 2}" y="{392 + i * 22}" text-anchor="middle"'
        f' fill="#000000" font-size="15"'
        f' font-family="Arial, sans-serif">{_svg_escape(line)}</text>'
        for i, line in enumerate(finding_lines)
    )

    drug_label = "drug candidate" if n_drugs == 1 else "drug candidates"

    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" style="background:#F2F2F7">\n'
        "\n"
        "  <defs>\n"
        '    <linearGradient id="bg_grad" x1="0%" y1="0%" x2="100%" y2="100%">\n'
        '      <stop offset="0%" style="stop-color:#FFFFFF;stop-opacity:1" />\n'
        '      <stop offset="100%" style="stop-color:#F2F2F7;stop-opacity:1" />\n'
        "    </linearGradient>\n"
        '    <linearGradient id="accent_grad" x1="0%" y1="0%" x2="100%" y2="0%">\n'
        '      <stop offset="0%" style="stop-color:#007AFF;stop-opacity:1" />\n'
        '      <stop offset="100%" style="stop-color:#34C759;stop-opacity:1" />\n'
        "    </linearGradient>\n"
        '    <marker id="ga_arrow" viewBox="0 0 10 10" refX="9" refY="5"'
        ' markerWidth="8" markerHeight="8" orient="auto-start-reverse">\n'
        '      <path d="M 0 0 L 10 5 L 0 10 z" fill="#007AFF"/>\n'
        "    </marker>\n"
        "  </defs>\n"
        "\n"
        f'  <rect width="{width}" height="{height}"'
        ' fill="url(#bg_grad)" rx="12"/>\n'
        f'  <rect x="0" y="0" width="{width}" height="4"'
        ' fill="url(#accent_grad)" rx="2"/>\n'
        "\n"
        '  <text x="30" y="38" fill="#007AFF" font-size="14"'
        ' font-family="Arial, sans-serif" font-weight="600"'
        " letter-spacing=\"2\">LUMINOUS</text>\n"
        f'  <text x="{width - 30}" y="38" fill="rgba(60,60,67,0.55)" font-size="11"'
        ' font-family="Arial, sans-serif"'
        " text-anchor=\"end\">AI Structure Interpreter</text>\n"
        "\n"
        f'  <line x1="30" y1="50" x2="{width - 30}" y2="50"'
        ' stroke="rgba(0,0,0,0.06)" stroke-width="1"/>\n'
        "\n"
        f'  <text x="{width // 2}" y="88" text-anchor="middle" fill="#000000"'
        ' font-size="28" font-family="Arial, sans-serif"'
        f" font-weight=\"bold\">{_svg_escape(protein)}</text>\n"
        f"  {mutation_line}\n"
        "\n"
        "  <!-- Flow: Structure -> Trust Audit -> Insights -->\n"
        '  <rect x="60" y="140" width="180" height="70" rx="8"'
        ' fill="#F2F2F7" stroke="rgba(0,0,0,0.06)" stroke-width="1.5"/>\n'
        '  <text x="150" y="168" text-anchor="middle" fill="#007AFF"'
        ' font-size="13" font-family="Arial, sans-serif"'
        " font-weight=\"700\">STRUCTURE</text>\n"
        '  <text x="150" y="192" text-anchor="middle" fill="rgba(60,60,67,0.6)"'
        f' font-size="12" font-family="Arial, sans-serif">'
        f"{n_residues} residues</text>\n"
        "\n"
        '  <line x1="240" y1="175" x2="290" y2="175" stroke="#007AFF"'
        ' stroke-width="2" marker-end="url(#ga_arrow)"/>\n'
        "\n"
        '  <rect x="300" y="140" width="180" height="70" rx="8"'
        ' fill="#F2F2F7" stroke="rgba(0,0,0,0.06)" stroke-width="1.5"/>\n'
        '  <text x="390" y="168" text-anchor="middle" fill="#34C759"'
        ' font-size="13" font-family="Arial, sans-serif"'
        " font-weight=\"700\">TRUST AUDIT</text>\n"
        f'  <text x="390" y="192" text-anchor="middle" fill="{confidence_color}"'
        ' font-size="12" font-family="Arial, sans-serif">'
        f"{confidence_pct or 'N/A'} confidence</text>\n"
        "\n"
        '  <line x1="480" y1="175" x2="530" y2="175" stroke="#007AFF"'
        ' stroke-width="2" marker-end="url(#ga_arrow)"/>\n'
        "\n"
        '  <rect x="540" y="140" width="200" height="70" rx="8"'
        ' fill="#F2F2F7" stroke="rgba(0,0,0,0.06)" stroke-width="1.5"/>\n'
        '  <text x="640" y="168" text-anchor="middle" fill="#FF9500"'
        ' font-size="13" font-family="Arial, sans-serif"'
        " font-weight=\"700\">INSIGHTS</text>\n"
        '  <text x="640" y="192" text-anchor="middle" fill="rgba(60,60,67,0.6)"'
        ' font-size="12" font-family="Arial, sans-serif">'
        f"{n_drugs} {drug_label}</text>\n"
        "\n"
        "  <!-- Central metric -->\n"
        '  <rect x="250" y="235" width="300" height="80" rx="10"'
        f' fill="#F2F2F7" stroke="{confidence_color}" stroke-width="2"/>\n'
        '  <text x="400" y="265" text-anchor="middle" fill="#000000"'
        ' font-size="14" font-family="Arial, sans-serif">Mean pLDDT</text>\n'
        f'  <text x="400" y="298" text-anchor="middle" fill="{confidence_color}"'
        ' font-size="30" font-family="Arial, sans-serif"'
        f" font-weight=\"bold\">{avg_plddt:.1f}</text>\n"
        "\n"
        '  <line x1="400" y1="315" x2="400" y2="345" stroke="#007AFF"'
        ' stroke-width="2" marker-end="url(#ga_arrow)"/>\n'
        "\n"
        "  <!-- Finding box -->\n"
        f'  <rect x="60" y="350" width="{width - 120}"'
        f' height="{finding_box_height}" rx="8"'
        ' fill="#F2F2F7" stroke="#007AFF" stroke-width="1.5"/>\n'
        '  <text x="80" y="372" fill="#007AFF" font-size="11"'
        ' font-family="Arial, sans-serif" font-weight="700"'
        " letter-spacing=\"1.5\">KEY FINDING</text>\n"
        f"  {finding_text_svg}\n"
        "\n"
        f'  <text x="{width // 2}" y="{height - 14}" text-anchor="middle"'
        ' fill="rgba(60,60,67,0.55)" font-size="10" font-family="Arial, sans-serif">'
        "Powered by Tamarind Bio (Boltz-2) | Anthropic Claude"
        " | BioRender | Modal</text>\n"
        "\n"
        "</svg>"
    )
    return svg


def _svg_escape(text: str) -> str:
    """Escape special characters for SVG text content."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _wrap_text(text: str, max_chars: int = 70) -> list[str]:
    """Wrap text into lines of approximately max_chars width."""
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if current and len(current) + 1 + len(word) > max_chars:
            lines.append(current)
            current = word
        else:
            current = f"{current} {word}" if current else word
    if current:
        lines.append(current)
    return lines if lines else [text]
