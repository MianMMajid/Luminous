#!/usr/bin/env python3
"""Test script for the Claude Analysis engine.

Runs through sandbox safety tests, then hits the Claude API with real
analysis prompts against a synthetic bio dataset.

Usage:
    python3 scripts/test_claude_analysis.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd

from src.claude_analysis import execute_analysis_code, run_claude_analysis

# ---------------------------------------------------------------------------
# Synthetic dataset (mimics a typical bio experiment)
# ---------------------------------------------------------------------------

np.random.seed(42)
N = 120

df = pd.DataFrame({
    "patient_id": [f"P{i:03d}" for i in range(N)],
    "group": np.random.choice(["Control", "Treatment_A", "Treatment_B"], N),
    "dose_mg": np.random.choice([0, 10, 25, 50, 100], N).astype(float),
    "age": np.random.normal(55, 12, N).round(1),
    "sex": np.random.choice(["M", "F"], N),
    "baseline_score": np.random.normal(50, 10, N).round(2),
    "week4_score": np.random.normal(45, 12, N).round(2),
    "week8_score": np.random.normal(40, 15, N).round(2),
    "biomarker_A": np.random.lognormal(2, 0.8, N).round(3),
    "biomarker_B": np.random.normal(100, 25, N).round(3),
    "survival_months": np.random.exponential(24, N).round(1),
    "event": np.random.binomial(1, 0.6, N),
    "response": np.random.choice(["CR", "PR", "SD", "PD"], N, p=[0.15, 0.25, 0.35, 0.25]),
})
# Add dose-response signal
df["week8_score"] = df["week8_score"] - df["dose_mg"] * 0.15 + np.random.normal(0, 3, N)
# Add correlation between biomarkers
df["biomarker_B"] = df["biomarker_A"] * 8 + np.random.normal(0, 15, N)

print(f"Test dataset: {df.shape[0]} rows × {df.shape[1]} columns")
print(f"Columns: {list(df.columns)}")
print()

# ---------------------------------------------------------------------------
# Test 1: Sandbox safety
# ---------------------------------------------------------------------------

def test_sandbox():
    print("=" * 60)
    print("TEST 1: Sandbox Safety")
    print("=" * 60)

    # 1a. Safe code should work
    code = """
import numpy as np
corr = np.corrcoef(df['biomarker_A'], df['biomarker_B'])[0, 1]
results = {
    'tables': [df[['biomarker_A', 'biomarker_B']].describe()],
    'figures': [],
    'text': f'Pearson r = {corr:.4f}',
    'warnings': [],
}
"""
    r = execute_analysis_code(code, df, timeout_seconds=10)
    assert r["error"] is None, f"Safe code failed: {r['error']}"
    assert "Pearson r" in r["text"]
    print(f"  ✓ Safe code executes correctly: {r['text']}")

    # 1b. Blocked import (os)
    r = execute_analysis_code("import os\nresults={'tables':[],'figures':[],'text':'','warnings':[]}", df, 5)
    assert r["error"] and "not allowed" in r["error"]
    print(f"  ✓ 'import os' blocked: {r['error'][:60]}")

    # 1c. Blocked import (subprocess)
    r = execute_analysis_code("import subprocess\nresults={'tables':[],'figures':[],'text':'','warnings':[]}", df, 5)
    assert r["error"] is not None
    print(f"  ✓ 'import subprocess' blocked: {r['error'][:60]}")

    # 1d. Blocked pattern (open)
    r = execute_analysis_code("f = open('/etc/passwd')\nresults={'tables':[],'figures':[],'text':'','warnings':[]}", df, 5)
    assert r["error"] is not None
    print(f"  ✓ 'open()' blocked")

    # 1e. Blocked pattern (requests)
    r = execute_analysis_code("import requests\nresults={'tables':[],'figures':[],'text':'','warnings':[]}", df, 5)
    assert r["error"] is not None
    print(f"  ✓ 'import requests' blocked")

    # 1f. Timeout (busy loop — SIGALRM fires after 3s)
    code_slow = """
x = 0
while True:
    x += 1
