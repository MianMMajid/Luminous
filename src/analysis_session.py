from __future__ import annotations

from datetime import datetime
from typing import Any, MutableMapping

from pydantic import BaseModel, Field

from src.models import (
    BioContext,
    DiseaseAssociation,
    DrugCandidate,
    LiteratureSummary,
    PredictionResult,
    ProteinQuery,
    RegionConfidence,
    TrustAudit,
)
from src.trust_auditor import build_trust_audit
from src.utils import parse_pdb_plddt, safe_json_dumps


DEFAULT_SESSION_VALUES = {
    "query_input": "",
    "query_parsed": False,
    "parsed_query": None,
    "raw_query": "",
    "prediction_result": None,
    "trust_audit": None,
    "bio_context": None,
    "interpretation": None,
    "active_tab": "Lumi",
    "pipeline_running": False,
    "chat_messages": [],
    "tamarind_results": {},
    "playground_pinned": [],
    "playground_plan": None,
    "stats_data": None,
    "stats_results": None,
    "stats_survival_data": None,
    "_chat_thinking": False,
    "_interpretation_attempted": False,
    "experiment_tracker": {},
    "generated_hypotheses": None,
    "playground_inspiration": None,
    "structure_analysis": None,
}

ANALYSIS_RESET_KEYS = [
    "prediction_result",
    "trust_audit",
    "bio_context",
    "interpretation",
    "stats_data",
    "stats_results",
    "stats_survival_data",
    "structure_analysis",
    "generated_hypotheses",
    "panel_figure_data",
    "graphical_abstract_svg",
    "figure_checklist_state",
    "experiment_tracker",
    "sketch_image_bytes",
    "sketch_interpretation",
    "comparison_data",
    "playground_inspiration",
    "playground_pinned",
    "playground_plan",
    "esmfold_pdb",
    "docked_complex_pdb",
    "generated_video",
    "_interpretation_attempted",
    "_prediction_raw",
]

DYNAMIC_CACHE_PREFIXES = (
    "variant_data_",
    "alphamissense_",
    "domains_",
    "flexibility_",
    "pockets_",
    "struct_analysis_",
    "alphafold_",
    "biorender_results_",
    "tamarind_results_",
    "svg_diagram_",
    "svg_",
    "_dashboard_",
    "_variant_fetch_attempted_",
    "variant_enrichment_",
    "pdf_bytes_",
    "nma_traj_",
    "morph_traj_",
    "charge_",
    "struct_diff_",
    "electrostatics_data_",
    "html_report_",
    "figure_kit_",
    "cex_",
    "rcsb_pdb_id_",
    "biorender_prompt_",
)

PROJECT_PLAIN_KEYS = [
    "interpretation",
    "chat_messages",
    "experiment_tracker",
    "stats_data",
    "stats_results",
    "stats_survival_data",
    "structure_analysis",
    "generated_hypotheses",
    "panel_figure_data",
    "graphical_abstract_svg",
    "figure_checklist_state",
    "sketch_interpretation",
    "comparison_data",
    "playground_pinned",
    "playground_plan",
    "playground_inspiration",
    "sketch_image_bytes",
    "generated_video",
    "esmfold_pdb",
]

PROJECT_DYNAMIC_PREFIXES = (
    "variant_data_",
    "variant_enrichment_",
    "alphamissense_",
    "domains_",
    "flexibility_",
    "pockets_",
    "struct_analysis_",
    "alphafold_",
    "biorender_results_",
    "tamarind_results_",
    "svg_diagram_",
    "svg_",
    "pdf_bytes_",
    "html_report_",
    "figure_kit_",
    "rcsb_pdb_id_",
    "cex_",
    "biorender_prompt_",
    "electrostatics_data_",
    "nma_traj_",
    "morph_traj_",
    "charge_",
    "struct_diff_",
)


class AnalysisSession(BaseModel):
    raw_query: str = ""
    query_parsed: bool = False
    parsed_query: ProteinQuery | None = None
    prediction_result: PredictionResult | None = None
    trust_audit: TrustAudit | None = None
    bio_context: BioContext | None = None
    interpretation: str | None = None
    chat_messages: list[dict[str, Any]] = Field(default_factory=list)
    experiment_tracker: dict[str, Any] = Field(default_factory=dict)
    active_tab: str = "Lumi"
    pipeline_running: bool = False
    artifacts: dict[str, Any] = Field(default_factory=dict)


def ensure_session_defaults(session_state: MutableMapping[str, Any]) -> None:
    for key, value in DEFAULT_SESSION_VALUES.items():
        if key not in session_state:
            session_state[key] = value.copy() if isinstance(value, dict) else value[:] if isinstance(value, list) else value


