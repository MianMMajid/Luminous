"""Tamarind Bio Multi-Tool Analysis Panel.

Displays available Tamarind tools for the current query type,
lets the user select which to run, and shows results inline.
"""
from __future__ import annotations

import streamlit as st

from src.models import PredictionResult, ProteinQuery
from src.utils import run_async

# Emoji tags for tool display (hyphenated keys match Tamarind API slugs)
_TOOL_EMOJI = {
    "esmfold": "zap",
    "aggrescan3d": "clump",
    "temstapro": "temp",
    "camsol": "drop",
    "proteinmpnn-ddg": "ddG",
    "thermompnn": "scan",
    "autodock-vina": "dock",
    "gnina": "AI-dock",
    "masif": "surface",
    "reinvent": "design",
    "prodigy": "bind",
    "boltzgen": "binder",
    "proteinmpnn": "MPNN",
    "diffdock": "diff",
    "dockq": "score",
    "rfdiffusion": "RFdiff",
    "rfantibody": "Ab",
    "biophi": "human",
}


def render_tamarind_panel(
    query: ProteinQuery,
    prediction: PredictionResult,
):
    """Render the Tamarind Bio multi-tool analysis panel."""
    from src.tamarind_analyses import get_available_analyses, is_available

    if not is_available():
        st.info(
            "Tamarind Bio API key required. "
            "Add `TAMARIND_API_KEY=your_key` to your `.env` file in the project root. "
            "Get a free key at [tamarind.bio](https://tamarind.bio).",
            icon="🔑",
        )
        return

    st.markdown("### Tamarind Bio Computational Suite")
    st.caption(
        f"Tools recommended for **{query.question_type.replace('_', ' ')}** analysis. "
        "Select tools to run and click Analyze. All tools run concurrently via Tamarind's cloud."
    )

    analyses = get_available_analyses(query.question_type)
    cache_key = f"tamarind_results_{query.protein_name}_{query.question_type}"
    cached_results = st.session_state.get(cache_key)

    if cached_results:
        _render_results(cached_results, query)
        if st.button("Re-run Analysis", key="tam_rerun"):
            st.session_state.pop(cache_key, None)
            st.rerun()
        return

    # Tool selector
    st.markdown("**Available tools for this query:**")

    selected = []
    cols = st.columns(2)
    for i, (tool_key, display_name, description) in enumerate(analyses):
        col = cols[i % 2]
        tag = _TOOL_EMOJI.get(tool_key, "tool")
        checked = col.checkbox(
            f"`{tag}` **{display_name}**",
            value=True,
            key=f"tam_sel_{tool_key}",
            help=description,
        )
        if checked:
            selected.append(tool_key)

    # Drug SMILES input for docking tools
    drug_smiles = None
    if any(t in selected for t in ("autodock-vina", "gnina", "diffdock", "reinvent")):
        st.markdown("---")
        smiles_input = st.text_input(
            "Drug SMILES for docking (leave empty for auto-detection from bio context)",
            placeholder="CC(=O)Oc1ccccc1C(=O)O",
            key="tam_drug_smiles",
        )
        if smiles_input.strip():
            drug_smiles = [smiles_input.strip()]
        else:
            # Try to extract SMILES from bio context drugs
            bio_ctx = st.session_state.get("bio_context")
            if bio_ctx and bio_ctx.drugs:
                st.caption(
                    f"Known drugs: {', '.join(d.name for d in bio_ctx.drugs[:3])}. "
                    "Enter a SMILES string to dock a specific molecule."
                )

    # Run button
    if st.button(
        f"Run {len(selected)} Tamarind Tool{'s' if len(selected) != 1 else ''}",
        type="primary",
        disabled=not selected,
        key="tam_run",
    ):
        _execute_analyses(query, prediction, selected, drug_smiles, cache_key)
        st.rerun()


