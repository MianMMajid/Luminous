# Luminous — Complete Technical Reference

> **The AI Structure Interpreter** — decode proteins, mutations, and drugs with confidence-aware visualization.
>
> Built for the YC Bio x AI Hackathon, March 2026 (Tamarind Bio + BioRender)

---

## What It Does

Luminous takes a plain-English query like "TP53 with R248W mutation" and delivers a complete scientific analysis: 3D structure prediction, per-residue trust audit, variant landscape, drug candidates, literature review, AI interpretation with citations, and testable hypotheses — all in under 60 seconds.

It solves the **"So What?" gap**: every lab can predict a protein structure now, but no tool tells them what it *means*.

---

## Architecture Overview

```
User Query → Claude Parser → Boltz-2 (Tamarind/Modal) → Trust Audit
                                                              ↓
Claude MCP ← PubMed + Open Targets + ChEMBL + Wiley    Mol* 3D Viewer
     ↓                                                       ↓
Citations API → Grounded Interpretation          36+ Interactive Plots
     ↓                                                       ↓
Extended Thinking → Testable Hypotheses          PDF/JSON/ZIP Exports
```

**Stack**: Streamlit 1.50+ · Python 3.12 · Anthropic SDK · molviewspec · Plotly · biotite · ProDy · fpdf2

---

## The 8 Tabs

### 1. Lumi (Chat Agent)
Autonomous research agent with **40+ tools** powered by Claude Tool Use. Users type questions in natural language; the agent searches databases, analyzes structure, and returns structured answers with full tool call transparency.

- iMessage-style chat bubbles with rich markdown rendering (code blocks, headers, lists)
- Tool call display: shows tool name, input parameters, and full output (up to 2000 chars)
- Background task execution (non-blocking) with thinking indicator
- Suggestion pills for quick starts (context-aware based on loaded protein)
- File upload support: PDB, CIF, FASTA, CSV, TSV, PNG, JPG
- MCP-style tool browser showing all 40+ tools organized by category
- Standalone mode: works even without a loaded protein query

### 2. Search (Query Input)
Natural language protein query entry. Claude parses "p53 R248W mutation — is it druggable?" into a structured `ProteinQuery` with protein name, mutation notation, question type, UniProt ID, and sequence.

- 6 example buttons: TP53 R248W, BRCA1 C61G, EGFR T790M, INS, SPIKE RBD, HBA1
- Advanced Boltz-2 settings: recycling steps (1-10), MSA toggle, affinity prediction toggle
- Compute backend selector: Auto / Tamarind / Modal / RCSB
- Immediate pipeline kickoff on submit

### 3. Structure (Hero Screen)
3D protein structure viewer with confidence-aware trust audit — the core visualization.

- **3D Viewer** (molviewspec / Mol* engine):
  - Per-residue pLDDT coloring (blue >90, cyan 70-90, yellow 50-70, orange <50)
  - Per-residue tooltips (pLDDT score, chain, residue number)
  - MVSX data dict embedding (PDB + color JSON + tooltip JSON in single iframe)
  - RCSB PDB fallback viewer link

- **Trust Audit Panel**:
  - Overall confidence badge with emoji + percentage
  - pTM / ipTM scores for multimer complexes
  - Region-level confidence breakdown (flagged low-confidence zones)
  - Known limitations list (8 Boltz-2 caveats from `data/known_limitations.json`)
  - Suggested validation experiments

- **Sub-components** (inside expandable panels):
  - Sequence Viewer — interactive amino acid strip with confidence coloring
  - Mutation Impact — SIFT/PolyPhen scores, structural context radar chart
  - Variant Landscape — ClinVar + OncoKB + AlphaMissense overlay on structure
  - Drug Resistance — 3D mapping of known resistance mutations
  - Structural Insights — secondary structure, contact maps, Ramachandran
  - Disorder Detector — flags intrinsically disordered regions (AlphaFold hallucinations)
  - Residue Dashboard — multi-track per-residue metrics (pLDDT, SASA, flexibility, conservation, packing)
  - Tamarind Panel — submit custom Tamarind Bio jobs directly
  - Pipeline Builder — chain analysis tools in sequence
  - Confidence Heatmap — PAE-style matrix visualization
  - PAE Viewer — Predicted Aligned Error from Boltz-2
  - Electrostatics Viewer — surface charge and electrostatic potential
  - AlphaFold Comparison — side-by-side predicted vs experimental (RMSD, GDT-TS, TM-score)
  - Comparison Mode — load two structures for structural alignment
  - Affinity Panel — binding affinity (ΔG, Kd) from Boltz-2