def clear_tasks_safely() -> None:
    try:
        from src.task_manager import task_manager

        task_manager.clear()
    except Exception:
        pass


def reset_analysis_state(
    session_state: MutableMapping[str, Any],
    *,
    clear_query: bool = False,
    clear_tasks: bool = True,
) -> None:
    if clear_tasks:
        clear_tasks_safely()

    for key in ANALYSIS_RESET_KEYS:
        session_state[key] = None

    session_state["chat_messages"] = []
    session_state["playground_pinned"] = []
    session_state["_chat_thinking"] = False
    session_state["_interpretation_attempted"] = False

    if clear_query:
        session_state["parsed_query"] = None
        session_state["query_parsed"] = False
        session_state["raw_query"] = ""

    for key in list(session_state.keys()):
        if isinstance(key, str) and key.startswith(DYNAMIC_CACHE_PREFIXES):
            del session_state[key]


def set_parsed_query(
    session_state: MutableMapping[str, Any],
    parsed_query: ProteinQuery,
    raw_query: str,
) -> None:
    session_state["parsed_query"] = parsed_query
    session_state["raw_query"] = raw_query
    session_state["query_parsed"] = True


def store_prediction_result(
    session_state: MutableMapping[str, Any],
    *,
    pdb_content: str,
    confidence: dict,
    affinity: dict | None = None,
    source: str = "precomputed",
    skip_plddt: bool = False,
    chain_ids: list[str] | None = None,
    residue_ids: list[int] | None = None,
    plddt_per_residue: list[float] | None = None,
) -> PredictionResult:
    resolved_chain_ids = chain_ids or []
    resolved_residue_ids = residue_ids or []
    resolved_plddt = plddt_per_residue or []

    if pdb_content and not (resolved_chain_ids and resolved_residue_ids and resolved_plddt):
        try:
            resolved_chain_ids, resolved_residue_ids, resolved_plddt = parse_pdb_plddt(
                pdb_content
            )
        except Exception:
            resolved_chain_ids, resolved_residue_ids, resolved_plddt = [], [], []

    if skip_plddt:
        resolved_plddt = []

    prediction = PredictionResult(
        pdb_content=pdb_content,
        confidence_json=confidence,
        affinity_json=affinity,
        plddt_per_residue=resolved_plddt,
        chain_ids=resolved_chain_ids,
        residue_ids=resolved_residue_ids,
        compute_source=source,
    )
    session_state["prediction_result"] = prediction
    return prediction


def deserialize_bio_context(context_data: dict) -> BioContext:
    try:
        disease_assocs = []
        for item in context_data.get("disease_associations", []):
            try:
                disease_assocs.append(DiseaseAssociation(**item))
            except Exception:
                pass

        drugs = []
        for item in context_data.get("drugs", []):
            try:
                drugs.append(DrugCandidate(**item))
            except Exception:
                pass

        try:
            literature = LiteratureSummary(**context_data.get("literature", {}))
        except Exception:
            literature = LiteratureSummary()

        return BioContext(
            narrative=context_data.get("narrative", ""),
            disease_associations=disease_assocs,
            drugs=drugs,
            literature=literature,
            pathways=context_data.get("pathways", []),
            suggested_experiments=context_data.get("suggested_experiments", []),
        )
    except Exception:
        return BioContext(
            narrative=context_data.get("narrative", "Precomputed context (partial load).")
        )


def store_bio_context(
    session_state: MutableMapping[str, Any],
    context_data: dict | BioContext,
) -> BioContext:
    bio_context = (
        context_data if isinstance(context_data, BioContext) else deserialize_bio_context(context_data)
    )
    session_state["bio_context"] = bio_context
    return bio_context


def ensure_trust_audit(
    session_state: MutableMapping[str, Any],
    query: ProteinQuery,
    prediction: PredictionResult,
) -> TrustAudit:
    trust_audit = session_state.get("trust_audit")
    if trust_audit is not None:
        return trust_audit

    trust_audit = build_trust_audit(
        query,
        prediction.pdb_content,
        prediction.confidence_json,
        chain_ids=prediction.chain_ids if prediction.chain_ids else None,
        residue_ids=prediction.residue_ids if prediction.residue_ids else None,
        plddt_scores=prediction.plddt_per_residue if prediction.plddt_per_residue else None,
        is_experimental=(prediction.compute_source == "rcsb"),
    )
    session_state["trust_audit"] = trust_audit
    return trust_audit


