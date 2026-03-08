"""Protein Structure Network (PSN) analysis.

Graph-theoretic analysis of residue contact networks reveals allosteric
hotspots, communication pathways, and functional modules that are invisible
in static structure views. Uses Cα contact graphs with networkx.

Key insights scientists don't normally see:
- Betweenness centrality → allosteric communication bottlenecks
- Community detection (Louvain) → functional modules (often differ from domains)
- Shortest paths → how a mutation propagates to a distant binding site
- Closeness centrality → residues that can quickly reach all others
- Degree centrality → local connectivity hubs
"""
from __future__ import annotations

import io

import biotite.structure as struc
import biotite.structure.io.pdb as pdb
import networkx as nx
import numpy as np


def build_protein_network(
    pdb_content: str,
    chain: str | None = None,
    contact_cutoff: float = 8.0,
    min_seq_sep: int = 2,
) -> dict:
    """Build a residue-level protein structure network and compute graph metrics.

    Parameters
    ----------
    pdb_content : str
        PDB file content.
    chain : str | None
        Chain ID to analyze (default: first chain).
    contact_cutoff : float
        Cα-Cα distance cutoff for edges (default 8 Å).
    min_seq_sep : int
        Minimum sequence separation to form an edge (default 2, excludes i±1).

    Returns
    -------
    dict with:
        - graph_stats: nodes, edges, density, avg_clustering
        - betweenness: per-residue betweenness centrality
        - closeness: per-residue closeness centrality
        - degree: per-residue degree centrality
        - communities: list of community dicts (members, size, centroid)
        - hub_residues: top 15 by betweenness
        - bridge_residues: high betweenness + low degree (bottlenecks)
        - shortest_paths: populated by find_communication_path()
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    if chain:
        chain_struct = structure[structure.chain_id == chain]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_struct = structure[structure.chain_id == chain]

    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    n = len(res_ids)

    if n < 10:
        return _empty_result()

    # Build contact graph
    coords = ca_atoms.coord
    G = nx.Graph()
    for r in res_ids:
        G.add_node(r)

    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) >= min_seq_sep:
                dist = float(np.linalg.norm(coords[i] - coords[j]))
                if dist < contact_cutoff:
                    G.add_edge(res_ids[i], res_ids[j], weight=dist)

    if G.number_of_edges() < 5:
        return _empty_result()

    # Centrality metrics
    k_sample = min(n, 200) if n > 300 else None
    betweenness = nx.betweenness_centrality(G, k=k_sample, weight="weight")
    closeness = nx.closeness_centrality(G, distance="weight")
    degree = nx.degree_centrality(G)

    # Community detection (Louvain)
    communities = _detect_communities(G, res_ids)

    # Hub residues (top 15 by betweenness)
    sorted_bc = sorted(betweenness.items(), key=lambda x: x[1], reverse=True)
    hub_residues = [
        {"residue": int(r), "betweenness": round(c, 5),
         "closeness": round(closeness.get(r, 0), 5),
         "degree": round(degree.get(r, 0), 5)}
        for r, c in sorted_bc[:15] if c > 0
    ]

    # Bridge residues: high betweenness but LOW degree → bottleneck nodes
    bc_vals = list(betweenness.values())
    bc_threshold = np.percentile(bc_vals, 85) if bc_vals else 0
    deg_vals = list(degree.values())
    deg_median = np.median(deg_vals) if deg_vals else 0.5

    bridge_residues = [
        {"residue": int(r), "betweenness": round(betweenness[r], 5),
         "degree": round(degree[r], 5)}
        for r in res_ids
        if betweenness.get(r, 0) > bc_threshold and degree.get(r, 0) < deg_median
    ]

    return {
        "residue_ids": res_ids,
        "graph_stats": {
            "nodes": G.number_of_nodes(),
            "edges": G.number_of_edges(),
            "density": round(nx.density(G), 4),
            "avg_clustering": round(nx.average_clustering(G), 4),
            "connected_components": nx.number_connected_components(G),
        },
        "betweenness": {int(k): round(v, 5) for k, v in betweenness.items()},
        "closeness": {int(k): round(v, 5) for k, v in closeness.items()},
        "degree": {int(k): round(v, 5) for k, v in degree.items()},
        "communities": communities,
        "hub_residues": hub_residues,
        "bridge_residues": bridge_residues,
        "contact_cutoff": contact_cutoff,
        "summary": {
            "n_communities": len(communities),
            "n_hubs": len(hub_residues),
            "n_bridges": len(bridge_residues),
            "avg_betweenness": round(float(np.mean(bc_vals)), 5) if bc_vals else 0,
            "max_betweenness": round(float(np.max(bc_vals)), 5) if bc_vals else 0,
        },
    }


def find_communication_path(
    pdb_content: str,
    source_residue: int,
    target_residue: int,
    chain: str | None = None,
    contact_cutoff: float = 8.0,
) -> dict:
    """Find the shortest structural communication path between two residues.

    This reveals how a mutation at one site could propagate to affect
    a distant functional site through the protein's contact network.
    """
    pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
    structure = pdb_file.get_structure(model=1)

    if chain:
        chain_struct = structure[structure.chain_id == chain]
    else:
        chains = sorted(set(structure.chain_id))
        chain = chains[0] if chains else "A"
        chain_struct = structure[structure.chain_id == chain]

    ca_mask = chain_struct.atom_name == "CA"
    ca_atoms = chain_struct[ca_mask]
    res_ids = [int(r) for r in ca_atoms.res_id]
    coords = ca_atoms.coord
    n = len(res_ids)

    G = nx.Graph()
    for r in res_ids:
        G.add_node(r)
    for i in range(n):
        for j in range(i + 1, n):
            if abs(i - j) >= 2:
                dist = float(np.linalg.norm(coords[i] - coords[j]))
                if dist < contact_cutoff:
                    G.add_edge(res_ids[i], res_ids[j], weight=dist)

    if source_residue not in G or target_residue not in G:
        return {"error": "Source or target residue not in network",
                "path": [], "path_length": -1}

    try:
        path = nx.shortest_path(G, source_residue, target_residue, weight="weight")
        path_length = nx.shortest_path_length(G, source_residue, target_residue, weight="weight")

        # Compute per-step distances
        steps = []
        for i in range(len(path) - 1):
            edge_data = G.edges[path[i], path[i + 1]]
            steps.append({
                "from": path[i],
                "to": path[i + 1],
                "distance": round(edge_data["weight"], 1),
            })

        # Euclidean (direct) distance for comparison
        src_idx = res_ids.index(source_residue)
        tgt_idx = res_ids.index(target_residue)
        direct_dist = float(np.linalg.norm(coords[src_idx] - coords[tgt_idx]))

        return {
            "source": source_residue,
            "target": target_residue,
            "path": path,
            "path_length": round(float(path_length), 1),
            "n_hops": len(path) - 1,
            "steps": steps,
            "direct_distance": round(direct_dist, 1),
            "path_to_direct_ratio": round(float(path_length) / direct_dist, 2) if direct_dist > 0 else 0,
            "seq_distance": abs(source_residue - target_residue),
        }
    except nx.NetworkXNoPath:
        return {"error": "No path between residues",
                "path": [], "path_length": -1}


def _detect_communities(G: nx.Graph, res_ids: list[int]) -> list[dict]:
    """Detect structural communities using greedy modularity optimization."""
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        raw_communities = greedy_modularity_communities(G, weight="weight")
    except Exception:
        return []

    communities = []
    for idx, members in enumerate(raw_communities):
        member_list = sorted(int(m) for m in members)
        if len(member_list) < 3:
            continue
        communities.append({
            "id": idx,
            "members": member_list,
            "size": len(member_list),
            "start": member_list[0],
            "end": member_list[-1],
            "contiguous": _is_mostly_contiguous(member_list),
        })

    communities.sort(key=lambda c: c["start"])
    for i, c in enumerate(communities):
        c["id"] = i

    return communities


def _is_mostly_contiguous(residues: list[int], gap_tolerance: float = 0.2) -> bool:
    """Check if a community is mostly contiguous in sequence."""
    if len(residues) < 2:
        return True
    span = residues[-1] - residues[0] + 1
    coverage = len(residues) / span
    return coverage > (1 - gap_tolerance)


def _empty_result() -> dict:
    return {
        "residue_ids": [],
        "graph_stats": {},
        "betweenness": {},
        "closeness": {},
        "degree": {},
        "communities": [],
        "hub_residues": [],
        "bridge_residues": [],
        "contact_cutoff": 8.0,
        "summary": {},
    }
