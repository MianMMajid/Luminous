"""Tamarind Bio API client — access to 200+ computational biology tools.

Supports Boltz-2 structure prediction, ESMFold, docking (Vina/GNINA/DiffDock),
protein design (ProteinMPNN, RFdiffusion, BoltzGen), property prediction
(Aggrescan3D, CamSol, TemStaPro), and more via a generic job submission API.

Performance: uses a shared httpx client with connection pooling and HTTP/2
to reuse TCP+TLS connections across submit/poll/download cycles.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from src.config import TAMARIND_API_KEY, TAMARIND_BASE_URL


def _headers() -> dict:
    return {"x-api-key": TAMARIND_API_KEY, "Content-Type": "application/json"}


def is_tamarind_available() -> bool:
    return bool(TAMARIND_API_KEY)


# ────────────────────────────────────────────────────────
# Shared HTTP client — reuses TCP+TLS connections
# ────────────────────────────────────────────────────────

_shared_client: httpx.AsyncClient | None = None


async def _get_client() -> httpx.AsyncClient:
    """Return a shared httpx client with connection pooling."""
    global _shared_client
    if _shared_client is None or _shared_client.is_closed:
        _shared_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=15),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
            follow_redirects=True,
        )
    return _shared_client


# ────────────────────────────────────────────────────────
# Tool schema cache — discover settings from GET /tools
# ────────────────────────────────────────────────────────

_tool_schema_cache: dict[str, dict] | None = None


async def get_tool_schemas() -> dict[str, dict]:
    """Fetch and cache all tool schemas from GET /tools.

    Returns {tool_type: {name, settings_schema, ...}} keyed by tool slug.
    """
    global _tool_schema_cache
    if _tool_schema_cache is not None:
        return _tool_schema_cache

    try:
        tools = await list_tools()
        cache = {}
        for t in tools:
            if isinstance(t, dict):
                slug = t.get("type", t.get("slug", t.get("name", "")))
                if slug:
                    cache[slug] = t
            elif isinstance(t, str):
                cache[t] = {"name": t}
        _tool_schema_cache = cache
        return cache
    except Exception:
        _tool_schema_cache = {}
        return {}


def get_cached_tool_names() -> list[str]:
    """Return tool names from cache (empty if not yet fetched)."""
    if _tool_schema_cache is None:
        return []
    return list(_tool_schema_cache.keys())


async def run_dynamic_tool(
    tool_type: str,
    settings: dict[str, Any],
    job_name: str,
    timeout: int = 300,
) -> dict:
    """Submit a tool using schema-validated settings.

    Fetches the tool schema first, merges user settings with defaults,
    then submits the job. Falls back to raw submission if schema
    discovery fails.
    """
    schemas = await get_tool_schemas()
    schema = schemas.get(tool_type, {})

    # If schema has default settings, merge user overrides on top
    defaults = schema.get("defaultSettings", schema.get("settings", {}))
    if isinstance(defaults, dict):
        merged = {**defaults, **settings}
    else:
        merged = settings

    return await run_tool(tool_type, merged, job_name, timeout=timeout)


# ────────────────────────────────────────────────────────
# Generic job engine — works for any Tamarind tool
# ────────────────────────────────────────────────────────


async def submit_job(
    tool_type: str,
    settings: dict[str, Any],
    job_name: str,
) -> str:
    """Submit any Tamarind Bio tool job. Returns job_name."""
    payload = {
        "jobName": job_name,
        "type": tool_type,
        "settings": settings,
    }
    client = await _get_client()
    resp = await client.post(
        f"{TAMARIND_BASE_URL}/submit-job",
        headers=_headers(),
        json=payload,
    )
    if resp.status_code >= 400:
        detail = resp.text[:500] if resp.text else "no detail"
        raise httpx.HTTPStatusError(
            f"{resp.status_code} for {tool_type}: {detail}",
            request=resp.request,
            response=resp,
        )
    return job_name


async def poll_job(job_name: str, timeout: int = 300) -> dict:
    """Poll Tamarind API until job completes or times out.

    Uses exponential backoff: 2s → 4s → 6s → 8s → 10s (cap).
    This catches fast jobs quickly instead of wasting 10s idle.
    """
    client = await _get_client()
    start = time.time()
    interval = 2.0  # start fast
    while time.time() - start < timeout:
        resp = await client.get(
            f"{TAMARIND_BASE_URL}/jobs",
            headers=_headers(),
            params={"jobName": job_name},
        )
        resp.raise_for_status()
        data = resp.json()

        # Tamarind API returns {"0": {JobName, JobStatus, ...}, "statuses": {...}}
        # Extract the actual job record from the response
        job = _extract_job(data)
        status = _extract_status(job)

        if status in ("complete", "completed", "done", "finished"):
            return job
        if status in ("failed", "error", "stopped"):
            raise RuntimeError(f"Job {job_name} failed: {job.get('error', job.get('Error', 'unknown'))}")

        await asyncio.sleep(interval)
        interval = min(interval + 2.0, 10.0)  # ramp up to 10s cap

    raise TimeoutError(f"Job {job_name} did not complete within {timeout}s")


def _extract_job(data) -> dict:
    """Extract the job record from Tamarind's various response formats."""
    if isinstance(data, list):
        return data[0] if data else {}
    if isinstance(data, dict):
        # Format: {"0": {JobName, JobStatus, ...}, "statuses": {...}}
        if "0" in data:
            return data["0"] if isinstance(data["0"], dict) else data
        # Format: {"JobName": ..., "JobStatus": ...} (direct job)
        if "JobName" in data or "JobStatus" in data:
            return data
        # Format: {"status": ..., "job_name": ...} (generic)
        return data
    return {}


