from __future__ import annotations

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import BioContext, ProteinQuery, TrustAudit

INTERPRET_SYSTEM = """\
You are a structural biologist interpreting an AI-predicted protein structure.
Given the protein query, trust audit results, biological context data, and any
additional computational analyses from Tamarind Bio's tool suite, provide a
clear, scientifically accurate interpretation.

Your interpretation should:
1. Summarize the key structural findings
2. Highlight confidence concerns from the trust audit
3. Connect structural features to biological function and disease
4. Integrate any Tamarind Bio analysis results (docking, stability, etc.)
5. Suggest actionable next steps — reference specific Tamarind Bio tools
   when relevant (e.g., "Run ProteinMPNN-ddG to quantify the stability
   impact" or "Use BoltzGen to design binders targeting this interface")
6. Be honest about limitations and uncertainties

IMPORTANT: You are provided with source documents containing biological
context data. You MUST cite these documents when making claims. The
citations system will automatically track your references — just make
claims that are grounded in the provided documents.

Write in clear scientific prose suitable for a researcher who is not a
structural biologist. Use markdown formatting. Be concise but thorough."""


def generate_interpretation(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext,
) -> str:
    """Generate Claude-powered interpretation with citations.

    Uses the Citations API to ground claims in the bio_context data,
    producing verifiable, source-attributed interpretations.
    """
    if not ANTHROPIC_API_KEY:
        return _fallback_interpretation(query, trust_audit, bio_context)

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Build documents for the Citations API
    documents = _build_citation_documents(
        query, trust_audit, bio_context
    )
    prompt_text = _build_prompt(query, trust_audit)

    # Assemble user content: documents first, then the question
    user_content: list[dict] = []
    for doc in documents:
        user_content.append(doc)
    user_content.append({"type": "text", "text": prompt_text})

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=INTERPRET_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        return _format_cited_response(message.content)
    except Exception:
        # Fallback to non-citation call if citations fail
        try:
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=2048,
                system=INTERPRET_SYSTEM,
                messages=[{
                    "role": "user",
                    "content": _build_prompt_full(
                        query, trust_audit, bio_context
                    ),
                }],
            )
            return message.content[0].text
        except Exception:
            return _fallback_interpretation(
                query, trust_audit, bio_context
            )


def _build_citation_documents(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext,
) -> list[dict]:
    """Build document content blocks for the Citations API."""
    documents = []

    # Document 1: Trust Audit data
    audit_lines = [
        f"Overall confidence: {trust_audit.overall_confidence} "
        f"({trust_audit.confidence_score:.2%})",
    ]
    if trust_audit.ptm is not None:
        audit_lines.append(f"pTM score: {trust_audit.ptm:.3f}")
    if trust_audit.iptm is not None:
        audit_lines.append(f"ipTM score: {trust_audit.iptm:.3f}")
    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        audit_lines.append(
            f"{len(flagged)} flagged regions with low confidence:"
        )
        for r in flagged[:5]:
            audit_lines.append(
                f"  Chain {r.chain} residues {r.start_residue}-"
                f"{r.end_residue}: avg pLDDT {r.avg_plddt} "
                f"({r.flag})"
            )
    if trust_audit.known_limitations:
        audit_lines.append("Known limitations:")
        for lim in trust_audit.known_limitations[:5]:
            audit_lines.append(f"  - {lim}")
    if trust_audit.training_data_note:
        audit_lines.append(
            f"Training data note: {trust_audit.training_data_note}"
        )
    if trust_audit.suggested_validation:
        audit_lines.append("Suggested validation experiments:")
        for sv in trust_audit.suggested_validation[:5]:
            audit_lines.append(f"  - {sv}")

    documents.append({
        "type": "document",
        "source": {
            "type": "text",
            "media_type": "text/plain",
            "data": "\n".join(audit_lines),
        },
        "title": f"Trust Audit — {query.protein_name}",
        "citations": {"enabled": True},
    })

    # Document 2: Narrative / gene context
    if bio_context.narrative:
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": bio_context.narrative,
            },
            "title": f"Biological Context — {query.protein_name}",
            "citations": {"enabled": True},
        })

    # Document 3: Disease associations
    if bio_context.disease_associations:
        disease_text = "\n".join(
            f"{d.disease}"
            + (f" (score: {d.score})" if d.score else "")
            + (f" — {d.evidence}" if d.evidence else "")
            for d in bio_context.disease_associations[:10]
        )
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": disease_text,
            },
            "title": "Disease Associations",
            "citations": {"enabled": True},
        })

    # Document 4: Drug data
    if bio_context.drugs:
        drug_lines = []
        for drug in bio_context.drugs[:10]:
            line = drug.name
            if drug.phase:
                line += f" ({drug.phase})"
            if drug.mechanism:
                line += f" — {drug.mechanism}"
            drug_lines.append(line)
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": "\n".join(drug_lines),
            },
            "title": "Drug Candidates & Therapeutics",
            "citations": {"enabled": True},
        })

    # Document 5: Literature findings
    if bio_context.literature.key_findings:
        lit_text = "\n".join(
            bio_context.literature.key_findings[:10]
        )
        documents.append({
            "type": "document",
            "source": {
                "type": "text",
                "media_type": "text/plain",
                "data": lit_text,
            },
            "title": (
                f"Recent Literature "
                f"({bio_context.literature.total_papers} papers)"
            ),
            "citations": {"enabled": True},
        })

    return documents


