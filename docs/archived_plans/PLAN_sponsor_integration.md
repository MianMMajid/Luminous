# Sponsor Integration Enhancement Plan

**Goal:** Make Tamarind Bio, BioRender, and Modal integrations genuinely functional and demo-visible — not just branding — so judges see real sponsor tool usage.

**Current state:** Tamarind is well-integrated but only via precomputed data. BioRender is scaffolded with curated fallbacks. Modal is not installed and not used for compute. This plan fixes all three.

---

## Phase 1: Modal Boltz-2 GPU Compute (HIGHEST PRIORITY)

**Why:** Modal is the weakest integration. The sidebar says "Modal — Serverless GPU compute" but Modal isn't even installed. Judges will notice. Modal also sponsors $20k in credits.

### 1A. Create `src/modal_predict.py` — Modal Boltz-2 inference function

**New file.** This is a Modal app that runs Boltz-2 on H100 GPUs.

```
src/modal_predict.py
├── modal.App("biovista-boltz")
├── image: debian_slim + uv_pip_install("boltz==2.1.1")
├── volume: "boltz-models" for model weights (avoids re-download)
├── download_model() — downloads boltz-community/boltz-2 from HuggingFace
├── boltz_predict(sequence, job_name, predict_affinity) → dict
│   ├── Writes YAML input file (version: 1, sequences: [{protein: {id: A, sequence: ...}}])
│   ├── If predict_affinity: adds properties: [{affinity: {binder: ...}}]
│   ├── Runs: boltz predict input.yaml --use_msa_server --cache /models/boltz --output_format pdb
│   ├── Reads output: PDB file, confidence JSON, affinity JSON
│   └── Returns: {pdb: str, confidence: dict, affinity: dict|None}
└── local_entrypoint() for CLI testing
```

**Key specs:**
- GPU: `"H100"` (Boltz-2 needs ~48GB VRAM)
- Timeout: `10 * 60` (10 minutes — Boltz-2 typically finishes in ~2 min on H100)
- Volume: `modal.Volume.from_name("boltz-models", create_if_missing=True)` mounted at `/models/boltz`
- Image: `modal.Image.debian_slim(python_version="3.12").uv_pip_install("boltz==2.1.1")`
- Output format: PDB (not default CIF) to match our existing pipeline

**YAML input format for Boltz-2:**
```yaml
version: 1
sequences:
  - protein:
      id: A
      sequence: MVHLTPEEKS...
properties:
  - affinity:
      binder: A
```

**Output parsing:** Boltz writes to `boltz_results_input/predictions/input/`:
- `input_model_0.pdb` — structure
- `confidence_input_model_0.json` — {confidence_score, ptm, iptm, complex_plddt}
- `affinity_input.json` — {affinity_probability_binary, affinity_pred_value (log10 IC50 in µM)}

### 1B. Create `src/modal_client.py` — client wrapper for calling Modal from Streamlit

**New file.** Thin wrapper that calls the deployed Modal function from our Streamlit app.

```
src/modal_client.py
├── run_modal_prediction(sequence, job_name, predict_affinity) → tuple[str, dict, dict|None]
│   ├── Uses modal.Function.from_name("biovista-boltz", "boltz_predict")
│   ├── Calls fn.remote(sequence, job_name, predict_affinity)
│   ├── Returns (pdb_content, confidence_json, affinity_json)
│   └── Raises RuntimeError on failure
└── is_modal_available() → bool
    └── Checks if modal is installed and credentials exist
```

### 1C. Wire Modal into `components/structure_viewer.py` fallback chain

**Edit existing file.** Update `_run_prediction()` to add Modal as a compute option:

Current fallback chain:
```
precomputed → Tamarind API → RCSB PDB
```

New fallback chain:
```
precomputed → Tamarind API → Modal Boltz-2 → RCSB PDB
```

Add Modal as the second-priority compute backend after Tamarind. When Tamarind fails or has no API key, try Modal before falling back to RCSB.

Also: add a radio button or selectbox in the Query tab letting users choose compute backend:
- "Auto (fastest available)" — default
- "Tamarind Bio Cloud" — Tamarind API
- "Modal GPU (H100)" — Modal Boltz-2
- "RCSB PDB (experimental)" — fallback

This makes the compute choice **visible** to judges.

### 1D. Update `deploy_modal.py` — add GPU function alongside web server

**Edit existing file.** Current file only deploys Streamlit web server. Add the Boltz-2 prediction function to the same Modal app so both deploy together.

### 1E. Add `modal` to `pyproject.toml`

**Edit existing file.** Add `"modal>=0.73"` to dependencies.