def _execute_analyses(
    query: ProteinQuery,
    prediction: PredictionResult,
    selected: list[str],
    drug_smiles: list[str] | None,
    cache_key: str,
):
    """Run selected analyses with progress display."""
    from src.tamarind_analyses import run_analyses

    with st.status(
        f"Running {len(selected)} Tamarind tools concurrently...", expanded=True
    ) as status:
        for tool in selected:
            st.write(f"Submitting **{tool}**...")

        async def _run():
            return await run_analyses(
                query, prediction.pdb_content, selected, drug_smiles
            )

        results = run_async(_run())
        st.session_state[cache_key] = results
        n_ok = sum(1 for r in results if r.get("type") != "error")
        n_err = len(results) - n_ok
        label = f"Complete: {n_ok} succeeded"
        if n_err:
            label += f", {n_err} failed"
        status.update(label=label, state="complete")


def _render_results(results: list[dict], query: ProteinQuery):
    """Render analysis results in expandable cards."""
    # Split successes and errors
    successes = [r for r in results if r.get("type") not in ("error", "skipped")]
    errors = [r for r in results if r.get("type") in ("error", "skipped")]

    for result in successes:
        tool = result.get("tool", "Unknown")
        rtype = result.get("type", "")

        with st.expander(f"**{tool}** — {rtype.replace('_', ' ').title()}"):
            _render_single_result(result, query)

    if errors:
        with st.expander(f"Errors ({len(errors)})", expanded=False):
            for err in errors:
                reason = err.get("error", err.get("reason", "Unknown"))
                st.warning(f"**{err.get('tool', '?')}**: {reason}")


def _render_single_result(result: dict, query: ProteinQuery):
    """Render a single tool result based on its type."""
    rtype = result.get("type", "")
    raw = result.get("raw", {})
    tool = result.get("tool", "")

    if rtype == "structure_comparison":
        _render_structure_comparison(raw, query)
    elif rtype == "aggregation":
        _render_aggregation(raw)
    elif rtype == "thermostability":
        _render_thermostability(raw)
    elif rtype == "solubility":
        _render_solubility(raw)
    elif rtype == "stability_change":
        _render_stability_change(raw, query)
    elif rtype == "stability_scan":
        _render_stability_scan(raw)
    elif rtype == "docking":
        _render_docking(raw, tool)
    elif rtype == "surface":
        _render_surface(raw)
    elif rtype == "drug_design":
        _render_drug_design(raw)
    elif rtype == "binding_energy":
        _render_binding_energy(raw)
    elif rtype == "binder_design":
        _render_binder_design(raw)
    elif rtype == "sequence_design":
        _render_sequence_design(raw)
    else:
        # Generic JSON display for unknown types
        st.json(raw)

    # Always show provenance
    st.caption(f"Computed via Tamarind Bio | Tool: {tool}")


# ────────────────────────────────────────────────────────
# Type-specific renderers
# ────────────────────────────────────────────────────────


def _render_structure_comparison(raw: dict, query: ProteinQuery):
    """ESMFold vs Boltz-2 comparison."""
    esm_pdb = raw.get("pdb", raw.get("structure", ""))
    if esm_pdb:
        st.markdown(
            f"ESMFold predicted structure for **{query.protein_name}** "
            "(single-sequence, no MSA — 60x faster than AlphaFold2)."
        )
        st.markdown(
            "Compare ESMFold's confidence with Boltz-2 to cross-validate "
            "uncertain regions. Agreement = higher trust."
        )
        st.download_button(
            "Download ESMFold PDB",
            esm_pdb,
            file_name=f"{query.protein_name}_esmfold.pdb",
            mime="chemical/x-pdb",
        )
    _show_scores(raw)


def _render_aggregation(raw: dict):
    """Aggrescan3D aggregation propensity."""
    score = raw.get("score", raw.get("aggregation_score"))
    if score is not None:
        col1, col2 = st.columns(2)
        col1.metric("Aggregation Score", f"{score:.2f}" if isinstance(score, float) else str(score))
        risk = "High" if (isinstance(score, (int, float)) and score > 0) else "Low"
        col2.metric("Aggregation Risk", risk)
    hotspots = raw.get("hotspots", raw.get("aggregation_prone_regions", []))
    if hotspots:
        st.markdown(f"**Aggregation-prone regions:** {len(hotspots)} identified")
        for h in hotspots[:5]:
            if isinstance(h, dict):
                st.markdown(f"- Residues {h.get('start', '?')}-{h.get('end', '?')}: score {h.get('score', '?')}")
            else:
                st.markdown(f"- {h}")
    _show_scores(raw)


