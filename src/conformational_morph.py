"""Conformational morphing between two protein structures.

Uses Biotite superimposition + NumPy linear interpolation to generate
smooth multi-model PDB trajectories. Mol* renders the trajectory as
an animation.
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np
import streamlit as st


@st.cache_data(ttl=3600, show_spinner=False)
def generate_morph_trajectory(
    pdb_content_a: str,
    pdb_content_b: str,
    n_frames: int = 20,
) -> str | None:
    """Generate a multi-model PDB with linearly interpolated frames.

    Parameters
    ----------
    pdb_content_a : PDB string for conformation A
    pdb_content_b : PDB string for conformation B
    n_frames : number of intermediate frames (default 20)

    Returns
    -------
    Multi-model PDB string suitable for Mol* trajectory animation,
    or None if structures are incompatible.
    """
    try:
        struct_a = pdb.PDBFile.read(io.StringIO(pdb_content_a)).get_structure(model=1)
        struct_b = pdb.PDBFile.read(io.StringIO(pdb_content_b)).get_structure(model=1)
    except Exception:
        return None

    # Filter to first chain of each
    chain_a = sorted(set(struct_a.chain_id))[0]
    chain_b = sorted(set(struct_b.chain_id))[0]
    struct_a = struct_a[struct_a.chain_id == chain_a]
    struct_b = struct_b[struct_b.chain_id == chain_b]

    # Match by CA atoms and residue ID
    ca_a = struct_a[struct_a.atom_name == "CA"]
    ca_b = struct_b[struct_b.atom_name == "CA"]

    # Find common residue IDs
    res_a = set(int(r) for r in ca_a.res_id)
    res_b = set(int(r) for r in ca_b.res_id)
    common = sorted(res_a & res_b)

    if len(common) < 10:
        return None

    # Filter both structures to common residues (all atoms)
    mask_a = np.isin(struct_a.res_id.astype(int), common)
    mask_b = np.isin(struct_b.res_id.astype(int), common)
    struct_a = struct_a[mask_a]
    struct_b = struct_b[mask_b]

    # Match atom counts — use only atoms present in both
    # Build atom key: (res_id, atom_name)
    keys_a = [(int(struct_a.res_id[i]), str(struct_a.atom_name[i]).strip())
              for i in range(len(struct_a))]
    keys_b = [(int(struct_b.res_id[i]), str(struct_b.atom_name[i]).strip())
              for i in range(len(struct_b))]

    set_b = set(keys_b)
    common_mask_a = [k in set_b for k in keys_a]
    set_a = set(keys_a)
    common_mask_b = [k in set_a for k in keys_b]

    struct_a = struct_a[common_mask_a]
    struct_b = struct_b[common_mask_b]

    if len(struct_a) != len(struct_b) or len(struct_a) < 10:
        return None

    # Superimpose B onto A
    struct_b_fit, _ = struc.superimpose(struct_a, struct_b)

    coords_a = struct_a.coord
    coords_b = struct_b_fit.coord

    # Generate interpolated frames (A → B → A for smooth loop)
    t_values = np.linspace(0, 1, n_frames // 2 + 1)
    # Forward: A→B
    forward = [(1 - t) * coords_a + t * coords_b for t in t_values]
    # Backward: B→A (skip first and last to avoid duplicates)
    backward = list(reversed(forward[1:-1]))
    all_frames = forward + backward

    # Build multi-model PDB string
    lines: list[str] = []
    for model_idx, frame_coords in enumerate(all_frames, start=1):
        lines.append(f"MODEL     {model_idx:4d}")
        frame_struct = struct_a.copy()
        frame_struct.coord = frame_coords
        pdb_file = pdb.PDBFile()
        pdb_file.set_structure(frame_struct)
        model_text = str(pdb_file)
        # Remove any existing MODEL/ENDMDL from inner PDB
        for line in model_text.split("\n"):
            if not line.startswith("MODEL") and not line.startswith("ENDMDL") and not line.startswith("END"):
                lines.append(line)
        lines.append("ENDMDL")
    lines.append("END")

    return "\n".join(lines)


def compute_morph_rmsd(pdb_content_a: str, pdb_content_b: str) -> float | None:
    """Compute CA RMSD between two structures after superimposition."""
    try:
        struct_a = pdb.PDBFile.read(io.StringIO(pdb_content_a)).get_structure(model=1)
        struct_b = pdb.PDBFile.read(io.StringIO(pdb_content_b)).get_structure(model=1)
    except Exception:
        return None

    chain_a = sorted(set(struct_a.chain_id))[0]
    chain_b = sorted(set(struct_b.chain_id))[0]
    ca_a = struct_a[(struct_a.chain_id == chain_a) & (struct_a.atom_name == "CA")]
    ca_b = struct_b[(struct_b.chain_id == chain_b) & (struct_b.atom_name == "CA")]

    common = sorted(set(int(r) for r in ca_a.res_id) & set(int(r) for r in ca_b.res_id))
    if len(common) < 10:
        return None

    ca_a = ca_a[np.isin(ca_a.res_id.astype(int), common)]
    ca_b = ca_b[np.isin(ca_b.res_id.astype(int), common)]

    if len(ca_a) != len(ca_b):
        return None

    ca_b_fit, _ = struc.superimpose(ca_a, ca_b)
    return float(struc.rmsd(ca_a, ca_b_fit))
