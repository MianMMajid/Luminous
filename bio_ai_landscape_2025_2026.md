# Bio AI & Computational Biology: What the Community Is Actually Debating (2025-2026)

*Research compiled March 2026*

---

## 1. THE FOUNDATION MODEL RECKONING: Do They Actually Work?

### The Single-Cell Foundation Model Controversy
This is arguably the hottest debate in computational biology right now. A Nature Methods paper (August 2025) systematically benchmarked five foundation models (scGPT, scFoundation, scBERT, Geneformer, UCE) plus GEARS and CPA against deliberately simple baselines for predicting gene perturbation effects. **None of the deep learning models outperformed the baselines.** Even the simplest baseline -- taking the mean of training examples -- beat scGPT and scFoundation. A separate Genome Biology study showed that for zero-shot cell type clustering, selecting highly variable genes (HVG) and using established methods like Harmony and scVI outperformed both Geneformer and scGPT across all metrics.

**What scientists are arguing about:**
- Whether the masked language model pretraining framework used by scGPT/Geneformer is fundamentally mismatched for non-sequential omics data
- Whether foundation models capture anything beyond what simple statistical summaries already encode
- Whether the field is suffering from "benchmark gaming" where models look good on contrived tasks but fail on real biological questions
- A counter-paper on bioRxiv (October 2025) argues these models *do* outperform baselines when metrics are properly calibrated -- the debate is live and unresolved

### Protein Language Models: Bigger Is Not Better
ESM-2 (15B parameters) does not consistently outperform ESM-2 (650M) or ESM-C (600M), especially on limited data. More fundamentally, researchers showed ESM-2's performance is highly correlated with the number of sequence neighbors in the training set -- suggesting it stores coevolution statistics rather than learning protein physics. If it had truly learned folding principles, performance should not depend on sequence neighbor density.

### Architectural Mismatch
Transformers were designed for human language. Biological sequences are governed by physicochemical laws, contain non-local dependencies (structural motifs), and have varying lengths. The community increasingly questions whether forcing biology into a next-token-prediction framework is the right paradigm.

---

## 2. AI DRUG DISCOVERY: The Year of the Reality Check

### 2025's Sobering Clinical Results
- Multiple AI-designed drugs were deprioritized, shelved after Phase II, or showed no efficacy signal
- AI has NOT demonstrably improved pharma's ~90% clinical failure rate
- Recursion cut three programs in May 2025, halting development for cerebral cavernous malformation and NF2
- Deal announcements totaled $15B in "biobucks," but actual upfront payments were ~2% of headline figures
- 95% of enterprise generative AI pilots failed to deliver measurable business impact

### The One Success (With Caveats)
The first drug with both target and molecule designed entirely by AI completed Phase IIa trials for idiopathic pulmonary fibrosis, showing dose-dependent improvement. But: only 71 patients enrolled, requiring larger validation.

### What AI Actually Does Well
- Compresses early discovery timelines by 30-40%
- Reduces preclinical candidate development to 13-18 months (vs. 3-4 years traditional)
- Cannot bypass clinical trial duration, regulatory review, or manufacturing scale-up
- **Consensus: AI is a valuable early-stage accelerator, not a panacea**

### The Virtual Screening Revolution (Real, But Nuanced)
- Boltz-2 delivers near physics-level binding affinity predictions at 1,000x the speed of free-energy perturbation simulations
- DrugCLIP scans millions of compounds against thousands of targets in hours (10 million times faster than traditional screening)
- But validation remains the bottleneck -- speed without clinical translation is just faster failure

### Key Players to Watch
- **Isomorphic Labs**: $600M raise (March 2025), $3B in partnerships with Eli Lilly and Novartis, first Phase I trials expected late 2026
- **Recursion**: Pipeline cuts but expanding "ClinTech" AI for clinical trial optimization; ~7 programs in trials
- **Insilico Medicine**: ISM001-055 in Phase II for IPF -- the leading AI-designed drug candidate

---

## 3. SELF-DRIVING LABS: Will Robots Replace Biologists?

### The Nature Debate (February 2026)
A Nature article sparked widespread debate: "Will self-driving 'robot labs' replace biologists?" Philip Romero (protein engineer) declared these systems "are going to be the future of biology." Others insist human skills remain essential.

### Current Capabilities
- Ginkgo Bioworks + OpenAI demonstrated GPT-5 interpreting results and designing experiments executed by Ginkgo's robotics
- University of Illinois combined AI + automated robotics + synthetic biology: enzyme variants with 26-fold increased activity and 90-fold greater substrate specificity
- ChemCrow architecture: LLM front-end controlling spectrometers, liquid-handling robots, chromatography via action-queue API
- McKinsey reports pharma could reduce R&D cycle times by 500+ days through comprehensive AI + automation