def build_analysis_session(session_state: MutableMapping[str, Any]) -> AnalysisSession:
    artifacts: dict[str, Any] = {}
    for key in PROJECT_PLAIN_KEYS:
        value = session_state.get(key)
        if value is not None:
            artifacts[key] = value

    return AnalysisSession(
        raw_query=session_state.get("raw_query", ""),
        query_parsed=session_state.get("query_parsed", False),
        parsed_query=session_state.get("parsed_query"),
        prediction_result=session_state.get("prediction_result"),
        trust_audit=session_state.get("trust_audit"),
        bio_context=session_state.get("bio_context"),
        interpretation=session_state.get("interpretation"),
        chat_messages=session_state.get("chat_messages", []),
        experiment_tracker=session_state.get("experiment_tracker", {}),
        active_tab=session_state.get("active_tab", "Lumi"),
        pipeline_running=session_state.get("pipeline_running", False),
        artifacts=artifacts,
    )


def serialize_session_state(session_state: MutableMapping[str, Any]) -> dict:
    data: dict[str, Any] = {
        "luminous_project_version": "1.2",
        "saved_at": datetime.now().isoformat(),
    }

    analysis_session = build_analysis_session(session_state)
    if analysis_session.parsed_query is not None:
        data["parsed_query"] = analysis_session.parsed_query.model_dump()
    if analysis_session.prediction_result is not None:
        data["prediction_result"] = analysis_session.prediction_result.model_dump()
    if analysis_session.trust_audit is not None:
        data["trust_audit"] = analysis_session.trust_audit.model_dump()
    if analysis_session.bio_context is not None:
        data["bio_context"] = analysis_session.bio_context.model_dump()

    data["raw_query"] = analysis_session.raw_query
    data["query_parsed"] = analysis_session.query_parsed

    for key in PROJECT_PLAIN_KEYS:
        value = session_state.get(key)
        if value is None:
            continue
        try:
            safe_json_dumps(value)
            data[key] = value
        except (TypeError, ValueError):
            pass

    dynamic_caches: dict[str, Any] = {}
    for key, value in session_state.items():
        if isinstance(key, str) and key.startswith(PROJECT_DYNAMIC_PREFIXES):
            try:
                safe_json_dumps(value)
                dynamic_caches[key] = value
            except (TypeError, ValueError):
                pass
    if dynamic_caches:
        data["_dynamic_caches"] = dynamic_caches

    return data


def restore_session_state(
    session_state: MutableMapping[str, Any],
    data: dict,
) -> None:
    reset_analysis_state(session_state, clear_query=True, clear_tasks=True)

    if "parsed_query" in data:
        try:
            session_state["parsed_query"] = ProteinQuery(**data["parsed_query"])
        except Exception:
            pass
    if "raw_query" in data:
        session_state["raw_query"] = data["raw_query"]
    if "query_parsed" in data:
        session_state["query_parsed"] = data["query_parsed"]

    if "prediction_result" in data:
        try:
            session_state["prediction_result"] = PredictionResult(**data["prediction_result"])
        except Exception:
            pass

    if "trust_audit" in data:
        try:
            trust_audit_data = data["trust_audit"].copy()
            if "regions" in trust_audit_data:
                regions = []
                for region in trust_audit_data["regions"]:
                    try:
                        regions.append(RegionConfidence(**region))
                    except Exception:
                        pass
                trust_audit_data["regions"] = regions
            session_state["trust_audit"] = TrustAudit(**trust_audit_data)
        except Exception:
            pass

    if "bio_context" in data:
        try:
            bio_context_data = data["bio_context"].copy()
            if "disease_associations" in bio_context_data:
                bio_context_data["disease_associations"] = [
                    DiseaseAssociation(**item)
                    for item in bio_context_data["disease_associations"]
                    if isinstance(item, dict)
                ]
            if "drugs" in bio_context_data:
                bio_context_data["drugs"] = [
                    DrugCandidate(**item)
                    for item in bio_context_data["drugs"]
                    if isinstance(item, dict)
                ]
            if "literature" in bio_context_data:
                try:
                    bio_context_data["literature"] = LiteratureSummary(
                        **bio_context_data["literature"]
                    )
                except Exception:
                    bio_context_data["literature"] = LiteratureSummary()
            session_state["bio_context"] = BioContext(**bio_context_data)
        except Exception:
            pass

    if "interpretation" in data:
        session_state["interpretation"] = data["interpretation"]
    if "chat_messages" in data:
        session_state["chat_messages"] = data["chat_messages"]
    if "experiment_tracker" in data:
        session_state["experiment_tracker"] = data["experiment_tracker"]

    for key in PROJECT_PLAIN_KEYS:
        if key in data:
            session_state[key] = data[key]

    dynamic_caches = data.get("_dynamic_caches")
    if isinstance(dynamic_caches, dict):
        for key, value in dynamic_caches.items():
            session_state[key] = value
