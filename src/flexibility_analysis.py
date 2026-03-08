"""ProDy-based protein dynamics analysis (Anisotropic Network Model).

Computes per-residue flexibility from predicted structure coordinates.
High flexibility + high pLDDT = interesting dynamics (not disorder).
"""
from __future__ import annotations

import io


def compute_anm_flexibility(
    pdb_content: str,
    chain: str | None = None,
) -> dict:
    """Compute per-residue flexibility using Anisotropic Network Model.

    Returns dict with flexibility scores (0=rigid, 1=most flexible),
    hinge residues, and raw square fluctuations.
    """
    import numpy as np
    import prody

    # Suppress ProDy logging
    prody.confProDy(verbosity="none")

    struct = prody.parsePDBStream(io.StringIO(pdb_content))
    ca_atoms = struct.select("calpha")
    if ca_atoms is None:
        return _empty_result()

    if chain:
        ca_chain = struct.select(f"calpha and chain {chain}")
        if ca_chain is not None and len(ca_chain) > 5:
            ca_atoms = ca_chain

    n_atoms = len(ca_atoms)
    if n_atoms < 10:
        return _empty_result()

    # Build ANM
    anm = prody.ANM("protein")
    anm.buildHessian(ca_atoms, cutoff=15.0)
    n_modes = min(20, n_atoms - 6)  # Can't exceed DOF - 6 trivial modes
    if n_modes < 1:
        return _empty_result()

    anm.calcModes(n_modes=n_modes)

    # Per-residue square fluctuations from first 10 modes (or fewer)
    use_modes = min(10, n_modes)
    sq_flucts = prody.calcSqFlucts(anm[:use_modes])

    # Normalize to 0-1
    fmin, fmax = sq_flucts.min(), sq_flucts.max()
    if fmax - fmin > 1e-10:
        flexibility = (sq_flucts - fmin) / (fmax - fmin)
    else:
        flexibility = np.zeros_like(sq_flucts)

    res_ids = ca_atoms.getResnums().tolist()

    # Detect hinge residues (sign changes in first mode eigenvector)
    hinges = _detect_hinges(anm, ca_atoms)

    # Classify regions
    flex_threshold = 0.7
    rigid_threshold = 0.2
    flexible_residues = [r for r, f in zip(res_ids, flexibility) if f > flex_threshold]
    rigid_residues = [r for r, f in zip(res_ids, flexibility) if f < rigid_threshold]

    return {
        "residue_ids": res_ids,
        "flexibility": [float(f) for f in flexibility],
        "sq_fluctuations": [float(f) for f in sq_flucts],
        "flexible_residues": flexible_residues,
        "rigid_residues": rigid_residues,
        "hinge_residues": hinges,
        "n_modes": n_modes,
        "pct_rigid": len(rigid_residues) / len(res_ids) if res_ids else 0,
        "pct_flexible": len(flexible_residues) / len(res_ids) if res_ids else 0,
    }


def _detect_hinges(anm, atoms) -> list[int]:
    """Find hinge residues where the first mode eigenvector changes sign."""
    import numpy as np

    try:
        mode1 = anm[0].getEigvec()
        # Take x-component of each Cα's displacement
        x_disp = mode1[::3]
        sign_changes = np.where(np.diff(np.sign(x_disp)))[0]
        res_ids = atoms.getResnums()
        return [int(res_ids[i]) for i in sign_changes if i < len(res_ids)]
    except Exception:
        return []


def compare_flexibility_to_plddt(
    flexibility: dict,
    plddt_scores: list[float],
    residue_ids: list[int],
) -> dict:
    """Find discordant regions between ANM flexibility and pLDDT confidence."""
    import numpy as np

    flex_vals = flexibility.get("flexibility", [])
    flex_res = flexibility.get("residue_ids", [])

    if not flex_vals or not plddt_scores:
        return {"correlation": 0.0, "interesting_residues": [], "flags": []}

    # Align by residue ID
    plddt_map = dict(zip(residue_ids, plddt_scores))
    aligned_flex, aligned_plddt = [], []
    for r, f in zip(flex_res, flex_vals):
        if r in plddt_map:
            aligned_flex.append(f)
            aligned_plddt.append(plddt_map[r] / 100.0)

    if len(aligned_flex) < 5:
        return {"correlation": 0.0, "interesting_residues": [], "flags": []}

    correlation = float(np.corrcoef(aligned_flex, aligned_plddt)[0, 1])

    flags = []
    interesting = []
    for r, f, p in zip(flex_res, flex_vals, [plddt_map.get(r, 50) for r in flex_res]):
        if f > 0.7 and p > 70:
            interesting.append(r)
            flags.append(f"Residue {r}: high flexibility + high pLDDT → interesting dynamics")
        elif f < 0.2 and p < 50:
            flags.append(f"Residue {r}: rigid + low pLDDT → possible prediction error")

    return {
        "correlation": correlation,
        "interesting_residues": interesting[:20],
        "flags": flags[:10],
    }


