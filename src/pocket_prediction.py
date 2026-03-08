"""Binding pocket prediction via P2Rank (Java) or SASA+contact heuristic fallback.

P2Rank uses ML to predict ligand-binding pockets from structure.
If P2Rank is not installed, falls back to a heuristic using SASA and
contact density to approximate pocket-like regions.
"""
from __future__ import annotations

import csv
import subprocess
import tempfile
from pathlib import Path


def is_p2rank_available() -> bool:
    """Check if P2Rank binary exists and Java is on PATH."""
    p2rank_path = Path(__file__).parent.parent / "tools" / "p2rank" / "prank"
    if not p2rank_path.exists():
        return False
    try:
        subprocess.run(
            ["java", "-version"], capture_output=True, timeout=5
        )
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def predict_pockets(pdb_content: str) -> dict:
    """Predict binding pockets. Uses P2Rank if available, else SASA heuristic."""
    if is_p2rank_available():
        return _predict_p2rank(pdb_content)
    return _fallback_pocket_heuristic(pdb_content)


def _predict_p2rank(pdb_content: str) -> dict:
    """Run P2Rank ML pocket prediction."""
    p2rank_path = Path(__file__).parent.parent / "tools" / "p2rank" / "prank"

    with tempfile.TemporaryDirectory() as tmpdir:
        pdb_file = Path(tmpdir) / "input.pdb"
        pdb_file.write_text(pdb_content)
        out_dir = Path(tmpdir) / "output"

        result = subprocess.run(
            [str(p2rank_path), "predict", "-f", str(pdb_file), "-o", str(out_dir)],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            return _fallback_pocket_heuristic(pdb_content)

        # Parse predictions CSV
        pred_files = list(out_dir.rglob("*_predictions.csv"))
        res_files = list(out_dir.rglob("*_residues.csv"))

        pockets = []
        if pred_files:
            with open(pred_files[0]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pockets.append({
                        "rank": int(row.get("rank", 0)),
                        "score": float(row.get("score", 0)),
                        "probability": float(row.get("probability", 0)),
                        "residues": _parse_residue_ids(row.get("residue_ids", "")),
                    })

        residue_scores = {}
        if res_files:
            with open(res_files[0]) as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        res_id = int(row.get("residue_label", "").strip())
                        score = float(row.get("score", 0))
                        residue_scores[res_id] = score
                    except (ValueError, TypeError):
                        pass

        top_residues = pockets[0]["residues"] if pockets else []
        return {
            "pockets": pockets,
            "residue_pocket_scores": residue_scores,
            "top_pocket_residues": top_residues,
            "method": "p2rank",
        }


def _fallback_pocket_heuristic(pdb_content: str) -> dict:
    """Approximate pocket prediction using SASA + contact density.

    Pocket-like residues are partially buried (10 < SASA < 50 Å²)
    with high contact density. No external dependency required.
    """
    import io

    import biotite.structure as struc
    import biotite.structure.io.pdb as pdb
    import numpy as np

    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    struct_full = pdb_file.get_structure(model=1)

    # Filter to first chain protein atoms
    protein = struct_full[struc.filter_amino_acids(struct_full)]
    if len(protein) == 0:
        return {"pockets": [], "residue_pocket_scores": {}, "top_pocket_residues": [], "method": "heuristic"}

    # Compute SASA
    sasa = struc.sasa(protein, vdw_radii="ProtOr")

    # Get Cα atoms for contact counting
    ca_mask = protein.atom_name == "CA"
    ca_atoms = protein[ca_mask]
    ca_coords = ca_atoms.coord

    if len(ca_coords) < 10:
        return {"pockets": [], "residue_pocket_scores": {}, "top_pocket_residues": [], "method": "heuristic"}

    # Distance matrix for contacts
    from scipy.spatial.distance import cdist
    dist_matrix = cdist(ca_coords, ca_coords)

    # Per-residue metrics
    res_ids = ca_atoms.res_id
    unique_res = sorted(set(res_ids))

    # Aggregate SASA per residue
    res_sasa = {}
    for res_id in unique_res:
        mask = protein.res_id == res_id
        res_sasa[int(res_id)] = float(np.sum(sasa[mask]))

    # Contact density per Cα
    contact_counts = {}
    for i, res_id in enumerate(res_ids):
        contacts = np.sum((dist_matrix[i] < 8.0) & (dist_matrix[i] > 0))
        contact_counts[int(res_id)] = int(contacts)

    # Score: pocket-like = partially buried + high contacts
    pocket_scores = {}
    for res_id in unique_res:
        rid = int(res_id)
        s = res_sasa.get(rid, 100)
        c = contact_counts.get(rid, 0)

        # Partially buried (10-50 Å²) gets higher score
        if 10 < s < 50:
            burial_score = 1.0 - abs(s - 30) / 20  # Peak at 30 Å²
        elif s <= 10:
            burial_score = 0.3  # Too buried — interior, not pocket
        else:
            burial_score = max(0, 1.0 - (s - 50) / 50)  # Exposed — low score

        # Normalize contacts (typical range 5-25)
        contact_score = min(c / 20.0, 1.0)

        pocket_scores[rid] = round(burial_score * 0.6 + contact_score * 0.4, 3)

    # Cluster high-scoring residues into pockets
    sorted_res = sorted(pocket_scores.items(), key=lambda x: -x[1])
    threshold = 0.5
    pocket_residues = [r for r, s in sorted_res if s > threshold]

    # Simple sequential clustering
    pockets = []
    if pocket_residues:
        current_pocket = [pocket_residues[0]]
        for r in pocket_residues[1:]:
            if r - current_pocket[-1] <= 5:
                current_pocket.append(r)
            else:
                if len(current_pocket) >= 3:
                    avg_score = sum(pocket_scores[x] for x in current_pocket) / len(current_pocket)
                    pockets.append({
                        "rank": len(pockets) + 1,
                        "score": round(avg_score * 10, 1),
                        "probability": round(avg_score, 2),
                        "residues": current_pocket,
                    })
                current_pocket = [r]
        if len(current_pocket) >= 3:
            avg_score = sum(pocket_scores[x] for x in current_pocket) / len(current_pocket)
            pockets.append({
                "rank": len(pockets) + 1,
                "score": round(avg_score * 10, 1),
                "probability": round(avg_score, 2),
                "residues": current_pocket,
            })

    # Sort by score descending and re-rank
    pockets.sort(key=lambda p: -p["score"])
    for i, p in enumerate(pockets):
        p["rank"] = i + 1

    top_residues = pockets[0]["residues"] if pockets else []
    return {
        "pockets": pockets[:5],
        "residue_pocket_scores": pocket_scores,
        "top_pocket_residues": top_residues,
        "method": "heuristic",
    }


def _parse_residue_ids(residue_str: str) -> list[int]:
    """Parse P2Rank residue ID string like '45 47 48 89'."""
    ids = []
    for part in residue_str.replace(",", " ").split():
        try:
            ids.append(int(part.strip()))
        except ValueError:
            pass
    return ids
