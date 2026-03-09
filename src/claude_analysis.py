"""Claude Analysis Engine — natural-language statistical analysis.

Users describe an analysis in plain English; Claude generates Python code
that runs against their DataFrame. The code is executed in a sandboxed
namespace with only whitelisted scientific libraries.
"""

from __future__ import annotations

import json
import re
import time
import traceback
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.config import ANTHROPIC_API_KEY, CLAUDE_FAST_MODEL, CLAUDE_MODEL

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are an expert biostatistician embedded in the Luminous protein analysis \
platform. The user describes a statistical analysis in natural language. \
You produce Python code that performs it on the provided DataFrame.

## Available libraries (ONLY these — nothing else)
- numpy (as np), pandas (as pd)
- scipy (scipy.stats, scipy.optimize, scipy.signal, scipy.spatial, scipy.interpolate)
- statsmodels (statsmodels.api, statsmodels.formula.api, statsmodels.stats, \
  statsmodels.regression, statsmodels.nonparametric, statsmodels.genmod, \
  statsmodels.duration, statsmodels.multivariate)
- sklearn (decomposition, cluster, preprocessing, metrics, linear_model, \
  ensemble, manifold, model_selection, feature_selection, svm, neighbors, tree)
- pingouin (as pg)
- lifelines (KaplanMeierFitter, CoxPHFitter, NelsonAalenFitter, etc.)
- plotly (plotly.graph_objects as go, plotly.express as px, plotly.subplots)
- math, statistics, itertools, functools, collections, re, json, io, warnings

## PROHIBITED — code will be REJECTED if it contains any of these
- os, sys, subprocess, pathlib, shutil, glob (no filesystem)
- socket, http, urllib, requests, httpx, aiohttp (no network)
- importlib, __import__, exec, eval, compile (no dynamic imports)
- open(), file I/O of any kind

## Input
`df` is a pandas DataFrame (pre-defined — do NOT redefine it).

## Output — your code MUST end by setting `results`
```
results = {
    "tables": [...],    # list of pd.DataFrame
    "figures": [...],   # list of plotly.graph_objects.Figure
    "text": "...",      # markdown interpretation of results
    "warnings": [...],  # list of warning strings (optional)
}
```

## Plotly style (match the Luminous app)
- template="plotly_white"
- paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)"
- font=dict(family="Nunito, system-ui, sans-serif", color="rgba(60,60,67,0.6)", size=12)
- Palette: ["#648FFF","#DC267F","#FE6100","#785EF0","#FFB000","#000000","#22A884"]
- height 400-500px, descriptive axis labels

## Statistical rigor
- Check assumptions before parametric tests
- Report effect sizes alongside p-values
- Use multiple-comparison correction when doing many tests
- Report confidence intervals where applicable
- Note sample-size limitations
- If ambiguous, choose the most appropriate analysis and explain your choice

## Rules
1. `df` is pre-defined. Do NOT redefine it.
2. `results` MUST be defined by end of code.
3. No print() or display(). Output through `results` only.
4. Do NOT modify `df` in place — use df.copy().
5. Handle NaN values explicitly.
6. If the analysis is impossible with the data, explain in results["text"] \
   and leave tables/figures empty.
