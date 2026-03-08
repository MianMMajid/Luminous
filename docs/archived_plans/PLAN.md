# BioVista: The AI Structure Interpreter
## Technical Plan — YC Bio x AI Hackathon, March 2026

---

## One-Liner

"Tell us about a protein. We'll predict its structure, tell you what to trust, explain what it means, and show you what to do next."

## The Problem (Scientifically Grounded)

AI structure prediction tools (AlphaFold, Boltz-2) produce 3D structures, but scientists
are left asking "so what?" There is no tool that:

1. **Surfaces known model limitations** for a specific prediction (Boltz-2 has ~40% false
   positive rate on binders, fails on flexible multi-domain proteins, ignores water/metals)
2. **Cross-references biological databases** to contextualize what the structure means
   (disease associations, known drugs, clinical trials, literature)
3. **Generates actionable next steps** (suggested wet-lab validation experiments)
4. **Produces publication-ready output** (BioRender figures + structured reports)

This is the #1 documented pain point in structural biology (PMC11623436) and zero
competitors at this hackathon are addressing it.

## Track: Scientific Data Visualization

Only 1-2 other teams in this track (vs 10+ in agents). Wide open.

---

## Architecture

```
                    USER INPUT
                        |
                  Natural Language Query
                  "P53 R248W mutation - is it druggable?"
                        |
                        v
              ┌─────────────────────┐
              │   CLAUDE ORCHESTRATOR│
              │   (anthropic SDK)    │
              │                     │
              │  1. Parse intent    │
              │  2. Route to APIs   │
              │  3. Synthesize      │
              └────────┬────────────┘
                       │
          ┌────────────┼────────────────┐
          v            v                v
   ┌──────────┐ ┌───────────┐ ┌─────────────────┐
   │ TAMARIND │ │  CLAUDE   │ │   BIORENDER     │
   │ BIO API  │ │  MCP      │ │   MCP           │
   │          │ │ CONNECTORS│ │   CONNECTOR     │
   │ Boltz-2  │ │           │ │                 │
   │ structure│ │ PubMed    │ │ Generate        │
   │ predict  │ │ Open      │ │ publication     │
   │          │ │ Targets   │ │ figure          │
   │ (backup: │ │ ChEMBL    │ │                 │
   │  Modal)  │ │ bioRxiv   │ │                 │
   └────┬─────┘ └─────┬─────┘ └───────┬─────────┘
        │              │               │
        v              v               v
   ┌──────────────────────────────────────────────┐
   │              STREAMLIT APP                    │
   │                                               │
   │  Tab 1: Query + Status                        │
   │  Tab 2: 3D Structure + Trust Audit            │
   │  Tab 3: Biological Context + Interpretation   │
   │  Tab 4: Report + BioRender Figure + Export    │
   └──────────────────────────────────────────────┘
```

---

## Tech Stack

### Core Framework
| Component | Tool | Version | Why |
|-----------|------|---------|-----|
| Package manager | **uv** | latest | 100x faster than pip, manages Python + venvs + deps |
| Linter/Formatter | **ruff** | latest | 100x faster than flake8+black, catches bugs instantly |
| Python | **3.12** | 3.12.x | Broad library support, good perf |
| App framework | **Streamlit** | 1.55.0 | Molecular viz components, largest ecosystem |
| AI coding | **Claude Code** (this tool) | current | Terminal-native, full codebase awareness, MCP support |

### Python Dependencies
| Package | Purpose |
|---------|---------|
| `streamlit>=1.55` | App framework |
| `anthropic>=0.84` | Claude API (orchestration, interpretation, MCP) |
| `streamlit-molstar>=0.4.21` | 3D protein visualization (Mol* viewer) |
| `py3Dmol>=2.5` | Lightweight 3D molecular rendering |
| `plotly>=6.0` | Interactive heatmaps, charts |
| `biotite>=1.6` | PDB parsing, structure analysis (10x faster than Biopython) |
| `httpx>=0.28` | Async API calls to Tamarind/Modal |
| `pydantic>=2.5` | Data validation, API response models |
| `pandas>=2.2` | DataFrames (Streamlit compatibility) |

