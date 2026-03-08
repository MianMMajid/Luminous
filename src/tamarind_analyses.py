"""Orchestrate multi-tool Tamarind Bio analyses per question type.

Instead of just running Boltz-2, this module dispatches the right combination
of Tamarind's 200+ tools based on the user's question type:

  - structure:       Boltz-2 + ESMFold comparison + Aggrescan3D + TemStaPro
  - mutation_impact: Boltz-2 + ProteinMPNN-ddG + ThermoMPNN + CamSol
  - druggability:    Boltz-2 + AutoDock Vina/GNINA/DiffDock + REINVENT + MaSIF
  - binding:         Boltz-2 + PRODIGY + BoltzGen + DockQ + RFdiffusion
  - antibody:        RFantibody + BioPhi + ProteinMPNN + ImmuneBuilder
  - dynamics:        ESMFold + TemStaPro + CamSol + AlphaFlow

Each analysis runs asynchronously and results are stored in session state
under "tamarind_analyses" for display by the UI component.
"""
from __future__ import annotations

import asyncio
from typing import Any

from src.config import TAMARIND_API_KEY
from src.models import ProteinQuery


def is_available() -> bool:
    return bool(TAMARIND_API_KEY)


# ────────────────────────────────────────────────────────
# Question-type dispatchers
# ────────────────────────────────────────────────────────

# Maps question_type → list of (analysis_name, runner_func, description)
ANALYSIS_REGISTRY: dict[str, list[tuple[str, str, str]]] = {
    "structure": [
        ("esmfold", "ESMFold Comparison", "Fast single-sequence structure for cross-validation"),
        ("aggrescan3d", "Aggregation Propensity", "Predict aggregation-prone regions (Aggrescan3D)"),
        ("temstapro", "Thermostability", "Predict thermal stability (TemStaPro)"),
        ("camsol", "Solubility Profile", "Solubility scoring + aggregation hotspots (CamSol)"),
    ],
    "mutation_impact": [
        ("proteinmpnn-ddg", "Stability Change (ddG)", "Predict mutation impact on stability (ProteinMPNN-ddG)"),
        ("thermompnn", "Thermostability Scan", "Score all possible mutations for stability (ThermoMPNN)"),
        ("camsol", "Solubility Impact", "Check if mutation affects solubility (CamSol)"),
        ("aggrescan3d", "Aggregation Risk", "Check if mutation creates aggregation hotspot (Aggrescan3D)"),
    ],
    "druggability": [
        ("autodock-vina", "Molecular Docking (Vina)", "Dock known drugs to predicted structure"),
        ("gnina", "AI Docking (GNINA)", "CNN-enhanced docking for better accuracy"),
        ("diffdock", "Generative Docking (DiffDock)", "Diffusion-based docking — better for flexible ligands"),
        ("masif", "Surface Fingerprint", "Identify druggable surface patches (MaSIF)"),
        ("peppatch", "Electrostatic Patches", "Map electrostatic surface patches for binding sites"),
        ("reinvent", "De Novo Drug Design", "Generate novel small molecules targeting this protein"),
    ],
    "binding": [
        ("prodigy", "Binding Energy (PRODIGY)", "Predict binding free energy and Kd"),
        ("dockq", "Docking Quality (DockQ)", "Evaluate docking model quality against reference"),
        ("boltzgen", "De Novo Binder Design", "Design protein binders with 60-70% hit rate (BoltzGen)"),
        ("bindcraft", "Peptide Binder Design", "Design peptide/miniprotein binders (BindCraft)"),
        ("rfdiffusion", "Backbone Design (RFdiffusion)", "De novo backbone design for binder scaffolds"),
        ("masif", "Interface Fingerprint", "Characterize binding surface (MaSIF)"),
        ("proteinmpnn", "Interface Redesign", "Redesign binding interface (ProteinMPNN)"),
    ],
    "antibody": [
        ("rfantibody", "CDR Design (RFantibody)", "De novo antibody CDR design targeting antigen"),
        ("biophi", "Humanization (BioPhi)", "Antibody humanization + humanness scoring (Sapiens/OASis)"),
        ("immunebuilder", "Ab Structure (ImmuneBuilder)", "Predict antibody structure (ABodyBuilder2)"),
        ("proteinmpnn", "Sequence Optimization", "Optimize antibody sequence via inverse folding"),
        ("prodigy", "Binding Affinity", "Predict antibody-antigen binding energy"),
    ],
    "dynamics": [
        ("esmfold", "Cross-Validate (ESMFold)", "Fast single-sequence structure for cross-validation"),
        ("alphaflow", "Conformational Ensemble", "Generate conformational ensemble (AlphaFlow)"),
        ("temstapro", "Thermostability", "Predict thermal stability (TemStaPro)"),
        ("camsol", "Solubility Profile", "Solubility scoring + aggregation hotspots (CamSol)"),
        ("aggrescan3d", "Aggregation Propensity", "Predict aggregation-prone regions (Aggrescan3D)"),
    ],
}

