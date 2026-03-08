from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from src.models import PredictionResult, ProteinQuery


def render_affinity_panel(query: ProteinQuery, prediction: PredictionResult):
    """Render binding affinity results from Boltz-2 — a feature AlphaFold can't do."""
    affinity = prediction.affinity_json
    if not affinity:
        return

    st.markdown("#### Binding Affinity Prediction")
    st.caption(
        "Boltz-2 uniquely predicts binding affinity alongside structure "
        "-- achieving accuracy comparable to physics-based FEP methods at 1000x speed."
    )

    # Extract affinity values with safe defaults
    delta_g = affinity.get("delta_g")
    kd = affinity.get("kd")
    ic50 = affinity.get("ic50")
    confidence = affinity.get("affinity_confidence")

    # Display metrics
    metric_cols = st.columns(4)
    if delta_g is not None:
        metric_cols[0].metric(
            "Binding Energy (dG)",
            f"{delta_g:.2f} kcal/mol",
            delta="Favorable" if delta_g < -7 else "Moderate" if delta_g < -5 else "Weak",
            delta_color="normal" if delta_g < -7 else "off",
        )
    if kd is not None:
        kd_str = _format_kd(kd)
        metric_cols[1].metric("Kd", kd_str)
    if ic50 is not None:
        metric_cols[2].metric("IC50", f"{ic50:.1f} nM" if ic50 > 1 else f"{ic50*1000:.0f} pM")
    if confidence is not None:
        metric_cols[3].metric(
            "Affinity Confidence",
            f"{confidence:.2f}",
            delta="Reliable" if confidence > 0.7 else "Use caution",
            delta_color="normal" if confidence > 0.7 else "off",
        )

    # Affinity comparison chart if multiple poses/compounds
    poses = affinity.get("poses", [])
    if poses and len(poses) > 1:
        _render_pose_comparison(poses)
        _render_pose_gallery(poses)

    # Interpretation
    if delta_g is not None:
        _render_affinity_interpretation(query, delta_g, kd, confidence)


def _format_kd(kd: float) -> str:
    """Format Kd in appropriate units."""
    if kd < 1e-9:
        return f"{kd * 1e12:.1f} pM"
    elif kd < 1e-6:
        return f"{kd * 1e9:.1f} nM"
    elif kd < 1e-3:
        return f"{kd * 1e6:.1f} uM"
    else:
        return f"{kd * 1e3:.1f} mM"


def _render_pose_comparison(poses: list[dict]):
    """Show comparison of multiple binding poses."""
    names = [p.get("name", f"Pose {i+1}") for i, p in enumerate(poses)]
    energies = [p.get("delta_g", 0) for p in poses]
    confidences = [p.get("confidence", 0) for p in poses]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=names,
        y=energies,
        marker_color=["#0053D6" if c > 0.7 else "#FFDB13" if c > 0.5 else "#FF7D45"
                       for c in confidences],
        text=[f"Conf: {c:.2f}" for c in confidences],
        hovertemplate="%{x}<br>dG: %{y:.2f} kcal/mol<br>%{text}<extra></extra>",
    ))
    fig.update_layout(
        yaxis_title="Binding Energy (kcal/mol)",
        template="plotly_white",
        height=250,
        margin=dict(t=10, b=40, l=50, r=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
        yaxis=dict(gridcolor="rgba(0,0,0,0.08)"),
    )
    st.plotly_chart(fig, use_container_width=True)


def _render_pose_gallery(poses: list[dict]):
    """Detailed pose gallery showing individual binding mode characteristics."""
    st.markdown("#### Binding Pose Gallery")
    st.caption(
        "Each pose represents a distinct binding conformation. "
        "Multiple high-confidence poses suggest conformational flexibility."
    )

    # Show up to 6 poses in a grid
    display_poses = poses[:6]
    cols = st.columns(min(3, len(display_poses)))

    for i, pose in enumerate(display_poses):
        col = cols[i % len(cols)]
        name = pose.get("name", f"Pose {i + 1}")
        dg = pose.get("delta_g")
        conf = pose.get("confidence", 0)
        kd_val = pose.get("kd")
        rmsd = pose.get("rmsd")

        conf_color = "#34C759" if conf > 0.7 else "#FF9500" if conf > 0.5 else "#FF3B30"
        rank_label = "Best" if i == 0 else f"#{i + 1}"

        energy_str = f"{dg:.2f} kcal/mol" if dg is not None else "N/A"
        kd_str = f"Kd: {_format_kd(kd_val)}" if kd_val is not None else ""
        rmsd_str = f"RMSD: {rmsd:.2f} Å" if rmsd is not None else ""
        extras = " | ".join(filter(None, [kd_str, rmsd_str]))

        col.markdown(
            f'<div style="background:#F2F2F7;padding:10px;border-radius:8px;'
            f'border:1px solid {"#007AFF" if i == 0 else "#C6C6C8"};margin-bottom:8px">'
            f'<div style="display:flex;justify-content:space-between;align-items:center">'
            f'<span style="font-weight:700;font-size:0.95em">{name}</span>'
            f'<span style="background:{"rgba(0,122,255,0.06)" if i == 0 else "#E5E5EA"};'
            f'padding:1px 8px;border-radius:10px;font-size:0.75em;color:rgba(60,60,67,0.6)">'
            f'{rank_label}</span></div>'
            f'<div style="font-size:1.3em;font-weight:800;color:{conf_color};'
            f'margin:6px 0">{energy_str}</div>'
            f'<div style="font-size:0.82em;color:rgba(60,60,67,0.6)">Confidence: '
            f'<span style="color:{conf_color};font-weight:600">{conf:.2f}</span></div>'
            f'{"<div style=font-size:0.78em;color:rgba(60,60,67,0.55);margin-top:2px>" + extras + "</div>" if extras else ""}'
            f'</div>',
            unsafe_allow_html=True,
        )

    if len(poses) > 6:
        st.caption(f"Showing top 6 of {len(poses)} poses.")


def _render_affinity_interpretation(
    query: ProteinQuery,
    delta_g: float,
    kd: float | None,
    confidence: float | None,
):
    """Provide human-readable interpretation of binding affinity."""
    if delta_g < -9:
        strength = "very strong"
        emoji = "green"
    elif delta_g < -7:
        strength = "strong"
        emoji = "green"
    elif delta_g < -5:
        strength = "moderate"
        emoji = "orange"
    else:
        strength = "weak"
        emoji = "red"

    partner = query.interaction_partner or "the binding partner"
    msg = (
        f"The predicted binding of {query.protein_name} to {partner} is **{strength}** "
        f"(dG = {delta_g:.2f} kcal/mol)."
    )
    if kd is not None:
        msg += f" Estimated Kd: {_format_kd(kd)}."

    if confidence is not None and confidence < 0.5:
        msg += (
            " **Caution:** Affinity prediction confidence is low. "
            "Boltz-2 binding affinity predictions have ~40% false positive rate "
            "for ligand poses. Validate with SPR or ITC."
        )

    if emoji == "green":
        st.success(msg)
    elif emoji == "orange":
        st.warning(msg)
    else:
        st.error(msg)
