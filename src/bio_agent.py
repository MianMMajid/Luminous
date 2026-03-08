"""Bio Research Agent with autonomous tool chaining.

Wraps existing Luminous analysis modules AND online bioinformatics APIs
as tool functions, exposed through Claude's native tool_use API for
autonomous multi-step research workflows.
"""
from __future__ import annotations

import json

from src.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from src.utils import safe_json_dumps

AGENT_SYSTEM_PROMPT = """You are Lumi, an autonomous structural biology research agent and \
assistant scientist built into the Luminous platform. You function as a \
knowledgeable lab partner who can independently investigate protein questions \
using a comprehensive toolkit spanning structure analysis, genomics, \
pharmacology, and literature.

## Your capabilities

**Local analysis** (works on loaded protein structures):
- analyze_structure: SASA, secondary structure, contacts, Ramachandran
- build_trust_audit: pLDDT confidence, flagged regions, validation suggestions
- predict_pockets: Ligand-binding pocket prediction
- compute_flexibility: ANM-based dynamics and hinge residues
- compute_surface_properties: Hydrophobicity, charge, surface patches
- predict_ptm_sites: Post-translational modification sites (glycosylation, phosphorylation, etc.)
- compute_conservation: Per-residue conservation scores (ConSurf-like 1-9 scale)
- predict_disorder: Intrinsic disorder prediction from sequence + structure
- compare_structures: Predicted vs experimental RMSD, GDT-TS, TM-score
- auto_investigate: Comprehensive auto-analysis — runs ALL tools and cross-references results
- build_protein_network: Graph-theoretic PSN — allosteric hubs, communities, bridge residues
- find_communication_path: Shortest structural path between two residues (mutation propagation)
- compute_residue_depth: Continuous burial gradient (more informative than binary SASA)
- generate_hypotheses: Synthesize data into testable claims

**Online databases** (live queries, no structure needed):
- get_protein_info: UniProt — function, domains, GO terms, diseases, sequence
- fold_sequence: ESMFold — instant structure prediction from amino acid sequence
- lookup_alphafold: AlphaFold DB — pre-computed structures by UniProt ID
- predict_variant_effect: Ensembl VEP — SIFT/PolyPhen scores for mutations
- check_population_frequency: gnomAD — allele frequency, gene constraint (pLI)
- get_interaction_network: STRING — protein-protein interaction partners
- classify_domains: InterPro — protein domains, families, sites
- lookup_compound: PubChem — drug properties, Lipinski, mechanism
- get_pharmacogenomics: PharmGKB — drug-gene clinical annotations
- search_literature: Semantic Scholar — citation-ranked paper search
- search_open_access_literature: Europe PMC — open-access biomedical papers
- search_pdb_structures: RCSB PDB — experimental structures by name/gene
- fetch_bio_context: MCP — PubMed, Open Targets, Wiley, ChEMBL context

**Scientific illustration** (BioRender integration):
- search_biorender_templates: Find relevant figure templates from BioRender's library
- search_biorender_icons: Find scientific icons (proteins, drugs, pathways, cells)
- generate_figure_prompt: Create a ready-to-paste BioRender AI text-to-figure prompt

## How to work

1. **Think like a scientist**: Form a question → gather evidence → synthesize → conclude
2. **Chain tools logically**: e.g., get_protein_info → classify_domains → predict_pockets → generate_hypotheses
3. **Cross-reference**: Validate findings across multiple sources (UniProt + literature + gnomAD)
4. **Be honest about uncertainty**: Cite prediction confidence, distinguish prediction from experiment
5. **Suggest next steps**: Recommend specific experiments, computational tools, or follow-up analyses
6. **Use online tools proactively**: Don't just use loaded data — query databases to enrich analysis
7. **Suggest figures**: When findings are significant, proactively suggest BioRender templates \
or generate a figure prompt. For drug-target results → suggest drug mechanism templates. \
For PPI findings → suggest interaction diagrams. For mutation analysis → suggest mutagenesis templates.

## Response style
- Concise, scientific, actionable
- Use markdown: headers, bold, bullet points, tables where appropriate
- Cite sources (UniProt, gnomAD, PubChem, etc.) with identifiers
- When discussing variants, always mention population frequency and clinical significance
- When discussing drugs, include mechanism and clinical phase
- When uncertain, say so explicitly
- When suggesting figures, include the BioRender template name and link"""


