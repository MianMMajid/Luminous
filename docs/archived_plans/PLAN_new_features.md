# New Feature Implementation Plan

**Goal:** Add 3 high-impact differentiators to Luminous before demo day (March 8, 2026). Each feature is scoped to ~2-3 hours of implementation and designed to wow judges while being technically grounded.

---

## Feature 1: "Sketch Your Hypothesis" Tab

**What:** A drawable canvas where researchers sketch rough pathway/mechanism diagrams, then Claude Vision converts them into clean, interactive figures. No other hackathon team has this.

**Why it wins:** Judges see a researcher literally drawing on a whiteboard → AI turns it into a publication figure. This is the "wow" moment.

### New Dependencies

```toml
# Add to pyproject.toml [project] dependencies
"streamlit-drawable-canvas>=0.9.3",
```

### New File: `components/sketch_hypothesis.py`

```
components/sketch_hypothesis.py (~200 lines)
├── render_sketch_hypothesis()          # Main tab entry point
│   ├── Two-column layout: left=canvas, right=output
│   ├── Canvas controls: drawing mode, stroke color/width, background
│   ├── "Interpret Sketch" button → Claude Vision
│   └── Output: structured diagram + Plotly figure + downloadable SVG
│
├── _render_canvas() → CanvasResult     # Drawing canvas setup
│   └── st_canvas(
│         fill_color="rgba(255,165,0,0.3)",
│         stroke_width=3,
│         stroke_color="#4A90D9",
│         background_color="#1a1a2e",
│         height=500,
│         width=700,
│         drawing_mode="freedraw",  # also "line", "rect", "circle", "transform"
│         key="sketch_canvas",
│       )
│       Returns: CanvasResult with .image_data (numpy RGBA) and .json_data (fabric.js objects)
│
├── _interpret_sketch(image_bytes, query, context) → dict
│   ├── Encode canvas as PNG: PIL Image.fromarray(image_data) → BytesIO → base64
│   ├── Send to Claude Vision:
│   │   client.messages.create(
│   │       model=CLAUDE_MODEL,
│   │       max_tokens=4096,
│   │       system=SKETCH_SYSTEM_PROMPT,
│   │       messages=[{
│   │           "role": "user",
│   │           "content": [
│   │               {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
│   │               {"type": "text", "text": f"Protein: {query.protein_name}. Interpret this sketch..."}
│   │           ]
│   │       }],
│   │   )
│   ├── Response format (structured JSON via system prompt):
│   │   {
│   │       "title": "Proposed mechanism ...",
│   │       "description": "The sketch shows ...",
│   │       "elements": [
│   │           {"label": "P53", "type": "protein", "role": "tumor suppressor"},
│   │           {"label": "MDM2", "type": "protein", "role": "E3 ubiquitin ligase"},
│   │           {"label": "→", "type": "interaction", "mechanism": "ubiquitination"}
│   │       ],
│   │       "mermaid": "graph TD\n  P53[P53 Tumor Suppressor] -->|ubiquitination| MDM2[MDM2 E3 Ligase]\n  ...",
│   │       "testable_prediction": "If X, then Y should be measurable by Z",
│   │       "confidence_note": "Based on the structure prediction confidence of ..."
│   │   }
│   └── Returns parsed dict
│
├── _render_structured_output(interpretation: dict, query)
│   ├── st.markdown(interpretation["description"])
│   ├── Mermaid diagram: st.markdown(f"```mermaid\n{interpretation['mermaid']}\n```")
│   │   NOTE: Streamlit renders mermaid natively in st.markdown since v1.33
│   ├── Plotly network graph as interactive figure:
│   │   - Nodes = elements with type-based colors (protein=blue, drug=green, pathway=orange)
│   │   - Edges = interactions with labeled mechanisms
│   │   - go.Figure with go.Scatter for nodes + go.Scatter for edges
│   ├── Testable prediction callout: st.success(interpretation["testable_prediction"])
│   └── Download buttons: SVG (from Plotly), Mermaid text, JSON data
│
└── _fallback_sketch_response() → dict  # No API key fallback
    └── Returns template interpretation with placeholder values
```

### System Prompt: `SKETCH_SYSTEM_PROMPT`

