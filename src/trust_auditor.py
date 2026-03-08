from __future__ import annotations

import json
from pathlib import Path

from src.models import ProteinQuery, RegionConfidence, TrustAudit
from src.utils import (
    compute_region_confidence,
    overall_confidence_level,
    parse_pdb_plddt,
)

LIMITATIONS_PATH = Path("data/known_limitations.json")


def _load_limitations() -> dict:
    if LIMITATIONS_PATH.exists():
        return json.loads(LIMITATIONS_PATH.read_text())
    return {}


def build_trust_audit(
    query: ProteinQuery,
    pdb_content: str,
    confidence_json: dict,
    chain_ids: list[str] | None = None,
    residue_ids: list[int] | None = None,
    plddt_scores: list[float] | None = None,
    is_experimental: bool = False,
) -> TrustAudit:
    """Build a comprehensive trust audit from Boltz-2 outputs."""
    limitations_db = _load_limitations()
    boltz_limits = limitations_db.get("boltz2", {})

    # Use provided pLDDT scores or extract from PDB B-factor column
    # NEVER reparse B-factors for experimental structures (RCSB) — they are
    # crystallographic B-factors, not pLDDT confidence scores.
    if chain_ids is None or residue_ids is None or plddt_scores is None:
        if is_experimental:
            # For experimental structures, parse only chain/residue IDs,
            # set pLDDT to empty (no confidence info available)
            chain_ids, residue_ids, _ = parse_pdb_plddt(pdb_content)
            plddt_scores = []
        else:
            chain_ids, residue_ids, plddt_scores = parse_pdb_plddt(pdb_content)

    # Compute overall confidence
    if is_experimental or not plddt_scores:
        # Experimental structures: no pLDDT available, use confidence_json or N/A
        confidence_score = confidence_json.get("confidence_score", 0.0)
    else:
        confidence_score = confidence_json.get(
            "confidence_score",
            sum(plddt_scores) / max(len(plddt_scores), 1) / 100.0,
        )
    ptm = confidence_json.get("ptm")
    iptm = confidence_json.get("iptm")
    complex_plddt = confidence_json.get("complex_plddt")

    # Compute region-level confidence
    raw_regions = compute_region_confidence(chain_ids, residue_ids, plddt_scores)
    regions = [RegionConfidence(**r) for r in raw_regions]

    # Collect known limitations
    known_limitations = []
    if is_experimental:
        known_limitations.append(
            "This is an experimental structure (RCSB PDB) — confidence metrics "
            "are not available. B-factors reflect crystallographic disorder, not "
            "model confidence."
        )
    for lim in boltz_limits.get("general", []):
        if isinstance(lim, dict) and "description" in lim:
            known_limitations.append(lim["description"])

    # Add mutation-specific limitations
    mutation_limits = limitations_db.get("mutation_specific", {})
    if query.mutation:
        known_limitations.append(mutation_limits.get(
            "gain_of_function",
            "Gain-of-function mutations may not show detectable structural changes",
        ))

    if query.interaction_partner:
        general_limits = boltz_limits.get("general", [])
        if general_limits and isinstance(general_limits[0], dict):
            known_limitations.append(
                general_limits[0].get(
                    "description",
                    "Protein-ligand binding poses have ~40% false positive rate",
                )
            )
        else:
            known_limitations.append(
                "Protein-ligand binding poses have ~40% false positive rate"
            )

    # Training data bias note
    training_bias = boltz_limits.get("training_bias", {})
    training_note = training_bias.get("description", "")
    well_studied = training_bias.get("well_studied_proteins", [])
    if query.protein_name.upper() in [p.upper() for p in well_studied]:
        training_note += (
            f" {query.protein_name} is well-studied with many PDB structures, "
            "so predictions may be more reliable but could overfit to known conformations."
        )

    # Suggested validations
    suggested = _suggest_validation(query, confidence_score, regions)

    return TrustAudit(
        overall_confidence=overall_confidence_level(confidence_score),
        confidence_score=round(confidence_score, 4),
        ptm=ptm,
        iptm=iptm,
        complex_plddt=complex_plddt,
        regions=regions,
        known_limitations=known_limitations,
        training_data_note=training_note,
        suggested_validation=suggested,
    )


def _suggest_validation(
    query: ProteinQuery,
    confidence_score: float,
    regions: list[RegionConfidence],
) -> list[str]:
    """Generate experiment suggestions based on confidence and query type."""
    suggestions = []

    low_regions = [r for r in regions if r.flag is not None]
    if low_regions:
        suggestions.append(
            "Low-confidence regions detected. Consider experimental structure "
            "determination (X-ray crystallography or cryo-EM) for these regions."
        )

    if confidence_score < 0.7:
        suggestions.append(
            "Overall confidence is below 70%. Validate key findings with "
            "experimental methods before drawing conclusions."
        )

    if query.mutation:
        suggestions.append(
            f"Validate {query.mutation} impact with thermal shift assay (DSF) "
            "or hydrogen-deuterium exchange (HDX-MS)."
        )

    if query.question_type == "binding":
        suggestions.append(
            "Validate binding prediction with SPR (surface plasmon resonance) "
            "or ITC (isothermal titration calorimetry)."
        )

    if query.question_type == "druggability":
        suggestions.append(
            "Confirm druggable pocket with experimental fragment screening "
            "(X-ray crystallography or NMR)."
        )

    return suggestions


def get_residue_flags(
    query: ProteinQuery,
    residue_ids: list[int],
    plddt_scores: list[float],
) -> dict[int, str]:
    """Flag specific residues with warnings."""
    flags: dict[int, str] = {}

    for res_id, score in zip(residue_ids, plddt_scores):
        if score < 50:
            flags[res_id] = "Very low confidence - likely disordered"
        elif score < 70:
            flags[res_id] = "Low confidence - interpret with caution"

    # Flag mutation site
    if query.mutation:
        import re
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation)
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in {r for r in residue_ids}:
                existing = flags.get(mut_pos, "")
                flags[mut_pos] = f"MUTATION SITE ({query.mutation})" + (
                    f" | {existing}" if existing else ""
                )

    return flags