### What They Cannot Do Yet
- Tasks requiring fine dexterity
- Experiments without clear-cut measures of progress
- Genuinely creative experimental design vs. optimization within known parameter spaces
- The field distinguishes between "automated" (following instructions faster) and "autonomous" (making decisions)

### Access Models Emerging
"Cloud labs" offer subscription-based remote-control access to experimental capabilities, potentially democratizing science but raising questions about who controls the infrastructure.

---

## 4. GENERATIVE PROTEIN DESIGN: The Wet Lab Validation Era

### 2025-2026 Breakthroughs
- **RFdiffusion2** (April 2025): Designs enzymes with tailor-made active sites given only a description of the chemical reaction. Successfully scaffolded all 41 active sites in a diverse benchmark.
- **RFdiffusion3** (December 2025): 10x faster than RFdiffusion2, atom-level precision, open source, designs DNA binders
- **OriginFlow**: Flow-matching model achieving 90% expression, solubility, and affinity on PD-L1, RBD, VEGF targets
- De novo proteins binding influenza hemagglutinin stem (Kd ~25 nM) and PD-L1 (Kd ~12 nM) with functional inhibition
- Generative AI proteins outperforming nature at genome editing (October 2025)

### The Open vs. Closed Debate
The AlphaFold3 saga defined this: DeepMind initially released a closed server, triggering an open letter with 1,000+ scientist signatures demanding code release. Community rallied around open alternatives (Boltz-1, Chai-1, OpenFold3). DeepMind released code in November 2024, but the damage catalyzed a permanent "open science" movement in structural biology. Boltz-1 and Boltz-2 are fully open source and match AF3 performance.

---

## 5. AGENTIC AI FOR SCIENCE: The Newest Frontier

### Google's AI Co-Scientist
Multi-agent system built on Gemini 2.0 for hypothesis generation, literature review, and experimental design. Successfully proposed drug repurposing candidates for AML validated in wet lab. But: critics question whether it is "remixing the past" rather than discovering something genuinely new. Key limitation: cannot access paywalled research, cannot distinguish low- from high-quality studies.

### Agentic Bioinformatics
A new named subfield (2025) deploying autonomous agents for real-time data generation, experimental design, and high-dimensional analysis. The ICLR 2026 MLGenX workshop theme is specifically "From Reasoning to Experimentation: Closing the Loop Between AI Agents and the Biological Lab."

### The "Agentic Lab" System
A bioRxiv preprint describes an agentic-physical AI platform unifying LLM/VLM reasoning with real-world lab operations via multi-agent orchestration with specialized subagents for knowledge retrieval, protocol design, and multimodal analysis.

---

## 6. SPATIAL TRANSCRIPTOMICS + AI: Rapidly Evolving Methods

### Key Developments
- Foundation models for spatial omics showing strong results across multiple tasks
- Graph-based, contrastive learning, and transformer approaches each contributing unique strengths
- Spotiphy: New tool bridging sequencing-based and imaging-based spatial transcriptomics
- SpatialAgent: LLM integrating 19 toolchains to process spatial transcriptome data, improving cell type prediction by 6-19 percentage points
- Spatial omics adoption growing at ~28% annually with 500+ published datasets as of 2025

### Open Challenges
- Low-resolution spatial assays still have spatial blur and ambient RNA contamination
- Integrating histopathology with omics achieves up to 90% accuracy for tissue-level predictions but tissue heterogeneity remains hard
- Cross-modality prediction accuracy improved 20-30% vs. unimodal baselines but still insufficient for many applications

---

## 7. THE VIRTUAL CELL: Biology's Moonshot

### Chan Zuckerberg Initiative + NVIDIA
CZI is building "virtual cells" -- digital twins of human cells where cellular processes can be simulated. NVIDIA partnership (October 2025) to scale development. CZI launched **rBio**, a reasoning model trained on virtual cell simulations. Priscilla Chan estimated ~5 years to achieve the goal.

### The Debate
- Whether we have sufficient data across modalities (genomics, proteomics, metabolomics, imaging) to build realistic virtual cells
- Whether foundation models can capture causal relationships (not just correlations) needed for true simulation
- The fundamental question: predictive accuracy is often insufficient in biology -- the real questions are *causal* (how does perturbing gene X affect pathway Y?)
- No consensus on whether current architectures can represent the full complexity of cellular state spaces

---

## 8. EVO2 AND GENOME-SCALE MODELS

### The Model
Released February 2025, Evo2 is trained on 9.3 trillion DNA base pairs from 128,000+ genomes across all domains of life. 1 million token context window with single-nucleotide resolution. Computational scale matching leading text LLMs.

### Capabilities
Zero-shot mutation impact prediction, genome annotation, gene essentiality identification, and prediction of pathogenic BRCA1 variants -- all without task-specific fine-tuning.

### The "Not Yet" Assessment
A Nature Digital Medicine perspective (2025) titled "Genomic language models could transform medicine but not yet" argues that while powerful, these models are not ready for clinical deployment. How much of the non-conserved genome contributes to regulation remains debated, and model interpretability is insufficient for medical decision-making.