### 1F. Update sidebar sponsor description

**Edit `app.py`.** Change Modal description from generic "Serverless GPU compute" to:
```
"Modal — Boltz-2 on H100 GPUs (serverless)"
```

### 1G. Add compute provenance badge to structure viewer

**Edit `components/structure_viewer.py`.** After loading a prediction, show a small badge:
```
"Computed via: [Tamarind Bio API | Modal H100 | RCSB PDB | Precomputed Demo]"
```

This makes it crystal clear which sponsor tool produced the result.

---

## Phase 2: Tamarind Bio API Enhancement

**Why:** Tamarind is a co-organizer. Integration is solid but all demo data is precomputed. We need to show the API is real.

### 2A. Add `GET /tools` discovery to sidebar

**Edit `app.py` or create `src/tamarind_tools.py`.** On app startup (or on-demand), call `GET /tools` and display Tamarind's available tools in the sidebar:

```
### Tamarind Bio Tools
✅ Boltz-2 (Structure + Affinity)
✅ Chai-1 (Structure Prediction)
✅ ProteinMPNN (Sequence Design)
✅ RFdiffusion (Binder Design)
✅ BoltzGen (Peptide Design)
... and 15+ more
```

Cache with `@st.cache_data(ttl=300)`. If API key missing, show "Configure Tamarind API key to unlock 20+ tools."

This proves to judges we're connected to the real Tamarind platform.

### 2B. Add "Design a Binder" CTA powered by Tamarind

**Edit `components/hypothesis_panel.py` or `components/drug_resistance.py`.** After showing drug resistance or structural insights, add a call-to-action:

```
"Ready to design a resistance-evasive binder?"
→ [Design with BoltzGen on Tamarind] button
```

When clicked, pre-fills a Tamarind API call with:
- Target: current protein structure
- Hotspot residues: from the structural analysis
- Tool: BoltzGen or RFdiffusion

This demonstrates the **pipeline** from analysis → action, using Tamarind's design tools.

### 2C. Expose advanced Boltz-2 parameters

**Edit `components/query_input.py`.** Add an "Advanced Settings" expander with:
- Recycling steps slider (1-10, default 3)
- MSA toggle (on/off)
- Predict affinity checkbox
- Cyclic peptide flag

These map directly to Tamarind's Boltz-2 API parameters. Shows judges we understand the tool deeply.

### 2D. Add stability scoring via ThermoMPNN

**New feature (optional, medium effort).** For mutation queries, call Tamarind's ThermoMPNN endpoint to get ΔΔG stability prediction. Display alongside the structural analysis.

This adds a second Tamarind tool beyond Boltz-2, showing breadth of integration.

API call:
```python
payload = {
    "jobName": f"biovista_thermo_{query.protein_name}_{query.mutation}",
    "type": "thermompnn",
    "settings": {
        "pdbFile": pdb_content,  # or upload first
        "mutations": [query.mutation],
    },
}
```

### 2E. Update Tamarind test in `scripts/test_apis.py`

**Edit existing file.** Enhance test to also verify:
- `GET /tools` returns tool list
- Boltz is in the available tools
- API key has sufficient permissions

---

## Phase 3: BioRender MCP Enhancement

**Why:** BioRender is a co-organizer. Current integration requires manual button click and often falls back to curated (hardcoded) suggestions. Needs to be more visible and automatic.

### 3A. Pre-cache BioRender results for demo examples

**Add to `data/precomputed/` directories.** For each demo example (p53_r248w, brca1_c61g, egfr_t790m), add a `biorender.json` with pre-fetched template/icon results.

Generate by running the MCP search once per example and saving the output:
```json
[
  {"name": "Protein Mutation Impact", "type": "template", "description": "...", "url": "..."},
  {"name": "Drug-Target Binding", "type": "template", "description": "...", "url": "..."},
  {"name": "Tumor Suppressor Icon", "type": "icon", "description": "...", "url": null}
]
```

**Edit `components/report_export.py`** to load precomputed BioRender results alongside other precomputed data, making them appear instantly during demo.

### 3B. Auto-fetch BioRender results on tab load

**Edit `components/report_export.py`.** Instead of requiring the user to click "Search BioRender Templates", auto-fetch when Tab 4 opens:

```python
cache_key = f"biorender_results_{query.protein_name}"
if st.session_state.get(cache_key) is None:
    # Try precomputed first
    precomputed = _load_precomputed_biorender(query)
    if precomputed:
        st.session_state[cache_key] = precomputed
    else:
        # Auto-fetch via MCP (or fall back to curated)
        from src.biorender_search import search_biorender_templates
        st.session_state[cache_key] = search_biorender_templates(query)
```

