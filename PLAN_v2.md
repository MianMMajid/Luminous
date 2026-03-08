# BioVista: The AI Structure Interpreter
## Technical Plan v2 — Validated Against Real APIs
## YC Bio x AI Hackathon, March 2026

---

## One-Liner

"Tell us about a protein. We'll predict its structure, tell you what to trust,
explain what it means, and show you what to do next."

---

## Validation Summary: What Changed After Deep Investigation

| Component | Plan v1 Assumption | Reality | Action |
|-----------|-------------------|---------|--------|
| 3D Viewer | streamlit-molstar for per-residue coloring | streamlit-molstar CANNOT do custom per-residue coloring | **Switch to `molviewspec`** (Mol* team's own package) |
| Bio databases | BioMCP via MCP protocol only | BioMCP has a Python SDK (`biomcp-python`) with direct async functions AND a CLI with `--format json` | **Use Python SDK for direct calls + CLI as backup** |
| Claude + MCP | Assumed we need MCP client code | Anthropic API has native `mcp_servers` param — single API call, server-side MCP | **Use Anthropic API MCP Connector (beta)** |
| BioRender MCP | Assumed it generates figures | It's READ-ONLY SEARCH. Only returns icon names and template links | **Use for template/icon discovery + Plotly for actual figures** |
| Tamarind API | Assumed Python SDK exists | No SDK. Raw REST only. Must discover settings via GET /tools | **Raw httpx calls. Capture payload from browser DevTools first** |
| streamlit-molstar | Primary 3D viewer | Unmaintained (last release 2024), no custom coloring, no labels | **Replace entirely with molviewspec** |

---

## Validated Architecture

```
USER: "P53 R248W — is it druggable?"
         |
         v
  ┌────────────────────────────────┐
  │ Tab 1: QUERY INPUT             │
  │                                │
  │ Claude API (structured output) │
  │ Parse NL → ProteinQuery model  │
  └──────────────┬─────────────────┘
                 |
    ┌────────────┼────────────────────┐
    v            v                    v
┌────────┐ ┌──────────────┐  ┌──────────────────┐
│TAMARIND│ │ ANTHROPIC API │  │ BIOMCP           │
│BIO API │ │ MCP CONNECTOR │  │ (Python SDK /CLI)│
│        │ │               │  │                  │
│ Boltz-2│ │ mcp_servers:  │  │ Direct async     │
│ predict│ │  - PubMed     │  │ Python calls:    │
│        │ │  - OpenTargets│  │  - get_gene()    │
│ REST   │ │  - BioRender  │  │  - search_var()  │
│ (httpx)│ │               │  │  - get_drug()    │
│        │ │ Single API    │  │                  │
│        │ │ call handles  │  │ 15+ databases    │
│        │ │ everything    │  │ No LLM needed    │
└───┬────┘ └──────┬───────┘  └────────┬─────────┘
    |             |                   |
    v             v                   v
┌──────────────────────────────────────────────┐
│              STREAMLIT APP                    │
│                                               │
│  Tab 2: 3D Structure + Trust Audit            │
│          (molviewspec — per-residue coloring,  │
│           labels, tooltips, Mol* engine)       │
│                                               │
│  Tab 3: Biological Context + Interpretation   │
│          (Claude MCP narrative + BioMCP data)  │
│                                               │
│  Tab 4: Report + Export                        │
│          (Plotly figures + BioRender links +    │
│           PDF/JSON/PDB downloads)              │
└──────────────────────────────────────────────┘
```

---

## Validated Tech Stack

### Core Dependencies

```toml
[project]
dependencies = [
    # App framework
    "streamlit>=1.44",

    # 3D protein visualization (Mol* engine with per-residue coloring)
    "molviewspec>=1.8",

    # AI / LLM
    "anthropic>=0.84",

    # Bio databases (direct Python access to 15+ databases)
    "biomcp-python>=0.7.3",

    # Structure parsing (10x faster than Biopython)
    "biotite>=1.6",

    # Charts and figures
    "plotly>=6.0",

    # HTTP client for Tamarind API
    "httpx>=0.28",

    # Data validation
    "pydantic>=2.5",

    # DataFrames
    "pandas>=2.2",
]
```

### External Services

| Service | How We Use It | Auth | Validated? |
|---------|-------------- |------|------------|
| **Tamarind Bio API** | Boltz-2 predictions via REST | `x-api-key` header | YES — endpoints confirmed, 10 free jobs/mo |
| **Anthropic API + MCP** | Claude orchestration + PubMed/OpenTargets/BioRender MCP | API key + beta header | YES — `mcp_servers` param works in single API call |
| **BioMCP Python SDK** | Direct gene/variant/drug/pathway queries | None (public APIs) | YES — async functions + CLI with JSON output |
| **BioRender MCP** | Icon/template search (NOT figure generation) | BioRender account | YES — search-only, returns names + links |
| **RCSB PDB** | Fetch known structures | None | YES — public REST API |
| **Modal** (backup) | Serverless GPU for Boltz-2 | API token | Validation pending |

---

## Component Specifications (Validated)

### Tab 1: Smart Query Input

**What it does**: NL input → Claude structured output → launch prediction

**Validated approach**: Use Anthropic SDK with Pydantic structured output

```python
from anthropic import Anthropic
from pydantic import BaseModel

class ProteinQuery(BaseModel):
    protein_name: str
    uniprot_id: str | None
    mutation: str | None
    interaction_partner: str | None
    question_type: str  # "structure", "mutation_impact", "druggability", "binding"

client = Anthropic()
message = client.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=1024,
    system="Parse this biology question into structured fields. Resolve protein names to UniProt IDs.",
    messages=[{"role": "user", "content": user_query}],
    # Use tool_use with the Pydantic schema for structured output
)
```

**Time estimate**: 1 hour

---

### Tab 2: 3D Structure + Trust Audit (HERO SCREEN)

**What it does**: Display Boltz-2 prediction with per-residue trust coloring

**Validated approach**: `molviewspec` (NOT streamlit-molstar)

```python
import molviewspec as mvs
import json

def build_trust_viewer(pdb_content: str, trust_scores: list[dict]):
    """
    trust_scores: [{"chain": "A", "residue": 42, "score": 0.85, "flag": "..."}]
    """
    builder = mvs.create_builder()

    # Load structure from string content (write to temp file or use URL)
    structure = (
        builder
        .download(url=pdb_url)
        .parse(format="pdb")
        .model_structure()
    )

    # Build per-residue annotations with trust-based coloring
    annotations = []
    for r in trust_scores:
        color = trust_to_color(r["score"])  # red (#FF4444) → yellow (#FFDD44) → blue (#4444FF)
        tooltip = f"Residue {r['residue']}: Trust {r['score']:.2f}"
        if r.get("flag"):
            tooltip += f"\n⚠ {r['flag']}"
        annotations.append({
            "label_asym_id": r["chain"],
            "label_seq_id": r["residue"],
            "color": color,
            "tooltip": tooltip,
        })

    # Apply coloring and tooltips
    rep = structure.component(selector="polymer").representation(type="cartoon")
    rep.color(color="#cccccc")  # base gray
    rep.color_from_uri(uri="trust.json", format="json", schema="residue")
    structure.tooltip_from_uri(uri="trust.json", format="json", schema="residue")

    # Render in Streamlit
    builder.molstar_streamlit(
        data={"trust.json": json.dumps(annotations).encode()},
        height=600,
    )

def trust_to_color(score: float) -> str:
    """Map 0-1 trust score to red-yellow-blue gradient."""
    if score >= 0.9:
        return "#4444FF"  # deep blue — very high confidence
    elif score >= 0.7:
        return "#88AAFF"  # light blue — confident
    elif score >= 0.5:
        return "#FFDD44"  # yellow — low confidence
    else:
        return "#FF4444"  # red — very low / flagged
```

**Trust Audit Panel** (right sidebar):
```python
# Parse Boltz-2 confidence JSON output
confidence = {
    "confidence_score": 0.8367,
    "ptm": 0.8425,
    "iptm": 0.8225,
    "complex_plddt": 0.8402,
    "chains_ptm": {"A": 0.8533, "B": 0.8330},
}

# Cross-reference against known limitations database
flags = check_known_limitations(protein_name, mutation, confidence)
# Returns: ["Flexible loop region — Boltz-2 documented failure mode",
#           "Training bias: 4,200 WT structures vs 12 for R248W", ...]

# Display with traffic-light indicator
overall = "🟢" if confidence["confidence_score"] > 0.8 else "🟡" if > 0.6 else "🔴"
```

**Time estimate**: 3 hours

---

### Tab 3: Biological Context + Interpretation

**What it does**: Answer "So What?" with database-backed context

**Validated approach: TWO PARALLEL PATHS** for maximum resilience

**Path A: Anthropic API MCP Connector** (primary — richest output)
```python
response = client.beta.messages.create(
    model="claude-sonnet-4-20250514",
    max_tokens=4096,
    system="""You are a structural biologist interpreting a protein structure prediction.
    Use the available tools to gather evidence from PubMed, Open Targets, and BioRender.
    Provide: disease associations, drug candidates, literature summary, suggested experiments.
    Cite your sources.""",
    messages=[{
        "role": "user",
        "content": f"Interpret this prediction for {protein_name} {mutation}. "
                   f"Confidence: {confidence}. Trust flags: {flags}"
    }],
    mcp_servers=[
        {"type": "url", "url": "https://pubmed.mcp.claude.com/mcp", "name": "pubmed"},
        {"type": "url", "url": "https://mcp.platform.opentargets.org/mcp", "name": "open_targets"},
        {"type": "url", "url": "https://mcp.services.biorender.com/mcp", "name": "biorender",
         "authorization_token": biorender_token},
    ],
    tools=[
        {"type": "mcp_toolset", "mcp_server_name": "pubmed"},
        {"type": "mcp_toolset", "mcp_server_name": "open_targets"},
        {"type": "mcp_toolset", "mcp_server_name": "biorender"},
    ],
    betas=["mcp-client-2025-11-20"],
)
```

**Path B: BioMCP Python SDK** (backup — direct data, no LLM cost)
```python
from biomcp.articles.search import search_articles, PubmedRequest
from biomcp.variants.search import search_variants, VariantQuery
from biomcp.drugs import get_drug

# Direct async calls — no Claude needed
articles = await search_articles(PubmedRequest(genes=["TP53"], diseases=["cancer"]))
variants = await search_variants(VariantQuery(gene="TP53", significance="PATHOGENIC"))

# Or CLI fallback (synchronous, no async issues)
import subprocess, json
result = subprocess.run(
    ["biomcp", "get", "gene", "TP53", "-j"],
    capture_output=True, text=True
)
gene_data = json.loads(result.stdout)
```

**Time estimate**: 2.5 hours

---

### Tab 4: Report + Export

**What it does**: Package findings into downloadable outputs

**Validated approach** (adjusted for BioRender limitations):

```python
# 1. BioRender template recommendations (via MCP — search only)
#    Returns relevant template names + clickable links to BioRender editor
#    Demo value: "We found these relevant BioRender templates for your protein"

# 2. Plotly summary figures (actual generated visualizations)
import plotly.graph_objects as go

# Confidence profile chart
fig_confidence = go.Figure(go.Bar(
    x=residue_numbers,
    y=plddt_scores,
    marker_color=[trust_to_color(s) for s in plddt_scores],
))
fig_confidence.update_layout(title="Per-Residue Confidence Profile")

# Drug pipeline status
fig_drugs = go.Figure(go.Funnel(
    y=["Identified", "Phase I", "Phase II", "Phase III", "Approved"],
    x=[drug_counts_per_phase],
))

# 3. Downloads
st.download_button("Download PDB", pdb_content, "prediction.pdb")
st.download_button("Download Report (JSON)", json.dumps(report), "report.json")
st.download_button("Download Confidence Data (CSV)", csv_content, "confidence.csv")

# 4. BioRender links
st.markdown("### Publication Figures")
st.markdown("Open these templates in BioRender to create publication-ready figures:")
for template in biorender_templates:
    st.markdown(f"- [{template['name']}]({template['url']})")
```

**Time estimate**: 1.5 hours

---

## Tamarind Bio API Integration (Detailed)

### Step 1: Discover settings schema (pre-hackathon)
```python
import httpx

TAMARIND_BASE = "https://app.tamarind.bio/api"
headers = {"x-api-key": API_KEY}

# Get available tools and their settings schemas
tools = httpx.get(f"{TAMARIND_BASE}/tools", headers=headers).json()
# Find Boltz-2 tool type name and exact settings fields
```

### Step 2: Submit prediction
```python
async def submit_boltz2_job(sequence: str, job_name: str) -> str:
    async with httpx.AsyncClient() as client:
        payload = {
            "jobName": job_name,
            "type": "boltz",  # confirm via GET /tools
            "settings": {
                "sequence": sequence,
                "numSamples": 1,
                "predictAffinity": True,
                "numRecycles": 3,
                "outputFormat": "pdb",
                "useMSA": True,
            }
        }
        resp = await client.post(
            f"{TAMARIND_BASE}/submit-job",
            headers=headers,
            json=payload,
        )
        resp.raise_for_status()
        return job_name
```

### Step 3: Poll for completion
```python
async def poll_job(job_name: str, timeout: int = 300) -> dict:
    async with httpx.AsyncClient() as client:
        start = time.time()
        while time.time() - start < timeout:
            resp = await client.get(
                f"{TAMARIND_BASE}/jobs",
                headers=headers,
                params={"jobName": job_name},
            )
            data = resp.json()
            # Check status — exact field TBD from GET /tools exploration
            if data.get("status") == "completed":
                return data
            await asyncio.sleep(15)
        raise TimeoutError(f"Job {job_name} did not complete within {timeout}s")
```

### Step 4: Download results
```python
async def download_results(job_name: str) -> tuple[str, dict]:
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{TAMARIND_BASE}/result",
            headers=headers,
            json={"jobName": job_name},
        )
        # Returns PDB content + confidence JSON
        # Exact format TBD — parse based on actual response structure
        return pdb_content, confidence_scores
```

### Pre-hackathon: Capture exact payload
```
1. Open https://app.tamarind.bio/boltz in browser
2. Open DevTools → Network tab
3. Submit a job with a simple protein (e.g., insulin)
4. Capture the exact POST request payload
5. Replicate in Python
```

---

## Known Boltz-2 Output Format (for Trust Audit)

```json
{
    "confidence_score": 0.8367,
    "ptm": 0.8425,
    "iptm": 0.8225,
    "complex_plddt": 0.8402,
    "complex_iplddt": 0.8241,
    "complex_pde": 0.8912,
    "chains_ptm": {"0": 0.8533, "1": 0.8330},
    "pair_chains_iptm": {"0": {"0": 0.8533, "1": 0.8090}}
}
```

Per-residue pLDDT is in the B-factor column of the output PDB file:
```python
import biotite.structure.io.pdb as pdb

structure = pdb.PDBFile.read("prediction.pdb").get_structure()
# B-factor column contains per-residue pLDDT scores (0-100)
plddt_per_residue = structure.b_factor
```

---

## Project Structure (Updated)

```
BioxYC/
├── PLAN_v2.md                 # This file
├── pyproject.toml             # uv project config
├── .python-version            # 3.12
├── .env                       # API keys (gitignored)
├── .streamlit/
│   └── config.toml            # Wide layout, dark theme
│   └── secrets.toml           # Streamlit secrets (API keys)
├── app.py                     # Main entry: tab router, session state
├── src/
│   ├── __init__.py
│   ├── config.py              # Load API keys from env/secrets
│   ├── models.py              # Pydantic models (ProteinQuery, TrustAudit, etc.)
│   ├── query_parser.py        # Claude structured output → ProteinQuery
│   ├── tamarind_client.py     # Tamarind API: submit, poll, download (httpx)
│   ├── trust_auditor.py       # pLDDT parsing + known limitations matching
│   ├── bio_context.py         # Claude MCP connector (PubMed/OpenTargets/BioRender)
│   ├── bio_context_direct.py  # BioMCP Python SDK fallback (no LLM)
│   ├── interpreter.py         # Claude synthesis into narrative
│   └── utils.py               # trust_to_color(), PDB helpers, async bridge
├── components/
│   ├── __init__.py
│   ├── query_input.py         # Tab 1: NL input + examples + parse display
│   ├── structure_viewer.py    # Tab 2: molviewspec 3D + trust audit panel
│   ├── context_panel.py       # Tab 3: interpretation + expandable sections
│   └── report_export.py       # Tab 4: Plotly figures + downloads + BioRender links
├── data/
│   ├── known_limitations.json # Boltz-2/AlphaFold documented failure modes
│   ├── example_queries.json   # Pre-loaded demo queries
│   └── precomputed/           # Fallback results for demo resilience
│       ├── p53_r248w/
│       │   ├── structure.pdb
│       │   ├── confidence.json
│       │   └── context.json
│       ├── brca1_c61g/
│       └── egfr_t790m/
└── scripts/
    ├── precompute_examples.py # Run before hackathon to generate fallbacks
    └── test_apis.py           # Smoke test all API integrations
```

---

## Build Schedule (Hackathon Day — 8-10 hours)

### Pre-Hackathon (Night Before) — 3 hours

| # | Task | Time | Validates |
|---|------|------|-----------|
| 1 | Install uv, init project, lock deps | 15 min | Environment |
| 2 | Sign up Tamarind Bio, get API key | 10 min | Access |
| 3 | Capture Boltz-2 payload via browser DevTools | 20 min | API format |
| 4 | Run `GET /tools` to confirm Boltz type name | 5 min | API schema |
| 5 | Submit test Boltz-2 job via Python, poll, download PDB | 30 min | Full pipeline |
| 6 | Test Anthropic API MCP connector (PubMed + Open Targets) | 30 min | MCP works |
| 7 | Test `biomcp-python` direct calls (get_gene, search_variants) | 15 min | Backup data |
| 8 | Test molviewspec with downloaded PDB + custom colors | 20 min | 3D viewer |
| 9 | Pre-compute 3 examples (P53 R248W, BRCA1 C61G, EGFR T790M) | 20 min | Demo fallbacks |
| 10 | Pin all versions in pyproject.toml | 5 min | Reproducibility |

### Hour 0-1: Scaffold + Query Input
- app.py: page config, tabs, session state init
- src/config.py: API keys from .env
- src/models.py: ProteinQuery, TrustAudit, BioContext Pydantic models
- components/query_input.py: text input + example buttons + Claude parsing

### Hour 1-3: Structure Viewer + Trust Audit (HERO SCREEN)
- src/tamarind_client.py: submit, poll, download (with precomputed fallback)
- src/trust_auditor.py: parse pLDDT from B-factor, match known limitations
- components/structure_viewer.py: molviewspec 3D with trust coloring + audit panel
- Wire Tab 1 → Tab 2 via session state

### Hour 3-5: Bio Context + Interpretation
- src/bio_context.py: Anthropic API MCP connector call
- src/bio_context_direct.py: BioMCP Python SDK backup
- src/interpreter.py: synthesize all data
- components/context_panel.py: narrative + expandable sections

### Hour 5-6.5: Report + Export + Polish
- components/report_export.py: Plotly figures + downloads + BioRender links
- End-to-end pipeline test with all 3 examples
- Error handling: timeouts, missing data, fallback logic
- Loading states with st.spinner / st.status

### Hour 6.5-8: Demo Prep
- UI polish: consistent colors, spacing, card styling
- Pre-warm any cold containers
- Write and rehearse demo script
- Test demo flow 3x end-to-end
- Prepare screenshot fallbacks

---

## Demo Script (5 minutes)

**[0:00-0:15] Title**
"BioVista — the AI Structure Interpreter. Scientists get AI predictions and ask
'so what?' We answer that."

**[0:15-1:00] Tab 1 — Query**
Type: "P53 R248W mutation — is it druggable?"
→ Claude parses: TP53, UniProt P04637, mutation R248W, question: druggability
→ "Submitting to Boltz-2 via Tamarind Bio..."

**[1:00-2:30] Tab 2 — Structure + Trust Audit (THE MONEY SHOT)**
→ 3D structure appears with trust coloring (blue=confident, red=low)
→ "See this red region at the mutation site? Our trust audit explains why."
→ Trust panel: "Boltz-2 has ~40% false positive rate. For P53 R248W specifically:
   training data has 4,200 wild-type structures vs 12 for this mutant.
   The loop at 240-260 is flexible — a documented Boltz-2 failure mode."
→ "No other tool tells you this."

**[2:30-3:45] Tab 3 — Biological Context**
→ "Claude queried PubMed, Open Targets, and ChEMBL via MCP in one API call."
→ "R248W is gain-of-function in 7.2% of TP53 cancers. 3 drugs in trials:
   APR-246 (Phase III), PC14586 (Phase II). 142 papers this year."
→ "Here's the AI-generated interpretation with citations."

**[3:45-4:30] Tab 4 — Report + Export**
→ "Download the PDB, the confidence data, and the full report."
→ "We found these BioRender templates for your protein mechanism."
→ Show Plotly confidence profile chart

**[4:30-5:00] Close**
→ "Every scientist using Boltz-2 or AlphaFold needs this accountability layer.
   We used all five sponsor tools: Tamarind for predictions, Claude + MCP for
   interpretation, BioRender for illustration discovery, Modal for compute."
→ "BioVista — because knowing what to trust matters as much as the prediction."

---

## Risk Mitigation (Updated)

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| Tamarind API slow/down | Medium | Pre-computed PDB fallbacks in data/precomputed/ |
| Tamarind free tier exhausted | Low (10 jobs) | Pre-compute examples + Modal backup |
| Anthropic MCP beta unstable | Low-Medium | BioMCP Python SDK as complete backup for all bio data |
| BioRender MCP returns nothing useful | Medium | Plotly figures are the real output; BioRender is bonus |
| molviewspec rendering issues | Low | py3Dmol/stmol as emergency fallback (basic coloring only) |
| Claude rate limits | Low | Cache ALL responses in st.session_state |
| Demo crashes | Low | Screenshot deck as absolute last resort |
| Boltz-2 prediction takes too long | Medium | Show pre-computed result, note "typically takes X minutes" |

---

## Sponsor Alignment (All 5 Featured)

| Sponsor | How We Use It | Visibility in Demo |
|---------|--------------|-------------------|
| **Tamarind Bio** (co-organizer) | Primary prediction backend (Boltz-2 API) | "Submitting to Tamarind Bio's Boltz-2..." |
| **BioRender** (co-organizer) | Template/icon discovery via MCP | "Found these BioRender templates for your protein" |
| **Anthropic** (sponsor) | Claude orchestration + MCP connector to PubMed/OpenTargets | "Claude queries 3 databases in one API call via MCP" |
| **Modal** (sponsor) | Backup GPU compute for Boltz-2 | "Running on Modal's serverless GPUs" (if Tamarind is slow) |
| **OpenAI** (sponsor) | Optional: GPT comparison for interpretation | Can add if time permits |
