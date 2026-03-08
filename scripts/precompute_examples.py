#!/usr/bin/env python3
"""Pre-compute example results for demo resilience.

Downloads structures from RCSB PDB and generates confidence/context data
so the demo works without API access.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

EXAMPLES = {
    "p53_r248w": {
        "pdb_id": "1TUP",  # TP53 DNA-binding domain
        "protein_name": "TP53",
        "mutation": "R248W",
        "question_type": "druggability",
        "confidence": {
            "confidence_score": 0.78,
            "ptm": 0.81,
            "iptm": None,
            "complex_plddt": 0.79,
        },
        "context": {
            "narrative": (
                "TP53 (tumor protein p53) is the most frequently mutated gene in human cancers, "
                "with R248W being one of the six hotspot mutations in the DNA-binding domain. "
                "This gain-of-function mutation disrupts DNA binding and confers oncogenic "
                "properties. R248W is found in approximately 7.2% of TP53-mutant cancers."
            ),
            "disease_associations": [
                {"disease": "Li-Fraumeni Syndrome", "score": 0.99, "evidence": "Germline TP53 mutations"},
                {"disease": "Breast Cancer", "score": 0.95, "evidence": "Somatic hotspot mutation"},
                {"disease": "Colorectal Cancer", "score": 0.92, "evidence": "Frequent somatic mutation"},
                {"disease": "Lung Adenocarcinoma", "score": 0.90, "evidence": "Driver mutation"},
                {"disease": "Ovarian Cancer", "score": 0.88, "evidence": "High-frequency somatic mutation"},
            ],
            "drugs": [
                {"name": "APR-246 (Eprenetapopt)", "phase": "Phase III", "mechanism": "Reactivates mutant p53 by restoring wild-type conformation", "source": "ClinicalTrials.gov"},
                {"name": "PC14586 (Rezatapopt)", "phase": "Phase II", "mechanism": "Selective Y220C p53 reactivator", "source": "PMC"},
                {"name": "PRIMA-1", "phase": "Phase I", "mechanism": "Converts to methylene quinuclidinone, binds cysteine residues in p53 core domain", "source": "PubMed"},
                {"name": "Arsenic Trioxide", "phase": "Phase II", "mechanism": "Stabilizes p53 folding via zinc coordination", "source": "PMC"},
            ],
            "literature": {
                "total_papers": 3847,
                "recent_papers": 142,
                "key_findings": [
                    "R248W p53 exhibits gain-of-function oncogenic activity beyond loss of tumor suppression",
                    "Structural studies reveal R248W disrupts DNA minor groove interactions",
                    "Combination of APR-246 with cisplatin shows synergistic effects in ovarian cancer",
                    "Cryo-EM structures reveal allosteric mechanisms of p53 reactivation compounds",
                    "Machine learning models predict drug sensitivity based on p53 mutation status",
                ],
            },
            "pathways": [
                "p53 signaling pathway",
                "Apoptosis",
                "Cell cycle arrest",
                "DNA damage response",
                "Senescence",
            ],
            "suggested_experiments": [
                "Thermal shift assay (DSF) to validate R248W impact on protein stability",
                "HDX-MS to map conformational changes induced by R248W",
                "Co-crystallization with APR-246 metabolite to validate binding mode",
                "Cellular assays for p53 transcriptional activity restoration",
            ],
        },
    },
    "brca1_c61g": {
        "pdb_id": "1JM7",  # BRCA1 RING domain
        "protein_name": "BRCA1",
        "mutation": "C61G",
        "question_type": "mutation_impact",
        "confidence": {
            "confidence_score": 0.82,
            "ptm": 0.85,
            "iptm": 0.79,
            "complex_plddt": 0.83,
        },
        "context": {
            "narrative": (
                "BRCA1 C61G is a pathogenic missense variant in the RING finger domain that "
                "disrupts zinc coordination essential for BRCA1-BARD1 heterodimerization. "
                "This variant abolishes E3 ubiquitin ligase activity and impairs homologous "
                "recombination DNA repair, conferring high risk of breast and ovarian cancer."
            ),
            "disease_associations": [
                {"disease": "Hereditary Breast Cancer", "score": 0.99, "evidence": "ClinVar: Pathogenic"},
                {"disease": "Hereditary Ovarian Cancer", "score": 0.97, "evidence": "ClinVar: Pathogenic"},
                {"disease": "Fanconi Anemia", "score": 0.60, "evidence": "Biallelic BRCA1 mutations"},
            ],
            "drugs": [
                {"name": "Olaparib", "phase": "Approved", "mechanism": "PARP inhibitor — synthetic lethality with BRCA1 deficiency", "source": "FDA"},
                {"name": "Talazoparib", "phase": "Approved", "mechanism": "PARP inhibitor — PARP trapping", "source": "FDA"},
                {"name": "Rucaparib", "phase": "Approved", "mechanism": "PARP inhibitor", "source": "FDA"},
                {"name": "Niraparib", "phase": "Approved", "mechanism": "PARP inhibitor", "source": "FDA"},
            ],
            "literature": {
                "total_papers": 1256,
                "recent_papers": 87,
                "key_findings": [
                    "C61G disrupts zinc binding in RING domain, abolishing BARD1 interaction",
                    "PARP inhibitors show durable responses in BRCA1-mutant cancers",
                    "Structural basis of BRCA1 RING domain function revealed by NMR",
                ],
            },
            "pathways": ["Homologous recombination", "DNA damage response", "Ubiquitin-proteasome pathway"],
            "suggested_experiments": [
                "Validate zinc binding disruption with ICP-MS or atomic absorption",
                "BARD1 co-immunoprecipitation to confirm loss of interaction",
                "HR reporter assay (DR-GFP) to measure repair deficiency",
            ],
        },
    },
    "egfr_t790m": {
        "pdb_id": "3W2S",  # EGFR kinase domain with T790M
        "protein_name": "EGFR",
        "mutation": "T790M",
        "question_type": "binding",
        "confidence": {
            "confidence_score": 0.91,
            "ptm": 0.93,
            "iptm": 0.88,
            "complex_plddt": 0.90,
        },
        "context": {
            "narrative": (
                "EGFR T790M is the most common acquired resistance mutation to first- and "
                "second-generation EGFR tyrosine kinase inhibitors (TKIs) in non-small cell "
                "lung cancer. The methionine substitution at the gatekeeper position sterically "
                "hinders binding of reversible inhibitors like gefitinib and erlotinib while "
                "increasing ATP affinity."
            ),
            "disease_associations": [
                {"disease": "Non-Small Cell Lung Cancer", "score": 0.99, "evidence": "Driver and resistance mutation"},
                {"disease": "Glioblastoma", "score": 0.70, "evidence": "EGFR amplification/mutation"},
            ],
            "drugs": [
                {"name": "Osimertinib", "phase": "Approved", "mechanism": "Third-generation EGFR TKI — covalently binds C797, overcomes T790M", "source": "FDA"},
                {"name": "Lazertinib", "phase": "Approved", "mechanism": "Third-generation EGFR TKI targeting T790M", "source": "FDA"},
                {"name": "Amivantamab", "phase": "Approved", "mechanism": "Bispecific EGFR-MET antibody", "source": "FDA"},
                {"name": "Gefitinib", "phase": "Approved (1st-gen)", "mechanism": "Reversible EGFR TKI — ineffective against T790M", "source": "FDA"},
            ],
            "literature": {
                "total_papers": 4521,
                "recent_papers": 198,
                "key_findings": [
                    "T790M restores ATP affinity to wild-type levels while sterically blocking reversible TKIs",
                    "Osimertinib overcomes T790M resistance via covalent binding to C797",
                    "C797S tertiary mutation confers resistance to third-generation TKIs",
                    "Combination strategies with MET inhibitors show promise post-osimertinib",
                ],
            },
            "pathways": ["EGFR signaling", "RAS-MAPK pathway", "PI3K-AKT pathway", "Cell proliferation"],
            "suggested_experiments": [
                "SPR or ITC to measure binding affinity of TKIs to T790M mutant",
                "Cell viability assays in Ba/F3-EGFR-T790M cells",
                "Structural analysis of drug binding mode by X-ray crystallography",
            ],
        },
    },
    "spike_rbd": {
        "pdb_id": "6M0J",  # SARS-CoV-2 RBD bound to ACE2
        "protein_name": "SPIKE",
        "mutation": None,
        "question_type": "binding",
        "confidence": {
            "confidence_score": 0.92,
            "ptm": 0.94,
            "iptm": 0.89,
            "complex_plddt": 0.91,
        },
        "context": {
            "narrative": (
                "The SARS-CoV-2 spike protein receptor-binding domain (RBD, residues 319-541) "
                "mediates host cell entry by binding human ACE2. The RBD undergoes conformational "
                "changes between 'up' (ACE2-accessible) and 'down' (hidden) states. Key contact "
                "residues (K417, E484, N501) are hotspots for immune-evasive mutations in variants "
                "of concern (Alpha, Beta, Delta, Omicron)."
            ),
            "disease_associations": [
                {"disease": "COVID-19", "score": 0.99, "evidence": "Primary viral entry mechanism"},
                {"disease": "Post-acute COVID Syndrome", "score": 0.75, "evidence": "Persistent spike-mediated effects"},
            ],
            "drugs": [
                {"name": "Nirmatrelvir (Paxlovid)", "phase": "Approved", "mechanism": "SARS-CoV-2 Mpro inhibitor", "source": "FDA"},
                {"name": "Bebtelovimab", "phase": "Approved (EUA)", "mechanism": "Monoclonal antibody targeting RBD", "source": "FDA"},
                {"name": "Sotrovimab", "phase": "Approved (EUA)", "mechanism": "Monoclonal antibody binding conserved RBD epitope", "source": "FDA"},
                {"name": "Evusheld (tixagevimab/cilgavimab)", "phase": "Approved (EUA)", "mechanism": "Long-acting antibody cocktail targeting RBD", "source": "FDA"},
            ],
            "literature": {
                "total_papers": 28500,
                "recent_papers": 450,
                "key_findings": [
                    "Cryo-EM reveals RBD conformational dynamics between up/down states on trimeric spike",
                    "N501Y mutation increases ACE2 binding affinity 10-fold, driving Alpha variant spread",
                    "E484K enables immune escape from convalescent and vaccine-elicited antibodies",
                    "Pan-sarbecovirus antibodies target conserved RBD class 4 epitopes",
                ],
            },
            "pathways": ["Viral entry", "ACE2-RAS signaling", "Innate immune response", "Antibody neutralization"],
            "suggested_experiments": [
                "SPR to measure RBD-ACE2 binding kinetics for variant mutations",
                "Pseudovirus neutralization assay with convalescent sera",
                "Cryo-EM of spike trimer to visualize RBD dynamics",
            ],
        },
    },
    "hba1_hemoglobin": {
        "pdb_id": "1HHO",  # Human deoxyhemoglobin
        "protein_name": "HBA1",
        "mutation": None,
        "question_type": "structure",
        "confidence": {
            "confidence_score": 0.95,
            "ptm": 0.96,
            "iptm": 0.93,
            "complex_plddt": 0.94,
        },
        "context": {
            "narrative": (
                "Hemoglobin alpha-1 (HBA1) is a 142-amino acid globin that forms the alpha "
                "subunit of adult hemoglobin (alpha2-beta2 tetramer). It binds heme via the "
                "proximal histidine (H87) and undergoes cooperative conformational changes "
                "(T→R transition) during oxygen binding. Mutations in HBA1 cause alpha-thalassemia "
                "and unstable hemoglobin variants."
            ),
            "disease_associations": [
                {"disease": "Alpha-Thalassemia", "score": 0.99, "evidence": "HBA1/HBA2 deletions or point mutations"},
                {"disease": "Hemoglobin H Disease", "score": 0.90, "evidence": "3 of 4 alpha-globin genes deleted"},
                {"disease": "Hydrops Fetalis", "score": 0.85, "evidence": "All 4 alpha-globin genes deleted (fatal)"},
            ],
            "drugs": [
                {"name": "Hydroxyurea", "phase": "Approved", "mechanism": "Increases fetal hemoglobin (HbF) production", "source": "FDA"},
                {"name": "Luspatercept", "phase": "Approved", "mechanism": "TGF-beta superfamily ligand trap — improves erythropoiesis", "source": "FDA"},
                {"name": "Voxelotor", "phase": "Approved", "mechanism": "HbS polymerization inhibitor (stabilizes oxy-Hb)", "source": "FDA"},
            ],
            "literature": {
                "total_papers": 8200,
                "recent_papers": 180,
                "key_findings": [
                    "High-resolution crystal structures reveal cooperative oxygen binding mechanism",
                    "CRISPR-based gene therapy corrects alpha-thalassemia in preclinical models",
                    "Molecular dynamics simulations explain allosteric T→R transition in hemoglobin",
                ],
            },
            "pathways": ["Oxygen transport", "Heme biosynthesis", "Erythropoiesis", "Iron homeostasis"],
            "suggested_experiments": [
                "Oxygen equilibrium curves to measure P50 and Hill coefficient",
                "Circular dichroism to assess alpha-helix content and stability",
                "Size-exclusion chromatography to confirm tetramer assembly",
            ],
        },
    },
    "insulin": {
        "pdb_id": "4INS",  # Human insulin hexamer
        "protein_name": "INS",
        "mutation": None,
        "question_type": "structure",
        "confidence": {
            "confidence_score": 0.88,
            "ptm": 0.90,
            "iptm": 0.85,
            "complex_plddt": 0.87,
        },
        "context": {
            "narrative": (
                "Human insulin (INS) is a peptide hormone produced by pancreatic beta cells "
                "that regulates glucose homeostasis. The mature hormone is a 51-amino acid "
                "heterodimer of A-chain (21 aa) and B-chain (30 aa) linked by disulfide bonds. "
                "Insulin binds the insulin receptor (INSR) tyrosine kinase to activate PI3K-AKT "
                "and RAS-MAPK signaling, promoting glucose uptake and glycogen synthesis."
            ),
            "disease_associations": [
                {"disease": "Type 1 Diabetes Mellitus", "score": 0.99, "evidence": "Autoimmune destruction of beta cells"},
                {"disease": "Type 2 Diabetes Mellitus", "score": 0.95, "evidence": "Insulin resistance and relative deficiency"},
                {"disease": "Neonatal Diabetes", "score": 0.80, "evidence": "INS gene mutations (e.g., C96Y)"},
                {"disease": "Hyperinsulinism", "score": 0.70, "evidence": "Gain-of-function INS mutations"},
            ],
            "drugs": [
                {"name": "Insulin Lispro", "phase": "Approved", "mechanism": "Rapid-acting insulin analog (B28-B29 swap)", "source": "FDA"},
                {"name": "Insulin Glargine", "phase": "Approved", "mechanism": "Long-acting basal insulin (A21G, B31R, B32R)", "source": "FDA"},
                {"name": "Insulin Detemir", "phase": "Approved", "mechanism": "Long-acting insulin with fatty acid acylation", "source": "FDA"},
                {"name": "Tirzepatide", "phase": "Approved", "mechanism": "Dual GIP/GLP-1 receptor agonist", "source": "FDA"},
            ],
            "literature": {
                "total_papers": 12450,
                "recent_papers": 340,
                "key_findings": [
                    "Cryo-EM structure of insulin bound to full-length insulin receptor reveals asymmetric binding",
                    "Ultra-rapid insulin analogs achieve faster onset through reduced self-association",
                    "Smart insulin concepts using glucose-responsive polymers show promise in preclinical models",
                    "Oral insulin delivery via nanoparticle encapsulation advancing through Phase II trials",
                ],
            },
            "pathways": [
                "Insulin signaling pathway",
                "PI3K-AKT signaling",
                "Glucose metabolism",
                "MAPK/ERK cascade",
                "mTOR signaling",
            ],
            "suggested_experiments": [
                "Circular dichroism to assess structural integrity of insulin formulations",
                "SPR to measure insulin-INSR binding kinetics",
                "Cell-based glucose uptake assay to validate functional activity",
            ],
        },
    },
}


def download_pdb(pdb_id: str) -> str | None:
    """Download PDB file from RCSB."""
    try:
        resp = httpx.get(
            f"https://files.rcsb.org/download/{pdb_id}.pdb",
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.text
    except Exception as e:
        print(f"  Failed to download {pdb_id}: {e}")
    return None


def _parse_mutation_pos(mutation: str | None) -> int | None:
    """Extract numeric position from mutation like 'R248W'."""
    if not mutation:
        return None
    import re
    m = re.match(r"[A-Z](\d+)[A-Z]", mutation)
    return int(m.group(1)) if m else None


def _get_pocket_residues(protein_name: str) -> list[int]:
    """Get known binding pocket residues."""
    try:
        from components.drug_resistance import _RESISTANCE_DB
        data = _RESISTANCE_DB.get(protein_name.upper(), {})
        return data.get("binding_pocket_residues", [])
    except ImportError:
        return []


def _to_native(obj):
    """Recursively convert numpy types to Python native for JSON serialization."""
    import numpy as np
    if isinstance(obj, dict):
        return {_to_native(k): _to_native(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_native(v) for v in obj]
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def _compute_structure_analysis(pdb_content: str, config: dict) -> dict | None:
    """Compute SASA, SSE, contact map, packing, centrality, Ramachandran."""
    try:
        from src.structure_analysis import analyze_structure
        mutation_pos = _parse_mutation_pos(config.get("mutation"))
        pocket_residues = _get_pocket_residues(config["protein_name"])

        analysis = analyze_structure(
            pdb_content,
            mutation_pos=mutation_pos,
            pocket_residues=pocket_residues,
            first_chain=None,  # auto-detect
        )

        # Remove non-serializable numpy arrays
        if "contact_map" in analysis:
            del analysis["contact_map"]  # NxN ndarray, too large for JSON
        if "contact_map_residues" in analysis:
            analysis["contact_map_residues"] = list(analysis["contact_map_residues"])

        # Convert all numpy types to native Python for clean JSON serialization
        analysis = _to_native(analysis)

        return analysis
    except Exception as e:
        print(f"    Structure analysis failed: {e}")
        return None


def _compute_flexibility(pdb_content: str) -> dict | None:
    """Compute ANM flexibility scores."""
    try:
        from src.flexibility_analysis import compute_anm_flexibility
        return _to_native(compute_anm_flexibility(pdb_content))
    except Exception as e:
        print(f"    Flexibility analysis failed: {e}")
        return None


def _compute_pockets(pdb_content: str) -> dict | None:
    """Compute binding pocket predictions."""
    try:
        from src.pocket_prediction import predict_pockets
        return _to_native(predict_pockets(pdb_content))
    except Exception as e:
        print(f"    Pocket prediction failed: {e}")
        return None


def _generate_interpretation(config: dict) -> dict | None:
    """Pre-generate AI interpretation text."""
    from src.config import ANTHROPIC_API_KEY
    if not ANTHROPIC_API_KEY:
        return _fallback_interpretation(config)
    try:
        from src.interpreter import generate_interpretation
        from src.models import (
            BioContext,
            DiseaseAssociation,
            DrugCandidate,
            LiteratureSummary,
            ProteinQuery,
            TrustAudit,
        )

        query = ProteinQuery(
            protein_name=config["protein_name"],
            mutation=config.get("mutation"),
            question_type=config.get("question_type", "structure"),
        )

        conf = config["confidence"]
        trust_audit = TrustAudit(
            overall_confidence="high" if conf["confidence_score"] >= 0.8 else "medium",
            confidence_score=conf["confidence_score"],
            ptm=conf.get("ptm"),
            iptm=conf.get("iptm"),
            complex_plddt=conf.get("complex_plddt"),
        )

        ctx = config["context"]
        bio_context = BioContext(
            narrative=ctx.get("narrative", ""),
            disease_associations=[DiseaseAssociation(**d) for d in ctx.get("disease_associations", [])],
            drugs=[DrugCandidate(**d) for d in ctx.get("drugs", [])],
            literature=LiteratureSummary(**ctx.get("literature", {})),
            pathways=ctx.get("pathways", []),
            suggested_experiments=ctx.get("suggested_experiments", []),
        )

        text = generate_interpretation(query, trust_audit, bio_context)
        return {"text": text, "model": "claude-sonnet-4-20250514"}
    except Exception as e:
        print(f"    Interpretation generation failed: {e}")
        return _fallback_interpretation(config)


def _fallback_interpretation(config: dict) -> dict:
    """Generate a basic interpretation without Claude API."""
    protein = config["protein_name"]
    mutation = config.get("mutation", "")
    narrative = config["context"].get("narrative", "")
    drugs = config["context"].get("drugs", [])
    conf = config["confidence"]["confidence_score"]

    drug_text = ""
    if drugs:
        drug_names = ", ".join(d["name"] for d in drugs[:3])
        drug_text = f"\n\nTherapeutic options include {drug_names}."

    text = (
        f"## Structure Prediction Summary for {protein}\n\n"
        f"**Overall Confidence:** {'high' if conf >= 0.8 else 'medium'} ({conf:.1%})\n\n"
        f"{'**Mutation:** ' + mutation + chr(10) + chr(10) if mutation else ''}"
        f"{narrative}{drug_text}\n\n"
        f"*Pre-generated interpretation for demo resilience.*"
    )
    return {"text": text, "model": "fallback"}


def precompute(name: str, config: dict):
    """Download and save precomputed data for one example."""
    print(f"\nProcessing {name}...")
    base = Path(f"data/precomputed/{name}")
    base.mkdir(parents=True, exist_ok=True)

    # Download PDB (skip if already present)
    pdb_id = config["pdb_id"]
    pdb_file = base / "structure.pdb"
    if pdb_file.exists() and pdb_file.stat().st_size > 1000:
        print("  structure.pdb already exists, skipping download")
        pdb_content = pdb_file.read_text()
    else:
        print(f"  Downloading {pdb_id} from RCSB PDB...")
        pdb_content = download_pdb(pdb_id)
        if pdb_content:
            pdb_file.write_text(pdb_content)
            atom_count = sum(1 for line in pdb_content.split("\n") if line.startswith("ATOM"))
            print(f"  Saved structure.pdb ({atom_count} atoms)")
        else:
            print(f"  WARNING: Could not download {pdb_id}")
            return

    # Save confidence
    (base / "confidence.json").write_text(json.dumps(config["confidence"], indent=2))
    print("  Saved confidence.json")

    # Save context
    (base / "context.json").write_text(json.dumps(config["context"], indent=2))
    print("  Saved context.json")

    # ── Extended precomputations (NEW) ──

    # Structure analysis (SASA, SSE, packing, centrality, Ramachandran)
    print("  Computing structure analysis...")
    analysis = _compute_structure_analysis(pdb_content, config)
    if analysis:
        (base / "structure_analysis.json").write_text(json.dumps(analysis, indent=2))
        n_res = len(analysis.get("residue_ids", []))
        print(f"  Saved structure_analysis.json ({n_res} residues)")

    # ANM flexibility
    print("  Computing flexibility (ANM)...")
    flex = _compute_flexibility(pdb_content)
    if flex:
        (base / "flexibility.json").write_text(json.dumps(flex, indent=2))
        n_hinge = len(flex.get("hinge_residues", []))
        print(f"  Saved flexibility.json ({n_hinge} hinge residues)")

    # Binding pocket prediction
    print("  Predicting binding pockets...")
    pockets = _compute_pockets(pdb_content)
    if pockets:
        (base / "pockets.json").write_text(json.dumps(pockets, indent=2))
        n_pockets = len(pockets.get("pockets", []))
        print(f"  Saved pockets.json ({n_pockets} pockets)")

    # AI interpretation
    print("  Generating interpretation...")
    interp = _generate_interpretation(config)
    if interp:
        (base / "interpretation.json").write_text(json.dumps(interp, indent=2))
        model = interp.get("model", "unknown")
        print(f"  Saved interpretation.json (via {model})")

    print(f"  Done: {name}")


def main():
    print("=" * 60)
    print("Luminous — Pre-computing Example Data")
    print("=" * 60)

    for name, config in EXAMPLES.items():
        try:
            precompute(name, config)
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n" + "=" * 60)
    print("Pre-computation complete!")
    print("Run `uv run streamlit run app.py` to test.")


if __name__ == "__main__":
    main()
