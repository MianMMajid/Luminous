from __future__ import annotations

import json

import streamlit as st

mvs = None  # lazy-loaded in render_structure_viewer() to avoid ~0.5s startup cost

from src.models import PredictionResult, ProteinQuery, TrustAudit
from src.services import AnalysisSessionService, PredictionService
from src.trust_auditor import get_residue_flags
from src.utils import (
    build_trust_annotations,
    confidence_emoji,
    run_async,
)


def render_structure_viewer():
    """Tab 2: 3D structure viewer with trust audit panel -- THE HERO SCREEN."""
    if not st.session_state.get("query_parsed"):
        from components.empty_state import render_empty_state
        render_empty_state("structure")
        return
    global mvs
    if mvs is None:
        try:
            import molviewspec as _mvs
            mvs = _mvs
        except Exception:
            pass
    if mvs is None:
        st.warning(
            "3D viewer requires Python 3.10+. "
            "Current version doesn't support molviewspec. "
            "Run: `brew install python@3.12 && python3.12 -m pip install -r requirements.txt`"
        )
        return

    query: ProteinQuery | None = st.session_state.get("parsed_query")
    if query is None:
        st.warning("Query data not available. Please re-enter your query.")
        return
    prediction: PredictionResult | None = st.session_state.get("prediction_result")

    # Run prediction if not done
    if prediction is None:
        _run_prediction(query)
        prediction = st.session_state.get("prediction_result")
        if prediction is None:
            return

    # Build trust audit if not done
    if st.session_state.get("trust_audit") is None:
        try:
            trust_audit = AnalysisSessionService.ensure_trust_audit(
                st.session_state,
                query,
                prediction,
            )
        except Exception as e:
            st.error(
                f"Trust audit could not be completed: {e}\n\n"
                "The structure is still shown below. Trust metrics are unavailable."
            )
            # Don't return — continue rendering the structure without trust audit

    trust_audit: TrustAudit | None = st.session_state.get("trust_audit")

    # Compact header with protein metadata
    mut_str = f" ({query.mutation})" if query.mutation else ""
    source_str = prediction.compute_source.upper() if prediction and prediction.compute_source else "Predicted"
    conf_str = ""
    if trust_audit:
        conf_str = f' · {confidence_emoji(trust_audit.overall_confidence)} {trust_audit.overall_confidence.title()} confidence'
    st.markdown(
        f'<div class="lumi-tab-header">'
        f'<div class="tab-title">{query.protein_name}{mut_str}</div>'
        f'<div class="tab-subtitle">{source_str} structure{conf_str}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Guided Tour — quick-focus buttons for key structural regions
    _render_guided_tour(query, prediction, trust_audit)

    # Layout: 3D viewer (left) + Trust audit panel (right)
    if trust_audit:
        viewer_col, audit_col = st.columns([3, 1])
        with viewer_col:
            _render_3d_viewer(query, prediction, trust_audit)
        with audit_col:
            _render_trust_panel(query, trust_audit)
    else:
        _render_3d_viewer(query, prediction, trust_audit)

    # Sequence viewer (full width, below 3D viewer)
    from components.sequence_viewer import render_sequence_viewer

    render_sequence_viewer(query, prediction, trust_audit)

    # Binding affinity panel (if available)
    if prediction.affinity_json:
        from components.affinity_panel import render_affinity_panel

        render_affinity_panel(query, prediction)

    # Mutation Structural Impact (if mutation specified)
    if query.mutation:
        from components.mutation_impact import render_mutation_impact

        bio_context = st.session_state.get("bio_context")
        render_mutation_impact(query, prediction, trust_audit, bio_context)

    # ── Query-aware panel rendering ──
    # Only show panels relevant to the scientist's actual question
    qtype = query.question_type

    # Variant Pathogenicity Landscape — mutation/druggability context
    if qtype in ("mutation_impact", "druggability") or query.mutation:
        from components.variant_landscape import render_variant_landscape

        render_variant_landscape(query, prediction)

    # Drug Resistance Mechanism Viewer — needs both drug context AND a mutation
    if qtype in ("druggability", "mutation_impact") and query.mutation:
        from components.drug_resistance import render_drug_resistance

        render_drug_resistance(
            query, prediction, st.session_state.get("bio_context")
        )

    # Structural Insights — always relevant but adapts internally
    from components.structural_insights import render_structural_insights

    render_structural_insights(query, prediction)

    # Disorder Region Detector — structure/binding/mutation context
    if qtype != "druggability":
        from components.disorder_detector import render_disorder_detection

        render_disorder_detection(query, prediction, trust_audit)

    # Auto-Analyze — one-click recommended analyses
    st.divider()
    _render_auto_analyze(query, prediction)

    # ── Advanced Analysis & Deep Exploration ──
    # Collapses secondary tools to reduce cognitive overload on the hero screen.
    st.divider()
    with st.expander("Advanced Analysis & Deep Exploration", expanded=False):
        st.caption(
            "Residue-level dashboard, Tamarind Bio tools, confidence heatmaps, "
            "electrostatics, AlphaFold comparison, and data export."
        )
        adv_tabs = st.tabs([
            "Residue Dashboard",
            "Tamarind Bio",
            "Confidence & PAE",
            "Comparison",
            "Data Export",
        ])

        # ── Tab 1: Residue Dashboard ──
        with adv_tabs[0]:
            from components.residue_dashboard import render_residue_dashboard

            structure_analysis = st.session_state.get("structure_analysis") or {}
            if not structure_analysis and prediction.pdb_content:
                try:
                    from src.structure_analysis import analyze_structure
                    import re
                    mutation_pos = None
                    if query.mutation:
                        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
                        if m:
                            mutation_pos = int(m.group(1))
                    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
                    structure_analysis = analyze_structure(prediction.pdb_content, mutation_pos=mutation_pos, first_chain=first_chain)
                    st.session_state["structure_analysis"] = structure_analysis
                    st.session_state[f"struct_analysis_{query.protein_name}_{query.mutation}"] = structure_analysis
                except Exception:
                    pass
            variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
            render_residue_dashboard(
                structure_analysis,
                prediction.plddt_per_residue or [],
                query,
                variant_data,
            )

        # ── Tab 2: Tamarind Bio ──
        with adv_tabs[1]:
            from components.tamarind_panel import render_tamarind_panel

            render_tamarind_panel(query, prediction)

            st.divider()
            from components.pipeline_builder import render_pipeline_builder

            render_pipeline_builder(query, prediction)

        # ── Tab 3: Confidence Heatmap, PAE, Electrostatics ──
        with adv_tabs[2]:
            conf_tab1, conf_tab2, conf_tab3, conf_tab4 = st.tabs([
                "Confidence Heatmap", "PAE Domain Map",
                "Electrostatic Surface", "AlphaFold Comparison",
            ])
            with conf_tab1:
                from components.confidence_heatmap import render_confidence_heatmap

                render_confidence_heatmap(prediction)
            with conf_tab2:
                from components.pae_viewer import render_pae_viewer

                render_pae_viewer(prediction.confidence_json or {}, query)
            with conf_tab3:
                from components.electrostatics_viewer import render_electrostatics_panel

                render_electrostatics_panel(prediction.pdb_content, query)
            with conf_tab4:
                from components.alphafold_compare import render_alphafold_comparison

                render_alphafold_comparison(query, prediction)

        # ── Tab 4: Variant Comparison ──
        with adv_tabs[3]:
            from components.comparison_mode import render_comparison_mode

            render_comparison_mode(query, prediction, trust_audit)

        # ── Tab 5: Data Export ──
        with adv_tabs[4]:
            if prediction.plddt_per_residue:
                from components.playground import _build_plddt_chart_json, pin_button

                mean_plddt = sum(prediction.plddt_per_residue) / len(prediction.plddt_per_residue)
                pin_button(
                    "pLDDT Distribution",
                    f"{len(prediction.plddt_per_residue)} residues, mean pLDDT {mean_plddt:.1f}",
                    "chart",
                    {"plddt": prediction.plddt_per_residue, "residue_ids": prediction.residue_ids},
                    _build_plddt_chart_json(prediction.plddt_per_residue, prediction.residue_ids),
                    key="pin_plddt_dist",
                )

            export_col1, export_col2 = st.columns(2)
            with export_col1:
                if prediction.plddt_per_residue:
                    import pandas as pd

                    if st.button("Send to Statistics", key="struct_send_stats",
                                 help="Send pLDDT data to the Statistics tab for analysis",
                                 width="stretch"):
                        n = min(
                            len(prediction.residue_ids),
                            len(prediction.chain_ids),
                            len(prediction.plddt_per_residue),
                        )
                        if n > 0:
                            df = pd.DataFrame({
                                "residue_id": prediction.residue_ids[:n],
                                "chain": prediction.chain_ids[:n],
                                "plddt": prediction.plddt_per_residue[:n],
                            })
                            st.session_state["stats_data"] = df
                            st.toast("pLDDT data sent to Statistics tab!")

            with export_col2:
                if prediction.plddt_per_residue:
                    import pandas as pd
                    import io as _io

                    n = min(
                        len(prediction.residue_ids),
                        len(prediction.chain_ids) if prediction.chain_ids else len(prediction.residue_ids),
                        len(prediction.plddt_per_residue),
                    )
                    if st.button("Download All Residue Data (CSV)", key="export_residue_csv",
                                 help="Export comprehensive per-residue analysis as CSV",
                                 width="stretch"):
                        data = {"residue_id": prediction.residue_ids[:n]}
                        if prediction.chain_ids:
                            data["chain"] = prediction.chain_ids[:n]
                        if prediction.plddt_per_residue:
                            data["plddt"] = prediction.plddt_per_residue[:n]

                        flex_data = st.session_state.get(f"flexibility_{query.protein_name}")
                        if flex_data and flex_data.get("flexibility") and flex_data.get("residue_ids"):
                            flex_map = dict(zip(flex_data["residue_ids"], flex_data["flexibility"]))
                            data["flexibility"] = [flex_map.get(r, None) for r in data["residue_id"]]

                        pocket_data = st.session_state.get(f"pockets_{query.protein_name}")
                        if pocket_data and pocket_data.get("residue_pocket_scores"):
                            scores = pocket_data["residue_pocket_scores"]
                            data["pocket_score"] = [scores.get(r, 0.0) for r in data["residue_id"]]

                        export_df = pd.DataFrame(data)
                        csv_buffer = _io.StringIO()
                        export_df.to_csv(csv_buffer, index=False)
                        st.download_button(
                            "Save CSV",
                            csv_buffer.getvalue(),
                            f"{query.protein_name}_residue_annotations.csv",
                            mime="text/csv",
                            key="save_residue_csv",
                        )


def _run_prediction(query: ProteinQuery):
    """Submit Boltz-2 prediction or load precomputed/RCSB results.

    Fallback chain: precomputed → Tamarind API → Modal H100 → RCSB PDB
    """
    backend = st.session_state.get("compute_backend", "auto")

    dispatch = PredictionService.run_prediction(
        query,
        st.session_state,
        backend=backend,
        num_recycles=st.session_state.get("boltz_recycling_steps", 3),
        use_msa=st.session_state.get("boltz_use_msa", True),
        predict_affinity=st.session_state.get("boltz_predict_affinity", True),
    )

    if dispatch.status == "loaded":
        st.caption(dispatch.message)
        return
    if dispatch.status == "running":
        st.info(dispatch.message)
        _render_prediction_progress()
        return
    if dispatch.status == "submitted":
        if dispatch.skipped_backends:
            st.caption(f"Skipped backends: {', '.join(dispatch.skipped_backends)}")
        st.info(dispatch.message)
        _render_prediction_progress()
        return
    if dispatch.skipped_backends:
        st.caption(f"Skipped backends: {', '.join(dispatch.skipped_backends)}")
    st.warning(dispatch.message)


def _submit_prediction_background(query: ProteinQuery, backend: str) -> bool:
    """Submit prediction as a background task. Returns True if submitted."""
    from src.task_manager import task_manager

    num_recycles = st.session_state.get("boltz_recycling_steps", 3)
    use_msa = st.session_state.get("boltz_use_msa", True)
    predict_affinity = st.session_state.get("boltz_predict_affinity", True)

    skipped: list[str] = []

    if backend in ("auto", "tamarind"):
        from src.config import TAMARIND_API_KEY
        if TAMARIND_API_KEY:
            from src.background_tasks import run_prediction_tamarind
            task_manager.submit(
                task_id="prediction",
                fn=run_prediction_tamarind,
                args=(query.sequence, query.protein_name, query.mutation),
                kwargs={
                    "predict_affinity": predict_affinity,
                    "num_recycles": num_recycles,
                    "use_msa": use_msa,
                },
                label="Boltz-2 structure prediction (Tamarind)",
                target_keys={"__direct__": "_prediction_raw"},
            )
            return True
        else:
            skipped.append("Tamarind (no API key)")

    if backend in ("auto", "modal"):
        from src.modal_client import is_modal_available
        if is_modal_available():
            from src.background_tasks import run_prediction_modal
            task_manager.submit(
                task_id="prediction",
                fn=run_prediction_modal,
                args=(query.sequence, query.protein_name, query.mutation),
                kwargs={"predict_affinity": predict_affinity},
                label="Boltz-2 structure prediction (Modal H100)",
                target_keys={"__direct__": "_prediction_raw"},
            )
            return True
        else:
            skipped.append("Modal (not configured)")

    if skipped:
        st.caption(f"Skipped backends: {', '.join(skipped)}")
    return False


def _render_prediction_progress():
    """Show a waiting card while prediction runs in background."""
    st.markdown(
        '<div class="glow-card" style="text-align:center;padding:32px 24px;'
        'border-color:rgba(255,149,0,0.3)">'
        '<div style="font-size:2rem;margin-bottom:8px">🧬</div>'
        '<div style="font-weight:600;font-size:1.1rem;margin-bottom:6px">'
        'Structure prediction running...</div>'
        '<div style="font-size:0.88rem;color:rgba(60,60,67,0.6)">'
        'Boltz-2 is predicting the 3D structure. This typically takes 30s–5min.<br>'
        'Feel free to explore other tabs — Lumi will notify you when it\'s done.'
        '</div></div>',
        unsafe_allow_html=True,
    )


def _run_tamarind(query: ProteinQuery) -> bool:
    """Run Boltz-2 prediction via Tamarind Bio API. Returns True on success."""
    from src.config import TAMARIND_API_KEY

    if not TAMARIND_API_KEY:
        st.info("No Tamarind API key configured. Trying next backend...")
        return False

    with st.status("Running Boltz-2 prediction via Tamarind Bio...", expanded=True) as status:
        try:
            st.write("Submitting prediction job...")

            job_name = f"luminous_{query.protein_name}_{query.mutation or 'wt'}"
            from src.tamarind_client import download_results, poll_job, submit_boltz2_job

            num_recycles = st.session_state.get("boltz_recycling_steps", 3)
            use_msa = st.session_state.get("boltz_use_msa", True)
            predict_affinity = st.session_state.get("boltz_predict_affinity", True)

            async def _run():
                await submit_boltz2_job(
                    query.sequence, job_name,
                    predict_affinity=predict_affinity,
                    num_recycling_steps=num_recycles,
                    use_msa=use_msa,
                )
                await poll_job(job_name)
                return await download_results(job_name)

            result = run_async(_run())
            pdb = result.get("pdb", result.get("structure", ""))
            confidence = result.get("confidence", {})
            affinity = result.get("affinity")
            _store_prediction(pdb, confidence, affinity, source="tamarind")
            status.update(label="Prediction complete!", state="complete")
            return True
        except Exception as e:
            status.update(label="Tamarind failed — trying next backend", state="error")
            st.warning(f"Tamarind API error: {e}")
            return False


def _run_modal(query: ProteinQuery) -> bool:
    """Run Boltz-2 prediction via Modal H100 GPU. Returns True on success."""
    from src.modal_client import is_modal_available

    if not is_modal_available():
        st.info("Modal not available. Trying next backend...")
        return False

    with st.status("Running Boltz-2 on Modal H100 GPU...", expanded=True) as status:
        try:
            st.write("Submitting to Modal serverless GPU...")
            from src.modal_client import run_modal_prediction

            job_name = f"luminous_{query.protein_name}_{query.mutation or 'wt'}"
            predict_affinity = st.session_state.get("boltz_predict_affinity", True)
            pdb, confidence, affinity = run_modal_prediction(
                query.sequence, job_name, predict_affinity=predict_affinity
            )
            _store_prediction(pdb, confidence, affinity, source="modal")
            status.update(label="Modal prediction complete!", state="complete")
            return True
        except Exception as e:
            status.update(label="Modal failed — trying next backend", state="error")
            st.warning(f"Modal error: {e}")
            return False


def _load_precomputed_context(context_data: dict):
    """Load precomputed biological context into session state."""
    AnalysisSessionService.store_bio_context(st.session_state, context_data)


def _fetch_rcsb_background(uniprot_id: str) -> dict:
    """Fetch RCSB PDB structure in a background thread (no st.* calls).

    Returns dict compatible with _apply_prediction_result in notification_poller.
    """
    import httpx

    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
    search_query = {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                "operator": "exact_match",
                "value": uniprot_id,
            },
        },
        "return_type": "entry",
        "request_options": {
            "results_content_type": ["experimental"],
            "return_all_hits": False,
        },
    }
    resp = httpx.post(search_url, json=search_query, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError("RCSB PDB search failed")

    results = resp.json()
    hits = results.get("result_set", [])
    if not hits:
        raise RuntimeError("No experimental structures found in RCSB PDB")

    pdb_id = hits[0].get("identifier", "")
    if not pdb_id:
        raise RuntimeError("No PDB identifier in search results")

    pdb_resp = httpx.get(
        f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=30
    )
    if pdb_resp.status_code != 200:
        raise RuntimeError(f"Could not download PDB {pdb_id}")

    return {
        "pdb": pdb_resp.text,
        "confidence": {},
        "source": "rcsb",
        "skip_plddt": True,
    }


def _store_prediction(
    pdb_content: str, confidence: dict,
    affinity: dict | None = None, source: str = "precomputed",
    skip_plddt: bool = False,
):
    """Parse PDB and store prediction result in session state.

    Set skip_plddt=True for experimental structures (RCSB) where B-factors
    are crystallographic, not pLDDT confidence scores.
    """
    AnalysisSessionService.store_prediction(
        st.session_state,
        pdb_content=pdb_content,
        confidence=confidence,
        affinity=affinity,
        source=source,
        skip_plddt=skip_plddt,
    )


def _render_molstar_with_annotations(
    prediction: PredictionResult,
    annotations: list[dict],
    height: int = 600,
):
    """Reusable Mol* renderer with per-residue color + tooltip annotations.

    Each annotation dict: {"label_asym_id": str, "label_seq_id": int, "color": str, "tooltip": str}
    """
    if not prediction.pdb_content:
        st.warning("No structure data available.")
        return

    builder = mvs.create_builder()
    structure = (
        builder.download(url="structure.pdb")
        .parse(format="pdb")
        .model_structure()
    )
    rep = structure.component().representation(type="cartoon")
    if annotations:
        rep.color_from_uri(
            uri="annot_colors.json", format="json", schema="residue"
        )
        structure.tooltip_from_uri(
            uri="annot_tooltips.json", format="json", schema="residue"
        )

    data: dict[str, bytes] = {
        "structure.pdb": prediction.pdb_content.encode("utf-8"),
    }
    if annotations:
        color_data = [
            {"label_asym_id": a["label_asym_id"], "label_seq_id": a["label_seq_id"], "color": a["color"]}
            for a in annotations
        ]
        tooltip_data = [
            {"label_asym_id": a["label_asym_id"], "label_seq_id": a["label_seq_id"], "tooltip": a.get("tooltip", "")}
            for a in annotations
        ]
        data["annot_colors.json"] = json.dumps(color_data).encode("utf-8")
        data["annot_tooltips.json"] = json.dumps(tooltip_data).encode("utf-8")

    mvs.molstar_streamlit(builder, data=data, height=height)


def _render_3d_viewer(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render the Mol* 3D viewer with trust coloring."""
    if not prediction.pdb_content:
        st.warning("No structure data available.")
        return

    # Color mode selector
    color_modes = [
        "Trust (pLDDT)", "AlphaMissense", "Domains",
        "Flexibility (ANM)", "NMA Animation", "Morph Animation",
        "Binding Pockets",
        "Charge Surface", "Structure Diff",
        "Conservation", "Hydrophobicity", "Residue Depth",
        "PSN Communities", "Mutation Impact",
    ]
    color_mode = st.radio(
        "Color by:",
        color_modes,
        horizontal=True,
        key="structure_color_mode",
    )

    # Dispatch to overlay renderers
    if color_mode == "AlphaMissense":
        _render_alphamissense_overlay(query, prediction, trust_audit)
        return
    elif color_mode == "Domains":
        _render_domain_overlay(query, prediction, trust_audit)
        return
    elif color_mode == "Flexibility (ANM)":
        _render_flexibility_overlay(query, prediction, trust_audit)
        return
    elif color_mode == "NMA Animation":
        _render_nma_animation(query, prediction, trust_audit)
        return
    elif color_mode == "Morph Animation":
        _render_morph_animation(query, prediction, trust_audit)
        return
    elif color_mode == "Binding Pockets":
        _render_pocket_overlay(query, prediction, trust_audit)
        return
    elif color_mode == "Charge Surface":
        _render_charge_surface(query, prediction, trust_audit)
        return
    elif color_mode == "Structure Diff":
        _render_structure_diff(query, prediction, trust_audit)
        return
    elif color_mode == "Conservation":
        _render_conservation_overlay(query, prediction)
        return
    elif color_mode == "Hydrophobicity":
        _render_hydrophobicity_overlay(query, prediction)
        return
    elif color_mode == "Residue Depth":
        _render_depth_overlay(query, prediction)
        return
    elif color_mode == "PSN Communities":
        _render_psn_overlay(query, prediction)
        return
    elif color_mode == "Mutation Impact":
        _render_mutation_energy_delta(query, prediction)
        return

    # Default: Trust coloring
    # Build per-residue annotations
    flags = get_residue_flags(
        query, prediction.residue_ids, prediction.plddt_per_residue
    )
    annotations = build_trust_annotations(
        prediction.chain_ids,
        prediction.residue_ids,
        prediction.plddt_per_residue,
        flags,
    )

    # Build MolViewSpec state
    builder = mvs.create_builder()
    structure = (
        builder.download(url="structure.pdb")
        .parse(format="pdb")
        .model_structure()
    )

    # Cartoon representation with per-residue trust coloring
    rep = structure.component(selector="polymer").representation(type="cartoon")
    rep.color(color="#888888")

    if annotations:
        rep.color_from_uri(
            uri="trust_colors.json", format="json", schema="residue"
        )
        structure.tooltip_from_uri(
            uri="trust_tooltips.json", format="json", schema="residue"
        )

    # Overlay pathogenic variant positions on 3D structure
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    pathogenic_positions: dict[int, list[str]] = {}
    if variant_data and variant_data.get("pathogenic_positions"):
        for pos_key, names in variant_data["pathogenic_positions"].items():
            try:
                pathogenic_positions[int(pos_key)] = names
            except (ValueError, TypeError):
                pass

    # Enhance tooltips with variant information
    if pathogenic_positions and annotations:
        for ann in annotations:
            seq_id = ann.get("label_seq_id")
            if seq_id in pathogenic_positions:
                names = pathogenic_positions[seq_id]
                name_str = ", ".join(names) if isinstance(names, list) else str(names)
                ann["tooltip"] += f" | PATHOGENIC: {name_str}"
                ann["color"] = "#E00000"  # ClinVar standard red for pathogenic sites

    # Add ball+stick representations for pathogenic variant residues
    if pathogenic_positions:
        first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
        for pos in pathogenic_positions:
            try:
                comp = structure.component(
                    selector=mvs.ComponentExpression(
                        label_asym_id=first_chain,
                        label_seq_id=pos,
                    )
                )
                comp.representation(type="ball_and_stick").color(color="#E00000")
            except Exception:
                pass  # MolViewSpec API may not support this selector form

        # Mark the queried mutation position specially (gold)
        if query.mutation:
            import re as _re

            m = _re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
            if m:
                mut_pos = int(m.group(1))
                try:
                    comp = structure.component(
                        selector=mvs.ComponentExpression(
                            label_asym_id=first_chain,
                            label_seq_id=mut_pos,
                        )
                    )
                    comp.representation(type="ball_and_stick").color(
                        color="#FFCC00"
                    )
                except Exception:
                    pass

    # Build color and tooltip JSON
    color_data = [
        {
            "label_asym_id": a["label_asym_id"],
            "label_seq_id": a["label_seq_id"],
            "color": a["color"],
        }
        for a in annotations
    ]
    tooltip_data = [
        {
            "label_asym_id": a["label_asym_id"],
            "label_seq_id": a["label_seq_id"],
            "tooltip": a["tooltip"],
        }
        for a in annotations
    ]

    # Apply guided tour focus (highlight + zoom to selected residues)
    tour_residues = st.session_state.get("tour_focus")
    if tour_residues:
        first_chain_id = prediction.chain_ids[0] if prediction.chain_ids else "A"
        for res_id in tour_residues:
            try:
                focus_comp = structure.component(
                    selector=mvs.ComponentExpression(
                        label_asym_id=first_chain_id,
                        label_seq_id=int(res_id),
                    )
                )
                focus_comp.representation(type="ball_and_stick").color(color="#FF9500")
                focus_comp.focus()
            except Exception:
                pass

    # Render with MVSX data archive
    data = {
        "structure.pdb": prediction.pdb_content.encode("utf-8"),
    }
    if annotations:
        data["trust_colors.json"] = json.dumps(color_data).encode("utf-8")
        data["trust_tooltips.json"] = json.dumps(tooltip_data).encode("utf-8")

    mvs.molstar_streamlit(builder, data=data, height=600)

    # Show pathogenic variant note below the viewer
    if pathogenic_positions:
        n = len(pathogenic_positions)
        st.caption(
            f"\U0001f534 {n} pathogenic variant site{'s' if n != 1 else ''} "
            "highlighted in red on structure. "
            "Hover over red residues to see variant names."
        )
        if query.mutation:
            st.caption(
                "\U0001f7e1 Queried mutation position highlighted in gold."
            )

    # Color legend
    _render_color_legend()

    # Compute provenance badge
    _render_provenance_badge(prediction)


@st.cache_data(show_spinner="Computing flexibility (ANM)...")
def _compute_flexibility(pdb_content: str, chain: str | None) -> dict:
    from src.flexibility_analysis import compute_anm_flexibility
    return compute_anm_flexibility(pdb_content, chain)


@st.cache_data(show_spinner="Predicting binding pockets...")
def _compute_pockets(pdb_content: str, pdb_id: str | None = None) -> dict:
    from src.dogsite_pockets import predict_pockets_with_fallback
    return predict_pockets_with_fallback(pdb_content, pdb_id=pdb_id)


@st.cache_data(show_spinner="Generating NMA trajectory...")
def _compute_nma_trajectory(
    pdb_content: str, chain: str | None, mode_index: int, n_steps: int, rmsd: float
) -> dict:
    from src.flexibility_analysis import generate_nma_trajectory
    return generate_nma_trajectory(pdb_content, chain, mode_index, n_steps, rmsd)


@st.cache_data(show_spinner="Computing surface charge...")
def _compute_surface_charge(pdb_content: str, chain: str | None) -> dict:
    from src.surface_properties import compute_surface_properties
    return compute_surface_properties(pdb_content, chain)


def _render_flexibility_overlay(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by ANM flexibility."""
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"

    # Use precomputed flexibility if available
    flex_key = f"flexibility_{query.protein_name}"
    flex_data = st.session_state.get(flex_key)
    if flex_data is None:
        try:
            flex_data = _compute_flexibility(prediction.pdb_content, first_chain)
            st.session_state[flex_key] = flex_data
        except Exception as e:
            st.warning(f"Flexibility analysis failed: {e}")
            return

    if not flex_data.get("residue_ids"):
        st.info("Not enough residues for flexibility analysis.")
        return

    # Build color annotations: blue (rigid) → white → red (flexible)
    annotations = []
    chain = first_chain or "A"
    for res_id, flex_val in zip(flex_data.get("residue_ids", []), flex_data.get("flexibility", [])):
        if flex_val < 0.3:
            r, g, b = 30, 80, 200  # Blue = rigid
        elif flex_val < 0.7:
            frac = (flex_val - 0.3) / 0.4
            r = int(30 + frac * 225)
            g = int(80 + frac * 175)
            b = int(200 - frac * 200)
        else:
            r, g, b = 220, 50, 50  # Red = flexible

        color = f"#{r:02x}{g:02x}{b:02x}"
        label = f"Res {res_id}: flexibility {flex_val:.2f}"
        if res_id in flex_data.get("hinge_residues", []):
            label += " (HINGE)"
        annotations.append({
            "label_asym_id": chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": label,
        })

    # Render with MolViewSpec
    _render_molstar_with_annotations(prediction, annotations)

    # Flexibility legend
    cols = st.columns(3)
    for col, (color, label) in zip(cols, [
        ("#1E50C8", "Rigid (<0.3)"),
        ("#CCCCCC", "Intermediate"),
        ("#DC3232", "Flexible (>0.7)"),
    ]):
        col.markdown(
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:16px;height:16px;background:{color};border-radius:3px"></div>'
            f'<span style="font-size:0.85em">{label}</span></div>',
            unsafe_allow_html=True,
        )

    # Stats panel
    import plotly.graph_objects as go

    st.markdown("#### Flexibility Profile")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=flex_data.get("residue_ids", []),
        y=flex_data.get("flexibility", []),
        mode="lines",
        line=dict(color="#DC3232", width=2),
        name="Flexibility",
        hovertemplate="Residue %{x}<br>Flexibility: %{y:.2f}<extra></extra>",
    ))
    # Overlay pLDDT for comparison
    if prediction.plddt_per_residue:
        fig.add_trace(go.Scatter(
            x=prediction.residue_ids,
            y=[p / 100 for p in prediction.plddt_per_residue],
            mode="lines",
            line=dict(color="#007AFF", width=1, dash="dot"),
            name="pLDDT (normalized)",
            yaxis="y",
        ))
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=250,
        margin=dict(t=10, b=30, l=50, r=20),
        yaxis_title="Score (0-1)",
        xaxis_title="Residue",
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, width="stretch")

    # Key metrics
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Rigid Core", f"{flex_data.get('pct_rigid', 0):.0%}")
    mcol2.metric("Flexible Loops", f"{flex_data.get('pct_flexible', 0):.0%}")
    hinge_res = flex_data.get("hinge_residues", [])
    mcol3.metric("Hinge Residues", len(hinge_res))

    if hinge_res:
        st.caption(f"Hinge residues: {', '.join(map(str, hinge_res[:15]))}")

    _render_provenance_badge(prediction)


