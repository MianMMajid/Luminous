from __future__ import annotations

from datetime import datetime
from typing import Any, MutableMapping

from src.analysis_session import serialize_session_state, restore_session_state


class ProjectService:
    @staticmethod
    def serialize(session_state: MutableMapping[str, Any]) -> dict:
        return serialize_session_state(session_state)

    @staticmethod
    def restore(session_state: MutableMapping[str, Any], data: dict) -> None:
        restore_session_state(session_state, data)

    @staticmethod
    def filename(data: dict) -> str:
        protein = "unknown"
        mutation = ""
        if "parsed_query" in data:
            query_data = data["parsed_query"]
            protein = (
                query_data.get("protein_name", "unknown")
                if isinstance(query_data, dict)
                else "unknown"
            )
            parsed_mutation = (
                query_data.get("mutation", "") if isinstance(query_data, dict) else ""
            )
            if parsed_mutation:
                mutation = f"_{parsed_mutation}"

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_protein = "".join(char if char.isalnum() else "_" for char in protein)
        safe_mutation = "".join(char if char.isalnum() else "_" for char in mutation)
        return f"{safe_protein}{safe_mutation}_{timestamp}.json"