def _render_thermostability(raw: dict):
    """TemStaPro thermostability prediction."""
    tm = raw.get("melting_temperature", raw.get("Tm", raw.get("tm")))
    label = raw.get("label", raw.get("stability_class"))
    col1, col2 = st.columns(2)
    if tm is not None:
        col1.metric("Predicted Tm", f"{tm:.1f} C" if isinstance(tm, float) else str(tm))
    if label:
        col2.metric("Stability Class", str(label))
    _show_scores(raw)


def _render_solubility(raw: dict):
    """CamSol solubility scoring."""
    score = raw.get("solubility_score", raw.get("score"))
    if score is not None:
        st.metric("Solubility Score", f"{score:.2f}" if isinstance(score, float) else str(score))
    regions = raw.get("low_solubility_regions", raw.get("aggregation_hotspots", []))
    if regions:
        st.markdown(f"**Low-solubility regions:** {len(regions)}")
        for r in regions[:5]:
            if isinstance(r, dict):
                st.markdown(f"- Residues {r.get('start', '?')}-{r.get('end', '?')}")
            else:
                st.markdown(f"- {r}")
    _show_scores(raw)


def _render_stability_change(raw: dict, query: ProteinQuery):
    """ProteinMPNN-ddG mutation stability impact."""
    ddg = raw.get("ddG", raw.get("ddg", raw.get("stability_change")))
    if ddg is not None:
        try:
            val = float(ddg)
        except (ValueError, TypeError):
            val = 0
        st.metric(
            f"ddG for {query.mutation or 'mutation'}",
            f"{val:+.2f} kcal/mol",
            delta="Destabilizing" if val > 0 else "Stabilizing",
            delta_color="inverse",
        )
        if val > 2.0:
            st.error("Strongly destabilizing mutation (ddG > 2 kcal/mol)")
        elif val > 0.5:
            st.warning("Moderately destabilizing mutation")
        elif val < -0.5:
            st.success("Stabilizing mutation")
    _show_scores(raw)


def _render_stability_scan(raw: dict):
    """ThermoMPNN full stability scan."""
    mutations = raw.get("mutations", raw.get("stabilizing_mutations", []))
    if mutations:
        st.markdown(f"**Top stabilizing mutations** ({len(mutations)} analyzed):")
        # Show top 10
        top = sorted(mutations, key=lambda m: m.get("ddG", m.get("score", 0)))[:10]
        for m in top:
            pos = m.get("position", m.get("residue", "?"))
            mut = m.get("mutation", m.get("name", "?"))
            score = m.get("ddG", m.get("score", "?"))
            st.markdown(f"- **{mut}** (pos {pos}): ddG = {score}")
    _show_scores(raw)


def _render_docking(raw: dict, tool: str):
    """AutoDock Vina / GNINA docking results."""
    affinity = raw.get("binding_affinity", raw.get("affinity", raw.get("score")))
    if affinity is not None:
        st.metric(
            f"Binding Affinity ({tool})",
            f"{affinity:.2f} kcal/mol" if isinstance(affinity, (int, float)) else str(affinity),
        )
    poses = raw.get("poses", raw.get("docking_poses", []))
    if poses:
        st.markdown(f"**{len(poses)} docking poses generated**")
        for i, pose in enumerate(poses[:3]):
            score = pose.get("score", pose.get("affinity", "?"))
            st.markdown(f"- Pose {i + 1}: {score} kcal/mol")
    # Download docked complex
    docked_pdb = raw.get("docked_pdb", raw.get("complex", ""))
    if docked_pdb:
        st.download_button(
            "Download Docked Complex",
            docked_pdb,
            file_name=f"docked_{tool.lower()}.pdb",
            mime="chemical/x-pdb",
        )
    _show_scores(raw)


