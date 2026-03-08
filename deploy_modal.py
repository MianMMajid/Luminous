"""Deploy Luminous to Modal for serverless hosting + GPU compute.

Usage:
    modal deploy deploy_modal.py     # Deploy both web server + GPU function
    modal run deploy_modal.py        # Test GPU function locally

This deploys:
  1. Streamlit web server (CPU) — serves the Luminous UI
  2. Boltz-2 GPU function (H100) — runs structure prediction on demand
"""
from __future__ import annotations

import modal

app = modal.App("luminous")

# ── Web Server Image (CPU) ──
web_image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install(
        "streamlit>=1.44",
        "molviewspec>=1.8",
        "anthropic>=0.84",
        "biomcp-python>=0.7.3",
        "biotite>=1.6",
        "plotly>=6.0",
        "httpx>=0.28",
        "pydantic>=2.5",
        "pandas>=2.2",
        "numpy",
        "python-dotenv",
        "modal>=0.73",
        "fpdf2>=2.8",
        "networkx",
    )
    .copy_local_dir(".", "/app", ignore=[".venv", "__pycache__", ".git", "*.pyc"])
)


@app.function(
    image=web_image,
    secrets=[modal.Secret.from_name("luminous-secrets")],
    cpu=2,
    memory=2048,
    timeout=600,
)
@modal.web_server(8501, startup_timeout=60)
def serve():
    import subprocess

    subprocess.Popen(
        [
            "streamlit",
            "run",
            "/app/app.py",
            "--server.port=8501",
            "--server.address=0.0.0.0",
            "--server.headless=true",
            "--browser.gatherUsageStats=false",
        ]
    )


# ── Boltz-2 GPU Function (H100) ──
# This is also defined in src/modal_predict.py as a standalone app.
# Here we re-export it so `modal deploy deploy_modal.py` deploys everything.
gpu_image = (
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("wget", "git")
    .pip_install("boltz", "pyyaml", "numpy")
)

model_volume = modal.Volume.from_name("boltz-models", create_if_missing=True)


@app.function(
    image=gpu_image,
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
    """Run Boltz-2 inference on H100 GPU. See src/modal_predict.py for docs."""
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    import yaml

    work_dir = Path(tempfile.mkdtemp())

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

    cmd = [
        "boltz", "predict",
        str(input_file),
        "--use_msa_server",
        "--cache", "/models/boltz",
        "--output_format", "pdb",
        "--out_dir", str(work_dir / "output"),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=8 * 60, cwd=str(work_dir),
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Boltz-2 failed (exit {result.returncode}): {result.stderr[:500]}"
        )

    model_volume.commit()

    pred_dir = work_dir / "output"
    pdb_files = list(pred_dir.rglob("*.pdb"))
    conf_files = list(pred_dir.rglob("confidence*.json"))
    aff_files = list(pred_dir.rglob("affinity*.json"))

    if not pdb_files:
        raise RuntimeError(f"No PDB output. stdout: {result.stdout[:300]}")

    pdb_content = pdb_files[0].read_text()
    confidence = json.loads(conf_files[0].read_text()) if conf_files else {}
    affinity = json.loads(aff_files[0].read_text()) if aff_files else None

    return {"pdb": pdb_content, "confidence": confidence, "affinity": affinity}


@app.local_entrypoint()
def main():
    """CLI test: run a small prediction."""
    test_seq = "MVHLTPEEKSAVTALWGKVNVDEVGGEALGRLLVVYPWTQRFFESFGDLSTPDAVMGNPKVKAHGKKVLGAFSDGLAHLDN"
    print(f"Testing Boltz-2 on {len(test_seq)} residues...")
    result = boltz_predict.remote(test_seq, "test_job", predict_affinity=False)
    print(f"PDB: {len(result['pdb'])} chars | Confidence keys: {list(result['confidence'].keys())}")
    print("Done!")
