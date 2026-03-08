"""Structural property analysis from PDB coordinates using biotite.

Computes insights a scientist can't see from sequence or pLDDT alone:
SASA (buried vs exposed), secondary structure, 3D distances between
mutations, variants, drug binding pockets, contact maps, packing
density, Ramachandran angles, and residue interaction network centrality.
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import numpy as np

# Max residues for O(n²) analyses (contact map, packing density, network)
_MAX_RESIDUES_PAIRWISE = 2000


def analyze_structure(
    pdb_content: str,
    mutation_pos: int | None = None,
    variant_positions: dict[int, list[str]] | None = None,
    pocket_residues: list[int] | None = None,
    first_chain: str | None = None,
) -> dict:
    """Compute structural properties from PDB coordinates.

    Returns a dict with per-residue SASA, secondary structure, and
    spatial distance metrics for mutations, variants, and binding pockets.
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    # Filter to first chain if specified
    if first_chain:
        chain_mask = structure.chain_id == first_chain
        chain_struct = structure[chain_mask]
    else:
        chains = list(set(structure.chain_id))
        chains.sort()
        first_chain = chains[0] if chains else "A"
        chain_mask = structure.chain_id == first_chain
        chain_struct = structure[chain_mask]

    # CA atoms for per-residue analysis
    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]

    result: dict = {
        "residue_ids": res_ids,
        "chain": first_chain,
    }

    # ── 1. Solvent Accessible Surface Area ──
    sasa_values = struc.sasa(chain_struct, vdw_radii="ProtOr")
    # Aggregate SASA per residue
    sasa_per_residue: dict[int, float] = {}
    for i, atom in enumerate(chain_struct):
        rid = int(atom.res_id)
        if rid not in sasa_per_residue:
            sasa_per_residue[rid] = 0.0
        sasa_per_residue[rid] += sasa_values[i]

    result["sasa_per_residue"] = sasa_per_residue

    # Classify buried vs exposed (threshold: 25 Å² relative SASA)
    result["buried_residues"] = [r for r, s in sasa_per_residue.items() if s < 25.0]
    result["exposed_residues"] = [r for r, s in sasa_per_residue.items() if s >= 25.0]

    # ── 2. Secondary Structure ──
    sse = struc.annotate_sse(chain_struct)
    # Map residue IDs to SSE (one per residue)
    sse_per_residue: dict[int, str] = {}
    seen_residues: set[int] = set()
    sse_idx = 0
    for atom in chain_struct:
        rid = int(atom.res_id)
        if rid not in seen_residues:
            seen_residues.add(rid)
            if sse_idx < len(sse):
                sse_per_residue[rid] = sse[sse_idx]
                sse_idx += 1
    result["sse_per_residue"] = sse_per_residue

    # Count secondary structure elements
    sse_counts = {"a": 0, "b": 0, "c": 0}
    for s in sse_per_residue.values():
        key = str(s).strip()
        if key in ("a", "b", "c"):
            sse_counts[key] += 1
        else:
            sse_counts["c"] += 1  # treat unknown as coil
    result["sse_counts"] = sse_counts

    # ── 3. Mutation site analysis ──
    if mutation_pos is not None and mutation_pos in sasa_per_residue:
        mut_sasa = float(sasa_per_residue[mutation_pos])
        result["mutation_sasa"] = mut_sasa
        result["mutation_is_buried"] = bool(mut_sasa < 25.0)
        result["mutation_sse"] = str(sse_per_residue.get(mutation_pos, "c"))

        # Build CA coordinate lookup
        ca_coords = {}
        for i, rid in enumerate(res_ids):
            ca_coords[rid] = ca_atoms.coord[i]

        # ── 4. Mutation-to-binding-pocket distance ──
        if pocket_residues and mutation_pos in ca_coords:
            mut_coord = ca_coords[mutation_pos]
            pocket_dists = []
            for pr in pocket_residues:
                if pr in ca_coords:
                    d = np.linalg.norm(mut_coord - ca_coords[pr])
                    pocket_dists.append((pr, float(d)))
            if pocket_dists:
                pocket_dists.sort(key=lambda x: x[1])
                result["mutation_to_pocket_min_distance"] = pocket_dists[0][1]
                result["mutation_to_pocket_nearest_residue"] = pocket_dists[0][0]
                result["mutation_in_pocket"] = pocket_dists[0][1] < 8.0
                result["mutation_to_pocket_distances"] = pocket_dists[:5]

        # ── 5. Mutation-to-pathogenic-variant 3D distances ──
        if variant_positions and mutation_pos in ca_coords:
            mut_coord = ca_coords[mutation_pos]
            var_dists = []
            for vpos, vnames in variant_positions.items():
                if vpos in ca_coords and vpos != mutation_pos:
                    d = float(np.linalg.norm(mut_coord - ca_coords[vpos]))
                    name_str = ", ".join(vnames) if isinstance(vnames, list) else str(vnames)
                    var_dists.append({
                        "position": vpos,
                        "name": name_str,
                        "distance_3d": round(d, 1),
                        "distance_seq": abs(vpos - mutation_pos),
                    })
            var_dists.sort(key=lambda x: x["distance_3d"])
            result["mutation_to_variant_distances"] = var_dists

    else:
        # Build CA coords even without mutation for cluster analysis
        ca_coords = {}
        for i, rid in enumerate(res_ids):
            ca_coords[rid] = ca_atoms.coord[i]

    # ── 6. 3D spatial clustering of pathogenic variants ──
    if variant_positions:
        var_pos_list = [p for p in variant_positions if p in ca_coords]
        if len(var_pos_list) >= 2:
            # Pairwise distances between all pathogenic variants
            pairwise = []
            for i, p1 in enumerate(var_pos_list):
                for p2 in var_pos_list[i + 1:]:
                    d3d = float(np.linalg.norm(ca_coords[p1] - ca_coords[p2]))
                    d_seq = abs(p1 - p2)
                    n1 = variant_positions[p1]
                    n2 = variant_positions[p2]
                    name1 = ", ".join(n1) if isinstance(n1, list) else str(n1)
                    name2 = ", ".join(n2) if isinstance(n2, list) else str(n2)
                    pairwise.append({
                        "pos1": p1, "pos2": p2,
                        "name1": name1, "name2": name2,
                        "distance_3d": round(d3d, 1),
                        "distance_seq": d_seq,
                        "spatially_close": d3d < 10.0,
                        "seq_distant_but_3d_close": d_seq > 20 and d3d < 10.0,
                    })
            pairwise.sort(key=lambda x: x["distance_3d"])
            result["variant_pairwise_distances"] = pairwise

            # Find clusters (variants within 10Å of each other)
            close_pairs = [p for p in pairwise if p["spatially_close"]]
            hidden_clusters = [p for p in pairwise if p["seq_distant_but_3d_close"]]
            result["variant_3d_clusters"] = close_pairs
            result["hidden_spatial_clusters"] = hidden_clusters

    # ── 7. Contact Map (Cα–Cα distance matrix) ──
    n_res = len(res_ids)
    if 3 <= n_res <= _MAX_RESIDUES_PAIRWISE:
        valid_res = [r for r in res_ids if r in ca_coords]
        n_valid = len(valid_res)
        if n_valid >= 3:
            ca_array = np.array([ca_coords[r] for r in valid_res])
            dist_matrix = np.sqrt(
                ((ca_array[:, None, :] - ca_array[None, :, :]) ** 2).sum(axis=-1)
            )
            result["contact_map"] = dist_matrix
            result["contact_map_residues"] = valid_res

            # Contacts per residue (< 8 Å, excluding ±1 sequential neighbours)
            contacts_per_res: dict[int, int] = {}
            for i in range(n_valid):
                mask = (dist_matrix[i] < 8.0)
                # Exclude self and ±1 sequential neighbours
                for j in range(n_valid):
                    if abs(i - j) <= 1:
                        mask[j] = False
                contacts_per_res[valid_res[i]] = int(mask.sum())
            result["contacts_per_residue"] = contacts_per_res

    # ── 8. Local Packing Density (Cβ neighbours within 12 Å) ──
    if 3 <= n_res <= _MAX_RESIDUES_PAIRWISE:
        cb_mask = chain_struct.atom_name == "CB"
        cb_atoms = chain_struct[cb_mask]
        cb_coords: dict[int, np.ndarray] = {}
        for i in range(len(cb_atoms)):
            rid = int(cb_atoms.res_id[i])
            cb_coords[rid] = cb_atoms.coord[i]
        # Glycine fallback: use Cα when no Cβ exists
        for rid in res_ids:
            if rid not in cb_coords and rid in ca_coords:
                cb_coords[rid] = ca_coords[rid]

        cb_res = sorted(r for r in cb_coords if r in set(res_ids))
        if len(cb_res) >= 3:
            cb_array = np.array([cb_coords[r] for r in cb_res])
            cb_dist = np.sqrt(
                ((cb_array[:, None, :] - cb_array[None, :, :]) ** 2).sum(axis=-1)
            )
            packing: dict[int, int] = {}
            for i, rid in enumerate(cb_res):
                mask = (cb_dist[i] < 12.0)
                mask[i] = False  # exclude self
                packing[rid] = int(mask.sum())
            result["packing_density"] = packing

    # ── 9. Ramachandran (φ/ψ dihedral angles) ──
    try:
        phi, psi, _omega = struc.dihedral_backbone(chain_struct)
        # Map to residue IDs (one entry per residue)
        rama_data: list[dict] = []
        seen_rama: set[int] = set()
        r_idx = 0
        for atom in chain_struct:
            rid = int(atom.res_id)
            if rid not in seen_rama:
                seen_rama.add(rid)
                if r_idx < len(phi) and r_idx < len(psi):
                    phi_val = float(phi[r_idx])
                    psi_val = float(psi[r_idx])
                    if not (np.isnan(phi_val) or np.isnan(psi_val)):
                        rama_data.append({
                            "residue": rid,
                            "phi": round(np.degrees(phi_val), 1),
                            "psi": round(np.degrees(psi_val), 1),
                        })
                r_idx += 1
        if rama_data:
            result["ramachandran"] = rama_data
            # Classify into regions
            n_favored = sum(1 for r in rama_data if _rama_favored(r["phi"], r["psi"]))
            n_allowed = sum(1 for r in rama_data if _rama_allowed(r["phi"], r["psi"]))
            n_outlier = len(rama_data) - n_favored - n_allowed
            result["rama_stats"] = {
                "total": len(rama_data),
                "favored": n_favored,
                "allowed": n_allowed,
                "outlier": n_outlier,
                "favored_pct": round(100 * n_favored / len(rama_data), 1),
            }
    except Exception:
        pass  # dihedral_backbone can fail on incomplete backbone

    # ── 10. Residue Interaction Network (betweenness centrality) ──
    contact_res = result.get("contact_map_residues", [])
    contact_mat = result.get("contact_map")
    if contact_mat is not None and len(contact_res) >= 5:
        try:
            import networkx as nx

            G = nx.Graph()
            n_c = len(contact_res)
            for r in contact_res:
                G.add_node(r)
            for i in range(n_c):
                for j in range(i + 1, n_c):
                    if abs(i - j) > 1 and contact_mat[i, j] < 8.0:
                        G.add_edge(contact_res[i], contact_res[j],
                                   weight=float(contact_mat[i, j]))

            if G.number_of_edges() > 0:
                # Approximate for large proteins
                k_sample = min(n_c, 200) if n_c > 300 else None
                centrality = nx.betweenness_centrality(G, k=k_sample)
                result["network_centrality"] = {
                    int(k): round(v, 5) for k, v in centrality.items()
                }
                sorted_c = sorted(centrality.items(), key=lambda x: x[1], reverse=True)
                result["hub_residues"] = [
                    {"residue": int(r), "centrality": round(c, 5)}
                    for r, c in sorted_c[:15] if c > 0
                ]
                result["network_edges"] = G.number_of_edges()
                result["network_nodes"] = G.number_of_nodes()

                # Check if mutation or variants hit hub residues
                if mutation_pos is not None:
                    mut_cent = centrality.get(mutation_pos, 0.0)
                    result["mutation_centrality"] = round(mut_cent, 5)
                    # Percentile rank
                    all_cent = list(centrality.values())
                    result["mutation_centrality_percentile"] = round(
                        100 * sum(1 for c in all_cent if c <= mut_cent) / len(all_cent), 1
                    )
                if variant_positions:
                    variant_hub_hits = []
                    hub_set = {h["residue"] for h in result.get("hub_residues", [])}
                    for vpos, vnames in variant_positions.items():
                        if vpos in hub_set:
                            name_str = ", ".join(vnames) if isinstance(vnames, list) else str(vnames)
                            variant_hub_hits.append({
                                "position": vpos,
                                "name": name_str,
                                "centrality": centrality.get(vpos, 0.0),
                            })
                    if variant_hub_hits:
                        result["variants_at_hubs"] = variant_hub_hits
        except ImportError:
            pass

    return result


def _rama_favored(phi: float, psi: float) -> bool:
    """Check if phi/psi falls in a Ramachandran favored region."""
    # Right-handed α-helix
    if -160 <= phi <= -20 and -120 <= psi <= 20:
        return True
    # β-sheet (upper-left)
    if -180 <= phi <= -40 and 80 <= psi <= 180:
        return True
    # β-sheet (wrapped to negative ψ)
    if -180 <= phi <= -40 and -180 <= psi <= -120:
        return True
    return False


def _rama_allowed(phi: float, psi: float) -> bool:
    """Check if phi/psi falls in a Ramachandran allowed (but not favored) region."""
    if _rama_favored(phi, psi):
        return False
    # Generous allowed region: most of the left half + left-handed helix
    if -180 <= phi <= 0 and -180 <= psi <= 180:
        return True
    # Left-handed α-helix
    if 20 <= phi <= 120 and -20 <= psi <= 80:
        return True
    return False