def _make_tools() -> list[dict]:
    """Define tool schemas for the Anthropic API tool_use format."""
    return [
        # ── Local analysis tools ──────────────────────────────────────
        {
            "name": "analyze_structure",
            "description": (
                "Compute structural properties from loaded PDB: SASA, secondary structure, "
                "contact maps, packing density, Ramachandran angles, residue interaction network, "
                "and mutation-to-pocket distances. Requires a protein structure to be loaded."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "mutation_pos": {
                        "type": "integer",
                        "description": "Residue number of the mutation to analyze (optional)",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "build_trust_audit",
            "description": (
                "Audit the confidence of the loaded structure prediction. Returns overall confidence "
                "score, per-region pLDDT, pTM/ipTM, flagged low-confidence regions, known "
                "limitations, and suggested validation experiments."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "fetch_bio_context",
            "description": (
                "Fetch biological context from PubMed, Open Targets, Wiley Scholar Gateway, "
                "and ChEMBL via MCP. Returns disease associations, drug candidates, pathway info, "
                "literature summary with paper titles and DOIs."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "search_variants",
            "description": (
                "Search pre-loaded ClinVar variant data for pathogenic variants in the protein. "
                "Returns variant positions, pathogenicity classifications, and hotspot regions."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "predict_pockets",
            "description": (
                "Predict ligand-binding pockets on the loaded protein structure using "
                "SASA/contact heuristics. Returns ranked pockets with residue lists and scores."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "compute_flexibility",
            "description": (
                "Compute per-residue flexibility using Anisotropic Network Model (ANM/ProDy) "
                "on loaded structure. Returns flexibility scores, hinge residues, rigid/flexible regions."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "generate_hypotheses",
            "description": (
                "Generate testable scientific hypotheses by synthesizing structure, trust audit, "
                "biological context, and variant data. Each hypothesis: claim, evidence, confidence, "
                "test method, clinical impact."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # ── Online database tools ─────────────────────────────────────
        {
            "name": "get_protein_info",
            "description": (
                "Query UniProt for comprehensive protein annotation: function, domains, GO terms, "
                "subcellular location, disease associations, known PDB structures, sequence. "
                "Accepts gene name (TP53) or UniProt ID (P04637). Resolves gene→UniProt automatically."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Gene name (e.g., TP53, BRCA1, EGFR) or UniProt ID (e.g., P04637)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "fold_sequence",
            "description": (
                "Predict 3D protein structure from amino acid sequence using ESMFold (Meta). "
                "Very fast (~5-15s). Max ~400 residues, single chain. Returns PDB with pLDDT "
                "in B-factor column. Use this when user provides a FASTA sequence."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "sequence": {
                        "type": "string",
                        "description": "Amino acid sequence (1-letter codes, max ~400 residues). FASTA headers are stripped.",
                    },
                },
                "required": ["sequence"],
            },
        },
        {
            "name": "lookup_alphafold",
            "description": (
                "Fetch pre-computed AlphaFold structure from EBI database by UniProt ID. "
                "241M+ structures available. Returns PDB content + metadata (pLDDT, organism, gene). "
                "Prefer this over ESMFold when UniProt ID is known."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "uniprot_id": {
                        "type": "string",
                        "description": "UniProt accession ID (e.g., P04637 for human p53)",
                    },
                },
                "required": ["uniprot_id"],
            },
        },
        {
            "name": "predict_variant_effect",
            "description": (
                "Predict the functional impact of a protein mutation using Ensembl VEP. "
                "Returns SIFT score (tolerated/deleterious), PolyPhen (benign/damaging), "
                "consequence type, and colocated known variants. Accepts simple format (R248W) "
                "or HGVS notation."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "gene_or_protein": {
                        "type": "string",
                        "description": "Gene name (TP53) or UniProt ID (P04637)",
                    },
                    "mutation": {
                        "type": "string",
                        "description": "Mutation in simple format (R248W) or HGVS (P04637:p.Arg248Trp)",
                    },
                    "species": {
                        "type": "string",
                        "description": "Species (default: human)",
                        "default": "human",
                    },
                },
                "required": ["gene_or_protein", "mutation"],
            },
        },
        {
            "name": "check_population_frequency",
            "description": (
                "Query gnomAD for gene constraint scores (pLI, o/e ratios) and population "
                "allele frequencies. Reveals if a gene is intolerant to mutations — critical "
                "for clinical variant interpretation. Accepts gene symbol (TP53)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "gene": {
                        "type": "string",
                        "description": "Gene symbol (e.g., TP53, BRCA1, EGFR)",
                    },
                    "variant": {
                        "type": "string",
                        "description": "Optional specific variant (e.g., R248W) to check frequency",
                    },
                },
                "required": ["gene"],
            },
        },
        {
            "name": "get_interaction_network",
            "description": (
                "Query STRING DB for protein-protein interaction network. Returns interaction "
                "partners with confidence scores, experimental evidence, and functional enrichment "
                "(GO terms, KEGG pathways). Species: human by default."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein": {
                        "type": "string",
                        "description": "Protein/gene name (e.g., TP53, EGFR, KRAS)",
                    },
                    "species": {
                        "type": "integer",
                        "description": "NCBI taxonomy ID (default: 9606 for human)",
                        "default": 9606,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max interaction partners to return (default: 15)",
                        "default": 15,
                    },
                },
                "required": ["protein"],
            },
        },
        {
            "name": "classify_domains",
            "description": (
                "Classify protein domains and families using InterPro. Returns domain architecture, "
                "family memberships, active/binding sites, and associated GO terms. Accepts "
                "UniProt ID or gene name."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "UniProt ID (P04637) or gene name (TP53)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "lookup_compound",
            "description": (
                "Look up a drug or chemical compound in PubChem. Returns molecular properties "
                "(weight, formula, LogP, TPSA), Lipinski Rule of Five assessment, and pharmacology "
                "description. Use for drug mechanism questions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Drug/compound name (e.g., imatinib, osimertinib, aspirin)",
                    },
                },
                "required": ["name"],
            },
        },
        {
            "name": "get_pharmacogenomics",
            "description": (
                "Query PharmGKB for pharmacogenomic clinical annotations — drug-gene interactions "
                "with evidence levels. Reveals how genetic variants affect drug response. "
                "Accepts gene name or drug name."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "gene_or_drug": {
                        "type": "string",
                        "description": "Gene name (CYP2D6, TP53) or drug name (imatinib, warfarin)",
                    },
                },
                "required": ["gene_or_drug"],
            },
        },
        {
            "name": "search_literature",
            "description": (
                "Search Semantic Scholar for scientific papers with citation counts. "
                "Returns titles, abstracts, authors, DOIs, and citation metrics. "
                "Results ranked by relevance then sorted by citations."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'TP53 R248W cancer', 'KRAS G12C inhibitors')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max papers to return (default: 10, max: 20)",
                        "default": 10,
                    },
                    "year_min": {
                        "type": "integer",
                        "description": "Only papers from this year onward (e.g., 2023)",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_open_access_literature",
            "description": (
                "Search Europe PMC for open-access biomedical literature. Broader coverage "
                "than PubMed alone, includes preprints and PMC full-text. No auth needed."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'BRCA1 structure function', 'EGFR T790M resistance')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max papers to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "search_pdb_structures",
            "description": (
                "Search RCSB PDB for experimental (X-ray, cryo-EM, NMR) protein structures. "
                "Returns PDB IDs, resolution, method, deposition date, and citation info. "
                "Use to find experimental structures to compare against predictions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Protein/gene name or keyword (e.g., 'TP53 DNA binding domain')",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max structures to return (default: 5)",
                        "default": 5,
                    },
                },
                "required": ["query"],
            },
        },
        # ── Advanced analysis tools ─────────────────────────────────
        {
            "name": "compute_surface_properties",
            "description": (
                "Compute per-residue surface properties: hydrophobicity (Kyte-Doolittle), "
                "charge at pH 7.4, hydrophobic surface patches, charged clusters. "
                "Identifies potential binding and interaction surfaces. Requires loaded PDB."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "predict_ptm_sites",
            "description": (
                "Predict post-translational modification sites from sequence motifs and "
                "structural accessibility: glycosylation (N-X-S/T), phosphorylation, "
                "ubiquitination, disulfide bonds. Returns accessible sites with SASA scores."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "compute_conservation",
            "description": (
                "Compute per-residue conservation scores using amino acid properties, "
                "burial state, and local sequence context. Returns ConSurf-like 1-9 scale "
                "(9=most conserved), highly conserved patches, and variable positions."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "predict_disorder",
            "description": (
                "Predict intrinsically disordered regions by combining amino acid propensity, "
                "sequence complexity, pLDDT confidence, and structural signals. Returns "
                "per-residue disorder scores (>0.5 = disordered) and identified regions."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "compare_structures",
            "description": (
                "Compare predicted structure against an experimental PDB structure. "
                "Computes global RMSD, GDT-TS, TM-score, and per-residue deviations. "
                "Identifies well-modeled and poorly-predicted regions."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "pdb_id": {
                        "type": "string",
                        "description": "RCSB PDB ID of experimental structure to compare (e.g., '1TUP')",
                    },
                },
                "required": ["pdb_id"],
            },
        },
        {
            "name": "auto_investigate",
            "description": (
                "Run comprehensive auto-investigation: executes structure analysis, "
                "surface properties, pocket prediction, PTM analysis, disorder prediction, "
                "conservation, and flexibility in optimal order. Cross-references results "
                "to generate prioritized findings and smart annotations. Best first tool."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        {
            "name": "build_protein_network",
            "description": (
                "Build a Protein Structure Network (PSN) and compute graph metrics. "
                "Reveals allosteric hotspots via betweenness centrality, functional modules "
                "via community detection, and bridge residues (bottleneck communication nodes). "
                "These graph-theoretic insights are invisible in static structure views."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "contact_cutoff": {
                        "type": "number",
                        "description": "Cα distance cutoff for contacts (default 8.0 Å)",
                    },
                },
                "required": [],
            },
        },
        {
            "name": "find_communication_path",
            "description": (
                "Find the shortest structural communication path between two residues "
                "in the protein structure network. Shows how a mutation at one site "
                "propagates through the contact network to affect a distant functional site."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "source_residue": {
                        "type": "integer",
                        "description": "Starting residue number (e.g., mutation site)",
                    },
                    "target_residue": {
                        "type": "integer",
                        "description": "Target residue number (e.g., active site residue)",
                    },
                },
                "required": ["source_residue", "target_residue"],
            },
        },
        {
            "name": "compute_residue_depth",
            "description": (
                "Compute per-residue depth (distance to nearest surface atom). "
                "More informative than binary SASA — reveals continuous burial gradient. "
                "Deep residues are most sensitive to mutations and most conserved."
            ),
            "input_schema": {"type": "object", "properties": {}, "required": []},
        },
        # ── BioRender illustration tools ──────────────────────────────
        {
            "name": "search_biorender_templates",
            "description": (
                "Search BioRender's library of professionally designed figure templates. "
                "Returns template names, descriptions, and clickable URLs for templates "
                "relevant to the protein analysis. Use after discovering significant findings "
                "to suggest publication-quality figure templates."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein_name": {
                        "type": "string",
                        "description": "Protein/gene name for context (e.g., TP53, EGFR)",
                    },
                    "question_type": {
                        "type": "string",
                        "description": "Analysis type: 'druggability', 'mutation_impact', 'binding', or 'structure'",
                        "enum": ["druggability", "mutation_impact", "binding", "structure"],
                    },
                    "mutation": {
                        "type": "string",
                        "description": "Mutation if relevant (e.g., R248W)",
                    },
                },
                "required": ["protein_name", "question_type"],
            },
        },
        {
            "name": "search_biorender_icons",
            "description": (
                "Search BioRender's library of 50,000+ scientific icons by keyword. "
                "Returns icon category links for proteins, receptors, antibodies, enzymes, "
                "drugs, cells, nucleic acids, and lab equipment. Use to suggest visual "
                "assets for figures."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword (e.g., 'kinase receptor', 'antibody', 'DNA repair')",
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "generate_figure_prompt",
            "description": (
                "Generate a ready-to-paste text prompt for BioRender's AI text-to-figure tool. "
                "Creates a specific, detailed prompt that a researcher can copy into BioRender "
                "to generate a publication-quality pathway or mechanism diagram. Use after "
                "completing an analysis to help the researcher create a summary figure."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "protein_name": {
                        "type": "string",
                        "description": "Protein/gene name",
                    },
                    "question_type": {
                        "type": "string",
                        "description": "Analysis type: 'druggability', 'mutation_impact', 'binding', or 'structure'",
                    },
                    "mutation": {
                        "type": "string",
                        "description": "Mutation if relevant",
                    },
                    "key_findings": {
                        "type": "string",
                        "description": "Brief summary of key findings to incorporate into the figure (1-3 sentences)",
                    },
                },
                "required": ["protein_name", "question_type"],
            },
        },
    ]


