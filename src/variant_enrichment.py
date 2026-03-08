"""Variant data enrichment via myvariant.info API.

Aggregates ClinVar, gnomAD, CADD, SIFT, PolyPhen, dbNSFP, and COSMIC
data for each variant in a single API call.
"""
from __future__ import annotations

import httpx
import streamlit as st


_BASE_URL = "https://myvariant.info/v1"


@st.cache_data(ttl=3600, show_spinner=False)
def enrich_variants(
    gene_name: str,
    variant_positions: list[int],
    ref_genome: str = "hg38",
) -> dict:
    """Enrich variant positions with multi-source annotations.

    Uses myvariant.info to aggregate data from ClinVar, gnomAD v4,
    CADD, SIFT, PolyPhen-2, and COSMIC.

    Returns dict with per-position enrichment data.
    """
    if not variant_positions:
        return {"enriched": {}, "sources": []}

    enriched: dict[int, dict] = {}
    sources_found: set[str] = set()

    _FIELDS = (
        "cadd.phred,cadd.consequence,"
        "clinvar.clinical_significance,clinvar.rcv.conditions,"
        "gnomad_exome.af.af,gnomad_genome.af.af,"
        "dbnsfp.genename,dbnsfp.aa.pos,dbnsfp.sift.pred,"
        "dbnsfp.polyphen2.hdiv.pred,"
        "dbnsfp.revel.score,dbnsfp.mutationtaster.pred,"
        "cosmic.cosmic_id,cosmic.tumor_site"
    )

    # Strategy 1: Batch query via clinvar gene symbol (finds ClinVar variants)
    try:
        resp = httpx.get(
            f"{_BASE_URL}/query",
            params={
                "q": f"clinvar.gene.symbol:{gene_name}",
                "fields": _FIELDS,
                "size": min(len(variant_positions) * 5, 1000),
            },
            timeout=15.0,
        )
        resp.raise_for_status()
        data = resp.json()
        for hit in data.get("hits", []):
            _extract_hit(hit, enriched, sources_found, variant_positions)
    except Exception:
        pass

    # Strategy 2: Paginated query via dbNSFP gene name (SIFT/PP2/REVEL)
    # Results are sorted by genomic position, so we page through to find
    # all target amino acid positions.
    target_set = set(variant_positions)
    found_set = set(enriched.keys())
    remaining = target_set - found_set
    page_size = 1000
    for offset in range(0, 10000, page_size):
        if not remaining:
            break
        try:
            resp = httpx.get(
                f"{_BASE_URL}/query",
                params={
                    "q": f"dbnsfp.genename:{gene_name}",
                    "fields": _FIELDS,
                    "size": page_size,
                    "from": offset,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
            hits = data.get("hits", [])
            if not hits:
                break
            for hit in hits:
                _extract_hit(
                    hit, enriched, sources_found, variant_positions,
                )
            remaining = target_set - set(enriched.keys())
        except Exception:
            break

    return {
        "enriched": enriched,
        "sources": sorted(sources_found),
        "n_enriched": len(enriched),
    }


def _extract_hit(
    hit: dict,
    enriched: dict,
    sources: set,
    target_positions: list[int] | None = None,
):
    """Extract enrichment data from a myvariant.info hit."""
    # Try to resolve amino acid position from dbNSFP
    pos = None
    dbnsfp = hit.get("dbnsfp", {})
    if isinstance(dbnsfp, dict):
        # Position is in dbnsfp.aa.pos (list of ints per transcript)
        aa = dbnsfp.get("aa", {})
        if isinstance(aa, dict):
            aapos = aa.get("pos")
            if aapos is not None:
                pos = _safe_int(aapos)

    # If no position resolved but we have target positions, assign to
    # all targets (batch enrichment — annotations apply gene-wide)
    if pos is None and target_positions:
        # Only add gene-level annotations (CADD, etc) if they exist
        _extract_annotations_genelevel(
            hit, enriched, sources, target_positions,
        )
        return

    if pos is None:
        return

    # Skip if not in our target positions
    if target_positions and pos not in target_positions:
        return

    entry = enriched.get(pos, {})
    _extract_annotations(hit, entry, sources)

    if entry:
        enriched[pos] = entry


def _extract_annotations_genelevel(
    hit: dict,
    enriched: dict,
    sources: set,
    target_positions: list[int],
):
    """Extract annotations that apply gene-wide to all target positions."""
    # Only extract CADD and ClinVar — these have specific variant IDs
    # Don't scatter SIFT/PP2 across all positions (those are per-variant)
    cadd = hit.get("cadd", {})
    if isinstance(cadd, dict) and cadd.get("phred"):
        # CADD is per-variant, can't distribute — skip
        pass

    clinvar = hit.get("clinvar", {})
    if isinstance(clinvar, dict):
        sig = clinvar.get("clinical_significance")
        if sig:
            sources.add("ClinVar")

    gnomad_ex = hit.get("gnomad_exome", {})
    if isinstance(gnomad_ex, dict):
        af_data = gnomad_ex.get("af", {})
        if isinstance(af_data, dict) and af_data.get("af") is not None:
            sources.add("gnomAD")


def _extract_annotations(hit: dict, entry: dict, sources: set):
    """Extract per-variant annotations into entry dict."""
    # CADD
    cadd = hit.get("cadd", {})
    if isinstance(cadd, dict) and cadd.get("phred"):
        entry["cadd_phred"] = _safe_float(cadd["phred"])
        entry["cadd_consequence"] = cadd.get("consequence", "")
        sources.add("CADD")

    # ClinVar
    clinvar = hit.get("clinvar", {})
    if isinstance(clinvar, dict):
        sig = clinvar.get("clinical_significance")
        if sig:
            entry["clinvar_significance"] = (
                sig if isinstance(sig, str) else str(sig)
            )
            sources.add("ClinVar")
        rcv = clinvar.get("rcv", {})
        if isinstance(rcv, dict):
            conds = rcv.get("conditions", {})
            if isinstance(conds, dict) and conds.get("name"):
                entry["clinvar_condition"] = conds["name"]

    # gnomAD
    gnomad_ex = hit.get("gnomad_exome", {})
    gnomad_ge = hit.get("gnomad_genome", {})
    af = None
    if isinstance(gnomad_ex, dict):
        af_data = gnomad_ex.get("af", {})
        if isinstance(af_data, dict):
            af = _safe_float(af_data.get("af"))
    if af is None and isinstance(gnomad_ge, dict):
        af_data = gnomad_ge.get("af", {})
        if isinstance(af_data, dict):
            af = _safe_float(af_data.get("af"))
    if af is not None:
        entry["gnomad_af"] = af
        sources.add("gnomAD")

    # dbNSFP predictions
    dbnsfp = hit.get("dbnsfp", {})
    if isinstance(dbnsfp, dict):
        sift = dbnsfp.get("sift", {})
        if isinstance(sift, dict) and sift.get("pred"):
            pred = sift["pred"]
            # Take first prediction if list
            if isinstance(pred, list):
                pred = pred[0] if pred else None
            if pred:
                entry["sift_pred"] = pred
                sources.add("SIFT")

        pp2 = dbnsfp.get("polyphen2", {})
        if isinstance(pp2, dict):
            hdiv = pp2.get("hdiv", {})
            if isinstance(hdiv, dict) and hdiv.get("pred"):
                pred = hdiv["pred"]
                if isinstance(pred, list):
                    pred = pred[0] if pred else None
                if pred:
                    entry["polyphen2_pred"] = pred
                    sources.add("PolyPhen-2")

        revel = dbnsfp.get("revel", {})
        if isinstance(revel, dict) and revel.get("score"):
            entry["revel_score"] = _safe_float(revel["score"])
            sources.add("REVEL")

    # COSMIC
    cosmic = hit.get("cosmic", {})
    if isinstance(cosmic, dict) and cosmic.get("cosmic_id"):
        entry["cosmic_id"] = cosmic["cosmic_id"]
        sources.add("COSMIC")


def _safe_float(val) -> float | None:
    """Safely convert to float."""
    if val is None:
        return None
    try:
        if isinstance(val, list):
            val = val[0]
        return float(val)
    except (ValueError, TypeError, IndexError):
        return None


def _safe_int(val) -> int | None:
    """Safely convert to int."""
    if val is None:
        return None
    try:
        if isinstance(val, list):
            val = val[0]
        return int(float(val))
    except (ValueError, TypeError, IndexError):
        return None


def format_enrichment_summary(enriched: dict[int, dict]) -> list[dict]:
    """Format enriched data into a table-friendly list."""
    rows = []
    for pos, data in sorted(enriched.items()):
        row = {"Position": pos}
        if "cadd_phred" in data:
            row["CADD"] = f"{data['cadd_phred']:.1f}"
        if "clinvar_significance" in data:
            row["ClinVar"] = data["clinvar_significance"]
        if "gnomad_af" in data:
            row["gnomAD AF"] = f"{data['gnomad_af']:.2e}"
        if "sift_pred" in data:
            row["SIFT"] = data["sift_pred"]
        if "polyphen2_pred" in data:
            row["PolyPhen-2"] = data["polyphen2_pred"]
        if "revel_score" in data:
            row["REVEL"] = f"{data['revel_score']:.3f}"
        if "cosmic_id" in data:
            row["COSMIC"] = "Yes"
        rows.append(row)
    return rows