### 4. Biology (Context + Interpretation)
Biological context gathered via Claude MCP (single API call to 4 databases) + AI interpretation grounded with Citations API.

- **MCP Databases**: PubMed, Open Targets, Wiley Scholar Gateway, BioRender
- **Displays**:
  - AI narrative summary (2-3 paragraphs, cited)
  - Disease associations with evidence scores
  - Drug candidates (name, phase, mechanism, source)
  - Literature findings (paper titles, DOIs, key findings)
  - Biological pathways
  - Suggested experiments
- **Hypothesis Panel**: Claude generates 3-5 testable scientific hypotheses using Extended Thinking
- **Network Graph**: Interactive knowledge graph (streamlit-agraph) showing protein → diseases → drugs → pathways

### 5. Report (Exports & Figures)
Publication-ready exports and AI-generated figures.

- **Figure Studio** (tabbed interface):
  - **Data-Driven Figures**: Plotly charts (confidence landscape, pLDDT distribution, variant chart, drug chart)
  - **Code Execution Figures**: Claude writes + executes real matplotlib/seaborn code in a sandbox → PNG output
    - 5 figure types: Confidence Landscape, Variant Impact Heatmap, Structure Quality Dashboard, Drug-Target Landscape, Mutation in Context
  - **Figure Kit**: Diagram templates with customization
  - **Panel Composer**: Multi-panel figure layout builder
  - **Graphical Abstract**: One-click scientific summary figure
  - **Video Panel**: Gemini Veo protein animation generation
  - **Experiment Tracker**: Log and track validation experiments

- **Exports**:
  - PDF report (branded header, metrics, color-coded tables, AI narrative, charts)
  - PDB file download
  - Confidence JSON download
  - ZIP archive (PDB + JSONs + figures)
  - Interactive HTML (Plotly)

### 6. Stats (Statistical Analysis)
Standalone statistical workbench — works independently of the protein pipeline.

- **Data Input**: CSV upload, paste values, import from other tabs
- **14 Test Types**:
  - t-test, paired t-test, Welch's t-test
  - Mann-Whitney U, Wilcoxon signed-rank
  - One-way ANOVA, two-way ANOVA, Kruskal-Wallis
  - Pearson correlation, Spearman correlation
  - Chi-square, Fisher's exact
  - Logistic regression, ROC curves
- **Diagnostics**: Shapiro-Wilk normality, Levene's variance, Bonferroni/FDR correction
- **Survival Analysis** (lifelines): Kaplan-Meier curves, log-rank tests, Cox proportional hazards
- **Curve Fitting**: Nonlinear regression, parameter estimation, residual diagnostics
- **PCA & Clustering**: Principal component analysis, K-means, hierarchical clustering
- **Claude Analysis Mode**: Describe any test in plain English → Claude writes and executes Python code → renders tables + figures

### 7. Workspace (Insight Collection)
Pin insights from any tab, compare side-by-side, find unexpected connections.

- **Pin System**: Any component can pin an insight (chart, metric, finding, warning)
- **Compare Mode**: Side-by-side view of two pinned visualizations
- **Overlay Mode**: Superimpose compatible data tracks (e.g., pLDDT + variant positions)
- **Inspire Me**: Claude agent finds unexpected connections between pinned findings
- **Experiment Planner**: Generates step-by-step experimental protocols from collected insights (Tamarind-aware)

### 8. Sketch (Vision Hypothesis)
Draw biological mechanisms on a canvas; Claude Vision interprets the biology.

- **Bidirectional Canvas Component**: Custom HTML5 canvas (draw pathways, arrows, labels)
- **Image Upload Fallback**: Upload PNG/JPG of whiteboard sketches
- **Claude Vision Analysis**: Identifies biological entities, interactions, mechanisms
- **Structured Output**:
  - Title + scientific description
  - Entity list (proteins, drugs, metabolites, pathways, organelles)
  - Interaction map (activation, inhibition, binding, phosphorylation, transport)
  - Mermaid diagram code
  - Testable prediction ("If X, then Y measurable by Z")
  - Confidence note
- **Network Visualization**: Plotly force-directed graph of entities + interactions
- **Downloads**: JSON, Mermaid (.mmd), network data

---

## Claude AI Features (6 Capabilities)

### 1. Tool Use (Agent SDK)
- **File**: `src/bio_agent.py`
- **40+ tools** for autonomous multi-step protein research
- Agent loop with up to 15 iterations per turn
- Tool categories: Structure Analysis, Databases, Literature, AI & Design, Illustration

