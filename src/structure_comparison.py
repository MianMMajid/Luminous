"""Predicted vs experimental structure comparison.

Fetches experimental structures from RCSB PDB and computes
per-residue RMSD against predicted structures using biotite
superimposition.
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np


def compare_structures(
    predicted_pdb: str,
    experimental_pdb: str,
    chain_pred: str | None = None,
    chain_exp: str | None = None,
) -> dict:
    """Compare predicted and experimental structures.

    Superimposes CA atoms and computes per-residue distances (RMSD).

    Returns dict with global RMSD, per-residue deviations, and
    regions of high/low agreement.
    """
    # Parse both structures
    pred_file = pdb.PDBFile.read(io.StringIO(predicted_pdb))
    exp_file = pdb.PDBFile.read(io.StringIO(experimental_pdb))

    pred_struct = pred_file.get_structure(model=1)
    exp_struct = exp_file.get_structure(model=1)

    # Select chains
    pred_chain = _select_chain(pred_struct, chain_pred)
    exp_chain = _select_chain(exp_struct, chain_exp)

    # Get CA atoms
    pred_ca = pred_chain[pred_chain.atom_name == "CA"]
    exp_ca = exp_chain[exp_chain.atom_name == "CA"]

    if len(pred_ca) < 5 or len(exp_ca) < 5:
        return {"error": "Insufficient CA atoms for comparison"}

    # Align by residue number — find common residues
    pred_res = {int(r): i for i, r in enumerate(pred_ca.res_id)}
    exp_res = {int(r): i for i, r in enumerate(exp_ca.res_id)}
    common_res = sorted(set(pred_res.keys()) & set(exp_res.keys()))

    if len(common_res) < 10:
        # Try sequential alignment if residue numbering doesn't match
        min_len = min(len(pred_ca), len(exp_ca))
        pred_coords = pred_ca.coord[:min_len]
        exp_coords = exp_ca.coord[:min_len]
        common_res = list(range(1, min_len + 1))
        pred_rids = [int(pred_ca.res_id[i]) for i in range(min_len)]
        exp_rids = [int(exp_ca.res_id[i]) for i in range(min_len)]
    else:
        pred_indices = [pred_res[r] for r in common_res]
        exp_indices = [exp_res[r] for r in common_res]
        pred_coords = pred_ca.coord[pred_indices]
        exp_coords = exp_ca.coord[exp_indices]
        pred_rids = common_res
        exp_rids = common_res

    n = len(common_res)

    # Superimpose using Kabsch algorithm
    fitted_pred, transformation = struc.superimpose(
        exp_coords, pred_coords
    )

    # Per-residue CA-CA distance after superposition
    per_residue_dist = np.sqrt(
        np.sum((fitted_pred - exp_coords) ** 2, axis=1)
    )

    # Global RMSD
    global_rmsd = float(np.sqrt(np.mean(per_residue_dist ** 2)))

    # GDT-TS (Global Distance Test - Total Score)
    gdt_1 = float(np.sum(per_residue_dist < 1.0) / n)
    gdt_2 = float(np.sum(per_residue_dist < 2.0) / n)
    gdt_4 = float(np.sum(per_residue_dist < 4.0) / n)
    gdt_8 = float(np.sum(per_residue_dist < 8.0) / n)
    gdt_ts = (gdt_1 + gdt_2 + gdt_4 + gdt_8) / 4.0

    # TM-score approximation
    d0 = 1.24 * (n - 15) ** (1.0 / 3.0) - 1.8 if n > 15 else 0.5
    tm_scores = 1.0 / (1.0 + (per_residue_dist / d0) ** 2)
    tm_score = float(np.sum(tm_scores) / n)

    # Classify regions
    per_res_dict = {}
    well_modeled = []
    moderate_deviation = []
    poor_regions = []

    for i, rid in enumerate(pred_rids):
        dist = float(per_residue_dist[i])
        per_res_dict[rid] = round(dist, 2)

        if dist < 1.0:
            well_modeled.append(rid)
        elif dist < 3.0:
            moderate_deviation.append(rid)
        else:
            poor_regions.append(rid)

    # Find contiguous poor regions
    poor_stretches = _find_stretches(poor_regions, min_size=3)

    return {
        "global_rmsd": round(global_rmsd, 2),
        "gdt_ts": round(gdt_ts, 3),
        "tm_score": round(tm_score, 3),
        "n_aligned": n,
        "n_predicted": len(pred_ca),
        "n_experimental": len(exp_ca),
        "per_residue_rmsd": per_res_dict,
        "well_modeled": well_modeled,
        "moderate_deviation": moderate_deviation,
        "poor_regions": poor_regions,
        "poor_stretches": poor_stretches,
        "gdt_components": {
            "gdt_1A": round(gdt_1, 3),
            "gdt_2A": round(gdt_2, 3),
            "gdt_4A": round(gdt_4, 3),
            "gdt_8A": round(gdt_8, 3),
        },
        "quality_assessment": _assess_quality(global_rmsd, gdt_ts, tm_score),
        "summary": {
            "global_rmsd": round(global_rmsd, 2),
            "gdt_ts": round(gdt_ts, 3),
            "tm_score": round(tm_score, 3),
            "pct_well_modeled": round(len(well_modeled) / n, 3) if n else 0,
            "pct_poor": round(len(poor_regions) / n, 3) if n else 0,
            "n_poor_stretches": len(poor_stretches),
        },
    }


def fetch_experimental_pdb(pdb_id: str) -> str | None:
    """Download experimental PDB from RCSB."""
    import httpx

    try:
        url = f"https://files.rcsb.org/download/{pdb_id.upper()}.pdb"
        resp = httpx.get(url, timeout=httpx.Timeout(20.0, connect=10.0))
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def compare_with_plddt(
    comparison: dict,
    plddt_scores: list[float],
    residue_ids: list[int],
) -> dict:
    """Cross-reference per-residue RMSD with pLDDT confidence.

    Finds cases where pLDDT is high but RMSD is also high (surprising errors)
    and where pLDDT is low but RMSD is also low (better than expected).
    """
    per_res_rmsd = comparison.get("per_residue_rmsd", {})
    if not per_res_rmsd or not plddt_scores:
        return {"correlation": 0.0, "surprising_errors": [], "better_than_expected": []}

    plddt_map = dict(zip(residue_ids, plddt_scores))

    # Compute correlation
    aligned_rmsd = []
    aligned_plddt = []
    for rid, rmsd_val in per_res_rmsd.items():
        if rid in plddt_map:
            aligned_rmsd.append(rmsd_val)
            aligned_plddt.append(plddt_map[rid])

    if len(aligned_rmsd) < 10:
        return {"correlation": 0.0, "surprising_errors": [], "better_than_expected": []}

    correlation = float(np.corrcoef(aligned_rmsd, aligned_plddt)[0, 1])

    surprising_errors = []
    better_than_expected = []

    for rid, rmsd_val in per_res_rmsd.items():
        plddt_val = plddt_map.get(rid)
        if plddt_val is None:
            continue

        if plddt_val > 80 and rmsd_val > 3.0:
            surprising_errors.append({
                "residue": rid,
                "plddt": round(plddt_val, 1),
                "rmsd": rmsd_val,
                "note": "High confidence but poor prediction",
            })
        elif plddt_val < 50 and rmsd_val < 1.0:
            better_than_expected.append({
                "residue": rid,
                "plddt": round(plddt_val, 1),
                "rmsd": rmsd_val,
                "note": "Low confidence but good prediction",
            })

    return {
        "correlation": round(correlation, 3),
        "surprising_errors": surprising_errors[:20],
        "better_than_expected": better_than_expected[:20],
        "n_surprising_errors": len(surprising_errors),
        "n_better_than_expected": len(better_than_expected),
    }


def _select_chain(structure, chain: str | None):
    """Select specified chain or first chain."""
    if chain:
        mask = structure.chain_id == chain
        return structure[mask]
    chains = sorted(set(structure.chain_id))
    if chains:
        return structure[structure.chain_id == chains[0]]
    return structure


def _find_stretches(positions: list[int], min_size: int = 3) -> list[dict]:
    """Find contiguous stretches in a sorted list of positions."""
    if not positions:
        return []

    positions = sorted(positions)
    stretches = []
    current = [positions[0]]

    for p in positions[1:]:
        if p - current[-1] <= 2:
            current.append(p)
        else:
            if len(current) >= min_size:
                stretches.append({
                    "start": current[0],
                    "end": current[-1],
                    "size": len(current),
                })
            current = [p]

    if len(current) >= min_size:
        stretches.append({
            "start": current[0],
            "end": current[-1],
            "size": len(current),
        })

    return stretches


def _assess_quality(rmsd: float, gdt_ts: float, tm_score: float) -> str:
    """Assess overall prediction quality."""
    if tm_score > 0.9 and rmsd < 1.0:
        return "Excellent — near-experimental accuracy"
    elif tm_score > 0.7 and rmsd < 2.0:
        return "Good — reliable for most analyses"
    elif tm_score > 0.5 and rmsd < 4.0:
        return "Moderate — backbone topology correct, details may vary"
    elif tm_score > 0.3:
        return "Low — same fold family, significant local errors"
    else:
        return "Poor — structure may have different fold"
