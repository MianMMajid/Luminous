"""Variant pathogenicity analysis via BioMCP.

Connects ClinVar/OncoKB variant data to the 3D structure,
bridging the gap between structure prediction and clinical significance.
"""
from __future__ import annotations

import json
import re

from src.models import ProteinQuery
from src.utils import run_async


def fetch_variant_landscape(query: ProteinQuery) -> dict:
    """Fetch known pathogenic variants for the protein from ClinVar/OncoKB.

    Returns a dict with:
      - variants: list of variant dicts with position, significance, etc.
      - summary: text summary
      - pathogenic_positions: set of residue positions with pathogenic variants
    """
    try:
        return run_async(_fetch_async(query))
    except Exception:
        return _fetch_cli_fallback(query)


async def _fetch_async(query: ProteinQuery) -> dict:
    """Use BioMCP async SDK for variant search."""
    import asyncio

    from biomcp.variants.search import (
        ClinicalSignificance,
        VariantQuery,
        search_variants,
    )

    # Search for pathogenic variants
    pathogenic_task = search_variants(
        VariantQuery(
            gene=query.protein_name,
            significance=ClinicalSignificance.PATHOGENIC,
            size=20,
        ),
        output_json=True,
        include_cbioportal=True,
        include_oncokb=True,
    )

    # Search for likely pathogenic variants
    likely_path_task = search_variants(
        VariantQuery(
            gene=query.protein_name,
            significance=ClinicalSignificance.LIKELY_PATHOGENIC,
            size=10,
        ),
        output_json=True,
        include_cbioportal=False,
        include_oncokb=False,
    )

    results = await asyncio.gather(pathogenic_task, likely_path_task, return_exceptions=True)

    variants = []
    for result in results:
        if isinstance(result, Exception) or not isinstance(result, str):
            continue
        try:
            parsed = json.loads(result)
            if isinstance(parsed, list):
                variants.extend(parsed)
            elif isinstance(parsed, dict):
                # BioMCP wraps results in "variants" key (not "hits")
                if "variants" in parsed:
                    v_data = parsed["variants"]
                    if isinstance(v_data, list):
                        variants.extend(v_data)
                    elif isinstance(v_data, dict):
                        variants.append(v_data)
                elif "hits" in parsed:
                    variants.extend(parsed["hits"])
                else:
                    variants.append(parsed)
        except (json.JSONDecodeError, TypeError):
            continue

    return _process_variants(variants, query)