### 2. Vision (Image Understanding)
- **File**: `components/sketch_hypothesis.py`
- Hand-drawn diagram → structured biological interpretation
- Supports PNG, JPEG, WebP input formats
- Context-aware (protein name + mutation injected into system prompt)

### 3. Citations API (Source Grounding)
- **File**: `src/interpreter.py`
- Builds citation documents from trust_audit + bio_context data
- AI interpretation grounded in source material — every claim attributed
- Fallback: standard interpretation without citations if API unavailable

### 4. Code Execution Tool
- **File**: `src/code_execution_figures.py`
- `code_execution_20250825` tool type + `files-api-2025-04-14` beta
- Claude writes matplotlib/seaborn Python code → executed in sandbox → PNG returned
- 5 figure types with detailed prompts
- Results: image bytes, generated code, stdout

### 5. Extended Thinking
- **File**: `src/hypothesis_engine.py`
- `thinking={"type": "enabled", "budget_tokens": 5000}`
- Generates scientifically rigorous testable hypotheses
- Deep reasoning over structure + variants + drugs + literature

### 6. MCP (Model Context Protocol)
- **File**: `src/bio_context.py`
- Single API call with `mcp_servers` parameter queries 4 databases simultaneously
- **Servers**: PubMed, Open Targets, Wiley Scholar Gateway, BioRender
- Beta header: `mcp-client-2025-11-20`

---

## Agent Tools (40+)

### Local Structure Analysis (requires loaded PDB)
| Tool | What It Does |
|------|-------------|
| `analyze_structure` | SASA, secondary structure, contacts, packing, Ramachandran, residue network |
| `build_trust_audit` | pLDDT confidence, pTM/ipTM, flagged regions, limitations, validation suggestions |
| `fetch_bio_context` | MCP query to PubMed + Open Targets + Wiley + ChEMBL |
| `search_variants` | ClinVar pathogenic variants for this protein |
| `predict_pockets` | Ligand-binding pocket prediction (SASA/contact heuristics) |
| `compute_flexibility` | ANM-based dynamics, hinge residues (via ProDy) |
| `generate_hypotheses` | Synthesize all data → testable scientific claims |
| `compute_surface_properties` | Hydrophobicity, charge, patches |
| `predict_ptm_sites` | Post-translational modification sites (glycosylation, phosphorylation, ubiquitination) |
| `compute_conservation` | Per-residue conservation scoring (ConSurf-like 1-9 scale) |
| `predict_disorder` | Intrinsic disorder prediction from sequence + structure |
| `compare_structures` | RMSD, GDT-TS, TM-score vs experimental structure |
| `auto_investigate` | Run all local tools in optimal order, cross-reference results |
| `build_protein_network` | Protein Structure Network (PSN), betweenness centrality, allosteric hubs |
| `find_communication_path` | Shortest structural path between two residues (mutation propagation) |
| `compute_residue_depth` | Continuous burial gradient (more informative than binary SASA) |

### Online Database Queries (no structure needed)
| Tool | Database | Returns |
|------|----------|---------|
| `get_protein_info` | UniProt | Function, domains, GO terms, diseases, sequence |
| `fold_sequence` | ESMFold | Instant structure prediction (max ~400 residues) |
| `lookup_alphafold` | AlphaFold DB | Pre-computed structures (241M+ by UniProt ID) |
| `predict_variant_effect` | Ensembl VEP | SIFT, PolyPhen-2, consequence types |
| `check_population_frequency` | gnomAD | Allele frequency, pLI, constraint scores |
| `get_interaction_network` | STRING DB | Protein-protein interactions, confidence scores |
| `classify_domains` | InterPro | Domain architecture, families, binding sites |
| `lookup_compound` | PubChem | Drug properties, Lipinski rules, pharmacology |
| `get_pharmacogenomics` | PharmGKB | Drug-gene clinical annotations |
| `search_literature` | Semantic Scholar | Papers with citation metrics, DOIs |
| `search_open_access_literature` | Europe PMC | Open-access biomedical literature |
| `search_pdb_structures` | RCSB PDB | Experimental structures by name/gene |

### BioRender Illustration
| Tool | What It Does |
|------|-------------|
| `search_biorender_templates` | Find figure templates by protein + question type |
| `search_biorender_icons` | 50,000+ scientific icons (search by keyword) |
| `generate_figure_prompt` | Create text-to-figure prompt for BioRender AI |

---

## Databases & APIs Connected (20+)