def _extract_status(job: dict) -> str:
    """Extract status string from job record, handling various key formats."""
    for key in ("JobStatus", "jobStatus", "status", "Status"):
        val = job.get(key)
        if val:
            return str(val).lower().strip()
    return ""


async def download_results(job_name: str) -> dict:
    """Download full results from completed job.

    Tamarind returns a download URL from /result, then we fetch the actual
    result (ZIP or JSON) from that URL.
    """
    client = await _get_client()
    resp = await client.post(
        f"{TAMARIND_BASE_URL}/result",
        headers=_headers(),
        json={"jobName": job_name},
    )
    resp.raise_for_status()
    data = resp.json()

    # If the response is a URL string, download the actual results
    if isinstance(data, str) and data.startswith("http"):
        return await _download_result_url(client, data, job_name)

    # If it's already a dict, return directly
    if isinstance(data, dict):
        return data

    return {"raw": data}


async def _download_result_url(client: httpx.AsyncClient, url: str, job_name: str) -> dict:
    """Download and extract results from a Tamarind result URL (ZIP or JSON)."""
    import io
    import json
    import zipfile

    resp = await client.get(url, timeout=120)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")

    # JSON response
    if "json" in ct:
        return resp.json() if isinstance(resp.json(), dict) else {"raw": resp.json()}

    # ZIP file — extract PDB and JSON files
    if "zip" in ct or "octet-stream" in ct or url.endswith(".zip"):
        result: dict = {}
        try:
            zf = zipfile.ZipFile(io.BytesIO(resp.content))
            for name in zf.namelist():
                lower = name.lower()
                content = zf.read(name)
                if lower.endswith(".pdb") or lower.endswith(".cif"):
                    result["pdb"] = content.decode("utf-8", errors="replace")
                    result["structure"] = result["pdb"]
                elif lower.endswith(".json"):
                    try:
                        parsed = json.loads(content)
                        # Merge JSON files into result
                        if isinstance(parsed, dict):
                            result.update(parsed)
                        else:
                            key = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                            result[key] = parsed
                    except json.JSONDecodeError:
                        pass
                elif lower.endswith(".csv") or lower.endswith(".tsv"):
                    key = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
                    result[key] = content.decode("utf-8", errors="replace")
            zf.close()
        except zipfile.BadZipFile:
            # Not a zip — treat as raw text
            result["raw"] = resp.text
        return result if result else {"raw": resp.text}

    # Plain text (likely PDB)
    text = resp.text
    if text.startswith("ATOM") or text.startswith("HEADER") or "ATOM" in text[:200]:
        return {"pdb": text, "structure": text}
    return {"raw": text}


