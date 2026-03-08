"""Residue depth analysis — continuous burial gradient.

Unlike binary SASA (buried/exposed), residue depth measures how far each
residue is from the nearest solvent-accessible surface atom. This reveals:
- Deeply buried core residues (mutations here are most destabilizing)
- Intermediate depth residues (often at interfaces or pocket linings)
- The continuous burial gradient that SASA misses

Depth correlates with:
- Mutational sensitivity (deep = sensitive)
- Conservation (deep = more conserved)
- Thermodynamic stability contribution
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np


def compute_residue_depth(
    pdb_content: str,
    chain: str | None = None,
    sasa_surface_threshold: float = 25.0,
) -> dict:
    """Compute per-residue depth (distance to nearest surface atom).

    Parameters
    ----------
    pdb_content : str
        PDB file content.
    chain : str | None
        Chain to analyze (default: first chain).
    sasa_surface_threshold : float
        SASA threshold to define surface atoms (default 25 Å²).

    Returns
    -------
    dict with per-residue depth values, classifications, and summary.
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    if chain:
        chain_struct = structure[structure.chain_id == chain]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_struct = structure[structure.chain_id == chain]

    # Filter to amino acids only
    aa_mask = struc.filter_amino_acids(chain_struct)
    protein = chain_struct[aa_mask]
    if len(protein) < 10:
        return _empty_result()

    # Compute SASA to identify surface atoms
    sasa = struc.sasa(protein, vdw_radii="ProtOr")

    # Surface atoms: SASA > 0 (any solvent exposure)
    surface_mask = sasa > 1.0  # atoms with any solvent exposure
    surface_coords = protein.coord[surface_mask]

    if len(surface_coords) < 5:
        return _empty_result()

    # CA atoms for per-residue metrics
    ca_mask = protein.atom_name == "CA"
    ca_atoms = protein[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    ca_coords = ca_atoms.coord

    if len(res_ids) < 5:
        return _empty_result()

    # Compute depth: minimum distance from each CA to any surface atom
    # Use chunked computation for memory efficiency on large proteins
    n_ca = len(ca_coords)
    n_surf = len(surface_coords)
    chunk_size = 500

    depths = np.zeros(n_ca)
    for start in range(0, n_ca, chunk_size):
        end = min(start + chunk_size, n_ca)
        ca_chunk = ca_coords[start:end]
        # Pairwise distances: (chunk_size, n_surface)
        diff = ca_chunk[:, np.newaxis, :] - surface_coords[np.newaxis, :, :]
        dists = np.sqrt(np.sum(diff ** 2, axis=2))
        depths[start:end] = np.min(dists, axis=1)

    # Normalize to 0-1 scale
    d_min, d_max = float(depths.min()), float(depths.max())
    if d_max - d_min > 0.01:
        depth_normalized = (depths - d_min) / (d_max - d_min)
    else:
        depth_normalized = np.zeros_like(depths)

    depth_per_residue = {
        int(r): round(float(d), 3) for r, d in zip(res_ids, depths)
    }
    depth_normalized_per_residue = {
        int(r): round(float(d), 3) for r, d in zip(res_ids, depth_normalized)
    }

    # Classify depth zones
    deep_core = [r for r, d in depth_per_residue.items() if d > 8.0]
    intermediate = [r for r, d in depth_per_residue.items() if 4.0 < d <= 8.0]
    surface = [r for r, d in depth_per_residue.items() if d <= 4.0]

    return {
        "residue_ids": res_ids,
        "depth": depth_per_residue,
        "depth_normalized": depth_normalized_per_residue,
        "deep_core": deep_core,
        "intermediate": intermediate,
        "surface": surface,
        "summary": {
            "n_residues": len(res_ids),
            "n_deep_core": len(deep_core),
            "n_intermediate": len(intermediate),
            "n_surface": len(surface),
            "max_depth": round(d_max, 1),
            "mean_depth": round(float(np.mean(depths)), 1),
            "median_depth": round(float(np.median(depths)), 1),
        },
    }


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "depth": {},
        "depth_normalized": {},
        "deep_core": [],
        "intermediate": [],
        "surface": [],
        "summary": {},
    }