### Via Claude MCP (single API call)
- **PubMed** — article search, citation metrics
- **Open Targets** — disease associations, clinical significance
- **Wiley Scholar Gateway** — full-text journal access
- **BioRender** — scientific figure template search

### Via Agent Tool Use
- **UniProt** — protein function, domains, GO, sequence
- **AlphaFold DB** — 241M+ pre-computed structures
- **Ensembl VEP** — variant effect prediction (SIFT, PolyPhen-2)
- **gnomAD** — population allele frequencies, gene constraint
- **STRING DB** — protein-protein interactions
- **InterPro** — domain architecture, families
- **PubChem** — drug/compound properties
- **PharmGKB** — pharmacogenomics annotations
- **Semantic Scholar** — academic papers with citation metrics
- **Europe PMC** — open-access biomedical literature
- **RCSB PDB** — experimental 3D structures

### Via BioMCP Python (direct, no LLM needed)
- **biomcp-python v0.7.3**: PubMed, ChEMBL, ClinVar, OpenFDA, enrichr, biomarkers, diseases, interventions, trials

### Via Tamarind Bio REST API
- **200+ bioinformatics tools**: Boltz-2, ESMFold, Vina/GNINA/DiffDock (docking), ProteinMPNN (design), RFdiffusion, BoltzGen, Aggrescan3D, CamSol, TemStaPro, and more

---

## Sponsor Integration (All 5)

### Anthropic Claude
- **Models**: claude-opus-4-6 (main), claude-sonnet-4-20250514 (fast/code execution)
- **6 features demonstrated**: Tool Use, Vision, Citations API, Code Execution, Extended Thinking, MCP
- **Visibility**: Agent chat, interpretation, figure generation, sketch analysis, hypothesis generation

### Tamarind Bio
- **Integration**: REST API with async httpx, schema discovery via `GET /tools`
- **Tools used**: Boltz-2 (structure prediction + affinity), ESMFold (fast folding), docking (Vina/GNINA), design (ProteinMPNN)
- **Visibility**: Compute backend selector in sidebar, Tamarind panel in Structure tab, tool list in sidebar

### Modal
- **Integration**: Python SDK, `modal.Function.from_name("luminous", "boltz_predict")`
- **Hardware**: H100/A100 GPUs (48GB+ VRAM), serverless auto-scaling
- **Visibility**: Compute backend selector ("Modal GPU (H100)"), sidebar connected services

### BioRender
- **Integration**: MCP search (templates + icons) — search only, no figure composition
- **Visibility**: Agent tool use, Biology tab suggestions, chat recommendations

### Gemini Veo (Google)
- **Integration**: Video generation from structure screenshots or text prompts
- **Styles**: Cinematic, educational, technical, abstract
- **Visibility**: Video panel in Report tab, sidebar connected services

---

## Data Models (Pydantic v2)

```
ProteinQuery
├── protein_name: str
├── uniprot_id: str | None
├── mutation: str | None
├── interaction_partner: str | None
├── question_type: str  (structure / mutation_impact / druggability / binding)
└── sequence: str | None

PredictionResult
├── pdb_content: str
├── confidence_json: dict
├── affinity_json: dict | None
├── plddt_per_residue: list[float]
├── chain_ids: list[str]
├── residue_ids: list[int]
└── compute_source: str  (tamarind / modal / rcsb / precomputed)

TrustAudit
├── overall_confidence: str  (high / medium / low)
├── confidence_score: float
├── ptm: float | None
├── iptm: float | None
├── regions: list[RegionConfidence]
├── known_limitations: list[str]
├── training_data_note: str | None
└── suggested_validation: list[str]

BioContext
├── narrative: str
├── disease_associations: list[DiseaseAssociation]
├── drugs: list[DrugCandidate]
├── literature: LiteratureSummary
├── pathways: list[str]
└── suggested_experiments: list[str]
```

---

## Precomputed Examples (6 Proteins)

| Protein | Mutation | Use Case |
|---------|----------|----------|
| TP53 | R248W | Cancer hotspot, drug resistance |
| BRCA1 | C61G | Breast cancer, structural impact |
| EGFR | T790M | Drug resistance (gefitinib) |
| INS | — | Insulin, diabetes, compact protein |
| SPIKE | — | SARS-CoV-2 RBD, ACE2 binding |
| HBA1 | — | Hemoglobin, thalassemia |

Each includes: `structure.pdb`, `confidence.json`, `metadata.json`, and optional `context/`, `variants/`, `structure_analysis/`

---

