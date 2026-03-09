"""Tamarind Bio Pipeline Builder — smart next-step recommendations + multi-tool workflows.

After any analysis completes, this component recommends context-aware next steps
with one-click "Run This" buttons. It also provides predefined pipeline templates
for common workflows like mutation analysis, drug target validation, and binder design.

Results flow back into session state to update the structure viewer and trust audit.
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from src.models import PredictionResult, ProteinQuery
from src.tamarind_analyses import ANALYSIS_REGISTRY, get_available_analyses, is_available
from src.utils import run_async

# ────────────────────────────────────────────────────────
# Pipeline template definitions
# ────────────────────────────────────────────────────────

PIPELINE_TEMPLATES: dict[str, dict[str, Any]] = {
    "full_mutation": {
        "name": "Full Mutation Analysis",
        "description": "Comprehensive mutation impact assessment: predict structure, "
                       "quantify stability change, scan for stabilizing substitutions, "
                       "and assess solubility and aggregation risk.",
        "tools": [
            ("proteinmpnn-ddg", "ProteinMPNN-ddG", "Stability change (ddG)"),
            ("thermompnn", "ThermoMPNN", "Full mutation scan"),
            ("camsol", "CamSol", "Solubility impact"),
            ("aggrescan3d", "Aggrescan3D", "Aggregation risk"),
        ],
        "color": "#F59E0B",
        "icon": "Mut",
        "requires": "mutation",
    },
    "drug_target": {
        "name": "Drug Target Validation",
        "description": "End-to-end druggability assessment: map binding surfaces, "
                       "dock known drugs, and generate novel small molecules.",
        "tools": [
            ("masif", "MaSIF", "Surface fingerprint"),
            ("autodock-vina", "AutoDock Vina", "Molecular docking"),
            ("reinvent", "REINVENT 4", "De novo drug design"),
        ],
        "color": "#7C3AED",
        "icon": "Drug",
        "requires": None,
    },
    "binder_design": {
        "name": "Binder Design",
        "description": "Design protein binders targeting your structure: score binding energy, "
                       "generate de novo binders, and redesign interfaces.",
        "tools": [
            ("prodigy", "PRODIGY", "Binding energy"),
            ("boltzgen", "BoltzGen", "De novo binders"),
            ("proteinmpnn", "ProteinMPNN", "Interface redesign"),
        ],
        "color": "#34C759",
        "icon": "Bind",
        "requires": None,
    },
    "protein_engineering": {
        "name": "Protein Engineering",
        "description": "Engineer better proteins: cross-validate structure, assess thermostability, "
                       "and redesign sequences for improved properties.",
        "tools": [
            ("esmfold", "ESMFold", "Structure cross-validation"),
            ("temstapro", "TemStaPro", "Thermostability"),
            ("proteinmpnn", "ProteinMPNN", "Sequence redesign"),
        ],
        "color": "#0891B2",
        "icon": "Eng",
        "requires": "sequence",
    },
}


# ────────────────────────────────────────────────────────
# Tool metadata for recommendations
# ────────────────────────────────────────────────────────

_TOOL_TIME_ESTIMATES: dict[str, str] = {
    "esmfold": "~30s",
    "aggrescan3d": "~1-2 min",
    "temstapro": "~30s",
    "camsol": "~1-2 min",
    "proteinmpnn-ddg": "~1-2 min",
    "thermompnn": "~3-5 min",
    "autodock-vina": "~3-5 min",
    "gnina": "~3-5 min",
    "masif": "~3-5 min",
    "reinvent": "~5-10 min",
    "prodigy": "~1-2 min",
    "boltzgen": "~5-10 min",
    "proteinmpnn": "~1-2 min",
}

_TOOL_RELEVANCE: dict[str, dict[str, str]] = {
    "esmfold": {
        "structure": "Cross-validate Boltz-2 with a fast single-sequence predictor",
        "mutation_impact": "See how the mutation affects an independent structure prediction",
        "druggability": "Quick structure check before investing in docking",
        "binding": "Verify binding interface prediction with an orthogonal method",
    },
    "aggrescan3d": {
        "structure": "Identify aggregation-prone regions in your predicted structure",
        "mutation_impact": "Check if the mutation creates new aggregation hotspots",
        "druggability": "Ensure target protein is stable enough for drug development",
        "binding": "Verify binder candidates won't aggregate",
    },
    "temstapro": {
        "structure": "Assess whether this protein is thermally stable",
        "mutation_impact": "Quantify thermostability impact of the mutation",
        "druggability": "Confirm target stability for assay development",
        "binding": "Check if binding interface is in a stable region",
    },
    "camsol": {
        "structure": "Profile solubility across the protein sequence",
        "mutation_impact": "Does the mutation affect protein solubility?",
        "druggability": "Solubility check for recombinant protein production",
        "binding": "Assess solubility of designed binders",
    },
    "proteinmpnn-ddg": {
        "mutation_impact": "Quantify exactly how much your mutation destabilizes the fold",
        "structure": "Screen for stabilizing mutations to improve your construct",
        "druggability": "Identify resistance mutations that may affect drug binding",
        "binding": "Predict whether interface mutations affect stability",
    },
    "thermompnn": {
        "mutation_impact": "Scan ALL possible mutations for stabilizing substitutions",
        "structure": "Find the most stabilizing mutations for protein engineering",
        "druggability": "Identify potential resistance mutations comprehensively",
        "binding": "Optimize interface residues for thermal stability",
    },
    "autodock-vina": {
        "druggability": "Dock known drugs to validate predicted binding pockets",
        "mutation_impact": "See if the mutation disrupts drug binding geometry",
        "structure": "Explore whether any known compounds bind this structure",
        "binding": "Dock small molecule competitors against protein binders",
    },
    "gnina": {
        "druggability": "CNN-enhanced docking for higher accuracy than Vina alone",
        "mutation_impact": "AI-scored docking to detect subtle binding changes",
        "structure": "Advanced docking with learned scoring functions",
        "binding": "Score small molecule interference with protein interactions",
    },
    "masif": {
        "druggability": "Map druggable surface patches with geometric deep learning",
        "binding": "Characterize the binding interface fingerprint",
        "structure": "Discover potential interaction surfaces",
        "mutation_impact": "Check if mutation alters surface interaction properties",
    },
    "reinvent": {
        "druggability": "Generate novel small molecules optimized for this target",
        "structure": "Explore chemical space for structure-based drug design",
        "mutation_impact": "Design drugs that work despite the mutation",
        "binding": "Generate small molecule modulators of protein interactions",
    },
    "prodigy": {
        "binding": "Predict binding free energy and dissociation constant",
        "druggability": "Score protein-drug binding affinity",
        "structure": "Assess inter-chain binding strength in complexes",
        "mutation_impact": "Quantify how the mutation affects binding energy",
    },
    "boltzgen": {
        "binding": "Design de novo protein binders with 60-70% experimental hit rate",
        "druggability": "Generate biologic alternatives to small molecule drugs",
        "structure": "Design binders to probe functional regions",
        "mutation_impact": "Create binders that target the mutant form specifically",
    },
    "proteinmpnn": {
        "binding": "Redesign binding interface for improved affinity",
        "structure": "Inverse folding: redesign sequence to match desired structure",
        "mutation_impact": "Find compensatory mutations to rescue destabilized fold",
        "druggability": "Design protein variants with enhanced druggability",
    },
}


# ────────────────────────────────────────────────────────
# Main render function
# ────────────────────────────────────────────────────────


def render_pipeline_builder(
    query: ProteinQuery,
    prediction: PredictionResult,
):
    """Render the Tamarind Bio Pipeline Builder section."""
    st.markdown("### Tamarind Bio Pipeline Builder")
    st.caption(
        "Run multi-tool workflows with one click, or pick individual next steps. "
        "All tools run via Tamarind Bio's cloud compute."
    )

    # Initialize tamarind_results in session state if not present
    if "tamarind_results" not in st.session_state:
        st.session_state["tamarind_results"] = {}

    # Check if there are already completed analyses
    existing_results = st.session_state.get("tamarind_results", {})

    # Section 1: Pipeline Templates
    _render_pipeline_templates(query, prediction)

    # Section 2: Smart Next-Step Recommender
    st.markdown("---")
    _render_smart_recommendations(query, prediction, existing_results)

    # Section 3: Results Summary (if any results exist)
    if existing_results:
        st.markdown("---")
        _render_results_summary(query, existing_results)


# ────────────────────────────────────────────────────────
# Pipeline Templates
# ────────────────────────────────────────────────────────


def _render_pipeline_templates(
    query: ProteinQuery,
    prediction: PredictionResult,
):
    """Render predefined pipeline template cards with visual workflow diagrams."""
    st.markdown("#### Pipeline Templates")
    st.caption("Predefined multi-tool workflows for common analysis patterns.")

    # Filter templates: show most relevant first, but show all
    question_type = query.question_type
    priority_order = {
        "mutation_impact": ["full_mutation", "protein_engineering", "drug_target", "binder_design"],
        "druggability": ["drug_target", "binder_design", "full_mutation", "protein_engineering"],
        "binding": ["binder_design", "drug_target", "protein_engineering", "full_mutation"],
        "structure": ["protein_engineering", "drug_target", "binder_design", "full_mutation"],
    }
    ordered_keys = priority_order.get(question_type, list(PIPELINE_TEMPLATES.keys()))

    cols = st.columns(2)
    for idx, tpl_key in enumerate(ordered_keys):
        tpl = PIPELINE_TEMPLATES[tpl_key]
        col = cols[idx % 2]

        with col:
            # Check if template requirements are met
            can_run = True
            missing_reason = ""
            if tpl["requires"] == "mutation" and not query.mutation:
                can_run = False
                missing_reason = "Requires a mutation in query"
            elif tpl["requires"] == "sequence" and not query.sequence:
                can_run = False
                missing_reason = "Requires a protein sequence"

            api_available = is_available()

            # Template card
            color = tpl["color"]
            st.markdown(
                f'<div class="glow-card" style="border-color:{color};margin-bottom:12px;padding:12px 16px">'
                f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">'
                f'<span style="background:{color};color:#000;padding:2px 8px;border-radius:4px;'
                f'font-size:0.75em;font-weight:700">{tpl["icon"]}</span>'
                f'<span style="color:{color};font-weight:700;font-size:1.05rem">{tpl["name"]}</span>'
                f'</div>'
                f'<div style="font-size:0.82em;color:rgba(60,60,67,0.6);margin-bottom:10px">'
                f'{tpl["description"]}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            # Visual pipeline flow
            _render_pipeline_flow(tpl["tools"], color)

            # Check which tools already have results
            completed_tools = [
                t[0] for t in tpl["tools"]
                if t[0] in st.session_state.get("tamarind_results", {})
            ]
            remaining_tools = [
                t[0] for t in tpl["tools"]
                if t[0] not in st.session_state.get("tamarind_results", {})
            ]

            # Run button
            if not api_available:
                st.info(
                    "Tamarind Bio API key required to run this pipeline. "
                    "Add `TAMARIND_API_KEY=your_key` to your `.env` file in the project root. "
                    "Get a free key at [tamarind.bio](https://tamarind.bio).",
                    icon="🔑",
                )
            elif not can_run:
                st.caption(f"_{missing_reason}_")
            elif not remaining_tools:
                st.success("All tools in this pipeline have completed.")
            else:
                n_remaining = len(remaining_tools)
                btn_label = (
                    f"Run Full Pipeline ({len(tpl['tools'])} tools)"
                    if not completed_tools
                    else f"Run Remaining ({n_remaining} tool{'s' if n_remaining != 1 else ''})"
                )
                if st.button(
                    btn_label,
                    key=f"pipeline_run_{tpl_key}",
                    type="primary",
                    width="stretch",
                ):
                    _execute_pipeline(query, prediction, tpl, remaining_tools)


def _render_pipeline_flow(tools: list[tuple[str, str, str]], color: str):
    """Render a visual workflow diagram using styled HTML divs with arrows."""
    flow_html_parts = []
    for i, (tool_key, display_name, short_desc) in enumerate(tools):
        # Check if this tool has results
        has_result = tool_key in st.session_state.get("tamarind_results", {})
        bg_color = "rgba(52,199,89,0.06)" if has_result else "#F2F2F7"
        border = f"1px solid {'#34C759' if has_result else 'rgba(0,0,0,0.06)'}"
        status_dot = (
            '<span style="color:#34C759;font-size:0.7em">done</span>'
            if has_result
            else f'<span style="color:rgba(60,60,67,0.55);font-size:0.7em">{_TOOL_TIME_ESTIMATES.get(tool_key, "")}</span>'
        )

        flow_html_parts.append(
            f'<div style="display:inline-flex;align-items:center;gap:4px">'
            f'<div style="background:{bg_color};border:{border};padding:4px 10px;'
            f'border-radius:6px;font-size:0.78em;text-align:center;min-width:80px">'
            f'<div style="color:#000000;font-weight:600">{display_name}</div>'
            f'{status_dot}'
            f'</div>'
        )

        # Add arrow between steps (not after last)
        if i < len(tools) - 1:
            flow_html_parts.append(
                f'<span style="color:{color};font-size:1.2em;margin:0 2px">&#8594;</span>'
            )

        flow_html_parts.append('</div>')

    st.markdown(
        '<div style="display:flex;flex-wrap:wrap;align-items:center;gap:4px;margin:6px 0 10px 0">'
        + "".join(flow_html_parts)
        + '</div>',
        unsafe_allow_html=True,
    )


def _execute_pipeline(
    query: ProteinQuery,
    prediction: PredictionResult,
    template: dict[str, Any],
    tool_keys: list[str],
):
    """Execute a pipeline template — run tools sequentially with progress."""
    from src.tamarind_analyses import _run_safe

    total = len(tool_keys)
    progress_bar = st.progress(0, text=f"Starting pipeline: {template['name']}...")

    results_dict = st.session_state.get("tamarind_results", {})

    # Get drug SMILES from bio context if needed
    drug_smiles = _get_drug_smiles_from_context()

    for i, tool_key in enumerate(tool_keys):
        display_name = next(
            (t[1] for t in template["tools"] if t[0] == tool_key), tool_key
        )
        progress_bar.progress(
            (i) / total,
            text=f"Running {display_name} ({i + 1}/{total})...",
        )

        async def _run_tool(tk=tool_key):
            return await _run_safe(tk, query, prediction.pdb_content, drug_smiles)

        result = run_async(_run_tool())

        # Store result
        results_dict[tool_key] = result
        _integrate_result_into_state(tool_key, result, query)

    st.session_state["tamarind_results"] = results_dict
    progress_bar.progress(1.0, text=f"Pipeline complete: {template['name']}")


# ────────────────────────────────────────────────────────
# Smart Next-Step Recommender
# ────────────────────────────────────────────────────────


def _render_smart_recommendations(
    query: ProteinQuery,
    prediction: PredictionResult,
    existing_results: dict[str, Any],
):
    """Show context-aware recommended next tools with one-click run buttons."""
    st.markdown("#### Recommended Next Steps")

    # Get tools relevant to this question type
    available = get_available_analyses(query.question_type)
    # Also add tools from other question types that might be relevant
    all_tool_keys = set()
    for tools_list in ANALYSIS_REGISTRY.values():
        for t in tools_list:
            all_tool_keys.add(t[0])

    # Build recommendations: exclude already-completed tools
    completed_keys = set(existing_results.keys())
    recommendations = []

    # First: tools recommended for this question type (not yet run)
    for tool_key, display_name, description in available:
        if tool_key not in completed_keys:
            relevance = _TOOL_RELEVANCE.get(tool_key, {}).get(
                query.question_type, description
            )
            recommendations.append((tool_key, display_name, relevance, "primary"))

    # Second: tools from other question types (cross-domain insights)
    for qt, tools_list in ANALYSIS_REGISTRY.items():
        if qt == query.question_type:
            continue
        for tool_key, display_name, description in tools_list:
            if tool_key not in completed_keys and tool_key not in {r[0] for r in recommendations}:
                relevance = _TOOL_RELEVANCE.get(tool_key, {}).get(
                    query.question_type, description
                )
                recommendations.append((tool_key, display_name, relevance, "secondary"))

    if not recommendations:
        st.success("All available analyses have been run. Check the results summary below.")
        return

    if not is_available():
        st.info(
            "Set `TAMARIND_API_KEY` in your `.env` file to enable one-click tool execution. "
            "Below are the tools that would be recommended for your query."
        )

    # Show recommendations in groups: primary (for this question type) and secondary (cross-domain)
    primary_recs = [r for r in recommendations if r[3] == "primary"]
    secondary_recs = [r for r in recommendations if r[3] == "secondary"]

    if primary_recs:
        _render_recommendation_cards(
            primary_recs, query, prediction, "For this analysis"
        )

    if secondary_recs:
        with st.expander(f"Cross-Domain Tools ({len(secondary_recs)} more)", expanded=False):
            _render_recommendation_cards(
                secondary_recs, query, prediction, "Additional tools"
            )


def _render_recommendation_cards(
    recommendations: list[tuple[str, str, str, str]],
    query: ProteinQuery,
    prediction: PredictionResult,
    section_label: str,
):
    """Render recommendation cards with run buttons."""
    cols = st.columns(min(len(recommendations), 3))
    for i, (tool_key, display_name, relevance, _priority) in enumerate(recommendations):
        col = cols[i % min(len(recommendations), 3)]
        time_est = _TOOL_TIME_ESTIMATES.get(tool_key, "~2-5 min")

        with col:
            st.markdown(
                f'<div class="glow-card" style="padding:10px 14px;margin-bottom:8px">'
                f'<div style="font-weight:700;color:#000000;font-size:0.95rem;margin-bottom:4px">'
                f'{display_name}</div>'
                f'<div style="font-size:0.8em;color:rgba(60,60,67,0.6);margin-bottom:6px">{relevance}</div>'
                f'<div style="font-size:0.72em;color:rgba(60,60,67,0.55)">Est. time: {time_est}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

            if is_available():
                # Check if requirements are met
                can_run = _check_tool_requirements(tool_key, query)
                if can_run:
                    if st.button(
                        f"Run {display_name}",
                        key=f"rec_run_{tool_key}",
                        width="stretch",
                    ):
                        _execute_single_tool(tool_key, display_name, query, prediction)
                else:
                    st.caption("_Missing required input_")


def _check_tool_requirements(tool_key: str, query: ProteinQuery) -> bool:
    """Check if a tool's input requirements are met by the current query."""
    sequence_required = {"esmfold", "temstapro", "camsol"}
    mutation_required = {"proteinmpnn-ddg"}
    drug_required = {"autodock-vina", "gnina"}

    if tool_key in sequence_required and not query.sequence:
        return False
    if tool_key in mutation_required and not query.mutation:
        return False
    if tool_key in drug_required:
        # Can run if drug SMILES are available from context
        smiles = _get_drug_smiles_from_context()
        if not smiles:
            return False
    return True