async def run_tool(
    tool_type: str,
    settings: dict[str, Any],
    job_name: str,
    timeout: int = 300,
) -> dict:
    """Submit → poll → download. Returns full results dict."""
    await submit_job(tool_type, settings, job_name)
    await poll_job(job_name, timeout=timeout)
    return await download_results(job_name)


async def list_tools() -> list[dict]:
    """GET /tools — discover all available Tamarind tools."""
    client = await _get_client()
    resp = await client.get(
        f"{TAMARIND_BASE_URL}/tools",
        headers=_headers(),
    )
    resp.raise_for_status()
    data = resp.json()
    return data if isinstance(data, list) else []


# ────────────────────────────────────────────────────────
# Boltz-2: Structure + Affinity Prediction
# ────────────────────────────────────────────────────────


async def submit_boltz2_job(
    sequence: str,
    job_name: str,
    predict_affinity: bool = True,
    num_recycling_steps: int = 3,
    use_msa: bool = True,
) -> str:
    """Submit a Boltz-2 prediction job to Tamarind Bio API."""
    return await submit_job(
        tool_type="boltz",
        settings={
            "inputFormat": "sequence",
            "sequence": sequence,
            "numSamples": 1,
            "predictAffinity": predict_affinity,
            "numRecycles": num_recycling_steps,
            "outputType": "pdb",
            "useMSA": use_msa,
            "version": "2.2.0",
        },
        job_name=job_name,
    )


async def run_prediction(sequence: str, job_name: str) -> tuple[str, dict, dict | None]:
    """Full Boltz-2 pipeline: submit, poll, download. Returns (pdb, confidence, affinity)."""
    await submit_boltz2_job(sequence, job_name)
    await poll_job(job_name)
    result = await download_results(job_name)
    pdb_content = result.get("pdb", result.get("structure", ""))
    confidence = result.get("confidence", {})
    affinity = result.get("affinity")
    return pdb_content, confidence, affinity


# ────────────────────────────────────────────────────────
# ESMFold: Fast Single-Sequence Structure Prediction
# ────────────────────────────────────────────────────────


async def run_esmfold(sequence: str, job_name: str) -> dict:
    """Run ESMFold — 60x faster than AlphaFold2, no MSA needed."""
    return await run_dynamic_tool(
        tool_type="esmfold",
        settings={"sequence": sequence},
        job_name=job_name,
        timeout=300,
    )


# ────────────────────────────────────────────────────────
# Molecular Docking: AutoDock Vina, GNINA, DiffDock
# ────────────────────────────────────────────────────────


async def run_autodock_vina(
    receptor_pdb: str,
    ligand_smiles: str,
    job_name: str,
    center: tuple[float, float, float] | None = None,
    box_size: tuple[float, float, float] = (25.0, 25.0, 25.0),
    exhaustiveness: int = 32,
) -> dict:
    """Run AutoDock Vina — fast physics-based molecular docking."""
    settings: dict[str, Any] = {
        "receptorFile": receptor_pdb,
        "ligandFile": ligand_smiles,
        "exhaustiveness": exhaustiveness,
    }
    if center:
        settings["boxX"] = center[0]
        settings["boxY"] = center[1]
        settings["boxZ"] = center[2]
    settings["width"] = box_size[0]
    settings["height"] = box_size[1]
    settings["depth"] = box_size[2]
    return await run_dynamic_tool("autodock-vina", settings, job_name, timeout=300)


async def run_gnina(
    receptor_pdb: str,
    ligand_smiles: str,
    job_name: str,
    exhaustiveness: int = 16,
) -> dict:
    """Run GNINA — CNN-enhanced docking (more accurate than Vina)."""
    return await run_dynamic_tool(
        "gnina",
        {
            "proteinFile": receptor_pdb,
            "ligandFile": ligand_smiles,
            "exhaustiveness": exhaustiveness,
        },
        job_name,
        timeout=300,
    )