def execute_tool(tool_name: str, tool_input: dict, session_context: dict) -> str:
    """Execute a tool and return JSON string result."""
    try:
        # Local analysis tools
        if tool_name == "analyze_structure":
            return _exec_analyze_structure(tool_input, session_context)
        elif tool_name == "build_trust_audit":
            return _exec_trust_audit(session_context)
        elif tool_name == "fetch_bio_context":
            return _exec_bio_context(session_context)
        elif tool_name == "search_variants":
            return _exec_variants(session_context)
        elif tool_name == "predict_pockets":
            return _exec_pockets(session_context)
        elif tool_name == "compute_flexibility":
            return _exec_flexibility(session_context)
        elif tool_name == "generate_hypotheses":
            return _exec_hypotheses(session_context)
        # Online database tools
        elif tool_name == "get_protein_info":
            return _exec_protein_info(tool_input)
        elif tool_name == "fold_sequence":
            return _exec_fold_sequence(tool_input, session_context)
        elif tool_name == "lookup_alphafold":
            return _exec_alphafold(tool_input, session_context)
        elif tool_name == "predict_variant_effect":
            return _exec_variant_effect(tool_input)
        elif tool_name == "check_population_frequency":
            return _exec_population_freq(tool_input)
        elif tool_name == "get_interaction_network":
            return _exec_interactions(tool_input)
        elif tool_name == "classify_domains":
            return _exec_domains(tool_input)
        elif tool_name == "lookup_compound":
            return _exec_compound(tool_input)
        elif tool_name == "get_pharmacogenomics":
            return _exec_pharmacogenomics(tool_input)
        elif tool_name == "search_literature":
            return _exec_literature(tool_input)
        elif tool_name == "search_open_access_literature":
            return _exec_europe_pmc(tool_input)
        elif tool_name == "search_pdb_structures":
            return _exec_pdb_search(tool_input)
        # Advanced analysis tools
        elif tool_name == "compute_surface_properties":
            return _exec_surface_properties(session_context)
        elif tool_name == "predict_ptm_sites":
            return _exec_ptm_sites(session_context)
        elif tool_name == "compute_conservation":
            return _exec_conservation(session_context)
        elif tool_name == "predict_disorder":
            return _exec_disorder(session_context)
        elif tool_name == "compare_structures":
            return _exec_compare_structures(tool_input, session_context)
        elif tool_name == "auto_investigate":
            return _exec_auto_investigate(session_context)
        # PSN and depth tools
        elif tool_name == "build_protein_network":
            return _exec_protein_network(session_context, tool_input)
        elif tool_name == "find_communication_path":
            return _exec_communication_path(session_context, tool_input)
        elif tool_name == "compute_residue_depth":
            return _exec_residue_depth(session_context)
        # BioRender illustration tools
        elif tool_name == "search_biorender_templates":
            return _exec_biorender_templates(tool_input)
        elif tool_name == "search_biorender_icons":
            return _exec_biorender_icons(tool_input)
        elif tool_name == "generate_figure_prompt":
            return _exec_figure_prompt(tool_input)
        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Local analysis tool executors ─────────────────────────────────────

