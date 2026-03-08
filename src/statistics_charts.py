"""Plotly figure builders for the Statistics tab.

All functions return ``go.Figure`` objects. No Streamlit imports.
Uses the IBM Design Language color-blind safe palette and Apple Light Mode
base layout to match the rest of the Luminous app.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

# ---------------------------------------------------------------------------
# GLOBAL CONFIG
# ---------------------------------------------------------------------------

# Color-blind safe palette (IBM Design Language)
CB_PALETTE = [
    "#648FFF",  # blue
    "#DC267F",  # magenta
    "#FE6100",  # orange
    "#785EF0",  # purple
    "#FFB000",  # gold
    "#000000",  # black
    "#22A884",  # teal
]

# Apple Light Mode base layout (must match rest of Luminous app)
_BASE_LAYOUT = dict(
    template="plotly_white",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Nunito, system-ui, sans-serif", color="rgba(60,60,67,0.6)", size=12),
    margin=dict(t=30, b=50, l=60, r=20),
    xaxis=dict(gridcolor="rgba(0,0,0,0.08)", zeroline=False),
    yaxis=dict(gridcolor="rgba(0,0,0,0.08)", zeroline=False),
)


def _hex_to_rgba(hex_color: str, alpha: float = 1.0) -> str:
    """Convert a hex color string to an rgba() CSS string."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


# ---------------------------------------------------------------------------
# HELPER: significance bracket
# ---------------------------------------------------------------------------

def _add_significance_bracket(
    fig: go.Figure,
    group_names: list[str],
    p_value: float,
    y_offset_frac: float = 0.05,
) -> go.Figure:
    """Add a significance bracket with *, **, ***, or ns between two groups."""
    # Gather all y-values from traces
    all_y: list[float] = []
    for trace in fig.data:
        if hasattr(trace, "y") and trace.y is not None:
            all_y.extend(
                v for v in trace.y
                if v is not None and np.isfinite(v)
            )
    if not all_y:
        return fig

    y_max = max(all_y)
    y_min = min(all_y)
    y_range = y_max - y_min if y_max != y_min else 1.0
    bracket_y = y_max + y_range * y_offset_frac
    text_y = bracket_y + y_range * 0.02

    # Star annotation
    if p_value < 0.001:
        p_text = "***"
    elif p_value < 0.01:
        p_text = "**"
    elif p_value < 0.05:
        p_text = "*"
    else:
        p_text = "ns"
    p_display = f"p = {p_value:.4f}" if p_value >= 0.001 else "p < 0.001"

    # Bracket lines (positions 0 and 1 for two box/violin groups)
    x0, x1 = 0, 1
    fig.add_shape(
        type="line", x0=x0, x1=x0,
        y0=bracket_y - y_range * 0.01, y1=bracket_y,
        line=dict(color="rgba(60,60,67,0.6)", width=1.5),
    )
    fig.add_shape(
        type="line", x0=x0, x1=x1, y0=bracket_y, y1=bracket_y,
        line=dict(color="rgba(60,60,67,0.6)", width=1.5),
    )
    fig.add_shape(
        type="line", x0=x1, x1=x1,
        y0=bracket_y - y_range * 0.01, y1=bracket_y,
        line=dict(color="rgba(60,60,67,0.6)", width=1.5),
    )

    fig.add_annotation(
        x=(x0 + x1) / 2,
        y=text_y,
        text=f"{p_text}<br><sub>{p_display}</sub>",
        showarrow=False,
        font=dict(size=13, color="rgba(60,60,67,0.8)"),
    )

    # Extend y-axis to accommodate bracket
    fig.update_yaxes(range=[y_min - y_range * 0.05, text_y + y_range * 0.08])
    return fig


# ---------------------------------------------------------------------------
# 1. Distribution chart (histogram + optional rug)
# ---------------------------------------------------------------------------

