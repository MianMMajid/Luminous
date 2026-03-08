# Protein Structure Video & Animation Research (2024-2026)

Comprehensive survey of tools for generating protein structure videos and animations programmatically, with assessment of Streamlit integration feasibility.

---

## 1. AI Protein Dynamics Prediction

### Production-Ready / Code Available

| Tool | Approach | GitHub | Output | GPU Required | Streamlit Feasibility |
|------|----------|--------|--------|--------------|----------------------|
| **AlphaFlow** | Flow matching on AlphaFold | [bjing2016/alphaflow](https://github.com/bjing2016/alphaflow) | Multi-model PDB ensemble | Yes (A100) | Hard — requires OpenFold, heavy deps |
| **Str2Str** | Score-based diffusion, zero-shot | [arxiv 2306.03117](https://arxiv.org/abs/2306.03117) | PDB conformers | Yes | Hard — research code |
| **DynamicBind** | Equivariant diffusion for protein-ligand | [luwei0917/DynamicBind](https://github.com/luwei0917/DynamicBind) | PDB with ligand-induced conformational changes | Yes | Hard — heavy model |
| **ConfDiff** | Force-guided SE(3) diffusion (ByteDance, ICML'24) | [bytedance/ConfDiff](https://github.com/bytedance/ConfDiff) | PDB ensemble | Yes | Hard — research code |
| **P2DFlow** | SE(3) flow matching on ESMFold (2025) | [BLEACH366/P2DFlow](https://github.com/BLEACH366/P2DFlow) | PDB ensemble | Yes | Hard — research code |
| **EigenFold** | Harmonic diffusion | [bjing2016/EigenFold](https://github.com/bjing2016/EigenFold) | PDB conformers | Yes | Hard — research code |
| **GENIE 2** | Diffusion for protein design (diversity) | [aqlaboratory/genie2](https://github.com/aqlaboratory/genie2) | PDB structures | Yes | Hard — design-focused, not dynamics |
| **ClustENM/ClustENMD** | NMA + MD hybrid (in ProDy) | [prody/ProDy](https://github.com/prody/ProDy) | PDB ensemble | CPU OK (OpenMM for MD steps) | **MEDIUM** — `pip install prody`, well-documented API |
| **Boltz-2 + Boltz-sample** | Pair representation scaling for ensemble | via Tamarind Bio API | Multi-conformation PDB | Yes (cloud) | **EASY via Tamarind** — already integrated |

### Key Insight: Boltz-sample (Jan 2026)
A new method that modulates Boltz-2's latent pair representation to steer conformational sampling. By rescaling the pair representation, it generates diverse conformational ensembles from a single sequence. Available through Tamarind Bio. This is the most practical path for your hackathon since you already have Tamarind integration.

### Mac-Diff (2026, Nature Machine Intelligence)
Conditional diffusion with locality-aware modal alignment. State of the art for generating conformational ensembles for unseen proteins. Recovered conformational distributions of fast-folding proteins and predicted allosteric protein alternative conformations. No public code found yet.

---

## 2. Programmatic Protein Animation (Python -> MP4/GIF)

### Tier 1: Best Options for Streamlit

| Tool | Headless? | Output | Install | Integration Difficulty |
|------|-----------|--------|---------|----------------------|
| **PyMOL open-source** | Yes (`-c` flag) | PNG frames -> ffmpeg -> MP4 | `conda install -c conda-forge pymol-open-source` | **MEDIUM** — well-documented scripting API |
| **Blender + Molecular Nodes** | Yes (v4.2+) | MP4/PNG/EXR (cinema quality) | `pip install molecularnodes` (experimental) + Blender | **HARD locally, EASY on Modal** |
| **MolViewSpec animations** | Browser-only | Interpolated scenes in Mol* | `pip install molviewspec` | **EASY** — already in your stack |
| **ProDy traverseMode** | Yes | Multi-model PDB (then render) | `pip install prody` | **EASY** — pure Python, no GPU |

### Tier 2: Viable but More Complex

| Tool | Headless? | Output | Notes |
|------|-----------|--------|-------|
| **ChimeraX** | Yes (offscreen, `movie record`) | PNG frames -> MP4 | Supersample support, offscreen rendering, but heavy install |
| **VMD + Tachyon** | Yes (`-dispdev text`) | PPM frames -> MP4 | TachyonInternal for fast renders; VMDviz Python wrapper exists |
| **nglview MovieMaker** | Needs Jupyter kernel | GIF or MP4 (via moviepy) | `view.render_image()` per frame; unstable API for headless |
| **py3Dmol** | No (browser widget) | PNG per frame (manual) | No built-in animation export; would need Puppeteer |

### Detailed: PyMOL Headless Animation Pipeline

```python
# PyMOL headless movie generation
import pymol
from pymol import cmd

pymol.finish_launching(['pymol', '-c', '-q'])  # -c = command-line only, -q = quiet

cmd.load("protein.pdb")
cmd.show("cartoon")
cmd.color("cyan")
cmd.set("ray_opaque_background", 0)

# Create rotation movie
cmd.mset("1 x360")  # 360 frames
cmd.util.mroll(1, 360, 1)  # rotate 1 degree per frame
cmd.set("ray_trace_frames", 1)
cmd.set("cache_frames", 0)  # avoid OOM on long movies
cmd.mpng("/tmp/frames/frame", width=1920, height=1080)

# Then use ffmpeg to stitch:
# ffmpeg -r 30 -i /tmp/frames/frame%04d.png -c:v libx264 -pix_fmt yuv420p output.mp4
```

### Detailed: MolViewSpec Animation (Already in Your Stack!)

```python
import molviewspec as mvs

# Create multi-scene animation
scenes = []
for angle in range(0, 360, 10):
    builder = mvs.create_builder()
    structure = builder.download(url="structure.pdb").parse(format="pdb").model_structure()
    structure.component().representation().color(color="cyan")
    builder.camera(position=[...], target=[...])  # rotate camera
    scenes.append(builder)

# MolViewSpec animations interpolate between scenes automatically
# transition_duration_ms and linger_duration_ms control timing
# Mol* viewer handles rendering client-side
```

**Important**: Mol* can export animations to MP4 directly in the browser. The Export Animation control panel lets you select animation type and time properties, then renders. This is purely client-side (browser WebGL).

---

## 3. Normal Mode Analysis (NMA) Animation

### ProDy (Best Option) -- `pip install prody`

```python
import prody

# Load structure
pdb = prody.parsePDB('1abc')
calphas = pdb.select('calpha')

# Compute ANM
anm = prody.ANM('protein')
anm.buildHessian(calphas)
anm.calcModes(n_modes=10)

# Generate trajectory along mode 1
ensemble = prody.traverseMode(anm[0], calphas, n_steps=20, rmsd=2.0)

# Write multi-model PDB for animation
prody.writePDB('nma_trajectory.pdb', ensemble)

# Write NMD file for VMD/NMWiz visualization
prody.writeNMD('modes.nmd', anm[:3], calphas)
```

**Output**: Multi-model PDB file that can be:
- Loaded into Mol*/MolViewSpec as trajectory (use model slider)
- Rendered with PyMOL as movie
- Visualized with nglview in Jupyter

**Key Functions**:
- `traverseMode()` — generates conformers along a mode with configurable RMSD and steps
- `writeNMD()` — NMD format for VMD NMWiz plugin
- `writePDB()` — multi-model PDB for trajectory visualization
- ANM (Anisotropic Network Model) and GNM (Gaussian Network Model) both supported

### iMODS Web Server
- URL: http://imods.chaconlab.org
- Free, no login required
- Internal coordinates NMA (preserves covalent geometry, 1/3 fewer DOF)
- Outputs: animations, morphing trajectories, covariance maps, mobility profiles
- **No REST API documented** — web interface only, not suitable for programmatic Streamlit integration
- Could potentially be scraped but fragile approach

### Bio3D (R)
- R package, callable from Python via rpy2
- Provides NMA, PCA, ensemble analysis
- Not recommended for Streamlit (R dependency adds complexity)

---

## 4. Folding Simulation Visualization

### OpenMM (Most Practical)

```python
from openmm.app import *
from openmm import *
from openmm.unit import *

# Quick coarse-grained or structure-based simulation
pdb = PDBFile('input.pdb')
forcefield = ForceField('amber14-all.xml', 'amber14/tip3pfb.xml')
system = forcefield.createSystem(pdb.topology, nonbondedMethod=PME)
integrator = LangevinMiddleIntegrator(300*kelvin, 1/picosecond, 0.004*picoseconds)
simulation = Simulation(pdb.topology, system, integrator)
simulation.context.setPositions(pdb.positions)

# Save trajectory
simulation.reporters.append(DCDReporter('trajectory.dcd', 1000))
simulation.reporters.append(PDBReporter('trajectory.pdb', 5000))  # multi-model PDB
simulation.step(50000)

# Trajectory formats: PDB, PDBx/mmCIF, DCD, XTC
```

**Output formats**: PDB (multi-model), DCD, XTC — all loadable by MDAnalysis, MDTraj, nglview
**Headless**: Yes, pure Python
**Install**: `conda install -c conda-forge openmm`
**Caveat**: Real folding simulations need microseconds (too slow for demo). Use structure-based models (SBMOpenMM) for fast folding visualization.

### SBMOpenMM (Fast Folding)
- Structure-based model library for protein folding simulations
- Much faster than all-atom MD for folding events
- GitHub: CompBiochBiophLab/sbm-openmm
- Good for demo: shows folding pathway in minutes, not days

### MDAnalysis + MDTraj for Trajectory Handling

```python
import MDAnalysis as mda

# Write multi-model PDB from trajectory
u = mda.Universe('topology.pdb', 'trajectory.dcd')
protein = u.select_atoms('protein')
with mda.Writer("trajectory_multimodel.pdb", multiframe=True) as pdb:
    for ts in u.trajectory:
        pdb.write(protein)
```

---

## 5. Structure Morphing (Interpolation Between Conformations)

### FATCAT (Web Server + Java)
- URL: https://fatcat.godziklab.org/
- Flexible structure alignment with twist detection at hinge points
- **Generates morphing movies**: linear interpolation between aligned models, then energy minimization of intermediates
- Java implementation available (jFATCAT-rigid, jFATCAT-flexible) in BioJava
- **No Python API** — web server only for morphing; Java for alignment
- RCSB provides alignment API: https://alignment.rcsb.org/

### MORPH-PRO (Web Server)
- Upload two PDB files (start/end conformations)
- Automatically determines number of intermediate conformations
- Visualize as movie or step-by-step
- **Web-only, no API**

### PyMOL Morph (Best Programmatic Option)

```python
import pymol
from pymol import cmd

pymol.finish_launching(['pymol', '-c', '-q'])
cmd.load("conf_open.pdb", "open")
cmd.load("conf_closed.pdb", "closed")

# RigiMOL morphing (included with PyMOL)
cmd.morph("morph_obj", "open", "closed", refinement=3)

# Export frames
cmd.mset("1 x60")  # 60 frames
cmd.mpng("/tmp/morph/frame", width=1920, height=1080)
```

### ChimeraX Morph Conformations

```
# ChimeraX command-line morphing
open conf1.pdb
open conf2.pdb
morph #1 #2 frames 50 method corkscrew
movie record
turn y 1 360
wait 360
movie encode output morph.mp4
```
- Offscreen rendering supported with `graphics` command
- Supersample up to 4x for smooth edges

### ProDy Interpolation (Pure Python, Simplest)

```python
import prody
import numpy as np

# Load two conformations
conf1 = prody.parsePDB('open.pdb')
conf2 = prody.parsePDB('closed.pdb')

# Align
prody.alignCoordsets(conf1, conf2)

# Linear interpolation
coords1 = conf1.getCoords()
coords2 = conf2.getCoords()
n_frames = 20
for i in range(n_frames):
    t = i / (n_frames - 1)
    interpolated = coords1 * (1 - t) + coords2 * t
    conf1.setCoords(interpolated)
    prody.writePDB(f'morph_{i:03d}.pdb', conf1)
```

---

## 6. Cloud Rendering Services

### Modal + Blender (BEST for Hackathon)

Modal has an **official documented example** for rendering Blender videos on GPU:
- URL: https://modal.com/docs/examples/blender_video
- GPUs render >10x faster than CPUs
- 4 seconds of 1080p 60 FPS in ~3 minutes on 10 L40S GPUs
- Per-frame latency: ~6 seconds on GPU, ~1 minute on CPU
- Uses `render.map()` to parallelize across frames

```python
import modal

app = modal.App("protein-video")
image = modal.Image.debian_slim().apt_install("blender").pip_install("molecularnodes")

@app.function(gpu="L40S", image=image)
def render_frame(frame_num: int, pdb_content: bytes) -> bytes:
    import bpy
    import molecularnodes as mn
    # Load PDB, style, render frame
    # Return PNG bytes
    ...

@app.local_entrypoint()
def main():
    frames = list(render_frame.map(range(360), [pdb_bytes] * 360))
    # Stitch with ffmpeg locally
```

### Modal + PyMOL (Simpler Alternative)

```python
import modal

app = modal.App("pymol-render")
image = (modal.Image.debian_slim()
    .apt_install("xvfb", "ffmpeg")
    .conda_install("pymol-open-source", channels=["conda-forge"])
)

@app.function(image=image, cpu=4)  # CPU is fine for PyMOL ray tracing
def render_protein_video(pdb_content: bytes) -> bytes:
    import pymol
    from pymol import cmd
    # ... render frames, stitch with ffmpeg, return MP4 bytes
```

### ChatMol MCP Server
- Connects PyMOL/ChimeraX to Claude AI via MCP
- Can execute commands and capture images
- **Not suitable for video** — designed for single image capture, not animation
- Released March 2025

### Puppeteer + Mol* (Hacky but Possible)
- Run Mol* in headless Chrome via Puppeteer
- Use puppeteer-video-recorder to capture animation
- npm package: `puppeteer-screen-recorder`
- Could run on Modal with headless Chrome container
- **Fragile approach** — timing issues, WebGL in headless Chrome can be unreliable

---

## Recommended Strategy for Streamlit Hackathon

### Fastest Path (< 2 hours to implement)

1. **NMA with ProDy** (`pip install prody`):
   - Compute ANM modes from PDB structure
   - Use `traverseMode()` to generate multi-model PDB trajectory
   - Display in MolViewSpec as trajectory with model slider
   - Pure Python, no GPU, no external tools

2. **Boltz-2 Ensemble via Tamarind**:
   - Submit multiple Boltz-2 predictions with different seeds
   - Or use Boltz-sample approach if Tamarind supports it
   - Concatenate results into multi-model PDB
   - Display ensemble in MolViewSpec

3. **MolViewSpec Scene Animation**:
   - Create multiple MolViewSpec scenes with different views/colors
   - Use built-in interpolation (`transition_duration_ms`)
   - No video generation needed — Mol* handles animation client-side

### Medium Path (4-6 hours)

4. **PyMOL on Modal** for cinema-quality rendering:
   - Run PyMOL headless on Modal container
   - Render rotation + NMA animation frames
   - Stitch with ffmpeg into MP4
   - Return via Modal function, display with `st.video()`

### Premium Path (8+ hours)

5. **Blender + Molecular Nodes on Modal**:
   - Cinema-quality rendering with proper lighting, materials
   - GPU-accelerated (Cycles renderer)
   - Official Modal example exists for Blender
   - Could produce stunning demo videos

---

## Summary Table: All Tools Assessed

| Tool | Python API | Headless | Output | Install Difficulty | Streamlit Integration |
|------|-----------|----------|--------|-------------------|----------------------|
| ProDy (ANM/NMA) | Native | Yes | Multi-model PDB | Easy (pip) | **EASY** |
| MolViewSpec | Native | Browser | Scene interpolation | Easy (pip) | **EASY** (already using) |
| Boltz-2 ensemble | Via Tamarind | Cloud | PDB files | None (API) | **EASY** (already using) |
| PyMOL open-source | Native | Yes (-c) | PNG frames | Medium (conda) | **MEDIUM** |
| Blender+MolNodes | Experimental | Yes (4.2+) | MP4/frames | Hard | **HARD locally, MEDIUM on Modal** |
| ChimeraX | CLI | Yes (offscreen) | PNG frames | Medium | **MEDIUM** |
| VMD | Tcl/Python | Yes | PPM frames | Medium | **MEDIUM** |
| nglview MovieMaker | Native | Partial | GIF/MP4 | Easy (pip) | **HARD** (needs Jupyter kernel) |
| OpenMM | Native | Yes | DCD/PDB trajectory | Medium (conda) | **MEDIUM** |
| AlphaFlow | Native | Yes | PDB ensemble | Hard (OpenFold dep) | **HARD** |
| Modal+Blender | Via Modal | Yes (cloud) | MP4 | Easy (Modal handles deps) | **MEDIUM** |
| Modal+PyMOL | Via Modal | Yes (cloud) | MP4 | Easy (Modal handles deps) | **MEDIUM** |

---

## Sources

- [Beyond static structures: protein conformations in post-AlphaFold era](https://academic.oup.com/bib/article/26/4/bbaf340/8202937)
- [Mac-Diff: conditional diffusion for conformational ensembles (Nature MI 2026)](https://www.nature.com/articles/s42256-026-01198-9)
- [Awesome AI4MolConformation-MD list](https://github.com/AspirinCode/awesome-AI4MolConformation-MD)
- [Str2Str: Score-based zero-shot conformation sampling](https://arxiv.org/abs/2306.03117)
- [AlphaFlow GitHub](https://github.com/bjing2016/alphaflow)
- [AlphaFlow paper](https://arxiv.org/html/2402.04845v2)
- [DynamicBind GitHub](https://github.com/luwei0917/DynamicBind)
- [DynamicBind paper (Nature Communications)](https://www.nature.com/articles/s41467-024-45461-2)
- [ConfDiff GitHub (ByteDance)](https://github.com/bytedance/ConfDiff)
- [P2DFlow GitHub](https://github.com/BLEACH366/P2DFlow)
- [P2DFlow paper (JCTC)](https://pubs.acs.org/doi/10.1021/acs.jctc.4c01620)
- [EigenFold GitHub](https://github.com/bjing2016/EigenFold)
- [GENIE 2 GitHub](https://github.com/aqlaboratory/genie2)
- [Boltz-sample conformational steering (bioRxiv Jan 2026)](https://www.biorxiv.org/content/10.64898/2026.01.23.701250v1)
- [Boltz-2 on Tamarind Bio](https://app.tamarind.bio/boltz)
- [PyMOL open-source GitHub](https://github.com/schrodinger/pymol-open-source)
- [PyMOL conda-forge](https://anaconda.org/conda-forge/pymol-open-source)
- [PyMOL mpng command](https://pymol.org/dokuwiki/doku.php?id=command:mpng)
- [PyMOL headless rendering (no GUI)](https://bcrf.biochem.wisc.edu/2023/11/02/no-gui-pymol-for-high-throughput-images-and-optional-docker/)
- [PyMOL making movies](https://pymolwiki.org/index.php/Making_Movies)
- [ChimeraX movie command](https://www.cgl.ucsf.edu/chimerax/docs/user/commands/movie.html)
- [ChimeraX offscreen rendering](https://www.cgl.ucsf.edu/chimerax/docs/user/commands/graphics.html)
- [Molecular Nodes Blender add-on](https://github.com/BradyAJohnston/MolecularNodes)
- [Molecular Nodes PyPI](https://pypi.org/project/molecularnodes/)
- [Molecular Nodes releases (v4.2.12, March 2025)](https://github.com/BradyAJohnston/MolecularNodes/releases)
- [VMDviz: Python automation for trajectory movies](https://github.com/nec4/VMDviz)
- [nglview MovieMaker API](https://nglviewer.org/nglview/latest/_api/nglview.contrib.movie.html)
- [nglview movie tutorial (AmberMD)](https://ambermd.org/tutorials/analysis/tutorial_notebooks/nglview_movie/index.html)
- [ProDy GitHub](https://github.com/prody/ProDy)
- [ProDy ANM tutorial](http://www.bahargroup.org/prody/tutorials/enm_analysis/anm.html)
- [ProDy traverseMode / writePDB](https://snyk.io/advisor/python/ProDy/functions/prody.writePDB)
- [ClustENMD paper (Bioinformatics)](https://academic.oup.com/bioinformatics/article/37/21/3956/6317825)
- [iMODS web server](https://academic.oup.com/nar/article/42/W1/W271/2435308)
- [iMODS server URL](http://imods.chaconlab.org)
- [OpenMM documentation](https://docs.openmm.org/latest/userguide/application/02_running_sims.html)
- [SBMOpenMM for folding simulations](https://github.com/CompBiochBiophLab/sbm-openmm)
- [MDAnalysis multi-model PDB writing](https://docs.mdanalysis.org/stable/documentation_pages/coordinates/PDB.html)
- [FATCAT flexible alignment](https://fatcat.godziklab.org/)
- [MORPH-PRO server](https://ncbi.nlm.nih.gov/pmc/articles/PMC3738870)
- [Mol* movie export](https://molstar.org/viewer-docs/tips/movie-export/)
- [MolViewSpec animations](https://molstar.org/mol-view-spec-docs/animations/)
- [MolViewSpec GitHub](https://github.com/molstar/mol-view-spec)
- [Modal Blender rendering example](https://modal.com/docs/examples/blender_video)
- [Modal GPU docs](https://modal.com/docs/guide/gpu)
- [ChatMol MCP server GitHub](https://github.com/ChatMol/molecule-mcp)
- [Stmol: Streamlit molecular visualization](https://pmc.ncbi.nlm.nih.gov/articles/PMC9538479/)
- [EnGens ensemble generator](https://academic.oup.com/bib/article/24/4/bbad242/7219768)
- [BioExcel biobb conformational ensemble tutorial](http://mmb.irbbarcelona.org/biobb/workflows/tutorials/biobb_wf_flexdyn)
- [PyMOL EGL support discussion](https://github.com/schrodinger/pymol-open-source/issues/201)
- [Puppeteer video recorder](https://www.npmjs.com/package/puppeteer-video-recorder)
- [Protein animation from PDB (Kamil Slowikowski)](https://slowkow.com/notes/protein-animation/)
- [Rotating protein animation tutorial](https://slowkow.com/notes/protein-animation/)