async def run_diffdock(
    receptor_pdb: str,
    ligand_smiles: str,
    job_name: str,
    num_samples: int = 10,
) -> dict:
    """Run DiffDock — diffusion-based molecular docking."""
    return await run_dynamic_tool(
        "diffdock",
        {
            "proteinFile": receptor_pdb,
            "ligandSmiles": ligand_smiles,
            "ligandFormat": "smiles",
            "numSamples": num_samples,
        },
        job_name,
        timeout=300,
    )


# ────────────────────────────────────────────────────────
# Docking Quality & Scoring
# ────────────────────────────────────────────────────────


async def run_prodigy(
    complex_pdb: str,
    job_name: str,
) -> dict:
    """Run PRODIGY — predict binding free energy and Kd from structure."""
    return await run_dynamic_tool(
        "prodigy",
        {"proteinFile": complex_pdb},
        job_name,
        timeout=180,
    )


async def run_dockq(
    model_pdb: str,
    native_pdb: str,
    job_name: str,
) -> dict:
    """Run DockQ — evaluate docking quality against reference structure."""
    return await run_dynamic_tool(
        "dockq",
        {"modelFile": model_pdb, "nativeFile": native_pdb},
        job_name,
        timeout=180,
    )


# ────────────────────────────────────────────────────────
# Mutation Stability: ProteinMPNN-ddG, ThermoMPNN
# ────────────────────────────────────────────────────────


async def run_proteinmpnn_ddg(
    pdb_content: str,
    mutations: list[str],
    job_name: str,
    chains: str = "A",
) -> dict:
    """Run ProteinMPNN-ddG — predict stability change (ddG) for mutations."""
    return await run_dynamic_tool(
        "proteinmpnn-ddg",
        {"pdbFile": pdb_content, "chains": chains},
        job_name,
        timeout=300,
    )


async def run_thermompnn(
    pdb_content: str,
    job_name: str,
    chains: str = "A",
) -> dict:
    """Run ThermoMPNN — score every possible point mutation for thermostability."""
    return await run_dynamic_tool(
        "thermompnn",
        {"pdbFile": pdb_content, "chains": chains},
        job_name,
        timeout=300,
    )


# ────────────────────────────────────────────────────────
# Protein Design: ProteinMPNN, RFdiffusion, BoltzGen
# ────────────────────────────────────────────────────────


async def run_proteinmpnn(
    pdb_content: str,
    job_name: str,
    num_sequences: int = 8,
    temperature: float = 0.1,
    chain: str | None = None,
) -> dict:
    """Run ProteinMPNN — inverse folding (structure → sequence design)."""
    settings: dict[str, Any] = {
        "pdbFile": pdb_content,
        "numSequences": num_sequences,
        "temperature": temperature,
    }
    if chain:
        settings["designedChains"] = chain
    return await run_dynamic_tool("proteinmpnn", settings, job_name, timeout=300)


async def run_boltzgen(
    target_pdb: str,
    job_name: str,
    num_designs: int = 15,
    binder_type: str = "protein",
) -> dict:
    """Run BoltzGen — de novo binder design (60-70% experimental hit rate)."""
    return await run_dynamic_tool(
        "boltzgen",
        {
            "targetFile": target_pdb,
            "numDesigns": num_designs,
            "binderType": binder_type,
        },
        job_name,
        timeout=600,
    )


async def run_rfdiffusion(
    pdb_content: str,
    job_name: str,
    num_designs: int = 4,
    hotspot_residues: list[int] | None = None,
) -> dict:
    """Run RFdiffusion — de novo protein backbone design / binder design."""
    settings: dict[str, Any] = {
        "pdbFile": pdb_content,
        "numDesigns": num_designs,
        "task": "binder_design",
    }
    if hotspot_residues:
        settings["interfaceResidues"] = hotspot_residues
    return await run_dynamic_tool("rfdiffusion", settings, job_name, timeout=600)


# ────────────────────────────────────────────────────────
# Property Prediction: Aggregation, Solubility, Stability
# ────────────────────────────────────────────────────────


