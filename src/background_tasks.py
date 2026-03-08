"""Background task functions — sync wrappers for long-running operations.

These functions are designed to run in background threads via task_manager.
They must NOT call any st.* functions (no session state, no UI).
They return plain dicts that the notification poller writes into session state.
"""
from __future__ import annotations

import asyncio


def _get_event_loop():
    """Get or create an event loop for this thread."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


# ── Structure Prediction ─────────────────────────────────────────────────────


def run_prediction_tamarind(
    sequence: str,
    protein_name: str,
    mutation: str | None,
    predict_affinity: bool = True,
    num_recycles: int = 3,
    use_msa: bool = True,
) -> dict:
    """Run Boltz-2 prediction via Tamarind Bio API (sync wrapper).

    Returns dict with keys: pdb, confidence, affinity, source.
    """
    from src.tamarind_client import download_results, poll_job, submit_boltz2_job

    job_name = f"luminous_{protein_name}_{mutation or 'wt'}"
    loop = _get_event_loop()

    async def _run():
        await submit_boltz2_job(
            sequence, job_name,
            predict_affinity=predict_affinity,
            num_recycling_steps=num_recycles,
            use_msa=use_msa,
        )
        await poll_job(job_name)
        return await download_results(job_name)

    result = loop.run_until_complete(_run())

    return {
        "pdb": result.get("pdb", result.get("structure", "")),
        "confidence": result.get("confidence", {}),
        "affinity": result.get("affinity"),
        "source": "tamarind",
    }


def run_prediction_modal(
    sequence: str,
    protein_name: str,
    mutation: str | None,
    predict_affinity: bool = True,
) -> dict:
    """Run Boltz-2 prediction via Modal H100 GPU (sync wrapper).

    Returns dict with keys: pdb, confidence, affinity, source.
    """
    from src.modal_client import run_modal_prediction

    job_name = f"luminous_{protein_name}_{mutation or 'wt'}"
    pdb, confidence, affinity = run_modal_prediction(
        sequence, job_name, predict_affinity=predict_affinity,
    )

    return {
        "pdb": pdb,
        "confidence": confidence,
        "affinity": affinity,
        "source": "modal",
    }


def run_prediction_rcsb(uniprot_id: str) -> dict:
    """Fetch experimental structure from RCSB PDB (sync wrapper).

    Returns dict with keys: pdb, confidence, affinity, source, skip_plddt.
    """
    import httpx

    # Search RCSB for PDB entries matching this UniProt ID
    search_url = "https://search.rcsb.org/rcsbsearch/v2/query"
    search_query = {
        "query": {
            "type": "terminal",
            "service": "text",
            "parameters": {
                "attribute": "rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession",
                "operator": "exact_match",
                "value": uniprot_id,
            },
        },
        "return_type": "entry",
        "request_options": {"results_content_type": ["experimental"]},
    }

    resp = httpx.post(search_url, json=search_query, timeout=15)
    if resp.status_code != 200:
        raise RuntimeError(f"RCSB search failed: {resp.status_code}")

    data = resp.json()
    results = data.get("result_set", [])
    if not results:
        raise RuntimeError(f"No experimental structures found for {uniprot_id}")

    pdb_id = results[0].get("identifier", "")
    if not pdb_id:
        raise RuntimeError("No PDB ID in search results")

    # Download PDB file
    pdb_url = f"https://files.rcsb.org/download/{pdb_id}.pdb"
    pdb_resp = httpx.get(pdb_url, timeout=30)
    if pdb_resp.status_code != 200:
        raise RuntimeError(f"Failed to download {pdb_id}.pdb")

    return {
        "pdb": pdb_resp.text,
        "confidence": {},
        "affinity": None,
        "source": "rcsb",
        "skip_plddt": True,
    }


# ── Biological Context ───────────────────────────────────────────────────────


def fetch_bio_context_background(
    protein_name: str,
    uniprot_id: str | None,
    mutation: str | None,
    question_type: str,
    interaction_partner: str | None,
    sequence: str | None,
) -> dict:
    """Fetch biological context from MCP + BioMCP (sync wrapper).

    Returns dict with keys: bio_context (BioContext object).
    """
    from src.models import BioContext, ProteinQuery

    query = ProteinQuery(
        protein_name=protein_name,
        uniprot_id=uniprot_id,
        mutation=mutation,
        question_type=question_type,
        interaction_partner=interaction_partner,
        sequence=sequence,
    )

    # Try MCP first, then BioMCP direct, then empty
    try:
        from src.bio_context import fetch_bio_context_mcp
        ctx = fetch_bio_context_mcp(query)
        if ctx.narrative or ctx.disease_associations or ctx.drugs:
            return {"bio_context": ctx}
    except Exception:
        pass

    try:
        from src.bio_context_direct import fetch_bio_context_direct
        ctx = fetch_bio_context_direct(query)
        return {"bio_context": ctx}
    except Exception:
        pass

    return {"bio_context": BioContext()}


def generate_interpretation_background(
    protein_name: str,
    uniprot_id: str | None,
    mutation: str | None,
    question_type: str,
    interaction_partner: str | None,
    sequence: str | None,
    trust_audit_dict: dict,
    bio_context_obj,
) -> dict:
    """Generate AI interpretation (sync wrapper).

    Returns dict with key: interpretation (str).
    """
    from src.models import ProteinQuery, RegionConfidence, TrustAudit

    query = ProteinQuery(
        protein_name=protein_name,
        uniprot_id=uniprot_id,
        mutation=mutation,
        question_type=question_type,
        interaction_partner=interaction_partner,
        sequence=sequence,
    )

    # Reconstruct TrustAudit from dict
    if isinstance(trust_audit_dict, dict):
        ta = trust_audit_dict.copy()
        if "regions" in ta:
            regions = []
            for r in ta["regions"]:
                try:
                    regions.append(RegionConfidence(**r) if isinstance(r, dict) else r)
                except Exception:
                    pass
            ta["regions"] = regions
        trust_audit = TrustAudit(**ta)
    else:
        trust_audit = trust_audit_dict  # Already a TrustAudit object

    try:
        from src.interpreter import generate_interpretation
        interp = generate_interpretation(query, trust_audit, bio_context_obj)
    except Exception:
        from src.interpreter import _fallback_interpretation
        interp = _fallback_interpretation(query, trust_audit, bio_context_obj)

    return {"interpretation": interp}


# ── Video Generation ─────────────────────────────────────────────────────────


def generate_video_background(
    image_bytes: bytes | None,
    prompt: str | None,
    style: str = "rotate",
    text_only: bool = False,
) -> dict:
    """Generate a protein video via Gemini Veo (sync wrapper).

    Returns dict with key: video_bytes (bytes).
    """
    from src.video_generator import (
        generate_protein_video,
        generate_protein_video_text_only,
    )

    if text_only or image_bytes is None:
        if not prompt:
            prompt = (
                "Slowly rotating 3D protein molecular structure, "
                "scientific visualization, cinematic lighting, dark background"
            )
        video = generate_protein_video_text_only(prompt)
    else:
        video = generate_protein_video(image_bytes, prompt=prompt, style=style)

    return {"video_bytes": video}
