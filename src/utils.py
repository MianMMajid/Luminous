from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path


# biotite is lazy-loaded in parse_pdb_plddt() to avoid ~0.5s startup cost


class SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types, Pydantic models, datetime, and bytes."""

    def default(self, obj):
        import base64

        if isinstance(obj, (bytes, bytearray)):
            return {"__bytes_b64__": base64.b64encode(obj).decode("ascii")}
        try:
            import numpy as np
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, np.bool_):
                return bool(obj)
        except ImportError:
            pass
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


def safe_json_dumps(obj, **kwargs) -> str:
    """JSON dumps with safe handling of numpy/Pydantic/datetime/bytes types."""
    kwargs.setdefault("cls", SafeJSONEncoder)
    return json.dumps(obj, **kwargs)


def _bytes_object_hook(obj: dict):
    """Decode ``{"__bytes_b64__": "..."}`` back to bytes on load."""
    if "__bytes_b64__" in obj and len(obj) == 1:
        import base64
        return base64.b64decode(obj["__bytes_b64__"])
    return obj


def safe_json_loads(text: str):
    """JSON loads that restores base64-encoded bytes produced by safe_json_dumps."""
    return json.loads(text, object_hook=_bytes_object_hook)


def trust_to_color(score: float) -> str:
    """Map pLDDT score (0-100) to color. Uses AlphaFold convention."""
    if score >= 90:
        return "#0053D6"  # deep blue — very high confidence
    elif score >= 70:
        return "#65CBF3"  # light blue — confident
    elif score >= 50:
        return "#FFDB13"  # yellow — low confidence
    else:
        return "#FF7D45"  # orange — very low confidence


def trust_to_label(score: float) -> str:
    if score >= 90:
        return "Very High"
    elif score >= 70:
        return "High"
    elif score >= 50:
        return "Low"
    else:
        return "Very Low"


def overall_confidence_level(score: float) -> str:
    if score >= 0.8:
        return "high"
    elif score >= 0.6:
        return "medium"
    else:
        return "low"


def confidence_emoji(level: str) -> str:
    """Shape-distinct indicators for colorblind accessibility."""
    return {"high": "✅", "medium": "⚠️", "low": "❌"}.get(level, "⚪")


def parse_pdb_plddt(pdb_content: str) -> tuple[list[str], list[int], list[float]]:
    """Extract per-residue pLDDT from PDB B-factor column.

    Returns (chain_ids, residue_ids, plddt_scores).
    """
    if not pdb_content or not pdb_content.strip():
        return [], [], []

    try:
        import biotite.structure.io.pdb as pdb
        pdb_file = pdb.PDBFile.read(io.StringIO(pdb_content))
        structure = pdb_file.get_structure(model=1, extra_fields=["b_factor"])
    except Exception:
        return [], [], []

    # Get CA atoms for per-residue data
    ca_mask = structure.atom_name == "CA"
    ca_atoms = structure[ca_mask]

    chain_ids = [c for c in ca_atoms.chain_id]
    residue_ids = [int(r) for r in ca_atoms.res_id]
    plddt_scores = [float(b) for b in ca_atoms.b_factor]

    return chain_ids, residue_ids, plddt_scores


def build_trust_annotations(
    chain_ids: list[str],
    residue_ids: list[int],
    plddt_scores: list[float],
    flags: dict[int, str] | None = None,
) -> list[dict]:
    """Build molviewspec annotation JSON for per-residue coloring."""
    annotations = []
    flags = flags or {}
    for chain, res_id, score in zip(chain_ids, residue_ids, plddt_scores):
        entry = {
            "label_asym_id": chain,
            "label_seq_id": res_id,
            "color": trust_to_color(score),
        }
        tooltip = f"Residue {res_id}: pLDDT {score:.1f} ({trust_to_label(score)})"
        if res_id in flags:
            tooltip += f"\n⚠ {flags[res_id]}"
        entry["tooltip"] = tooltip
        annotations.append(entry)
    return annotations


def compute_region_confidence(
    chain_ids: list[str],
    residue_ids: list[int],
    plddt_scores: list[float],
    window: int = 20,
) -> list[dict]:
    """Compute sliding-window region confidences."""
    if not residue_ids or not plddt_scores:
        return []

    # Ensure all lists are the same length to prevent IndexError
    min_len = min(len(chain_ids), len(residue_ids), len(plddt_scores))
    if min_len == 0:
        return []
    chain_ids = chain_ids[:min_len]
    residue_ids = residue_ids[:min_len]
    plddt_scores = plddt_scores[:min_len]

    regions = []
    i = 0
    while i < len(residue_ids):
        chain = chain_ids[i]
        start = residue_ids[i]
        end = min(start + window - 1, residue_ids[-1])

        # Collect scores in this window for this chain
        scores = []
        j = i
        while j < len(residue_ids) and residue_ids[j] <= end and chain_ids[j] == chain:
            scores.append(plddt_scores[j])
            j += 1

        if scores:
            avg = sum(scores) / len(scores)
            flag = None
            if avg < 50:
                flag = "Very low confidence region — interpret with extreme caution"
            elif avg < 70:
                flag = "Low confidence — consider experimental validation"

            regions.append({
                "chain": chain,
                "start_residue": start,
                "end_residue": residue_ids[j - 1] if j > i else end,
                "avg_plddt": round(avg, 1),
                "flag": flag,
            })
        i = j if j > i else i + 1

    return regions


_event_loop: asyncio.AbstractEventLoop | None = None


def run_async(coro):
    """Bridge async code into Streamlit's sync world.

    Reuses a single event loop to preserve httpx connection pools
    across calls within the same Streamlit session.
    """
    global _event_loop
    if _event_loop is None or _event_loop.is_closed():
        _event_loop = asyncio.new_event_loop()
    return _event_loop.run_until_complete(coro)


def load_precomputed(example_name: str) -> dict | None:
    """Load precomputed results for demo fallback."""
    base = Path("data/precomputed") / example_name
    if not base.exists():
        return None

    result = {}
    pdb_file = base / "structure.pdb"
    if pdb_file.exists():
        result["pdb"] = pdb_file.read_text()

    def _safe_json(path: Path):
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None

    conf_file = base / "confidence.json"
    if conf_file.exists():
        val = _safe_json(conf_file)
        if val is not None:
            result["confidence"] = val

    context_file = base / "context.json"
    if context_file.exists():
        val = _safe_json(context_file)
        if val is not None:
            result["context"] = val

    affinity_file = base / "affinity.json"
    if affinity_file.exists():
        val = _safe_json(affinity_file)
        if val is not None:
            result["affinity"] = val

    variants_file = base / "variants.json"
    if variants_file.exists():
        val = _safe_json(variants_file)
        if val is not None:
            result["variants"] = fix_variant_dict_keys(val)

    # Extended precomputed data (structure analysis, flexibility, pockets, interpretation)
    for key, filename in [
        ("structure_analysis", "structure_analysis.json"),
        ("flexibility", "flexibility.json"),
        ("pockets", "pockets.json"),
        ("interpretation", "interpretation.json"),
    ]:
        fpath = base / filename
        if fpath.exists():
            val = _safe_json(fpath)
            if val is not None:
                result[key] = val

    # Fix JSON key types: per-residue dicts need int keys (JSON only has string keys)
    if "structure_analysis" in result:
        result["structure_analysis"] = _fix_residue_dict_keys(result["structure_analysis"])

    # Fix pocket score keys (JSON serializes int keys as strings)
    if "pockets" in result and isinstance(result["pockets"], dict):
        rps = result["pockets"].get("residue_pocket_scores")
        if rps and isinstance(rps, dict):
            result["pockets"]["residue_pocket_scores"] = {
                int(k) if isinstance(k, str) and k.isdigit() else k: v
                for k, v in rps.items()
            }

    return result if result else None


def _fix_residue_dict_keys(analysis: dict) -> dict:
    """Convert string dict keys back to int for per-residue data after JSON roundtrip."""
    int_key_fields = [
        "sasa_per_residue", "sse_per_residue", "packing_density",
        "network_centrality", "contacts_per_residue",
    ]
    for field in int_key_fields:
        if field in analysis and isinstance(analysis[field], dict):
            converted = {}
            for k, v in analysis[field].items():
                try:
                    int_key = int(k)
                except (ValueError, TypeError):
                    int_key = k
                # Ensure numeric values are proper floats/ints
                if field == "sse_per_residue":
                    converted[int_key] = v  # keep as string ("a", "b", "c")
                elif isinstance(v, str):
                    try:
                        converted[int_key] = float(v)
                    except ValueError:
                        converted[int_key] = v
                else:
                    converted[int_key] = v
            analysis[field] = converted
    return analysis


def fix_variant_dict_keys(variants: dict) -> dict:
    """Convert pathogenic_positions string keys to int after JSON roundtrip."""
    if "pathogenic_positions" in variants and isinstance(variants["pathogenic_positions"], dict):
        converted = {}
        for k, v in variants["pathogenic_positions"].items():
            try:
                converted[int(k)] = v
            except (ValueError, TypeError):
                converted[k] = v
        variants["pathogenic_positions"] = converted
    return variants