## Visualization Types (36+)

### 3D Structure
- Mol* viewer with per-residue pLDDT coloring, tooltips, MVSX embedding

### Heatmaps
- PAE matrix, pLDDT-weighted confidence heatmap, variant impact heatmap (seaborn clustermap)

### Line Charts
- Confidence landscape (pLDDT per residue + SSE strip), pLDDT distribution (histogram + KDE)

### Scatter/Bubble
- Drug landscape (phase × mechanism), residue centrality, variant severity

### Bar Charts
- Pocket scores, SSE composition, hub residue centrality

### Network Graphs
- Interactive knowledge graph (protein → diseases → drugs → pathways)
- Protein Structure Network (PSN) with community detection

### Radar/Spider
- Mutation structural context (SASA, centrality, burial, pocket distance)

### Donut/Pie
- SSE composition percentages

### Sequence Strips
- Amino acid sequence with confidence coloring, domain annotations

### Multi-Track Dashboards
- Residue dashboard: 4-6 parallel tracks (pLDDT, SASA, flexibility, conservation, packing, variants)

### Code Execution Figures (matplotlib/seaborn PNGs)
- Confidence Landscape, Variant Impact Heatmap, Structure Quality Dashboard, Drug-Target Landscape, Mutation in Context

---

## Export Formats

| Format | Content |
|--------|---------|
| PDF | Branded report with metrics, charts, AI narrative, color-coded tables |
| PDB | Raw structure file |
| JSON | Confidence scores, analysis results, full state |
| CSV | Tabular data (variants, pockets, domains) |
| ZIP | Complete analysis bundle (PDB + JSONs + figures) |
| PNG | Code Execution figures, chart screenshots |
| SVG | Graphical abstracts, pathway diagrams |
| HTML | Interactive Plotly charts |
| MP4 | Protein animation videos (Gemini Veo) |
| MMD | Mermaid diagram code |

---

## Background Task System

Thread-pool executor (4 threads) with 2-second polling via `@st.fragment`.

| Task | Backend | Typical Time |
|------|---------|-------------|
| Structure prediction | Tamarind/Modal/RCSB | 10-60s |
| Biological context | Claude MCP | 5-20s |
| AI interpretation | Claude Citations | 3-10s |
| Variant landscape | ClinVar + enrichment | 5-15s |
| Chat response | Agent Tool Use loop | 2-30s |
| Figure generation | Claude Code Execution | 5-15s |
| Video generation | Gemini Veo | 60-180s |

Toast notifications on completion. Pipeline status in sidebar. Non-blocking — users can explore other tabs while tasks run.

---

## UX & Design

- **Theme**: Apple Light Mode (clean white + glassy black accents)
- **Fonts**: Nunito (display + body), Geist Mono (code)
- **WCAG**: AAA contrast (7:1+ for critical text), 44px minimum touch targets
- **CSS**: 56KB custom stylesheet
- **Animations**: DNA character with animated blink + strand wiggle, Lottie sidebar spinner
- **Auth**: Google OAuth via Streamlit native `st.login()`, hero landing page for unauthenticated users
- **Responsive**: Adapts to mobile/tablet/desktop

---

## Deployment

- **Platform**: Railway (auto-deploys on push to master)
- **Domain**: `luminous-dev.up.railway.app`
- **Entrypoint**: `Procfile` → `start.sh` → `streamlit run app.py`
- **Secrets**: Generated at runtime from Railway environment variables
- **Environment Variables**: ANTHROPIC_API_KEY, TAMARIND_API_KEY, GEMINI_API_KEY, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, STREAMLIT_COOKIE_SECRET

---

## Key Differentiators

1. **Structure → Meaning** — solves the "So What?" gap no competitor bridges
2. **Per-residue trust audit** — identifies trustworthy regions for wet lab validation
3. **Disorder detection** — flags AlphaFold hallucinations in intrinsically disordered regions
4. **Drug resistance in 3D** — explains WHY mutations confer resistance structurally
5. **Variant reclassification** — structural context reclassifies Variants of Uncertain Significance
6. **Binding affinity** — Boltz-2 is the only tool predicting ΔG alongside structure
7. **Visual hypothesis sketching** — draw mechanisms, Claude Vision interprets
8. **Citations grounding** — interpretations backed by source documents, not hallucinated
9. **6 Claude features in one app** — Tool Use, Vision, Citations, Code Execution, Extended Thinking, MCP
10. **All 5 sponsors integrated** — Anthropic, Tamarind Bio, Modal, BioRender, Gemini