results = {'tables': [], 'figures': [], 'text': 'done', 'warnings': []}
"""
    start = time.time()
    r = execute_analysis_code(code_slow, df, timeout_seconds=3)
    elapsed = time.time() - start
    assert r["error"] and "timed out" in r["error"].lower()
    assert elapsed < 6, f"Timeout took too long: {elapsed:.1f}s"
    print(f"  ✓ Timeout works ({elapsed:.1f}s elapsed, 3s limit)")

    # 1g. df is a copy (original not mutated)
    original_len = len(df)
    code_mutate = """
df.drop(df.index, inplace=True)
results = {'tables': [], 'figures': [], 'text': f'len={len(df)}', 'warnings': []}
"""
    r = execute_analysis_code(code_mutate, df, 5)
    assert len(df) == original_len, "Original df was mutated!"
    print(f"  ✓ Original DataFrame not mutated (still {len(df)} rows)")

    # 1h. Plotly figure generation
    code_fig = """
import plotly.graph_objects as go
fig = go.Figure()
fig.add_trace(go.Scatter(x=df['dose_mg'], y=df['week8_score'], mode='markers'))
fig.update_layout(template='plotly_white', title='Dose vs Response')
results = {
    'tables': [],
    'figures': [fig],
    'text': 'Scatter plot generated.',
    'warnings': [],
}
"""
    r = execute_analysis_code(code_fig, df, 10)
    assert r["error"] is None
    assert len(r["figures"]) == 1
    print(f"  ✓ Plotly figure generated successfully")

    # 1i. scipy works
    code_scipy = """
from scipy import stats
t_stat, p_val = stats.ttest_ind(
    df[df['group'] == 'Control']['week8_score'],
    df[df['group'] == 'Treatment_A']['week8_score'],
)
results = {
    'tables': [],
    'figures': [],
    'text': f't={t_stat:.3f}, p={p_val:.4f}',
    'warnings': [],
}
"""
    r = execute_analysis_code(code_scipy, df, 10)
    assert r["error"] is None
    assert "t=" in r["text"]
    print(f"  ✓ scipy.stats works: {r['text']}")

    # 1j. sklearn works
    code_sklearn = """
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
numeric = df[['age', 'baseline_score', 'week4_score', 'week8_score', 'biomarker_A', 'biomarker_B']].dropna()
scaled = StandardScaler().fit_transform(numeric)
pca = PCA(n_components=2).fit(scaled)
results = {
    'tables': [],
    'figures': [],
    'text': f'PCA variance explained: {pca.explained_variance_ratio_[0]:.3f}, {pca.explained_variance_ratio_[1]:.3f}',
    'warnings': [],
}
"""
    r = execute_analysis_code(code_sklearn, df, 10)
    assert r["error"] is None
    print(f"  ✓ sklearn PCA works: {r['text']}")

    print("\n  All sandbox tests passed ✓\n")


# ---------------------------------------------------------------------------
# Test 2: Claude API integration (requires API key)
# ---------------------------------------------------------------------------

PROMPTS = [
    "Compare week8_score between Control and Treatment_A groups using the appropriate test. Show a comparison plot.",
    "Fit a dose-response curve (dose_mg vs week8_score) and calculate IC50.",
    "Run PCA on all numeric columns, show a biplot colored by group, and a scree plot.",
]


def test_claude_api():
    from src.config import ANTHROPIC_API_KEY

    if not ANTHROPIC_API_KEY:
        print("=" * 60)
        print("TEST 2: Claude API (SKIPPED — no API key)")
        print("=" * 60)
        print("  Set ANTHROPIC_API_KEY in .env to run API tests.\n")
        return

    print("=" * 60)
    print("TEST 2: Claude API Integration")
    print("=" * 60)

    for i, prompt in enumerate(PROMPTS):
        print(f"\n  [{i+1}/{len(PROMPTS)}] Prompt: {prompt[:70]}...")
        t0 = time.time()

        code, explanation, messages = run_claude_analysis(
            user_prompt=prompt,
            df=df,
            conversation_history=None,
            previous_results=None,
            use_opus=False,
        )

        api_time = time.time() - t0
        print(f"    API response: {api_time:.1f}s, code: {len(code)} chars")

        if not code:
            print(f"    ✗ No code generated. Explanation: {explanation[:100]}")
            continue

        # Execute the generated code
        result = execute_analysis_code(code, df, timeout_seconds=30)
        exec_time = result["execution_time"]

        if result["error"]:
            print(f"    ✗ Execution error: {result['error'][:120]}")
            # Try auto-fix
            print(f"    Attempting auto-fix...")
            code2, _, msgs2 = run_claude_analysis(
                user_prompt=f"Fix this error: {result['error'][:500]}",
                df=df,
                conversation_history=messages,
                previous_results=[result],
                use_opus=False,
            )
            if code2:
                result2 = execute_analysis_code(code2, df, timeout_seconds=30)
                if result2["error"]:
                    print(f"    ✗ Auto-fix also failed: {result2['error'][:80]}")
                else:
                    print(f"    ✓ Auto-fix succeeded!")
                    result = result2
            continue

        print(f"    ✓ Executed in {exec_time:.2f}s")
        print(f"    Tables: {len(result['tables'])}, Figures: {len(result['figures'])}")
        if result["text"]:
            # Show first 150 chars of interpretation
            print(f"    Text: {result['text'][:150].replace(chr(10), ' ')}...")
        if result["warnings"]:
            print(f"    Warnings: {result['warnings']}")

    print(f"\n  Claude API tests complete ✓\n")


# ---------------------------------------------------------------------------
# Test 3: Edge cases
# ---------------------------------------------------------------------------

def test_edge_cases():
    print("=" * 60)
    print("TEST 3: Edge Cases")
    print("=" * 60)

    # 3a. Empty DataFrame
    empty_df = pd.DataFrame()
    code = """
