from __future__ import annotations

import json

from anthropic import Anthropic

from src.config import (
    ANTHROPIC_API_KEY,
    BIORENDER_MCP_URL,
    BIORENDER_TOKEN,
    CLAUDE_FAST_MODEL,
    MCP_BETA_HEADER,
    OPEN_TARGETS_MCP_URL,
    PUBMED_MCP_URL,
    WILEY_MCP_URL,
)
from src.models import (
    BioContext,
    DiseaseAssociation,
    DrugCandidate,
    LiteratureSummary,
    ProteinQuery,
)

CONTEXT_SYSTEM = """You are a biomedical research assistant. Given a protein query, use the
available tools to gather comprehensive biological context from PubMed, Open Targets,
BioRender, and the Wiley Scholar Gateway.

For the protein query, find:
1. Disease associations and clinical significance
2. Known drugs and drug candidates targeting this protein
3. Recent literature findings (last 2 years) — prioritize recent review articles and clinical studies
4. Relevant biological pathways
5. Suggested experiments for validation

When searching the literature, also use the Wiley Scholar Gateway to find full-text journal
articles. Include specific paper titles, DOIs, and key quotes where available. Prioritize
high-impact reviews and clinical studies from the last 2 years.

In the "sources" field of the literature object, list which databases you successfully queried
(e.g., "PubMed", "Open Targets", "Wiley", "BioRender").

Respond with a JSON object matching this schema:
{
  "narrative": "A 2-3 paragraph scientific summary",
  "disease_associations": [{"disease": "name", "score": 0.0, "evidence": "..."}],
  "drugs": [{"name": "drug", "phase": "Phase III", "mechanism": "...", "source": "..."}],
  "literature": {
    "total_papers": 0,
    "recent_papers": 0,
    "key_findings": ["..."],
    "sources": ["PubMed", "Open Targets", "Wiley"],
    "paper_titles": ["Title of paper 1", "Title of paper 2"],
    "dois": ["10.xxxx/...", "10.xxxx/..."]
  },
  "pathways": ["pathway names"],
  "suggested_experiments": ["experiment descriptions"]
}"""


def fetch_bio_context_mcp(query: ProteinQuery) -> BioContext:
    """Fetch biological context using Anthropic API MCP connector.

    Single API call handles PubMed, Open Targets, and BioRender server-side.
    """
    if not ANTHROPIC_API_KEY:
        return BioContext()

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    user_prompt = f"Gather biological context for protein {query.protein_name}"
    if query.mutation:
        user_prompt += f" with mutation {query.mutation}"
    if query.interaction_partner:
        user_prompt += f" and its interaction with {query.interaction_partner}"
    user_prompt += f". Focus on: {query.question_type}."

    mcp_servers = [
        {"type": "url", "url": PUBMED_MCP_URL, "name": "pubmed"},
        {"type": "url", "url": OPEN_TARGETS_MCP_URL, "name": "open_targets"},
    ]
    tools = [
        {"type": "mcp_toolset", "mcp_server_name": "pubmed"},
        {"type": "mcp_toolset", "mcp_server_name": "open_targets"},
    ]

    # Wiley Scholar Gateway — no auth required
    if WILEY_MCP_URL:
        mcp_servers.append({
            "type": "url",
            "url": WILEY_MCP_URL,
            "name": "wiley",
        })
        tools.append({"type": "mcp_toolset", "mcp_server_name": "wiley"})

    if BIORENDER_TOKEN:
        mcp_servers.append({
            "type": "url",
            "url": BIORENDER_MCP_URL,
            "name": "biorender",
            "authorization_token": BIORENDER_TOKEN,
        })
        tools.append({"type": "mcp_toolset", "mcp_server_name": "biorender"})

    # Use the beta MCP connector
    response = client.beta.messages.create(
        model=CLAUDE_FAST_MODEL,
        max_tokens=4096,
        system=CONTEXT_SYSTEM,
        messages=[{"role": "user", "content": user_prompt}],
        mcp_servers=mcp_servers,
        tools=tools,
        betas=[MCP_BETA_HEADER],
    )

    # Extract the final text response (after all tool use)
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text = block.text
            break

    if not text:
        return BioContext()

    return _parse_context_response(text)


def _parse_context_response(text: str) -> BioContext:
    """Parse Claude's response into BioContext model."""
    # Strip markdown code fences if present
    if "```" in text:
        text = text.split("```json")[-1] if "```json" in text else text.split("```")[-2]
        text = text.strip().rstrip("`")

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return BioContext(narrative=text)

    # Build literature summary, handling both old and new field formats
    lit_data = data.get("literature", {})
    literature = LiteratureSummary(
        total_papers=lit_data.get("total_papers", 0),
        recent_papers=lit_data.get("recent_papers", 0),
        key_findings=lit_data.get("key_findings", []),
        sources=lit_data.get("sources", []),
        paper_titles=lit_data.get("paper_titles", []),
        dois=lit_data.get("dois", []),
    )

    return BioContext(
        narrative=data.get("narrative", ""),
        disease_associations=[
            DiseaseAssociation(**d) for d in data.get("disease_associations", [])
        ],
        drugs=[DrugCandidate(**d) for d in data.get("drugs", [])],
        literature=literature,
        pathways=data.get("pathways", []),
        suggested_experiments=data.get("suggested_experiments", []),
    )