def _exec_analyze_structure(tool_input: dict, ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})

    from src.structure_analysis import analyze_structure

    mutation_pos = tool_input.get("mutation_pos") or ctx.get("mutation_pos")
    result = analyze_structure(pdb, mutation_pos=mutation_pos)

    # Filter out large arrays for concise output
    summary = {k: v for k, v in result.items()
               if not isinstance(v, (list,)) or len(v) < 20}
    summary["n_residues"] = len(result.get("residue_ids", []))
    if "contact_map" in result:
        summary["contact_map"] = f"[{result['contact_map'].shape} matrix]"
    return safe_json_dumps(summary)


def _exec_trust_audit(ctx: dict) -> str:
    trust = ctx.get("trust_audit")
    if trust:
        return safe_json_dumps(trust.model_dump())

    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})

    from src.models import ProteinQuery
    from src.trust_auditor import build_trust_audit

    query = ctx.get("query") or ProteinQuery(
        protein_name=ctx.get("protein_name", "unknown"),
        question_type="structure",
    )
    confidence = ctx.get("confidence_json", {})
    audit = build_trust_audit(query, pdb, confidence)
    return safe_json_dumps(audit.model_dump())


def _exec_bio_context(ctx: dict) -> str:
    bio = ctx.get("bio_context")
    if bio:
        return safe_json_dumps(bio.model_dump())

    from src.models import ProteinQuery

    query = ctx.get("query") or ProteinQuery(
        protein_name=ctx.get("protein_name", "unknown"),
        question_type="structure",
    )

    # Try MCP connector first (includes Wiley Scholar Gateway)
    try:
        from src.bio_context import fetch_bio_context_mcp
        bio = fetch_bio_context_mcp(query)
        if bio.narrative or bio.disease_associations or bio.drugs:
            return safe_json_dumps(bio.model_dump())
    except Exception:
        pass

    # Fallback to BioMCP direct
    try:
        from src.bio_context_direct import fetch_bio_context_direct
        bio = fetch_bio_context_direct(query)
        return safe_json_dumps(bio.model_dump())
    except Exception as e:
        return json.dumps({"error": f"Bio context fetch failed: {e}"})


