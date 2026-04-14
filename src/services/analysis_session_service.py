from __future__ import annotations

from typing import Any, MutableMapping

from src.analysis_session import (
    AnalysisSession,
    build_analysis_session,
    ensure_session_defaults,
    ensure_trust_audit,
    reset_analysis_state,
    serialize_session_state,
    restore_session_state,
    set_parsed_query,
    store_bio_context,
    store_prediction_result,
)
from src.models import PredictionResult, ProteinQuery, TrustAudit


class AnalysisSessionService:
    @staticmethod
    def ensure_defaults(session_state: MutableMapping[str, Any]) -> None:
        ensure_session_defaults(session_state)

    @staticmethod
    def reset_analysis(
        session_state: MutableMapping[str, Any],
        *,
        clear_query: bool = False,
        clear_tasks: bool = True,
    ) -> None:
        reset_analysis_state(
            session_state, clear_query=clear_query, clear_tasks=clear_tasks
        )

    @staticmethod
    def set_query(
        session_state: MutableMapping[str, Any],
        parsed_query: ProteinQuery,
        raw_query: str,
    ) -> None:
        set_parsed_query(session_state, parsed_query, raw_query)

    @staticmethod
    def store_prediction(
        session_state: MutableMapping[str, Any],
        **kwargs,
    ) -> PredictionResult:
        return store_prediction_result(session_state, **kwargs)

    @staticmethod
    def store_bio_context(
        session_state: MutableMapping[str, Any],
        context_data,
    ):
        return store_bio_context(session_state, context_data)

    @staticmethod
    def ensure_trust_audit(
        session_state: MutableMapping[str, Any],
        query: ProteinQuery,
        prediction: PredictionResult,
    ) -> TrustAudit:
        return ensure_trust_audit(session_state, query, prediction)

    @staticmethod
    def build_session(session_state: MutableMapping[str, Any]) -> AnalysisSession:
        return build_analysis_session(session_state)

    @staticmethod
    def serialize(session_state: MutableMapping[str, Any]) -> dict:
        return serialize_session_state(session_state)

    @staticmethod
    def restore(session_state: MutableMapping[str, Any], data: dict) -> None:
        restore_session_state(session_state, data)
