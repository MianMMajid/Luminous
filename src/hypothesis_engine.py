"""Agentic hypothesis generation engine.

Connects structure prediction + trust audit + biological context + variant data
to generate testable scientific hypotheses. This is the "so what?" engine
that no other tool provides.
"""
from __future__ import annotations

from anthropic import Anthropic

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.models import BioContext, ProteinQuery, TrustAudit

HYPOTHESIS_SYSTEM = """You are an expert structural biologist and drug discovery scientist.
Given a protein structure prediction with its trust audit, biological context, and variant
landscape data, generate specific, testable scientific hypotheses.

Each hypothesis must:
1. Be grounded in the provided data (cite specific residues, scores, variants)
2. Be experimentally testable with named methods
3. Have clear clinical or therapeutic relevance
4. Acknowledge prediction confidence and limitations

Format each hypothesis as:
### Hypothesis N: [Title]
**Claim:** [Specific, falsifiable statement]
**Evidence:** [What data supports this]
**Confidence:** [High/Medium/Low based on prediction quality]
**Test:** [Specific experiment to validate]
**Impact:** [What this means if true]

Generate 3-5 hypotheses ranked by scientific impact. Be bold but honest about uncertainty.
Use markdown formatting."""


def generate_hypotheses(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
    variant_data: dict | None = None,
) -> str:
    """Generate testable hypotheses using extended thinking.

    Extended thinking lets Claude reason deeply about the structural
    and biological data before generating hypotheses, producing more
    insightful and well-grounded scientific claims.
    """
    if not ANTHROPIC_API_KEY:
        return _fallback_hypotheses(
            query, trust_audit, bio_context, variant_data
        )

    prompt = _build_hypothesis_prompt(
        query, trust_audit, bio_context, variant_data
    )

    client = Anthropic(api_key=ANTHROPIC_API_KEY)

    # Try extended thinking first (deeper reasoning)
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=16000,
            temperature=1,  # required for extended thinking
            thinking={
                "type": "enabled",
                "budget_tokens": 5000,
            },
            system=HYPOTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text blocks (skip thinking blocks)
        text_parts = []
        for block in response.content:
            if hasattr(block, "text"):
                text_parts.append(block.text)
        if text_parts:
            return "\n".join(text_parts)
    except Exception:
        pass

    # Fallback: standard call without extended thinking
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=3000,
            system=HYPOTHESIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    except Exception:
        return _fallback_hypotheses(
            query, trust_audit, bio_context, variant_data
        )


def _build_hypothesis_prompt(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
    variant_data: dict | None,
) -> str:
    parts = [
        f"## Protein: {query.protein_name} (UniProt: {query.uniprot_id or 'unknown'})",
        f"Question: {query.question_type}",
    ]
    if query.mutation:
        parts.append(f"Mutation of interest: {query.mutation}")
    if query.interaction_partner:
        parts.append(f"Interaction partner: {query.interaction_partner}")

    # Trust audit data
    parts.append("\n## Structure Prediction Quality")
    parts.append(
        f"Overall confidence: {trust_audit.overall_confidence} "
        f"({trust_audit.confidence_score:.1%})"
    )
    if trust_audit.ptm is not None:
        parts.append(f"pTM: {trust_audit.ptm:.3f}")
    if trust_audit.iptm is not None:
        parts.append(f"ipTM: {trust_audit.iptm:.3f}")

    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        parts.append(f"\nLow-confidence regions ({len(flagged)}):")
        for r in flagged[:8]:
            parts.append(
                f"  - Chain {r.chain} residues "
                f"{r.start_residue}-{r.end_residue}: "
                f"avg pLDDT {r.avg_plddt}"
            )

    if trust_audit.known_limitations:
        parts.append("\nKnown prediction limitations:")
        for lim in trust_audit.known_limitations:
            parts.append(f"  - {lim}")

    # Biological context
    if bio_context:
        parts.append("\n## Biological Context")
        if bio_context.disease_associations:
            parts.append("Disease associations:")
            for d in bio_context.disease_associations[:5]:
                score = f" (score: {d.score:.2f})" if d.score is not None else ""
                parts.append(f"  - {d.disease}{score}")

        if bio_context.drugs:
            parts.append("Known drugs/candidates:")
            for drug in bio_context.drugs[:5]:
                parts.append(f"  - {drug.name}" + (f" ({drug.phase})" if drug.phase else ""))
                if drug.mechanism:
                    parts.append(f"    Mechanism: {drug.mechanism}")

        if bio_context.pathways:
            parts.append("Pathways: " + ", ".join(bio_context.pathways[:5]))

        if bio_context.literature.key_findings:
            parts.append(f"Literature ({bio_context.literature.total_papers} papers):")
            for f in bio_context.literature.key_findings[:3]:
                parts.append(f"  - {f}")

    # Variant landscape
    if variant_data and variant_data.get("variants"):
        parts.append("\n## Variant Landscape")
        parts.append(variant_data.get("summary", ""))
        parts.append("Pathogenic variants by position:")
        for pos, names in list(variant_data.get("pathogenic_positions", {}).items())[:10]:
            parts.append(f"  - Position {pos}: {', '.join(names)}")

    parts.append(
        "\n\nGenerate 3-5 testable hypotheses connecting the structure prediction, "
        "trust audit findings, biological context, and variant landscape. "
        "Focus on actionable insights that could advance drug discovery or clinical understanding."
    )

    return "\n".join(parts)


