from __future__ import annotations

import json

import molviewspec as mvs
import streamlit as st

from src.models import PredictionResult, ProteinQuery, TrustAudit
from src.trust_auditor import build_trust_audit, get_residue_flags
from src.utils import (
    build_trust_annotations,
    confidence_emoji,
    load_precomputed,
    parse_pdb_plddt,
    run_async,
)


def render_structure_viewer():
    """Tab 2: 3D structure viewer with trust audit panel -- THE HERO SCREEN."""
    if not st.session_state.get("query_parsed"):
        st.info(
            "No query loaded yet. Go to the **Query** tab and enter a protein to investigate. "
            "You can type a protein name (e.g. TP53), add a mutation (e.g. R248W), "
            "or try one of the example queries."
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
            trust_audit = build_trust_audit(
                query,
                prediction.pdb_content,
                prediction.confidence_json,
                chain_ids=prediction.chain_ids if prediction.chain_ids else None,
                residue_ids=prediction.residue_ids if prediction.residue_ids else None,
                plddt_scores=prediction.plddt_per_residue if prediction.plddt_per_residue else None,
                is_experimental=(prediction.compute_source == "rcsb"),
            )
            st.session_state["trust_audit"] = trust_audit
        except Exception as e:
            st.error(
                f"Trust audit could not be completed: {e}\n\n"
                "The structure is still shown below. Trust metrics are unavailable."
            )
            # Don't return — continue rendering the structure without trust audit

    trust_audit: TrustAudit | None = st.session_state.get("trust_audit")

    # Auto-generate interpretation if context is loaded but interpretation isn't
    if (
        st.session_state.get("bio_context") is not None
        and st.session_state.get("interpretation") is None
    ):
        _auto_interpret(query, {})

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

    # Variant Pathogenicity Landscape
    from components.variant_landscape import render_variant_landscape

    render_variant_landscape(query, prediction)

    # Drug Resistance Mechanism Viewer
    from components.drug_resistance import render_drug_resistance

    render_drug_resistance(
        query, prediction, st.session_state.get("bio_context")
    )

    # Structural Insights (SASA, 3D distances, secondary structure)
    from components.structural_insights import render_structural_insights

    render_structural_insights(query, prediction)

    # Disorder Region Detector
    from components.disorder_detector import render_disorder_detection

    render_disorder_detection(query, prediction, trust_audit)

    # Auto-Analyze — one-click recommended analyses
    st.divider()
    _render_auto_analyze(query, prediction)

    # Tamarind Bio Multi-Tool Analysis
    st.divider()
    from components.tamarind_panel import render_tamarind_panel

    render_tamarind_panel(query, prediction)

    # Tamarind Bio Pipeline Builder — smart next steps + multi-tool workflows
    st.divider()
    from components.pipeline_builder import render_pipeline_builder

    render_pipeline_builder(query, prediction)

    # Residue Dashboard — genome-browser-style multi-track strip chart
    st.divider()
    from components.residue_dashboard import render_residue_dashboard

    structure_analysis = st.session_state.get("structure_analysis", {})
    variant_data = st.session_state.get(f"variant_data_{query.protein_name}")
    render_residue_dashboard(
        structure_analysis,
        prediction.plddt_per_residue or [],
        query,
        variant_data,
    )

    # Pin pLDDT to Playground
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

    # Send pLDDT data to Statistics tab
    if prediction.plddt_per_residue:
        import pandas as pd

        if st.button("Send to Statistics", key="struct_send_stats",
                     help="Send pLDDT data to the Statistics tab for analysis"):
            # Align lists to shortest length to prevent ValueError
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

    # Comprehensive residue annotation export
    if prediction.plddt_per_residue:
        n = min(
            len(prediction.residue_ids),
            len(prediction.chain_ids) if prediction.chain_ids else len(prediction.residue_ids),
            len(prediction.plddt_per_residue),
        )
        if st.button("Download All Residue Data (CSV)", key="export_residue_csv",
                     help="Export comprehensive per-residue analysis as CSV"):
            import io as _io

            data = {"residue_id": prediction.residue_ids[:n]}
            if prediction.chain_ids:
                data["chain"] = prediction.chain_ids[:n]
            if prediction.plddt_per_residue:
                data["plddt"] = prediction.plddt_per_residue[:n]

            # Add flexibility if computed
            flex_data = st.session_state.get(f"flexibility_{query.protein_name}")
            if flex_data and flex_data.get("flexibility"):
                flex_map = dict(zip(flex_data["residue_ids"], flex_data["flexibility"]))
                data["flexibility"] = [flex_map.get(r, None) for r in data["residue_id"]]

            # Add pocket scores if computed
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

    # Advanced analysis section
    with st.expander("Advanced Analysis", expanded=False):
        adv_tab1, adv_tab2, adv_tab3, adv_tab4 = st.tabs([
            "Confidence Heatmap", "PAE Domain Map",
            "Electrostatic Surface", "AlphaFold Comparison",
        ])
        with adv_tab1:
            from components.confidence_heatmap import render_confidence_heatmap

            render_confidence_heatmap(prediction)
        with adv_tab2:
            from components.pae_viewer import render_pae_viewer

            render_pae_viewer(prediction.confidence_json or {}, query)
        with adv_tab3:
            from components.electrostatics_viewer import render_electrostatics_panel

            render_electrostatics_panel(prediction.pdb_content, query)
        with adv_tab4:
            from components.alphafold_compare import render_alphafold_comparison

            render_alphafold_comparison(query, prediction)

    # Variant Comparison Mode
    from components.comparison_mode import render_comparison_mode

    render_comparison_mode(query, prediction, trust_audit)


def _run_prediction(query: ProteinQuery):
    """Submit Boltz-2 prediction or load precomputed/RCSB results.

    Fallback chain: precomputed → Tamarind API → Modal H100 → RCSB PDB
    """
    # Check user-selected compute backend
    backend = st.session_state.get("compute_backend", "auto")

    # Try precomputed first (demo resilience) — unless user forced a backend
    if backend == "auto":
        example_map = {
            "TP53": "p53_r248w",
            "BRCA1": "brca1_c61g",
            "EGFR": "egfr_t790m",
            "INS": "insulin",
            "SPIKE": "spike_rbd",
            "HBA1": "hba1_hemoglobin",
        }
        example_name = example_map.get(query.protein_name.upper())
        if example_name:
            precomputed = load_precomputed(example_name)
            if precomputed and precomputed.get("pdb"):
                confidence = dict(precomputed.get("confidence", {}))
                plddt_override = confidence.pop("plddt_per_residue", None)
                chain_override = confidence.pop("chain_ids", None)
                resid_override = confidence.pop("residue_ids", None)

                affinity_data = precomputed.get("affinity")
                if plddt_override and chain_override and resid_override:
                    st.session_state["prediction_result"] = PredictionResult(
                        pdb_content=precomputed["pdb"],
                        confidence_json=confidence,
                        affinity_json=affinity_data,
                        plddt_per_residue=plddt_override,
                        chain_ids=chain_override,
                        residue_ids=resid_override,
                        compute_source="precomputed",
                    )
                else:
                    _store_prediction(
                        precomputed["pdb"], confidence, affinity_data,
                        source="precomputed",
                    )

                if precomputed.get("context") and st.session_state.get("bio_context") is None:
                    _load_precomputed_context(precomputed["context"])

                if precomputed.get("variants"):
                    var_key = f"variant_data_{query.protein_name}"
                    if st.session_state.get(var_key) is None:
                        st.session_state[var_key] = precomputed["variants"]

                # Load precomputed structure analysis, flexibility, pockets
                if precomputed.get("structure_analysis"):
                    cache_key = f"struct_analysis_{query.protein_name}_{query.mutation}"
                    if st.session_state.get(cache_key) is None:
                        st.session_state[cache_key] = precomputed["structure_analysis"]
                    if not st.session_state.get("structure_analysis"):
                        st.session_state["structure_analysis"] = precomputed["structure_analysis"]

                if precomputed.get("flexibility"):
                    flex_key = f"flexibility_{query.protein_name}"
                    if st.session_state.get(flex_key) is None:
                        st.session_state[flex_key] = precomputed["flexibility"]

                if precomputed.get("pockets"):
                    pocket_key = f"pockets_{query.protein_name}"
                    if st.session_state.get(pocket_key) is None:
                        st.session_state[pocket_key] = precomputed["pockets"]

                if precomputed.get("interpretation"):
                    if st.session_state.get("interpretation") is None:
                        interp_data = precomputed["interpretation"]
                        st.session_state["interpretation"] = interp_data.get("text", "")

                _auto_interpret(query, precomputed)
                st.caption(f"Loaded Boltz-2 prediction for {query.protein_name}")
                return

    # Live compute — respect user backend choice or auto-fallback
    if query.sequence:
        st.session_state["pipeline_running"] = True
        if backend in ("auto", "tamarind"):
            if _run_tamarind(query):
                st.session_state["pipeline_running"] = False
                return
        if backend in ("auto", "modal"):
            if _run_modal(query):
                st.session_state["pipeline_running"] = False
                return
        st.session_state["pipeline_running"] = False

    # RCSB PDB fallback
    if backend in ("auto", "rcsb") and query.uniprot_id:
        st.session_state["pipeline_running"] = True
        _fetch_from_rcsb(query)
        st.session_state["pipeline_running"] = False
        return

    st.warning(
        "No sequence or precomputed data available. "
        "Select an example or provide a protein sequence."
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


def _auto_interpret(query: ProteinQuery, precomputed: dict):
    """Auto-generate interpretation when precomputed data is loaded."""
    if st.session_state.get("interpretation") is not None:
        return
    # Build trust audit first if needed
    trust_audit = st.session_state.get("trust_audit")
    bio_context = st.session_state.get("bio_context")
    if trust_audit and bio_context:
        try:
            from src.interpreter import generate_interpretation
            interp = generate_interpretation(query, trust_audit, bio_context)
            st.session_state["interpretation"] = interp
        except Exception:
            from src.interpreter import _fallback_interpretation
            st.session_state["interpretation"] = _fallback_interpretation(
                query, trust_audit, bio_context
            )


def _load_precomputed_context(context_data: dict):
    """Load precomputed biological context into session state."""
    from src.models import BioContext, DiseaseAssociation, DrugCandidate, LiteratureSummary

    st.session_state["bio_context"] = BioContext(
        narrative=context_data.get("narrative", ""),
        disease_associations=[
            DiseaseAssociation(**d) for d in context_data.get("disease_associations", [])
        ],
        drugs=[DrugCandidate(**d) for d in context_data.get("drugs", [])],
        literature=LiteratureSummary(**context_data.get("literature", {})),
        pathways=context_data.get("pathways", []),
        suggested_experiments=context_data.get("suggested_experiments", []),
    )


def _fetch_from_rcsb(query: ProteinQuery):
    """Fetch a known structure from RCSB PDB as fallback."""
    import httpx

    with st.spinner(f"Fetching experimental structure for {query.uniprot_id} from RCSB PDB..."):
        try:
            search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
            search_query = {
                "query": {
                    "type": "terminal",
                    "service": "text",
                    "parameters": {
                        "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                        "operator": "exact_match",
                        "value": query.uniprot_id,
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
                st.warning("RCSB PDB search failed.")
                return

            results = resp.json()
            hits = results.get("result_set", [])
            if not hits:
                st.warning("No experimental structures found in RCSB PDB.")
                return

            pdb_id = hits[0].get("identifier", "")
            if not pdb_id:
                return

            pdb_resp = httpx.get(
                f"https://files.rcsb.org/download/{pdb_id}.pdb", timeout=30
            )
            if pdb_resp.status_code != 200:
                st.warning(f"Could not download PDB {pdb_id}.")
                return

            _store_prediction(pdb_resp.text, {}, source="rcsb",
                             skip_plddt=True)
            st.warning(
                f"Loaded experimental structure **{pdb_id}** from RCSB PDB. "
                "**B-factors are NOT pLDDT scores** — confidence metrics are unavailable "
                "for experimental structures. Trust audit values are not meaningful."
            )

        except Exception as e:
            st.warning(f"RCSB PDB fetch failed: {e}")


def _store_prediction(
    pdb_content: str, confidence: dict,
    affinity: dict | None = None, source: str = "precomputed",
    skip_plddt: bool = False,
):
    """Parse PDB and store prediction result in session state.

    Set skip_plddt=True for experimental structures (RCSB) where B-factors
    are crystallographic, not pLDDT confidence scores.
    """
    chain_ids, residue_ids, plddt_scores = [], [], []
    if pdb_content:
        try:
            chain_ids, residue_ids, plddt_scores = parse_pdb_plddt(pdb_content)
        except Exception:
            pass

    # For RCSB structures, B-factors are NOT pLDDT — don't use them
    if skip_plddt:
        plddt_scores = []

    st.session_state["prediction_result"] = PredictionResult(
        pdb_content=pdb_content,
        confidence_json=confidence,
        affinity_json=affinity,
        plddt_per_residue=plddt_scores,
        chain_ids=chain_ids,
        residue_ids=residue_ids,
        compute_source=source,
    )


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
        "Flexibility (ANM)", "NMA Animation", "Binding Pockets",
        "Charge Surface", "Structure Diff",
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
    elif color_mode == "Binding Pockets":
        _render_pocket_overlay(query, prediction, trust_audit)
        return
    elif color_mode == "Charge Surface":
        _render_charge_surface(query, prediction, trust_audit)
        return
    elif color_mode == "Structure Diff":
        _render_structure_diff(query, prediction, trust_audit)
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
def _compute_pockets(pdb_content: str) -> dict:
    from src.pocket_prediction import predict_pockets
    return predict_pockets(pdb_content)


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
    st.plotly_chart(fig, use_container_width=True)

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
            pocket_data = _compute_pockets(prediction.pdb_content)
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
            tooltip = f"Res {res_id}: Pocket {pocket_rank} (score {pocket_scores.get(res_id, 0):.2f})"
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

    charge_map = charge_data["charge"]
    res_ids = charge_data["residue_ids"]

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
    st.plotly_chart(fig, use_container_width=True)

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

            with st.spinner("Fetching AlphaFold structure..."):
                af_data = _fetch_alphafold(query.uniprot_id)
            if af_data is None:
                st.error(
                    f"Could not fetch AlphaFold structure for {query.uniprot_id}. "
                    "This protein may not be in the AlphaFold Database."
                )
                return
            st.session_state[af_key] = af_data
            st.rerun()
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
            with st.spinner("Aligning structures and computing RMSD..."):
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

    per_res_rmsd = diff_result["per_residue_rmsd"]

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
    mcol1.metric("Global RMSD", f"{diff_result['global_rmsd']:.2f} A")
    mcol2.metric("GDT-TS", f"{diff_result['gdt_ts']:.3f}")
    mcol3.metric("TM-score", f"{diff_result['tm_score']:.3f}")

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
    st.plotly_chart(fig, use_container_width=True)

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
                f"{s[0]}-{s[-1]}" if len(s) > 1 else str(s[0])
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
        st.plotly_chart(fig, use_container_width=True)

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
        st.plotly_chart(fig, use_container_width=True)

    _render_provenance_badge(prediction)


def _render_molstar_with_annotations(prediction: PredictionResult, annotations: list[dict]):
    """Render Mol* with custom color/tooltip annotations."""
    import molviewspec as mvs

    builder = mvs.create_builder()
    structure = (
        builder.download(url="structure.pdb")
        .parse(format="pdb")
        .model_structure()
    )

    rep = structure.component(selector="polymer").representation(type="cartoon")
    rep.color(color="#888888")

    if annotations:
        rep.color_from_uri(uri="overlay_colors.json", format="json", schema="residue")
        structure.tooltip_from_uri(uri="overlay_tooltips.json", format="json", schema="residue")

    color_data = [
        {"label_asym_id": a["label_asym_id"], "label_seq_id": a["label_seq_id"], "color": a["color"]}
        for a in annotations
    ]
    tooltip_data = [
        {"label_asym_id": a["label_asym_id"], "label_seq_id": a["label_seq_id"], "tooltip": a["tooltip"]}
        for a in annotations
    ]

    data = {"structure.pdb": prediction.pdb_content.encode("utf-8")}
    if annotations:
        data["overlay_colors.json"] = json.dumps(color_data).encode("utf-8")
        data["overlay_tooltips.json"] = json.dumps(tooltip_data).encode("utf-8")

    mvs.molstar_streamlit(builder, data=data, height=600)


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
        use_container_width=True,
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
        st.rerun()

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