def _exec_variants(ctx: dict) -> str:
    variant_data = ctx.get("variant_data")
    if variant_data:
        return safe_json_dumps(variant_data)
    return json.dumps({"note": "No variant data loaded. Run analysis from Structure tab first."})


def _exec_pockets(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})

    from src.pocket_prediction import predict_pockets
    result = predict_pockets(pdb)
    # Trim large residue score maps
    result["residue_pocket_scores"] = dict(
        sorted(result["residue_pocket_scores"].items(), key=lambda x: -x[1])[:20]
    )
    return safe_json_dumps(result)


def _exec_flexibility(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})

    from src.flexibility_analysis import compute_anm_flexibility
    result = compute_anm_flexibility(pdb)
    # Summarize — don't send full arrays
    return json.dumps({
        "n_residues": len(result["residue_ids"]),
        "pct_rigid": f"{result['pct_rigid']:.0%}",
        "pct_flexible": f"{result['pct_flexible']:.0%}",
        "n_hinge_residues": len(result["hinge_residues"]),
        "hinge_residues": result["hinge_residues"][:10],
        "flexible_residues": result["flexible_residues"][:15],
        "rigid_residues": result["rigid_residues"][:15],
    }, default=str)


def _exec_hypotheses(ctx: dict) -> str:
    query = ctx.get("query")
    trust = ctx.get("trust_audit")
    bio = ctx.get("bio_context")

    if not query or not trust or not bio:
        return json.dumps({"error": "Need query + trust audit + bio context to generate hypotheses"})

    try:
        from src.hypothesis_engine import generate_hypotheses
        hypotheses = generate_hypotheses(query, trust, bio)
        return hypotheses if isinstance(hypotheses, str) else safe_json_dumps(hypotheses)
    except Exception as e:
        return json.dumps({"error": f"Hypothesis generation failed: {e}"})


