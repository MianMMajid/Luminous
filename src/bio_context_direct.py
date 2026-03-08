from __future__ import annotations

import asyncio
import json
import subprocess

from src.models import (
    BioContext,
    DiseaseAssociation,
    DrugCandidate,
    LiteratureSummary,
    ProteinQuery,
)
from src.utils import run_async


def fetch_bio_context_direct(query: ProteinQuery) -> BioContext:
    """Fetch biological context using BioMCP — async SDK first, CLI fallback.

    No LLM needed — direct database queries.
    """
    try:
        return run_async(_fetch_async(query))
    except Exception:
        return _fetch_via_cli(query)


async def _fetch_async(query: ProteinQuery) -> BioContext:
    """Use BioMCP async Python SDK for direct database access."""
    narrative_parts = []
    diseases: list[DiseaseAssociation] = []
    drugs: list[DrugCandidate] = []
    literature = LiteratureSummary()
    pathways: list[str] = []

    # Run queries concurrently
    gene_task = _get_gene_async(query.protein_name)
    article_task = _search_articles_async(query.protein_name, query.mutation)

    tasks = [gene_task, article_task]
    if query.question_type in ("druggability", "binding"):
        tasks.append(_get_drugs_async(query.protein_name))
    if query.mutation:
        tasks.append(_search_variants_async(query.protein_name, query.mutation))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results back to task names for safe access
    result_idx = 0

    # Process gene info (always first)
    if result_idx < len(results):
        gene_result = results[result_idx]
        if isinstance(gene_result, str) and gene_result:
            narrative_parts.append(gene_result)
    result_idx += 1

    # Process articles (always second)
    if result_idx < len(results):
        article_result = results[result_idx]
        if isinstance(article_result, dict):
            literature = LiteratureSummary(**article_result)
    result_idx += 1

    # Process drugs (if queried)
    if query.question_type in ("druggability", "binding"):
        if result_idx < len(results):
            drug_result = results[result_idx]
            if isinstance(drug_result, list):
                drugs = drug_result
        result_idx += 1

    # Process variants (if queried)
    if query.mutation:
        if result_idx < len(results):
            variant_result = results[result_idx]
            if isinstance(variant_result, str) and variant_result:
                narrative_parts.append(variant_result)
        result_idx += 1

    narrative = " ".join(narrative_parts) if narrative_parts else (
        f"Biological context for {query.protein_name}."
    )

    return BioContext(
        narrative=narrative,
        disease_associations=diseases,
        drugs=drugs,
        literature=literature,
        pathways=pathways,
    )


async def _get_gene_async(gene_symbol: str) -> str:
    """Get gene information via BioMCP async SDK."""
    try:
        from biomcp.genes.getter import get_gene
        result = await get_gene(gene_symbol, output_json=True)
        if isinstance(result, str):
            data = json.loads(result)
            # Extract structured fields into a concise narrative
            parts = []
            if isinstance(data, dict):
                if data.get("summary"):
                    parts.append(data["summary"])
                if data.get("function"):
                    parts.append(f"Function: {data['function']}")
                if data.get("pathways"):
                    pw = data["pathways"]
                    if isinstance(pw, list):
                        pw_names = [
                            p.get("name", str(p)) if isinstance(p, dict) else str(p)
                            for p in pw[:5]
                        ]
                        parts.append(f"Pathways: {', '.join(pw_names)}")
            return " ".join(parts) if parts else str(data)[:500]
        return ""
    except Exception:
        return ""


async def _search_articles_async(gene: str, mutation: str | None = None) -> dict:
    """Search PubMed articles via BioMCP."""
    try:
        from biomcp.articles.search import PubmedRequest, search_articles
        req = PubmedRequest(genes=[gene])
        result = await search_articles(req, output_json=True, limit=10, page=1)
        if isinstance(result, str):
            data = json.loads(result)
            articles = data if isinstance(data, list) else data.get("articles", [])
            return {
                "total_papers": len(articles),
                "recent_papers": len(articles),
                "key_findings": [
                    a.get("title", "") for a in articles[:5]
                    if isinstance(a, dict) and a.get("title")
                ],
            }
    except Exception:
        pass
    return {"total_papers": 0, "recent_papers": 0, "key_findings": []}