### 3C. Fix bio_context.py system prompt

**Edit `src/bio_context.py`.** The system prompt (`CONTEXT_SYSTEM`) tells Claude to gather from "PubMed, Open Targets, and BioRender" but the actual prompt text only asks for disease associations, drugs, literature, and pathways — nothing BioRender-specific.

Add to the system prompt:
```
6. Relevant BioRender templates or scientific illustrations for this protein
```

And add a field to the response schema:
```
"biorender_suggestions": ["template or icon names"]
```

### 3D. Add BioRender visual cards with icons

**Edit `components/report_export.py`.** Instead of plain text list, render BioRender results as styled cards matching the app's dark theme:

```python
for tmpl in templates:
    st.markdown(
        f'<div class="glow-card" style="padding:10px 14px;margin-bottom:8px">'
        f'<span style="font-weight:600;color:#4A90D9">{tmpl["name"]}</span>'
        f'<span style="float:right;font-size:0.8em;color:#00CC88">{tmpl["type"].upper()}</span>'
        f'<br><span style="font-size:0.85em;color:#8890a4">{tmpl["description"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )
```

### 3E. Add BioRender test to `scripts/test_apis.py`

**Edit existing file.** Add test #11:

```python
def test_biorender_mcp():
    """Test BioRender MCP search."""
    print("11. Testing BioRender MCP...")
    if not BIORENDER_TOKEN:
        print("   SKIP (no BIORENDER_TOKEN)")
        return
    from src.biorender_search import search_biorender_templates
    from src.models import ProteinQuery
    q = ProteinQuery(protein_name="TP53", mutation="R248W", question_type="mutation_impact")
    results = search_biorender_templates(q)
    print(f"   Found {len(results)} templates/icons")
    print("   PASS")
```

### 3F. Add BioRender section to PDF report

**Edit `src/pdf_report.py`.** Add a "Publication Figures via BioRender" section that lists the discovered templates. This makes BioRender visible even in the downloadable report.

---

## Phase 4: Cross-Sponsor Visibility (Polish)

### 4A. Add compute provenance tracking

**Edit `src/models.py`.** Add a `compute_source` field to `PredictionResult`:

```python
class PredictionResult(BaseModel):
    ...
    compute_source: str = "precomputed"  # "tamarind", "modal", "rcsb", "precomputed"
```

This flows through the entire pipeline so every component knows which sponsor produced the data.

### 4B. Add "Powered By" data provenance footer to each major panel

**Edit key components.** At the bottom of major analysis panels, add a subtle provenance line:

- Structure viewer: `"Structure: Boltz-2 via [Tamarind Bio | Modal H100] | Visualization: MolViewSpec/Mol*"`
- Context panel: `"Data: PubMed + Open Targets via Anthropic MCP | BioMCP (ChEMBL, ClinVar)"`
- Report tab: `"Figures: Plotly | Templates: BioRender MCP | AI: Claude Opus"`

### 4C. Add sponsor attribution to AI interpretation

**Edit `src/interpreter.py`.** Append a "Data Sources" section to the interpretation:

```python
sources = [
    "Structure predicted by Boltz-2 (Tamarind Bio)",
    "Confidence audit using pLDDT, pTM, ipTM metrics",
    "Literature from PubMed via Anthropic MCP connector",
    "Disease associations from Open Targets via MCP",
]
if bio_context.drugs:
    sources.append("Drug data from ChEMBL via BioMCP")
```

### 4D. Update "Powered By" sidebar with live status

**Edit `app.py`.** Change the static sponsor list to show live connection status:

```python
sponsors = [
    ("Tamarind Bio", _check_tamarind(), "Boltz-2 structure + affinity prediction"),
    ("Modal", _check_modal(), "Boltz-2 on H100 GPUs (serverless)"),
    ("Anthropic Claude", _check_anthropic(), "AI interpretation + MCP connector"),
    ("BioRender", _check_biorender(), "Scientific illustration via MCP"),
    ("BioMCP", True, "15+ bio databases (PubMed, ChEMBL, ClinVar)"),
    ("MolViewSpec", True, "Mol* 3D visualization engine"),
]
for name, connected, desc in sponsors:
    icon = "🟢" if connected else "⚪"
    # render with icon
```

---

## Implementation Order & Effort Estimates