```
You are Lumi, a structural biology expert. A researcher has drawn a rough sketch
of a biological mechanism or hypothesis on a digital whiteboard.

Interpret the sketch in the context of the loaded protein ({protein_name}).
Identify:
1. Biological entities (proteins, drugs, metabolites, pathways)
2. Interactions (arrows, connections, inhibitions)
3. The scientific hypothesis being proposed

Return a JSON object with keys: title, description, elements (array),
mermaid (valid Mermaid graph syntax), testable_prediction, confidence_note.

Connect your interpretation to the trust audit data when relevant.
```

### Integration into `app.py`

```python
# Add after line 65 (tab definitions):
tab_query, tab_structure, tab_context, tab_report, tab_sketch, tab_chat = st.tabs([
    "Query",
    "Structure & Trust",
    "Biological Context",
    "Report & Export",
    "Sketch Hypothesis",   # NEW
    "Ask Lumi",
])

# Add new tab block:
with tab_sketch:
    from components.sketch_hypothesis import render_sketch_hypothesis
    render_sketch_hypothesis()
```

### Example UX Flow

1. User loads P53 R248W query → structure + trust audit + context populate
2. User clicks "Sketch Hypothesis" tab
3. Canvas appears with dark background, protein query context shown above
4. User draws: box labeled "P53" → arrow → box "MDM2" → X mark → box "Apoptosis"
5. User clicks "Interpret Sketch"
6. Claude Vision sees the drawing + knows it's P53 context
7. Returns structured interpretation with Mermaid diagram + Plotly network + testable prediction
8. User can download the clean figure for their presentation

### Time Estimate Breakdown

- Canvas setup + controls: 30 min
- Claude Vision integration: 45 min
- Mermaid + Plotly output rendering: 45 min
- Fallback + error handling: 15 min
- Polish + testing: 15 min

---

## Feature 2: Claude Agent SDK Bio Research Agent

**What:** Wrap all existing `src/` analysis modules as `@tool` functions and expose them through a single Claude agent that can autonomously chain analyses. Replaces the simple chat in Tab 6 with a real agent.

**Why it wins:** Judges see Claude autonomously deciding to run trust audit → fetch variants → check binding pocket → generate hypotheses, all in a single chat turn. This is the "agentic" demo that shows Anthropic integration depth.

### New Dependencies

```toml
# Add to pyproject.toml [project] dependencies
"claude-agent-sdk>=0.1",
```

### New File: `src/bio_agent.py`