### External APIs
| Service | Purpose | Auth | Free Tier |
|---------|---------|------|-----------|
| **Tamarind Bio API** | Boltz-2 structure prediction | API key (`x-api-key`) | 10 jobs/month |
| **Anthropic Claude API** | Orchestration, interpretation, MCP | API key | Pay-as-you-go |
| **BioRender MCP** | Publication figure generation | Via Claude MCP connector | With Claude subscription |
| **Modal** (backup) | Serverless GPU for Boltz-2 | API token | Free tier credits |
| **RCSB PDB API** | Fetch known structures | None (public) | Unlimited |
| **UniProt API** | Protein metadata | None (public) | Unlimited |

### MCP Servers (The Secret Weapon)

**BioMCP** (biomcp.org) — single Rust binary wrapping 15+ databases. Install: `curl -fsSL https://biomcp.org/install.sh | bash`

| Entity | Data Sources Covered |
|--------|---------------------|
| Gene | MyGene.info, UniProt, Reactome, QuickGO, STRING, CIViC |
| Variant | MyVariant.info, ClinVar, gnomAD, CIViC, OncoKB, cBioPortal, GWAS Catalog |
| Article | PubMed, PubTator3, Europe PMC |
| Trial | ClinicalTrials.gov, NCI CTS API |
| Drug | MyChem.info, ChEMBL, OpenTargets, Drugs@FDA, CIViC |
| Disease | Monarch Initiative, MONDO, CIViC, OpenTargets |
| Pathway | Reactome, g:Profiler |
| Protein | UniProt, InterPro, STRING, PDB/AlphaFold |

**Additional MCP Connectors:**

| MCP Server | Type | Endpoint/Install |
|------------|------|-----------------|
| BioRender | Official (Anthropic) | `https://mcp.services.biorender.com/mcp` |
| Open Targets | Official (OT) | `https://mcp.platform.opentargets.org/mcp` |
| PubMed | Official (Anthropic) | Via life-sciences plugin |
| ChEMBL | deepsense.ai | `https://mcp.deepsense.ai/chembl/mcp` |
| PDB-MCP-Server | Community | github.com/Augmented-Nature/PDB-MCP-Server |
| AlphaFold MCP | Community | github.com/Augmented-Nature/AlphaFold-MCP-Server |
| UniProt MCP | Community | github.com/Augmented-Nature/Augmented-Nature-UniProt-MCP-Server |

**Claude Desktop MCP Config** (`~/Library/Application Support/Claude/claude_desktop_config.json`):
```json
{
  "mcpServers": {
    "biomcp": {
      "command": "biomcp",
      "args": ["serve"]
    },
    "open-targets": {
      "url": "https://mcp.platform.opentargets.org/mcp"
    }
  }
}
```

---

## Project Structure

```
BioxYC/
├── PLAN.md                    # This file
├── pyproject.toml             # uv project config + dependencies
├── .python-version            # Python 3.12
├── ruff.toml                  # Ruff config
├── .streamlit/
│   └── config.toml            # Streamlit theme (dark, wide layout)
├── app.py                     # Main Streamlit entry point (tab router)
├── src/
│   ├── __init__.py
│   ├── config.py              # API keys, constants, model configs
│   ├── query_parser.py        # Claude-powered NL query parsing
│   ├── structure_predictor.py # Tamarind API / Modal Boltz-2 client
│   ├── trust_auditor.py       # Confidence analysis + known limitations
│   ├── bio_context.py         # Claude MCP queries (Open Targets, ChEMBL, PubMed)
│   ├── interpreter.py         # Claude synthesis of all data into narrative
│   ├── figure_generator.py    # BioRender MCP figure generation
│   ├── models.py              # Pydantic models for all data structures
│   └── utils.py               # PDB parsing, color mapping, shared helpers
├── components/
│   ├── __init__.py
│   ├── query_input.py         # Tab 1: NL input + query status
│   ├── structure_viewer.py    # Tab 2: 3D viewer + trust audit overlay
│   ├── context_panel.py       # Tab 3: Biological interpretation
│   └── report_export.py       # Tab 4: Report + BioRender figure + downloads
├── data/
│   ├── known_limitations.json # Boltz-2/AlphaFold documented failure modes
│   ├── example_queries.json   # Pre-loaded demo queries
│   └── precomputed/           # Pre-computed results for demo fallback
│       ├── p53_r248w.pdb
│       ├── p53_r248w_audit.json
│       └── p53_r248w_context.json
└── tests/
    └── test_pipeline.py       # Smoke tests for each component
```