---

## 9. CRISPR + AI: Maturing But Not Solved

### New Methods
- **CCLMoff**: Deep learning framework using pretrained RNA language models for off-target prediction
- **crispAI**: Neural network providing uncertainty estimates for off-target cleavage activity
- **Explainable AI (XAI)** techniques beginning to illuminate black-box CRISPR models
- No single model consistently outperforms across all scenarios; CRISPR-Net, R-CRISPR, and Crispr-SGRU show strongest overall performance

### The Real Frontier
AI-designed synthetic proteins outperforming natural CRISPR proteins at genome editing. The shift from predicting off-targets to actually *designing* better editing systems represents a paradigm change.

---

## 10. DIGITAL TWINS FOR PATIENTS: Promise Outpacing Reality

### Where It Works
- Early warning systems leveraging DT technology reduced code blue incidents by 60%
- Bone metastasis digital twins reproducing tumor biology with unprecedented precision
- DT-GPT extending LLM-based clinical trajectory prediction

### Where It Doesn't (Yet)
- Routine clinical application remains limited to pilot tests and experimental settings
- Next-gen twins must integrate molecular, cellular, tissue, organ, clinical, behavioral, AND environmental data
- FDA released first draft guidance on AI models in drug development (2025), but regulatory frameworks are nascent

---

## 11. BIOSECURITY: The Elephant in the Room

### Concrete Risks Identified
- AI can elucidate how to make contact-transmitted pathogens airborne
- AI-powered platforms lower expertise thresholds for engineering hazardous organisms
- Biological design tools could enable pandemic pathogens "more devastating than anything seen to date"

### Policy Response
- Experts advocate capability-based evaluations (not pathogen lists) before model deployment
- Proposed measures: excluding concerning training data, machine unlearning, restricting API access
- The quality, accessibility, and oversight of genomic data identified as a key leverage point
- Push for international standards but no consensus framework yet

---

## 12. THE REPRODUCIBILITY CRISIS IN BIO-AI

### The Problem
- 41 papers from 30 fields found with data leakage errors affecting 648 papers
- Data leakage causes artificially inflated performance metrics and models that fail on independent datasets
- Major conferences (NeurIPS, ICML) have implemented paper checklists but enforcement varies

### Specific to Biology
- Improper data splitting (normalization before train/test split) is rampant
- Population biases in training data lead to models that underperform for underrepresented groups
- Benchmarks in protein structure prediction, drug discovery, and single-cell analysis all have known contamination issues

---

## 13. WHAT SCIENTISTS ARE ACTUALLY RACING TO SOLVE

1. **Causal models of cellular perturbation** -- can we predict what happens when you knock out gene X, not just correlate?
2. **Multimodal integration** -- unifying transcriptomics, proteomics, imaging, and clinical data into coherent models
3. **Closing the design-build-test loop** -- AI designs + robotic execution + automated analysis, fully autonomous
4. **Generative models that actually work in wet labs** -- moving from in silico metrics to experimental validation
5. **Clinical translation of AI drug candidates** -- getting past Phase II with genuine efficacy signals
6. **Interpretability** -- understanding *why* models make predictions, not just that they do
7. **Scaling to whole-organism models** -- from proteins to cells to tissues to patients

---

## 14. KEY CONFERENCES AND VENUES (2025-2026)

- **MLSB at NeurIPS 2025** (December): ML for structural biology, dual locations (San Diego + Copenhagen)
- **ICLR 2026** (April, Rio de Janeiro): Record 19,797 submissions, 70% jump from 2025; MLGenX, GEM, LMRL workshops
- **ISMB 2026**: Major computational biology venue
- **ECCB 2026**: European computational biology
- **GEM Workshop at ICLR**: Seed Grant competition promoting dry-wet lab collaborations
- **Bio-IT World Expo 2026** (May, Boston)

---

## SUMMARY: The Real State of Play

The bio AI field in early 2026 is characterized by a **productive tension between ambition and accountability**. The hype cycle of 2023-2024 -- where every new foundation model was framed as transformative -- has given way to a more rigorous era where benchmarks matter, wet lab validation is demanded, and simple baselines are the bar to clear.

**The biggest unresolved questions:**
- Can foundation models learn biology's causal structure, or are they sophisticated lookup tables?
- Will AI-designed drugs actually improve clinical success rates, or just get to failure faster?
- Should self-driving labs be accessible infrastructure or does science require human intuition at the bench?
- How do we govern dual-use AI capabilities in biology before a catastrophic misuse event?
- Is the virtual cell achievable in 5 years, or is it this decade's fusion energy?

The community is moving from "can AI predict X?" to "does AI prediction of X actually advance biological understanding?" That shift -- from benchmarks to biology -- is the defining transition of 2025-2026.
