from __future__ import annotations

from src.background_tasks import (
    fetch_bio_context_background,
    generate_interpretation_background,
)
from src.models import BioContext, ProteinQuery, TrustAudit


class ContextService:
    @staticmethod
    def submit_background_context(query: ProteinQuery) -> None:
        from src.task_manager import task_manager

        task_manager.submit(
            task_id="bio_context",
            fn=fetch_bio_context_background,
            kwargs={
                "protein_name": query.protein_name,
                "uniprot_id": query.uniprot_id,
                "mutation": query.mutation,
                "question_type": query.question_type,
                "interaction_partner": query.interaction_partner,
                "sequence": query.sequence,
            },
            label="Biological context (PubMed, Open Targets, ChEMBL)",
        )

    @staticmethod
    def submit_background_interpretation(
        query: ProteinQuery,
        trust_audit: TrustAudit,
        bio_context: BioContext,
    ) -> None:
        from src.task_manager import task_manager

        task_manager.submit(
            task_id="interpretation",
            fn=generate_interpretation_background,
            kwargs={
                "protein_name": query.protein_name,
                "uniprot_id": query.uniprot_id,
                "mutation": query.mutation,
                "question_type": query.question_type,
                "interaction_partner": query.interaction_partner,
                "sequence": query.sequence,
                "trust_audit_dict": trust_audit,
                "bio_context_obj": bio_context,
            },
            label="AI interpretation",
        )

    @staticmethod
    def fetch_context_sync(query: ProteinQuery) -> BioContext:
        from src.models import BioContext

        try:
            from src.bio_context import fetch_bio_context_mcp

            context = fetch_bio_context_mcp(query)
            if context.narrative or context.disease_associations or context.drugs:
                return context
        except Exception:
            pass

        try:
            from src.bio_context_direct import fetch_bio_context_direct

            return fetch_bio_context_direct(query)
        except Exception:
            return BioContext()

    @staticmethod
    def generate_interpretation_sync(
        query: ProteinQuery,
        trust_audit: TrustAudit,
        bio_context: BioContext,
    ) -> str:
        try:
            from src.interpreter import generate_interpretation

            return generate_interpretation(query, trust_audit, bio_context)
        except Exception:
            from src.interpreter import _fallback_interpretation

            return _fallback_interpretation(query, trust_audit, bio_context)