---

## Detailed Component Specs

### Tab 1: Smart Query Input (`components/query_input.py`)

**Purpose**: Accept natural language, parse intent, launch prediction.

**UI Elements**:
- Text input: "Describe a protein, mutation, or drug interaction..."
- Example buttons: pre-loaded queries (P53 R248W, BRCA1 C61G, EGFR T790M)
- Query parsing display: show Claude's structured interpretation
- Status indicator: pipeline progress (parsing → predicting → analyzing → done)

**Backend** (`src/query_parser.py`):
```python
# Claude parses NL query into structured format
class ProteinQuery(BaseModel):
    protein_name: str           # e.g., "TP53"
    uniprot_id: str | None      # e.g., "P04637"
    mutation: str | None        # e.g., "R248W"
    interaction_partner: str | None  # e.g., "MDM2"
    question_type: Literal["structure", "mutation_impact", "druggability", "binding"]
    fasta_sequence: str | None  # if provided directly

# System prompt instructs Claude to extract structured fields
# from natural language, resolve protein names to UniProt IDs,
# and validate mutation notation
```

**Time estimate**: 1.5 hours

---

### Tab 2: 3D Structure + Trust Audit (`components/structure_viewer.py`)

**Purpose**: Display predicted structure with per-residue confidence coloring and
trust audit overlay. This is the HERO SCREEN — the demo centerpiece.

**UI Elements**:
- Left panel (70%): streamlit-molstar 3D viewer
  - Rotatable, zoomable protein structure
  - Color mode toggle: "By Chain" / "By Confidence (pLDDT)" / "By Trust Audit"
  - If mutation query: side-by-side wild-type vs mutant (two viewers)
- Right panel (30%): Trust Audit Card
  - Overall confidence score (traffic light: green/yellow/red)
  - Per-region breakdown (table with residue ranges + confidence levels)
  - Known model limitations for THIS specific target (from known_limitations.json + Claude analysis)
  - Training data bias assessment (PDB structure count for this protein/variant)

**Backend** (`src/structure_predictor.py` + `src/trust_auditor.py`):

Structure Prediction:
```python
# Primary: Tamarind Bio API
# POST https://app.tamarind.bio/api/v1/jobs
# Headers: x-api-key: <key>
# Body: { "model": "boltz2", "inputs": { ... } }
# Poll for completion, download PDB result

# Fallback: Modal with official Boltz-2 example
# modal.Function.lookup("boltz2-predict", "predict")
```

Trust Audit:
```python
class TrustAudit(BaseModel):
    overall_confidence: Literal["high", "medium", "low"]
    per_region: list[RegionConfidence]  # residue range + pLDDT + flags
    known_limitations: list[str]        # from DB + Claude analysis
    training_data_bias: TrainingBias    # PDB structure count, representation
    model_disagreement: str | None      # Boltz-2 vs AlphaFold comparison
    recommended_validation: list[str]   # suggested experiments

# Key logic:
# 1. Parse pLDDT from Boltz-2 output (per-residue confidence)
# 2. Flag regions with pLDDT < 70 as low confidence
# 3. Query RCSB PDB API: count structures for this protein/variant
# 4. Match target against known_limitations.json:
#    - Is it a flexible multi-domain protein? (Boltz-2 failure mode)
#    - Does it require water-mediated contacts? (Boltz-2 ignores these)
#    - Is it a membrane protein? (Boltz-2 weak on GPCRs)
#    - Ligand > 128 atoms? (Boltz-2 can't compute affinity)
# 5. Claude synthesizes findings into plain-English trust assessment
```

