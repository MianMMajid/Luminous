"""Online bioinformatics API integrations for Lumi agent.

All functions are synchronous (using httpx) and return JSON-serializable dicts.
Every function handles its own errors and returns {"error": ...} on failure.
"""
from __future__ import annotations

import json
import time

import httpx

# Shared client with sensible timeouts and connection pooling
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_HEADERS = {"Accept": "application/json", "User-Agent": "Luminous/1.0 (BioVista)"}
_sync_client: httpx.Client | None = None


def _get_sync_client() -> httpx.Client:
    """Return a shared sync httpx client with connection pooling."""
    global _sync_client
    if _sync_client is None or _sync_client.is_closed:
        _sync_client = httpx.Client(
            timeout=_TIMEOUT,
            follow_redirects=True,
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return _sync_client


def _get(url: str, params: dict | None = None, headers: dict | None = None) -> dict | list | str:
    """GET request with error handling."""
    hdrs = {**_HEADERS, **(headers or {})}
    client = _get_sync_client()
    resp = client.get(url, params=params, headers=hdrs)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        return resp.json()
    return resp.text


def _post(url: str, json_body: dict | None = None, data: str | None = None,
          headers: dict | None = None, content_type: str | None = None) -> dict | list | str:
    """POST request with error handling."""
    hdrs = {**_HEADERS, **(headers or {})}
    if content_type:
        hdrs["Content-Type"] = content_type
    client = _get_sync_client()
    if json_body is not None:
        resp = client.post(url, json=json_body, headers=hdrs)
    elif data is not None:
        resp = client.post(url, content=data, headers=hdrs)
    else:
        resp = client.post(url, headers=hdrs)
    resp.raise_for_status()
    ct = resp.headers.get("content-type", "")
    if "json" in ct:
        return resp.json()
    return resp.text


# ──────────────────────────────────────────────────────────────────────
# 1. ESMFold — Sequence → Structure (instant, no auth)
# ──────────────────────────────────────────────────────────────────────

def fold_sequence(sequence: str) -> dict:
    """Fold a protein sequence using ESMFold (Meta). Returns PDB string.

    Max ~400 residues, single chain. Very fast (~5-15s).
    Endpoint: POST https://api.esmatlas.com/foldSequence/v1/pdb/
    """
    try:
        sequence = sequence.strip().replace("\n", "").replace(" ", "")
        # Remove FASTA header if present
        if sequence.startswith(">"):
            lines = sequence.split("\n") if "\n" in sequence else sequence.split(">")
            sequence = "".join(l for l in lines if not l.startswith(">"))
            sequence = sequence.strip().replace("\n", "").replace(" ", "")

        if len(sequence) > 400:
            return {
                "error": f"Sequence too long ({len(sequence)} residues). ESMFold API limit is ~400. "
                         "Consider using Boltz-2 via Tamarind Bio for longer sequences."
            }
        if len(sequence) < 10:
            return {"error": f"Sequence too short ({len(sequence)} residues). Minimum ~10 required."}

        # Validate amino acid alphabet
        valid_aa = set("ACDEFGHIKLMNPQRSTVWY")
        invalid = set(sequence.upper()) - valid_aa
        if invalid:
            return {"error": f"Invalid amino acid characters: {invalid}. Use standard 1-letter codes."}

        pdb_text = _post(
            "https://api.esmatlas.com/foldSequence/v1/pdb/",
            data=sequence,
            content_type="text/plain",
        )
        if not isinstance(pdb_text, str) or "ATOM" not in pdb_text:
            return {"error": "ESMFold returned unexpected response. Service may be down."}

        # Count residues and extract pLDDT from B-factor
        atom_lines = [l for l in pdb_text.split("\n") if l.startswith("ATOM") and l[12:16].strip() == "CA"]
        n_residues = len(atom_lines)
        plddt_values = []
        for line in atom_lines:
            try:
                plddt_values.append(float(line[60:66].strip()))
            except (ValueError, IndexError):
                pass

        avg_plddt = sum(plddt_values) / len(plddt_values) if plddt_values else 0
        low_conf = sum(1 for p in plddt_values if p < 70)

        return {
            "pdb_content": pdb_text,
            "n_residues": n_residues,
            "avg_plddt": round(avg_plddt, 1),
            "low_confidence_residues": low_conf,
            "pct_confident": round((n_residues - low_conf) / max(n_residues, 1) * 100, 1),
            "source": "ESMFold (Meta)",
            "note": "pLDDT scores in B-factor column. Use trust audit for detailed analysis.",
        }
    except httpx.HTTPStatusError as e:
        return {"error": f"ESMFold API error (HTTP {e.response.status_code}). Service may be busy."}
    except Exception as e:
        return {"error": f"ESMFold folding failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 2. AlphaFold DB — Pre-computed structure lookup by UniProt ID
# ──────────────────────────────────────────────────────────────────────

def lookup_alphafold(uniprot_id: str) -> dict:
    """Fetch pre-computed AlphaFold structure by UniProt ID.

    Returns PDB content + metadata. 241M+ structures available.
    """
    try:
        uniprot_id = uniprot_id.strip().upper()

        # Get metadata
        meta = _get(f"https://alphafold.ebi.ac.uk/api/prediction/{uniprot_id}")
        if isinstance(meta, list) and len(meta) > 0:
            meta = meta[0]
        elif isinstance(meta, list):
            return {"error": f"No AlphaFold prediction found for {uniprot_id}"}

        # Download PDB
        pdb_url = meta.get("pdbUrl", "")
        if not pdb_url:
            return {"error": f"No PDB URL in AlphaFold response for {uniprot_id}"}

        pdb_text = _get(pdb_url, headers={"Accept": "text/plain"})
        if not isinstance(pdb_text, str) or "ATOM" not in pdb_text:
            return {"error": "Failed to download PDB from AlphaFold DB"}

        return {
            "pdb_content": pdb_text,
            "uniprot_id": uniprot_id,
            "gene": meta.get("gene", ""),
            "organism": meta.get("organismScientificName", ""),
            "model_version": meta.get("latestVersion", ""),
            "global_plddt": meta.get("globalMetricValue"),
            "source": "AlphaFold DB (EBI/DeepMind)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"No AlphaFold prediction found for UniProt ID '{uniprot_id}'. "
                             "Check the ID or try RCSB PDB for experimental structures."}
        return {"error": f"AlphaFold API error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"AlphaFold lookup failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 3. UniProt — Comprehensive protein annotation
# ──────────────────────────────────────────────────────────────────────

def get_protein_info(query: str) -> dict:
    """Fetch comprehensive protein info from UniProt.

    Accepts UniProt ID (P04637) or gene name (TP53).
    Returns function, domains, GO terms, subcellular location, etc.
    """
    try:
        query = query.strip()

        # If it looks like a gene name, search for it first
        if not (len(query) == 6 and query[0].isalpha() and query[1:].isalnum()):
            # Search UniProt
            search_url = "https://rest.uniprot.org/uniprotkb/search"
            results = _get(search_url, params={
                "query": f"(gene:{query}) AND (reviewed:true) AND (organism_id:9606)",
                "format": "json",
                "size": "1",
                "fields": "accession",
            })
            entries = results.get("results", []) if isinstance(results, dict) else []
            if not entries:
                # Try broader search (any organism)
                results = _get(search_url, params={
                    "query": f"(gene:{query}) AND (reviewed:true)",
                    "format": "json",
                    "size": "1",
                    "fields": "accession",
                })
                entries = results.get("results", []) if isinstance(results, dict) else []
            if not entries:
                return {"error": f"No UniProt entry found for '{query}'. Try a UniProt ID directly."}
            uniprot_id = entries[0].get("primaryAccession", query)
        else:
            uniprot_id = query

        # Fetch full entry
        data = _get(f"https://rest.uniprot.org/uniprotkb/{uniprot_id}.json")
        if not isinstance(data, dict):
            return {"error": "Unexpected UniProt response format"}

        # Extract key information
        protein_desc = data.get("proteinDescription", {})
        rec_name = protein_desc.get("recommendedName", {})
        full_name = rec_name.get("fullName", {}).get("value", "Unknown")

        gene_names = []
        for g in data.get("genes", []):
            if "geneName" in g:
                gene_names.append(g["geneName"]["value"])

        # Function
        function_text = ""
        for comment in data.get("comments", []):
            if comment.get("commentType") == "FUNCTION":
                for txt in comment.get("texts", []):
                    function_text += txt.get("value", "") + " "

        # Subcellular location
        locations = []
        for comment in data.get("comments", []):
            if comment.get("commentType") == "SUBCELLULAR LOCATION":
                for subloc in comment.get("subcellularLocations", []):
                    loc = subloc.get("location", {}).get("value", "")
                    if loc:
                        locations.append(loc)

        # Domains / features
        domains = []
        active_sites = []
        binding_sites = []
        for feat in data.get("features", []):
            ftype = feat.get("type", "")
            desc = feat.get("description", "")
            loc = feat.get("location", {})
            start = loc.get("start", {}).get("value", "?")
            end = loc.get("end", {}).get("value", "?")
            entry = f"{desc} ({start}-{end})" if desc else f"{ftype} ({start}-{end})"

            if ftype == "Domain":
                domains.append(entry)
            elif ftype == "Active site":
                active_sites.append(entry)
            elif ftype == "Binding site":
                binding_sites.append(entry)

        # GO terms
        go_terms = {"molecular_function": [], "biological_process": [], "cellular_component": []}
        for xref in data.get("uniProtKBCrossReferences", []):
            if xref.get("database") == "GO":
                go_id = xref.get("id", "")
                props = {p["key"]: p["value"] for p in xref.get("properties", [])}
                term = props.get("GoTerm", "")
                if term.startswith("F:"):
                    go_terms["molecular_function"].append(term[2:])
                elif term.startswith("P:"):
                    go_terms["biological_process"].append(term[2:])
                elif term.startswith("C:"):
                    go_terms["cellular_component"].append(term[2:])

        # PDB cross-references (experimental structures)
        pdb_ids = []
        for xref in data.get("uniProtKBCrossReferences", []):
            if xref.get("database") == "PDB":
                pdb_ids.append(xref.get("id", ""))

        # Disease associations
        diseases = []
        for comment in data.get("comments", []):
            if comment.get("commentType") == "DISEASE":
                disease = comment.get("disease", {})
                if disease:
                    diseases.append({
                        "name": disease.get("diseaseId", ""),
                        "description": disease.get("description", "")[:200],
                        "mim": disease.get("diseaseCrossReference", {}).get("id", ""),
                    })

        # Sequence info
        seq_data = data.get("sequence", {})
        length = seq_data.get("length", 0)
        mass = seq_data.get("molWeight", 0)
        sequence = seq_data.get("value", "")

        organism = data.get("organism", {}).get("scientificName", "")

        return {
            "uniprot_id": uniprot_id,
            "protein_name": full_name,
            "gene_names": gene_names,
            "organism": organism,
            "function": function_text.strip()[:500],
            "subcellular_location": locations[:5],
            "domains": domains[:10],
            "active_sites": active_sites[:5],
            "binding_sites": binding_sites[:10],
            "go_molecular_function": go_terms["molecular_function"][:8],
            "go_biological_process": go_terms["biological_process"][:8],
            "go_cellular_component": go_terms["cellular_component"][:5],
            "known_pdb_structures": pdb_ids[:10],
            "diseases": diseases[:5],
            "sequence_length": length,
            "molecular_weight_da": mass,
            "sequence": sequence[:100] + "..." if len(sequence) > 100 else sequence,
            "source": "UniProt (Swiss-Prot reviewed)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"UniProt entry not found for '{query}'."}
        return {"error": f"UniProt API error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"UniProt lookup failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 4. Ensembl VEP — Variant Effect Prediction
# ──────────────────────────────────────────────────────────────────────

def predict_variant_effect(
    gene_or_protein: str,
    mutation: str,
    species: str = "human",
) -> dict:
    """Predict functional effect of a mutation using Ensembl VEP.

    Accepts HGVS notation or simple format (e.g., "R248W" on TP53).
    Returns SIFT, PolyPhen, consequence type, etc.
    """
    try:
        mutation = mutation.strip()
        gene_or_protein = gene_or_protein.strip()

        # Build HGVS protein notation if simple format given (e.g., R248W)
        import re
        simple_match = re.match(r"^([A-Z])(\d+)([A-Z])$", mutation)

        if simple_match:
            # First, get the Ensembl gene/transcript ID via UniProt
            info = get_protein_info(gene_or_protein)
            uniprot_id = info.get("uniprot_id", gene_or_protein)

            # Use HGVS protein notation: ENSP or UniProt:p.Arg248Trp
            aa_map = {
                "A": "Ala", "C": "Cys", "D": "Asp", "E": "Glu", "F": "Phe",
                "G": "Gly", "H": "His", "I": "Ile", "K": "Lys", "L": "Leu",
                "M": "Met", "N": "Asn", "P": "Pro", "Q": "Gln", "R": "Arg",
                "S": "Ser", "T": "Thr", "V": "Val", "W": "Trp", "Y": "Tyr",
            }
            ref = aa_map.get(simple_match.group(1), simple_match.group(1))
            pos = simple_match.group(2)
            alt = aa_map.get(simple_match.group(3), simple_match.group(3))
            hgvs = f"{uniprot_id}:p.{ref}{pos}{alt}"
        else:
            hgvs = mutation

        # Call Ensembl VEP HGVS endpoint
        url = f"https://rest.ensembl.org/vep/{species}/hgvs/{hgvs}"
        result = _get(url, headers={"Content-Type": "application/json"})

        if isinstance(result, list) and len(result) > 0:
            vep = result[0]
        elif isinstance(result, dict):
            if "error" in result:
                return {"error": f"Ensembl VEP: {result['error']}"}
            vep = result
        else:
            return {"error": "No VEP results returned"}

        # Extract transcript consequences
        consequences = []
        for tc in vep.get("transcript_consequences", [])[:5]:
            cons = {
                "gene_symbol": tc.get("gene_symbol", ""),
                "transcript_id": tc.get("transcript_id", ""),
                "consequence": ", ".join(tc.get("consequence_terms", [])),
                "impact": tc.get("impact", ""),
                "biotype": tc.get("biotype", ""),
                "amino_acids": tc.get("amino_acids", ""),
                "protein_position": tc.get("protein_start"),
            }
            # SIFT
            if "sift_prediction" in tc:
                cons["sift"] = f"{tc['sift_prediction']} ({tc.get('sift_score', '?')})"
            # PolyPhen
            if "polyphen_prediction" in tc:
                cons["polyphen"] = f"{tc['polyphen_prediction']} ({tc.get('polyphen_score', '?')})"
            consequences.append(cons)

        return {
            "query": hgvs,
            "most_severe_consequence": vep.get("most_severe_consequence", ""),
            "transcript_consequences": consequences,
            "colocated_variants": [
                {
                    "id": cv.get("id", ""),
                    "frequencies": {
                        k: v for k, v in cv.get("frequencies", {}).items()
                    } if cv.get("frequencies") else None,
                }
                for cv in vep.get("colocated_variants", [])[:3]
            ],
            "source": "Ensembl VEP (GRCh38)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 400:
            return {"error": f"Invalid variant notation '{mutation}'. Use format like R248W or HGVS notation."}
        return {"error": f"Ensembl VEP error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"Variant effect prediction failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 5. gnomAD — Population allele frequencies (via GraphQL)
# ──────────────────────────────────────────────────────────────────────

def check_population_frequency(gene: str, variant: str | None = None) -> dict:
    """Query gnomAD for population allele frequencies and constraint scores.

    If variant given (e.g., R248W), finds specific variant frequency.
    If only gene given, returns constraint scores (pLI, LOEUF, missense Z).
    """
    try:
        gene = gene.strip().upper()

        # Always get gene constraint scores
        constraint_query = """
        query GeneConstraint($gene: String!) {
          gene(gene_symbol: $gene, reference_genome: GRCh38) {
            gene_id
            symbol
            gnomad_constraint {
              pLI
              oe_lof
              oe_lof_upper
              oe_mis
              oe_mis_upper
              exp_lof
              obs_lof
              exp_mis
              obs_mis
            }
          }
        }
        """
        result = _post(
            "https://gnomad.broadinstitute.org/api",
            json_body={"query": constraint_query, "variables": {"gene": gene}},
        )

        gene_data = result.get("data", {}).get("gene") if isinstance(result, dict) else None
        if not gene_data:
            return {"error": f"Gene '{gene}' not found in gnomAD. Check the gene symbol."}

        constraint = gene_data.get("gnomad_constraint", {}) or {}
        output: dict = {
            "gene": gene_data.get("symbol", gene),
            "gene_id": gene_data.get("gene_id", ""),
            "constraint": {
                "pLI": constraint.get("pLI"),
                "oe_lof": constraint.get("oe_lof"),
                "oe_lof_upper": constraint.get("oe_lof_upper"),
                "oe_mis": constraint.get("oe_mis"),
                "oe_mis_upper": constraint.get("oe_mis_upper"),
            },
            "interpretation": _interpret_constraint(constraint),
        }

        # If variant specified, search for it
        if variant:
            import re
            m = re.match(r"^([A-Z])(\d+)([A-Z])$", variant.strip())
            if m:
                pos = int(m.group(2))
                # Search for variants at this position in the gene
                variant_query = """
                query GeneVariants($gene: String!) {
                  gene(gene_symbol: $gene, reference_genome: GRCh38) {
                    variants(dataset: gnomad_r4) {
                      variant_id
                      pos
                      consequence
                      hgvsp
                      exome {
                        ac
                        an
                        af
                        homozygote_count
                      }
                      genome {
                        ac
                        an
                        af
                        homozygote_count
                      }
                    }
                  }
                }
                """
                # This query can be very large. gnomAD recommends using their
                # variant search instead. Try the simpler approach via REST-like search.
                output["variant_query"] = variant
                output["note"] = (
                    f"For specific variant {variant} frequencies, check gnomAD browser directly. "
                    "Gene-level constraint scores above indicate overall intolerance to mutations."
                )

        output["source"] = "gnomAD v4 (Broad Institute)"
        return output
    except Exception as e:
        return {"error": f"gnomAD query failed: {e}"}


def _interpret_constraint(c: dict) -> str:
    """Human-readable interpretation of gnomAD constraint scores."""
    parts = []
    pli = c.get("pLI")
    if pli is not None:
        if pli > 0.9:
            parts.append(f"Highly intolerant to loss-of-function (pLI={pli:.2f})")
        elif pli > 0.5:
            parts.append(f"Moderately intolerant to LoF (pLI={pli:.2f})")
        else:
            parts.append(f"Tolerant to loss-of-function (pLI={pli:.2f})")

    oe_mis = c.get("oe_mis")
    if oe_mis is not None:
        if oe_mis < 0.6:
            parts.append(f"Constrained against missense (o/e={oe_mis:.2f})")
        elif oe_mis < 0.8:
            parts.append(f"Moderately constrained for missense (o/e={oe_mis:.2f})")
        else:
            parts.append(f"Tolerant to missense (o/e={oe_mis:.2f})")

    return "; ".join(parts) if parts else "Constraint scores not available"


# ──────────────────────────────────────────────────────────────────────
# 6. STRING — Protein-protein interaction network
# ──────────────────────────────────────────────────────────────────────

def get_interaction_network(protein: str, species: int = 9606, limit: int = 15) -> dict:
    """Query STRING DB for protein-protein interactions.

    Returns interaction partners with confidence scores.
    Species 9606 = Homo sapiens.
    """
    try:
        protein = protein.strip()

        # Resolve protein name to STRING ID
        resolve = _get(
            "https://string-db.org/api/json/get_string_ids",
            params={"identifiers": protein, "species": species, "limit": 1},
        )
        if not resolve or (isinstance(resolve, list) and len(resolve) == 0):
            return {"error": f"Protein '{protein}' not found in STRING DB (species: {species})"}

        string_id = resolve[0]["stringId"] if isinstance(resolve, list) else resolve.get("stringId", "")

        # Get interaction partners
        interactions = _get(
            "https://string-db.org/api/json/network",
            params={
                "identifiers": protein,
                "species": species,
                "required_score": 400,  # Medium confidence
                "limit": limit,
            },
        )

        if not isinstance(interactions, list):
            return {"error": "Unexpected STRING response format"}

        # Parse interactions
        partners = []
        seen = set()
        for edge in interactions:
            partner_a = edge.get("preferredName_A", "")
            partner_b = edge.get("preferredName_B", "")
            score = edge.get("score", 0)

            # Get the partner (not the query protein)
            partner = partner_b if partner_a.upper() == protein.upper() else partner_a
            if partner.upper() in seen:
                continue
            seen.add(partner.upper())

            partners.append({
                "partner": partner,
                "combined_score": score,
                "experimental": edge.get("escore", 0),
                "database": edge.get("dscore", 0),
                "textmining": edge.get("tscore", 0),
                "coexpression": edge.get("ascore", 0),
            })

        # Sort by combined score
        partners.sort(key=lambda x: x["combined_score"], reverse=True)

        # Functional enrichment
        enrichment = _get(
            "https://string-db.org/api/json/enrichment",
            params={"identifiers": protein, "species": species},
        )
        go_enrichment = []
        if isinstance(enrichment, list):
            for term in enrichment[:8]:
                if term.get("category") in ("Process", "Function", "Component", "KEGG"):
                    go_enrichment.append({
                        "category": term.get("category", ""),
                        "term": term.get("description", ""),
                        "p_value": term.get("p_value", 1),
                        "proteins": term.get("number_of_genes", 0),
                    })

        return {
            "query_protein": protein,
            "string_id": string_id,
            "n_interactions": len(partners),
            "interactions": partners[:limit],
            "functional_enrichment": go_enrichment[:8],
            "source": "STRING DB v12 (string-db.org)",
        }
    except Exception as e:
        return {"error": f"STRING query failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 7. InterPro — Domain/family classification
# ──────────────────────────────────────────────────────────────────────

def classify_domains(uniprot_id_or_gene: str) -> dict:
    """Classify protein domains and families using InterPro.

    Accepts UniProt ID or gene name (resolves via UniProt first).
    """
    try:
        query = uniprot_id_or_gene.strip()

        # Resolve gene name to UniProt ID if needed
        if not (len(query) >= 6 and query[0].isalpha()):
            info = get_protein_info(query)
            if "error" in info:
                return info
            query = info.get("uniprot_id", query)

        # Query InterPro for this protein
        data = _get(f"https://www.ebi.ac.uk/interpro/api/entry/all/protein/uniprot/{query}")

        if not isinstance(data, dict):
            return {"error": f"No InterPro results for '{query}'"}

        entries = []
        for result in data.get("results", []):
            meta = result.get("metadata", {}) or {}
            go_list = meta.get("go_terms") or []
            entry = {
                "accession": meta.get("accession", ""),
                "name": meta.get("name") or meta.get("accession", ""),
                "type": meta.get("type", ""),
                "source_database": meta.get("source_database", ""),
                "go_terms": [
                    go.get("name", "") for go in go_list[:5]
                ],
            }
            # Get location on protein
            for protein_data in result.get("proteins") or []:
                for loc in protein_data.get("entry_protein_locations") or []:
                    for frag in loc.get("fragments") or []:
                        entry["start"] = frag.get("start")
                        entry["end"] = frag.get("end")
                        break
                    break
            entries.append(entry)

        # Group by type
        families = [e for e in entries if e["type"] == "family"]
        domains = [e for e in entries if e["type"] == "domain"]
        sites = [e for e in entries if e["type"] in ("active_site", "binding_site", "conserved_site")]
        other = [e for e in entries if e["type"] not in ("family", "domain", "active_site", "binding_site", "conserved_site")]

        return {
            "uniprot_id": query,
            "n_entries": len(entries),
            "families": families[:5],
            "domains": domains[:10],
            "sites": sites[:5],
            "other": other[:5],
            "source": "InterPro (EBI)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"No InterPro entries for '{uniprot_id_or_gene}'"}
        return {"error": f"InterPro API error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"InterPro query failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 8. PubChem — Compound/drug lookup
# ──────────────────────────────────────────────────────────────────────

def lookup_compound(name: str) -> dict:
    """Lookup a compound/drug in PubChem by name.

    Returns structure, properties, bioactivity summary.
    """
    try:
        name = name.strip()

        # Search by name
        data = _get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/JSON"
        )
        if not isinstance(data, dict):
            return {"error": f"Compound '{name}' not found in PubChem"}

        compounds = data.get("PC_Compounds", [])
        if not compounds:
            return {"error": f"No PubChem results for '{name}'"}

        cid = compounds[0].get("id", {}).get("id", {}).get("cid")
        if not cid:
            return {"error": "Could not extract PubChem CID"}

        # Get properties
        props = _get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/property/"
            "MolecularFormula,MolecularWeight,IUPACName,InChIKey,XLogP,HBondDonorCount,"
            "HBondAcceptorCount,TPSA,RotatableBondCount,ExactMass/JSON"
        )
        prop_data = {}
        if isinstance(props, dict):
            prop_table = props.get("PropertyTable", {}).get("Properties", [])
            if prop_table:
                prop_data = prop_table[0]

        # Get description (pharmacology, mechanism, etc.)
        desc_data = _get(
            f"https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/{cid}/description/JSON"
        )
        description = ""
        if isinstance(desc_data, dict):
            for info in desc_data.get("InformationList", {}).get("Information", []):
                desc = info.get("Description", "")
                if len(desc) > len(description):
                    description = desc
        description = description[:500]

        # Lipinski's Rule of Five check
        mw = prop_data.get("MolecularWeight", 0)
        logp = prop_data.get("XLogP", 0)
        hbd = prop_data.get("HBondDonorCount", 0)
        hba = prop_data.get("HBondAcceptorCount", 0)
        lipinski_violations = sum([
            float(mw) > 500 if mw else False,
            float(logp) > 5 if logp else False,
            int(hbd) > 5 if hbd else False,
            int(hba) > 10 if hba else False,
        ])

        return {
            "cid": cid,
            "name": name,
            "iupac_name": prop_data.get("IUPACName", ""),
            "molecular_formula": prop_data.get("MolecularFormula", ""),
            "molecular_weight": prop_data.get("MolecularWeight"),
            "xlogp": prop_data.get("XLogP"),
            "hbond_donors": prop_data.get("HBondDonorCount"),
            "hbond_acceptors": prop_data.get("HBondAcceptorCount"),
            "tpsa": prop_data.get("TPSA"),
            "rotatable_bonds": prop_data.get("RotatableBondCount"),
            "exact_mass": prop_data.get("ExactMass"),
            "inchikey": prop_data.get("InChIKey", ""),
            "lipinski_violations": lipinski_violations,
            "drug_like": lipinski_violations <= 1,
            "description": description,
            "source": "PubChem (NCBI)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"Compound '{name}' not found in PubChem. Try the exact drug name."}
        return {"error": f"PubChem API error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"PubChem lookup failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 9. Semantic Scholar — Citation-aware literature search
# ──────────────────────────────────────────────────────────────────────

def search_literature(query: str, limit: int = 10, year_min: int | None = None) -> dict:
    """Search Semantic Scholar for papers with citation context.

    Returns papers with titles, abstracts, citation counts, and DOIs.
    """
    try:
        query = query.strip()
        params: dict = {
            "query": query,
            "limit": min(limit, 20),
            "fields": "title,abstract,year,citationCount,influentialCitationCount,authors,externalIds,url,publicationTypes",
        }
        if year_min:
            params["year"] = f"{year_min}-"

        # Semantic Scholar has strict rate limits — retry once on 429
        try:
            data = _get("https://api.semanticscholar.org/graph/v1/paper/search", params=params)
        except httpx.HTTPStatusError as rate_err:
            if rate_err.response.status_code == 429:
                time.sleep(3)
                data = _get("https://api.semanticscholar.org/graph/v1/paper/search", params=params)
            else:
                raise
        if not isinstance(data, dict):
            return {"error": "Unexpected Semantic Scholar response"}

        papers = []
        for paper in data.get("data", []):
            ext_ids = paper.get("externalIds", {}) or {}
            authors = paper.get("authors", []) or []
            papers.append({
                "title": paper.get("title", ""),
                "year": paper.get("year"),
                "citations": paper.get("citationCount", 0),
                "influential_citations": paper.get("influentialCitationCount", 0),
                "authors": ", ".join(a.get("name", "") for a in authors[:4])
                           + (" et al." if len(authors) > 4 else ""),
                "doi": ext_ids.get("DOI", ""),
                "pmid": ext_ids.get("PubMed", ""),
                "abstract": (paper.get("abstract") or "")[:300],
                "url": paper.get("url", ""),
                "pub_types": paper.get("publicationTypes", []),
            })

        # Sort by citation count (most cited first)
        papers.sort(key=lambda x: x.get("citations", 0), reverse=True)

        return {
            "query": query,
            "total_results": data.get("total", 0),
            "papers": papers[:limit],
            "source": "Semantic Scholar (Allen AI)",
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 429:
            return {"error": "Semantic Scholar rate limited. Try again in a few seconds."}
        return {"error": f"Semantic Scholar error (HTTP {e.response.status_code})"}
    except Exception as e:
        return {"error": f"Literature search failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 10. RCSB PDB — Experimental structure search
# ──────────────────────────────────────────────────────────────────────

def search_pdb_structures(query: str, limit: int = 5) -> dict:
    """Search RCSB PDB for experimental structures by protein/gene name.

    Returns PDB IDs, resolution, method, organism, and chain info.
    """
    try:
        query = query.strip()

        # Use RCSB Search API
        search_body = {
            "query": {
                "type": "terminal",
                "service": "full_text",
                "parameters": {"value": query},
            },
            "return_type": "entry",
            "request_options": {
                "paginate": {"start": 0, "rows": limit},
                "sort": [{"sort_by": "score", "direction": "desc"}],
            },
        }
        search_result = _post(
            "https://search.rcsb.org/rcsbsearch/v2/query",
            json_body=search_body,
        )

        if not isinstance(search_result, dict):
            return {"error": "Unexpected RCSB search response"}

        pdb_ids = [r.get("identifier", "") for r in search_result.get("result_set", [])]
        if not pdb_ids:
            return {"error": f"No experimental structures found for '{query}' in RCSB PDB"}

        # Fetch details for each PDB
        structures = []
        for pdb_id in pdb_ids[:limit]:
            try:
                entry = _get(f"https://data.rcsb.org/rest/v1/core/entry/{pdb_id}")
                if not isinstance(entry, dict):
                    continue

                struct = entry.get("rcsb_entry_info", {})
                citation = entry.get("rcsb_primary_citation", {})

                structures.append({
                    "pdb_id": pdb_id,
                    "title": entry.get("struct", {}).get("title", ""),
                    "method": struct.get("experimental_method", ""),
                    "resolution_angstrom": struct.get("resolution_combined", [None])[0]
                                           if struct.get("resolution_combined") else None,
                    "deposition_date": struct.get("deposit_date", ""),
                    "polymer_count": struct.get("polymer_entity_count", 0),
                    "citation_title": citation.get("title", ""),
                    "citation_doi": citation.get("pdbx_database_id_doi", ""),
                })
            except Exception:
                structures.append({"pdb_id": pdb_id, "error": "Failed to fetch details"})

        return {
            "query": query,
            "total_found": search_result.get("total_count", 0),
            "structures": structures,
            "source": "RCSB PDB (rcsb.org)",
        }
    except Exception as e:
        return {"error": f"RCSB PDB search failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 11. PharmGKB — Pharmacogenomics annotations
# ──────────────────────────────────────────────────────────────────────

def get_pharmacogenomics(gene_or_drug: str) -> dict:
    """Query PharmGKB for pharmacogenomic annotations.

    Returns drug-gene interactions with evidence levels and clinical annotations.
    """
    try:
        query = gene_or_drug.strip()

        # Try as gene first (symbol lookup)
        gene_data = None
        gene_id = None
        try:
            resp = _get(
                "https://api.pharmgkb.org/v1/data/gene",
                params={"symbol": query},
            )
            gene_list = resp.get("data", []) if isinstance(resp, dict) else []
            if isinstance(gene_list, list) and gene_list:
                gene_data = gene_list[0]
                gene_id = gene_data.get("id")
        except Exception:
            pass

        # Try as drug if gene didn't work
        drug_data = None
        if not gene_data:
            try:
                resp = _get(
                    "https://api.pharmgkb.org/v1/data/chemical",
                    params={"name": query},
                )
                drug_list = resp.get("data", []) if isinstance(resp, dict) else []
                if isinstance(drug_list, list) and drug_list:
                    drug_data = drug_list[0]
            except Exception:
                pass

        if not gene_data and not drug_data:
            return {"error": f"No PharmGKB results for '{query}'. Try exact gene symbol or drug name."}

        result: dict = {"query": query, "source": "PharmGKB (Stanford)"}

        if gene_data:
            result["gene"] = {
                "symbol": gene_data.get("symbol", ""),
                "name": gene_data.get("name", ""),
                "id": gene_id,
                "cpic_gene": gene_data.get("cpicGene", False),
                "pharmgkb_accession": gene_data.get("pharmgkbAccessions", []),
            }

            # Get clinical annotations for this gene
            annotations = []
            if gene_id:
                try:
                    ann_resp = _get(
                        "https://api.pharmgkb.org/v1/data/clinicalAnnotation",
                        params={"relatedGenes.accessionId": gene_id},
                    )
                    ann_list = ann_resp.get("data", []) if isinstance(ann_resp, dict) else []
                    for ann in ann_list[:8]:
                        chemicals = ann.get("relatedChemicals", []) or []
                        diseases = ann.get("relatedDiseases", []) or []
                        annotations.append({
                            "drug": ", ".join(c.get("name", "") for c in chemicals),
                            "phenotype": ", ".join(d.get("name", "") for d in diseases),
                            "level_of_evidence": ann.get("level", ""),
                            "phenotype_categories": ann.get("phenotypeCategories", []),
                        })
                except Exception:
                    pass
            result["clinical_annotations"] = annotations

        if drug_data:
            result["drug"] = {
                "name": drug_data.get("name", ""),
                "id": drug_data.get("id", ""),
                "generic_names": drug_data.get("genericNames", []),
                "trade_names": (drug_data.get("tradeNames") or [])[:5],
                "types": drug_data.get("types", []),
                "top_clinical_annotation_level": drug_data.get("topClinicalAnnotationLevel"),
            }

        return result
    except Exception as e:
        return {"error": f"PharmGKB query failed: {e}"}


# ──────────────────────────────────────────────────────────────────────
# 12. Europe PMC — Full-text literature search (no auth needed)
# ──────────────────────────────────────────────────────────────────────

def search_europe_pmc(query: str, limit: int = 10) -> dict:
    """Search Europe PMC for open-access biomedical literature.

    Broader coverage than PubMed alone. No auth required.
    """
    try:
        query = query.strip()
        data = _get(
            "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
            params={
                "query": query,
                "format": "json",
                "pageSize": min(limit, 25),
            },
        )

        if not isinstance(data, dict):
            return {"error": "Unexpected Europe PMC response"}

        result_list = (data.get("resultList") or {}).get("result", [])

        papers = []
        for result in result_list:
            papers.append({
                "title": result.get("title", ""),
                "authors": result.get("authorString", ""),
                "journal": result.get("journalTitle", ""),
                "year": result.get("pubYear", ""),
                "doi": result.get("doi", ""),
                "pmid": result.get("pmid", ""),
                "pmcid": result.get("pmcid", ""),
                "is_open_access": result.get("isOpenAccess") == "Y",
                "cited_by": result.get("citedByCount", 0),
                "abstract": (result.get("abstractText") or "")[:300],
            })

        return {
            "query": query,
            "total_results": data.get("hitCount", 0),
            "papers": papers,
            "source": "Europe PMC (EBI)",
        }
    except Exception as e:
        return {"error": f"Europe PMC search failed: {e}"}
