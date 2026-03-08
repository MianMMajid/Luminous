"""AI-powered auto-investigation and smart annotations.

Orchestrates multiple analysis modules to automatically investigate
a protein and generate a comprehensive "first look" report with
actionable annotations. Runs analyses in optimal order, cross-references
results, and produces prioritized findings.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class InvestigationResult:
    """Complete auto-investigation output."""
    protein_name: str
    findings: list[dict] = field(default_factory=list)
    annotations: list[dict] = field(default_factory=list)
    risk_flags: list[dict] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    analyses_run: list[str] = field(default_factory=list)
    summary: str = ""


def auto_investigate(
    pdb_content: str,
    protein_name: str = "unknown",
    mutation: str | None = None,
    plddt_scores: list[float] | None = None,
    chain: str | None = None,
) -> InvestigationResult:
    """Run comprehensive auto-investigation on a protein structure.

    Executes analyses in optimal order and cross-references results
    to generate smart annotations and prioritized findings.
    """
    result = InvestigationResult(protein_name=protein_name)

    # Phase 1: Core structural analysis
    structure_data = _run_structure_analysis(pdb_content, mutation, result)

    # Phase 2: Surface and physicochemical properties
    surface_data = _run_surface_analysis(pdb_content, chain, result)

    # Phase 3: Binding pocket prediction
    pocket_data = _run_pocket_analysis(pdb_content, result)

    # Phase 4: PTM prediction
    ptm_data = _run_ptm_analysis(pdb_content, chain, result)

    # Phase 5: Disorder prediction
    disorder_data = _run_disorder_analysis(pdb_content, plddt_scores, chain, result)

    # Phase 6: Conservation scoring
    conservation_data = _run_conservation_analysis(pdb_content, chain, result)

    # Phase 7: Flexibility analysis
    flexibility_data = _run_flexibility_analysis(pdb_content, chain, result)

    # Phase 8: Cross-reference and annotate
    _cross_reference(
        result, structure_data, surface_data, pocket_data,
        ptm_data, disorder_data, conservation_data, flexibility_data,
        mutation, plddt_scores,
    )

    # Phase 9: Generate summary
    result.summary = _generate_summary(result)

    return result


def generate_smart_annotations(
    pdb_content: str,
    plddt_scores: list[float] | None = None,
    mutation: str | None = None,
    chain: str | None = None,
) -> list[dict]:
    """Generate per-residue smart annotations for the 3D viewer.

    Returns a list of annotation dicts with residue position, label,
    color, and tooltip information.
    """
    import re

    mutation_pos = None
    if mutation:
        m = re.match(r"[A-Za-z](\d+)[A-Za-z]", mutation)
        if m:
            mutation_pos = int(m.group(1))

    annotations: list[dict] = []

    # Run quick analyses
    try:
        from src.surface_properties import compute_surface_properties
        surface = compute_surface_properties(pdb_content, chain)

        # Annotate hydrophobic patches
        for patch in surface.get("hydrophobic_patches", []):
            mid = patch["residues"][len(patch["residues"]) // 2]
            annotations.append({
                "residue": mid,
                "label": f"Hydrophobic patch ({patch['size']} res)",
                "color": "#FF9500",
                "type": "surface_patch",
                "residues": patch["residues"],
                "priority": 2,
            })

        # Annotate charged clusters
        for patch in surface.get("positive_patches", []):
            mid = patch["residues"][len(patch["residues"]) // 2]
            annotations.append({
                "residue": mid,
                "label": f"Positive cluster ({patch['size']} res)",
                "color": "#007AFF",
                "type": "charge_cluster",
                "residues": patch["residues"],
                "priority": 3,
            })
        for patch in surface.get("negative_patches", []):
            mid = patch["residues"][len(patch["residues"]) // 2]
            annotations.append({
                "residue": mid,
                "label": f"Negative cluster ({patch['size']} res)",
                "color": "#FF3B30",
                "type": "charge_cluster",
                "residues": patch["residues"],
                "priority": 3,
            })
    except Exception:
        pass

    # Annotate binding pockets
    try:
        from src.pocket_prediction import predict_pockets
        pockets = predict_pockets(pdb_content)
        for pocket in pockets.get("pockets", [])[:3]:
            mid = pocket["residues"][len(pocket["residues"]) // 2]
            annotations.append({
                "residue": mid,
                "label": f"Pocket #{pocket['rank']} (p={pocket['probability']:.2f})",
                "color": "#32D74B",
                "type": "binding_pocket",
                "residues": pocket["residues"],
                "priority": 1,
            })
    except Exception:
        pass

    # Annotate PTM sites
    try:
        from src.ptm_analysis import predict_ptm_sites
        ptms = predict_ptm_sites(pdb_content, chain)
        for site in ptms.get("accessible_sites", [])[:10]:
            annotations.append({
                "residue": site["residue_id"],
                "label": f"{site['ptm_type']} ({site['amino_acid']}{site['residue_id']})",
                "color": "#AF52DE",
                "type": "ptm_site",
                "priority": 3,
            })
    except Exception:
        pass

    # Annotate disordered regions
    try:
        from src.disorder_prediction import predict_disorder
        disorder = predict_disorder(pdb_content, plddt_scores, chain)
        for region in disorder.get("disordered_regions", []):
            mid = region["residues"][len(region["residues"]) // 2]
            annotations.append({
                "residue": mid,
                "label": f"Disordered ({region['start']}-{region['end']})",
                "color": "#8E8E93",
                "type": "disorder",
                "residues": region["residues"],
                "priority": 2,
            })
    except Exception:
        pass

    # Annotate mutation site
    if mutation_pos:
        annotations.append({
            "residue": mutation_pos,
            "label": f"Mutation: {mutation}",
            "color": "#FF3B30",
            "type": "mutation",
            "priority": 0,
        })

    # Sort by priority (lower = more important)
    annotations.sort(key=lambda a: a.get("priority", 5))

    return annotations


# ── Analysis runners ──────────────────────────────────────────────────

def _run_structure_analysis(pdb_content: str, mutation: str | None, result: InvestigationResult) -> dict:
    """Run core structural analysis."""
    try:
        import re
        from src.structure_analysis import analyze_structure

        mutation_pos = None
        if mutation:
            m = re.match(r"[A-Za-z](\d+)[A-Za-z]", mutation)
            if m:
                mutation_pos = int(m.group(1))

        data = analyze_structure(pdb_content, mutation_pos=mutation_pos)
        result.analyses_run.append("structure_analysis")

        # Extract key findings
        n_res = len(data.get("residue_ids", []))
        n_buried = len(data.get("buried_residues", []))
        n_exposed = len(data.get("exposed_residues", []))
        sse = data.get("sse_counts", {})

        result.findings.append({
            "type": "structure",
            "title": "Structural Overview",
            "detail": f"{n_res} residues: {sse.get('a', 0)} helix, {sse.get('b', 0)} sheet, {sse.get('c', 0)} coil. "
                      f"{n_buried} buried, {n_exposed} exposed.",
            "priority": 1,
        })

        if mutation_pos and data.get("mutation_is_buried"):
            result.risk_flags.append({
                "type": "buried_mutation",
                "residue": mutation_pos,
                "severity": "high",
                "message": f"Mutation at {mutation} is buried (SASA={data.get('mutation_sasa', 0):.1f} A^2) — likely destabilizing",
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_surface_analysis(pdb_content: str, chain: str | None, result: InvestigationResult) -> dict:
    try:
        from src.surface_properties import compute_surface_properties
        data = compute_surface_properties(pdb_content, chain)
        result.analyses_run.append("surface_properties")

        summary = data.get("summary", {})
        n_patches = summary.get("n_hydrophobic_patches", 0)
        if n_patches > 0:
            result.findings.append({
                "type": "surface",
                "title": "Hydrophobic Surface Patches",
                "detail": f"{n_patches} hydrophobic patch(es) found on surface — potential binding/interaction sites",
                "priority": 2,
            })

        net_charge = summary.get("surface_net_charge", 0)
        if abs(net_charge) > 5:
            charge_type = "positive" if net_charge > 0 else "negative"
            result.findings.append({
                "type": "surface",
                "title": "Surface Charge Bias",
                "detail": f"Strong {charge_type} surface charge ({net_charge:+.1f}) — may affect binding specificity",
                "priority": 3,
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_pocket_analysis(pdb_content: str, result: InvestigationResult) -> dict:
    try:
        from src.pocket_prediction import predict_pockets
        data = predict_pockets(pdb_content)
        result.analyses_run.append("pocket_prediction")

        pockets = data.get("pockets", [])
        if pockets:
            top = pockets[0]
            result.findings.append({
                "type": "druggability",
                "title": "Top Binding Pocket",
                "detail": f"Pocket 1: {len(top['residues'])} residues, score={top['score']:.1f}, "
                          f"probability={top['probability']:.2f}",
                "priority": 1,
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_ptm_analysis(pdb_content: str, chain: str | None, result: InvestigationResult) -> dict:
    try:
        from src.ptm_analysis import predict_ptm_sites
        data = predict_ptm_sites(pdb_content, chain)
        result.analyses_run.append("ptm_analysis")

        n_sites = data.get("n_sites", 0)
        if n_sites > 0:
            types = data.get("summary", {}).get("types_found", [])
            result.findings.append({
                "type": "ptm",
                "title": "PTM Sites Predicted",
                "detail": f"{n_sites} potential PTM site(s): {', '.join(types)}",
                "priority": 3,
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_disorder_analysis(
    pdb_content: str, plddt: list[float] | None, chain: str | None,
    result: InvestigationResult,
) -> dict:
    try:
        from src.disorder_prediction import predict_disorder
        data = predict_disorder(pdb_content, plddt, chain)
        result.analyses_run.append("disorder_prediction")

        summary = data.get("summary", {})
        pct = summary.get("pct_disordered", 0)
        if pct > 0.1:
            result.findings.append({
                "type": "disorder",
                "title": "Disordered Regions",
                "detail": f"{summary.get('n_disordered', 0)} residues ({pct:.0%}) predicted disordered in "
                          f"{summary.get('n_disordered_regions', 0)} region(s)",
                "priority": 2,
            })
            if pct > 0.3:
                result.risk_flags.append({
                    "type": "high_disorder",
                    "severity": "medium",
                    "message": f">{pct:.0%} predicted disordered — structure prediction may be unreliable in these regions",
                })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_conservation_analysis(pdb_content: str, chain: str | None, result: InvestigationResult) -> dict:
    try:
        from src.conservation import compute_conservation_scores
        data = compute_conservation_scores(pdb_content, chain)
        result.analyses_run.append("conservation")

        summary = data.get("summary", {})
        pct_conserved = summary.get("pct_conserved", 0)
        n_patches = len(data.get("conserved_patches", []))

        if n_patches > 0:
            result.findings.append({
                "type": "conservation",
                "title": "Conserved Regions",
                "detail": f"{n_patches} highly conserved patch(es), {pct_conserved:.0%} of residues highly conserved",
                "priority": 2,
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _run_flexibility_analysis(pdb_content: str, chain: str | None, result: InvestigationResult) -> dict:
    try:
        from src.flexibility_analysis import compute_anm_flexibility
        data = compute_anm_flexibility(pdb_content, chain)
        result.analyses_run.append("flexibility")

        hinges = data.get("hinge_residues", [])
        if hinges:
            result.findings.append({
                "type": "dynamics",
                "title": "Hinge Residues",
                "detail": f"{len(hinges)} hinge residue(s) detected — potential conformational switch points",
                "priority": 3,
            })

        return data
    except Exception as e:
        return {"error": str(e)}


def _cross_reference(
    result: InvestigationResult,
    structure: dict, surface: dict, pockets: dict,
    ptms: dict, disorder: dict, conservation: dict, flexibility: dict,
    mutation: str | None, plddt: list[float] | None,
) -> None:
    """Cross-reference results across analyses to find compound insights."""
    import re

    mutation_pos = None
    if mutation:
        m = re.match(r"[A-Za-z](\d+)[A-Za-z]", mutation)
        if m:
            mutation_pos = int(m.group(1))

    # Cross-ref 1: Mutation in pocket
    if mutation_pos:
        top_pocket_res = set(pockets.get("top_pocket_residues", []))
        if mutation_pos in top_pocket_res:
            result.annotations.append({
                "type": "mutation_in_pocket",
                "residue": mutation_pos,
                "message": f"Mutation {mutation} directly in top binding pocket — high druggability impact",
                "severity": "critical",
            })

    # Cross-ref 2: PTMs in pockets
    ptm_residues = set(ptms.get("ptm_per_residue", {}).keys())
    pocket_residues = set(pockets.get("top_pocket_residues", []))
    ptm_in_pocket = ptm_residues & pocket_residues
    if ptm_in_pocket:
        result.annotations.append({
            "type": "ptm_in_pocket",
            "residues": sorted(ptm_in_pocket),
            "message": f"PTM sites overlap with binding pocket at {len(ptm_in_pocket)} position(s) — "
                       "modifications may regulate binding",
            "severity": "high",
        })

    # Cross-ref 3: Conserved pocket residues
    conserved = set(conservation.get("highly_conserved", []))
    conserved_pocket = conserved & pocket_residues
    if conserved_pocket and len(conserved_pocket) >= 3:
        result.annotations.append({
            "type": "conserved_pocket",
            "residues": sorted(conserved_pocket),
            "message": f"Binding pocket contains {len(conserved_pocket)} highly conserved residues — "
                       "functionally important site",
            "severity": "high",
        })

    # Cross-ref 4: Mutation at conserved position
    if mutation_pos and mutation_pos in conserved:
        result.risk_flags.append({
            "type": "mutation_at_conserved",
            "residue": mutation_pos,
            "severity": "high",
            "message": f"Mutation {mutation} at highly conserved position — likely functional impact",
        })

    # Cross-ref 5: Disordered regions with high pLDDT
    if plddt:
        disordered_set = set(
            r for r, is_dis in disorder.get("is_disordered", {}).items() if is_dis
        )
        res_ids = structure.get("residue_ids", [])
        for idx, rid in enumerate(res_ids):
            if idx < len(plddt) and rid in disordered_set and plddt[idx] > 80:
                result.annotations.append({
                    "type": "false_positive_disorder",
                    "residue": rid,
                    "message": f"Residue {rid}: predicted disordered but high pLDDT — may be a genuine flexible region",
                    "severity": "info",
                })
                break  # Only flag once

    # Cross-ref 6: Flexible + conserved = functional dynamics
    flex_res = set(flexibility.get("flexible_residues", []))
    flex_conserved = flex_res & conserved
    if len(flex_conserved) >= 3:
        result.findings.append({
            "type": "functional_dynamics",
            "title": "Conserved Flexible Regions",
            "detail": f"{len(flex_conserved)} residues are both flexible AND conserved — "
                      "suggests functionally important conformational dynamics",
            "priority": 1,
        })

    # Generate recommendations
    _generate_recommendations(result, mutation, mutation_pos, structure, pockets)


def _generate_recommendations(
    result: InvestigationResult,
    mutation: str | None,
    mutation_pos: int | None,
    structure: dict,
    pockets: dict,
) -> None:
    """Generate actionable recommendations based on findings."""
    if mutation_pos:
        result.recommendations.append(
            f"Run VEP analysis for {mutation} to check SIFT/PolyPhen predictions"
        )
        result.recommendations.append(
            f"Check gnomAD population frequency for the gene to assess constraint"
        )

    if pockets.get("pockets"):
        result.recommendations.append(
            "Search PubChem for known compounds targeting this protein"
        )
        result.recommendations.append(
            "Compare predicted pocket with experimental ligand-bound structures in PDB"
        )

    has_high_disorder = any(f.get("type") == "high_disorder" for f in result.risk_flags)
    if has_high_disorder:
        result.recommendations.append(
            "Consider using AlphaFold Multimer or cryo-EM for disordered regions"
        )

    result.recommendations.append(
        "Search STRING DB for interaction partners to contextualize findings"
    )
    result.recommendations.append(
        "Retrieve UniProt annotations for experimentally validated features"
    )


def _generate_summary(result: InvestigationResult) -> str:
    """Generate a concise natural-language summary of findings."""
    parts = [f"**Auto-investigation of {result.protein_name}**"]
    parts.append(f"Ran {len(result.analyses_run)} analyses.")

    if result.risk_flags:
        critical = [f for f in result.risk_flags if f.get("severity") in ("critical", "high")]
        if critical:
            parts.append(f"\n**{len(critical)} high-priority flag(s):**")
            for flag in critical[:3]:
                parts.append(f"- {flag['message']}")

    if result.findings:
        top_findings = sorted(result.findings, key=lambda f: f.get("priority", 5))[:5]
        parts.append(f"\n**Key findings:**")
        for finding in top_findings:
            parts.append(f"- **{finding['title']}**: {finding['detail']}")

    if result.annotations:
        parts.append(f"\n**{len(result.annotations)} cross-reference annotation(s) generated.**")

    if result.recommendations:
        parts.append(f"\n**Recommended next steps:**")
        for rec in result.recommendations[:4]:
            parts.append(f"- {rec}")

    return "\n".join(parts)