**Color Mapping for 3D Viewer**:
```python
# pLDDT-based coloring (AlphaFold convention):
# > 90: Deep blue (very high confidence)
# 70-90: Light blue (confident)
# 50-70: Yellow (low confidence)
# < 50: Orange/Red (very low confidence — interpret with caution)

# Trust audit overlay adds:
# Red border/highlight on regions matching known failure modes
# Pulsing animation on flagged residues (if supported)
```

**Time estimate**: 3 hours (most complex component)

---

### Tab 3: Biological Context + Interpretation (`components/context_panel.py`)

**Purpose**: Answer "So What?" with database-backed biological context.

**UI Elements**:
- AI Interpretation Panel (full-width card):
  - Plain-English narrative: "This mutation destabilizes the DNA-binding domain..."
  - Key findings bullets with source citations
- Disease Associations (expandable):
  - Open Targets data: diseases linked to this protein/variant
  - Clinical significance (pathogenic/benign/VUS status)
- Drug Landscape (expandable):
  - ChEMBL compounds targeting this protein/region
  - Clinical trial status for each compound
  - Whether the specific mutation affects drug binding
- Literature (expandable):
  - Recent paper count from PubMed
  - Key paper summaries from bioRxiv/PubMed
  - Link to full search results
- Pathway Context (compact):
  - Key pathways involving this protein (from Open Targets)
  - Upstream/downstream regulators

**Backend** (`src/bio_context.py` + `src/interpreter.py`):
```python
# Claude with MCP connectors queries all databases in parallel:
# 1. Open Targets: disease associations, genetic evidence, target tractability
# 2. ChEMBL: compounds, bioactivity data, clinical trials
# 3. PubMed: paper count, key abstracts
# 4. bioRxiv: recent preprints
# 5. UniProt: protein function, domains, PTMs

# Claude synthesizes all results into a structured interpretation
class BiologicalContext(BaseModel):
    narrative: str                    # Plain-English interpretation
    disease_associations: list[DiseaseAssoc]
    drugs: list[DrugCandidate]
    literature_summary: LiteratureSummary
    pathways: list[PathwayInfo]
    suggested_experiments: list[str]  # wet-lab validation steps
```

**Time estimate**: 2.5 hours

---

### Tab 4: Report + Export (`components/report_export.py`)

**Purpose**: Package everything into downloadable, shareable outputs.

**UI Elements**:
- Report preview: rendered markdown summary of all findings
- BioRender figure: AI-generated publication-quality mechanism figure
- Download buttons:
  - PDB file (predicted structure)
  - PDF report (trust audit + context + interpretation)
  - BioRender figure (SVG/PNG)
  - JSON data (raw structured results for programmatic use)
- Share link (if time permits): unique URL for this analysis

**Backend** (`src/figure_generator.py`):
```python
# BioRender MCP connector:
# Claude generates a BioRender figure description
# MCP connector searches for relevant icons/templates
# Composes a figure showing:
#   - Protein structure schematic
#   - Mutation location highlighted
#   - Drug binding mechanism
#   - Key pathway connections

# Fallback if BioRender MCP is unavailable:
# Generate a Plotly-based summary figure with:
#   - Structure confidence plot
#   - Drug pipeline status chart
#   - Disease association heatmap
```

**Time estimate**: 1.5 hours

---

## Data Files to Pre-Build

### `data/known_limitations.json`
```json
{
  "boltz2": {
    "general": [
      "~40% false positive rate on predicted binders (DeepMirror, 2025)",
      "Cannot model water-mediated interactions",
      "Cannot model metal coordination or cofactors",
      "Limited to ligands < 128 atoms (excludes PROTACs, peptides)",
      "No protein-protein interaction affinity prediction",
      "Single static snapshot — no conformational dynamics"
    ],
    "target_flags": {
      "flexible_multi_domain": {
        "description": "Boltz-2 fails on flexible multi-domain proteins",
        "examples": ["PI3K-alpha", "WRN Helicase", "cGAS"],
        "evidence": "DeepMirror 2025: SAR correlation collapsed to r=0.26 on cGAS"
      },
      "membrane_protein": {
        "description": "Poor performance on GPCRs, transporters, ion channels",
        "evidence": "Benchmark variance increases substantially due to sparse training data"
      },
      "allosteric_site": {
        "description": "Cannot capture allosteric conformational changes",
        "evidence": "WRN Helicase: reverted to ATP-bound instead of required ATP-free conformation"
      },
      "intrinsically_disordered": {
        "description": "~30% of human proteins are intrinsically disordered; out of reach",
        "evidence": "Harvard/Northwestern 2025 paper on IDP design acknowledges this gap"
      }
    }
  },
  "alphafold": {
    "general": [
      "Running out of training data (PDB is 94% non-pharma structures)",
      "RNA structure failures with monovalent ions",
      "Cannot predict novel drug interactions",
      "Training data bias toward common conformations",
      "Single conformational state only"
    ]
  }
}
```

