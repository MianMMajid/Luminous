from __future__ import annotations

import json

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_FAST_MODEL
from src.models import ProteinQuery

PARSE_SYSTEM = """You are a biology query parser. Extract structured information from natural language questions about proteins.

Rules:
- Resolve common protein names to official gene symbols (e.g., "p53" -> "TP53")
- Identify UniProt IDs if mentioned or if you know them for common proteins
- Extract mutation notation (e.g., R248W, C61G, T790M)
- Identify interaction partners (drugs, other proteins)
- Classify the question type: "structure", "mutation_impact", "druggability", or "binding"
- If a FASTA sequence is provided, include it in the sequence field

Respond with ONLY valid JSON matching this schema:
{
  "protein_name": "official gene symbol",
  "uniprot_id": "UniProt accession or null",
  "mutation": "mutation notation or null",
  "interaction_partner": "partner name or null",
  "question_type": "one of: structure, mutation_impact, druggability, binding",
  "sequence": "amino acid sequence or null"
}"""


def parse_query(user_input: str) -> ProteinQuery:
    """Parse natural language query into structured ProteinQuery using Claude."""
    if not ANTHROPIC_API_KEY:
        return _fallback_parse(user_input)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        message = client.messages.create(
            model=CLAUDE_FAST_MODEL,
            max_tokens=512,
            system=PARSE_SYSTEM,
            messages=[{"role": "user", "content": user_input}],
        )
    except Exception:
        return _fallback_parse(user_input)

    if not message.content:
        return _fallback_parse(user_input)

    text = message.content[0].text
    # Strip markdown code fences if present
    if text.startswith("```"):
        parts = text.split("\n", 1)
        if len(parts) > 1:
            text = parts[1].rsplit("```", 1)[0]

    try:
        data = json.loads(text)
        return ProteinQuery(**data)
    except (json.JSONDecodeError, Exception):
        return _fallback_parse(user_input)


def _fallback_parse(user_input: str) -> ProteinQuery:
    """Basic regex-free fallback when no API key is available."""
    upper = user_input.upper()

    protein_name = "unknown"
    for name in ["TP53", "P53", "BRCA1", "BRCA2", "EGFR", "KRAS", "INS", "INSULIN"]:
        if name in upper:
            protein_name = name.replace("P53", "TP53").replace("INSULIN", "INS")
            break

    mutation = None
    import re
    m = re.search(r"\b([A-Z]\d{1,4}[A-Z])\b", user_input)
    if m:
        mutation = m.group(1)

    question_type = "structure"
    if "DRUG" in upper:
        question_type = "druggability"
    elif "MUTATION" in upper or "VARIANT" in upper or "IMPACT" in upper:
        question_type = "mutation_impact"
    elif "BIND" in upper or "INTERACT" in upper:
        question_type = "binding"

    uniprot_map = {
        "TP53": "P04637", "BRCA1": "P38398", "EGFR": "P00533",
        "KRAS": "P01116", "INS": "P01308",
    }

    return ProteinQuery(
        protein_name=protein_name,
        uniprot_id=uniprot_map.get(protein_name),
        mutation=mutation,
        question_type=question_type,
    )