def _render_nma_animation(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render animated protein dynamics using Normal Mode Analysis.

    Generates multi-model PDB from ProDy traverseMode() and displays
    it in Mol* with model cycling for animation playback.
    """
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"

    # Controls
    ctrl_cols = st.columns([1, 1, 1])
    with ctrl_cols[0]:
        mode_index = st.selectbox(
            "Normal mode",
            options=list(range(6)),
            format_func=lambda i: f"Mode {i + 1}" + (" (slowest)" if i == 0 else ""),
            index=0,
            key="nma_mode_index",
        )
    with ctrl_cols[1]:
        rmsd = st.slider(
            "Amplitude (RMSD, A)",
            min_value=0.5,
            max_value=4.0,
            value=1.5,
            step=0.5,
            key="nma_rmsd",
        )
    with ctrl_cols[2]:
        n_steps = st.slider(
            "Frames per direction",
            min_value=3,
            max_value=15,
            value=8,
            step=1,
            key="nma_n_steps",
        )

    # Generate trajectory
    traj_key = f"nma_traj_{query.protein_name}_{mode_index}_{n_steps}_{rmsd}"
    traj_data = st.session_state.get(traj_key)
    if traj_data is None:
        try:
            traj_data = _compute_nma_trajectory(
                prediction.pdb_content, first_chain, mode_index, n_steps, rmsd
            )
            st.session_state[traj_key] = traj_data
        except Exception as e:
            st.warning(f"NMA trajectory generation failed: {e}")
            return

    if traj_data.get("error"):
        st.warning(f"NMA error: {traj_data['error']}")
        return

    if not traj_data.get("pdb_content"):
        st.info("Could not generate trajectory for this structure.")
        return

    n_frames = traj_data.get("n_frames", 0)
    if n_frames < 1:
        st.info("Trajectory has no frames.")
        return

    # Frame selector — user picks which frame to view
    frame_col1, frame_col2 = st.columns([3, 1])
    with frame_col1:
        frame_idx = st.slider(
            "Animation frame",
            min_value=0,
            max_value=n_frames - 1,
            value=n_frames // 2,  # Start at center (equilibrium)
            key="nma_frame_idx",
            help="Slide to see the protein move along the selected normal mode",
        )
    with frame_col2:
        center_label = "center" if frame_idx == n_frames // 2 else ""
        direction = "+" if frame_idx > n_frames // 2 else ("-" if frame_idx < n_frames // 2 else "eq")
        st.markdown(f"**Frame {frame_idx + 1}/{n_frames}** {center_label}")
        st.caption(f"Direction: {direction}")

    # Render selected frame in Mol*
    builder = mvs.create_builder()
    parsed = builder.download(url="trajectory.pdb").parse(format="pdb")
    struct = parsed.model_structure(model_index=frame_idx)
    rep = struct.component(selector="polymer").representation(type="cartoon")
    rep.color(color="bfactor")

    data = {
        "trajectory.pdb": traj_data["pdb_content"].encode("utf-8"),
    }

    mvs.molstar_streamlit(builder, data=data, height=600)

    # Animation info
    st.caption(
        f"Mode {mode_index + 1} | "
        f"{n_frames} frames | "
        f"RMSD = {rmsd:.1f} A | "
        f"Variance explained: {traj_data.get('variance_pct', 0):.1f}%"
    )
    st.caption(
        "Use the model slider in the Mol* viewer to cycle through frames. "
        "Each frame shows a snapshot of the protein's predicted motion."
    )

    # Mode summary metrics
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Mode", f"{mode_index + 1}")
    mcol2.metric("Frames", n_frames)
    mcol3.metric("Variance", f"{traj_data.get('variance_pct', 0):.1f}%")

    # Explain what NMA animation shows
    with st.expander("What is Normal Mode Analysis?", expanded=False):
        st.markdown(
            "**Normal Mode Analysis (NMA)** predicts the large-scale "
            "collective motions of a protein from its 3D structure.\n\n"
            "- **Mode 1** is the slowest, largest-amplitude motion (often "
            "domain opening/closing)\n"
            "- Higher modes capture progressively faster, more localized motions\n"
            "- The animation shows the protein 'breathing' along the selected mode\n"
            "- **Amplitude (RMSD)** controls how far the structure deforms\n"
            "- Regions that move most are functionally important (hinges, loops)"
        )

    _render_provenance_badge(prediction)


def _render_morph_animation(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render conformational morphing between predicted and AlphaFold structures."""
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"

    # Need a second structure — AlphaFold reference
    af_key = f"alphafold_{query.uniprot_id}"
    af_data = st.session_state.get(af_key)

    if not query.uniprot_id:
        st.warning(
            "Morph Animation requires a UniProt ID to fetch the AlphaFold reference. "
            "Try an example query or enter a UniProt accession."
        )
        return

    if af_data is None:
        st.info(
            "Morphing shows a smooth trajectory between your predicted structure "
            "and the AlphaFold reference — revealing conformational differences."
        )
        if st.button("Fetch AlphaFold Structure for Morphing", key="fetch_af_morph", type="primary"):
            from components.alphafold_compare import _fetch_alphafold
            with st.status("Fetching AlphaFold structure..."):
                af_data = _fetch_alphafold(query.uniprot_id)
            if af_data is None:
                st.error(f"Could not fetch AlphaFold structure for {query.uniprot_id}.")
                return
            st.session_state[af_key] = af_data
        else:
            return

    af_pdb = af_data.get("pdb_content")
    if not af_pdb:
        st.warning("AlphaFold data is missing PDB content.")
        return

    # Controls
    ctrl1, ctrl2 = st.columns(2)
    with ctrl1:
        n_frames = st.slider(
            "Frames", min_value=10, max_value=40, value=20, step=2,
            key="morph_n_frames",
            help="Number of intermediate frames in the morphing trajectory",
        )
    with ctrl2:
        from src.conformational_morph import compute_morph_rmsd
        rmsd_val = compute_morph_rmsd(prediction.pdb_content, af_pdb)
        if rmsd_val is not None:
            st.metric("CA RMSD", f"{rmsd_val:.2f} A")
        else:
            st.metric("CA RMSD", "N/A")

    # Generate trajectory
    morph_key = f"morph_traj_{query.protein_name}_{n_frames}"
    morph_pdb = st.session_state.get(morph_key)
    if morph_pdb is None:
        from src.conformational_morph import generate_morph_trajectory
        with st.status("Generating morph trajectory..."):
            morph_pdb = generate_morph_trajectory(
                prediction.pdb_content, af_pdb, n_frames=n_frames,
            )
        if morph_pdb is None:
            st.warning(
                "Could not generate morph trajectory. "
                "Structures may be too different or have incompatible chains."
            )
            return
        st.session_state[morph_key] = morph_pdb

    # Count frames in the multi-model PDB
    model_count = morph_pdb.count("MODEL ")

    # Frame selector
    frame_col1, frame_col2 = st.columns([3, 1])
    with frame_col1:
        frame_idx = st.slider(
            "Morph frame",
            min_value=0,
            max_value=max(model_count - 1, 0),
            value=0,
            key="morph_frame_idx",
            help="Slide to morph between Boltz-2 prediction and AlphaFold structure",
        )
    with frame_col2:
        mid = model_count // 2
        if frame_idx == 0:
            label = "Prediction (start)"
        elif frame_idx == mid:
            label = "AlphaFold (mid)"
        elif frame_idx == model_count - 1:
            label = "Prediction (end)"
        else:
            label = f"Frame {frame_idx + 1}/{model_count}"
        st.markdown(f"**{label}**")

    # Render in Mol*
    builder = mvs.create_builder()
    parsed = builder.download(url="morph.pdb").parse(format="pdb")
    struct = parsed.model_structure(model_index=frame_idx)
    struct.component(selector="polymer").representation(type="cartoon").color(color="bfactor")

    data = {"morph.pdb": morph_pdb.encode("utf-8")}
    mvs.molstar_streamlit(builder, data=data, height=600)

    st.caption(
        f"Conformational morph: {model_count} frames | "
        f"Prediction <-> AlphaFold (looping) | "
        f"Colored by B-factor/pLDDT"
    )
    st.caption(
        "The morph trajectory linearly interpolates atomic coordinates between "
        "the two structures after superimposition. Use the slider to see how "
        "the predicted structure transitions to the AlphaFold reference."
    )

    # Download button
    st.download_button(
        "Download Morph Trajectory (PDB)",
        morph_pdb,
        f"{query.protein_name}_morph_trajectory.pdb",
        mime="chemical/x-pdb",
        key="download_morph_pdb",
    )

    _render_provenance_badge(prediction)


def _render_guided_tour(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
):
    """Render guided tour quick-focus buttons for key structural regions."""
    import re as _re

    # Collect available tour stops
    stops: list[dict] = [{"label": "Full Structure", "key": "full", "icon": "🔬"}]

    # Mutation site
    mut_pos = None
    if query.mutation:
        m = _re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            stops.append({
                "label": f"Mutation ({query.mutation})",
                "key": "mutation",
                "icon": "🧬",
                "residues": [mut_pos],
            })

    # Binding pocket (top pocket)
    pocket_data = st.session_state.get(f"pockets_{query.protein_name}")
    if pocket_data and pocket_data.get("pockets"):
        top_pocket = pocket_data["pockets"][0]
        pocket_res = top_pocket.get("residues", [])[:10]
        if pocket_res:
            stops.append({
                "label": f"Binding Pocket #{top_pocket.get('rank', 1)}",
                "key": "pocket",
                "icon": "💊",
                "residues": pocket_res,
            })

    # Low confidence region
    if prediction.plddt_per_residue and prediction.residue_ids:
        first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
        low_res = []
        for i, (rid, sc) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
            if first_chain and i < len(prediction.chain_ids) and prediction.chain_ids[i] != first_chain:
                continue
            if sc < 50:
                low_res.append(rid)
        if low_res:
            # Pick the cluster center
            center_res = low_res[len(low_res) // 2]
            stops.append({
                "label": f"Low Confidence ({len(low_res)} res)",
                "key": "low_conf",
                "icon": "⚠️",
                "residues": low_res[:10],
            })

    # Hub residues (high centrality)
    structure_analysis = st.session_state.get("structure_analysis") or {}
    hub_residues = structure_analysis.get("hub_residues", [])
    if hub_residues:
        stops.append({
            "label": f"Hub Residues ({len(hub_residues)})",
            "key": "hubs",
            "icon": "🔗",
            "residues": hub_residues[:10],
        })

    if len(stops) <= 1:
        return  # Only "Full Structure" — not useful to show tour

    # Render tour buttons
    st.markdown(
        '<div style="display:flex;align-items:center;gap:4px;margin-bottom:8px">'
        '<span style="font-size:0.8em;color:rgba(60,60,67,0.55);font-weight:600">GUIDED TOUR</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    cols = st.columns(len(stops))
    for i, stop in enumerate(stops):
        with cols[i]:
            if st.button(
                f"{stop['icon']} {stop['label']}",
                key=f"tour_{stop['key']}",
                width="stretch",
            ):
                st.session_state["tour_focus"] = stop.get("residues")
                st.session_state["tour_stop"] = stop["key"]


def _render_pocket_overlay(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by predicted binding pockets."""
    # Use precomputed pockets if available
    pocket_key = f"pockets_{query.protein_name}"
    pocket_data = st.session_state.get(pocket_key)
    if pocket_data is None:
        try:
            # Pass PDB ID for DoGSiteScorer API if available
            pdb_id = None
            if prediction.compute_source == "rcsb" and query.uniprot_id:
                pdb_id = st.session_state.get(f"rcsb_pdb_id_{query.protein_name}")
            pocket_data = _compute_pockets(prediction.pdb_content, pdb_id=pdb_id)
            st.session_state[pocket_key] = pocket_data
        except Exception as e:
            st.warning(f"Pocket prediction failed: {e}")
            return

    pockets = pocket_data.get("pockets", [])
    pocket_scores = pocket_data.get("residue_pocket_scores", {})
    method = pocket_data.get("method", "unknown")

    if not pockets:
        st.info("No binding pockets detected.")
        return

    # Build color annotations
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    pocket_colors = ["#34C759", "#AF52DE", "#FF9500", "#EC4899", "#0891B2"]
    residue_to_pocket = {}
    for p in pockets:
        for r in p.get("residues", []):
            residue_to_pocket[r] = p.get("rank", 0)

    annotations = []
    for res_id in prediction.residue_ids:
        pocket_rank = residue_to_pocket.get(res_id)
        if pocket_rank is not None:
            color = pocket_colors[(pocket_rank - 1) % len(pocket_colors)]
            # Ensure int key lookup (pocket_scores may have string keys from JSON)
            ps = pocket_scores.get(res_id, pocket_scores.get(str(res_id), 0))
            tooltip = f"Res {res_id}: Pocket {pocket_rank} (score {ps:.2f})"
        else:
            color = "#333333"
            tooltip = f"Res {res_id}: no pocket"
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": tooltip,
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Pocket cards
    st.markdown("#### Predicted Binding Pockets")
    cols = st.columns(min(len(pockets), 3))
    for i, pocket in enumerate(pockets[:3]):
        with cols[i]:
            p_rank = pocket.get("rank", i + 1)
            p_score = pocket.get("score", 0)
            p_prob = pocket.get("probability", 0)
            p_residues = pocket.get("residues", [])
            color = pocket_colors[(p_rank - 1) % len(pocket_colors)]
            st.markdown(
                f'<div class="glow-card" style="border-color:{color}">'
                f'<div style="color:{color};font-weight:700;font-size:1.1rem">'
                f'Pocket {p_rank}</div>'
                f'<div style="font-size:0.85em;color:rgba(60,60,67,0.6)">'
                f'Score: {p_score:.1f} | '
                f'Prob: {p_prob:.0%} | '
                f'{len(p_residues)} residues</div>'
                f'<div style="font-size:0.82em;color:rgba(60,60,67,0.55);margin-top:4px">'
                f'Residues: {", ".join(map(str, p_residues[:10]))}'
                f'{"..." if len(p_residues) > 10 else ""}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Check if mutation is in a pocket
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            for pocket in pockets:
                if mut_pos in pocket.get("residues", []):
                    st.warning(
                        f"**{query.mutation}** is located in predicted binding pocket "
                        f"{pocket.get('rank', '?')} (score {pocket.get('score', 0):.1f}). "
                        "This mutation may directly affect drug binding."
                    )
                    break

    st.caption(f"Pocket prediction method: {method}")
    _render_provenance_badge(prediction)


def _render_charge_surface(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by per-residue formal charge at pH 7.4."""
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"

    # Compute or retrieve cached surface charge data
    charge_key = f"charge_{query.protein_name}"
    charge_data = st.session_state.get(charge_key)
    if charge_data is None:
        try:
            charge_data = _compute_surface_charge(prediction.pdb_content, first_chain)
            st.session_state[charge_key] = charge_data
        except Exception as e:
            st.warning(f"Surface charge analysis failed: {e}")
            return

    if not charge_data.get("residue_ids"):
        st.info("Not enough residues for charge analysis.")
        return

    charge_map = charge_data.get("charge", {})
    res_ids = charge_data.get("residue_ids", [])

    # Build color annotations: blue = positive, red = negative, white = neutral
    annotations = []
    chain = first_chain or "A"
    for rid in res_ids:
        q = charge_map.get(rid, 0.0)
        if q >= 0.9:
            # Fully positive (Arg, Lys)
            color = "#2563EB"
            label = f"Res {rid}: charge +{q:.1f} (positive)"
        elif 0.05 < q < 0.9:
            # Partially positive (His ~0.1 at pH 7.4)
            color = "#93C5FD"
            label = f"Res {rid}: charge +{q:.2f} (partially positive)"
        elif q <= -0.9:
            # Fully negative (Asp, Glu)
            color = "#DC2626"
            label = f"Res {rid}: charge {q:.1f} (negative)"
        else:
            # Neutral
            color = "#E5E7EB"
            label = f"Res {rid}: charge {q:.1f} (neutral)"
        annotations.append({
            "label_asym_id": chain,
            "label_seq_id": rid,
            "color": color,
            "tooltip": label,
        })

    # Render with MolViewSpec
    _render_molstar_with_annotations(prediction, annotations)

    # Charge legend
    cols = st.columns(4)
    for col, (color, label) in zip(cols, [
        ("#2563EB", "Positive (Arg, Lys)"),
        ("#93C5FD", "Partially + (His)"),
        ("#DC2626", "Negative (Asp, Glu)"),
        ("#E5E7EB", "Neutral"),
    ]):
        col.markdown(
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:16px;height:16px;background:{color};border-radius:3px;'
            f'border:1px solid #ccc"></div>'
            f'<span style="font-size:0.85em">{label}</span></div>',
            unsafe_allow_html=True,
        )

    # Strip chart of per-residue charge
    import plotly.graph_objects as go

    st.markdown("#### Charge Profile")
    charge_vals = [charge_map.get(r, 0.0) for r in res_ids]
    charge_colors = []
    for q in charge_vals:
        if q >= 0.9:
            charge_colors.append("#2563EB")
        elif 0.05 < q < 0.9:
            charge_colors.append("#93C5FD")
        elif q <= -0.9:
            charge_colors.append("#DC2626")
        else:
            charge_colors.append("#E5E7EB")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=res_ids,
        y=charge_vals,
        marker_color=charge_colors,
        name="Charge",
        hovertemplate="Residue %{x}<br>Charge: %{y:.2f}<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=250,
        margin=dict(t=10, b=30, l=50, r=20),
        yaxis_title="Formal Charge",
        xaxis_title="Residue",
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, width="stretch")

    # Key metrics
    summary = charge_data.get("summary", {})
    n_pos = summary.get("n_positive_residues", 0)
    n_neg = summary.get("n_negative_residues", 0)
    n_neutral = len(res_ids) - n_pos - n_neg
    net_charge = summary.get("net_charge", 0.0)
    surface_charge = summary.get("surface_net_charge", 0.0)

    mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
    mcol1.metric("Net Charge", f"{net_charge:+.1f}")
    mcol2.metric("Surface Charge", f"{surface_charge:+.1f}")
    mcol3.metric("Positive", n_pos)
    mcol4.metric("Negative", n_neg)
    mcol5.metric("Neutral", n_neutral)

    # Charged patch info
    pos_patches = charge_data.get("positive_patches", [])
    neg_patches = charge_data.get("negative_patches", [])
    if pos_patches or neg_patches:
        st.markdown("#### Charged Patches")
        pcols = st.columns(2)
        with pcols[0]:
            if pos_patches:
                st.markdown(f"**{len(pos_patches)} positive patch(es)**")
                for i, patch in enumerate(pos_patches[:5], 1):
                    res_str = ", ".join(map(str, patch[:8]))
                    if len(patch) > 8:
                        res_str += "..."
                    st.caption(f"Patch {i} ({len(patch)} res): {res_str}")
            else:
                st.caption("No positive patches detected.")
        with pcols[1]:
            if neg_patches:
                st.markdown(f"**{len(neg_patches)} negative patch(es)**")
                for i, patch in enumerate(neg_patches[:5], 1):
                    res_str = ", ".join(map(str, patch[:8]))
                    if len(patch) > 8:
                        res_str += "..."
                    st.caption(f"Patch {i} ({len(patch)} res): {res_str}")
            else:
                st.caption("No negative patches detected.")

    _render_provenance_badge(prediction)


def _render_structure_diff(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by per-residue RMSD vs AlphaFold reference."""
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"

    # Check for AlphaFold data in session state
    af_key = f"alphafold_{query.uniprot_id}"
    af_data = st.session_state.get(af_key)

    if not query.uniprot_id:
        st.warning(
            "Structure Diff requires a UniProt ID to fetch the AlphaFold reference. "
            "Try an example query or enter a UniProt accession."
        )
        return

    if af_data is None:
        st.info(
            "AlphaFold reference structure is needed for comparison. "
            "Click below to fetch it from the AlphaFold Database."
        )
        if st.button(
            "Fetch AlphaFold Structure",
            key="fetch_af_for_diff",
            type="primary",
        ):
            from components.alphafold_compare import _fetch_alphafold

            with st.status("Fetching AlphaFold structure..."):
                af_data = _fetch_alphafold(query.uniprot_id)
            if af_data is None:
                st.error(
                    f"Could not fetch AlphaFold structure for {query.uniprot_id}. "
                    "This protein may not be in the AlphaFold Database."
                )
                return
            st.session_state[af_key] = af_data
            # Fall through to render comparison inline
        else:
            return

    af_pdb = af_data.get("pdb_content")
    if not af_pdb:
        st.warning("AlphaFold data is missing PDB content.")
        return

    # Compare structures
    from src.structure_comparison import compare_structures

    diff_key = f"struct_diff_{query.protein_name}"
    diff_result = st.session_state.get(diff_key)
    if diff_result is None:
        try:
            with st.status("Aligning structures and computing RMSD..."):
                diff_result = compare_structures(
                    prediction.pdb_content,
                    af_pdb,
                    chain_pred=first_chain,
                )
            st.session_state[diff_key] = diff_result
        except Exception as e:
            st.warning(f"Structure comparison failed: {e}")
            return

    if diff_result.get("error"):
        st.warning(f"Comparison error: {diff_result['error']}")
        return

    per_res_rmsd = diff_result.get("per_residue_rmsd", {})

    # Build color annotations by RMSD thresholds
    annotations = []
    chain = first_chain or "A"
    for rid in prediction.residue_ids:
        rmsd_val = per_res_rmsd.get(rid)
        if rmsd_val is None:
            color = "#AAAAAA"
            tooltip = f"Res {rid}: no alignment data"
        elif rmsd_val < 1.0:
            color = "#22C55E"
            tooltip = f"Res {rid}: RMSD {rmsd_val:.2f} A (excellent)"
        elif rmsd_val < 3.0:
            color = "#EAB308"
            tooltip = f"Res {rid}: RMSD {rmsd_val:.2f} A (moderate)"
        elif rmsd_val < 5.0:
            color = "#F97316"
            tooltip = f"Res {rid}: RMSD {rmsd_val:.2f} A (significant)"
        else:
            color = "#EF4444"
            tooltip = f"Res {rid}: RMSD {rmsd_val:.2f} A (poor)"
        annotations.append({
            "label_asym_id": chain,
            "label_seq_id": rid,
            "color": color,
            "tooltip": tooltip,
        })

    # Render with MolViewSpec
    _render_molstar_with_annotations(prediction, annotations)

    # RMSD legend
    cols = st.columns(4)
    for col, (color, label) in zip(cols, [
        ("#22C55E", "< 1 A (excellent)"),
        ("#EAB308", "1-3 A (moderate)"),
        ("#F97316", "3-5 A (significant)"),
        ("#EF4444", "> 5 A (poor)"),
    ]):
        col.markdown(
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:16px;height:16px;background:{color};border-radius:3px"></div>'
            f'<span style="font-size:0.85em">{label}</span></div>',
            unsafe_allow_html=True,
        )

    # Key metrics
    mcol1, mcol2, mcol3 = st.columns(3)
    mcol1.metric("Global RMSD", f"{diff_result.get('global_rmsd', 0):.2f} A")
    mcol2.metric("GDT-TS", f"{diff_result.get('gdt_ts', 0):.3f}")
    mcol3.metric("TM-score", f"{diff_result.get('tm_score', 0):.3f}")

    # Strip chart of per-residue RMSD
    import plotly.graph_objects as go

    st.markdown("#### Per-Residue RMSD")
    sorted_rids = sorted(per_res_rmsd.keys())
    rmsd_vals = [per_res_rmsd[r] for r in sorted_rids]
    rmsd_colors = []
    for v in rmsd_vals:
        if v < 1.0:
            rmsd_colors.append("#22C55E")
        elif v < 3.0:
            rmsd_colors.append("#EAB308")
        elif v < 5.0:
            rmsd_colors.append("#F97316")
        else:
            rmsd_colors.append("#EF4444")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=sorted_rids,
        y=rmsd_vals,
        marker_color=rmsd_colors,
        name="RMSD",
        hovertemplate="Residue %{x}<br>RMSD: %{y:.2f} A<extra></extra>",
    ))
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=250,
        margin=dict(t=10, b=30, l=50, r=20),
        yaxis_title="RMSD (A)",
        xaxis_title="Residue",
        legend=dict(orientation="h", y=1.1),
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, width="stretch")

    # Quality assessment
    qa = diff_result.get("quality_assessment")
    if qa:
        if isinstance(qa, str):
            st.info(qa)
        elif isinstance(qa, dict):
            grade = qa.get("grade", "")
            desc = qa.get("description", "")
            if grade or desc:
                st.info(f"**Quality: {grade}** -- {desc}")

    # Region breakdown
    n_well = len(diff_result.get("well_modeled", []))
    n_mod = len(diff_result.get("moderate_deviation", []))
    n_poor = len(diff_result.get("poor_regions", []))
    n_total = n_well + n_mod + n_poor
    if n_total > 0:
        rcol1, rcol2, rcol3 = st.columns(3)
        rcol1.metric("Well-Modeled", f"{n_well} ({n_well / n_total:.0%})")
        rcol2.metric("Moderate", f"{n_mod} ({n_mod / n_total:.0%})")
        rcol3.metric("Poor", f"{n_poor} ({n_poor / n_total:.0%})")

    poor_stretches = diff_result.get("poor_stretches", [])
    if poor_stretches:
        st.caption(
            f"Poor stretches (>5 A RMSD): "
            + ", ".join(
                (f"{s[0]}-{s[-1]}" if len(s) > 1 else str(s[0])) if s else "?"
                for s in poor_stretches[:8]
            )
        )

    _render_provenance_badge(prediction)


def _render_alphamissense_overlay(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by AlphaMissense pathogenicity scores."""
    from src.alphamissense import (
        fetch_alphamissense,
        get_pathogenicity_color,
    )

    if not query.uniprot_id:
        st.warning(
            "AlphaMissense requires a UniProt ID. "
            "Try an example query or enter a UniProt accession."
        )
        return

    # Fetch or use cached data
    am_key = f"alphamissense_{query.uniprot_id}"
    am_data = st.session_state.get(am_key)
    if am_data is None:
        am_data = fetch_alphamissense(query.uniprot_id)
        st.session_state[am_key] = am_data

    if not am_data.get("available"):
        st.info(
            f"AlphaMissense data not available for "
            f"{query.uniprot_id}. This protein may not be "
            "in the AlphaFold Database. Select 'Trust "
            "(pLDDT)' to view the default coloring."
        )
        # Render plain structure without coloring
        _render_molstar_with_annotations(prediction, [])
        _render_provenance_badge(prediction)
        return

    residue_scores = am_data.get("residue_scores", {})
    classification = am_data.get("classification", {})

    # Build color annotations
    first_chain = (
        prediction.chain_ids[0] if prediction.chain_ids else "A"
    )
    annotations = []
    for res_id in prediction.residue_ids:
        score = residue_scores.get(res_id)
        if score is not None:
            color = get_pathogenicity_color(score)
            am_class = classification.get(res_id, "unknown")
            tooltip = (
                f"Res {res_id}: AM score {score:.3f} "
                f"({am_class})"
            )
        else:
            color = "#AAAAAA"
            tooltip = f"Res {res_id}: no AlphaMissense data"
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": tooltip,
        })

    _render_molstar_with_annotations(prediction, annotations)

    # AlphaMissense color legend
    cols = st.columns(3)
    for col, (color, label) in zip(cols, [
        ("#1E50DC", "Benign (<0.34)"),
        ("#D2F0BE", "Ambiguous"),
        ("#DC3232", "Pathogenic (>0.564)"),
    ]):
        col.markdown(
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:16px;height:16px;background:{color};'
            f'border-radius:3px"></div>'
            f'<span style="font-size:0.85em">{label}</span></div>',
            unsafe_allow_html=True,
        )

    # Summary metrics
    st.markdown(am_data.get("summary", ""))

    # Pathogenicity profile chart
    import plotly.graph_objects as go

    scored_ids = sorted(residue_scores.keys())
    if scored_ids:
        fig = go.Figure()
        scores_list = [residue_scores[r] for r in scored_ids]
        colors_list = [
            get_pathogenicity_color(s) for s in scores_list
        ]

        fig.add_trace(go.Bar(
            x=scored_ids,
            y=scores_list,
            marker_color=colors_list,
            hovertemplate=(
                "Res %{x}<br>"
                "Pathogenicity: %{y:.3f}<extra></extra>"
            ),
        ))
        # Threshold lines
        fig.add_hline(
            y=0.564, line_dash="dash", line_color="#DC3232",
            annotation_text="Pathogenic",
            annotation_position="right",
            annotation_font_color="#DC3232",
        )
        fig.add_hline(
            y=0.34, line_dash="dash", line_color="#457B9D",
            annotation_text="Benign",
            annotation_position="right",
            annotation_font_color="#457B9D",
        )

        fig.update_layout(
            xaxis_title="Residue Position",
            yaxis_title="AlphaMissense Score",
            yaxis_range=[0, 1.05],
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=250,
            margin=dict(t=10, b=30, l=50, r=80),
            xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
            yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        )
        st.plotly_chart(fig, width="stretch")

    # Mutation-specific pathogenicity
    if query.mutation:
        import re as _re
        m = _re.match(r"([A-Z])(\d+)([A-Z])", query.mutation)
        if m:
            mut_pos = int(m.group(2))
            to_aa = m.group(3)
            sub_matrix = am_data.get("substitution_matrix", {})
            pos_subs = sub_matrix.get(mut_pos, {})
            if to_aa in pos_subs:
                score = pos_subs[to_aa]
                am_class = (
                    "pathogenic" if score > 0.564
                    else "ambiguous" if score > 0.34
                    else "benign"
                )
                score_color = (
                    "#DC3232" if am_class == "pathogenic"
                    else "#FF9500" if am_class == "ambiguous"
                    else "#34C759"
                )
                st.markdown(
                    f'<div class="glow-card" style="border-color:'
                    f'{score_color};padding:10px 14px">'
                    f'<div style="font-weight:700;font-size:1.1rem">'
                    f'{query.mutation} AlphaMissense</div>'
                    f'<div style="font-size:2rem;font-weight:800;'
                    f'color:{score_color}">{score:.3f}</div>'
                    f'<div style="font-size:0.85em;color:'
                    f'rgba(60,60,67,0.6)">'
                    f'Classification: {am_class.upper()}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            elif pos_subs:
                # Show all substitutions at this position
                st.markdown(
                    f"**Position {mut_pos}** — "
                    f"{len(pos_subs)} substitutions scored:"
                )
                sorted_subs = sorted(
                    pos_subs.items(), key=lambda x: -x[1]
                )
                for aa, sc in sorted_subs[:10]:
                    cl = (
                        "pathogenic" if sc > 0.564
                        else "ambiguous" if sc > 0.34
                        else "benign"
                    )
                    st.caption(f"  {aa}: {sc:.3f} ({cl})")

    _render_provenance_badge(prediction)


def _render_domain_overlay(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
):
    """Render structure colored by InterPro/Pfam domain annotations."""
    from src.domain_annotation import fetch_domain_annotations

    if not query.uniprot_id:
        st.warning(
            "Domain annotations require a UniProt ID. "
            "Try an example query or enter a UniProt accession."
        )
        return

    # Fetch or use cached data
    dom_key = f"domains_{query.uniprot_id}"
    dom_data = st.session_state.get(dom_key)
    if dom_data is None:
        dom_data = fetch_domain_annotations(query.uniprot_id)
        st.session_state[dom_key] = dom_data

    if not dom_data.get("available"):
        st.info(
            f"No domain annotations found for {query.uniprot_id}."
        )
        return

    domains = dom_data.get("domains", [])

    # Build color annotations
    first_chain = (
        prediction.chain_ids[0] if prediction.chain_ids else "A"
    )

    # Build residue→color map from domains
    res_color_map: dict[int, str] = {}
    res_domain_name: dict[int, str] = {}
    for d in domains:
        d_start = d.get("start", 0)
        d_end = d.get("end", 0)
        d_color = d.get("color", "#CCCCCC")
        d_name = d.get("name", "Unknown")
        for pos in range(d_start, d_end + 1):
            res_color_map[pos] = d_color
            res_domain_name[pos] = d_name

    annotations = []
    for res_id in prediction.residue_ids:
        if res_id in res_color_map:
            color = res_color_map[res_id]
            name = res_domain_name[res_id]
            tooltip = f"Res {res_id}: {name}"
        else:
            color = "#CCCCCC"
            tooltip = f"Res {res_id}: no domain annotation"
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": tooltip,
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Domain legend + cards
    st.markdown("#### Domain Architecture")

    # Deduplicate domains by name for the legend
    seen_names: set[str] = set()
    unique_domains: list[dict] = []
    for d in domains:
        dname = d.get("name", "Unknown")
        if dname not in seen_names:
            seen_names.add(dname)
            unique_domains.append(d)

    n_cols = min(len(unique_domains), 3)
    if n_cols > 0:
        cols = st.columns(n_cols)
        for i, d in enumerate(unique_domains[:6]):
            with cols[i % n_cols]:
                d_start = d.get("start", 0)
                d_end = d.get("end", 0)
                d_color = d.get("color", "#CCCCCC")
                d_name = d.get("name", "Unknown")
                d_db = d.get("database", "—")
                d_type = d.get("type", "—")
                length = d_end - d_start + 1
                st.markdown(
                    f'<div class="glow-card" style="'
                    f'border-color:{d_color};'
                    f'padding:8px 12px;margin-bottom:6px">'
                    f'<div style="display:flex;align-items:'
                    f'center;gap:6px">'
                    f'<div style="width:14px;height:14px;'
                    f'background:{d_color};border-radius:'
                    f'3px"></div>'
                    f'<span style="font-weight:700;font-size:'
                    f'0.95rem">{d_name}</span></div>'
                    f'<div style="font-size:0.82em;color:'
                    f'rgba(60,60,67,0.6)">'
                    f'{d_db} | {d_type} | '
                    f'Res {d_start}-{d_end} '
                    f'({length} aa)</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    # Domain map as a horizontal bar chart
    import plotly.graph_objects as go

    if domains:
        fig = go.Figure()

        # Background protein length bar
        max_res = max(prediction.residue_ids) if prediction.residue_ids else 100
        fig.add_trace(go.Bar(
            y=["Protein"],
            x=[max_res],
            orientation="h",
            marker_color="rgba(0,0,0,0.05)",
            hoverinfo="skip",
            showlegend=False,
        ))

        # Domain bars
        for d in domains:
            d_start = d.get("start", 0)
            d_end = d.get("end", 0)
            d_name = d.get("name", "Unknown")
            d_color = d.get("color", "#CCCCCC")
            d_db = d.get("database", "—")
            d_type = d.get("type", "—")
            length = d_end - d_start + 1
            fig.add_trace(go.Bar(
                y=["Protein"],
                x=[length],
                base=d_start,
                orientation="h",
                name=d_name,
                marker_color=d_color,
                marker_line_color="white",
                marker_line_width=1,
                hovertemplate=(
                    f"<b>{d_name}</b><br>"
                    f"{d_db} ({d_type})<br>"
                    f"Residues {d_start}-{d_end} "
                    f"({length} aa)"
                    "<extra></extra>"
                ),
            ))

        # Mark mutation position
        if query.mutation:
            import re as _re
            m = _re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
            if m:
                mut_pos = int(m.group(1))
                fig.add_vline(
                    x=mut_pos, line_dash="dash",
                    line_color="#FF3B30", line_width=2,
                    annotation_text=query.mutation,
                    annotation_font_color="#FF3B30",
                )

        fig.update_layout(
            barmode="overlay",
            template="plotly_white",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            height=120,
            margin=dict(t=10, b=30, l=60, r=20),
            xaxis_title="Residue Position",
            yaxis=dict(showticklabels=False),
            xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
            legend=dict(
                orientation="h", y=-0.4,
                font=dict(size=10),
            ),
            showlegend=True,
        )
        st.plotly_chart(fig, width="stretch")

    _render_provenance_badge(prediction)


def _render_conservation_overlay(query: ProteinQuery, prediction: PredictionResult):
    """Color structure by conservation score (1-9 ConSurf scale)."""
    try:
        from src.conservation import compute_conservation_scores
        data = compute_conservation_scores(prediction.pdb_content)
    except Exception as e:
        st.warning(f"Conservation computation failed: {e}")
        return

    scores = data.get("conservation_scores", {})
    if not scores:
        st.info("No conservation data available.")
        return

    # ConSurf color scale: variable (cyan) → conserved (magenta)
    _CONSURF_COLORS = {
        1: "#00FFFF", 2: "#33D4E6", 3: "#66AACC",
        4: "#997FB3", 5: "#996699", 6: "#B34D80",
        7: "#CC3366", 8: "#E6194D", 9: "#FF0033",
    }

    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    annotations = []
    for res_id in prediction.residue_ids:
        score = scores.get(res_id, 5)
        color = _CONSURF_COLORS.get(score, "#996699")
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": f"Res {res_id}: conservation {score}/9"
                       f" ({'highly conserved' if score >= 7 else 'variable' if score <= 3 else 'moderate'})",
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:4px;align-items:center;margin-top:8px">'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Variable</span>'
        + "".join(
            f'<span style="display:inline-block;width:20px;height:12px;'
            f'border-radius:2px;background:{_CONSURF_COLORS[i]}"></span>'
            for i in range(1, 10)
        )
        + '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Conserved</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Stats
    n_conserved = len(data.get("highly_conserved", []))
    n_variable = len(data.get("variable", []))
    patches = data.get("conserved_patches", [])
    col1, col2, col3 = st.columns(3)
    col1.metric("Highly Conserved", f"{n_conserved} residues")
    col2.metric("Variable", f"{n_variable} residues")
    col3.metric("Conserved Patches", len(patches))

    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            mut_score = scores.get(mut_pos, 5)
            if mut_score >= 7:
                st.error(
                    f"**{query.mutation}** is at a **highly conserved** position "
                    f"(conservation {mut_score}/9) — mutations here are likely damaging."
                )
            elif mut_score <= 3:
                st.success(
                    f"**{query.mutation}** is at a **variable** position "
                    f"(conservation {mut_score}/9) — may be tolerated."
                )

    _render_provenance_badge(prediction)


def _render_hydrophobicity_overlay(query: ProteinQuery, prediction: PredictionResult):
    """Color structure by Kyte-Doolittle hydrophobicity."""
    try:
        from src.surface_properties import compute_surface_properties
        data = compute_surface_properties(prediction.pdb_content)
    except Exception as e:
        st.warning(f"Surface property computation failed: {e}")
        return

    hydro = data.get("hydrophobicity_smoothed", {})
    if not hydro:
        st.info("No hydrophobicity data available.")
        return

    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    annotations = []
    for res_id in prediction.residue_ids:
        val = hydro.get(res_id, 0.0)
        # Scale: -4.5 (hydrophilic/blue) → +4.5 (hydrophobic/orange)
        norm = (val + 4.5) / 9.0  # 0-1
        norm = max(0, min(1, norm))
        r = int(50 + 180 * norm)
        g = int(130 - 50 * norm)
        b = int(220 - 180 * norm)
        color = f"#{r:02x}{g:02x}{b:02x}"
        label = "hydrophobic" if val > 0.5 else "hydrophilic" if val < -0.5 else "neutral"
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": f"Res {res_id}: KD={val:+.1f} ({label})",
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:8px;align-items:center;margin-top:8px">'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Hydrophilic</span>'
        '<span style="display:inline-block;width:100px;height:12px;border-radius:2px;'
        'background:linear-gradient(to right,#3282DC,#966645,#E6500A)"></span>'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Hydrophobic</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Patch summary
    patches = data.get("hydrophobic_patches", [])
    summary = data.get("summary", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Surface Net Charge", f"{summary.get('surface_net_charge', 0):+.1f}")
    col2.metric("Hydrophobic Patches", len(patches))
    col3.metric("Surface %", f"{summary.get('pct_surface', 0):.0%}")

    if patches:
        st.caption(f"Hydrophobic patches (potential binding sites): "
                   + ", ".join(f"{p['start']}-{p['end']}" for p in patches[:5]))

    _render_provenance_badge(prediction)


def _render_depth_overlay(query: ProteinQuery, prediction: PredictionResult):
    """Color structure by residue depth (distance to surface)."""
    try:
        from src.residue_depth import compute_residue_depth
        data = compute_residue_depth(prediction.pdb_content)
    except Exception as e:
        st.warning(f"Depth computation failed: {e}")
        return

    depth = data.get("depth", {})
    depth_norm = data.get("depth_normalized", {})
    if not depth:
        st.info("No depth data available.")
        return

    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    annotations = []
    for res_id in prediction.residue_ids:
        d = depth_norm.get(res_id, 0.0)
        # Surface (white/teal) → Deep core (dark blue)
        r = int(230 - 200 * d)
        g = int(245 - 190 * d)
        b = int(250 - 100 * d)
        color = f"#{max(0,r):02x}{max(0,g):02x}{max(0,b):02x}"
        raw_d = depth.get(res_id, 0.0)
        zone = "deep core" if raw_d > 8 else "intermediate" if raw_d > 4 else "surface"
        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": f"Res {res_id}: depth {raw_d:.1f} Å ({zone})",
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:8px;align-items:center;margin-top:8px">'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Surface</span>'
        '<span style="display:inline-block;width:100px;height:12px;border-radius:2px;'
        'background:linear-gradient(to right,#E6F5FA,#1E3796)"></span>'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">Deep Core</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    summary = data.get("summary", {})
    col1, col2, col3 = st.columns(3)
    col1.metric("Deep Core", f"{summary.get('n_deep_core', 0)} residues")
    col2.metric("Intermediate", f"{summary.get('n_intermediate', 0)} residues")
    col3.metric("Max Depth", f"{summary.get('max_depth', 0):.1f} Å")

    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            mut_depth = depth.get(mut_pos, 0)
            if mut_depth > 8:
                st.error(
                    f"**{query.mutation}** is in the **deep core** ({mut_depth:.1f} Å) — "
                    "mutations here are highly destabilizing."
                )
            elif mut_depth > 4:
                st.warning(
                    f"**{query.mutation}** is at **intermediate** depth ({mut_depth:.1f} Å) — "
                    "may affect stability or interface contacts."
                )

    _render_provenance_badge(prediction)


def _render_psn_overlay(query: ProteinQuery, prediction: PredictionResult):
    """Color structure by Protein Structure Network community + show network graph."""
    try:
        from src.protein_network import build_protein_network
        data = build_protein_network(prediction.pdb_content)
    except Exception as e:
        st.warning(f"PSN computation failed: {e}")
        return

    communities = data.get("communities", [])
    betweenness = data.get("betweenness", {})
    bridge_residues = {b["residue"] for b in data.get("bridge_residues", [])}
    hub_residues = {h["residue"] for h in data.get("hub_residues", [])}

    if not communities:
        st.info("No structural communities detected.")
        return

    # Assign colors to communities
    _COMMUNITY_COLORS = [
        "#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE",
        "#FF2D55", "#5856D6", "#00C7BE", "#FF6482", "#32D74B",
    ]
    res_to_community: dict[int, int] = {}
    for c in communities:
        for r in c["members"]:
            res_to_community[r] = c["id"]

    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    annotations = []
    for res_id in prediction.residue_ids:
        comm_id = res_to_community.get(res_id)
        if comm_id is not None:
            color = _COMMUNITY_COLORS[comm_id % len(_COMMUNITY_COLORS)]
        else:
            color = "#555555"

        # Mark hubs and bridges
        role = ""
        if res_id in bridge_residues:
            role = " [BRIDGE]"
        elif res_id in hub_residues:
            role = " [HUB]"
        bc = betweenness.get(res_id, 0)

        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": res_id,
            "color": color,
            "tooltip": f"Res {res_id}: Community {comm_id if comm_id is not None else '?'}"
                       f" | BC={bc:.4f}{role}",
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Community legend
    legend_html = '<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:8px">'
    for c in communities[:8]:
        color = _COMMUNITY_COLORS[c["id"] % len(_COMMUNITY_COLORS)]
        legend_html += (
            f'<span style="display:inline-flex;align-items:center;gap:4px;'
            f'font-size:0.82em;color:rgba(60,60,67,0.6)">'
            f'<span style="display:inline-block;width:10px;height:10px;'
            f'border-radius:50%;background:{color}"></span>'
            f'Module {c["id"]} ({c["size"]} res)</span>'
        )
    legend_html += "</div>"
    st.markdown(legend_html, unsafe_allow_html=True)

    # Stats
    stats = data.get("graph_stats", {})
    summary = data.get("summary", {})
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Communities", len(communities))
    col2.metric("Hub Residues", summary.get("n_hubs", 0))
    col3.metric("Bridge Residues", summary.get("n_bridges", 0))
    col4.metric("Network Density", f"{stats.get('density', 0):.3f}")

    # PSN network graph visualization
    _render_psn_graph(data, query)

    _render_provenance_badge(prediction)


def _render_psn_graph(psn_data: dict, query: ProteinQuery):
    """Render an interactive Plotly force-directed graph of the PSN."""
    import plotly.graph_objects as go

    communities = psn_data.get("communities", [])
    betweenness = psn_data.get("betweenness", {})
    degree = psn_data.get("degree", {})
    hub_set = {h["residue"] for h in psn_data.get("hub_residues", [])}
    bridge_set = {b["residue"] for b in psn_data.get("bridge_residues", [])}
    res_ids = psn_data.get("residue_ids", [])

    if not communities or not res_ids:
        return

    # Build community membership lookup
    _COMM_COLORS = [
        "#007AFF", "#FF3B30", "#34C759", "#FF9500", "#AF52DE",
        "#FF2D55", "#5856D6", "#00C7BE", "#FF6482", "#32D74B",
    ]
    res_to_comm: dict[int, int] = {}
    for c in communities:
        for r in c["members"]:
            res_to_comm[r] = c["id"]

    # Use betweenness for y-position (high BC = top), sequence position for x
    # This creates a "landscape" view where hubs rise above the baseline
    min_rid, max_rid = min(res_ids), max(res_ids)
    span = max_rid - min_rid or 1

    bc_vals = list(betweenness.values())
    max_bc = max(bc_vals) if bc_vals else 1

    # Position residues
    x_pos = {r: (r - min_rid) / span for r in res_ids}
    y_pos = {r: betweenness.get(r, 0) / max_bc if max_bc > 0 else 0 for r in res_ids}

    # Sample for large proteins (show every Nth residue + all hubs/bridges)
    important = hub_set | bridge_set
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            important.add(int(m.group(1)))

    if len(res_ids) > 150:
        step = len(res_ids) // 100
        sampled = set(res_ids[::step]) | important
    else:
        sampled = set(res_ids)

    # Node traces (one per community for legend)
    for c in communities:
        members_in_sample = [r for r in c["members"] if r in sampled]
        if not members_in_sample:
            continue

        color = _COMM_COLORS[c["id"] % len(_COMM_COLORS)]
        sizes = []
        symbols = []
        labels = []
        for r in members_in_sample:
            bc = betweenness.get(r, 0)
            # Size: 4-16 based on degree centrality
            d = degree.get(r, 0)
            sz = 4 + 12 * d
            sizes.append(sz)
            if r in bridge_set:
                symbols.append("diamond")
                labels.append(f"Res {r} [BRIDGE] BC={bc:.4f}")
            elif r in hub_set:
                symbols.append("star")
                labels.append(f"Res {r} [HUB] BC={bc:.4f}")
            else:
                symbols.append("circle")
                labels.append(f"Res {r} BC={bc:.4f}")

        fig_data = go.Scatter(
            x=[x_pos[r] for r in members_in_sample],
            y=[y_pos[r] for r in members_in_sample],
            mode="markers",
            marker=dict(
                size=sizes,
                color=color,
                symbol=symbols,
                line=dict(width=0.5, color="rgba(0,0,0,0.3)"),
            ),
            text=labels,
            hoverinfo="text",
            name=f"Module {c['id']} ({c['size']})",
        )
        if "_psn_fig" not in st.session_state:
            st.session_state["_psn_fig"] = go.Figure()
        st.session_state["_psn_fig"].add_trace(fig_data)

    fig = go.Figure()
    # Re-add traces properly
    for c in communities:
        members_in_sample = [r for r in c["members"] if r in sampled]
        if not members_in_sample:
            continue
        color = _COMM_COLORS[c["id"] % len(_COMM_COLORS)]
        sizes = [4 + 12 * degree.get(r, 0) for r in members_in_sample]
        symbols = [
            "diamond" if r in bridge_set else "star" if r in hub_set else "circle"
            for r in members_in_sample
        ]
        labels = [
            f"Res {r}"
            + (" [BRIDGE]" if r in bridge_set else " [HUB]" if r in hub_set else "")
            + f" | BC={betweenness.get(r, 0):.4f}"
            for r in members_in_sample
        ]
        fig.add_trace(go.Scatter(
            x=[x_pos[r] for r in members_in_sample],
            y=[y_pos[r] for r in members_in_sample],
            mode="markers",
            marker=dict(size=sizes, color=color, symbol=symbols,
                        line=dict(width=0.5, color="rgba(0,0,0,0.3)")),
            text=labels, hoverinfo="text",
            name=f"Module {c['id']} ({c['size']})",
        ))

    # Mutation marker
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in x_pos:
                fig.add_trace(go.Scatter(
                    x=[x_pos[mut_pos]], y=[y_pos[mut_pos]],
                    mode="markers+text",
                    marker=dict(size=18, color="#FF3B30", symbol="x",
                                line=dict(width=2, color="#FF3B30")),
                    text=[query.mutation], textposition="top center",
                    textfont=dict(size=11, color="#FF3B30"),
                    hoverinfo="text",
                    hovertext=f"{query.mutation} | BC={betweenness.get(mut_pos, 0):.4f}",
                    name="Mutation",
                    showlegend=True,
                ))

    fig.update_layout(
        title="Protein Structure Network — Allosteric Landscape",
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        height=350,
        margin=dict(t=40, b=40, l=40, r=20),
        xaxis=dict(title="Sequence Position", showgrid=False,
                   tickformat="d", gridcolor="rgba(0,0,0,0.05)"),
        yaxis=dict(title="Betweenness Centrality (allosteric importance)",
                   showgrid=True, gridcolor="rgba(0,0,0,0.08)"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02,
                    xanchor="left", x=0, font=dict(size=10)),
        font=dict(family="Inter, system-ui, sans-serif"),
    )

    st.plotly_chart(fig, width="stretch", key="psn_landscape_chart")

    st.caption(
        "Each dot is a residue. Height = allosteric importance (betweenness centrality). "
        "Colors = structural communities (functional modules). "
        "Stars = hub residues. Diamonds = bridge residues (communication bottlenecks)."
    )

    # Interpretation
    summary = psn_data.get("summary", {})
    n_hubs = summary.get("n_hubs", len(hub_set))
    n_bridges = summary.get("n_bridges", len(bridge_set))
    n_comms = summary.get("n_communities", len(communities))

    if query.mutation:
        import re as _re
        m = _re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            mut_bc = betweenness.get(mut_pos, 0)
            bc_rank = sum(1 for v in betweenness.values() if v > mut_bc)
            bc_pct = 100 * bc_rank / len(betweenness) if betweenness else 100
            mut_comm = res_to_comm.get(mut_pos, -1)
            comm_size = next((c["size"] for c in communities if c["id"] == mut_comm), 0)

            if mut_pos in hub_set:
                st.error(
                    f"**{query.mutation} is a network hub** (top {bc_pct:.0f}% centrality) "
                    f"in module {mut_comm} ({comm_size} residues). Disrupting this position "
                    f"likely propagates effects across the protein — high allosteric risk."
                )
            elif mut_pos in bridge_set:
                st.error(
                    f"**{query.mutation} is a bridge residue** — a communication bottleneck "
                    f"between structural modules. Mutation here may sever allosteric signaling."
                )
            elif mut_bc > 0 and bc_pct < 25:
                st.warning(
                    f"**{query.mutation} has above-average centrality** (top {bc_pct:.0f}%) "
                    f"in module {mut_comm}. May moderately affect inter-residue communication."
                )

    if n_bridges > 0:
        bridge_residues = [b["residue"] for b in psn_data.get("bridge_residues", [])]
        st.info(
            f"**{n_bridges} bridge residue(s)** identified ({', '.join(f'Res {r}' for r in bridge_residues[:5])}) "
            f"— these bottleneck positions control information flow between the {n_comms} structural modules. "
            f"Mutations at bridges are prime candidates for allosteric drug design."
        )


def _render_mutation_energy_delta(query: ProteinQuery, prediction: PredictionResult):
    """Mutation Impact Field — 3D 'shockwave' radiating from the mutation site.

    Colors every residue by the estimated structural impact of the mutation,
    computed from: distance decay from mutation site, pLDDT confidence,
    amino acid property disruption, and network centrality.

    This shows how a single mutation's effect ripples across the entire protein —
    the structural basis for pathogenicity.
    """
    import re

    if not query.mutation:
        st.info(
            "Select a protein with a mutation (e.g. **TP53 R248W**) to see "
            "the mutation impact field radiating across the structure."
        )
        _render_provenance_badge(prediction)
        return

    m = re.match(r"([A-Z])(\d+)([A-Z])", query.mutation)
    if not m:
        st.warning(f"Cannot parse mutation '{query.mutation}' for impact analysis.")
        _render_provenance_badge(prediction)
        return

    wt_aa, mut_pos, mt_aa = m.group(1), int(m.group(2)), m.group(3)

    import io
    import numpy as np
    try:
        import biotite.structure as struc
        import biotite.structure.io.pdb as pdbio
    except ImportError:
        st.warning("Biotite required for mutation impact analysis.")
        return

    pdb_file = pdbio.PDBFile.read(io.StringIO(prediction.pdb_content))
    structure = pdb_file.get_structure(model=1)
    aa_mask = struc.filter_amino_acids(structure)
    protein = structure[aa_mask]
    ca = protein[protein.atom_name == "CA"]

    if len(ca) < 5:
        return

    res_ids = [int(r) for r in ca.res_id]
    coords = ca.coord

    # Find mutation site coordinates
    if mut_pos not in res_ids:
        st.warning(f"Mutation position {mut_pos} not found in structure.")
        return

    mut_idx = res_ids.index(mut_pos)
    mut_coord = coords[mut_idx]

    # Amino acid property disruption score
    _AA_VOLUME = {
        "G": 60, "A": 88, "V": 140, "L": 166, "I": 166, "P": 112,
        "F": 189, "W": 227, "M": 162, "S": 89, "T": 116, "C": 108,
        "Y": 193, "H": 153, "D": 111, "E": 138, "N": 114, "Q": 143,
        "K": 168, "R": 173,
    }
    _AA_CHARGE = {
        "R": 1, "K": 1, "H": 0.5, "D": -1, "E": -1,
    }
    _AA_HYDRO = {
        "I": 4.5, "V": 4.2, "L": 3.8, "F": 2.8, "C": 2.5, "M": 1.9, "A": 1.8,
        "G": -0.4, "T": -0.7, "S": -0.8, "W": -0.9, "Y": -1.3, "P": -1.6,
        "H": -3.2, "E": -3.5, "Q": -3.5, "D": -3.5, "N": -3.5, "K": -3.9, "R": -4.5,
    }

    vol_delta = abs(_AA_VOLUME.get(wt_aa, 130) - _AA_VOLUME.get(mt_aa, 130)) / 170.0
    charge_delta = abs(_AA_CHARGE.get(wt_aa, 0) - _AA_CHARGE.get(mt_aa, 0)) / 2.0
    hydro_delta = abs(_AA_HYDRO.get(wt_aa, 0) - _AA_HYDRO.get(mt_aa, 0)) / 9.0

    # Combined disruption score (0-1)
    disruption = min(1.0, (vol_delta + charge_delta + hydro_delta) / 2.0)

    # pLDDT at mutation site (lower pLDDT = less confident = bigger impact zone)
    plddt_lookup = {}
    if prediction.plddt_per_residue and prediction.residue_ids:
        for rid, p in zip(prediction.residue_ids, prediction.plddt_per_residue):
            plddt_lookup[rid] = p
    mut_plddt = plddt_lookup.get(mut_pos, 70)

    # Distance from mutation to every residue
    distances = np.linalg.norm(coords - mut_coord, axis=1)
    max_dist = float(np.max(distances)) if len(distances) > 0 else 30.0

    # Impact field: exponential decay from mutation site
    # Modified by disruption score and local confidence
    decay_rate = 0.08 + 0.04 * (1 - mut_plddt / 100)  # Softer decay for low-confidence regions
    raw_impact = disruption * np.exp(-decay_rate * distances)

    # Boost for network neighbors (if PSN data available)
    psn_data = st.session_state.get(f"_dashboard_psn_{query.protein_name}")
    if psn_data and isinstance(psn_data, dict):
        betweenness = psn_data.get("betweenness", {})
        for i, r in enumerate(res_ids):
            bc = betweenness.get(r, 0)
            if bc > 0.01:  # Hub residues transmit impact more
                raw_impact[i] = min(1.0, raw_impact[i] * (1 + bc * 5))

    # Normalize to 0-1
    if raw_impact.max() > 0:
        impact = raw_impact / raw_impact.max()
    else:
        impact = raw_impact

    # Build color annotations: red (high impact) → yellow (medium) → blue (none)
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    annotations = []
    for i, (r, imp) in enumerate(zip(res_ids, impact)):
        # Red-yellow-blue gradient
        if imp > 0.5:
            # Red → Yellow
            t = (imp - 0.5) * 2
            red = 255
            green = int(60 + 195 * (1 - t))
            blue = int(48 * (1 - t))
        elif imp > 0.1:
            # Yellow → Light blue
            t = (imp - 0.1) / 0.4
            red = int(100 + 155 * t)
            green = int(160 + 95 * t)
            blue = int(220 - 172 * t)
        else:
            # Quiet blue-gray
            red, green, blue = 100, 160, 220

        color = f"#{red:02x}{green:02x}{blue:02x}"
        dist = distances[i]

        tooltip_parts = [f"Res {r}"]
        if r == mut_pos:
            tooltip_parts.append(f"MUTATION SITE: {query.mutation}")
            tooltip_parts.append(f"Disruption: {disruption:.0%}")
        else:
            tooltip_parts.append(f"Impact: {imp:.0%}")
            tooltip_parts.append(f"Distance from mutation: {dist:.1f} Å")
        if r in plddt_lookup:
            tooltip_parts.append(f"pLDDT: {plddt_lookup[r]:.0f}")

        annotations.append({
            "label_asym_id": first_chain,
            "label_seq_id": r,
            "color": color,
            "tooltip": " | ".join(tooltip_parts),
        })

    _render_molstar_with_annotations(prediction, annotations)

    # Legend
    st.markdown(
        '<div style="display:flex;gap:8px;align-items:center;margin-top:8px">'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">No impact</span>'
        '<span style="display:inline-block;width:120px;height:12px;border-radius:2px;'
        'background:linear-gradient(to right,#64A0DC,#FFF030,#FF3B30)"></span>'
        '<span style="font-size:0.82em;color:rgba(60,60,67,0.6)">High impact</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Metrics
    n_high = int(np.sum(impact > 0.5))
    n_medium = int(np.sum((impact > 0.1) & (impact <= 0.5)))
    impact_radius = float(np.percentile(distances[impact > 0.1], 90)) if np.sum(impact > 0.1) > 0 else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Disruption Score", f"{disruption:.0%}",
                help="Combined volume + charge + hydrophobicity change")
    col2.metric("High Impact Zone", f"{n_high} residues")
    col3.metric("Medium Impact Zone", f"{n_medium} residues")
    col4.metric("Impact Radius", f"{impact_radius:.0f} Å",
                help="90th percentile distance of affected residues")

    # Interpretation
    if disruption > 0.6:
        st.error(
            f"**{query.mutation} causes severe physicochemical disruption** — "
            f"volume Δ{vol_delta:.0%}, charge Δ{charge_delta:.0%}, "
            f"hydrophobicity Δ{hydro_delta:.0%}. The impact field extends "
            f"to {n_high + n_medium} surrounding residues."
        )
    elif disruption > 0.3:
        st.warning(
            f"**{query.mutation} causes moderate disruption** — "
            f"the structural shockwave affects {n_high + n_medium} residues "
            f"within {impact_radius:.0f} Å."
        )
    else:
        st.info(
            f"**{query.mutation} is a conservative substitution** — "
            f"limited structural impact predicted (disruption {disruption:.0%})."
        )

    _render_provenance_badge(prediction)


def _render_color_legend():
    """Show the pLDDT color legend below the viewer — single compact row."""
    legend = [
        ("#0053D6", ">90"),
        ("#65CBF3", "70-90"),
        ("#FFDB13", "50-70"),
        ("#FF7D45", "<50"),
    ]
    legend_html = "".join(
        f'<span style="display:inline-flex;align-items:center;gap:3px;margin-right:12px">'
        f'<span style="width:10px;height:10px;background:{c};border-radius:2px;display:inline-block"></span>'
        f'<span style="font-size:0.76rem;color:rgba(60,60,67,0.6)">{lbl}</span></span>'
        for c, lbl in legend
    )
    st.markdown(
        f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:2px;margin:4px 0">'
        f'<span style="font-size:0.74rem;color:rgba(60,60,67,0.45);margin-right:4px">pLDDT:</span>'
        f'{legend_html}</div>',
        unsafe_allow_html=True,
    )


def _render_provenance_badge(prediction: PredictionResult):
    """Show which compute backend produced this structure."""
    source_labels = {
        "tamarind": ("Tamarind Bio Boltz-2", "#34C759"),
        "modal": ("Modal H100 GPU", "#AF52DE"),
        "rcsb": ("RCSB PDB (experimental)", "#0891B2"),
        "precomputed": ("Precomputed Demo", "rgba(60,60,67,0.55)"),
    }
    label, color = source_labels.get(
        prediction.compute_source, ("Unknown", "rgba(60,60,67,0.55)")
    )
    st.markdown(
        f'<div style="margin-top:4px;margin-bottom:8px">'
        f'<span style="background:#F2F2F7;border:2px solid {color};padding:3px 10px;'
        f'border-radius:12px;font-size:0.82em;color:{color};font-weight:600">'
        f'Computed via: {label}</span> '
        f'<span style="background:#F2F2F7;border:2px solid rgba(0,0,0,0.12);padding:3px 10px;'
        f'border-radius:12px;font-size:0.82em;color:rgba(60,60,67,0.55)">'
        f'Visualization: MolViewSpec / Mol*</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


def _render_auto_analyze(query: ProteinQuery, prediction: PredictionResult):
    """One-click button to run all recommended analyses for this protein."""
    if st.button(
        "Run All Recommended Analyses",
        type="primary",
        key="auto_analyze_btn",
        help="Automatically runs flexibility, pocket prediction, surface analysis, and disorder detection",
        width="stretch",
    ):
        first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
        progress = st.progress(0, text="Starting analyses...")

        analyses = [
            ("Flexibility (ANM)", f"flexibility_{query.protein_name}",
             lambda: _compute_flexibility(prediction.pdb_content, first_chain)),
            ("Binding Pockets", f"pockets_{query.protein_name}",
             lambda: _compute_pockets(prediction.pdb_content)),
        ]

        completed = 0
        for name, key, func in analyses:
            if st.session_state.get(key) is None:
                progress.progress(
                    completed / len(analyses),
                    text=f"Computing {name}..."
                )
                try:
                    result = func()
                    st.session_state[key] = result
                except Exception as e:
                    st.warning(f"{name} failed: {e}")
            completed += 1

        progress.progress(1.0, text="All analyses complete!")
        st.toast("All recommended analyses completed!")

    # Show which analyses are already computed
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else "A"
    status_items = [
        ("Flexibility", f"flexibility_{query.protein_name}"),
        ("Pockets", f"pockets_{query.protein_name}"),
    ]
    completed_count = sum(1 for _, key in status_items if st.session_state.get(key) is not None)
    if completed_count > 0:
        st.caption(f"{completed_count}/{len(status_items)} analyses cached")


def _render_trust_panel(query: ProteinQuery, trust_audit: TrustAudit):
    """Right panel showing trust audit summary with scroll-safe container."""
    emoji = confidence_emoji(trust_audit.overall_confidence)
    st.markdown(f"### {emoji} Trust Audit")
    # Inject scroll container for the trust panel so it doesn't push content
    # off-screen when all expanders are open
    st.markdown(
        '<style>.trust-audit-scroll [data-testid="stVerticalBlockBorderWrapper"] '
        "{ max-height: 65vh; overflow-y: auto; -webkit-overflow-scrolling: touch; "
        "overscroll-behavior-y: contain; padding-right: 4px; }</style>",
        unsafe_allow_html=True,
    )

    # Overall confidence with color-coded ring
    conf = trust_audit.confidence_score
    conf_color = "#34C759" if conf >= 0.7 else "#FF9500" if conf >= 0.5 else "#FF3B30"
    st.markdown(
        f'<div style="text-align:center;margin:8px 0 12px 0">'
        f'<div style="font-size:2.4rem;font-weight:800;color:{conf_color}">'
        f'{conf:.0%}</div>'
        f'<div style="font-size:0.82rem;color:rgba(60,60,67,0.6);text-transform:uppercase;'
        f'letter-spacing:1px" title="Overall prediction confidence. Higher means more trustworthy structure.">'
        f'{trust_audit.overall_confidence} '
        f'<span style="cursor:help;opacity:0.5;font-size:0.82em">&#9432;</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # Detailed scores in compact cards
    score_items = [
        ("pTM", trust_audit.ptm, "Predicted TM-score. >0.5 indicates correct fold, >0.8 is high confidence."),
        ("ipTM", trust_audit.iptm, "Interface pTM — confidence in protein-protein interactions. >0.8 is reliable."),
        ("Complex pLDDT", trust_audit.complex_plddt, "Per-residue confidence averaged across the complex. >70 is generally reliable."),
    ]
    for label, val, help_text in score_items:
        if val is not None:
            val_color = "#34C759" if val >= 0.7 else "#FF9500" if val >= 0.5 else "#FF3B30"
            st.markdown(
                f'<div class="glow-card" style="padding:6px 10px;margin-bottom:4px;'
                f'display:flex;justify-content:space-between;align-items:center">'
                f'<span style="color:rgba(60,60,67,0.6);font-size:0.85rem" '
                f'title="{help_text}">{label} '
                f'<span style="cursor:help;opacity:0.5;font-size:0.82em">&#9432;</span></span>'
                f'<span style="font-weight:700;color:{val_color}">{val:.3f}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Flagged regions — compact inline cards
    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        st.markdown(
            f'<div style="font-size:0.85rem;font-weight:600;margin:8px 0 4px;color:rgba(60,60,67,0.6)">'
            f'Flagged Regions ({len(flagged)})</div>',
            unsafe_allow_html=True,
        )
        for r in flagged[:8]:
            plddt_color = "#FF3B30" if r.avg_plddt < 50 else "#FF9500" if r.avg_plddt < 70 else "#8E8E93"
            st.markdown(
                f'<div style="display:flex;align-items:center;gap:6px;padding:4px 8px;'
                f'margin-bottom:3px;background:rgba(255,149,0,0.06);border-left:3px solid {plddt_color};'
                f'border-radius:0 6px 6px 0;font-size:0.78rem">'
                f'<span style="font-weight:600;color:{plddt_color};min-width:28px">{r.avg_plddt:.0f}</span>'
                f'<span style="color:rgba(60,60,67,0.8)">{r.chain}:{r.start_residue}-{r.end_residue}</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

    # Known limitations
    if trust_audit.known_limitations:
        with st.expander(f"Known Limitations ({len(trust_audit.known_limitations)})"):
            for lim in trust_audit.known_limitations:
                st.markdown(f"- {lim}")

    # Training data note
    if trust_audit.training_data_note:
        with st.expander("Training Data Bias"):
            st.markdown(trust_audit.training_data_note)

    # Suggested validations
    if trust_audit.suggested_validation:
        with st.expander("Suggested Experiments"):
            for s in trust_audit.suggested_validation:
                st.markdown(f"- {s}")

    # Pin to Playground
    from components.playground import pin_button

    flagged_count = len([r for r in trust_audit.regions if r.flag])
    pin_button(
        "Confidence Overview",
        f"Overall: {trust_audit.overall_confidence} ({trust_audit.confidence_score:.1%}), "
        f"{flagged_count} flagged regions",
        "metric",
        {
            "confidence_score": trust_audit.confidence_score,
            "overall": trust_audit.overall_confidence,
            "flagged_regions": flagged_count,
        },
        key="pin_trust_audit",
    )