def _execute_single_tool(
    tool_key: str,
    display_name: str,
    query: ProteinQuery,
    prediction: PredictionResult,
):
    """Execute a single Tamarind tool and store results."""
    from src.tamarind_analyses import _run_safe

    drug_smiles = _get_drug_smiles_from_context()

    with st.status(f"Running {display_name}...", expanded=False):
        async def _run():
            return await _run_safe(tool_key, query, prediction.pdb_content, drug_smiles)

        result = run_async(_run())

    results_dict = st.session_state.get("tamarind_results", {})
    results_dict[tool_key] = result
    st.session_state["tamarind_results"] = results_dict
    _integrate_result_into_state(tool_key, result, query)


# ────────────────────────────────────────────────────────
# Results Summary
# ────────────────────────────────────────────────────────


def _render_results_summary(query: ProteinQuery, results: dict[str, Any]):
    """Render a summary of all pipeline results with key findings."""
    st.markdown("#### Pipeline Results Summary")

    successes = {k: v for k, v in results.items() if v.get("type") not in ("error", "skipped")}
    errors = {k: v for k, v in results.items() if v.get("type") in ("error", "skipped")}

    if not successes and not errors:
        return

    # Summary metrics row
    mcols = st.columns(3)
    mcols[0].metric("Tools Completed", len(successes))
    mcols[1].metric("Errors", len(errors))
    mcols[2].metric("Total Run", len(results))

    # Key findings card
    findings = _extract_key_findings(successes, query)
    if findings:
        st.markdown(
            '<div class="glow-card" style="border-color:#34C759;padding:14px 18px;margin:8px 0">'
            '<div style="color:#34C759;font-weight:700;font-size:1rem;margin-bottom:8px">'
            'Key Findings</div>',
            unsafe_allow_html=True,
        )
        for finding in findings:
            st.markdown(f"- {finding}")
        st.markdown('</div>', unsafe_allow_html=True)

    # Individual tool result expanders
    for tool_key, result in successes.items():
        tool_name = result.get("tool", tool_key)
        rtype = result.get("type", "").replace("_", " ").title()
        with st.expander(f"**{tool_name}** -- {rtype}", expanded=False):
            _render_inline_result(result, query)

    # Errors
    if errors:
        with st.expander(f"Errors ({len(errors)})", expanded=False):
            for tool_key, err in errors.items():
                reason = err.get("error", err.get("reason", "Unknown error"))
                st.warning(f"**{err.get('tool', tool_key)}**: {reason}")


