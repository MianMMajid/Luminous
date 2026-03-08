"""Client wrapper for calling Modal Boltz-2 function from Streamlit.

Handles Modal unavailability gracefully — never crashes the app.
"""
from __future__ import annotations


def is_modal_available() -> bool:
    """Check if Modal is installed and has valid credentials."""
    try:
        import os

        import modal  # noqa: F401

        # Modal requires either MODAL_TOKEN_ID+MODAL_TOKEN_SECRET or an active profile
        if os.getenv("MODAL_TOKEN_ID") and os.getenv("MODAL_TOKEN_SECRET"):
            return True
        # Check if modal has a stored config/profile
        try:
            from modal._utils.config import _profile

            return _profile() is not None
        except Exception:
            pass
        return False
    except ImportError:
        return False


def run_modal_prediction(
    sequence: str,
    job_name: str,
    predict_affinity: bool = True,
) -> tuple[str, dict, dict | None]:
    """Run Boltz-2 prediction via Modal GPU.

    Returns (pdb_content, confidence_json, affinity_json).
    Raises RuntimeError on failure, ImportError if modal not installed.
    """
    import modal

    fn = modal.Function.from_name("luminous", "boltz_predict")
    result = fn.remote(sequence, job_name, predict_affinity)

    pdb = result.get("pdb", "")
    confidence = result.get("confidence", {})
    affinity = result.get("affinity")

    if not pdb:
        raise RuntimeError("Modal returned empty PDB content")

    return pdb, confidence, affinity
