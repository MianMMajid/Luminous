from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, MutableMapping

from src.background_tasks import run_prediction_rcsb
from src.models import ProteinQuery
from src.services.analysis_session_service import AnalysisSessionService
from src.utils import load_precomputed


@dataclass
class PredictionDispatch:
    status: str
    message: str = ""
    skipped_backends: list[str] = field(default_factory=list)


class PredictionService:
    @staticmethod
    def run_prediction(
        query: ProteinQuery,
        session_state: MutableMapping[str, Any],
        *,
        backend: str,
        num_recycles: int = 3,
        use_msa: bool = True,
        predict_affinity: bool = True,
    ) -> PredictionDispatch:
        if backend == "auto" and PredictionService._apply_precomputed(query, session_state):
            return PredictionDispatch(
                status="loaded",
                message=f"Loaded Boltz-2 prediction for {query.protein_name}",
            )

        from src.task_manager import task_manager

        prediction_status = task_manager.status("prediction")
        if prediction_status and prediction_status.value == "running":
            return PredictionDispatch(
                status="running",
                message=(
                    "Structure prediction is running in the background. "
                    "You can explore other tabs while waiting — Lumi will notify you when it's done."
                ),
            )

        if query.sequence:
            dispatch = PredictionService._submit_background_prediction(
                query,
                backend=backend,
                num_recycles=num_recycles,
                use_msa=use_msa,
                predict_affinity=predict_affinity,
            )
            if dispatch.status == "submitted":
                return dispatch

        if backend in ("auto", "rcsb") and query.uniprot_id:
            if not prediction_status or prediction_status.value not in ("pending", "running"):
                task_manager.submit(
                    task_id="prediction",
                    fn=run_prediction_rcsb,
                    args=(query.uniprot_id,),
                    label=f"Fetching {query.uniprot_id} from RCSB PDB",
                )
            return PredictionDispatch(
                status="submitted",
                message=(
                    "Fetching experimental structure from RCSB PDB in the background. "
                    "Feel free to explore other tabs."
                ),
            )

        return PredictionDispatch(
            status="unavailable",
            message=(
                "No sequence or precomputed data available. "
                "Select an example or provide a protein sequence."
            ),
        )

    @staticmethod
    def _submit_background_prediction(
        query: ProteinQuery,
        *,
        backend: str,
        num_recycles: int,
        use_msa: bool,
        predict_affinity: bool,
    ) -> PredictionDispatch:
        from src.task_manager import task_manager

        skipped: list[str] = []

        if backend in ("auto", "tamarind"):
            from src.background_tasks import run_prediction_tamarind
            from src.config import TAMARIND_API_KEY

            if TAMARIND_API_KEY:
                task_manager.submit(
                    task_id="prediction",
                    fn=run_prediction_tamarind,
                    args=(query.sequence, query.protein_name, query.mutation),
                    kwargs={
                        "predict_affinity": predict_affinity,
                        "num_recycles": num_recycles,
                        "use_msa": use_msa,
                    },
                    label="Boltz-2 structure prediction (Tamarind)",
                    target_keys={"__direct__": "_prediction_raw"},
                )
                return PredictionDispatch(
                    status="submitted",
                    message=(
                        "Structure prediction submitted. "
                        "You can switch to other tabs — Lumi will notify you when it's ready."
                    ),
                )
            skipped.append("Tamarind (no API key)")

        if backend in ("auto", "modal"):
            from src.background_tasks import run_prediction_modal
            from src.modal_client import is_modal_available

            if is_modal_available():
                task_manager.submit(
                    task_id="prediction",
                    fn=run_prediction_modal,
                    args=(query.sequence, query.protein_name, query.mutation),
                    kwargs={"predict_affinity": predict_affinity},
                    label="Boltz-2 structure prediction (Modal H100)",
                    target_keys={"__direct__": "_prediction_raw"},
                )
                return PredictionDispatch(
                    status="submitted",
                    message=(
                        "Structure prediction submitted. "
                        "You can switch to other tabs — Lumi will notify you when it's ready."
                    ),
                    skipped_backends=skipped,
                )
            skipped.append("Modal (not configured)")

        return PredictionDispatch(
            status="unavailable",
            skipped_backends=skipped,
        )

    @staticmethod
    def _apply_precomputed(
        query: ProteinQuery,
        session_state: MutableMapping[str, Any],
    ) -> bool:
        example_map = {
            "TP53": "p53_r248w",
            "BRCA1": "brca1_c61g",
            "EGFR": "egfr_t790m",
            "INS": "insulin",
            "SPIKE": "spike_rbd",
            "HBA1": "hba1_hemoglobin",
        }
        example_name = example_map.get(query.protein_name.upper())
        if not example_name:
            return False

        precomputed = load_precomputed(example_name)
        if not precomputed or not precomputed.get("pdb"):
            return False

        confidence = dict(precomputed.get("confidence", {}))
        plddt_override = confidence.pop("plddt_per_residue", None)
        chain_override = confidence.pop("chain_ids", None)
        residue_override = confidence.pop("residue_ids", None)

        AnalysisSessionService.store_prediction(
            session_state,
            pdb_content=precomputed["pdb"],
            confidence=confidence,
            affinity=precomputed.get("affinity"),
            source="precomputed",
            chain_ids=chain_override,
            residue_ids=residue_override,
            plddt_per_residue=plddt_override,
        )

        if precomputed.get("context") and session_state.get("bio_context") is None:
            AnalysisSessionService.store_bio_context(session_state, precomputed["context"])

        if precomputed.get("variants"):
            variant_key = f"variant_data_{query.protein_name}"
            if session_state.get(variant_key) is None:
                session_state[variant_key] = precomputed["variants"]

        if precomputed.get("structure_analysis"):
            cache_key = f"struct_analysis_{query.protein_name}_{query.mutation}"
            if session_state.get(cache_key) is None:
                session_state[cache_key] = precomputed["structure_analysis"]
            if not session_state.get("structure_analysis"):
                session_state["structure_analysis"] = precomputed["structure_analysis"]

        if precomputed.get("flexibility"):
            flexibility_key = f"flexibility_{query.protein_name}"
            if session_state.get(flexibility_key) is None:
                session_state[flexibility_key] = precomputed["flexibility"]

        if precomputed.get("pockets"):
            pocket_key = f"pockets_{query.protein_name}"
            if session_state.get(pocket_key) is None:
                session_state[pocket_key] = precomputed["pockets"]

        if precomputed.get("interpretation") and session_state.get("interpretation") is None:
            interpretation_data = precomputed["interpretation"]
            session_state["interpretation"] = interpretation_data.get("text", "")

        return True