def _fetch_cli_fallback(query: ProteinQuery) -> dict:
    """CLI fallback for variant data."""
    import subprocess

    try:
        result = subprocess.run(
            ["biomcp", "variant", "search", "--gene", query.protein_name,
             "--significance", "pathogenic", "-j"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            if isinstance(data, list):
                variants = data
            elif isinstance(data, dict) and "variants" in data:
                variants = data["variants"] if isinstance(data["variants"], list) else [data["variants"]]
            elif isinstance(data, dict):
                variants = [data]
            else:
                variants = []
            return _process_variants(variants, query)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        pass

    return _empty_result()


def _process_variants(raw_variants: list, query: ProteinQuery) -> dict:
    """Process raw variant data into structured format with residue positions."""
    processed = []
    pathogenic_positions: dict[int, list[str]] = {}

    for v in raw_variants:
        if not isinstance(v, dict):
            continue

        # Extract residue position from various formats
        position = _extract_position(v)
        significance = _extract_significance(v)
        name = _extract_variant_name(v)

        if position is None:
            continue

        variant_info = {
            "position": position,
            "name": name,
            "significance": significance,
            "frequency": v.get("allele_freq", v.get("gnomad_af")),
            "cadd_score": v.get("cadd_phred", v.get("cadd", {}).get("phred") if isinstance(v.get("cadd"), dict) else None),
            "clinvar_id": v.get("clinvar", {}).get("rcv") if isinstance(v.get("clinvar"), dict) else v.get("rsid"),
            "oncokb": v.get("oncokb_summary"),
            "disease": _extract_disease(v),
        }
        processed.append(variant_info)

        if significance in ("pathogenic", "likely_pathogenic"):
            if position not in pathogenic_positions:
                pathogenic_positions[position] = []
            pathogenic_positions[position].append(name)

    # Sort by position
    processed.sort(key=lambda x: x["position"])

    # Summary
    path_count = sum(1 for v in processed if v["significance"] == "pathogenic")
    lp_count = sum(1 for v in processed if v["significance"] == "likely_pathogenic")

    summary = (
        f"Found {len(processed)} annotated variants for {query.protein_name}. "
        f"{path_count} pathogenic, {lp_count} likely pathogenic. "
        f"{len(pathogenic_positions)} residue positions harbor known pathogenic variants."
    )

    if query.mutation:
        mut_pos = _parse_mutation_position(query.mutation)
        if mut_pos and mut_pos in pathogenic_positions:
            summary += (
                f" The queried mutation {query.mutation} at position {mut_pos} "
                f"is at a known pathogenic site."
            )

    return {
        "variants": processed,
        "summary": summary,
        "pathogenic_positions": pathogenic_positions,
        "total": len(processed),
        "pathogenic_count": path_count,
        "likely_pathogenic_count": lp_count,
    }


def _extract_position(v: dict) -> int | None:
    """Extract amino acid position from variant data."""
    # Try hgvsp (protein change notation) — can be string or list
    hgvsp = v.get("hgvsp", "")
    # Also check nested dbnsfp.hgvsp (BioMCP/MyVariant format)
    if not hgvsp:
        dbnsfp = v.get("dbnsfp", {})
        if isinstance(dbnsfp, dict):
            hgvsp = dbnsfp.get("hgvsp", "")

    # Handle list of hgvsp values
    if isinstance(hgvsp, list):
        for h in hgvsp:
            if isinstance(h, str):
                m = re.search(r"p\.[A-Z][a-z]{2}(\d+)", h)
                if m:
                    return int(m.group(1))
    elif isinstance(hgvsp, str) and hgvsp:
        m = re.search(r"p\.[A-Z][a-z]{2}(\d+)", hgvsp)
        if m:
            return int(m.group(1))

    # Try direct position field
    for key in ("protein_position", "position", "aa_position"):
        pos = v.get(key)
        if pos is not None:
            try:
                return int(pos)
            except (ValueError, TypeError):
                pass

    # Try parsing from dbsnp/clinvar notation
    for key in ("_id", "rsid", "variant_id"):
        val = v.get(key, "")
        if isinstance(val, str):
            m = re.search(r"[A-Z](\d+)[A-Z]", val)
            if m:
                return int(m.group(1))

    return None


def _extract_significance(v: dict) -> str:
    """Extract clinical significance."""
    for key in ("clinical_significance", "significance", "clinvar_sig"):
        val = v.get(key, "")
        if isinstance(val, str) and val:
            return val.lower().replace(" ", "_")

    clinvar = v.get("clinvar", {})
    if isinstance(clinvar, dict):
        # Direct clinical_significance field
        sig = clinvar.get("clinical_significance", "")
        if isinstance(sig, str) and sig:
            return sig.lower().replace(" ", "_")

        # Check nested rcv array (BioMCP/MyVariant format: clinvar.rcv is a list)
        rcv = clinvar.get("rcv", [])
        if isinstance(rcv, list):
            for entry in rcv:
                if isinstance(entry, dict):
                    cs = entry.get("clinical_significance", "")
                    if isinstance(cs, str) and cs:
                        return cs.lower().replace(" ", "_")
        elif isinstance(rcv, dict):
            cs = rcv.get("clinical_significance", "")
            if isinstance(cs, str) and cs:
                return cs.lower().replace(" ", "_")

    return "unknown"


def _extract_variant_name(v: dict) -> str:
    """Extract human-readable variant name."""
    hgvsp = v.get("hgvsp", "")
    # Also check nested dbnsfp.hgvsp
    if not hgvsp:
        dbnsfp = v.get("dbnsfp", {})
        if isinstance(dbnsfp, dict):
            hgvsp = dbnsfp.get("hgvsp", "")
    # Take first element if list
    if isinstance(hgvsp, list):
        hgvsp = next((h for h in hgvsp if isinstance(h, str) and "p." in h), "")
    if hgvsp:
        # Convert p.Arg248Trp to R248W
        m = re.search(r"p\.([A-Z][a-z]{2})(\d+)([A-Z][a-z]{2})", hgvsp)
        if m:
            aa3_to_1 = {
                "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
                "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
                "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
                "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
            }
            from_aa = aa3_to_1.get(m.group(1), "?")
            to_aa = aa3_to_1.get(m.group(3), "?")
            return f"{from_aa}{m.group(2)}{to_aa}"

    return v.get("_id", v.get("rsid", v.get("variant_id", "unknown")))


def _extract_disease(v: dict) -> str | None:
    """Extract associated disease."""
    clinvar = v.get("clinvar", {})
    if isinstance(clinvar, dict):
        conditions = clinvar.get("conditions", [])
        if isinstance(conditions, list) and conditions:
            if isinstance(conditions[0], dict):
                return conditions[0].get("name")
            return str(conditions[0])

    return v.get("disease", v.get("condition"))


def _parse_mutation_position(mutation: str) -> int | None:
    """Parse position from mutation notation like R248W."""
    m = re.match(r"[A-Z](\d+)[A-Z]", mutation)
    return int(m.group(1)) if m else None


def _empty_result() -> dict:
    return {
        "variants": [],
        "summary": "No variant data available.",
        "pathogenic_positions": {},
        "total": 0,
        "pathogenic_count": 0,
        "likely_pathogenic_count": 0,
    }
