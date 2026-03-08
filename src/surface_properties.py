"""Surface property analysis: hydrophobicity, charge, and electrostatic potential.

Computes per-residue physicochemical properties from PDB coordinates
using Kyte-Doolittle hydrophobicity and amino acid charge at pH 7.4.
Identifies functional surface patches (hydrophobic binding sites,
charged interaction surfaces).
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np

# Kyte-Doolittle hydrophobicity scale (-4.5 = most hydrophilic, +4.5 = most hydrophobic)
_KD_HYDROPHOBICITY = {
    "ALA": 1.8, "ARG": -4.5, "ASN": -3.5, "ASP": -3.5, "CYS": 2.5,
    "GLN": -3.5, "GLU": -3.5, "GLY": -0.4, "HIS": -3.2, "ILE": 4.5,
    "LEU": 3.8, "LYS": -3.9, "MET": 1.9, "PHE": 2.8, "PRO": -1.6,
    "SER": -0.8, "THR": -0.7, "TRP": -0.9, "TYR": -1.3, "VAL": 4.2,
}

# Net charge at pH 7.4
_CHARGE_PH74 = {
    "ALA": 0, "ARG": 1, "ASN": 0, "ASP": -1, "CYS": 0,
    "GLN": 0, "GLU": -1, "GLY": 0, "HIS": 0.1, "ILE": 0,
    "LEU": 0, "LYS": 1, "MET": 0, "PHE": 0, "PRO": 0,
    "SER": 0, "THR": 0, "TRP": 0, "TYR": 0, "VAL": 0,
}

# Eisenberg consensus hydrophobicity (normalized, for surface patches)
_EISENBERG = {
    "ALA": 0.62, "ARG": -2.53, "ASN": -0.78, "ASP": -0.90, "CYS": 0.29,
    "GLN": -0.85, "GLU": -0.74, "GLY": 0.48, "HIS": -0.40, "ILE": 1.38,
    "LEU": 1.06, "LYS": -1.50, "MET": 0.64, "PHE": 1.19, "PRO": 0.12,
    "SER": -0.18, "THR": -0.05, "TRP": 0.81, "TYR": 0.26, "VAL": 1.08,
}


def compute_surface_properties(
    pdb_content: str,
    chain: str | None = None,
    window_size: int = 7,
) -> dict:
    """Compute per-residue surface properties from PDB coordinates.

    Returns dict with hydrophobicity, charge, and surface patch analysis.
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    # Filter to first chain
    if chain:
        chain_mask = structure.chain_id == chain
        chain_struct = structure[chain_mask]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_mask = structure.chain_id == chain
        chain_struct = structure[chain_mask]

    # CA atoms for per-residue analysis
    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    res_names = [str(r).strip() for r in ca_atoms.res_name]

    if len(res_ids) < 5:
        return _empty_result()

    # SASA for surface classification
    sasa_values = struc.sasa(chain_struct, vdw_radii="ProtOr")
    sasa_per_residue: dict[int, float] = {}
    for i, atom in enumerate(chain_struct):
        rid = int(atom.res_id)
        if rid not in sasa_per_residue:
            sasa_per_residue[rid] = 0.0
        sasa_per_residue[rid] += sasa_values[i]

    # Per-residue properties
    hydrophobicity: dict[int, float] = {}
    charge: dict[int, float] = {}
    eisenberg: dict[int, float] = {}

    for rid, rname in zip(res_ids, res_names):
        hydrophobicity[rid] = _KD_HYDROPHOBICITY.get(rname, 0.0)
        charge[rid] = _CHARGE_PH74.get(rname, 0.0)
        eisenberg[rid] = _EISENBERG.get(rname, 0.0)

    # Sliding window average for smoothed hydrophobicity profile
    hydro_vals = [hydrophobicity.get(r, 0.0) for r in res_ids]
    smoothed = _sliding_window(hydro_vals, window_size)
    hydrophobicity_smoothed = dict(zip(res_ids, smoothed))

    # Surface-exposed properties only
    surface_residues = [r for r in res_ids if sasa_per_residue.get(r, 0) > 25.0]
    buried_residues = [r for r in res_ids if sasa_per_residue.get(r, 0) <= 25.0]

    # Identify hydrophobic surface patches (exposed + hydrophobic)
    hydrophobic_surface = [
        r for r in surface_residues
        if hydrophobicity.get(r, 0) > 1.0
    ]

    # Identify charged surface clusters
    positive_surface = [r for r in surface_residues if charge.get(r, 0) > 0.5]
    negative_surface = [r for r in surface_residues if charge.get(r, 0) < -0.5]

    # Find contiguous hydrophobic patches on surface
    hydrophobic_patches = _find_patches(
        res_ids, lambda r: r in set(hydrophobic_surface), min_size=3
    )

    # Find charged clusters
    positive_patches = _find_patches(
        res_ids, lambda r: r in set(positive_surface), min_size=2
    )
    negative_patches = _find_patches(
        res_ids, lambda r: r in set(negative_surface), min_size=2
    )

    # Summary statistics
    surface_hydro_avg = (
        np.mean([hydrophobicity.get(r, 0) for r in surface_residues])
        if surface_residues else 0.0
    )
    net_charge = sum(charge.get(r, 0) for r in res_ids)
    surface_net_charge = sum(charge.get(r, 0) for r in surface_residues)

    # Isoelectric point estimate (simplified)
    n_pos = sum(1 for r in res_ids if charge.get(r, 0) > 0.5)
    n_neg = sum(1 for r in res_ids if charge.get(r, 0) < -0.5)

    return {
        "residue_ids": res_ids,
        "hydrophobicity": hydrophobicity,
        "hydrophobicity_smoothed": hydrophobicity_smoothed,
        "charge": charge,
        "eisenberg": eisenberg,
        "sasa": sasa_per_residue,
        "surface_residues": surface_residues,
        "buried_residues": buried_residues,
        "hydrophobic_surface_residues": hydrophobic_surface,
        "positive_surface_residues": positive_surface,
        "negative_surface_residues": negative_surface,
        "hydrophobic_patches": hydrophobic_patches,
        "positive_patches": positive_patches,
        "negative_patches": negative_patches,
        "summary": {
            "n_residues": len(res_ids),
            "n_surface": len(surface_residues),
            "n_buried": len(buried_residues),
            "pct_surface": round(len(surface_residues) / len(res_ids), 3),
            "surface_hydrophobicity_avg": round(float(surface_hydro_avg), 2),
            "net_charge": round(float(net_charge), 1),
            "surface_net_charge": round(float(surface_net_charge), 1),
            "n_positive_residues": n_pos,
            "n_negative_residues": n_neg,
            "n_hydrophobic_patches": len(hydrophobic_patches),
            "n_positive_patches": len(positive_patches),
            "n_negative_patches": len(negative_patches),
        },
    }


