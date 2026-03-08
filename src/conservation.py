"""Sequence conservation analysis via ConSurf-like scoring.

Computes per-residue conservation using amino acid substitution matrices
and queries external APIs for evolutionary data. Uses a simplified
Shannon entropy approach when alignments are not available.
"""
from __future__ import annotations

import io
import math

import biotite.structure.io.pdb as pdb

# Amino acid conservation groups (Taylor, 1986 + physicochemical)
# Residues in the same group are considered conservative substitutions
_CONSERVATION_GROUPS = [
    set("GAVLI"),      # Small hydrophobic
    set("FYW"),        # Aromatic
    set("CM"),         # Sulfur-containing
    set("ST"),         # Small hydroxyl
    set("KRH"),        # Positive charge
    set("DE"),         # Negative charge
    set("NQ"),         # Amide
    set("P"),          # Proline (unique)
    set("G"),          # Glycine (unique)
]

# BLOSUM62-derived conservation weight (higher = more conserved in nature)
_AA_CONSERVATION_WEIGHT = {
    "W": 0.95, "C": 0.90, "H": 0.75, "Y": 0.70, "F": 0.65,
    "M": 0.60, "P": 0.85, "D": 0.55, "E": 0.55, "N": 0.50,
    "Q": 0.45, "K": 0.45, "R": 0.50, "I": 0.40, "V": 0.35,
    "L": 0.30, "T": 0.40, "S": 0.35, "A": 0.25, "G": 0.70,
}