async def _get_drugs_async(gene: str) -> list[DrugCandidate]:
    """Get drug information via BioMCP."""
    try:
        from biomcp.drugs.getter import get_drug
        result = await get_drug(gene, output_json=True)
        if isinstance(result, str):
            data = json.loads(result)
            items = data if isinstance(data, list) else [data]
            drugs = []
            for d in items[:10]:
                if not isinstance(d, dict):
                    continue
                # Try multiple key patterns from BioMCP/ChEMBL/OpenTargets
                name = (
                    d.get("name")
                    or d.get("drugName")
                    or d.get("molecule_name")
                    or d.get("prefName")
                    or d.get("drug_name")
                )
                if not name or name == "Unknown":
                    continue  # Skip entries with no real name
                drugs.append(DrugCandidate(
                    name=name,
                    phase=(
                        d.get("phase")
                        or d.get("maximumClinicalTrialPhase")
                        or d.get("max_phase_for_ind")
                    ),
                    mechanism=(
                        d.get("mechanism")
                        or d.get("mechanismOfAction")
                        or d.get("mechanism_of_action")
                    ),
                    source="BioMCP/ChEMBL",
                ))
            return drugs
    except Exception:
        pass
    return []


async def _search_variants_async(gene: str, mutation: str) -> str:
    """Search variant info via BioMCP."""
    try:
        from biomcp.variants.getter import get_variant
        result = await get_variant(f"{gene}:{mutation}", output_json=False)
        return result if isinstance(result, str) else ""
    except Exception:
        pass
    return ""


# --- CLI Fallback ---


def _fetch_via_cli(query: ProteinQuery) -> BioContext:
    """Fetch biological context using BioMCP CLI as last resort."""
    narrative_parts = []
    drugs: list[DrugCandidate] = []
    literature = LiteratureSummary()
    pathways: list[str] = []

    # Gene info (biomcp gene get <SYMBOL>)
    gene_data = _run_biomcp_cli("gene", "get", query.protein_name)
    if gene_data and isinstance(gene_data, dict):
        summary = gene_data.get("summary", "")
        if summary:
            narrative_parts.append(summary)
        for pathway in gene_data.get("pathways", []):
            if isinstance(pathway, str):
                pathways.append(pathway)
            elif isinstance(pathway, dict):
                pathways.append(pathway.get("name", str(pathway)))

    # Articles (biomcp article search -g <SYMBOL>)
    article_data = _run_biomcp_cli("article", "search", "-g", query.protein_name)
    if article_data and isinstance(article_data, list):
        literature = LiteratureSummary(
            total_papers=len(article_data),
            recent_papers=len(article_data),
            key_findings=[
                a.get("title", "")
                for a in article_data[:5]
                if isinstance(a, dict)
            ],
        )

    # Drugs
    if query.question_type in ("druggability", "binding"):
        drug_data = _run_biomcp_cli("drug", "get", query.protein_name)
        if drug_data:
            items = drug_data if isinstance(drug_data, list) else [drug_data]
            for d in items[:10]:
                if isinstance(d, dict):
                    drugs.append(
                        DrugCandidate(
                            name=d.get("name", d.get("drugName", "Unknown")),
                            phase=d.get("phase", d.get("maximumClinicalTrialPhase")),
                            mechanism=d.get("mechanism", d.get("mechanismOfAction")),
                            source="BioMCP/ChEMBL",
                        )
                    )

    narrative = " ".join(narrative_parts) if narrative_parts else (
        f"Biological context for {query.protein_name}."
    )

    return BioContext(
        narrative=narrative,
        drugs=drugs,
        literature=literature,
        pathways=pathways,
    )


def _run_biomcp_cli(*args: str) -> dict | list | None:
    """Run biomcp CLI command and parse JSON output."""
    try:
        result = subprocess.run(
            ["biomcp", *args, "-j"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass
    return None