def _sliding_window(values: list[float], window: int) -> list[float]:
    """Compute sliding window average."""
    result = []
    half = window // 2
    for i in range(len(values)):
        start = max(0, i - half)
        end = min(len(values), i + half + 1)
        result.append(round(float(np.mean(values[start:end])), 3))
    return result


def _find_patches(
    res_ids: list[int],
    predicate,
    min_size: int = 3,
) -> list[dict]:
    """Find contiguous patches of residues satisfying predicate."""
    patches = []
    current: list[int] = []

    for r in res_ids:
        if predicate(r):
            if current and r - current[-1] > 2:
                if len(current) >= min_size:
                    patches.append({
                        "start": current[0],
                        "end": current[-1],
                        "size": len(current),
                        "residues": current,
                    })
                current = [r]
            else:
                current.append(r)
        else:
            if len(current) >= min_size:
                patches.append({
                    "start": current[0],
                    "end": current[-1],
                    "size": len(current),
                    "residues": current,
                })
            current = []

    if len(current) >= min_size:
        patches.append({
            "start": current[0],
            "end": current[-1],
            "size": len(current),
            "residues": current,
        })

    return patches


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "hydrophobicity": {},
        "hydrophobicity_smoothed": {},
        "charge": {},
        "eisenberg": {},
        "sasa": {},
        "surface_residues": [],
        "buried_residues": [],
        "hydrophobic_surface_residues": [],
        "positive_surface_residues": [],
        "negative_surface_residues": [],
        "hydrophobic_patches": [],
        "positive_patches": [],
        "negative_patches": [],
        "summary": {},
    }
