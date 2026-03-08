"""Protein domain annotations from InterPro.

Fetches domain/family/site annotations for a UniProt protein,
enabling colored domain segments on the 3D structure and
residue dashboard tracks.
"""
from __future__ import annotations

import httpx
import streamlit as st

_INTERPRO_API = "https://www.ebi.ac.uk/interpro/api"

# Domain type display colors
_DOMAIN_COLORS = [
    "#E63946",  # red
    "#457B9D",  # steel blue
    "#2A9D8F",  # teal
    "#E9C46A",  # gold
    "#F4A261",  # sandy
    "#264653",  # dark teal
    "#A8DADC",  # light blue
    "#6A4C93",  # purple
    "#1982C4",  # bright blue
    "#8AC926",  # lime green
]


@st.cache_data(ttl=3600, show_spinner="Fetching domain annotations...")
def fetch_domain_annotations(uniprot_id: str) -> dict:
    """Fetch InterPro domain annotations for a protein.

    Returns
    -------
    dict with keys:
      - domains: list of domain dicts with:
          name, accession, type, database, start, end, color
      - domain_map: {int: str} — residue position → domain name
      - summary: str
      - available: bool
    """
    if not uniprot_id:
        return _empty()

    # Query InterPro API for all entries matching this protein
    url = (
        f"{_INTERPRO_API}/entry/interpro/protein/uniprot/"
        f"{uniprot_id}?page_size=100"
    )

    domains: list[dict] = []

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            # Try Pfam as fallback
            return _fetch_pfam_fallback(uniprot_id)

        data = resp.json()
        results = data.get("results", [])

        color_idx = 0
        for entry in results:
            meta = entry.get("metadata", {})
            entry_name = meta.get("name", {})
            if isinstance(entry_name, dict):
                entry_name = entry_name.get("name", "Unknown")
            accession = meta.get("accession", "")
            entry_type = meta.get("type", "domain")
            source_db = meta.get("source_database", "InterPro")

            # Extract protein locations
            proteins = entry.get("proteins", [])
            for protein in proteins:
                locations = protein.get(
                    "entry_protein_locations", []
                )
                for loc_group in locations:
                    fragments = loc_group.get("fragments", [])
                    for frag in fragments:
                        start = frag.get("start")
                        end = frag.get("end")
                        if start is not None and end is not None:
                            color = _DOMAIN_COLORS[
                                color_idx % len(_DOMAIN_COLORS)
                            ]
                            domains.append({
                                "name": entry_name,
                                "accession": accession,
                                "type": entry_type,
                                "database": source_db,
                                "start": int(start),
                                "end": int(end),
                                "color": color,
                            })
                            color_idx += 1

    except Exception:
        return _fetch_pfam_fallback(uniprot_id)

    if not domains:
        return _fetch_pfam_fallback(uniprot_id)

    return _build_result(domains, uniprot_id)


def _fetch_pfam_fallback(uniprot_id: str) -> dict:
    """Fallback: fetch Pfam domains from InterPro."""
    url = (
        f"{_INTERPRO_API}/entry/pfam/protein/uniprot/"
        f"{uniprot_id}?page_size=100"
    )
    domains: list[dict] = []

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return _fetch_uniprot_fallback(uniprot_id)

        data = resp.json()
        results = data.get("results", [])

        color_idx = 0
        for entry in results:
            meta = entry.get("metadata", {})
            entry_name = meta.get("name", "Unknown")
            if isinstance(entry_name, dict):
                entry_name = entry_name.get("name", "Unknown")
            accession = meta.get("accession", "")

            proteins = entry.get("proteins", [])
            for protein in proteins:
                locations = protein.get(
                    "entry_protein_locations", []
                )
                for loc_group in locations:
                    fragments = loc_group.get("fragments", [])
                    for frag in fragments:
                        start = frag.get("start")
                        end = frag.get("end")
                        if (
                            start is not None
                            and end is not None
                        ):
                            color = _DOMAIN_COLORS[
                                color_idx % len(
                                    _DOMAIN_COLORS
                                )
                            ]
                            domains.append({
                                "name": entry_name,
                                "accession": accession,
                                "type": "domain",
                                "database": "Pfam",
                                "start": int(start),
                                "end": int(end),
                                "color": color,
                            })
                            color_idx += 1

    except Exception:
        return _fetch_uniprot_fallback(uniprot_id)

    if not domains:
        return _fetch_uniprot_fallback(uniprot_id)

    return _build_result(domains, uniprot_id)


def _fetch_uniprot_fallback(uniprot_id: str) -> dict:
    """Last resort: fetch domain features from UniProt API."""
    url = (
        f"https://rest.uniprot.org/uniprotkb/{uniprot_id}"
        f".json"
    )

    domains: list[dict] = []

    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code != 200:
            return _empty()

        data = resp.json()
        features = data.get("features", [])

        domain_types = {
            "Domain", "Region", "Zinc finger",
            "DNA binding", "Repeat", "Motif",
        }

        color_idx = 0
        for feat in features:
            feat_type = feat.get("type", "")
            if feat_type not in domain_types:
                continue

            desc = feat.get("description", feat_type)
            location = feat.get("location", {})
            start_val = location.get("start", {}).get(
                "value"
            )
            end_val = location.get("end", {}).get("value")

            if start_val is not None and end_val is not None:
                color = _DOMAIN_COLORS[
                    color_idx % len(_DOMAIN_COLORS)
                ]
                domains.append({
                    "name": desc,
                    "accession": "",
                    "type": feat_type.lower(),
                    "database": "UniProt",
                    "start": int(start_val),
                    "end": int(end_val),
                    "color": color,
                })
                color_idx += 1

    except Exception:
        return _empty()

    if not domains:
        return _empty()

    return _build_result(domains, uniprot_id)


def _build_result(
    domains: list[dict], uniprot_id: str
) -> dict:
    """Build the final result dict from domain list."""
    # Sort by start position
    domains.sort(key=lambda d: d["start"])

    # Build residue→domain map
    domain_map: dict[int, str] = {}
    for d in domains:
        for pos in range(d["start"], d["end"] + 1):
            domain_map[pos] = d["name"]

    # Deduplicate overlapping domains for summary
    unique_names = list(dict.fromkeys(
        d["name"] for d in domains
    ))

    summary = (
        f"{len(domains)} domain region(s) from "
        f"{len(unique_names)} annotation(s): "
        + ", ".join(unique_names[:8])
        + ("..." if len(unique_names) > 8 else "")
    )

    return {
        "domains": domains,
        "domain_map": domain_map,
        "summary": summary,
        "available": True,
    }


def _empty() -> dict:
    return {
        "domains": [],
        "domain_map": {},
        "summary": "No domain annotations available.",
        "available": False,
    }
