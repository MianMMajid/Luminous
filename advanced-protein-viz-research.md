# Advanced Protein Visualization, Design & Animation: Tool Research

*Research date: March 2026*

---

## 1. Interactive 3D Protein Editors

### Mol* (Molstar) — The Gold Standard for Web Viewing
- **What**: Comprehensive WebGL-based macromolecular viewer used by PDBe, AlphaFold DB, RCSB
- **Editing capabilities**: Mol* is a *viewer*, not an editor. It supports programmatic residue selection, mutation frequency overlay, focus representations (ball-and-stick for loci), and non-covalent interaction visualization. No drag-to-mutate or sculpting.
- **Python API**: Via `molviewspec` (v1.8.1) — declarative builder for views with per-residue coloring, labels, tooltips
- **License**: MIT
- **Streamlit**: Yes, via `molviewspec.molstar_streamlit()` (already in project) or `streamlit-molstar` package
- **Integration difficulty**: Already integrated. Best-in-class for viewing; for editing, need separate tools.
- **GitHub**: https://github.com/molstar/molstar
- **Key limitation**: Renders via iframe — no click callbacks back to Python

### 3Dmol.js / py3Dmol
- **What**: WebGL-accelerated JavaScript molecular graphics library, with Python wrapper `py3Dmol`
- **Capabilities**: Lines, crosses, sticks, spheres, cartoons; surface rendering with async loading; color by partial charge or atom type; isosurfaces from grid data; text/image labels; click callbacks
- **Editing**: Developers explicitly state focus is on *viewing*, not cheminformatics editing. No mutation/sculpting features.
- **Surface features**: `addSurface()` with VDW/SAS/SES types, color by property (charge, residue type)
- **Python API**: `py3Dmol` wraps the JS library for Jupyter/Streamlit
- **License**: BSD-3-Clause
- **Streamlit**: Via `stmol` package (MIT license, v0.0.9) which wraps py3Dmol
- **Integration difficulty**: Easy — `pip install stmol py3Dmol`
- **Best for**: Quick protein visualization with surface coloring in Streamlit when you need callbacks

