from __future__ import annotations

from pydantic import BaseModel


class ProteinQuery(BaseModel):
    protein_name: str
    uniprot_id: str | None = None
    mutation: str | None = None
    interaction_partner: str | None = None
    question_type: str = "structure"  # structure, mutation_impact, druggability, binding
    sequence: str | None = None


class RegionConfidence(BaseModel):
    chain: str
    start_residue: int
    end_residue: int
    avg_plddt: float
    flag: str | None = None


class TrustAudit(BaseModel):
    overall_confidence: str  # "high", "medium", "low"
    confidence_score: float
    ptm: float | None = None
    iptm: float | None = None
    complex_plddt: float | None = None
    regions: list[RegionConfidence] = []
    known_limitations: list[str] = []
    training_data_note: str | None = None
    suggested_validation: list[str] = []


class DrugCandidate(BaseModel):
    name: str
    phase: str | None = None
    mechanism: str | None = None
    source: str | None = None


class DiseaseAssociation(BaseModel):
    disease: str
    score: float | None = None
    evidence: str | None = None


class LiteratureSummary(BaseModel):
    total_papers: int = 0
    recent_papers: int = 0
    key_findings: list[str] = []
    sources: list[str] = []
    paper_titles: list[str] = []
    dois: list[str] = []


class BioContext(BaseModel):
    narrative: str = ""
    disease_associations: list[DiseaseAssociation] = []
    drugs: list[DrugCandidate] = []
    literature: LiteratureSummary = LiteratureSummary()
    pathways: list[str] = []
    suggested_experiments: list[str] = []


class PredictionResult(BaseModel):
    pdb_content: str = ""
    confidence_json: dict = {}
    affinity_json: dict | None = None
    plddt_per_residue: list[float] = []
    chain_ids: list[str] = []
    residue_ids: list[int] = []
    compute_source: str = "precomputed"  # "tamarind", "modal", "rcsb", "precomputed"