# ── Online database tool executors ────────────────────────────────────

def _exec_protein_info(tool_input: dict) -> str:
    from src.online_tools import get_protein_info
    result = get_protein_info(tool_input.get("query", ""))
    return safe_json_dumps(result)


def _exec_fold_sequence(tool_input: dict, ctx: dict | None = None) -> str:
    from src.online_tools import fold_sequence
    result = fold_sequence(tool_input.get("sequence", ""))
    # Don't send full PDB text to Claude — just the summary
    if "pdb_content" in result and "error" not in result:
        pdb_text = result.pop("pdb_content")
        result["pdb_available"] = True
        result["pdb_length_bytes"] = len(pdb_text)
        # Store in module-level cache and session context for downstream tools
        _fold_cache["last_pdb"] = pdb_text
        if ctx is not None:
            ctx["pdb_content"] = pdb_text
    return safe_json_dumps(result)


def _exec_alphafold(tool_input: dict, ctx: dict | None = None) -> str:
    from src.online_tools import lookup_alphafold
    result = lookup_alphafold(tool_input.get("uniprot_id", ""))
    if "pdb_content" in result and "error" not in result:
        pdb_text = result.pop("pdb_content")
        result["pdb_available"] = True
        result["pdb_length_bytes"] = len(pdb_text)
        _fold_cache["last_pdb"] = pdb_text
        _fold_cache["last_uniprot"] = tool_input.get("uniprot_id", "")
        if ctx is not None:
            ctx["pdb_content"] = pdb_text
    return safe_json_dumps(result)


def _exec_variant_effect(tool_input: dict) -> str:
    from src.online_tools import predict_variant_effect
    result = predict_variant_effect(
        gene_or_protein=tool_input.get("gene_or_protein", ""),
        mutation=tool_input.get("mutation", ""),
        species=tool_input.get("species", "human"),
    )
    return safe_json_dumps(result)


def _exec_population_freq(tool_input: dict) -> str:
    from src.online_tools import check_population_frequency
    result = check_population_frequency(
        gene=tool_input.get("gene", ""),
        variant=tool_input.get("variant"),
    )
    return safe_json_dumps(result)


def _exec_interactions(tool_input: dict) -> str:
    from src.online_tools import get_interaction_network
    result = get_interaction_network(
        protein=tool_input.get("protein", ""),
        species=tool_input.get("species", 9606),
        limit=tool_input.get("limit", 15),
    )
    return safe_json_dumps(result)


def _exec_domains(tool_input: dict) -> str:
    from src.online_tools import classify_domains
    result = classify_domains(tool_input.get("query", ""))
    return safe_json_dumps(result)


def _exec_compound(tool_input: dict) -> str:
    from src.online_tools import lookup_compound
    result = lookup_compound(tool_input.get("name", ""))
    return safe_json_dumps(result)


def _exec_pharmacogenomics(tool_input: dict) -> str:
    from src.online_tools import get_pharmacogenomics
    result = get_pharmacogenomics(tool_input.get("gene_or_drug", ""))
    return safe_json_dumps(result)


def _exec_literature(tool_input: dict) -> str:
    from src.online_tools import search_literature
    result = search_literature(
        query=tool_input.get("query", ""),
        limit=tool_input.get("limit", 10),
        year_min=tool_input.get("year_min"),
    )
    return safe_json_dumps(result)


def _exec_europe_pmc(tool_input: dict) -> str:
    from src.online_tools import search_europe_pmc
    result = search_europe_pmc(
        query=tool_input.get("query", ""),
        limit=tool_input.get("limit", 10),
    )
    return safe_json_dumps(result)


def _exec_pdb_search(tool_input: dict) -> str:
    from src.online_tools import search_pdb_structures
    result = search_pdb_structures(
        query=tool_input.get("query", ""),
        limit=tool_input.get("limit", 5),
    )
    return safe_json_dumps(result)


# ── Advanced analysis tool executors ──────────────────────────────────