### streamlit-molstar
- **What**: Streamlit component wrapping Mol* viewer
- **Features**: PDB/CIF/SDF/MRC support, trajectory playback (.xtc), pocket visualization (p2rank), docking result display, RCSB remote loading
- **Python API**: `st_molstar()`, `st_molstar_rcsb()`, `st_molstar_remote()`, `st_molstar_pockets()`, `st_molstar_docking()`
- **License**: MIT (with caveats — see issue #21)
- **Limitation**: No documented per-residue coloring support (molviewspec is better for this)
- **Integration difficulty**: Easy — `pip install streamlit-molstar`
- **GitHub**: https://github.com/pragmatic-streamlit/streamlit-molstar

### NGLView (NGL Viewer for Jupyter)
- **What**: IPython/Jupyter widget for molecular visualization using NGL
- **Features**: Per-residue coloring (`_set_color_by_residue()`), surface representations with opacity, trajectory playback, interoperability with MDTraj/MDAnalysis/RDKit
- **Python API**: Rich — `nglview.show_pdbid()`, `view.add_surface()`, `view.add_cartoon()`
- **License**: MIT
- **Streamlit**: Not directly compatible (Jupyter widget). Would need iframe embedding or conversion.
- **Integration difficulty**: Medium — works great in Jupyter, awkward in Streamlit
- **GitHub**: https://github.com/nglviewer/nglview

### PyMOL (Scripting for Custom Visualization)
- **What**: Industry-standard molecular visualization with Python scripting
- **Editing**: Mutagenesis wizard, rotamer selection, sculpting mode, builder for adding residues
- **Python API**: Full Python API via `pymol` module — `cmd.load()`, `cmd.color()`, `cmd.mutagenesis()`, `cmd.sculpt_activate()`
- **License**: Open-source version (BSD-like) or Schrodinger commercial
- **Streamlit**: Cannot embed directly. Can generate images/videos for display.
- **Integration difficulty**: Hard for interactive use in web apps; good for server-side rendering
- **Best for**: Generating publication-quality images and animations server-side

### JSME
- **What**: 2D/3D molecular editor in the browser (small molecules, not proteins)
- **Not suitable** for protein editing — designed for small molecule drawing

### Summary (Editing)
**No open-source browser-based protein *editor* exists.** Mol*, 3Dmol.js, and NGL are all viewers. For actual mutation/design, you need AI tools (ProteinMPNN, ESM3) or desktop apps (PyMOL, ChimeraX). The gap here is a genuine opportunity.

---

## 2. Protein Video/Animation Generation

### MolecularNodes (Blender) — Best for Production Animations
- **What**: Blender addon for molecular animations using Geometry Nodes
- **Version**: 4.5.10 (Jan 2026)
- **Features**: Import PDB/CIF, MD trajectories, EM density maps; full Blender animation pipeline; customizable styles; GPU overlay annotations (GSoC 2025)
- **Python API**: Yes — overhauled scripting API in recent versions with many examples in docs
- **License**: GPL-3.0
- **Streamlit**: Cannot embed Blender. Can render videos/images for display.
- **Integration difficulty**: Hard for real-time; excellent for pre-rendered content
- **GitHub**: https://github.com/BradyAJohnston/MolecularNodes
- **PyPI**: `pip install molecularnodes` (for headless scripting)

### ChimeraX
- **What**: UCSF successor to Chimera, 80% Python / 20% C++
- **Animation**: `movie record` command creates MP4/MOV/AVI via built-in ffmpeg; supports morphing between conformations
- **Python API**: Full — `ChimeraX.core`, command scripts, bundle system for plugins
- **License**: Free for academic, commercial license from RBVI
- **Streamlit**: Cannot embed. Server-side rendering only.
- **Integration difficulty**: Medium — good CLI/Python scripting for batch rendering
- **GitHub**: https://github.com/RBVI/ChimeraX

### ProDy — Normal Mode Analysis & Animation
- **What**: Python library for protein dynamics analysis (ANM, GNM, PCA)
- **Features**: Normal mode analysis, anisotropic network models, conformational sampling, NMWiz visualization plugin for VMD
- **Python API**: `prody.ANM()`, `prody.calcANM()`, mode animation generation
- **Visualization**: Jupyter via py3Dmol integration; VMD via NMWiz plugin
- **License**: MIT
- **Streamlit**: Can compute modes and generate animation data; visualize via py3Dmol/stmol
- **Integration difficulty**: Easy for computation, medium for visualization
- **GitHub**: https://github.com/prody/ProDy
- **Key use**: Generate B-factor/flexibility animations from structure alone (no MD needed)

### BioEmu (Microsoft) — AI Protein Dynamics
- **What**: Deep learning model generating protein conformational ensembles from sequence alone
- **Performance**: 1000 structures/hour on single GPU; 10,000-100,000x faster than MD
- **Python API**: `from bioemu.sample import main as sample; sample(sequence='...', num_samples=10, output_dir='...')`
- **GPU**: A100 80GB recommended (100 residues: 4 min, 300 residues: 40 min)
- **License**: MIT
- **Streamlit**: Generate ensembles server-side, animate transitions in viewer
- **Integration difficulty**: Medium — needs GPU, pip installable
- **GitHub**: https://github.com/microsoft/bioemu
- **HuggingFace**: https://huggingface.co/microsoft/bioemu

### AlphaFlow — Flow-Based Ensemble Generation
- **What**: AlphaFold2 fine-tuned with flow matching for conformational ensemble generation
- **Variants**: AlphaFlow-PDB, AlphaFlow-MD, AlphaFlow-MD+Templates; also ESMFlow (ESMFold-based)
- **Python API**: Yes, PyTorch-based
- **License**: MIT
- **Available on**: Tamarind Bio as hosted tool
- **GitHub**: https://github.com/bjing2016/alphaflow

### Manim (3Blue1Brown's Library)
- **What**: Python animation engine for mathematical/scientific explanatory videos
- **Protein use**: Not protein-specific, but can animate 3D objects, create smooth morphs, render equations
- **Could be used for**: Animated diagrams of protein concepts, confidence score evolution, pipeline explanations
- **Python API**: Full — scene-based, `Scene`, `ThreeDScene`, camera movement
- **License**: MIT
- **Streamlit**: Render videos server-side, display in app
- **Integration difficulty**: Medium — steep learning curve, not protein-aware
- **GitHub**: https://github.com/ManimCommunity/manim

### VMD (Visual Molecular Dynamics)
- **What**: Classic MD visualization tool from UIUC
- **Animation**: Trajectory playback, movie export, TCL/Python scripting
- **License**: Free for non-commercial
- **Streamlit**: Cannot embed. Server-side rendering only.

### MovieMaker (Web Server)
- **What**: Web server generating short protein motion movies
- **Features**: Rotation, morphing between conformers, vibrations, ligand docking, folding/unfolding
- **API**: Web-based (not programmatic)
- **Best for**: Quick one-off animations, not pipeline integration

### OpenMM — Molecular Dynamics Engine
- **What**: High-performance MD simulation toolkit with Python API
- **Features**: GPU-accelerated, multiple force fields (AMBER, CHARMM), energy minimization, equilibration
- **Python API**: Full — `openmm.app`, `Simulation`, `Topology`
- **License**: MIT
- **Use case**: Generate actual MD trajectories for animation
- **Integration difficulty**: High — needs GPU, force field setup, simulation time

### MDAnalysis / MDTraj — Trajectory Analysis
- **What**: Python libraries for reading/analyzing MD trajectories
- **MDAnalysis**: Reads GROMACS/AMBER/NAMD/LAMMPS formats, integrates with NGLView
- **MDTraj**: Lightweight, NumPy-based, RMSD/RMSF/secondary structure analysis
- **License**: GPL-2 (MDAnalysis) / LGPL-2.1 (MDTraj)
- **Streamlit**: Compute properties, feed to Plotly/py3Dmol for visualization
- **Integration difficulty**: Easy for analysis, medium for visualization

---

## 3. AI Protein Design Tools (Open APIs / Python SDKs)

### ESM3 (EvolutionaryScale) — Multimodal Protein Generation
- **What**: Frontier generative model reasoning across sequence, structure, and function simultaneously
- **Models**: esm3-small (1.4B, open), esm3-medium (7B, API), esm3-large (98B, API)
- **Python API**: `from esm.models.esm3 import ESM3; model = ESM3.from_pretrained("esm3-open"); model.generate(protein, GenerationConfig(track="sequence", num_steps=8))`
- **Forge API**: Cloud access with free academic tier — same code interface
- **License**: Non-commercial for open weights; Cambrian license for SageMaker
- **Install**: `pip install esm`
- **GitHub**: https://github.com/evolutionaryscale/esm
- **HuggingFace**: https://huggingface.co/EvolutionaryScale/esm3-sm-open-v1

### ESM-C (EvolutionaryScale) — Protein Embeddings
- **What**: Drop-in ESM-2 replacement focused on embeddings (not generation)
- **Models**: esmc-300m, esmc-600m, esmc-6b
- **Key**: 300M matches ESM-2 650M performance. Same API, half the compute.
- **Python API**: `from esm.models.esmc import ESMC; client = ESMC.from_pretrained("esmc_300m")`

### RFdiffusion3 (Baker Lab, Dec 2025) — State of the Art
- **What**: All-atom protein design via diffusion; designs proteins binding DNA, small molecules, other proteins
- **Key advance**: 10x faster than RFdiffusion2, atom-level precision, training code released
- **License**: Open source via Rosetta Commons Foundry (BSD-3-Clause for academic)
- **GitHub**: https://github.com/RosettaCommons/RFdiffusion
- **Hosted**: Tamarind Bio, Subseq
- **GPU**: Requires significant GPU (A100 recommended)

### ProteinMPNN (Dauparas et al.)
- **What**: Inverse folding — given backbone structure, designs sequences that fold to it
- **Python API**: PyTorch model, scripts in GitHub repo
- **License**: MIT
- **Hosted APIs**: Levitate Bio, Tamarind Bio, OpenProtein
- **GitHub**: https://github.com/dauparas/ProteinMPNN
- **Integration**: Can run locally with GPU or via hosted API

### BindCraft — One-Shot Binder Design
- **What**: Automated pipeline for de novo protein binder design using AlphaFold2 backpropagation + MPNN
- **Success rate**: 10-100% experimental success
- **Published**: Nature, 2025
- **License**: MIT (FreeBindCraft variant is fully open)
- **Requirements**: Linux, CUDA GPU, conda/mamba
- **GitHub**: https://github.com/martinpacesa/BindCraft

### ProtGPT2 — Generative Protein Language Model
- **What**: GPT-2 architecture (738M params) pre-trained on UniRef50 for de novo protein generation
- **Python API**: HuggingFace Transformers — `from transformers import pipeline; generator = pipeline('text-generation', model='nferruz/ProtGPT2')`
- **License**: Apache-2.0
- **HuggingFace**: https://huggingface.co/nferruz/ProtGPT2
- **Integration difficulty**: Easy — standard HuggingFace pipeline

### AIDO.Protein (GenBio AI)
- **What**: 16B parameter protein model with Mixture-of-Experts architecture
- **License**: Check HuggingFace model card
- **HuggingFace**: https://huggingface.co/genbio-ai/AIDO.Protein-16B

### Boltz-2 (MIT/Recursion, 2025)
- **What**: Structure prediction + binding affinity estimation; first DL model approaching FEP accuracy at 1000x speed
- **License**: MIT (code and weights)
- **Features**: Experimental method conditioning, distance constraints, multi-chain templates
- **Hosted**: Modal (official docs), Tamarind Bio, NVIDIA NIM, Google Colab
- **GitHub**: https://github.com/jwohlwend/boltz
- **Modal deployment**: https://modal.com/docs/examples/boltz_predict

### Chai-1 (Open) / Chai-2 (Restricted)
- **Chai-1**: Multimodal structure prediction competitive with AlphaFold3. Apache 2.0 license (code + weights).
- **Chai-2**: De novo antibody/binder design (June 2025). NOT open source — early access partners only.
- **GitHub**: https://github.com/chaidiscovery/chai-lab

### Tamarind Bio Platform — Hosted Design Tools
Complete list of tools available via REST API:
- **Structure prediction**: AlphaFold, Boltz-1x, Boltz-2, Chai-1, OpenFold3, ESMFold
- **Protein design**: RFdiffusion (by task), ProteinMPNN, BindCraft, RFpeptides, BoltzGen
- **Antibody**: RFantibody, AbLang+ProteinMPNN, IgDesign, Germinal
- **Dynamics**: AlphaFlow, GROMACS
- **Analysis**: PRODIGY (binding energy), ADMET, Smina (docking), TemStaPro (thermostability), TEMPRO (nanobody Tm), Deep Viscosity, Protein Properties, RMSD Calculator
- **New (2025)**: Proteus AI (ML-directed evolution), Deploy Custom Models, Protein Database
- **API**: REST, submit-job pattern, files under 4MB can be submitted inline
- **Pricing**: Pro account removes 10 job/month limit

---

## 4. Novel 3D Mapping Approaches

### Electrostatic Surface Mapping

**APBS + PDB2PQR** (Standard approach)
- **What**: Adaptive Poisson-Boltzmann Solver for continuum electrostatics
- **Python**: Can be called from Python via subprocess; PyMOL plugin (`pmg_tk.pdb2pqr_cli`, `map_new_apbs`)
- **Web server**: https://www.poissonboltzmann.org/
- **License**: BSD
- **GitHub**: https://github.com/Electrostatics
- **Streamlit**: Run server-side, visualize result as surface coloring in viewer

**PEP-Patch** — Electrostatic + Hydrophobicity Patches
- **What**: Quantifies electrostatic potential as surface patches; also supports hydrophobicity scales (Eisenberg, Crippen)
- **Python API**: Yes
- **License**: MIT
- **GitHub**: https://github.com/liedllab/surface_analyses (related)
- **Streamlit**: Compute patches, map to per-residue colors for molviewspec

### Hydrophobicity Mapping

**Kyte-Doolittle Scale** (most common)
- Color gradient: dodger blue (hydrophilic) -> white -> orange-red (hydrophobic)
- Implementable with Biotite (already in project) — compute per-residue, map to colors

**py3Dmol surface coloring**
- `viewer.addSurface(py3Dmol.SES, {'colorscheme': {'prop': 'b', 'gradient': 'rwb'}})` — color by B-factor or custom property
- Can inject hydrophobicity values as B-factors, then render colored surface

### Conservation Mapping

**ConSurf (2025 update)**
- **What**: Evolutionary conservation scoring mapped onto protein structures
- **2025 features**: Downloadable Python pipeline, works with AlphaFold models, PyMOL/ChimeraX output
- **Web server**: https://consurf.tau.ac.il/
- **Integration**: Download conservation scores, map to per-residue colors in molviewspec

**biostructmap**
- **What**: Python package mapping sequence-aligned data onto structures, including Kyte-Doolittle hydrophobicity
- **License**: MIT
- **GitHub**: https://github.com/andrewguy/biostructmap

**SURFMAP**
- **What**: Maps surface features (conservation, hydrophobicity, interaction sites) onto 2D/3D projections
- **Integrates**: ConSurf conservation data directly

### Binding Pocket Visualization

**pyKVFinder** — Best Python-native option
- **What**: Cavity detection + characterization (volume, area, depth, hydropathy)
- **Output**: NumPy arrays — directly scriptable into pipelines
- **Integrates**: matplotlib, NGL Viewer, SciPy, Jupyter
- **License**: GPL-2.0
- **GitHub**: https://github.com/LBC-LNBio/pyKVFinder

**fpocket**
- **What**: Fast pocket detection via Voronoi tessellation
- **License**: MIT
- **GitHub**: https://github.com/Discngine/fpocket
- **Note**: C-based with Python wrappers available

**DeepPocket**
- **What**: Deep learning-based ligand binding site detection
- **GitHub**: https://github.com/devalab/DeepPocket

### Protein-Protein Interaction Interface Mapping

**PLIP 2025** — Most comprehensive
- **What**: Protein-Ligand Interaction Profiler, now with protein-protein interaction support
- **2025 update**: Jupyter/Colab installation-free, batch processing, Python-based evaluations
- **License**: GPL-2.0

**MAGPIE**
- **What**: Interactive 3D visualization + sequence logo-style amino acid frequency at interface positions

### B-Factor / Flexibility Animation

**Already achievable with current stack:**
1. Parse PDB with Biotite (`extra_fields=["b_factor"]`)
2. Map B-factors to per-residue color gradient
3. Use ProDy ANM to compute normal modes for flexibility animation
4. Render in molviewspec with `color_from_uri()` using computed colors

---

## 5. Streamlit-Compatible Solutions (Ranked)

### Tier 1: Production-Ready, Already Proven

| Tool | Mechanism | Per-Residue Color | Surface | Callbacks | Install |
|------|-----------|-------------------|---------|-----------|---------|
| **molviewspec** | Mol* via iframe | Yes (color_from_uri) | Yes (built-in Mol*) | No | `pip install molviewspec` |
| **stmol + py3Dmol** | 3Dmol.js via iframe | Yes (setStyle) | Yes (addSurface) | Limited | `pip install stmol py3Dmol` |
| **Plotly 3D** | st.plotly_chart | Manual (scatter3d) | No (scatter only) | Yes (click events) | Built-in |

### Tier 2: Functional, Some Limitations

| Tool | Mechanism | Per-Residue Color | Surface | Callbacks | Install |
|------|-----------|-------------------|---------|-----------|---------|
| **streamlit-molstar** | Mol* component | Not documented | Via Mol* | No | `pip install streamlit-molstar` |
| **Dash Bio Molecule3D** | Plotly Dash component | Yes | Limited | Yes | Requires Dash (not Streamlit) |

### Tier 3: Requires Workarounds

| Tool | Mechanism | Notes |
|------|-----------|-------|
| **Three.js via st.components.v1.html** | Custom iframe | Full 3D control but must implement molecular rendering from scratch |
| **streamlit-stl** | Three.js STL viewer | For mesh files, not molecular data |
| **Streamlit Components v2** | Frameless custom UI | New in 2025 — bidirectional data flow without iframe, could enable custom viewers |

### Recommended Approach for BioVista

**Primary**: molviewspec (already integrated) — best per-residue coloring, tooltips, labels
**Secondary**: stmol/py3Dmol — for cases needing surface coloring (hydrophobicity, electrostatic)
**Tertiary**: Plotly 3D scatter — for simplified backbone visualization with click callbacks (e.g., selecting residues)

The new **Streamlit Components v2** (2025) with frameless bidirectional data flow could eventually solve the iframe callback limitation — worth monitoring.

---

## 6. Highest-Impact Integration Opportunities for BioVista

### Quick Wins (hours to integrate)
1. **Hydrophobicity mapping**: Compute Kyte-Doolittle per residue with Biotite, map to colors, render via molviewspec `color_from_uri` — purely computational, no new dependencies
2. **B-factor flexibility overlay**: Already have B-factor parsing; create color gradient and render
3. **ProDy normal modes**: `pip install prody`, compute ANM, generate mode vectors, animate as multi-frame PDB in viewer
4. **stmol/py3Dmol surface**: Add second viewer tab with surface coloring for hydrophobicity/charge

### Medium Effort (days)
4. **BioEmu conformational ensemble**: Generate 10-100 conformations from sequence, display as animation or overlay
5. **pyKVFinder pocket detection**: Detect binding pockets, highlight in viewer with labels
6. **Conservation overlay**: Fetch ConSurf scores via API, map to per-residue colors
7. **PLIP interaction analysis**: Analyze protein-ligand or protein-protein contacts, visualize

### Ambitious (week+)
8. **ESM3 protein generation**: Generate novel proteins from partial prompts, predict structure, visualize
9. **MolecularNodes video rendering**: Pre-render publication-quality animations for report export
10. **AlphaFlow ensemble animation**: Generate conformational diversity, animate transitions

---

## Sources

- [Mol* — molstar.org](https://molstar.org/)
- [3Dmol.js](https://3dmol.csb.pitt.edu/)
- [stmol on GitHub](https://github.com/napoles-uach/stmol)
- [streamlit-molstar on GitHub](https://github.com/pragmatic-streamlit/streamlit-molstar)
- [MolecularNodes on GitHub](https://github.com/BradyAJohnston/MolecularNodes)
- [ChimeraX on GitHub](https://github.com/RBVI/ChimeraX)
- [ProDy — Protein Dynamics Analysis](http://prody.csb.pitt.edu/)
- [BioEmu on GitHub](https://github.com/microsoft/bioemu)
- [AlphaFlow on GitHub](https://github.com/bjing2016/alphaflow)
- [ESM3 on GitHub](https://github.com/evolutionaryscale/esm)
- [RFdiffusion3 — Institute for Protein Design](https://www.ipd.uw.edu/2025/12/rfdiffusion3-now-available/)
- [ProteinMPNN — Science](https://www.science.org/doi/10.1126/science.add2187)
- [BindCraft on GitHub](https://github.com/martinpacesa/BindCraft)
- [ProtGPT2 on HuggingFace](https://huggingface.co/nferruz/ProtGPT2)
- [Boltz-2 on GitHub](https://github.com/jwohlwend/boltz)
- [Chai-1 on GitHub](https://github.com/chaidiscovery/chai-lab)
- [Tamarind Bio](https://www.tamarind.bio/)
- [Tamarind Bio Changelog](https://changelog.tamarind.bio)
- [APBS/PDB2PQR](https://www.poissonboltzmann.org/)
- [PEP-Patch](https://pmc.ncbi.nlm.nih.gov/articles/PMC10685443/)
- [ConSurf](https://academic.oup.com/nar/article/37/suppl_1/D323/1012935)
- [biostructmap on GitHub](https://github.com/andrewguy/biostructmap)
- [pyKVFinder](https://link.springer.com/article/10.1186/s12859-021-04519-4)
- [fpocket on GitHub](https://github.com/Discngine/fpocket)
- [PLIP 2025](https://academic.oup.com/nar/article/53/W1/W463/8128215)
- [SURFMAP](https://www.biorxiv.org/content/10.1101/2021.10.15.464543v2.full)
- [NGLView on GitHub](https://github.com/nglviewer/nglview)
- [MDAnalysis](https://www.mdanalysis.org/)
- [MDTraj](https://www.mdtraj.org/)
- [OpenMM](https://openmm.org/)
- [Manim Community](https://www.manim.community/)
- [Plotly 3D Protein Visualization](https://www.blopig.com/blog/2021/01/plotly-for-interactive-3d-plotting/)
- [Foldseek on GitHub](https://github.com/steineggerlab/foldseek)
- [Streamlit Components v2 — 2025 Release Notes](https://docs.streamlit.io/develop/quick-reference/release-notes/2025)
- [ML Engineer's Guide to Protein AI](https://huggingface.co/blog/MaziyarPanahi/protein-ai-landscape)
- [Microsoft BioEmu-1 — InfoQ](https://www.infoq.com/news/2025/02/microsoft-bioemu-1/)
- [RFdiffusion3 — GEN News](https://www.genengnews.com/topics/artificial-intelligence/rfdiffusion3-now-open-source-designs-dna-binders-and-advanced-enzymes/)
- [Modal Boltz-2 Deployment](https://modal.com/docs/examples/boltz_predict)