def build_distribution_chart(
    data: np.ndarray | pd.Series,
    label: str,
    show_rug: bool = True,
) -> go.Figure:
    """Histogram with an optional rug (tick) plot underneath."""
    if isinstance(data, pd.Series):
        values = data.dropna().values
    else:
        values = data[np.isfinite(data)]

    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=values,
        nbinsx=min(50, max(10, len(values) // 5)),
        marker_color=_hex_to_rgba(CB_PALETTE[0], 0.6),
        marker_line=dict(color=CB_PALETTE[0], width=1),
        name="Distribution",
        hovertemplate="Bin: %{x}<br>Count: %{y}<extra></extra>",
    ))

    if show_rug and len(values) <= 500:
        rug_y = -0.02 * (np.nanmax(values) if len(values) else 1.0)
        fig.add_trace(go.Scatter(
            x=values,
            y=[rug_y] * len(values),
            mode="markers",
            marker=dict(symbol="line-ns-open", size=8, color=CB_PALETTE[0]),
            name="Observations",
            hoverinfo="x",
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=label,
        yaxis_title="Count",
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# 2. Comparison chart (box + strip + significance bracket)
# ---------------------------------------------------------------------------

def build_comparison_chart(
    groups: dict[str, np.ndarray],
    dv_label: str,
    p_value: float | None = None,
) -> go.Figure:
    """Box plot with overlaid strip points and optional significance bracket."""
    fig = go.Figure()
    for i, (name, values) in enumerate(groups.items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Box(
            y=values,
            name=name,
            marker_color=color,
            boxmean="sd",
            jitter=0.3,
            pointpos=-1.5,
            hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        yaxis_title=dv_label,
        height=400,
        showlegend=False,
    )

    if p_value is not None and len(groups) == 2:
        fig = _add_significance_bracket(fig, list(groups.keys()), p_value)
    return fig


# ---------------------------------------------------------------------------
# 3. Scatter with fitted curve + CI/PI bands + R^2 annotation
# ---------------------------------------------------------------------------

def build_scatter_with_fit(
    x: np.ndarray,
    y: np.ndarray,
    fit_result: dict,
    x_label: str = "X",
    y_label: str = "Y",
    equation_name: str = "",
) -> go.Figure:
    """Scatter of raw data with fitted curve, confidence & prediction bands."""
    fig = go.Figure()

    # Raw data
    fig.add_trace(go.Scatter(
        x=x, y=y, mode="markers",
        marker=dict(color=CB_PALETTE[0], size=8,
                    line=dict(color=_hex_to_rgba(CB_PALETTE[0], 0.4), width=1)),
        name="Data",
        hovertemplate=f"{x_label}: %{{x:.3f}}<br>{y_label}: %{{y:.3f}}<extra></extra>",
    ))

    if fit_result.get("converged"):
        x_s = np.asarray(fit_result["x_smooth"])
        y_s = np.asarray(fit_result["y_smooth"])
        ci_lo = np.asarray(fit_result["ci_lower"])
        ci_hi = np.asarray(fit_result["ci_upper"])
        pi_lo = np.asarray(fit_result["pi_lower"])
        pi_hi = np.asarray(fit_result["pi_upper"])

        # Prediction band (lighter)
        fig.add_trace(go.Scatter(
            x=np.concatenate([x_s, x_s[::-1]]),
            y=np.concatenate([pi_hi, pi_lo[::-1]]),
            fill="toself",
            fillcolor=_hex_to_rgba(CB_PALETTE[0], 0.08),
            line=dict(color="rgba(0,0,0,0)"),
            name="95% Prediction",
            hoverinfo="skip",
            showlegend=True,
        ))

        # Confidence band (darker)
        fig.add_trace(go.Scatter(
            x=np.concatenate([x_s, x_s[::-1]]),
            y=np.concatenate([ci_hi, ci_lo[::-1]]),
            fill="toself",
            fillcolor=_hex_to_rgba(CB_PALETTE[0], 0.2),
            line=dict(color="rgba(0,0,0,0)"),
            name="95% CI",
            hoverinfo="skip",
            showlegend=True,
        ))

        # Fit line
        fig.add_trace(go.Scatter(
            x=x_s, y=y_s, mode="lines",
            line=dict(color=CB_PALETTE[1], width=2.5),
            name=equation_name or "Fit",
            hovertemplate=f"{x_label}: %{{x:.3f}}<br>Fit: %{{y:.3f}}<extra></extra>",
        ))

    r2 = fit_result.get("r_squared", 0)
    annotations = []
    if fit_result.get("converged"):
        annotations.append(dict(
            text=f"R\u00b2 = {r2:.4f}",
            xref="paper", yref="paper",
            x=0.98, y=0.98,
            showarrow=False,
            font=dict(size=13, color="rgba(60,60,67,0.6)"),
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=x_label,
        yaxis_title=y_label,
        height=450,
        legend=dict(orientation="h", y=-0.2),
        annotations=annotations,
    )
    return fig


# ---------------------------------------------------------------------------
# 4. Residual plot
# ---------------------------------------------------------------------------

def build_residual_plot(
    x: np.ndarray,
    residuals: np.ndarray,
) -> go.Figure:
    """Residuals vs X with a zero reference line."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x, y=residuals, mode="markers",
        marker=dict(color=CB_PALETTE[0], size=6),
        hovertemplate="X: %{x:.3f}<br>Residual: %{y:.3f}<extra></extra>",
        showlegend=False,
    ))
    fig.add_hline(
        y=0,
        line=dict(color="rgba(60,60,67,0.3)", width=1, dash="dash"),
    )
    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="X",
        yaxis_title="Residual",
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# 5. Q-Q normal plot
# ---------------------------------------------------------------------------

def build_qq_plot(
    residuals: np.ndarray,
) -> go.Figure:
    """Quantile-quantile plot against a normal distribution."""
    from scipy import stats

    theoretical = stats.probplot(residuals, dist="norm")[0]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=theoretical[0], y=theoretical[1], mode="markers",
        marker=dict(color=CB_PALETTE[0], size=6),
        name="Residuals",
        hovertemplate="Theoretical: %{x:.3f}<br>Sample: %{y:.3f}<extra></extra>",
    ))
    # Reference line
    mn, mx = float(np.min(theoretical[0])), float(np.max(theoretical[0]))
    fig.add_trace(go.Scatter(
        x=[mn, mx], y=[mn, mx], mode="lines",
        line=dict(color=CB_PALETTE[1], width=1.5, dash="dash"),
        name="Normal",
        hoverinfo="skip",
    ))
    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Theoretical Quantiles",
        yaxis_title="Sample Quantiles",
        height=350,
        showlegend=False,
    )
    return fig


# ---------------------------------------------------------------------------
# 6. Survival chart (Kaplan-Meier step curves with CI bands)
# ---------------------------------------------------------------------------

def build_survival_chart(
    km_result: dict,
    show_ci: bool = True,
) -> go.Figure:
    """Kaplan-Meier step curves with optional confidence interval bands."""
    fig = go.Figure()

    for i, (grp_name, curve) in enumerate(km_result["curves"].items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        timeline = curve["timeline"]
        survival = curve["survival"]

        # Step function
        fig.add_trace(go.Scatter(
            x=timeline, y=survival, mode="lines",
            line=dict(color=color, width=2.5, shape="hv"),
            name=grp_name,
            hovertemplate="Time: %{x:.1f}<br>Survival: %{y:.3f}<extra>%{fullData.name}</extra>",
        ))

        if show_ci:
            ci_lo = curve["ci_lower"]
            ci_hi = curve["ci_upper"]
            fig.add_trace(go.Scatter(
                x=timeline + timeline[::-1],
                y=ci_hi + ci_lo[::-1],
                fill="toself",
                fillcolor=_hex_to_rgba(color, 0.15),
                line=dict(color="rgba(0,0,0,0)"),
                showlegend=False,
                hoverinfo="skip",
            ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Time",
        yaxis_title="Survival Probability",
        yaxis_range=[-0.05, 1.05],
        height=450,
        legend=dict(orientation="h", y=-0.15),
    )

    # Median survival dashed lines
    for grp_name, median in km_result.get("median_survival", {}).items():
        if median is not None:
            fig.add_hline(
                y=0.5,
                line=dict(color="rgba(60,60,67,0.2)", width=1, dash="dot"),
            )
            fig.add_vline(
                x=median,
                line=dict(color="rgba(60,60,67,0.2)", width=1, dash="dot"),
            )

    return fig


# ---------------------------------------------------------------------------
# 7. Violin chart (violin + overlaid strip points + significance bracket)
# ---------------------------------------------------------------------------

def build_violin_chart(
    groups: dict[str, np.ndarray],
    dv_label: str,
    p_value: float | None = None,
) -> go.Figure:
    """Violin plot with overlaid strip points and optional significance bracket."""
    fig = go.Figure()
    for i, (name, values) in enumerate(groups.items()):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Violin(
            y=values,
            name=name,
            fillcolor=_hex_to_rgba(color, 0.3),
            line_color=color,
            box_visible=True,
            meanline_visible=True,
            points="all" if len(values) <= 100 else "outliers",
            pointpos=-0.5 if len(values) <= 100 else 0,
            jitter=0.3,
            hovertemplate="%{y:.3f}<extra>%{fullData.name}</extra>",
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        yaxis_title=dv_label,
        height=400,
        showlegend=False,
    )

    if p_value is not None and len(groups) == 2:
        fig = _add_significance_bracket(fig, list(groups.keys()), p_value)
    return fig


# ---------------------------------------------------------------------------
# 8. Volcano plot
# ---------------------------------------------------------------------------

def build_volcano_plot(
    log2fc: np.ndarray,
    neg_log10p: np.ndarray,
    labels: list[str] | np.ndarray | None = None,
    fc_thresh: float = 1.0,
    p_thresh: float = 0.05,
) -> go.Figure:
    """Volcano plot with colored quadrants (up=magenta, down=blue, ns=gray)."""
    log2fc = np.asarray(log2fc, dtype=float)
    neg_log10p = np.asarray(neg_log10p, dtype=float)
    neg_log10p_thresh = -np.log10(p_thresh) if p_thresh > 0 else 1.3

    # Classify points
    sig_mask = neg_log10p >= neg_log10p_thresh
    up_mask = sig_mask & (log2fc >= fc_thresh)
    down_mask = sig_mask & (log2fc <= -fc_thresh)
    ns_mask = ~(up_mask | down_mask)

    fig = go.Figure()

    # Not significant (gray)
    if ns_mask.sum() > 0:
        ns_labels = np.asarray(labels)[ns_mask] if labels is not None else None
        fig.add_trace(go.Scatter(
            x=log2fc[ns_mask],
            y=neg_log10p[ns_mask],
            mode="markers",
            marker=dict(color="rgba(142,142,147,0.4)", size=5),
            name="Not significant",
            text=ns_labels,
            hovertemplate="log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>",
        ))

    # Up-regulated (magenta)
    if up_mask.sum() > 0:
        up_labels = np.asarray(labels)[up_mask] if labels is not None else None
        show_text = labels is not None and up_mask.sum() <= 20
        fig.add_trace(go.Scatter(
            x=log2fc[up_mask],
            y=neg_log10p[up_mask],
            mode="markers+text" if show_text else "markers",
            text=up_labels if show_text else None,
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(color=CB_PALETTE[1], size=8),
            name="Up-regulated",
            hovertemplate=(
                ("<b>%{text}</b><br>" if labels is not None else "")
                + "log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>"
            ),
        ))

    # Down-regulated (blue)
    if down_mask.sum() > 0:
        down_labels = np.asarray(labels)[down_mask] if labels is not None else None
        show_text = labels is not None and down_mask.sum() <= 20
        fig.add_trace(go.Scatter(
            x=log2fc[down_mask],
            y=neg_log10p[down_mask],
            mode="markers+text" if show_text else "markers",
            text=down_labels if show_text else None,
            textposition="top center",
            textfont=dict(size=9),
            marker=dict(color=CB_PALETTE[0], size=8),
            name="Down-regulated",
            hovertemplate=(
                ("<b>%{text}</b><br>" if labels is not None else "")
                + "log2FC: %{x:.2f}<br>-log10(p): %{y:.2f}<extra></extra>"
            ),
        ))

    # Threshold lines
    fig.add_vline(x=fc_thresh, line_dash="dash", line_color="rgba(60,60,67,0.2)")
    fig.add_vline(x=-fc_thresh, line_dash="dash", line_color="rgba(60,60,67,0.2)")
    fig.add_hline(
        y=neg_log10p_thresh,
        line_dash="dash",
        line_color="rgba(60,60,67,0.2)",
        annotation_text=f"p = {p_thresh}",
        annotation_position="right",
    )

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="log2(Fold Change)",
        yaxis_title="-log10(p-value)",
        height=500,
    )
    return fig


# ---------------------------------------------------------------------------
# 9. Correlation heatmap (lower-triangle with significance stars)
# ---------------------------------------------------------------------------

def build_correlation_heatmap(
    corr_matrix: pd.DataFrame | dict,
    p_matrix: pd.DataFrame | dict | None = None,
) -> go.Figure:
    """Lower-triangle correlation heatmap with optional significance stars."""
    if isinstance(corr_matrix, dict):
        corr_df = pd.DataFrame(corr_matrix)
    else:
        corr_df = corr_matrix.copy()

    if p_matrix is not None:
        if isinstance(p_matrix, dict):
            p_df = pd.DataFrame(p_matrix)
        else:
            p_df = p_matrix.copy()
    else:
        p_df = None

    labels = corr_df.columns.tolist()
    n = len(labels)

    # Build masked matrix (lower triangle only) and annotation text
    z_masked = np.full((n, n), np.nan)
    text_matrix = [[""] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if j <= i:  # lower triangle + diagonal
                r_val = corr_df.iloc[i, j]
                z_masked[i, j] = r_val
                stars = ""
                if p_df is not None and j < i:
                    p_val = p_df.iloc[i, j]
                    if p_val < 0.001:
                        stars = "***"
                    elif p_val < 0.01:
                        stars = "**"
                    elif p_val < 0.05:
                        stars = "*"
                text_matrix[i][j] = f"{r_val:.2f}{stars}"

    fig = go.Figure(data=go.Heatmap(
        z=z_masked,
        x=labels,
        y=labels,
        colorscale=[
            [0, CB_PALETTE[1]],      # magenta for -1
            [0.5, "#F5F5F7"],        # near-white for 0 (not pure white on light bg)
            [1, CB_PALETTE[0]],      # blue for +1
        ],
        zmin=-1,
        zmax=1,
        text=text_matrix,
        texttemplate="%{text}",
        textfont=dict(size=11),
        hovertemplate="%{y} vs %{x}<br>r = %{z:.3f}<extra></extra>",
        colorbar=dict(title="r", len=0.8),
    ))

    fig.update_layout(
        **_BASE_LAYOUT,
        height=max(350, 60 * n),
        width=max(350, 60 * n),
        xaxis_tickangle=-45,
    )
    return fig


# ---------------------------------------------------------------------------
# 10. Slopegraph (paired before/after with connecting lines)
# ---------------------------------------------------------------------------

def build_slopegraph(
    before: np.ndarray,
    after: np.ndarray,
    labels: list[str] | None = None,
    p_value: float | None = None,
) -> go.Figure:
    """Paired before/after slopegraph with connecting lines."""
    before = np.asarray(before, dtype=float)
    after = np.asarray(after, dtype=float)
    # Ensure equal lengths (truncate to shorter)
    n = min(len(before), len(after))
    before = before[:n]
    after = after[:n]
    if n == 0:
        fig = go.Figure()
        fig.update_layout(**_BASE_LAYOUT, height=400)
        fig.add_annotation(text="No data to display", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig

    fig = go.Figure()

    # Individual lines
    for i in range(n):
        change = after[i] - before[i]
        color = CB_PALETTE[0] if change >= 0 else CB_PALETTE[1]
        lbl = labels[i] if labels else f"Sample {i + 1}"
        fig.add_trace(go.Scatter(
            x=["Before", "After"],
            y=[before[i], after[i]],
            mode="lines+markers",
            line=dict(color=color, width=1.5),
            marker=dict(color=color, size=7),
            name=lbl,
            showlegend=False,
            hovertemplate=f"<b>{lbl}</b><br>%{{x}}: %{{y:.3f}}<extra></extra>",
        ))

    # Mean line (bold)
    mean_before = float(np.nanmean(before))
    mean_after = float(np.nanmean(after))
    fig.add_trace(go.Scatter(
        x=["Before", "After"],
        y=[mean_before, mean_after],
        mode="lines+markers",
        line=dict(color=CB_PALETTE[5], width=3),
        marker=dict(color=CB_PALETTE[5], size=10),
        name="Mean",
        hovertemplate="<b>Mean</b><br>%{x}: %{y:.3f}<extra></extra>",
    ))

    if p_value is not None:
        p_text = f"p = {p_value:.4f}" if p_value >= 0.001 else "p < 0.001"
        fig.add_annotation(
            text=f"Paired test: {p_text}",
            xref="paper", yref="paper", x=0.5, y=1.05,
            showarrow=False,
            font=dict(size=12, color="rgba(60,60,67,0.75)"),
        )

    fig.update_layout(
        **_BASE_LAYOUT,
        height=400,
        yaxis_title="Value",
    )
    return fig


# ---------------------------------------------------------------------------
# 11. Interaction plot (two-way ANOVA)
# ---------------------------------------------------------------------------

def build_interaction_plot(
    df: pd.DataFrame,
    dv: str,
    factor_a: str,
    factor_b: str,
) -> go.Figure:
    """Two-way interaction plot: factor_a on x-axis, lines per factor_b level.

    Displays mean +/- SEM for each cell.
    """
    grouped = df.groupby([factor_a, factor_b])[dv].agg(["mean", "sem"]).reset_index()

    fig = go.Figure()
    for i, level_b in enumerate(df[factor_b].unique()):
        subset = grouped[grouped[factor_b] == level_b]
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Scatter(
            x=subset[factor_a].astype(str),
            y=subset["mean"],
            error_y=dict(type="data", array=subset["sem"].tolist(), visible=True),
            mode="lines+markers",
            name=f"{factor_b}={level_b}",
            marker=dict(color=color, size=10),
            line=dict(color=color, width=2.5),
            hovertemplate=(
                f"{factor_a}: %{{x}}<br>"
                f"Mean {dv}: %{{y:.3f}} \u00b1 %{{error_y.array:.3f}}<br>"
                f"{factor_b}: {level_b}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=factor_a,
        yaxis_title=f"Mean {dv} (\u00b1 SEM)",
        height=450,
        legend=dict(orientation="h", y=-0.15),
    )
    return fig


# ---------------------------------------------------------------------------
# 12. ROC chart
# ---------------------------------------------------------------------------

def build_roc_chart(
    fpr: list[float] | np.ndarray,
    tpr: list[float] | np.ndarray,
    auc_score: float,
    thresholds: list[float] | np.ndarray | None = None,
) -> go.Figure:
    """ROC curve with diagonal reference line and AUC annotation."""
    fpr = np.asarray(fpr)
    tpr = np.asarray(tpr)

    fig = go.Figure()

    # Chance line
    fig.add_trace(go.Scatter(
        x=[0, 1], y=[0, 1], mode="lines",
        line=dict(color="rgba(60,60,67,0.3)", width=1.5, dash="dash"),
        name="Chance (AUC = 0.5)",
        hoverinfo="skip",
    ))

    # ROC curve
    hover = "FPR: %{x:.3f}<br>TPR: %{y:.3f}<extra></extra>"
    fig.add_trace(go.Scatter(
        x=fpr, y=tpr, mode="lines",
        line=dict(color=CB_PALETTE[0], width=2.5),
        fill="tonexty",
        fillcolor=_hex_to_rgba(CB_PALETTE[0], 0.1),
        name=f"AUC = {auc_score:.3f}",
        hovertemplate=hover,
    ))

    # Optimal threshold point (Youden's J)
    if thresholds is not None and len(fpr) > 0 and len(tpr) > 0:
        thresholds = np.asarray(thresholds)
        j_scores = tpr - fpr
        if len(j_scores) > 0:
            opt_idx = int(np.argmax(j_scores))
            fig.add_trace(go.Scatter(
                x=[fpr[opt_idx]], y=[tpr[opt_idx]], mode="markers",
                marker=dict(color=CB_PALETTE[1], size=12, symbol="star"),
                name=f"Optimal (thresh={thresholds[opt_idx]:.3f})",
                hovertemplate=(
                    f"Optimal threshold: {thresholds[opt_idx]:.3f}<br>"
                    f"Sensitivity: {tpr[opt_idx]:.3f}<br>"
                    f"Specificity: {1 - fpr[opt_idx]:.3f}<extra></extra>"
                ),
            ))

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="False Positive Rate (1 - Specificity)",
        yaxis_title="True Positive Rate (Sensitivity)",
        xaxis_range=[-0.02, 1.02],
        yaxis_range=[-0.02, 1.02],
        height=450,
        legend=dict(x=0.4, y=0.05),
    )
    return fig


# ---------------------------------------------------------------------------
# 13. Bland-Altman chart
# ---------------------------------------------------------------------------

def build_bland_altman_chart(
    ba_result: dict,
) -> go.Figure:
    """Bland-Altman plot: scatter of mean vs difference with LoA lines.

    ``ba_result`` must contain keys: ``means``, ``diffs``, ``mean_diff``,
    ``upper_loa``, ``lower_loa``.
    """
    # Validate required keys
    required_keys = ("means", "diffs", "mean_diff", "upper_loa", "lower_loa")
    missing = [k for k in required_keys if k not in ba_result]
    if missing:
        fig = go.Figure()
        fig.update_layout(**_BASE_LAYOUT, height=450)
        fig.add_annotation(
            text=f"Missing data: {', '.join(missing)}",
            xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False,
        )
        return fig

    fig = go.Figure()

    # Scatter
    fig.add_trace(go.Scatter(
        x=ba_result["means"],
        y=ba_result["diffs"],
        mode="markers",
        marker=dict(color=CB_PALETTE[0], size=7, opacity=0.7),
        name="Observations",
        hovertemplate="Mean: %{x:.3f}<br>Difference: %{y:.3f}<extra></extra>",
    ))

    mean_diff = ba_result["mean_diff"]
    upper_loa = ba_result["upper_loa"]
    lower_loa = ba_result["lower_loa"]

    # Mean difference line
    fig.add_hline(
        y=mean_diff,
        line_color=CB_PALETTE[1],
        line_width=2,
        annotation_text=f"Mean diff: {mean_diff:.3f}",
        annotation_position="right",
    )

    # Upper limit of agreement
    fig.add_hline(
        y=upper_loa,
        line_dash="dash",
        line_color=CB_PALETTE[2],
        annotation_text=f"+1.96 SD: {upper_loa:.3f}",
        annotation_position="right",
    )

    # Lower limit of agreement
    fig.add_hline(
        y=lower_loa,
        line_dash="dash",
        line_color=CB_PALETTE[2],
        annotation_text=f"-1.96 SD: {lower_loa:.3f}",
        annotation_position="right",
    )

    # Zero reference
    fig.add_hline(y=0, line_color="rgba(60,60,67,0.15)", line_width=1)

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Mean of Two Methods",
        yaxis_title="Difference Between Methods",
        height=450,
    )
    return fig


# ---------------------------------------------------------------------------
# 14. Odds ratio forest plot
# ---------------------------------------------------------------------------

def build_odds_ratio_forest(
    labels: list[str],
    odds_ratios: list[float] | np.ndarray,
    ci_lower: list[float] | np.ndarray,
    ci_upper: list[float] | np.ndarray,
) -> go.Figure:
    """Horizontal forest plot with CI whiskers and null line at 1.0."""
    odds_ratios = np.asarray(odds_ratios, dtype=float)
    ci_lower = np.asarray(ci_lower, dtype=float)
    ci_upper = np.asarray(ci_upper, dtype=float)

    fig = go.Figure()

    for i, name in enumerate(labels):
        # Color significant (CI does not cross 1.0) vs non-significant
        significant = not (ci_lower[i] <= 1.0 <= ci_upper[i])
        color = CB_PALETTE[0] if significant else "rgba(142,142,147,0.6)"
        fig.add_trace(go.Scatter(
            x=[odds_ratios[i]],
            y=[name],
            error_x=dict(
                type="data",
                symmetric=False,
                array=[ci_upper[i] - odds_ratios[i]],
                arrayminus=[odds_ratios[i] - ci_lower[i]],
            ),
            mode="markers",
            marker=dict(color=color, size=10, symbol="diamond"),
            name=name,
            showlegend=False,
            hovertemplate=(
                f"<b>{name}</b><br>"
                f"OR: %{{x:.2f}} (95% CI: {ci_lower[i]:.2f}\u2013{ci_upper[i]:.2f})"
                f"<extra></extra>"
            ),
        ))

    # Null line at OR = 1.0
    fig.add_vline(x=1, line_dash="dash", line_color="rgba(60,60,67,0.3)")

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Odds Ratio (95% CI)",
        xaxis_type="log",
        height=max(250, 50 * len(labels)),
    )
    return fig


# ---------------------------------------------------------------------------
# 15. Contingency chart (grouped bar)
# ---------------------------------------------------------------------------

def build_contingency_chart(
    contingency_table: pd.DataFrame | dict,
) -> go.Figure:
    """Grouped bar chart for 2x2 or larger contingency tables."""
    if isinstance(contingency_table, dict):
        ct_df = pd.DataFrame(contingency_table)
    else:
        ct_df = contingency_table.copy()

    fig = go.Figure()
    for i, col in enumerate(ct_df.columns):
        color = CB_PALETTE[i % len(CB_PALETTE)]
        fig.add_trace(go.Bar(
            x=ct_df.index.astype(str),
            y=ct_df[col],
            name=str(col),
            marker_color=color,
            hovertemplate=f"{col}<br>Count: %{{y}}<extra></extra>",
        ))

    fig.update_layout(
        **_BASE_LAYOUT,
        barmode="group",
        xaxis_title="Category",
        yaxis_title="Count",
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# 16. PCA biplot
# ---------------------------------------------------------------------------

def build_pca_biplot(
    scores: list[dict] | pd.DataFrame,
    loadings: dict[str, list[float]],
    feature_names: list[str],
    explained_var: list[float],
) -> go.Figure:
    """2D scatter of PC1 vs PC2 with loading arrows and explained variance.

    Parameters
    ----------
    scores : list of dicts or DataFrame
        Each entry must have ``PC1`` and ``PC2`` keys. May also have
        ``color`` (group label) and ``label`` (point label).
    loadings : dict
        ``{feature_name: [pc1_loading, pc2_loading, ...]}``.
    feature_names : list[str]
        Feature names matching the loadings keys.
    explained_var : list[float]
        Explained variance ratio per component (0-1 scale).
    """
    if isinstance(scores, pd.DataFrame):
        score_dicts = scores.to_dict("records")
    else:
        score_dicts = scores

    fig = go.Figure()

    # Determine if color grouping is available
    has_color = len(score_dicts) > 0 and "color" in score_dicts[0]

    if has_color:
        unique_groups = list(dict.fromkeys(s["color"] for s in score_dicts))
        color_map = {c: CB_PALETTE[i % len(CB_PALETTE)] for i, c in enumerate(unique_groups)}

        for grp in unique_groups:
            grp_scores = [s for s in score_dicts if s["color"] == grp]
            fig.add_trace(go.Scatter(
                x=[s["PC1"] for s in grp_scores],
                y=[s["PC2"] for s in grp_scores],
                mode="markers",
                marker=dict(color=color_map[grp], size=7, opacity=0.7),
                name=str(grp),
                hovertemplate=(
                    "PC1: %{x:.2f}<br>PC2: %{y:.2f}<br>"
                    + (("%{text}<br>" if any("label" in s for s in grp_scores) else ""))
                    + "<extra>%{fullData.name}</extra>"
                ),
                text=[s.get("label", "") for s in grp_scores],
            ))
    else:
        fig.add_trace(go.Scatter(
            x=[s["PC1"] for s in score_dicts],
            y=[s["PC2"] for s in score_dicts],
            mode="markers",
            marker=dict(color=CB_PALETTE[0], size=7, opacity=0.7),
            name="Scores",
            hovertemplate="PC1: %{x:.2f}<br>PC2: %{y:.2f}<extra></extra>",
        ))

    # Loading vectors as arrows
    scale = 3.0  # scale for visibility
    for feat in feature_names:
        if feat not in loadings:
            continue
        load = loadings[feat]
        if len(load) < 2:
            continue
        fig.add_annotation(
            ax=0, ay=0,
            x=load[0] * scale, y=load[1] * scale,
            arrowhead=3, arrowsize=1.5, arrowwidth=1.5,
            arrowcolor=CB_PALETTE[1],
            xref="x", yref="y", axref="x", ayref="y",
        )
        fig.add_annotation(
            x=load[0] * scale * 1.15,
            y=load[1] * scale * 1.15,
            text=feat,
            showarrow=False,
            font=dict(size=10, color=CB_PALETTE[1]),
        )

    pc1_var = f" ({explained_var[0] * 100:.1f}%)" if len(explained_var) > 0 else ""
    pc2_var = f" ({explained_var[1] * 100:.1f}%)" if len(explained_var) > 1 else ""

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title=f"PC1{pc1_var}",
        yaxis_title=f"PC2{pc2_var}",
        height=450,
    )
    return fig


# ---------------------------------------------------------------------------
# 17. Scree plot (bar + cumulative line)
# ---------------------------------------------------------------------------

def build_scree_plot(
    explained_variance_ratio: list[float] | np.ndarray,
) -> go.Figure:
    """Scree plot: bars for individual variance, line for cumulative."""
    evr = np.asarray(explained_variance_ratio)
    cumvar = np.cumsum(evr)
    pcs = [f"PC{i + 1}" for i in range(len(evr))]

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=pcs,
        y=(evr * 100).tolist(),
        marker_color=CB_PALETTE[0],
        name="Individual",
        hovertemplate="PC: %{x}<br>Variance: %{y:.1f}%<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=pcs,
        y=(cumvar * 100).tolist(),
        mode="lines+markers",
        line=dict(color=CB_PALETTE[1], width=2),
        marker=dict(color=CB_PALETTE[1], size=8),
        name="Cumulative",
        hovertemplate="PC: %{x}<br>Cumulative: %{y:.1f}%<extra></extra>",
    ))

    # 80% threshold
    fig.add_hline(
        y=80,
        line_dash="dash",
        line_color="rgba(60,60,67,0.3)",
        annotation_text="80% threshold",
        annotation_position="right",
    )

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Principal Component",
        yaxis_title="Variance Explained (%)",
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# 18. Elbow plot (K-means)
# ---------------------------------------------------------------------------

def build_elbow_plot(
    k_values: list[int] | np.ndarray,
    inertias: list[float] | np.ndarray,
) -> go.Figure:
    """Line plot of inertia vs K with optimal K annotated."""
    k_values = np.asarray(k_values)
    inertias = np.asarray(inertias, dtype=float)

    # Heuristic for optimal K: largest second derivative (elbow)
    optimal_k = int(k_values[0])
    if len(k_values) >= 3:
        diffs = np.diff(inertias)
        diffs2 = np.diff(diffs)
        if len(diffs2) > 0:
            optimal_idx = int(np.argmax(np.abs(diffs2))) + 1
            optimal_k = int(k_values[optimal_idx])

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=k_values.tolist(),
        y=inertias.tolist(),
        mode="lines+markers",
        line=dict(color=CB_PALETTE[0], width=2.5),
        marker=dict(color=CB_PALETTE[0], size=8),
        name="Inertia",
        hovertemplate="K = %{x}<br>Inertia: %{y:.1f}<extra></extra>",
    ))

    # Mark optimal K
    _where = np.where(k_values == optimal_k)[0]
    opt_idx = int(_where[0]) if len(_where) > 0 else 0
    fig.add_trace(go.Scatter(
        x=[int(optimal_k)],
        y=[float(inertias[opt_idx])],
        mode="markers",
        marker=dict(color=CB_PALETTE[1], size=14, symbol="star"),
        name=f"Optimal K = {optimal_k}",
        hovertemplate=f"Optimal K = {optimal_k}<br>Inertia: {inertias[opt_idx]:.1f}<extra></extra>",
    ))

    fig.add_annotation(
        x=int(optimal_k),
        y=float(inertias[opt_idx]),
        text=f"K = {optimal_k}",
        showarrow=True,
        arrowhead=2,
        ax=30, ay=-30,
        font=dict(size=12, color=CB_PALETTE[1]),
    )

    fig.update_layout(
        **_BASE_LAYOUT,
        xaxis_title="Number of Clusters (K)",
        yaxis_title="Inertia (Within-Cluster SS)",
        height=350,
    )
    return fig


# ---------------------------------------------------------------------------
# 19. Regression diagnostics (2x2 subplot)
# ---------------------------------------------------------------------------

def build_regression_diagnostics(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    residuals: np.ndarray,
) -> go.Figure:
    """2x2 subplot: actual vs predicted, residuals vs predicted, Q-Q, residual histogram."""
    from scipy import stats

    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    residuals = np.asarray(residuals, dtype=float)

    fig = make_subplots(
        rows=2, cols=2,
        subplot_titles=(
            "Actual vs Predicted",
            "Residuals vs Predicted",
            "Q-Q Plot",
            "Residual Distribution",
        ),
        horizontal_spacing=0.12,
        vertical_spacing=0.14,
    )

    # --- (1,1) Actual vs Predicted ---
    fig.add_trace(
        go.Scatter(
            x=y_pred, y=y_true, mode="markers",
            marker=dict(color=CB_PALETTE[0], size=6),
            hovertemplate="Predicted: %{x:.3f}<br>Actual: %{y:.3f}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=1,
    )
    # Perfect prediction line
    all_vals = np.concatenate([y_true, y_pred])
    mn_val, mx_val = float(np.nanmin(all_vals)), float(np.nanmax(all_vals))
    fig.add_trace(
        go.Scatter(
            x=[mn_val, mx_val], y=[mn_val, mx_val], mode="lines",
            line=dict(color=CB_PALETTE[1], width=1.5, dash="dash"),
            hoverinfo="skip",
            showlegend=False,
        ),
        row=1, col=1,
    )

    # --- (1,2) Residuals vs Predicted ---
    fig.add_trace(
        go.Scatter(
            x=y_pred, y=residuals, mode="markers",
            marker=dict(color=CB_PALETTE[0], size=6),
            hovertemplate="Predicted: %{x:.3f}<br>Residual: %{y:.3f}<extra></extra>",
            showlegend=False,
        ),
        row=1, col=2,
    )
    fig.add_hline(
        y=0, row=1, col=2,
        line=dict(color="rgba(60,60,67,0.3)", width=1, dash="dash"),
    )

    # --- (2,1) Q-Q plot ---
    theoretical = stats.probplot(residuals, dist="norm")[0]
    fig.add_trace(
        go.Scatter(
            x=theoretical[0], y=theoretical[1], mode="markers",
            marker=dict(color=CB_PALETTE[0], size=6),
            hovertemplate="Theoretical: %{x:.3f}<br>Sample: %{y:.3f}<extra></extra>",
            showlegend=False,
        ),
        row=2, col=1,
    )
    qq_mn, qq_mx = float(np.min(theoretical[0])), float(np.max(theoretical[0]))
    fig.add_trace(
        go.Scatter(
            x=[qq_mn, qq_mx], y=[qq_mn, qq_mx], mode="lines",
            line=dict(color=CB_PALETTE[1], width=1.5, dash="dash"),
            hoverinfo="skip",
            showlegend=False,
        ),
        row=2, col=1,
    )

    # --- (2,2) Residual histogram ---
    fig.add_trace(
        go.Histogram(
            x=residuals,
            nbinsx=min(30, max(8, len(residuals) // 5)),
            marker_color=_hex_to_rgba(CB_PALETTE[0], 0.6),
            marker_line=dict(color=CB_PALETTE[0], width=1),
            hovertemplate="Bin: %{x}<br>Count: %{y}<extra></extra>",
            showlegend=False,
        ),
        row=2, col=2,
    )

    # Axis labels
    fig.update_xaxes(title_text="Predicted", row=1, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Actual", row=1, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_xaxes(title_text="Predicted", row=1, col=2, gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Residual", row=1, col=2, gridcolor="rgba(0,0,0,0.08)")
    fig.update_xaxes(title_text="Theoretical Quantiles", row=2, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Sample Quantiles", row=2, col=1, gridcolor="rgba(0,0,0,0.08)")
    fig.update_xaxes(title_text="Residual", row=2, col=2, gridcolor="rgba(0,0,0,0.08)")
    fig.update_yaxes(title_text="Count", row=2, col=2, gridcolor="rgba(0,0,0,0.08)")

    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Nunito, system-ui, sans-serif", color="rgba(60,60,67,0.6)", size=12),
        margin=dict(t=40, b=50, l=60, r=20),
        height=500,
        showlegend=False,
    )

    # Style subplot title annotations
    for annotation in fig.layout.annotations:
        annotation.update(font=dict(size=12, color="rgba(60,60,67,0.75)"))

    return fig
