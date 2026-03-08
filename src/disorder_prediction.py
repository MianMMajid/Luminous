"""Intrinsic disorder prediction from sequence and structure.

Combines multiple signals to predict disordered regions:
1. Amino acid composition (disorder-promoting residues)
2. Sequence complexity (low-complexity = often disordered)
3. pLDDT confidence (low pLDDT correlates with disorder)
4. SASA + secondary structure (exposed coil = likely disordered)
"""
from __future__ import annotations

import io
import math

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np

# Disorder propensity scale (DisProt-derived, normalized 0-1)
# Higher = more disorder-promoting
_DISORDER_PROPENSITY = {
    "A": 0.35, "R": 0.45, "N": 0.50, "D": 0.55, "C": 0.15,
    "Q": 0.55, "E": 0.60, "G": 0.50, "H": 0.35, "I": 0.15,
    "L": 0.15, "K": 0.55, "M": 0.25, "F": 0.10, "P": 0.65,
    "S": 0.55, "T": 0.40, "W": 0.05, "Y": 0.15, "V": 0.15,
}

# Order-promoting residues
_ORDER_PROMOTING = set("WFYILVMC")
# Disorder-promoting residues
_DISORDER_PROMOTING = set("AQEKSPDRG")

# 3-letter to 1-letter
_AA_3TO1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def predict_disorder(
    pdb_content: str,
    plddt_scores: list[float] | None = None,
    chain: str | None = None,
    window_size: int = 21,
) -> dict:
    """Predict intrinsically disordered regions from sequence and structure.

    Returns per-residue disorder scores (0-1, >0.5 = disordered)
    and identified disordered regions.
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    if chain:
        chain_mask = structure.chain_id == chain
        chain_struct = structure[chain_mask]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_struct = structure[structure.chain_id == chain]

    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    res_names = [str(r).strip() for r in ca_atoms.res_name]
    sequence = "".join(_AA_3TO1.get(rn, "X") for rn in res_names)

    if len(sequence) < 5:
        return _empty_result()

    # 1. Sequence-based disorder propensity (sliding window)
    seq_scores = _sequence_disorder(sequence, window_size)

    # 2. Complexity-based score
    complexity_scores = _sequence_complexity(sequence, window_size)

    # 3. Structure-based signals
    sasa_values = struc.sasa(chain_struct, vdw_radii="ProtOr")
    sasa_per_residue: dict[int, float] = {}
    for i, atom in enumerate(chain_struct):
        rid = int(atom.res_id)
        if rid not in sasa_per_residue:
            sasa_per_residue[rid] = 0.0
        sasa_per_residue[rid] += sasa_values[i]

    # Secondary structure
    sse = struc.annotate_sse(chain_struct)
    sse_per_residue: dict[int, str] = {}
    seen: set[int] = set()
    sse_idx = 0
    for atom in chain_struct:
        rid = int(atom.res_id)
        if rid not in seen:
            seen.add(rid)
            if sse_idx < len(sse):
                sse_per_residue[rid] = sse[sse_idx]
                sse_idx += 1

    # 4. Combine all signals into disorder score
    disorder_scores: list[float] = []
    for idx, rid in enumerate(res_ids):
        # Sequence propensity (40% weight)
        seq_score = seq_scores[idx] if idx < len(seq_scores) else 0.5

        # Complexity (15% weight)
        compl_score = complexity_scores[idx] if idx < len(complexity_scores) else 0.5

        # pLDDT signal (25% weight) — low pLDDT = high disorder
        plddt_score = 0.5
        if plddt_scores and idx < len(plddt_scores):
            plddt_val = plddt_scores[idx]
            plddt_score = max(0, 1.0 - plddt_val / 100.0)

        # Structure signal (20% weight) — exposed coil = disordered
        struct_score = 0.3
        sasa_val = sasa_per_residue.get(rid, 50)
        ss = str(sse_per_residue.get(rid, "c")).strip()

        if ss == "c" and sasa_val > 40:
            struct_score = 0.8
        elif ss == "c":
            struct_score = 0.5
        elif ss in ("a", "b"):
            struct_score = 0.1

        # Weighted combination
        combined = (
            0.40 * seq_score
            + 0.15 * compl_score
            + 0.25 * plddt_score
            + 0.20 * struct_score
        )
        disorder_scores.append(round(min(1.0, max(0.0, combined)), 3))

    # Identify disordered regions (score > 0.5, min 5 residues)
    disordered_regions = _find_disordered_regions(res_ids, disorder_scores)

    # Per-residue classification
    disorder_per_residue = dict(zip(res_ids, disorder_scores))
    is_disordered = {r: s > 0.5 for r, s in disorder_per_residue.items()}

    # Summary
    n_disordered = sum(1 for s in disorder_scores if s > 0.5)
    n_ordered = len(disorder_scores) - n_disordered

    return {
        "residue_ids": res_ids,
        "disorder_scores": disorder_per_residue,
        "is_disordered": is_disordered,
        "disordered_regions": disordered_regions,
        "sequence": sequence,
        "method": "multi-signal (propensity + complexity + pLDDT + structure)",
        "summary": {
            "n_residues": len(res_ids),
            "n_disordered": n_disordered,
            "n_ordered": n_ordered,
            "pct_disordered": round(n_disordered / len(res_ids), 3) if res_ids else 0,
            "n_disordered_regions": len(disordered_regions),
            "longest_disordered": max(
                (r["size"] for r in disordered_regions), default=0
            ),
        },
    }


def _sequence_disorder(sequence: str, window: int = 21) -> list[float]:
    """Compute per-residue disorder propensity from amino acid composition."""
    n = len(sequence)
    half = window // 2
    scores = []

    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        local_seq = sequence[start:end]

        # Average disorder propensity in window
        props = [_DISORDER_PROPENSITY.get(aa, 0.4) for aa in local_seq]
        avg_prop = sum(props) / len(props) if props else 0.4

        # Charge-hydrophobicity ratio (Uversky plot)
        n_charged = sum(1 for aa in local_seq if aa in "DEKR")
        n_hydrophobic = sum(1 for aa in local_seq if aa in _ORDER_PROMOTING)
        local_len = len(local_seq) or 1

        charge_ratio = n_charged / local_len
        hydro_ratio = n_hydrophobic / local_len

        # Disorder-order balance
        disorder_bias = charge_ratio - hydro_ratio

        # Combined score
        score = avg_prop * 0.6 + max(0, disorder_bias) * 0.4
        scores.append(min(1.0, max(0.0, score)))

    return scores


def _sequence_complexity(sequence: str, window: int = 21) -> list[float]:
    """Compute Shannon entropy-based sequence complexity.

    Low complexity (repetitive, biased composition) → high disorder score.
    """
    n = len(sequence)
    half = window // 2
    scores = []

    for i in range(n):
        start = max(0, i - half)
        end = min(n, i + half + 1)
        local_seq = sequence[start:end]
        local_len = len(local_seq) or 1

        # Shannon entropy
        aa_counts: dict[str, int] = {}
        for aa in local_seq:
            aa_counts[aa] = aa_counts.get(aa, 0) + 1

        entropy = 0.0
        for count in aa_counts.values():
            p = count / local_len
            if p > 0:
                entropy -= p * math.log2(p)

        # Normalize: max entropy for 20 aa types = log2(20) ≈ 4.32
        max_entropy = math.log2(min(20, local_len))
        normalized = entropy / max_entropy if max_entropy > 0 else 0

        # Low complexity → high disorder score
        disorder_from_complexity = max(0, 1.0 - normalized)
        scores.append(round(disorder_from_complexity, 3))

    return scores


def _find_disordered_regions(
    res_ids: list[int],
    scores: list[float],
    threshold: float = 0.5,
    min_size: int = 5,
) -> list[dict]:
    """Find contiguous disordered regions."""
    regions = []
    current: list[int] = []
    current_scores: list[float] = []

    for rid, score in zip(res_ids, scores):
        if score > threshold:
            if current and rid - current[-1] > 2:
                if len(current) >= min_size:
                    regions.append({
                        "start": current[0],
                        "end": current[-1],
                        "size": len(current),
                        "avg_score": round(sum(current_scores) / len(current_scores), 3),
                        "max_score": round(max(current_scores), 3),
                        "residues": current,
                    })
                current = [rid]
                current_scores = [score]
            else:
                current.append(rid)
                current_scores.append(score)
        else:
            if len(current) >= min_size:
                regions.append({
                    "start": current[0],
                    "end": current[-1],
                    "size": len(current),
                    "avg_score": round(sum(current_scores) / len(current_scores), 3),
                    "max_score": round(max(current_scores), 3),
                    "residues": current,
                })
            current = []
            current_scores = []

    if len(current) >= min_size:
        regions.append({
            "start": current[0],
            "end": current[-1],
            "size": len(current),
            "avg_score": round(sum(current_scores) / len(current_scores), 3),
            "max_score": round(max(current_scores), 3),
            "residues": current,
        })

    return regions


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "disorder_scores": {},
        "is_disordered": {},
        "disordered_regions": [],
        "sequence": "",
        "method": "none",
        "summary": {},
    }
