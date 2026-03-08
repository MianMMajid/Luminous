"""Post-translational modification (PTM) prediction and annotation.

Predicts potential PTM sites from sequence motifs and queries UniProt
for experimentally validated modifications. Maps PTMs onto structure
with SASA-based accessibility scoring.
"""
from __future__ import annotations

import io
import re

import biotite.structure as struc
import biotite.structure.io.pdb as pdb

# PTM motif definitions: (name, target_residue, regex_pattern, description)
_PTM_MOTIFS = [
    ("N-glycosylation", "N", r"N[^P][ST]", "N-X-S/T sequon (X != P)"),
    ("Phosphorylation (S)", "S", r"[RK].S", "Kinase consensus R/K-X-S"),
    ("Phosphorylation (T)", "T", r"[RK].T", "Kinase consensus R/K-X-T"),
    ("Phosphorylation (Y)", "Y", r"[ED]..Y", "Acidophilic kinase E/D-X-X-Y"),
    ("Myristoylation", "G", r"^MG", "N-terminal G after Met cleavage"),
    ("SUMOylation", "K", r"[VILMFP]K[ED]E", "ψ-K-x-E consensus"),
    ("Ubiquitination", "K", None, "Any lysine (candidate)"),
    ("Disulfide bond", "C", None, "Any cysteine (candidate)"),
    ("O-GlcNAc", "S", None, "Ser in disordered regions"),
    ("Palmitoylation", "C", None, "Cysteine near membrane"),
]

# 3-letter to 1-letter amino acid mapping
_AA_3TO1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}