results = {
    'tables': [],
    'figures': [],
    'text': f'DataFrame has {len(df)} rows, {len(df.columns)} columns',
    'warnings': ['Empty dataset'] if len(df) == 0 else [],
}
"""
    r = execute_analysis_code(code, empty_df, 5)
    assert r["error"] is None
    print(f"  ✓ Empty DataFrame handled: {r['text']}")

    # 3b. DataFrame with NaN
    nan_df = pd.DataFrame({"a": [1, 2, np.nan, 4], "b": [np.nan, 2, 3, 4]})
    code = """
results = {
    'tables': [],
    'figures': [],
    'text': f'NaN count: a={df["a"].isna().sum()}, b={df["b"].isna().sum()}',
    'warnings': [],
}
"""
    r = execute_analysis_code(code, nan_df, 5)
    assert r["error"] is None
    print(f"  ✓ NaN DataFrame handled: {r['text']}")

    # 3c. Missing results variable
    code = "x = 42"
    r = execute_analysis_code(code, df, 5)
    # Should return whatever was in namespace["results"] (the default empty dict)
    assert r["error"] is None
    print(f"  ✓ Missing results var returns default (text='{r['text']}')")

    # 3d. Code with syntax error
    code = "def foo(:\nresults = {}"
    r = execute_analysis_code(code, df, 5)
    assert r["error"] is not None
    print(f"  ✓ Syntax error caught: {r['error'][:50]}")

    # 3e. Code that raises an exception
    code = """
raise ValueError("intentional error")
"""
    r = execute_analysis_code(code, df, 5)
    assert r["error"] is not None and "intentional error" in r["error"]
    print(f"  ✓ Runtime exception caught")

    # 3f. Very large output table
    code = """
import pandas as pd
big = pd.DataFrame({'x': range(100000)})
results = {'tables': [big], 'figures': [], 'text': f'{len(big)} rows', 'warnings': []}
"""
    r = execute_analysis_code(code, df, 10)
    assert r["error"] is None
    assert len(r["tables"]) == 1
    print(f"  ✓ Large output table handled: {r['text']}")

    # 3g. Multiple figures
    code = """
import plotly.graph_objects as go
figs = []
for col in ['age', 'baseline_score', 'biomarker_A']:
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=df[col], name=col))
    fig.update_layout(template='plotly_white', title=col, height=300)
    figs.append(fig)
results = {'tables': [], 'figures': figs, 'text': '3 histograms', 'warnings': []}
"""
    r = execute_analysis_code(code, df, 10)
    assert r["error"] is None
    assert len(r["figures"]) == 3
    print(f"  ✓ Multiple figures: {len(r['figures'])} returned")

    print("\n  All edge case tests passed ✓\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print()
    print("╔══════════════════════════════════════════════╗")
    print("║   Claude Analysis Engine — Test Suite        ║")
    print("╚══════════════════════════════════════════════╝")
    print()

    test_sandbox()
    test_edge_cases()
    test_claude_api()

    print("All tests complete.")
