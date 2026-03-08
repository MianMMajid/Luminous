#!/usr/bin/env python3
"""Smoke test all API integrations before the hackathon demo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ANTHROPIC_API_KEY, TAMARIND_API_KEY


def test_imports():
    """Test all critical imports."""
    print("1. Testing imports...")
    import anthropic
    import molviewspec as mvs

    print(f"   molviewspec {mvs.__version__}, anthropic {anthropic.__version__}")
    print("   PASS")


def test_fallback_parser():
    """Test the fallback query parser."""
    print("2. Testing fallback parser...")
    from src.query_parser import _fallback_parse
    q = _fallback_parse("P53 R248W mutation - is it druggable?")
    assert q.protein_name == "TP53", f"Expected TP53, got {q.protein_name}"
    assert q.mutation == "R248W", f"Expected R248W, got {q.mutation}"
    assert q.question_type == "druggability", f"Expected druggability, got {q.question_type}"
    print("   PASS")


def test_molviewspec():
    """Test molviewspec builder can create state."""
    print("3. Testing molviewspec builder...")
    import molviewspec as mvs
    builder = mvs.create_builder()
    structure = builder.download(url="test.pdb").parse(format="pdb").model_structure()
    rep = structure.component(selector="polymer").representation(type="cartoon")
    rep.color(color="#888888")
    state = builder.get_state()
    assert state is not None
    print("   PASS")


def test_trust_audit():
    """Test trust audit with mock data."""
    print("4. Testing trust audit logic...")
    from src.models import ProteinQuery
    from src.trust_auditor import get_residue_flags
    from src.utils import build_trust_annotations

    q = ProteinQuery(protein_name="TP53", mutation="R248W", question_type="druggability")
    flags = get_residue_flags(q, [247, 248, 249], [85.0, 45.0, 75.0])
    assert 248 in flags, "Mutation site should be flagged"

    annotations = build_trust_annotations(["A", "A", "A"], [247, 248, 249], [85.0, 45.0, 75.0], flags)
    assert len(annotations) == 3
    assert annotations[1]["color"] == "#FF7D45"  # Very low confidence
    print("   PASS")


def test_anthropic_api():
    """Test Anthropic API connectivity."""
    print("5. Testing Anthropic API...")
    if not ANTHROPIC_API_KEY:
        print("   SKIP (no ANTHROPIC_API_KEY)")
        return
    from anthropic import Anthropic
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=50,
        messages=[{"role": "user", "content": "Say 'API test OK' in exactly those words."}],
    )
    print(f"   Response: {msg.content[0].text[:50]}")
    print("   PASS")


def test_anthropic_mcp():
    """Test Anthropic MCP connector with PubMed."""
    print("6. Testing Anthropic MCP connector...")
    if not ANTHROPIC_API_KEY:
        print("   SKIP (no ANTHROPIC_API_KEY)")
        return
    from anthropic import Anthropic

    from src.config import MCP_BETA_HEADER, PUBMED_MCP_URL
    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    try:
        resp = client.beta.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=256,
            messages=[{"role": "user", "content": "Search PubMed for 'TP53 R248W' and return 1 result title."}],
            mcp_servers=[{"type": "url", "url": PUBMED_MCP_URL, "name": "pubmed"}],
            tools=[{"type": "mcp_toolset", "mcp_server_name": "pubmed"}],
            betas=[MCP_BETA_HEADER],
        )
        text = next((b.text for b in resp.content if hasattr(b, "text")), "No text")
        print(f"   Response: {text[:80]}...")
        print("   PASS")
    except Exception as e:
        print(f"   FAIL: {e}")
        return False


def test_tamarind_api():
    """Test Tamarind API connectivity and tool discovery."""
    print("7. Testing Tamarind API...")
    if not TAMARIND_API_KEY:
        print("   SKIP (no TAMARIND_API_KEY)")
        return
    import httpx

    from src.config import TAMARIND_BASE_URL
    resp = httpx.get(
        f"{TAMARIND_BASE_URL}/tools",
        headers={"x-api-key": TAMARIND_API_KEY},
        timeout=15,
    )
    print(f"   Status: {resp.status_code}")
    if resp.status_code == 200:
        tools = resp.json()
        n = len(tools) if isinstance(tools, list) else "dict response"
        print(f"   Available tools: {n}")
        if isinstance(tools, list) and tools:
            # Show first few tool names
            names = [t.get("name", t) if isinstance(t, dict) else str(t) for t in tools[:8]]
            print(f"   Sample tools: {', '.join(names)}")
        print("   PASS")
    else:
        print(f"   FAIL: {resp.text[:100]}")
        return False


def test_tamarind_multi_tool():
    """Test Tamarind multi-tool analysis orchestrator."""
    print("7b. Testing Tamarind multi-tool orchestrator...")
    from src.tamarind_analyses import get_available_analyses
    for qtype in ("structure", "mutation_impact", "druggability", "binding", "antibody", "dynamics"):
        analyses = get_available_analyses(qtype)
        print(f"   {qtype}: {len(analyses)} tools — {', '.join(a[0] for a in analyses)}")
    print("   PASS")


def test_biomcp_cli():
    """Test BioMCP CLI."""
    print("8. Testing BioMCP CLI...")
    import subprocess
    try:
        # Correct syntax: biomcp gene get <SYMBOL> -j
        result = subprocess.run(
            ["biomcp", "gene", "get", "TP53", "-j"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            data = json.loads(result.stdout)
            print(f"   Gene data keys: {list(data.keys())[:5] if isinstance(data, dict) else type(data)}")
            print("   PASS")
        else:
            print(f"   FAIL: exit code {result.returncode}")
            if result.stderr:
                print(f"   stderr: {result.stderr[:100]}")
            return False
    except FileNotFoundError:
        print("   SKIP (biomcp not in PATH)")
    except Exception as e:
        print(f"   FAIL: {e}")
        return False


def test_rcsb_pdb():
    """Test RCSB PDB fetch."""
    print("9. Testing RCSB PDB fetch...")
    import httpx
    resp = httpx.get("https://files.rcsb.org/download/1TUP.pdb", timeout=15)
    if resp.status_code == 200:
        lines = resp.text.split("\n")
        atom_lines = [line for line in lines if line.startswith("ATOM")]
        print(f"   Downloaded 1TUP.pdb: {len(atom_lines)} ATOM records")
        print("   PASS")
    else:
        print(f"   FAIL: status {resp.status_code}")


def test_precomputed_data():
    """Test precomputed data loading."""
    print("10. Testing precomputed data...")
    from src.utils import load_precomputed
    for name in ["p53_r248w", "brca1_c61g", "egfr_t790m"]:
        data = load_precomputed(name)
        if data:
            keys = list(data.keys())
            print(f"    {name}: {keys}")
        else:
            print(f"    {name}: NOT FOUND")
    print("   DONE")


if __name__ == "__main__":
    print("=" * 60)
    print("Luminous API Smoke Test")
    print("=" * 60)
    print()

    tests = [
        test_imports,
        test_fallback_parser,
        test_molviewspec,
        test_trust_audit,
        test_anthropic_api,
        test_anthropic_mcp,
        test_tamarind_api,
        test_tamarind_multi_tool,
        test_biomcp_cli,
        test_rcsb_pdb,
        test_precomputed_data,
    ]

    failures = 0
    for test in tests:
        try:
            result = test()
            # Tests can return False to signal soft failure (printed FAIL but no exception)
            if result is False:
                failures += 1
        except Exception as e:
            print(f"   FAIL: {e}")
            failures += 1
        print()

    print("=" * 60)
    if failures:
        print(f"DONE: {failures} test(s) failed")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