def _format_cited_response(content_blocks: list) -> str:
    """Format a Citations API response into markdown with footnotes.

    Converts citation blocks into [n] footnote references with a
    Sources section at the bottom.
    """
    text_parts: list[str] = []
    sources: list[str] = []
    source_map: dict[str, int] = {}

    for block in content_blocks:
        if not hasattr(block, "text"):
            continue

        citations = getattr(block, "citations", None) or []
        if citations:
            # Text with citations — add footnote references
            text = block.text
            refs = []
            for cite in citations:
                doc_title = getattr(
                    cite, "document_title", None
                ) or "Source"
                cited_text = getattr(
                    cite, "cited_text", None
                ) or ""

                # Deduplicate sources by title+text
                key = f"{doc_title}:{cited_text[:80]}"
                if key not in source_map:
                    source_map[key] = len(sources) + 1
                    excerpt = (
                        cited_text[:120] + "..."
                        if len(cited_text) > 120
                        else cited_text
                    )
                    sources.append(
                        f"**[{source_map[key]}]** "
                        f"*{doc_title}* — \"{excerpt}\""
                    )
                refs.append(str(source_map[key]))

            ref_str = ",".join(refs)
            text_parts.append(f"{text} [{ref_str}]")
        else:
            text_parts.append(block.text)

    result = "".join(text_parts)

    if sources:
        result += "\n\n---\n### Sources\n"
        result += "\n".join(sources)

    return result


def _build_prompt(
    query: ProteinQuery,
    trust_audit: TrustAudit,
) -> str:
    """Build the user question (documents are separate)."""
    parts = [
        f"## Protein: {query.protein_name}",
        f"Question type: {query.question_type}",
    ]
    if query.mutation:
        parts.append(f"Mutation: {query.mutation}")
    if query.interaction_partner:
        parts.append(f"Interaction partner: {query.interaction_partner}")
    parts.append(
        "\nUsing the source documents provided, give a comprehensive "
        "interpretation of this protein's structure prediction. "
        "Cite the documents when making claims."
    )
    return "\n".join(parts)


def _build_prompt_full(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext,
) -> str:
    """Build a full prompt with inline context (fallback, no citations)."""
    parts = [
        f"## Protein: {query.protein_name}",
        f"Question type: {query.question_type}",
    ]
    if query.mutation:
        parts.append(f"Mutation: {query.mutation}")
    if query.interaction_partner:
        parts.append(
            f"Interaction partner: {query.interaction_partner}"
        )

    parts.append("\n## Trust Audit")
    parts.append(
        f"Overall confidence: {trust_audit.overall_confidence} "
        f"({trust_audit.confidence_score:.2%})"
    )
    if trust_audit.ptm is not None:
        parts.append(f"pTM: {trust_audit.ptm:.3f}")
    if trust_audit.iptm is not None:
        parts.append(f"ipTM: {trust_audit.iptm:.3f}")

    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        parts.append(f"\nFlagged regions ({len(flagged)}):")
        for r in flagged[:5]:
            parts.append(
                f"  - Chain {r.chain} {r.start_residue}-"
                f"{r.end_residue}: avg pLDDT {r.avg_plddt} "
                f"- {r.flag}"
            )

    if trust_audit.known_limitations:
        parts.append("\nKnown limitations:")
        for lim in trust_audit.known_limitations[:5]:
            parts.append(f"  - {lim}")
    if trust_audit.training_data_note:
        parts.append(
            f"\nTraining data: {trust_audit.training_data_note}"
        )

    parts.append("\n## Biological Context")
    if bio_context.narrative:
        parts.append(bio_context.narrative)
    if bio_context.disease_associations:
        parts.append("\nDisease associations:")
        for d in bio_context.disease_associations[:5]:
            parts.append(
                f"  - {d.disease}"
                + (f" (score: {d.score})" if d.score else "")
            )
    if bio_context.drugs:
        parts.append("\nKnown drugs/candidates:")
        for drug in bio_context.drugs[:5]:
            parts.append(
                f"  - {drug.name}"
                + (f" ({drug.phase})" if drug.phase else "")
            )
    if bio_context.literature.key_findings:
        parts.append(
            f"\nRecent literature "
            f"({bio_context.literature.total_papers} papers):"
        )
        for finding in bio_context.literature.key_findings[:3]:
            parts.append(f"  - {finding}")

    parts.append("\nPlease provide a comprehensive interpretation.")
    return "\n".join(parts)


def _fallback_interpretation(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext,
) -> str:
    """Generate basic interpretation without Claude API."""
    lines = [
        f"## Structure Prediction Summary for {query.protein_name}",
        "",
        f"**Overall Confidence:** {trust_audit.overall_confidence} "
        f"({trust_audit.confidence_score:.1%})",
        "",
    ]

    if query.mutation:
        lines.append(f"**Mutation:** {query.mutation}")
        lines.append("")

    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        lines.append(
            f"**Warning:** {len(flagged)} region(s) have low "
            "confidence scores."
        )
        lines.append(
            "These regions should be interpreted with caution."
        )
        lines.append("")

    if trust_audit.known_limitations:
        lines.append("### Known Limitations")
        for lim in trust_audit.known_limitations[:3]:
            lines.append(f"- {lim}")
        lines.append("")

    if trust_audit.suggested_validation:
        lines.append("### Suggested Validation")
        for s in trust_audit.suggested_validation:
            lines.append(f"- {s}")
        lines.append("")

    if bio_context.disease_associations:
        lines.append("### Disease Associations")
        for d in bio_context.disease_associations[:5]:
            lines.append(f"- {d.disease}")
        lines.append("")

    lines.append(
        "*Full AI interpretation requires an Anthropic API key.*"
    )
    return "\n".join(lines)