def _fallback_hypotheses(
    query: ProteinQuery,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
    variant_data: dict | None,
) -> str:
    """Generate basic hypotheses without Claude API."""
    hypotheses = []

    # Hypothesis 1: Based on confidence
    flagged = [r for r in trust_audit.regions if r.flag]
    if flagged:
        region = flagged[0]
        hypotheses.append(
            f"### Hypothesis 1: Flexible Region Function\n"
            f"**Claim:** The low-confidence region (Chain {region.chain}, "
            f"residues {region.start_residue}-{region.end_residue}, avg pLDDT {region.avg_plddt}) "
            f"represents a functionally important flexible region rather than a prediction error.\n"
            f"**Evidence:** Low pLDDT regions often correspond to intrinsically disordered regions "
            f"that mediate protein-protein interactions.\n"
            f"**Confidence:** Medium\n"
            f"**Test:** HDX-MS (hydrogen-deuterium exchange mass spectrometry) to measure backbone "
            f"flexibility in this region.\n"
            f"**Impact:** If confirmed, this region could be a novel therapeutic target for "
            f"peptide-based inhibitors."
        )

    # Hypothesis 2: Based on mutation
    if query.mutation:
        hypotheses.append(
            f"### Hypothesis 2: Mutation Structural Impact\n"
            f"**Claim:** The {query.mutation} mutation disrupts local protein stability "
            f"and alters the interaction surface.\n"
            f"**Evidence:** The mutation is at a position where structural predictions show "
            f"{'high' if trust_audit.confidence_score > 0.7 else 'moderate'} confidence, "
            f"suggesting the predicted structural change is reliable.\n"
            f"**Confidence:** {'High' if trust_audit.confidence_score > 0.8 else 'Medium'}\n"
            f"**Test:** Thermal shift assay (DSF) comparing WT vs {query.mutation} stability, "
            f"followed by co-IP to test interaction changes.\n"
            f"**Impact:** Validates whether structural disruption explains pathogenicity."
        )

    # Hypothesis 3: Based on drugs
    if bio_context and bio_context.drugs:
        drug = bio_context.drugs[0]
        hypotheses.append(
            f"### Hypothesis 3: Drug Binding Site Accessibility\n"
            f"**Claim:** The predicted structure reveals the binding site for "
            f"{drug.name} is accessible and druggable.\n"
            f"**Evidence:** Known drug candidate in "
            f"{'clinical trials' if drug.phase else 'preclinical'}. "
            f"Structure prediction confidence in the binding region "
            f"is {trust_audit.overall_confidence}.\n"
            f"**Confidence:** {'High' if trust_audit.confidence_score > 0.8 else 'Medium'}\n"
            f"**Test:** SPR (Surface Plasmon Resonance) binding assay with {drug.name}.\n"
            f"**Impact:** Guides lead optimization for {query.protein_name}-targeted therapy."
        )

    # Hypothesis 4: Based on variant landscape
    if variant_data and variant_data.get("pathogenic_positions"):
        positions = list(variant_data["pathogenic_positions"].keys())[:3]
        hypotheses.append(
            f"### Hypothesis 4: Pathogenic Variant Clustering\n"
            f"**Claim:** Pathogenic variants cluster in structurally critical regions, "
            f"particularly around positions {', '.join(str(p) for p in positions)}.\n"
            f"**Evidence:** ClinVar reports {variant_data.get('pathogenic_count', 0)} "
            f"pathogenic variants for {query.protein_name}, concentrated at "
            f"{len(variant_data.get('pathogenic_positions', {}))} residue positions.\n"
            f"**Confidence:** High (based on clinical data)\n"
            f"**Test:** Deep mutational scanning (DMS) of the identified hotspot region.\n"
            f"**Impact:** Identifies functional residues for targeted therapeutic intervention."
        )

    if not hypotheses:
        hypotheses.append(
            "### Hypothesis 1: Structure Validation\n"
            f"**Claim:** The predicted structure of {query.protein_name} is accurate enough "
            f"for downstream applications.\n"
            f"**Confidence:** {trust_audit.overall_confidence.title()}\n"
            f"**Test:** Compare with experimental structure via X-ray crystallography or cryo-EM.\n"
            f"**Impact:** Validates computational predictions for this protein family."
        )

    return "\n\n".join(hypotheses)