| Step | Priority | Files Changed/Created | Complexity |
|------|----------|----------------------|------------|
| **1A** Modal predict function | P0 | NEW `src/modal_predict.py` | Medium — follow Modal's official example |
| **1B** Modal client wrapper | P0 | NEW `src/modal_client.py` | Low — thin wrapper |
| **1C** Wire Modal into fallback | P0 | EDIT `components/structure_viewer.py` | Medium — add to fallback chain + UI selector |
| **1E** Add modal dependency | P0 | EDIT `pyproject.toml` | Trivial |
| **2A** Tamarind tools discovery | P1 | EDIT `app.py` or NEW `src/tamarind_tools.py` | Low |
| **3A** Pre-cache BioRender | P1 | ADD `data/precomputed/*/biorender.json` | Low |
| **3B** Auto-fetch BioRender | P1 | EDIT `components/report_export.py` | Low |
| **4A** Compute provenance | P1 | EDIT `src/models.py`, viewers | Low |
| **1F** Update sidebar text | P2 | EDIT `app.py` | Trivial |
| **1G** Compute badge | P2 | EDIT `components/structure_viewer.py` | Low |
| **2B** Design binder CTA | P2 | EDIT `components/hypothesis_panel.py` | Low-Medium |
| **2C** Advanced Boltz params | P2 | EDIT `components/query_input.py` | Low |
| **3C** Fix MCP prompt | P2 | EDIT `src/bio_context.py` | Trivial |
| **3D** BioRender visual cards | P2 | EDIT `components/report_export.py` | Low |
| **4B** Provenance footers | P2 | EDIT multiple components | Low |
| **4C** Attribution in interp | P2 | EDIT `src/interpreter.py` | Trivial |
| **4D** Live status sidebar | P2 | EDIT `app.py` | Low |
| **1D** Update deploy_modal | P3 | EDIT `deploy_modal.py` | Low |
| **2D** ThermoMPNN scoring | P3 | NEW feature | Medium |
| **2E** Enhanced Tamarind test | P3 | EDIT `scripts/test_apis.py` | Low |
| **3E** BioRender test | P3 | EDIT `scripts/test_apis.py` | Low |
| **3F** BioRender in PDF | P3 | EDIT `src/pdf_report.py` | Medium (file is 2137 lines) |

---

## Demo Script Impact

After these changes, the demo flow becomes:

1. **Query tab**: User picks "EGFR T790M" example
2. **Structure tab**: Loads precomputed → badge shows `"Computed via: Tamarind Bio Boltz-2"`
3. **Structure tab**: User submits custom sequence → selector shows `"Computing on Modal H100..."` → real GPU inference → badge shows `"Computed via: Modal H100 GPU"`
4. **Context tab**: Bio context auto-fetches → sources show `"PubMed via Anthropic MCP, Open Targets via MCP, ChEMBL via BioMCP"`
5. **Report tab**: BioRender templates auto-load → visual cards show relevant icons/templates
6. **Report tab**: PDF includes all sponsor attributions
7. **Sidebar**: Live green dots next to each connected sponsor tool
8. **Sidebar**: Tamarind tools list shows 20+ available tools

**Judge sees:** All 5 sponsors (Tamarind, Anthropic, BioRender, Modal, + BioMCP/MolViewSpec) actively contributing real functionality — not just logos.

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| Modal cold start during demo (10-20s) | Use precomputed for demo examples; Modal only for live custom queries |
| Modal credentials not configured | `is_modal_available()` check → skip gracefully |
| Tamarind API rate limits | Precomputed fallback for demo examples always works |
| BioRender MCP returns empty | Pre-cached results + curated fallback |
| Boltz-2 model download on Modal takes too long | Pre-download via `download_model.remote()` before demo |
| `boltz` package version mismatch | Pin to `boltz==2.1.1` in Modal image |
| Modal H100 not available | Fall back to A100-80GB: `gpu="A100-80GB"` |

---

## Files Summary

**New files (3):**
- `src/modal_predict.py` — Modal Boltz-2 inference app
- `src/modal_client.py` — client wrapper for calling Modal from Streamlit
- `data/precomputed/*/biorender.json` — pre-cached BioRender results (3 files)

**Edited files (10-12):**
- `pyproject.toml` — add modal dependency
- `app.py` — sidebar enhancements
- `src/models.py` — add compute_source field
- `src/bio_context.py` — fix BioRender prompt
- `src/interpreter.py` — add data source attribution
- `components/structure_viewer.py` — Modal fallback + compute badge
- `components/query_input.py` — advanced settings expander
- `components/report_export.py` — auto-fetch BioRender + visual cards
- `components/hypothesis_panel.py` — Tamarind design CTA
- `deploy_modal.py` — add GPU function
- `scripts/test_apis.py` — BioRender test + enhanced Tamarind test