def _render_surface(raw: dict):
    """MaSIF surface fingerprinting."""
    patches = raw.get("interaction_patches", raw.get("patches", []))
    if patches:
        st.markdown(f"**{len(patches)} interaction-competent surface patches found**")
        for p in patches[:5]:
            if isinstance(p, dict):
                st.markdown(
                    f"- Patch at residues {p.get('residues', '?')}: "
                    f"score {p.get('score', '?')}"
                )
    druggable = raw.get("druggable_sites", [])
    if druggable:
        st.success(f"{len(druggable)} potentially druggable surface sites identified")
    _show_scores(raw)


def _render_drug_design(raw: dict):
    """REINVENT 4 de novo small molecule design."""
    molecules = raw.get("molecules", raw.get("generated", []))
    if molecules:
        st.markdown(f"**{len(molecules)} novel molecules designed**")
        for i, mol in enumerate(molecules[:5]):
            smiles = mol.get("smiles", mol.get("SMILES", "?"))
            score = mol.get("score", mol.get("docking_score", "?"))
            st.code(smiles, language=None)
            if score != "?":
                st.caption(f"Score: {score}")
    _show_scores(raw)


def _render_binding_energy(raw: dict):
    """PRODIGY binding free energy prediction."""
    dg = raw.get("binding_energy", raw.get("dG", raw.get("free_energy")))
    kd = raw.get("Kd", raw.get("kd", raw.get("dissociation_constant")))
    col1, col2 = st.columns(2)
    if dg is not None:
        col1.metric("Binding Energy (dG)", f"{dg:.2f} kcal/mol" if isinstance(dg, float) else str(dg))
    if kd is not None:
        col2.metric("Dissociation Constant (Kd)", f"{kd:.2e} M" if isinstance(kd, float) else str(kd))
    contacts = raw.get("intermolecular_contacts", raw.get("contacts"))
    if contacts is not None:
        st.metric("Intermolecular Contacts", str(contacts))
    _show_scores(raw)


def _render_binder_design(raw: dict):
    """BoltzGen de novo binder design."""
    designs = raw.get("designs", raw.get("binders", []))
    if designs:
        st.markdown(f"**{len(designs)} binder designs generated** (BoltzGen: 60-70% experimental hit rate)")
        for i, d in enumerate(designs[:5]):
            seq = d.get("sequence", "")
            score = d.get("confidence", d.get("score", "?"))
            with st.expander(f"Design {i + 1} (score: {score})", expanded=i == 0):
                if seq:
                    st.code(seq[:100] + ("..." if len(seq) > 100 else ""), language=None)
    _show_scores(raw)


def _render_sequence_design(raw: dict):
    """ProteinMPNN inverse folding results."""
    sequences = raw.get("sequences", raw.get("designed_sequences", []))
    if sequences:
        st.markdown(f"**{len(sequences)} sequences designed** via inverse folding")
        for i, s in enumerate(sequences[:4]):
            seq = s.get("sequence", s) if isinstance(s, dict) else str(s)
            score = s.get("score", "") if isinstance(s, dict) else ""
            label = f"Seq {i + 1}" + (f" (score: {score})" if score else "")
            with st.expander(label, expanded=i == 0):
                st.code(seq[:120] + ("..." if len(str(seq)) > 120 else ""), language=None)
    _show_scores(raw)


def _show_scores(raw: dict):
    """Show any additional score fields from raw results."""
    score_keys = {"confidence", "plddt", "ptm", "iptm", "rmsd", "tm_score"}
    shown = []
    for k, v in raw.items():
        if k.lower() in score_keys and v is not None:
            shown.append((k, v))
    if shown:
        cols = st.columns(len(shown))
        for col, (k, v) in zip(cols, shown):
            formatted = f"{v:.3f}" if isinstance(v, float) else str(v)
            col.metric(k.upper(), formatted)