def _render_inline_result(result: dict, query: ProteinQuery):
    """Render a single tool result inline (delegating to tamarind_panel renderers)."""
    from components.tamarind_panel import _render_single_result
    _render_single_result(result, query)


def _extract_key_findings(
    successes: dict[str, Any], query: ProteinQuery
) -> list[str]:
    """Extract headline findings from completed tool results."""
    findings = []

    for tool_key, result in successes.items():
        raw = result.get("raw", {})
        rtype = result.get("type", "")
        tool_name = result.get("tool", tool_key)

        if rtype == "stability_change":
            ddg = raw.get("ddG", raw.get("ddg", raw.get("stability_change")))
            if ddg is not None:
                try:
                    val = float(ddg)
                    impact = "destabilizing" if val > 0 else "stabilizing"
                    findings.append(
                        f"**{tool_name}**: {query.mutation or 'Mutation'} has ddG = {val:+.2f} kcal/mol ({impact})"
                    )
                except (ValueError, TypeError):
                    pass

        elif rtype == "thermostability":
            tm = raw.get("melting_temperature", raw.get("Tm", raw.get("tm")))
            if tm is not None:
                findings.append(f"**{tool_name}**: Predicted melting temperature = {tm}")

        elif rtype == "solubility":
            score = raw.get("solubility_score", raw.get("score"))
            if score is not None:
                findings.append(f"**{tool_name}**: Solubility score = {score}")

        elif rtype == "aggregation":
            score = raw.get("score", raw.get("aggregation_score"))
            hotspots = raw.get("hotspots", raw.get("aggregation_prone_regions", []))
            if score is not None:
                findings.append(
                    f"**{tool_name}**: Aggregation score = {score}"
                    + (f", {len(hotspots)} hotspot(s)" if hotspots else "")
                )

        elif rtype == "docking":
            affinity = raw.get("binding_affinity", raw.get("affinity", raw.get("score")))
            if affinity is not None:
                findings.append(f"**{tool_name}**: Binding affinity = {affinity} kcal/mol")

        elif rtype == "binding_energy":
            dg = raw.get("binding_energy", raw.get("dG", raw.get("free_energy")))
            kd = raw.get("Kd", raw.get("kd"))
            parts = []
            if dg is not None:
                parts.append(f"dG = {dg} kcal/mol")
            if kd is not None:
                parts.append(f"Kd = {kd}")
            if parts:
                findings.append(f"**{tool_name}**: {', '.join(parts)}")

        elif rtype == "surface":
            patches = raw.get("interaction_patches", raw.get("patches", []))
            druggable = raw.get("druggable_sites", [])
            if patches or druggable:
                findings.append(
                    f"**{tool_name}**: {len(patches)} interaction patches"
                    + (f", {len(druggable)} druggable sites" if druggable else "")
                )

        elif rtype == "binder_design":
            designs = raw.get("designs", raw.get("binders", []))
            if designs:
                findings.append(
                    f"**{tool_name}**: {len(designs)} binder designs generated "
                    "(60-70% expected hit rate)"
                )

        elif rtype == "drug_design":
            molecules = raw.get("molecules", raw.get("generated", []))
            if molecules:
                findings.append(
                    f"**{tool_name}**: {len(molecules)} novel molecules designed"
                )

        elif rtype == "structure_comparison":
            esm_pdb = raw.get("pdb", raw.get("structure", ""))
            if esm_pdb:
                findings.append(
                    f"**{tool_name}**: ESMFold structure available for cross-validation"
                )

        elif rtype == "stability_scan":
            mutations = raw.get("mutations", raw.get("stabilizing_mutations", []))
            if mutations:
                findings.append(
                    f"**{tool_name}**: {len(mutations)} mutations scored for stability"
                )

        elif rtype == "sequence_design":
            sequences = raw.get("sequences", raw.get("designed_sequences", []))
            if sequences:
                findings.append(
                    f"**{tool_name}**: {len(sequences)} sequences designed via inverse folding"
                )

    return findings