"""

# ---------------------------------------------------------------------------
# Allowed / blocked modules
# ---------------------------------------------------------------------------

_ALLOWED_TOPLEVEL = frozenset({
    "numpy", "np", "pandas", "pd",
    "scipy", "statsmodels", "sklearn",
    "pingouin", "pg", "lifelines",
    "plotly", "go", "px",
    "math", "statistics", "itertools", "functools", "collections",
    "re", "json", "io", "warnings", "time", "copy", "string",
})

_BLOCKED_BUILTINS = frozenset({
    "open", "exec", "eval", "compile", "__import__", "input",
    "breakpoint", "exit", "quit",
})

_DANGER_PATTERNS = [
    "os.", "sys.", "subprocess", "pathlib", "shutil",
    "socket", "http.", "urllib", "requests.", "httpx",
    "open(", "__import__", "importlib",
]

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------

_real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __builtins__.__import__


def _restricted_import(name: str, *args: Any, **kwargs: Any):
    top = name.split(".")[0]
    if top not in _ALLOWED_TOPLEVEL:
        raise ImportError(
            f"Import of '{name}' is not allowed. "
            f"Only scientific libraries (scipy, statsmodels, sklearn, pingouin, "
            f"lifelines, plotly, numpy, pandas) are available."
        )
    return _real_import(name, *args, **kwargs)


def _make_safe_builtins() -> dict:
    import builtins
    safe = {}
    for name in dir(builtins):
        if name not in _BLOCKED_BUILTINS and not name.startswith("_"):
            safe[name] = getattr(builtins, name)
    safe["__import__"] = _restricted_import
    safe["__build_class__"] = builtins.__build_class__
    safe["__name__"] = "<claude_analysis>"
    return safe


# ---------------------------------------------------------------------------
# Code execution sandbox
# ---------------------------------------------------------------------------

def execute_analysis_code(
    code: str,
    df: pd.DataFrame,
    timeout_seconds: int = 30,
) -> dict:
    """Execute Claude-generated code in a sandboxed namespace.

    Returns dict with: tables, figures, text, warnings, error, code, execution_time.
    """
    import plotly.express as px
    from plotly.subplots import make_subplots

    start = time.time()

    # Pre-scan for dangerous patterns
    code_lower = code.lower()
    for pattern in _DANGER_PATTERNS:
        if pattern in code_lower:
            return _error_result(f"Blocked: code contains disallowed pattern '{pattern}'", code, start)

    # Build namespace
    namespace: dict[str, Any] = {
        "__builtins__": _make_safe_builtins(),
        "df": df.copy(),
        "np": np,
        "numpy": np,
        "pd": pd,
        "pandas": pd,
        "go": go,
        "px": px,
        "make_subplots": make_subplots,
        "results": {"tables": [], "figures": [], "text": "", "warnings": []},
    }

    # Run code with a threading-based timeout (signal.alarm doesn't work
    # in Streamlit's worker threads).
    exec_error: list = []
    def _run():
        try:
            exec(compile(code, "<claude_analysis>", "exec"), namespace)  # noqa: S102
        except Exception as e:
            exec_error.append(e)

    import threading
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=timeout_seconds)
    if t.is_alive():
        return _error_result(
            f"Analysis timed out after {timeout_seconds}s", code, start
        )
    if exec_error:
        e = exec_error[0]
        tb = traceback.format_exception(type(e), e, e.__traceback__)
        return _error_result(
            f"{type(e).__name__}: {e}\n\n{''.join(tb)}", code, start
        )

    # Extract and validate results
    raw = namespace.get("results", {})
    tables = []
    for t in raw.get("tables", []):
        if isinstance(t, pd.DataFrame):
            tables.append(t)
        elif isinstance(t, dict):
            tables.append(pd.DataFrame(t))

    figures = [f for f in raw.get("figures", []) if isinstance(f, go.Figure)]

    return {
        "tables": tables,
        "figures": figures,
        "text": str(raw.get("text", "")),
        "warnings": [str(w) for w in raw.get("warnings", [])],
        "error": None,
        "code": code,
        "execution_time": time.time() - start,
    }


def _error_result(error: str, code: str, start: float) -> dict:
    return {
        "tables": [],
        "figures": [],
        "text": "",
        "warnings": [],
        "error": error,
        "code": code,
        "execution_time": time.time() - start,
    }


# ---------------------------------------------------------------------------
# Data context builder
# ---------------------------------------------------------------------------

def _build_data_context(df: pd.DataFrame) -> str:
    """Concise data summary for the system prompt (≤6 000 chars)."""
    lines = [
        f"## Dataset: {df.shape[0]:,} rows × {df.shape[1]} columns",
        f"\nColumns and dtypes:\n{df.dtypes.to_string()}",
    ]

    if len(df) > 10_000:
        sample = df.sample(min(200, len(df)), random_state=42)
        lines.append(f"\nRandom sample (first 10 of 200):\n{sample.head(10).to_string()}")
        lines.append(f"\nNote: Large dataset ({len(df):,} rows). Consider sampling.")
    else:
        lines.append(f"\nFirst 5 rows:\n{df.head(5).to_string()}")

    lines.append(f"\nSummary statistics:\n{df.describe(include='all').to_string()}")
    lines.append(f"\nMissing values:\n{df.isnull().sum().to_string()}")

    ctx = "\n".join(lines)
    return ctx[:6000] + "\n... [truncated]" if len(ctx) > 6000 else ctx


# ---------------------------------------------------------------------------
# Claude API call
# ---------------------------------------------------------------------------

def run_claude_analysis(
    user_prompt: str,
    df: pd.DataFrame,
    conversation_history: list[dict] | None = None,
    previous_results: list[dict] | None = None,
    use_opus: bool = False,
) -> tuple[str, str, list[dict]]:
    """Send analysis request to Claude and return (code, explanation, messages)."""
    if not ANTHROPIC_API_KEY:
        return "", "Anthropic API key not configured. Set ANTHROPIC_API_KEY in .env.", []

    from anthropic import Anthropic

    client = Anthropic(api_key=ANTHROPIC_API_KEY)
    data_ctx = _build_data_context(df)
    system = SYSTEM_PROMPT + f"\n\n{data_ctx}"

    messages = list(conversation_history or [])

    # Inject previous error / code for iterative refinement
    content = user_prompt
    if previous_results:
        last = previous_results[-1]
        if last.get("error"):
            content += (
                f"\n\nPrevious attempt failed:\n```\n{last['error']}\n```\n"
                f"Previous code:\n```python\n{last.get('code', '')}\n```\n"
                "Fix the error and try again."
            )
        elif last.get("code"):
            content += (
                f"\n\nPrevious analysis code:\n```python\n{last['code']}\n```\n"
                "Modify this analysis as requested."
            )

    messages.append({"role": "user", "content": content})

    model = CLAUDE_MODEL if use_opus else CLAUDE_FAST_MODEL
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=system,
            messages=messages,
        )
    except Exception as e:
        err = str(e)
        if "credit balance" in err.lower() or "billing" in err.lower():
            return "", "Anthropic API credits exhausted. Add credits at console.anthropic.com.", messages
        return "", f"Claude API error: {err}", messages

    full_text = response.content[0].text if response.content else ""
    code = _extract_code(full_text)
    explanation = _extract_explanation(full_text, code)

    messages.append({"role": "assistant", "content": full_text})
    return code, explanation, messages


def _extract_code(text: str) -> str:
    """Extract the last Python code block from Claude's response."""
    matches = re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return matches[-1].strip()
    matches = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
    if matches:
        return matches[-1].strip()
    return ""


def _extract_explanation(text: str, code: str) -> str:
    """Return the non-code portion of Claude's response."""
    cleaned = re.sub(r"```(?:python)?\s*\n.*?```", "", text, flags=re.DOTALL)
    return cleaned.strip()