# Tools applicable to ALL question types
UNIVERSAL_ANALYSES = [
    ("temstapro", "Thermostability", "Predict thermal stability (TemStaPro)"),
]


def get_available_analyses(question_type: str) -> list[tuple[str, str, str]]:
    """Return (tool_key, display_name, description) for the given question type."""
    analyses = ANALYSIS_REGISTRY.get(question_type, ANALYSIS_REGISTRY["structure"])
    # Deduplicate while preserving order
    seen = set()
    result = []
    for item in analyses:
        if item[0] not in seen:
            seen.add(item[0])
            result.append(item)
    for item in UNIVERSAL_ANALYSES:
        if item[0] not in seen:
            seen.add(item[0])
            result.append(item)
    return result


# ────────────────────────────────────────────────────────
# Individual analysis runners
# ────────────────────────────────────────────────────────


async def _run_single_analysis(
    tool_key: str,
    query: ProteinQuery,
    pdb_content: str,
    drug_smiles: list[str] | None = None,
) -> dict[str, Any]:
    """Run a single Tamarind tool and return structured results."""
    from src.tamarind_client import (
        run_aggrescan3d,
        run_alphaflow,
        run_autodock_vina,
        run_bindcraft,
        run_biophi,
        run_boltzgen,
        run_camsol,
        run_diffdock,
        run_dockq,
        run_esmfold,
        run_gnina,
        run_immunebuilder,
        run_masif,
        run_peppatch,
        run_prodigy,
        run_proteinmpnn,
        run_proteinmpnn_ddg,
        run_reinvent,
        run_rfantibody,
        run_rfdiffusion,
        run_temstapro,
        run_thermompnn,
    )

    prefix = f"lum_{query.protein_name}_{tool_key}"

    if tool_key == "esmfold" and query.sequence:
        raw = await run_esmfold(query.sequence, f"{prefix}_esm")
        return {"tool": "ESMFold", "type": "structure_comparison", "raw": raw}

    elif tool_key == "aggrescan3d":
        raw = await run_aggrescan3d(pdb_content, f"{prefix}_agg")
        return {"tool": "Aggrescan3D", "type": "aggregation", "raw": raw}

    elif tool_key == "temstapro" and query.sequence:
        raw = await run_temstapro(query.sequence, f"{prefix}_therm")
        return {"tool": "TemStaPro", "type": "thermostability", "raw": raw}

    elif tool_key == "camsol" and query.sequence:
        raw = await run_camsol(query.sequence, f"{prefix}_sol", pdb_content=pdb_content)
        return {"tool": "CamSol", "type": "solubility", "raw": raw}

    elif tool_key == "proteinmpnn-ddg" and query.mutation:
        raw = await run_proteinmpnn_ddg(pdb_content, [query.mutation], f"{prefix}_ddg")
        return {"tool": "ProteinMPNN-ddG", "type": "stability_change", "raw": raw}

    elif tool_key == "thermompnn":
        raw = await run_thermompnn(pdb_content, f"{prefix}_thmpnn")
        return {"tool": "ThermoMPNN", "type": "stability_scan", "raw": raw}

    elif tool_key == "autodock-vina" and drug_smiles:
        raw = await run_autodock_vina(pdb_content, drug_smiles[0], f"{prefix}_vina")
        return {"tool": "AutoDock Vina", "type": "docking", "raw": raw}

    elif tool_key == "gnina" and drug_smiles:
        raw = await run_gnina(pdb_content, drug_smiles[0], f"{prefix}_gnina")
        return {"tool": "GNINA", "type": "docking", "raw": raw}

    elif tool_key == "masif":
        raw = await run_masif(pdb_content, f"{prefix}_masif")
        return {"tool": "MaSIF", "type": "surface", "raw": raw}

    elif tool_key == "reinvent":
        raw = await run_reinvent(pdb_content, f"{prefix}_reinv", num_molecules=20)
        return {"tool": "REINVENT 4", "type": "drug_design", "raw": raw}

    elif tool_key == "prodigy":
        raw = await run_prodigy(pdb_content, f"{prefix}_prod")
        return {"tool": "PRODIGY", "type": "binding_energy", "raw": raw}

    elif tool_key == "boltzgen":
        raw = await run_boltzgen(pdb_content, f"{prefix}_bgen", num_designs=5)
        return {"tool": "BoltzGen", "type": "binder_design", "raw": raw}

    elif tool_key == "proteinmpnn":
        raw = await run_proteinmpnn(pdb_content, f"{prefix}_mpnn", num_sequences=4)
        return {"tool": "ProteinMPNN", "type": "sequence_design", "raw": raw}

    elif tool_key == "diffdock" and drug_smiles:
        raw = await run_diffdock(pdb_content, drug_smiles[0], f"{prefix}_ddock")
        return {"tool": "DiffDock", "type": "docking", "raw": raw}

    elif tool_key == "dockq":
        # DockQ needs a native reference — use pdb_content as both model & native
        # (caller should provide native via kwargs in the future)
        raw = await run_dockq(pdb_content, pdb_content, f"{prefix}_dockq")
        return {"tool": "DockQ", "type": "docking_quality", "raw": raw}

    elif tool_key == "rfdiffusion":
        raw = await run_rfdiffusion(pdb_content, f"{prefix}_rfdiff", num_designs=4)
        return {"tool": "RFdiffusion", "type": "backbone_design", "raw": raw}

    elif tool_key == "rfantibody":
        raw = await run_rfantibody(pdb_content, f"{prefix}_rfab")
        return {"tool": "RFantibody", "type": "antibody_design", "raw": raw}

    elif tool_key == "biophi" and query.sequence:
        raw = await run_biophi(query.sequence, f"{prefix}_bphi")
        return {"tool": "BioPhi", "type": "humanization", "raw": raw}

    elif tool_key == "immunebuilder" and query.sequence:
        # ImmuneBuilder expects heavy/light chains; use full sequence as heavy
        raw = await run_immunebuilder(query.sequence, f"{prefix}_immb")
        return {"tool": "ImmuneBuilder", "type": "antibody_structure", "raw": raw}

    elif tool_key == "alphaflow" and query.sequence:
        raw = await run_alphaflow(query.sequence, f"{prefix}_aflow")
        return {"tool": "AlphaFlow", "type": "conformational_ensemble", "raw": raw}

    elif tool_key == "bindcraft" and pdb_content:
        raw = await run_bindcraft(pdb_content, f"{prefix}_bcraft")
        return {"tool": "BindCraft", "type": "binder_design", "raw": raw}

    elif tool_key == "peppatch":
        raw = await run_peppatch(pdb_content, f"{prefix}_ppatch")
        return {"tool": "PepPatch", "type": "electrostatic_surface", "raw": raw}

    return {"tool": tool_key, "type": "skipped", "reason": "Missing required input"}


# ────────────────────────────────────────────────────────
# Main orchestrator
# ────────────────────────────────────────────────────────


async def run_analyses(
    query: ProteinQuery,
    pdb_content: str,
    selected_tools: list[str],
    drug_smiles: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Run selected Tamarind analyses concurrently. Returns list of result dicts."""
    tasks = []
    for tool_key in selected_tools:
        tasks.append(
            _run_safe(tool_key, query, pdb_content, drug_smiles)
        )
    return await asyncio.gather(*tasks)


async def _run_safe(
    tool_key: str,
    query: ProteinQuery,
    pdb_content: str,
    drug_smiles: list[str] | None,
) -> dict[str, Any]:
    """Run a single analysis with error handling."""
    try:
        return await _run_single_analysis(tool_key, query, pdb_content, drug_smiles)
    except Exception as e:
        return {
            "tool": tool_key,
            "type": "error",
            "error": str(e),
        }