```
src/bio_agent.py (~250 lines)
├── Imports: claude_agent_sdk (@tool, create_sdk_mcp_server, ClaudeSDKClient)
│
├── @tool(name="analyze_structure", description="...", input_schema={...})
│   def tool_analyze_structure(pdb_content: str, mutation_pos: int | None = None) → dict
│   └── Wraps: src.structure_analysis.analyze_structure()
│       Returns: {sasa_summary, sse_counts, mutation_analysis, hub_residues}
│       (Filters large arrays like contact_map, returns only summaries)
│
├── @tool(name="build_trust_audit", description="...", input_schema={...})
│   def tool_trust_audit(protein_name: str, plddt_scores: list[float], ...) → dict
│   └── Wraps: src.trust_auditor.build_trust_audit()
│       Returns: {overall_confidence, confidence_score, flagged_regions, limitations}
│
├── @tool(name="fetch_bio_context", description="...", input_schema={...})
│   def tool_fetch_bio_context(gene_name: str, uniprot_id: str | None = None) → dict
│   └── Wraps: src.bio_context_direct.fetch_bio_context_direct()
│       Returns: {diseases, drugs, pathways, literature_summary}
│
├── @tool(name="search_variants", description="...", input_schema={...})
│   def tool_search_variants(gene_name: str) → dict
│   └── Wraps: src.variant_analyzer.analyze_variants()
│       Returns: {pathogenic_count, pathogenic_positions, hotspots, summary}
│
├── @tool(name="generate_hypotheses", description="...", input_schema={...})
│   def tool_hypotheses(protein_name: str, trust_json: str, context_json: str) → str
│   └── Wraps: src.hypothesis_engine.generate_hypotheses()
│       Returns: markdown string of hypotheses
│
├── @tool(name="search_biorender", description="...", input_schema={...})
│   def tool_biorender_search(protein_name: str, topic: str) → list[dict]
│   └── Wraps: src.biorender_search.search_biorender_templates()
│       Returns: list of {name, type, description, url}
│
├── @tool(name="interpret_structure", description="...", input_schema={...})
│   def tool_interpret(protein_name: str, trust_json: str, context_json: str) → str
│   └── Wraps: src.interpreter.generate_interpretation()
│       Returns: markdown interpretation
│
├── ALL_TOOLS = [tool_analyze_structure, tool_trust_audit, tool_fetch_bio_context,
│                tool_search_variants, tool_hypotheses, tool_biorender_search, tool_interpret]
│
├── AGENT_SYSTEM_PROMPT = """You are Lumi, an autonomous structural biology research agent.
│   You have tools to analyze protein structures, audit prediction trust, fetch biological
│   context, search variant databases, generate hypotheses, and find BioRender illustrations.
│
│   When asked a question about a protein:
│   1. Use your tools to gather relevant data
│   2. Chain analyses logically (e.g., trust audit before interpretation)
│   3. Synthesize findings into a clear answer
│   4. Always cite prediction confidence and limitations
│   5. Suggest next experimental steps
│
│   You can call multiple tools in sequence to build a complete picture."""
│
├── def create_bio_agent() → ClaudeSDKClient
│   ├── mcp_server = create_sdk_mcp_server(
│   │       name="luminous-bio-tools",
│   │       version="0.1.0",
│   │       tools=ALL_TOOLS,
│   │   )
│   ├── options = ClaudeAgentOptions(
│   │       model=CLAUDE_MODEL,
│   │       system=AGENT_SYSTEM_PROMPT,
│   │       mcp_servers=[mcp_server],
│   │       max_tokens=4096,
│   │       allowed_tools=[t.name for t in ALL_TOOLS],
│   │   )
│   └── return ClaudeSDKClient(options)
│
└── def run_agent_query(question: str, session_context: dict) → AsyncIterator[str]
    ├── Injects current session state (loaded PDB, trust audit, etc.) into prompt
    ├── agent = create_bio_agent()
    ├── Streams response with tool-use visibility
    └── Yields: chunks of text + tool-call indicators for UI
```

### Modified File: `components/chat_followup.py`

Replace the current simple Anthropic API call with the agent:

```
components/chat_followup.py (modifications)
├── render_chat_followup()
│   ├── Add toggle: st.toggle("Agent Mode", value=True, key="agent_mode")
│   │   - Agent mode: uses bio_agent with tools (shows tool calls in expanders)
│   │   - Simple mode: current behavior (direct Claude chat)
│   ├── When agent_mode is ON:
│   │   - Show available tools as chips/badges above chat
│   │   - Display tool calls inline with st.expander("🔧 Called: analyze_structure")
│   │   - Stream agent responses with st.write_stream()
│   └── Tool call display format:
│       with st.expander(f"🔧 {tool_name}", expanded=False):
│           st.json(tool_input)
│           st.markdown(f"**Result:** {tool_output_summary}")
│
└── _generate_response() → modified to route through agent or direct API
```

### Fallback Strategy

If `claude-agent-sdk` is not installed or fails:
1. Fall back to current `_generate_response()` (direct Anthropic API with system prompt)
2. No degradation in basic chat functionality
3. Agent features simply don't appear

### Session State Integration

The agent needs access to already-loaded data to avoid redundant API calls:

```python
session_context = {
    "pdb_content": st.session_state.get("prediction_result", {}).pdb_content,
    "trust_audit": st.session_state.get("trust_audit"),
    "bio_context": st.session_state.get("bio_context"),
    "variant_data": st.session_state.get("variant_data"),
    "protein_name": query.protein_name,
    "mutation": query.mutation,
}
```

Tools check session context first before making external calls. If trust audit is already computed, `tool_trust_audit` returns cached results.

---

## Feature 3: ProDy Flexibility + P2Rank Pocket Prediction Overlays