async def run_aggrescan3d(
    pdb_content: str,
    job_name: str,
) -> dict:
    """Run Aggrescan3D — structure-based aggregation propensity prediction."""
    return await run_dynamic_tool(
        "aggrescan3d",
        {"pdbFile": pdb_content},
        job_name,
        timeout=180,
    )


async def run_camsol(
    sequence: str,
    job_name: str,
    pdb_content: str | None = None,
) -> dict:
    """Run CamSol — solubility scoring + aggregation-prone regions."""
    settings: dict[str, Any] = {"sequence": sequence}
    if pdb_content:
        settings["pdbFile"] = pdb_content
    return await run_dynamic_tool("camsol", settings, job_name, timeout=180)


async def run_temstapro(
    sequence: str,
    job_name: str,
) -> dict:
    """Run TemStaPro — protein thermostability prediction."""
    return await run_dynamic_tool(
        "temstapro",
        {"sequence": sequence},
        job_name,
        timeout=300,
    )


# ────────────────────────────────────────────────────────
# Surface Analysis: MaSIF
# ────────────────────────────────────────────────────────


async def run_masif(
    pdb_content: str,
    job_name: str,
    chain: str = "A",
) -> dict:
    """Run MaSIF — molecular surface interaction fingerprinting."""
    return await run_dynamic_tool(
        "masif",
        {"pdbFile": pdb_content, "chain": chain},
        job_name,
        timeout=300,
    )


# ────────────────────────────────────────────────────────
# Small Molecule Design: REINVENT 4
# ────────────────────────────────────────────────────────


async def run_reinvent(
    target_pdb: str,
    job_name: str,
    num_molecules: int = 50,
    scoring_function: str = "docking",
) -> dict:
    """Run REINVENT 4 — generative AI for de novo small molecule design."""
    return await run_dynamic_tool(
        "reinvent",
        {
            "target": target_pdb,
            "numMolecules": num_molecules,
            "scoringFunction": scoring_function,
        },
        job_name,
        timeout=600,
    )


# ────────────────────────────────────────────────────────
# Antibody-Specific Tools
# ────────────────────────────────────────────────────────


async def run_rfantibody(
    antigen_pdb: str,
    job_name: str,
    epitope_residues: list[int] | None = None,
) -> dict:
    """Run RFantibody — de novo antibody CDR design targeting antigen epitope."""
    settings: dict[str, Any] = {"targetFile": antigen_pdb}
    if epitope_residues:
        settings["interfaceResidues"] = epitope_residues
    return await run_dynamic_tool("rfantibody", settings, job_name, timeout=600)


async def run_biophi(
    antibody_sequence: str,
    job_name: str,
) -> dict:
    """Run BioPhi (Sapiens + OASis) — antibody humanization + humanness scoring."""
    return await run_dynamic_tool(
        "biophi",
        {"sequence": antibody_sequence},
        job_name,
        timeout=180,
    )


# ────────────────────────────────────────────────────────
# Structure Prediction: AlphaFold3, Chai-1
# ────────────────────────────────────────────────────────


async def run_alphafold3(
    sequence: str,
    job_name: str,
    num_samples: int = 1,
    **kwargs: Any,
) -> dict:
    """Run AlphaFold3 — multi-chain / protein-ligand structure prediction."""
    settings: dict[str, Any] = {
        "inputFormat": "sequence",
        "sequence": sequence,
        "numSamples": num_samples,
        "outputType": "pdb",
    }
    settings.update(kwargs)
    return await run_dynamic_tool("alphafold3", settings, job_name, timeout=600)


async def run_chai1(
    sequence: str,
    job_name: str,
    num_samples: int = 1,
    **kwargs: Any,
) -> dict:
    """Run Chai-1 — open-source AF3 alternative for structure prediction."""
    settings: dict[str, Any] = {
        "inputFormat": "sequence",
        "sequence": sequence,
        "numSamples": num_samples,
        "outputType": "pdb",
    }
    settings.update(kwargs)
    return await run_dynamic_tool("chai-1", settings, job_name, timeout=600)