def generate_nma_trajectory(
    pdb_content: str,
    chain: str | None = None,
    mode_index: int = 0,
    n_steps: int = 10,
    rmsd: float = 1.5,
) -> dict:
    """Generate a multi-model PDB trajectory along a normal mode.

    Uses ProDy traverseMode() to create conformations showing protein
    "breathing" motion. The output PDB has 2*n_steps+1 models that can
    be animated in Mol*.

    Returns dict with multi-model PDB string, mode info, and n_frames.
    """
    import numpy as np
    import prody

    prody.confProDy(verbosity="none")

    struct = prody.parsePDBStream(io.StringIO(pdb_content))
    ca_atoms = struct.select("calpha")
    if ca_atoms is None:
        return {"pdb_content": None, "error": "No Cα atoms found"}

    if chain:
        ca_chain = struct.select(f"calpha and chain {chain}")
        if ca_chain is not None and len(ca_chain) > 5:
            ca_atoms = ca_chain

    n_atoms = len(ca_atoms)
    if n_atoms < 10:
        return {"pdb_content": None, "error": "Too few atoms for NMA"}

    # Build ANM and compute modes
    anm = prody.ANM("protein")
    anm.buildHessian(ca_atoms, cutoff=15.0)
    n_modes = min(20, n_atoms - 6)
    if n_modes < 1:
        return {"pdb_content": None, "error": "Cannot compute modes"}

    anm.calcModes(n_modes=n_modes)

    # Validate mode_index
    if mode_index >= n_modes:
        mode_index = 0

    # Generate trajectory along selected mode
    ensemble = prody.traverseMode(
        anm[mode_index], ca_atoms, n_steps=n_steps, rmsd=rmsd
    )
    n_frames = ensemble.numConfs()

    # Write multi-model PDB to string
    all_coords = ensemble.getCoordsets()
    output = io.StringIO()
    for i in range(n_frames):
        coords = all_coords[i]
        output.write(f"MODEL     {i + 1:4d}\n")
        for j, atom in enumerate(ca_atoms):
            x, y, z = coords[j]
            res_name = atom.getResname()
            chain_id = atom.getChid()
            res_num = atom.getResnum()
            atom_name = atom.getName()
            element = atom.getElement() or "C"
            bfactor = atom.getBeta()
            output.write(
                f"ATOM  {j + 1:5d}  {atom_name:<4s}{res_name:>3s} "
                f"{chain_id}{res_num:4d}    "
                f"{x:8.3f}{y:8.3f}{z:8.3f}"
                f"  1.00{bfactor:6.2f}          {element:>2s}\n"
            )
        output.write("ENDMDL\n")
    output.write("END\n")

    multimodel_pdb = output.getvalue()

    # Collect mode metadata
    eigenvalue = float(anm[mode_index].getEigval())
    variance_pct = float(
        eigenvalue / anm.getEigvals().sum() * 100
    ) if anm.getEigvals().sum() > 0 else 0.0

    return {
        "pdb_content": multimodel_pdb,
        "n_frames": n_frames,
        "mode_index": mode_index,
        "eigenvalue": eigenvalue,
        "variance_pct": variance_pct,
        "n_modes_available": n_modes,
        "rmsd": rmsd,
        "error": None,
    }


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "flexibility": [],
        "sq_fluctuations": [],
        "flexible_residues": [],
        "rigid_residues": [],
        "hinge_residues": [],
        "n_modes": 0,
        "pct_rigid": 0.0,
        "pct_flexible": 0.0,
    }