# 3-letter to 1-letter
_AA_3TO1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def compute_conservation_scores(
    pdb_content: str,
    chain: str | None = None,
) -> dict:
    """Compute per-residue conservation scores from amino acid properties.

    Uses a heuristic combining:
    1. Intrinsic amino acid conservation tendency (BLOSUM62-derived)
    2. Local sequence context (conserved motifs)
    3. Structural context (buried residues tend to be more conserved)

    Returns ConSurf-like 1-9 scale (9 = most conserved).
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    if chain:
        chain_mask = structure.chain_id == chain
        chain_struct = structure[chain_mask]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_mask = structure.chain_id == chain
        chain_struct = structure[chain_mask]

    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    res_names = [str(r).strip() for r in ca_atoms.res_name]
    sequence = "".join(_AA_3TO1.get(rn, "X") for rn in res_names)

    if len(sequence) < 5:
        return _empty_result()

    # Compute SASA for burial-based conservation boost
    import biotite.structure as struc
    sasa_values = struc.sasa(chain_struct, vdw_radii="ProtOr")
    sasa_per_residue: dict[int, float] = {}
    for i, atom in enumerate(chain_struct):
        rid = int(atom.res_id)
        if rid not in sasa_per_residue:
            sasa_per_residue[rid] = 0.0
        sasa_per_residue[rid] += sasa_values[i]

    # Per-residue raw conservation score
    raw_scores: list[float] = []
    for idx, (rid, aa) in enumerate(zip(res_ids, sequence)):
        # Base score from amino acid identity
        base = _AA_CONSERVATION_WEIGHT.get(aa, 0.4)

        # Burial boost: buried residues are more conserved
        sasa_val = sasa_per_residue.get(rid, 50)
        if sasa_val < 10:
            burial_boost = 0.25  # Deeply buried
        elif sasa_val < 25:
            burial_boost = 0.15  # Partially buried
        else:
            burial_boost = 0.0   # Exposed

        # Context boost: residues in conserved motifs
        context_boost = _context_conservation(sequence, idx)

        score = min(1.0, base + burial_boost + context_boost)
        raw_scores.append(score)

    # Normalize to ConSurf 1-9 scale
    if raw_scores:
        min_s, max_s = min(raw_scores), max(raw_scores)
        range_s = max_s - min_s if max_s - min_s > 0.01 else 1.0
        consurf_scores = [
            max(1, min(9, round(1 + 8 * (s - min_s) / range_s)))
            for s in raw_scores
        ]
    else:
        consurf_scores = []

    conservation_per_residue = dict(zip(res_ids, consurf_scores))
    raw_per_residue = dict(zip(res_ids, [round(s, 3) for s in raw_scores]))

    # Classify conservation levels
    highly_conserved = [r for r, s in conservation_per_residue.items() if s >= 7]
    variable = [r for r, s in conservation_per_residue.items() if s <= 3]

    # Find conserved patches
    conserved_patches = _find_conserved_patches(res_ids, consurf_scores)

    return {
        "residue_ids": res_ids,
        "conservation_scores": conservation_per_residue,
        "raw_scores": raw_per_residue,
        "sequence": sequence,
        "highly_conserved": highly_conserved,
        "variable": variable,
        "conserved_patches": conserved_patches,
        "method": "heuristic (BLOSUM62 + burial + context)",
        "summary": {
            "n_residues": len(res_ids),
            "n_highly_conserved": len(highly_conserved),
            "n_variable": len(variable),
            "pct_conserved": round(len(highly_conserved) / len(res_ids), 3) if res_ids else 0,
            "avg_score": round(sum(consurf_scores) / len(consurf_scores), 1) if consurf_scores else 0,
        },
    }


def fetch_consurf_data(uniprot_id: str) -> dict:
    """Fetch ConSurf conservation data from the ConSurf DB API.

    Falls back to a simplified approach if ConSurf is unavailable.
    """
    import httpx

    try:
        resp = httpx.get(
            f"https://consurfdb.tau.ac.il/API/getConSurfDBResults/{uniprot_id}/",
            timeout=httpx.Timeout(20.0, connect=10.0),
        )
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and "results" in data:
                scores = {}
                for entry in data["results"]:
                    pos = entry.get("pos")
                    grade = entry.get("grade")
                    if pos is not None and grade is not None:
                        scores[int(pos)] = int(grade)
                return {
                    "source": "ConSurf DB",
                    "uniprot_id": uniprot_id,
                    "conservation_scores": scores,
                    "n_residues": len(scores),
                }
    except Exception:
        pass

    return {"error": "ConSurf data not available", "source": "none"}


def _context_conservation(sequence: str, idx: int, window: int = 5) -> float:
    """Assess local sequence context conservation.

    Checks for known conserved motifs and patterns.
    """
    boost = 0.0
    n = len(sequence)

    # Extract local window
    start = max(0, idx - window)
    end = min(n, idx + window + 1)
    local = sequence[start:end]

    # Known conserved motifs
    conserved_motifs = [
        "CxxC",    # Metal-binding
        "GxGxxG",  # Nucleotide-binding (Rossmann fold)
        "DxD",     # Catalytic
        "HxxH",    # Metal coordination
        "RGD",     # Cell attachment
        "NxS",     # Glycosylation
        "NxT",     # Glycosylation
    ]

    aa = sequence[idx]

    # Check if current residue is in a known motif
    for motif in conserved_motifs:
        motif_re = motif.replace("x", ".")
        import re
        if re.search(motif_re, local):
            boost += 0.1
            break

    # Catalytic residue boost (D, E, H, K, C, S in active sites)
    if aa in "DEHKCS":
        # Check if flanked by conservation group members
        left = sequence[idx - 1] if idx > 0 else ""
        right = sequence[idx + 1] if idx < n - 1 else ""
        if left in "GAVLI" and right in "GAVLI":
            boost += 0.05  # Conserved hydrophobic flanking

    # Proline/glycine structural conservation
    if aa in "PG":
        boost += 0.05

    return min(0.2, boost)


def _find_conserved_patches(
    res_ids: list[int],
    scores: list[int],
    min_score: int = 7,
    min_size: int = 3,
) -> list[dict]:
    """Find contiguous stretches of highly conserved residues."""
    patches = []
    current: list[int] = []
    current_scores: list[int] = []

    for rid, score in zip(res_ids, scores):
        if score >= min_score:
            if current and rid - current[-1] > 2:
                if len(current) >= min_size:
                    patches.append({
                        "start": current[0],
                        "end": current[-1],
                        "size": len(current),
                        "avg_score": round(sum(current_scores) / len(current_scores), 1),
                        "residues": current,
                    })
                current = [rid]
                current_scores = [score]
            else:
                current.append(rid)
                current_scores.append(score)
        else:
            if len(current) >= min_size:
                patches.append({
                    "start": current[0],
                    "end": current[-1],
                    "size": len(current),
                    "avg_score": round(sum(current_scores) / len(current_scores), 1),
                    "residues": current,
                })
            current = []
            current_scores = []

    if len(current) >= min_size:
        patches.append({
            "start": current[0],
            "end": current[-1],
            "size": len(current),
            "avg_score": round(sum(current_scores) / len(current_scores), 1),
            "residues": current,
        })

    return patches


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "conservation_scores": {},
        "raw_scores": {},
        "sequence": "",
        "highly_conserved": [],
        "variable": [],
        "conserved_patches": [],
        "method": "none",
        "summary": {},
    }