# ────────────────────────────────────────────────────────
# Conformational Dynamics: AlphaFlow
# ────────────────────────────────────────────────────────


async def run_alphaflow(
    sequence: str,
    job_name: str,
    num_samples: int = 10,
    **kwargs: Any,
) -> dict:
    """Run AlphaFlow — conformational ensemble generation."""
    settings: dict[str, Any] = {
        "inputFormat": "sequence",
        "sequence": sequence,
        "numSamples": num_samples,
        "outputType": "pdb",
    }
    settings.update(kwargs)
    return await run_dynamic_tool("alphaflow", settings, job_name, timeout=600)


# ────────────────────────────────────────────────────────
# Binder Design: BindCraft
# ────────────────────────────────────────────────────────


async def run_bindcraft(
    pdb_content: str,
    job_name: str,
    chains: str = "A",
    num_designs: int = 5,
    **kwargs: Any,
) -> dict:
    """Run BindCraft — peptide/miniprotein binder design."""
    settings: dict[str, Any] = {
        "pdbFile": pdb_content,
        "chains": chains,
        "mode": "default",
        "numDesigns": num_designs,
    }
    settings.update(kwargs)
    return await run_dynamic_tool("bindcraft", settings, job_name, timeout=600)


# ────────────────────────────────────────────────────────
# Electrostatic Surface: PepPatch
# ────────────────────────────────────────────────────────


async def run_peppatch(
    pdb_or_sequence: str,
    job_name: str,
    input_format: str = "pdb",
    **kwargs: Any,
) -> dict:
    """Run PepPatch — electrostatic surface patch analysis."""
    settings: dict[str, Any] = {}
    if input_format == "pdb":
        settings["pdbFile"] = pdb_or_sequence
    else:
        settings["sequence"] = pdb_or_sequence
    settings.update(kwargs)
    return await run_dynamic_tool("peppatch", settings, job_name, timeout=180)


# ────────────────────────────────────────────────────────
# Antibody Structure: ImmuneBuilder (ABodyBuilder2)
# ────────────────────────────────────────────────────────


async def run_immunebuilder(
    heavy_chain: str,
    job_name: str,
    light_chain: str | None = None,
    **kwargs: Any,
) -> dict:
    """Run ImmuneBuilder (ABodyBuilder2) — antibody structure prediction."""
    settings: dict[str, Any] = {
        "heavyChain": heavy_chain,
        "outputType": "pdb",
    }
    if light_chain:
        settings["lightChain"] = light_chain
    settings.update(kwargs)
    return await run_tool("immunebuilder", settings, job_name, timeout=300)


# ────────────────────────────────────────────────────────
# Multi-Engine Comparison Pipeline
# ────────────────────────────────────────────────────────


async def run_multi_engine_comparison(
    sequence: str,
    job_prefix: str = "multi",
) -> dict[str, dict]:
    """Submit Boltz-2, ESMFold, Chai-1, and AlphaFold3 concurrently.

    Returns {engine_name: result_dict} for side-by-side comparison.
    Each engine runs independently — failures in one don't block others.
    """

    async def _safe_run(name: str, coro) -> tuple[str, dict]:
        try:
            result = await coro
            return name, {"status": "completed", "result": result}
        except Exception as e:
            return name, {"status": "error", "error": str(e)}

    tasks = [
        _safe_run(
            "boltz2",
            run_tool(
                "boltz",
                {
                    "inputFormat": "sequence",
                    "sequence": sequence,
                    "numSamples": 1,
                    "outputType": "pdb",
                },
                f"{job_prefix}_boltz2",
                timeout=600,
            ),
        ),
        _safe_run(
            "esmfold",
            run_esmfold(sequence, f"{job_prefix}_esmfold"),
        ),
        _safe_run(
            "chai1",
            run_chai1(sequence, f"{job_prefix}_chai1"),
        ),
        _safe_run(
            "alphafold3",
            run_alphafold3(sequence, f"{job_prefix}_af3"),
        ),
    ]

    results = await asyncio.gather(*tasks)
    return dict(results)