### `data/example_queries.json`
```json
[
  {
    "label": "P53 Cancer Mutation",
    "query": "What happens when P53 has the R248W mutation? Is it druggable?",
    "protein": "TP53",
    "uniprot": "P04637",
    "mutation": "R248W"
  },
  {
    "label": "BRCA1 Breast Cancer",
    "query": "Analyze the BRCA1 C61G variant and its impact on DNA repair",
    "protein": "BRCA1",
    "uniprot": "P38398",
    "mutation": "C61G"
  },
  {
    "label": "EGFR Drug Resistance",
    "query": "EGFR T790M mutation - why does it cause drug resistance to gefitinib?",
    "protein": "EGFR",
    "uniprot": "P00533",
    "mutation": "T790M"
  }
]
```

---

## Build Schedule (Hackathon Day)

### Pre-Hackathon (Night Before) — 3 hours
| Task | Time | Status |
|------|------|--------|
| `uv init` + install all deps + lock | 15 min | |
| Test Tamarind API: submit Boltz-2 job, poll, download PDB | 45 min | |
| Test Claude API + MCP connectors (PubMed, Open Targets, ChEMBL) | 45 min | |
| Test BioRender MCP connector | 30 min | |
| Test streamlit-molstar with real PDB file | 20 min | |
| Pre-compute 3 example results (P53, BRCA1, EGFR) as demo fallback | 15 min | |
| Set up Modal account + test Boltz-2 (backup) | 30 min | |

### Hour 0-1: Scaffold + Query Input
- [ ] `app.py`: Streamlit page config (wide, dark theme), tab structure
- [ ] `src/config.py`: API keys from env vars, constants
- [ ] `src/models.py`: All Pydantic models
- [ ] `components/query_input.py`: Text input + example buttons + Claude parsing
- [ ] `src/query_parser.py`: Claude NL → ProteinQuery structured output

### Hour 1-3: Structure Prediction + Trust Audit (HERO SCREEN)
- [ ] `src/structure_predictor.py`: Tamarind API client (submit, poll, download)
- [ ] `src/trust_auditor.py`: pLDDT parsing, known limitations matching, PDB count
- [ ] `components/structure_viewer.py`: streamlit-molstar with confidence coloring
- [ ] Trust audit panel (traffic light + per-region table + limitations)
- [ ] Wire Tab 1 → Tab 2 (query result flows to structure view)

### Hour 3-4: Biological Context
- [ ] `src/bio_context.py`: Claude MCP queries to Open Targets, ChEMBL, PubMed
- [ ] `src/interpreter.py`: Claude synthesis into narrative + structured findings
- [ ] `components/context_panel.py`: Interpretation card + expandable sections
- [ ] Wire Tab 2 → Tab 3 (structure data feeds into context)

### Hour 4-5: Report + BioRender + Export
- [ ] `src/figure_generator.py`: BioRender MCP figure generation
- [ ] `components/report_export.py`: Report preview + download buttons
- [ ] PDF generation (or markdown export as fallback)
- [ ] Wire Tab 3 → Tab 4 (all data flows to export)

### Hour 5-6: Integration + Edge Cases
- [ ] End-to-end pipeline test with all 3 example queries
- [ ] Error handling: API timeouts, missing data, fallback to precomputed
- [ ] Loading states and progress indicators for long operations
- [ ] Session state management (cache results across tabs)