def predict_ptm_sites(
    pdb_content: str,
    chain: str | None = None,
) -> dict:
    """Predict potential PTM sites from sequence motifs and structure.

    Returns dict with predicted sites, their accessibility, and summary.
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

    # Extract sequence
    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    res_names = [str(r).strip() for r in ca_atoms.res_name]
    sequence = "".join(_AA_3TO1.get(rn, "X") for rn in res_names)

    if len(sequence) < 5:
        return _empty_result()

    # Compute SASA for accessibility assessment
    sasa_values = struc.sasa(chain_struct, vdw_radii="ProtOr")
    sasa_per_residue: dict[int, float] = {}
    for i, atom in enumerate(chain_struct):
        rid = int(atom.res_id)
        if rid not in sasa_per_residue:
            sasa_per_residue[rid] = 0.0
        sasa_per_residue[rid] += sasa_values[i]

    # Build residue index → residue ID mapping
    idx_to_rid = dict(enumerate(res_ids))
    rid_to_aa = dict(zip(res_ids, sequence))

    # Scan for PTM motifs
    predicted_sites: list[dict] = []

    for ptm_name, target_aa, pattern, description in _PTM_MOTIFS:
        if pattern:
            for match in re.finditer(pattern, sequence):
                # Find the target residue position within the match
                match_start = match.start()
                match_seq = match.group()

                for offset, aa in enumerate(match_seq):
                    if aa == target_aa:
                        seq_pos = match_start + offset
                        if seq_pos in idx_to_rid:
                            rid = idx_to_rid[seq_pos]
                            sasa_val = sasa_per_residue.get(rid, 0)
                            accessible = sasa_val > 20.0

                            predicted_sites.append({
                                "residue_id": rid,
                                "amino_acid": target_aa,
                                "ptm_type": ptm_name,
                                "motif": match_seq,
                                "description": description,
                                "sasa": round(sasa_val, 1),
                                "accessible": accessible,
                                "confidence": "high" if accessible else "low",
                            })
                        break  # Only first target residue per match
        else:
            # No pattern — scan all residues of target type
            if target_aa == "K" and ptm_name == "Ubiquitination":
                # Only surface lysines
                for idx, aa in enumerate(sequence):
                    if aa == "K" and idx in idx_to_rid:
                        rid = idx_to_rid[idx]
                        sasa_val = sasa_per_residue.get(rid, 0)
                        if sasa_val > 30.0:  # Must be exposed
                            predicted_sites.append({
                                "residue_id": rid,
                                "amino_acid": "K",
                                "ptm_type": "Ubiquitination",
                                "motif": f"K{rid}",
                                "description": "Exposed lysine",
                                "sasa": round(sasa_val, 1),
                                "accessible": True,
                                "confidence": "medium",
                            })
            elif target_aa == "C" and ptm_name == "Disulfide bond":
                # Find cysteine pairs within 6 Å (Sγ distance)
                cys_atoms = []
                for i in range(len(chain_struct)):
                    atom = chain_struct[i]
                    if str(atom.atom_name).strip() == "SG" and str(atom.res_name).strip() == "CYS":
                        cys_atoms.append((int(atom.res_id), chain_struct.coord[i]))

                for i, (rid1, coord1) in enumerate(cys_atoms):
                    for rid2, coord2 in cys_atoms[i + 1:]:
                        import numpy as np
                        dist = float(np.linalg.norm(coord1 - coord2))
                        if dist < 6.0:
                            predicted_sites.append({
                                "residue_id": rid1,
                                "amino_acid": "C",
                                "ptm_type": "Disulfide bond",
                                "motif": f"C{rid1}-C{rid2}",
                                "description": f"Cys pair at {dist:.1f} Å",
                                "sasa": round(sasa_per_residue.get(rid1, 0), 1),
                                "accessible": False,
                                "confidence": "high" if dist < 3.0 else "medium",
                                "partner_residue": rid2,
                                "distance": round(dist, 1),
                            })

    # Deduplicate by (residue_id, ptm_type)
    seen = set()
    unique_sites = []
    for site in predicted_sites:
        key = (site["residue_id"], site["ptm_type"])
        if key not in seen:
            seen.add(key)
            unique_sites.append(site)

    # Sort by residue position
    unique_sites.sort(key=lambda s: s["residue_id"])

    # Per-residue PTM map for coloring
    ptm_per_residue: dict[int, list[str]] = {}
    for site in unique_sites:
        rid = site["residue_id"]
        if rid not in ptm_per_residue:
            ptm_per_residue[rid] = []
        ptm_per_residue[rid].append(site["ptm_type"])

    # Summary by type
    type_counts: dict[str, int] = {}
    for site in unique_sites:
        t = site["ptm_type"]
        type_counts[t] = type_counts.get(t, 0) + 1

    return {
        "predicted_sites": unique_sites,
        "ptm_per_residue": ptm_per_residue,
        "type_counts": type_counts,
        "n_sites": len(unique_sites),
        "accessible_sites": [s for s in unique_sites if s["accessible"]],
        "summary": {
            "total_predicted": len(unique_sites),
            "n_accessible": sum(1 for s in unique_sites if s["accessible"]),
            "n_high_confidence": sum(1 for s in unique_sites if s["confidence"] == "high"),
            "types_found": list(type_counts.keys()),
            "type_counts": type_counts,
        },
    }


def fetch_uniprot_ptms(uniprot_id: str) -> dict:
    """Fetch experimentally validated PTMs from UniProt.

    Returns dict with known modifications mapped to residue positions.
    """
    import httpx

    try:
        resp = httpx.get(
            f"https://rest.uniprot.org/uniprotkb/{uniprot_id}",
            params={"format": "json"},
            headers={"Accept": "application/json"},
            timeout=httpx.Timeout(15.0, connect=10.0),
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return {"error": f"UniProt PTM fetch failed: {e}", "ptms": []}

    ptms: list[dict] = []
    features = data.get("features", [])

    ptm_types = {
        "Modified residue", "Glycosylation", "Lipidation",
        "Cross-link", "Disulfide bond",
    }

    for feat in features:
        if feat.get("type") in ptm_types:
            location = feat.get("location", {})
            start = location.get("start", {}).get("value")
            end = location.get("end", {}).get("value")
            desc = feat.get("description", "")

            ptms.append({
                "type": feat["type"],
                "start": start,
                "end": end,
                "description": desc,
                "evidence": _extract_evidence(feat),
            })

    return {
        "uniprot_id": uniprot_id,
        "ptms": ptms,
        "n_ptms": len(ptms),
    }


def _extract_evidence(feature: dict) -> str:
    """Extract evidence type from UniProt feature."""
    evidences = feature.get("evidences", [])
    if evidences:
        codes = set()
        for ev in evidences:
            code = ev.get("code", "")
            if code:
                codes.add(code)
        if codes:
            return ", ".join(sorted(codes))
    return "predicted"


def _empty_result() -> dict:
    return {
        "predicted_sites": [],
        "ptm_per_residue": {},
        "type_counts": {},
        "n_sites": 0,
        "accessible_sites": [],
        "summary": {
            "total_predicted": 0,
            "n_accessible": 0,
            "n_high_confidence": 0,
            "types_found": [],
            "type_counts": {},
        },
    }
