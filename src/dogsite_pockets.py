"""Binding pocket prediction via DoGSiteScorer (proteins.plus REST API).

DoGSiteScorer uses machine learning to predict ligand-binding pockets
with druggability scoring. Falls back to local heuristic if API unavailable.
"""
from __future__ import annotations

import time

import httpx
import streamlit as st

_API_BASE = "https://proteins.plus/api/v2"


@st.cache_data(ttl=3600, show_spinner=False)
def predict_pockets_dogsite(pdb_id: str) -> dict | None:
    """Predict binding pockets using DoGSiteScorer via proteins.plus API.

    Parameters
    ----------
    pdb_id : 4-letter PDB code (e.g., "1M17")

    Returns
    -------
    Dict with pockets, residue scores, and druggability, or None if failed.
    """
    if not pdb_id or len(pdb_id) < 4:
        return None

    try:
        client = httpx.Client(timeout=30.0)

        # Step 1: Submit job
        resp = client.post(
            f"{_API_BASE}/dogsite",
            json={"pdbCode": pdb_id.upper()[:4]},
            headers={"Accept": "application/json"},
        )

        if resp.status_code not in (200, 201, 202):
            return None

        job = resp.json()
        job_id = job.get("id") or job.get("job_id")
        result_url = job.get("result_url") or job.get("url")

        if not job_id and not result_url:
            # Maybe result is immediate
            return _parse_dogsite_result(job)

        # Step 2: Poll for results (max 60s)
        poll_url = result_url or f"{_API_BASE}/dogsite/{job_id}"
        for _ in range(12):
            time.sleep(5)
            poll_resp = client.get(poll_url, headers={"Accept": "application/json"})
            if poll_resp.status_code == 200:
                data = poll_resp.json()
                status = data.get("status", "").lower()
                if status in ("completed", "finished", "done") or "pockets" in data:
                    return _parse_dogsite_result(data)
                if status in ("failed", "error"):
                    return None
            elif poll_resp.status_code == 202:
                continue  # Still processing
            else:
                return None

        return None  # Timeout

    except Exception:
        return None


def _parse_dogsite_result(data: dict) -> dict | None:
    """Parse DoGSiteScorer API response into our standard pocket format."""
    pockets = []
    residue_scores: dict[int, float] = {}

    # DoGSiteScorer returns pockets with residues, volume, druggability
    raw_pockets = data.get("pockets", data.get("results", []))
    if isinstance(raw_pockets, dict):
        raw_pockets = raw_pockets.get("pockets", [])

    if not raw_pockets:
        return None

    for i, pocket in enumerate(raw_pockets):
        if not isinstance(pocket, dict):
            continue

        residues = pocket.get("residues", pocket.get("residue_ids", []))
        if isinstance(residues, str):
            residues = [int(r.strip()) for r in residues.split(",") if r.strip().isdigit()]

        score = pocket.get("druggability_score", pocket.get("score", 0))
        volume = pocket.get("volume", 0)
        surface = pocket.get("surface_area", pocket.get("surface", 0))

        pockets.append({
            "rank": i + 1,
            "score": round(float(score) * 10 if float(score) <= 1 else float(score), 1),
            "probability": round(float(score), 3) if float(score) <= 1 else round(float(score) / 10, 3),
            "residues": [int(r) for r in residues][:20],
            "volume": round(float(volume), 1) if volume else None,
            "surface_area": round(float(surface), 1) if surface else None,
            "druggability": _druggability_label(float(score)),
        })

        # Per-residue pocket membership score
        for r in residues:
            rid = int(r)
            residue_scores[rid] = max(residue_scores.get(rid, 0), float(score))

    # Sort by score descending
    pockets.sort(key=lambda p: -p["score"])
    for i, p in enumerate(pockets):
        p["rank"] = i + 1

    top_residues = pockets[0]["residues"] if pockets else []

    return {
        "pockets": pockets[:5],
        "residue_pocket_scores": residue_scores,
        "top_pocket_residues": top_residues,
        "method": "dogsite",
        "n_pockets": len(pockets),
    }


def _druggability_label(score: float) -> str:
    """Convert druggability score to label."""
    if score > 0.8:
        return "druggable"
    if score > 0.5:
        return "intermediate"
    return "undruggable"


@st.cache_data(ttl=3600, show_spinner=False)
def predict_pockets_with_fallback(
    pdb_content: str,
    pdb_id: str | None = None,
) -> dict:
    """Try DoGSiteScorer first, fall back to local heuristic.

    Parameters
    ----------
    pdb_content : PDB string content
    pdb_id : Optional PDB code for DoGSiteScorer API

    Returns
    -------
    Standard pocket prediction dict.
    """
    # Try DoGSiteScorer if we have a PDB ID
    if pdb_id and len(pdb_id) >= 4:
        result = predict_pockets_dogsite(pdb_id)
        if result:
            return result

    # Fallback to local heuristic
    from src.pocket_prediction import predict_pockets
    return predict_pockets(pdb_content)