### Hour 6-7: Polish + Demo Prep
- [ ] UI polish: colors, spacing, card styling via st.markdown CSS
- [ ] Pre-warm Tamarind/Modal containers
- [ ] Write demo script (exact clicks, exact words)
- [ ] Test demo flow 3x end-to-end
- [ ] Screenshot fallbacks for any flaky components

### Hour 7-8: Buffer
- [ ] Bug fixes from demo testing
- [ ] Final polish pass
- [ ] Prepare 2-minute and 5-minute versions of demo

---

## Demo Script (5 minutes)

### Slide 0: Title (15 sec)
"BioVista — the AI Structure Interpreter. Scientists get structure predictions
and ask 'so what?' We answer that question."

### Live Demo (3.5 min)

**[Tab 1]** "I type: 'What happens when P53 has the R248W mutation? Is it druggable?'"
→ Claude parses the query, identifies TP53, UniProt P04637, mutation R248W
→ "Submitting to Boltz-2 via Tamarind Bio's API..."

**[Tab 2]** "Here's the predicted structure. But look — we don't just show it."
→ Point to confidence coloring: "Blue regions are high confidence. This yellow loop
at 240-260 is where the mutation sits — and our trust audit flags it."
→ Show Trust Audit panel: "Boltz-2 has documented failures on this type of flexible
loop region. Training data has 4,200 wild-type P53 structures vs only 12 for R248W.
We recommend validating with X-ray crystallography."

**[Tab 3]** "Now the 'so what?' — Claude queries Open Targets, ChEMBL, and PubMed."
→ "R248W is a gain-of-function hotspot in 7.2% of TP53-mutated cancers."
→ "Three compounds in clinical trials target this region: APR-246 in Phase III."
→ "142 papers in the last 12 months. Here's the AI-generated summary."

**[Tab 4]** "One click: download the PDB, the full report, and this BioRender figure."
→ Show BioRender-generated mechanism figure

### Closing (1 min)
"Every scientist using Boltz-2, AlphaFold, or any structure prediction tool needs
this. No tool tells you what to trust, what it means, or what to do next. We built
the accountability layer that bio AI has been missing."

"BioVista uses all five sponsor tools: Tamarind Bio for predictions, Claude for
interpretation via MCP connectors to PubMed/Open Targets/ChEMBL, BioRender for
publication figures, Modal for compute, and the pipeline is end-to-end."

---

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Tamarind API slow/down | Pre-computed results in `data/precomputed/` as instant fallback |
| Modal cold start during demo | Pre-warm container 10 min before demo |
| BioRender MCP unavailable | Plotly fallback figure (bar chart + pathway diagram) |
| Claude rate limits | Cache all Claude responses in session state |
| MCP connectors fail | Direct API calls to Open Targets/ChEMBL REST APIs as backup |
| Streamlit performance | `@st.cache_data` on all API calls, `@st.fragment` on heavy components |
| Demo crashes | Screenshot deck as absolute last resort |

---

## Sponsor Alignment Checklist

- [x] **Tamarind Bio** (co-organizer): API is the primary prediction backend
- [x] **BioRender** (co-organizer): MCP connector for figure generation
- [x] **Anthropic/Claude** (sponsor): Orchestration + interpretation + ALL MCP connectors
- [x] **Modal** (sponsor): Backup compute for Boltz-2
- [x] **OpenAI** (sponsor): Can add GPT comparison for interpretation (if time)

---

## What Makes This Win

1. **Solves the #1 pain point**: Structure → "So What?" gap (documented, peer-reviewed)
2. **Scientifically rigorous**: Real model limitations, real database cross-references, citations
3. **Empty competitive track**: 1-2 teams in viz vs 10+ in agents
4. **ALL sponsors featured**: Only project deeply integrating both organizers + all sponsors
5. **Visually memorable**: 3D protein with trust audit heatmap + BioRender figure
6. **Fundable thesis**: "Accountability layer for bio AI" — see Strand AI (YC'26)
7. **Working demo**: Pre-computed fallbacks ensure it NEVER crashes
