"""Modal serverless GPU function for Boltz-2 structure prediction.

Deploys Boltz-2 on H100 GPUs via Modal. Model weights are cached
in a persistent volume to avoid re-download on cold starts.

Usage:
    # Deploy:        modal deploy src/modal_predict.py
    # Test locally:  modal run src/modal_predict.py
"""
from __future__ import annotations

import modal

app = modal.App("luminous")

# Persistent volume for model weights (~5 GB, avoids re-download)
model_volume = modal.Volume.from_name("boltz-models", create_if_missing=True)

image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("wget", "git")
    .pip_install("boltz", "pyyaml", "numpy")
)


@app.function(
    image=image,
    gpu="H100",
    volumes={"/models/boltz": model_volume},
    timeout=10 * 60,
    memory=32768,
)
def boltz_predict(
    sequence: str,
    job_name: str = "luminous_job",
    predict_affinity: bool = True,
) -> dict:
    """Run Boltz-2 inference on a protein sequence.

    Returns dict with keys: pdb, confidence, affinity (optional).
    """
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    import yaml

    work_dir = Path(tempfile.mkdtemp())

    # ── Build YAML input ──
    input_data: dict = {
        "version": 1,
        "sequences": [
            {"protein": {"id": "A", "sequence": sequence}},
        ],
    }
    if predict_affinity:
        input_data["properties"] = [{"affinity": {"binder": "A"}}]

    input_file = work_dir / "input.yaml"
    input_file.write_text(yaml.dump(input_data, default_flow_style=False))

    # ── Run Boltz-2 ──
    cmd = [
        "boltz", "predict",
        str(input_file),
        "--use_msa_server",
        "--cache", "/models/boltz",
        "--output_format", "pdb",
        "--out_dir", str(work_dir / "output"),
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=8 * 60,
        cwd=str(work_dir),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Boltz-2 prediction failed (exit {result.returncode}): "
            f"{result.stderr[:500]}"
        )

    # Commit model weights to volume for next cold start
    model_volume.commit()

    # ── Parse outputs ──
    # Boltz writes to: output/boltz_results_input/predictions/input/
    pred_dir = work_dir / "output"
    # Find output files (directory structure may vary)
    pdb_files = list(pred_dir.rglob("*.pdb"))
    conf_files = list(pred_dir.rglob("confidence*.json"))
    aff_files = list(pred_dir.rglob("affinity*.json"))

    if not pdb_files:
        raise RuntimeError(
            f"No PDB output found. Boltz stdout: {result.stdout[:300]}"
        )

    pdb_content = pdb_files[0].read_text()
    confidence = {}
    if conf_files:
        confidence = json.loads(conf_files[0].read_text())

    affinity = None
    if aff_files:
        affinity = json.loads(aff_files[0].read_text())

    return {
        "pdb": pdb_content,
        "confidence": confidence,
        "affinity": affinity,
        "job_name": job_name,
    }


@app.local_entrypoint()
def main():
    """CLI test: run a small prediction."""
    test_seq = "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLSTPDAVMGNPKVKAHGKKVLGAFSDGLAHLDN"
    print(f"Submitting test prediction ({len(test_seq)} residues)...")
    result = boltz_predict.remote(test_seq, "test_job", predict_affinity=False)
    print(f"PDB length: {len(result['pdb'])} chars")
    print(f"Confidence keys: {list(result['confidence'].keys())}")
    print("Done!")