def _exec_surface_properties(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.surface_properties import compute_surface_properties
    result = compute_surface_properties(pdb)
    # Trim large per-residue dicts for conciseness
    summary = result.get("summary", {})
    summary["hydrophobic_patches"] = result.get("hydrophobic_patches", [])
    summary["positive_patches"] = result.get("positive_patches", [])
    summary["negative_patches"] = result.get("negative_patches", [])
    return safe_json_dumps(summary)


def _exec_ptm_sites(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.ptm_analysis import predict_ptm_sites
    result = predict_ptm_sites(pdb)
    # Return accessible sites + summary (trim full list)
    output = result.get("summary", {})
    output["accessible_sites"] = result.get("accessible_sites", [])[:15]
    return safe_json_dumps(output)


def _exec_conservation(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.conservation import compute_conservation_scores
    result = compute_conservation_scores(pdb)
    summary = result.get("summary", {})
    summary["conserved_patches"] = result.get("conserved_patches", [])
    summary["method"] = result.get("method", "")
    return safe_json_dumps(summary)


def _exec_disorder(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    plddt = ctx.get("plddt_scores")
    from src.disorder_prediction import predict_disorder
    result = predict_disorder(pdb, plddt)
    summary = result.get("summary", {})
    summary["disordered_regions"] = result.get("disordered_regions", [])
    summary["method"] = result.get("method", "")
    return safe_json_dumps(summary)


def _exec_compare_structures(tool_input: dict, ctx: dict) -> str:
    pdb_content = ctx.get("pdb_content", "")
    if not pdb_content:
        return json.dumps({"error": "No predicted PDB loaded"})
    pdb_id = tool_input.get("pdb_id", "")
    if not pdb_id:
        return json.dumps({"error": "pdb_id required"})
    from src.structure_comparison import fetch_experimental_pdb, compare_structures
    exp_pdb = fetch_experimental_pdb(pdb_id)
    if not exp_pdb:
        return json.dumps({"error": f"Could not fetch PDB {pdb_id}"})
    result = compare_structures(pdb_content, exp_pdb)
    # Trim per-residue RMSD to top deviations only
    if "per_residue_rmsd" in result:
        sorted_res = sorted(result["per_residue_rmsd"].items(), key=lambda x: -x[1])
        result["worst_residues"] = [{"residue": int(r), "rmsd": v} for r, v in sorted_res[:15]]
        del result["per_residue_rmsd"]
    return safe_json_dumps(result)


def _exec_auto_investigate(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.auto_investigation import auto_investigate
    query = ctx.get("query")
    protein_name = query.protein_name if query else ctx.get("protein_name", "unknown")
    mutation = query.mutation if query else None
    plddt = ctx.get("plddt_scores")
    result = auto_investigate(pdb, protein_name, mutation, plddt)
    return safe_json_dumps({
        "summary": result.summary,
        "findings": result.findings,
        "risk_flags": result.risk_flags,
        "annotations": result.annotations[:10],
        "recommendations": result.recommendations,
        "analyses_run": result.analyses_run,
    })


def _exec_protein_network(ctx: dict, tool_input: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.protein_network import build_protein_network
    cutoff = tool_input.get("contact_cutoff", 8.0)
    data = build_protein_network(pdb, contact_cutoff=cutoff)
    # Trim for conciseness
    return safe_json_dumps({
        "graph_stats": data.get("graph_stats"),
        "communities": data.get("communities", [])[:10],
        "hub_residues": data.get("hub_residues", [])[:10],
        "bridge_residues": data.get("bridge_residues", [])[:10],
        "summary": data.get("summary"),
    })


def _exec_communication_path(ctx: dict, tool_input: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.protein_network import find_communication_path
    source = tool_input.get("source_residue")
    target = tool_input.get("target_residue")
    if source is None or target is None:
        return json.dumps({"error": "source_residue and target_residue required"})
    return safe_json_dumps(find_communication_path(pdb, source, target))


def _exec_residue_depth(ctx: dict) -> str:
    pdb = ctx.get("pdb_content", "")
    if not pdb:
        return json.dumps({"error": "No PDB loaded"})
    from src.residue_depth import compute_residue_depth
    data = compute_residue_depth(pdb)
    return safe_json_dumps({
        "summary": data.get("summary"),
        "deep_core": data.get("deep_core", [])[:20],
        "intermediate_count": len(data.get("intermediate", [])),
        "surface_count": len(data.get("surface", [])),
    })


# ── BioRender illustration tool executors ─────────────────────────────

def _exec_biorender_templates(tool_input: dict) -> str:
    from src.biorender_search import search_biorender_templates
    results = search_biorender_templates(
        protein_name=tool_input.get("protein_name", ""),
        mutation=tool_input.get("mutation"),
        question_type=tool_input.get("question_type", "structure"),
    )
    return safe_json_dumps(results)


def _exec_biorender_icons(tool_input: dict) -> str:
    query = tool_input.get("query", "").strip()
    from src.biorender_search import _ICON_CATEGORIES, _ICON_SEARCH
    results = []
    query_lower = query.lower()

    # Keyword → category mapping for smarter matching
    keyword_map = {
        "protein": "proteins", "receptor": "receptors", "ligand": "receptors",
        "antibody": "antibodies", "enzyme": "enzymes", "kinase": "enzymes",
        "transporter": "transporters", "channel": "transporters",
        "drug": "chemistry", "molecule": "chemistry", "compound": "chemistry",
        "cell": "cell_types", "neuron": "cell_types", "immune": "cell_types",
        "dna": "nucleic_acids", "rna": "nucleic_acids", "gene": "nucleic_acids",
    }

    matched_cats = set()
    for word in query_lower.split():
        cat = keyword_map.get(word)
        if cat and cat not in matched_cats:
            matched_cats.add(cat)
            results.append({
                "category": cat,
                "url": _ICON_CATEGORIES.get(cat, ""),
                "type": "icon_category",
                "description": f"BioRender {cat.replace('_', ' ')} icon library",
            })

    # Also check direct category name matches
    for cat_name, cat_url in _ICON_CATEGORIES.items():
        if cat_name not in matched_cats and cat_name in query_lower:
            results.append({
                "category": cat_name,
                "url": cat_url,
                "type": "icon_category",
            })

    # Always add direct search link
    results.append({
        "name": f"Search: {query}",
        "url": f"{_ICON_SEARCH}{query.replace(' ', '+')}",
        "type": "icon_search",
        "description": f"Browse all BioRender icons matching '{query}'",
    })
    return safe_json_dumps(results)


def _exec_figure_prompt(tool_input: dict) -> str:
    from src.biorender_search import generate_figure_prompt
    prompt = generate_figure_prompt(
        protein_name=tool_input.get("protein_name", ""),
        mutation=tool_input.get("mutation"),
        question_type=tool_input.get("question_type", "structure"),
        interpretation=tool_input.get("key_findings"),
    )
    if prompt:
        return safe_json_dumps({
            "figure_prompt": prompt,
            "instructions": "Copy this prompt and paste it into BioRender's AI text-to-figure tool at biorender.com",
            "biorender_url": "https://www.biorender.com",
        })
    return json.dumps({"error": "Could not generate figure prompt"})


# ── Shared state ──────────────────────────────────────────────────────

# Cache for PDB content from fold/alphafold so UI can retrieve it
_fold_cache: dict[str, str] = {}


def get_last_folded_pdb() -> str | None:
    """Retrieve last PDB from fold_sequence or lookup_alphafold."""
    return _fold_cache.get("last_pdb")


def get_tool_schemas() -> list[dict]:
    """Return tool schemas for display in UI."""
    return [
        {"name": t["name"], "description": t["description"]}
        for t in _make_tools()
    ]


def run_agent_turn(
    messages: list[dict],
    session_context: dict,
) -> tuple[str, list[dict]]:
    """Run one agent turn: send messages, handle tool calls, return response.

    Returns (assistant_text, tool_calls_made) where tool_calls_made is a list
    of {"tool": name, "input": {...}, "output": "..."} dicts.
    """
    if not ANTHROPIC_API_KEY:
        return "Agent mode requires an Anthropic API key.", []

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    tools = _make_tools()

    tool_defs = tools  # Already in Anthropic API format

    # Initial call
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=4096,
            system=AGENT_SYSTEM_PROMPT,
            messages=messages,
            tools=tool_defs,
        )
    except Exception as e:
        err = str(e)
        if "credit balance" in err.lower() or "billing" in err.lower():
            return ("Anthropic API credits exhausted. "
                    "Please add credits at console.anthropic.com."), []
        raise

    tool_calls_made = []
    max_iterations = 15  # 28 tools — allow longer chains for comprehensive analysis

    while response.stop_reason == "tool_use" and max_iterations > 0:
        max_iterations -= 1

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                output = execute_tool(block.name, block.input, session_context)
                tool_calls_made.append({
                    "tool": block.name,
                    "input": block.input,
                    "output": output[:800],  # Increased truncation for richer tools
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })

        # Continue conversation with tool results
        messages = messages + [
            {"role": "assistant", "content": response.content},
            {"role": "user", "content": tool_results},
        ]

        try:
            response = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=4096,
                system=AGENT_SYSTEM_PROMPT,
                messages=messages,
                tools=tool_defs,
            )
        except Exception as e:
            err = str(e)
            if "credit balance" in err.lower() or "billing" in err.lower():
                return ("Anthropic API credits exhausted. "
                        "Please add credits at console.anthropic.com."), tool_calls_made
            raise

    # Extract final text
    text_parts = [b.text for b in response.content if hasattr(b, "text")]
    return "\n".join(text_parts), tool_calls_made
