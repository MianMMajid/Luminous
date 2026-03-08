"""AlphaMissense pathogenicity data from AlphaFold Database.

Fetches per-residue average pathogenicity scores and per-substitution
matrices, enabling a toggle between pLDDT confidence and variant
pathogenicity on the 3D structure -- matching AFDB 2025's marquee feature.
"""
from __future__ import annotations

import csv
import io

import httpx
import streamlit as st

# AlphaFold DB file endpoints
_AFDB_BASE = "https://alphafold.ebi.ac.uk/files"


@st.cache_data(ttl=3600, show_spinner="Fetching AlphaMissense data...")
def fetch_alphamissense(uniprot_id: str) -> dict:
    """Fetch AlphaMissense pathogenicity scores for a UniProt protein.

    Returns
    -------
    dict with keys:
      - residue_scores: {int: float} — per-residue average pathogenicity (0-1)
      - substitution_matrix: {int: {str: float}} — pos -> {aa: score}
      - classification: {int: str} — per-residue class (pathogenic/ambiguous/benign)
      - summary: str — text summary
      - available: bool
    """
    if not uniprot_id:
        return _empty()

    # Try the amino acid substitutions CSV from AFDB
    url = (
        f"{_AFDB_BASE}/AF-{uniprot_id}-F1-aa-substitutions.csv"
    )
    try:
        resp = httpx.get(url, timeout=15, follow_redirects=True)
        if resp.status_code == 200:
            return _parse_substitution_csv(resp.text, uniprot_id)
    except Exception:
        pass

    # Fallback: try the summary JSON
    summary_url = (
        f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}"
    )
    try:
        resp = httpx.get(summary_url, timeout=10, follow_redirects=True)
        if resp.status_code == 200:
            data = resp.json()
            # AFDB returns a list for some endpoints
            if isinstance(data, list) and data:
                data = data[0]
            am_url = data.get(
                "amAnnotationUrl",
                data.get("aminoAcidSubstitutionsUrl", ""),
            )
            if am_url:
                resp2 = httpx.get(
                    am_url, timeout=15, follow_redirects=True
                )
                if resp2.status_code == 200:
                    return _parse_substitution_csv(
                        resp2.text, uniprot_id
                    )
    except Exception:
        pass

    return _empty()


def _parse_substitution_csv(
    csv_text: str, uniprot_id: str
) -> dict:
    """Parse AlphaMissense amino acid substitutions CSV.

    AFDB format (with header):
      protein_variant,am_pathogenicity,am_class
      M1A,0.4065,Amb

    Or older format with uniprot prefix:
      uniprot_id, variant, am_pathogenicity, am_class
    """
    # Normalize class abbreviations
    _CLASS_MAP = {
        "lpath": "pathogenic",
        "path": "pathogenic",
        "pathogenic": "pathogenic",
        "likely_pathogenic": "pathogenic",
        "amb": "ambiguous",
        "ambiguous": "ambiguous",
        "lben": "benign",
        "ben": "benign",
        "benign": "benign",
        "likely_benign": "benign",
    }

    residue_scores: dict[int, list[float]] = {}
    substitution_matrix: dict[int, dict[str, float]] = {}
    classification_votes: dict[int, list[str]] = {}

    reader = csv.reader(io.StringIO(csv_text))
    for row in reader:
        if not row:
            continue
        # Skip header or comment rows
        first = row[0].strip()
        if first.startswith("#") or first.startswith("protein"):
            continue
        if first.startswith("uniprot"):
            continue

        # Detect format: 3-col (variant,score,class)
        # or 4-col (uniprot,variant,score,class)
        if len(row) >= 4 and (not first or not first[0].isalpha()):
            continue
        if len(row) >= 4:
            # 4-column format
            variant = row[1].strip()
            try:
                score = float(row[2].strip())
                am_class = row[3].strip().lower()
            except (ValueError, IndexError):
                continue
        elif len(row) >= 3:
            # 3-column format (AFDB standard)
            variant = first
            try:
                score = float(row[1].strip())
                am_class = row[2].strip().lower()
            except (ValueError, IndexError):
                continue
        else:
            continue

        # Normalize class
        am_class = _CLASS_MAP.get(am_class, am_class)

        # Parse position: "M1A" → pos=1, to_aa="A"
        if len(variant) < 3:
            continue
        try:
            pos = int(variant[1:-1])
            to_aa = variant[-1]
        except ValueError:
            continue

        residue_scores.setdefault(pos, []).append(score)
        substitution_matrix.setdefault(
            pos, {}
        )[to_aa] = score
        classification_votes.setdefault(
            pos, []
        ).append(am_class)

    if not residue_scores:
        return _empty()

    # Average scores per residue
    avg_scores = {
        pos: sum(scores) / len(scores) if scores else 0.0
        for pos, scores in residue_scores.items()
    }

    # Majority-vote classification per residue
    classification = {}
    for pos, votes in classification_votes.items():
        counts: dict[str, int] = {}
        for v in votes:
            counts[v] = counts.get(v, 0) + 1
        if counts:
            classification[pos] = max(counts, key=counts.get)

    # Summary stats
    n_pathogenic = sum(
        1 for c in classification.values() if c == "pathogenic"
    )
    n_ambiguous = sum(
        1 for c in classification.values() if c == "ambiguous"
    )
    n_benign = sum(
        1 for c in classification.values() if c == "benign"
    )
    total = len(classification)

    if total > 0:
        summary = (
            f"AlphaMissense data for {uniprot_id}: "
            f"{total} residues scored. "
            f"{n_pathogenic} pathogenic ({n_pathogenic/total:.0%}), "
            f"{n_ambiguous} ambiguous ({n_ambiguous/total:.0%}), "
            f"{n_benign} benign ({n_benign/total:.0%})."
        )
    else:
        summary = f"AlphaMissense data for {uniprot_id}: no residues classified."

    return {
        "residue_scores": avg_scores,
        "substitution_matrix": substitution_matrix,
        "classification": classification,
        "summary": summary,
        "available": True,
    }


def get_pathogenicity_color(score: float) -> str:
    """Map AlphaMissense score (0-1) to a color.

    Uses AFDB 2025 standard:
      Blue (benign, <0.34) → White (ambiguous) → Red (pathogenic, >0.564)
    """
    score = max(0.0, min(1.0, score))  # Clamp to valid range
    if score < 0.34:
        # Benign: deep blue → light blue
        frac = score / 0.34
        r = int(30 + frac * 180)
        g = int(80 + frac * 160)
        b = int(220 - frac * 40)
        return f"#{r:02x}{g:02x}{b:02x}"
    elif score > 0.564:
        # Pathogenic: light red → deep red
        frac = min((score - 0.564) / 0.436, 1.0)
        r = int(220 + frac * 20)
        g = int(100 - frac * 80)
        b = int(80 - frac * 60)
        return f"#{r:02x}{g:02x}{b:02x}"
    else:
        # Ambiguous: white-ish / light gray
        frac = (score - 0.34) / 0.224
        r = int(210 + frac * 30)
        g = int(240 - frac * 100)
        b = int(180 + frac * 10)
        return f"#{r:02x}{g:02x}{b:02x}"


def _empty() -> dict:
    return {
        "residue_scores": {},
        "substitution_matrix": {},
        "classification": {},
        "summary": "AlphaMissense data not available.",
        "available": False,
    }