**What:** Add per-residue flexibility (Normal Mode Analysis) and predicted binding pocket overlays to the 3D structure viewer. These complement the existing SASA, SSE, and contact analyses in `src/structure_analysis.py`.

**Why it wins:** Judges see the structure colored by dynamics (not just static pLDDT), with predicted drug binding pockets highlighted. This goes beyond what any AlphaFold viewer offers.

### New Dependencies

```toml
# Add to pyproject.toml [project] dependencies
"prody>=2.4",
```

P2Rank is a Java JAR — no Python package. We bundle it:

```bash
# Download P2Rank v2.4.2 (one-time setup, ~25MB)
mkdir -p tools/p2rank
curl -L https://github.com/rdk/p2rank/releases/download/2.4.2/p2rank-distro-2.4.2.tar.gz | \
    tar -xz -C tools/p2rank --strip-components=1
# Requires: Java 11+ on PATH
```

### New File: `src/flexibility_analysis.py`

```
src/flexibility_analysis.py (~120 lines)
├── compute_anm_flexibility(pdb_content: str, chain: str | None = None) → dict
│   ├── Parse PDB with ProDy:
│   │   import prody
│   │   from io import StringIO
│   │   struct = prody.parsePDBStream(StringIO(pdb_content))
│   │
│   ├── Select Cα atoms:
│   │   ca_atoms = struct.select("calpha")
│   │   if chain:
│   │       ca_atoms = struct.select(f"calpha and chain {chain}")
│   │
│   ├── Build ANM (Anisotropic Network Model):
│   │   anm = prody.ANM("protein")
│   │   anm.buildHessian(ca_atoms, cutoff=15.0)  # 15Å cutoff standard
│   │   anm.calcModes(n_modes=20)                # First 20 non-trivial modes
│   │
│   ├── Get per-residue flexibility (square fluctuations):
│   │   sq_flucts = prody.calcSqFlucts(anm[:10])  # First 10 modes
│   │   # Returns 1D numpy array, one value per Cα atom
│   │
│   ├── Normalize to 0-1 range:
│   │   flexibility = (sq_flucts - sq_flucts.min()) / (sq_flucts.max() - sq_flucts.min())
│   │
│   ├── Get residue IDs:
│   │   res_ids = ca_atoms.getResnums().tolist()
│   │
│   └── Return:
│       {
│           "residue_ids": res_ids,
│           "flexibility": flexibility.tolist(),      # 0=rigid, 1=most flexible
│           "sq_fluctuations": sq_flucts.tolist(),     # Raw values
│           "rigid_residues": [r for r, f in zip(res_ids, flexibility) if f < 0.2],
│           "flexible_residues": [r for r, f in zip(res_ids, flexibility) if f > 0.7],
│           "n_modes": 20,
│           "hinge_residues": _detect_hinges(anm, ca_atoms),  # Residues at mode boundaries
│       }
│
├── _detect_hinges(anm, atoms) → list[int]
│   ├── Mode shape sign changes indicate hinge points
│   ├── mode1 = anm[0].getEigvec()  # First non-trivial mode
│   ├── # Find residues where mode vector changes sign (hinge points)
│   └── Returns list of residue IDs at hinge positions
│
└── compare_flexibility_to_plddt(flexibility: dict, plddt_scores: dict) → dict
    ├── Correlation between ANM flexibility and pLDDT
    ├── High flexibility + low pLDDT = likely disordered (expected)
    ├── High flexibility + high pLDDT = interesting dynamics (flagged)
    ├── Low flexibility + low pLDDT = possible prediction error (flagged)
    └── Returns: {correlation, interesting_residues, flags}
```

### New File: `src/pocket_prediction.py`