# ────────────────────────────────────────────────────────
# Results integration — flow outputs back into Luminous state
# ────────────────────────────────────────────────────────


def _integrate_result_into_state(
    tool_key: str, result: dict[str, Any], query: ProteinQuery
):
    """Wire Tamarind tool outputs back into relevant session state for display
    in the structure viewer, trust audit, and other panels."""
    rtype = result.get("type", "")
    raw = result.get("raw", {})

    if rtype == "error" or rtype == "skipped":
        return

    # ESMFold → store alternate PDB for comparison
    if tool_key == "esmfold":
        esm_pdb = raw.get("pdb", raw.get("structure", ""))
        if esm_pdb:
            st.session_state["esmfold_pdb"] = esm_pdb

    # ProteinMPNN-ddG → store ddG value
    elif tool_key == "proteinmpnn-ddg":
        ddg = raw.get("ddG", raw.get("ddg", raw.get("stability_change")))
        if ddg is not None:
            st.session_state["tamarind_ddg"] = {
                "mutation": query.mutation,
                "ddg": ddg,
                "tool": "ProteinMPNN-ddG",
            }

    # Docking results → store docked complex for 3D viewer
    elif tool_key in ("autodock-vina", "gnina"):
        docked_pdb = raw.get("docked_pdb", raw.get("complex", ""))
        if docked_pdb:
            st.session_state["docked_complex_pdb"] = docked_pdb
            st.session_state["docking_tool"] = result.get("tool", tool_key)
        affinity = raw.get("binding_affinity", raw.get("affinity", raw.get("score")))
        if affinity is not None:
            st.session_state["docking_affinity"] = affinity

    # MaSIF → store druggable sites for annotation
    elif tool_key == "masif":
        druggable = raw.get("druggable_sites", [])
        patches = raw.get("interaction_patches", raw.get("patches", []))
        if druggable or patches:
            st.session_state["masif_surfaces"] = {
                "druggable_sites": druggable,
                "patches": patches,
            }

    # PRODIGY → store binding energy
    elif tool_key == "prodigy":
        dg = raw.get("binding_energy", raw.get("dG", raw.get("free_energy")))
        kd = raw.get("Kd", raw.get("kd", raw.get("dissociation_constant")))
        if dg is not None or kd is not None:
            st.session_state["prodigy_binding"] = {"dG": dg, "Kd": kd}

    # Thermostability → store Tm
    elif tool_key == "temstapro":
        tm = raw.get("melting_temperature", raw.get("Tm", raw.get("tm")))
        if tm is not None:
            st.session_state["predicted_tm"] = tm

    # CamSol → store solubility regions
    elif tool_key == "camsol":
        regions = raw.get("low_solubility_regions", raw.get("aggregation_hotspots", []))
        score = raw.get("solubility_score", raw.get("score"))
        if score is not None:
            st.session_state["solubility_score"] = score
        if regions:
            st.session_state["solubility_hotspots"] = regions

    # Aggrescan3D → store aggregation hotspots
    elif tool_key == "aggrescan3d":
        hotspots = raw.get("hotspots", raw.get("aggregation_prone_regions", []))
        score = raw.get("score", raw.get("aggregation_score"))
        if hotspots:
            st.session_state["aggregation_hotspots"] = hotspots
        if score is not None:
            st.session_state["aggregation_score"] = score

    # BoltzGen → store binder designs
    elif tool_key == "boltzgen":
        designs = raw.get("designs", raw.get("binders", []))
        if designs:
            st.session_state["binder_designs"] = designs

    # ThermoMPNN → store mutation scan
    elif tool_key == "thermompnn":
        mutations = raw.get("mutations", raw.get("stabilizing_mutations", []))
        if mutations:
            st.session_state["stability_scan_mutations"] = mutations


# ────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────


def _get_drug_smiles_from_context() -> list[str] | None:
    """Try to extract drug SMILES from session state or bio context."""
    # Check if user provided SMILES via the tamarind panel
    smiles_input = st.session_state.get("tam_drug_smiles", "")
    if smiles_input and smiles_input.strip():
        return [smiles_input.strip()]

    # Try to get from bio context
    bio_ctx = st.session_state.get("bio_context")
    if bio_ctx and bio_ctx.drugs:
        # We don't have SMILES directly in DrugCandidate model,
        # but return None to let the tool handle it
        pass

    return None