```
src/pocket_prediction.py (~100 lines)
├── predict_pockets(pdb_content: str) → dict
│   ├── Write PDB to temp file:
│   │   with tempfile.NamedTemporaryFile(suffix=".pdb") as f:
│   │       f.write(pdb_content.encode())
│   │       f.flush()
│   │
│   ├── Run P2Rank:
│   │   p2rank_path = Path(__file__).parent.parent / "tools" / "p2rank" / "prank"
│   │   cmd = [str(p2rank_path), "predict", "-f", f.name, "-o", tmpdir]
│   │   subprocess.run(cmd, capture_output=True, timeout=60)
│   │
│   ├── Parse predictions CSV:
│   │   predictions_file = tmpdir / "*_predictions.csv"
│   │   # Columns: name, rank, score, probability, center_x/y/z, residue_ids
│   │   df = pd.read_csv(predictions_file)
│   │
│   ├── Parse residue-level CSV:
│   │   residues_file = tmpdir / "*_residues.csv"
│   │   # Columns: chain, residue_label, residue_name, score, pocket
│   │   res_df = pd.read_csv(residues_file)
│   │
│   └── Return:
│       {
│           "pockets": [
│               {
│                   "rank": 1,
│                   "score": 12.5,
│                   "probability": 0.89,
│                   "center": [x, y, z],
│                   "residues": [45, 47, 48, 89, 91, ...],
│               },
│               ...
│           ],
│           "residue_pocket_scores": {45: 0.92, 47: 0.88, ...},
│           "top_pocket_residues": [45, 47, 48, 89, 91],  # Pocket 1 residues
│       }
│
├── is_p2rank_available() → bool
│   └── Check: p2rank binary exists AND java is on PATH
│
└── _fallback_pocket_heuristic(sasa_data: dict, contacts_data: dict) → dict
    ├── Without P2Rank: use SASA + contact density as pocket proxy
    ├── Pocket-like = partially buried (10 < SASA < 50) + high contacts
    └── Returns same format with lower confidence note
```

### Modified File: `components/structure_viewer.py`

Add new color mode options to the existing 3D viewer:

```
structure_viewer.py modifications:
├── Add to the color mode selector (existing radio/selectbox):
│   color_mode = st.radio("Color by:", [
│       "Trust (pLDDT)",          # existing
│       "Flexibility (ANM)",       # NEW
│       "Binding Pockets",         # NEW
│       "Secondary Structure",     # existing
│   ])
│
├── When "Flexibility (ANM)" selected:
│   ├── @st.cache_data
│   │   def _compute_flexibility(pdb_content, chain):
│   │       from src.flexibility_analysis import compute_anm_flexibility
│   │       return compute_anm_flexibility(pdb_content, chain)
│   ├── Build molviewspec color JSON:
│   │   - Blue (rigid, flexibility < 0.2)
│   │   - White (intermediate)
│   │   - Red (flexible, flexibility > 0.7)
│   │   - Same format as trust coloring: {"residue_id": N, "color": "#RRGGBB"}
│   ├── Show flexibility Plotly strip chart alongside viewer
│   ├── Highlight hinge residues with labels in Mol*
│   └── Show flexibility vs pLDDT correlation callout
│
├── When "Binding Pockets" selected:
│   ├── @st.cache_data
│   │   def _predict_pockets(pdb_content):
│   │       from src.pocket_prediction import predict_pockets
│   │       return predict_pockets(pdb_content)
│   ├── Color residues by pocket membership:
│   │   - Pocket 1: green (#00CC88)
│   │   - Pocket 2: orange (#FF8C00)
│   │   - Pocket 3: purple (#8B5CF6)
│   │   - Non-pocket: gray (#444444)
│   ├── Show pocket cards below viewer:
│   │   for pocket in pockets:
│   │       st.metric(f"Pocket {pocket['rank']}", f"Score: {pocket['score']:.1f}")
│   │       st.caption(f"Residues: {', '.join(map(str, pocket['residues'][:10]))}")
│   └── If mutation is in a pocket → st.warning("Mutation is in predicted binding pocket!")
│
└── New sub-component: _render_dynamics_panel(flexibility_data, plddt_data)
    ├── Plotly dual-axis chart: flexibility (red line) vs pLDDT (blue line) per residue
    ├── Highlight discordant regions (high pLDDT + high flexibility = interesting dynamics)
    ├── Summary metrics:
    │   - % rigid core
    │   - % flexible loops
    │   - Number of hinge points
    └── Connect to trust audit: "N residues flagged by trust audit are also predicted flexible"
```

### Modified File: `src/structure_analysis.py`

Add flexibility and pocket data to the main analysis pipeline:

```python
# At end of analyze_structure(), after network centrality section:

# ── 11. ANM Flexibility (optional) ──
try:
    from src.flexibility_analysis import compute_anm_flexibility
    flex_data = compute_anm_flexibility(pdb_content, first_chain)
    result["flexibility"] = flex_data["flexibility"]
    result["flexible_residues_anm"] = flex_data["flexible_residues"]
    result["rigid_residues_anm"] = flex_data["rigid_residues"]
    result["hinge_residues"] = flex_data["hinge_residues"]
except ImportError:
    pass

# ── 12. Pocket Prediction (optional) ──
try:
    from src.pocket_prediction import predict_pockets, is_p2rank_available
    if is_p2rank_available():
        pocket_data = predict_pockets(pdb_content)
        result["predicted_pockets"] = pocket_data["pockets"]
        result["pocket_residue_scores"] = pocket_data["residue_pocket_scores"]
except (ImportError, Exception):
    pass
```

### Fallback Chain

1. **ProDy installed + PDB loaded** → full ANM flexibility analysis
2. **ProDy not installed** → skip flexibility, no error
3. **P2Rank installed + Java available** → pocket prediction
4. **P2Rank missing** → use SASA + contact heuristic for approximate pockets
5. **Both missing** → existing pLDDT/SSE coloring only (current behavior)

---

## Integration: System Prompt Enhancement for Interpreter + Agent

Both `src/interpreter.py` and `src/hypothesis_engine.py` should receive the new structural data when available:

```python
# Add to _build_prompt() in both files, after existing sections:

if structure_analysis:
    if structure_analysis.get("flexible_residues_anm"):
        parts.append(f"\n## Predicted Dynamics (ANM)")
        parts.append(f"Flexible residues: {structure_analysis['flexible_residues_anm'][:10]}")
        parts.append(f"Hinge residues: {structure_analysis.get('hinge_residues', [])}")

    if structure_analysis.get("predicted_pockets"):
        parts.append(f"\n## Predicted Binding Pockets (P2Rank)")
        for p in structure_analysis["predicted_pockets"][:3]:
            parts.append(f"  Pocket {p['rank']}: score {p['score']:.1f}, "
                        f"residues {p['residues'][:5]}")
```

---

## Implementation Order (Priority Sequence)

### Phase 1: ProDy + P2Rank (do first — adds immediate visual impact)
1. `pip install prody` / add to pyproject.toml
2. Create `src/flexibility_analysis.py`
3. Create `src/pocket_prediction.py` (with SASA fallback)
4. Add color modes to `components/structure_viewer.py`
5. Optionally download P2Rank JAR
6. Test with precomputed P53 PDB

### Phase 2: Sketch Your Hypothesis (do second — the "wow" feature)
1. `pip install streamlit-drawable-canvas` / add to pyproject.toml
2. Create `components/sketch_hypothesis.py`
3. Add 6th tab to `app.py`
4. Test with P53 pathway sketch
5. Polish output formatting

### Phase 3: Claude Agent SDK (do last — enhances existing chat)
1. `pip install claude-agent-sdk` / add to pyproject.toml
2. Create `src/bio_agent.py` with @tool wrappers
3. Modify `components/chat_followup.py` to support agent mode
4. Test agent chaining (question → multiple tool calls → synthesis)
5. Add tool-call visibility UI

---

## Demo Script (for judges)

1. **Query Tab**: "What is the impact of R248W mutation on P53 tumor suppressor?"
2. **Structure Tab**: Show trust-colored structure → switch to **Flexibility** view → point out R248W is at a hinge point → switch to **Binding Pockets** → show R248W is near pocket 2
3. **Context Tab**: Show auto-gathered PubMed + disease data
4. **Sketch Tab**: Draw rough P53 → MDM2 → Ubiquitin pathway → click "Interpret" → get clean Mermaid diagram with testable prediction
5. **Ask Lumi Tab**: Toggle "Agent Mode" → ask "Should I trust this prediction for drug design?" → watch agent call trust_audit + pocket_prediction + variant_search autonomously → synthesized answer
6. **Report Tab**: Download PDF with all analyses

Each feature demonstrates a different sponsor: Anthropic (Claude Vision, Agent SDK), structural innovation (ProDy/P2Rank), and the "so what?" gap closure.
