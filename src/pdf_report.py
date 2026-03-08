"""PDF report generator using fpdf2 + matplotlib.

Produces an industry-standard clinical genomics-style PDF report with
branded header, metric cards, charts, color-coded tables, and AI narrative.
Zero system dependencies — pure Python.
"""
from __future__ import annotations

import hashlib
import io
import re
import uuid
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from fpdf import FPDF
from matplotlib.colors import LinearSegmentedColormap

from src.models import BioContext, PredictionResult, ProteinQuery, TrustAudit
from src.utils import trust_to_color

_APP_VERSION = "0.1.0"

# ─── Color Helpers ────────────────────────────────────────────────

def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


_BG = (255, 255, 255)
_BG2 = _hex_to_rgb("#F2F2F7")
_BORDER = _hex_to_rgb("#D0D5DD")
_TEXT = _hex_to_rgb("#1A1A2E")
_MUTED = _hex_to_rgb("#8E8E93")
_BLUE = _hex_to_rgb("#007AFF")
_CYAN = _hex_to_rgb("#0891B2")
_GREEN = _hex_to_rgb("#34C759")
_AMBER = _hex_to_rgb("#FF9500")
_RED = _hex_to_rgb("#FF3B30")
_ORANGE = _hex_to_rgb("#FF9500")
_YELLOW = _hex_to_rgb("#CA8A04")
_DEEP_BLUE = _hex_to_rgb("#1D4ED8")
_WHITE = (255, 255, 255)
_BANNER_BG = _hex_to_rgb("#1E3A5F")
_RUO_RED = _hex_to_rgb("#991B1B")


def _conf_color(score: float) -> tuple[int, int, int]:
    if score >= 0.7:
        return _GREEN
    if score >= 0.5:
        return _AMBER
    return _RED


def _plddt_color(score: float) -> tuple[int, int, int]:
    return _hex_to_rgb(trust_to_color(score))


# ─── Font Discovery ──────────────────────────────────────────────

def _find_fonts() -> tuple[str, str, str, str]:
    """Find Unicode-capable TTF fonts. Returns (regular, bold, italic, bold_italic)."""
    candidates = [
        # macOS
        ("/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
         "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"),
        # Linux (DejaVu)
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
        # Linux alternative
        ("/usr/share/fonts/TTF/DejaVuSans.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-Oblique.ttf",
         "/usr/share/fonts/TTF/DejaVuSans-BoldOblique.ttf"),
    ]
    for reg, bold, ital, bi in candidates:
        if Path(reg).exists():
            bold = bold if Path(bold).exists() else reg
            ital = ital if Path(ital).exists() else reg
            bi = bi if Path(bi).exists() else bold
            return reg, bold, ital, bi
    return "", "", "", ""


# ─── Custom PDF Class ────────────────────────────────────────────

class LuminousPDF(FPDF):
    """Custom FPDF subclass with Luminous branding."""

    _FONT = "BVFont"
    _use_unicode = False
    _header_label = ""
    _report_id = ""
    _fig_counter = 0
    _tbl_counter = 0
    _sec_counter = 0

    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(left=15, top=15, right=15)

        reg, bold, ital, bi = _find_fonts()
        if reg:
            try:
                self.add_font(self._FONT, "", reg)
                self.add_font(self._FONT, "B", bold)
                self.add_font(self._FONT, "I", ital)
                self.add_font(self._FONT, "BI", bi)
                self._use_unicode = True
            except Exception:
                self._FONT = "Helvetica"
        else:
            self._FONT = "Helvetica"

        self.add_page()

    @staticmethod
    def _safe(text: str) -> str:
        if not text:
            return ""
        return (
            str(text)
            .replace("\u2014", " - ")
            .replace("\u2013", "-")
            .replace("\u2018", "'")
            .replace("\u2019", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
            .replace("\u2026", "...")
            .replace("\u2265", ">=")
            .replace("\u2264", "<=")
            .replace("\u2122", "(TM)")
            .replace("\u00b0", " deg")
        )

    def next_fig(self) -> int:
        self._fig_counter += 1
        return self._fig_counter

    def next_tbl(self) -> int:
        self._tbl_counter += 1
        return self._tbl_counter

    def header(self):
        self.set_font(self._FONT, "I", 7)
        self.set_text_color(*_MUTED)
        self.set_xy(15, 5)
        label = f"Luminous | {self._header_label}" if self._header_label else "Luminous"
        self.cell(0, 4, label, align="L")
        self.set_xy(15, 5)
        right_txt = f"{self._report_id}   Page {self.page_no()}/{{nb}}"
        self.cell(0, 4, right_txt, align="R")
        self.ln(8)

    def footer(self):
        self.set_y(-18)
        self.set_font(self._FONT, "I", 6)
        self.set_text_color(*_MUTED)
        self.cell(0, 3, "FOR RESEARCH USE ONLY  |  Not for clinical diagnostic use", align="C")
        self.ln(3)
        self.cell(
            0, 3,
            f"Luminous v{_APP_VERSION}  |  Generated {datetime.now().strftime('%B %d, %Y at %H:%M')}",
            align="C",
        )

    def section_header(self, text: str):
        self._sec_counter += 1
        num = self._sec_counter
        if self.get_y() + 15 > 275:
            self.add_page()
        self.set_font(self._FONT, "B", 14)
        self.set_text_color(*_DEEP_BLUE)
        full = f"{num}. {self._safe(text)}"
        self.cell(0, 8, full, new_x="LMARGIN", new_y="NEXT")
        # PDF bookmark for navigation
        self.start_section(full, level=0)
        y = self.get_y()
        self.set_draw_color(*_BORDER)
        self.line(15, y, 195, y)
        self.ln(4)

    def subsection_header(self, text: str):
        if self.get_y() + 12 > 275:
            self.add_page()
        self.set_font(self._FONT, "B", 11)
        self.set_text_color(*_BLUE)
        self.cell(0, 6, self._safe(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text: str, size: float = 9):
        self.set_font(self._FONT, "", size)
        self.set_text_color(*_TEXT)
        self.multi_cell(0, 4.5, self._safe(text))
        self.ln(2)

    def muted_text(self, text: str, size: float = 8):
        self.set_font(self._FONT, "", size)
        self.set_text_color(*_MUTED)
        self.multi_cell(0, 4, self._safe(text))
        self.ln(1)

    def metric_row(self, metrics: list[tuple[str, str, tuple[int, int, int]]]):
        n = len(metrics)
        if n == 0:
            return
        if self.get_y() + 24 > 275:
            self.add_page()
        card_w = (180 / n) - 2
        start_x = 15
        y = self.get_y()
        for i, (label, value, color) in enumerate(metrics):
            x = start_x + i * (card_w + 2)
            self.set_fill_color(*_BG2)
            self.set_draw_color(*_BORDER)
            self.rect(x, y, card_w, 18, style="DF")
            self.set_font(self._FONT, "", 6.5)
            self.set_text_color(*_MUTED)
            self.set_xy(x + 2, y + 2)
            self.cell(card_w - 4, 3, label.upper(), align="C")
            self.set_font(self._FONT, "B", 14)
            self.set_text_color(*color)
            self.set_xy(x + 2, y + 6)
            self.cell(card_w - 4, 8, self._safe(value), align="C")
        self.set_y(y + 22)

    def narrative_box(self, text: str):
        safe_text = self._safe(text)
        y = self.get_y()
        self.set_font(self._FONT, "", 9)
        lines = self.multi_cell(170, 4.5, safe_text, dry_run=True, output="LINES")
        box_h = max(len(lines) * 4.5 + 10, 16)

        if y + box_h > 275:
            self.add_page()
            y = self.get_y()

        self.set_fill_color(*_BG2)
        self.rect(15, y, 180, box_h, "F")
        self.set_fill_color(*_BLUE)
        self.rect(15, y, 2.5, box_h, "F")

        self.set_xy(20, y + 4)
        self.set_font(self._FONT, "", 9)
        self.set_text_color(*_TEXT)
        self.multi_cell(168, 4.5, safe_text)
        self.set_y(y + box_h + 4)

    def add_chart(self, fig: plt.Figure, caption: str = ""):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=200, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        buf.seek(0)

        if self.get_y() + 65 > 275:
            self.add_page()

        num = self.next_fig()
        self.image(buf, x=15, w=180)
        if caption:
            self.set_font(self._FONT, "I", 7)
            self.set_text_color(*_MUTED)
            self.cell(0, 4, f"Figure {num}. {caption}", align="C",
                      new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def data_table(
        self,
        headers: list[str],
        rows: list[list[str]],
        col_widths: list[float] | None = None,
        row_colors: list[tuple[int, int, int] | None] | None = None,
        color_col: int | None = None,
        table_label: str = "",
    ):
        if not rows:
            return
        n_cols = len(headers)
        if col_widths is None:
            col_widths = [180 / n_cols] * n_cols

        estimated_h = (min(len(rows), 8) + 1) * 7 + 4
        if self.get_y() + estimated_h > 275:
            self.add_page()

        # Table number label
        num = self.next_tbl()
        if table_label:
            self.set_font(self._FONT, "I", 7)
            self.set_text_color(*_MUTED)
            self.cell(0, 4, f"Table {num}. {table_label}",
                      new_x="LMARGIN", new_y="NEXT")
            self.ln(1)

        # Header row
        self.set_fill_color(*_BG2)
        self.set_draw_color(*_BORDER)
        self.set_font(self._FONT, "B", 7)
        self.set_text_color(*_TEXT)
        y = self.get_y()
        for i, (header, w) in enumerate(zip(headers, col_widths)):
            x = 15 + sum(col_widths[:i])
            self.set_xy(x, y)
            self.cell(w, 7, header.upper(), fill=True, border=1, align="L")
        self.ln(7)

        # Data rows
        for ri, row in enumerate(rows):
            if self.get_y() + 7 > 275:
                self.add_page()

            if ri % 2 == 0:
                self.set_fill_color(*_BG)
            else:
                self.set_fill_color(*_BG2)

            y = self.get_y()
            for ci, (cell, w) in enumerate(zip(row, col_widths)):
                x = 15 + sum(col_widths[:ci])
                self.set_xy(x, y)

                use_color = False
                if row_colors and ri < len(row_colors) and row_colors[ri]:
                    if color_col is None or ci == color_col:
                        use_color = True

                if use_color:
                    self.set_text_color(*row_colors[ri])
                    self.set_font(self._FONT, "B", 8)
                else:
                    self.set_text_color(*_TEXT)
                    self.set_font(self._FONT, "", 8)

                cell_text = self._safe(str(cell))
                max_chars = int(w / 2.0)
                if len(cell_text) > max_chars:
                    cell_text = cell_text[:max_chars - 2] + ".."
                self.cell(w, 7, cell_text, fill=True, border=0, align="L")
            self.ln(7)

        self.set_text_color(*_TEXT)
        self.ln(3)

    def bullet_list(self, items: list[str], size: float = 8.5):
        self.set_font(self._FONT, "", size)
        self.set_text_color(*_TEXT)
        for item in items:
            if self.get_y() + 5 > 275:
                self.add_page()
            self.cell(5, 4, "-", align="R")
            self.cell(2)
            self.multi_cell(168, 4, self._safe(item))
            self.ln(1)
        self.ln(2)

    def trust_badge(self, level: str):
        color_map = {"high": _GREEN, "medium": _AMBER, "low": _RED}
        color = color_map.get(level.lower(), _MUTED)
        x, y = self.get_x(), self.get_y()
        self.set_fill_color(*color)
        self.set_draw_color(*color)
        self.rect(x, y, 22, 6, style="DF")
        self.set_font(self._FONT, "B", 7)
        self.set_text_color(*_WHITE)
        self.set_xy(x, y)
        self.cell(22, 6, level.upper(), align="C")
        self.set_xy(x + 25, y)


# ─── Amino Acid Properties ───────────────────────────────────────

_AA_PROPS: dict[str, dict] = {
    "G": {"name": "Glycine",       "charge": 0, "hydro": -0.4, "size": "tiny",   "mw": 57},
    "A": {"name": "Alanine",       "charge": 0, "hydro":  1.8, "size": "small",  "mw": 71},
    "V": {"name": "Valine",        "charge": 0, "hydro":  4.2, "size": "medium", "mw": 99},
    "L": {"name": "Leucine",       "charge": 0, "hydro":  3.8, "size": "large",  "mw": 113},
    "I": {"name": "Isoleucine",    "charge": 0, "hydro":  4.5, "size": "large",  "mw": 113},
    "P": {"name": "Proline",       "charge": 0, "hydro": -1.6, "size": "small",  "mw": 97},
    "F": {"name": "Phenylalanine", "charge": 0, "hydro":  2.8, "size": "large",  "mw": 147},
    "W": {"name": "Tryptophan",    "charge": 0, "hydro": -0.9, "size": "large",  "mw": 186},
    "M": {"name": "Methionine",    "charge": 0, "hydro":  1.9, "size": "large",  "mw": 131},
    "S": {"name": "Serine",        "charge": 0, "hydro": -0.8, "size": "small",  "mw": 87},
    "T": {"name": "Threonine",     "charge": 0, "hydro": -0.7, "size": "medium", "mw": 101},
    "C": {"name": "Cysteine",      "charge": 0, "hydro":  2.5, "size": "small",  "mw": 103},
    "Y": {"name": "Tyrosine",      "charge": 0, "hydro": -1.3, "size": "large",  "mw": 163},
    "H": {"name": "Histidine",     "charge": 1, "hydro": -3.2, "size": "medium", "mw": 137},
    "D": {"name": "Aspartate",     "charge":-1, "hydro": -3.5, "size": "medium", "mw": 115},
    "E": {"name": "Glutamate",     "charge":-1, "hydro": -3.5, "size": "large",  "mw": 129},
    "N": {"name": "Asparagine",    "charge": 0, "hydro": -3.5, "size": "medium", "mw": 114},
    "Q": {"name": "Glutamine",     "charge": 0, "hydro": -3.5, "size": "large",  "mw": 128},
    "K": {"name": "Lysine",        "charge": 1, "hydro": -3.9, "size": "large",  "mw": 128},
    "R": {"name": "Arginine",      "charge": 1, "hydro": -4.5, "size": "large",  "mw": 156},
}


# ─── Chart Renderers ─────────────────────────────────────────────

def _first_chain_data(prediction: PredictionResult) -> tuple[list[int], list[float]]:
    if not prediction.plddt_per_residue or not prediction.residue_ids:
        return [], []
    first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
    res_ids, scores = [], []
    for i, (rid, sc) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
        if i >= len(prediction.chain_ids):
            break
        if first_chain is None or prediction.chain_ids[i] == first_chain:
            res_ids.append(rid)
            scores.append(sc)
    return res_ids, scores


def _render_confidence_chart(
    prediction: PredictionResult, query: ProteinQuery,
) -> plt.Figure | None:
    res_ids, scores = _first_chain_data(prediction)
    if not res_ids:
        return None

    colors = [trust_to_color(s) for s in scores]
    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.bar(res_ids, scores, color=colors, width=1.0, edgecolor="none")

    for y_val, c, lbl in [(90, "#0053D6", "Very High"), (70, "#65CBF3", "High"), (50, "#FFDB13", "Low")]:
        ax.axhline(y=y_val, color=c, linewidth=0.7, linestyle="--", alpha=0.5)

    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation.upper())
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in res_ids:
                idx = res_ids.index(mut_pos)
                ax.scatter([mut_pos], [scores[idx]], color="#FFCC00", marker="*", s=120,
                           zorder=5, edgecolors="#FF3B30", linewidths=1.0)
                ax.annotate(query.mutation, (mut_pos, scores[idx]),
                            textcoords="offset points", xytext=(0, 8),
                            fontsize=7, color="#B45309", ha="center", weight="bold")

    ax.set_xlim(min(res_ids) - 1, max(res_ids) + 1)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Residue Number", color="#4B5563", fontsize=8)
    ax.set_ylabel("pLDDT Score", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_region_chart(trust_audit: TrustAudit) -> plt.Figure | None:
    if not trust_audit.regions:
        return None

    labels = [f"Ch {r.chain}: {r.start_residue}-{r.end_residue}" for r in trust_audit.regions]
    plddt_scores = [r.avg_plddt for r in trust_audit.regions]
    colors = [trust_to_color(s) for s in plddt_scores]
    flags = [bool(r.flag) for r in trust_audit.regions]

    fig, ax = plt.subplots(figsize=(10, 2.5))
    bars = ax.bar(range(len(labels)), plddt_scores, color=colors, edgecolor="none")

    for i, flagged in enumerate(flags):
        if flagged:
            bars[i].set_edgecolor("#FF3B30")
            bars[i].set_linewidth(2)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=6, color="#4B5563")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Avg pLDDT", color="#4B5563", fontsize=8)
    ax.axhline(y=70, color="#65CBF3", linewidth=0.7, linestyle="--", alpha=0.4)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_variant_chart(
    prediction: PredictionResult, variant_data: dict, query: ProteinQuery,
) -> plt.Figure | None:
    if not variant_data.get("pathogenic_positions"):
        return None

    res_ids, scores = _first_chain_data(prediction)
    if not res_ids:
        return None

    colors = [trust_to_color(s) for s in scores]
    fig, ax = plt.subplots(figsize=(10, 2.8))
    ax.bar(res_ids, scores, color=colors, width=1.0, edgecolor="none", alpha=0.5)

    path_pos = variant_data.get("pathogenic_positions", {})
    px, py = [], []
    for pos_str in path_pos:
        try:
            pos = int(pos_str)
        except (ValueError, TypeError):
            continue
        if pos in res_ids:
            px.append(pos)
            py.append(scores[res_ids.index(pos)])
    if px:
        ax.scatter(px, py, color="#FF3B30", marker="D", s=40, zorder=5,
                   edgecolors="white", linewidths=0.5, label="Pathogenic")

    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation.upper())
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in res_ids:
                idx = res_ids.index(mut_pos)
                ax.scatter([mut_pos], [scores[idx]], color="#FFCC00", marker="*", s=120,
                           zorder=6, edgecolors="#FF3B30", linewidths=1.0,
                           label=query.mutation)

    if px or query.mutation:
        ax.legend(loc="lower right", fontsize=7, facecolor="white",
                  edgecolor="#D0D5DD", labelcolor="#1A1A2E")

    ax.axhline(y=70, color="#65CBF3", linewidth=0.7, linestyle="--", alpha=0.4)
    ax.axhline(y=50, color="#FFDB13", linewidth=0.7, linestyle="--", alpha=0.4)
    ax.set_xlim(min(res_ids) - 1, max(res_ids) + 1)
    ax.set_ylim(0, 105)
    ax.set_xlabel("Residue Number", color="#4B5563", fontsize=8)
    ax.set_ylabel("pLDDT Score", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_variant_severity_chart(
    variant_data: dict, prediction: PredictionResult,
) -> plt.Figure | None:
    """CADD score vs allele frequency scatter for PDF."""
    variants = variant_data.get("variants", [])
    has_cadd = [v for v in variants if v.get("cadd_score") is not None]
    if not has_cadd:
        return None

    plddt_map: dict[int, float] = {}
    if prediction.plddt_per_residue and prediction.residue_ids:
        first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
        for i, (rid, sc) in enumerate(zip(prediction.residue_ids, prediction.plddt_per_residue)):
            if i >= len(prediction.chain_ids):
                break
            if first_chain is None or prediction.chain_ids[i] == first_chain:
                plddt_map[rid] = sc

    sig_colors = {
        "pathogenic": "#FF3B30", "likely_pathogenic": "#FF9500",
        "uncertain_significance": "#8E8E93", "likely_benign": "#007AFF", "benign": "#34C759",
    }

    fig, ax = plt.subplots(figsize=(10, 3.5))
    for v in has_cadd:
        cadd = v["cadd_score"]
        freq = v.get("frequency") or 1e-5
        pos = v.get("position", 0)
        sig = v.get("significance", "unknown")
        plddt = plddt_map.get(pos, 70)
        size = max(15, plddt / 2.5)
        color = sig_colors.get(sig, "#8E8E93")
        ax.scatter(freq, cadd, s=size, c=color, edgecolors="white",
                   linewidths=0.4, alpha=0.85, zorder=5)

    ax.axhline(y=20, color="#FF3B30", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axhline(y=15, color="#FF9500", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.axvline(x=0.01, color="#8E8E93", linewidth=0.8, linestyle="--", alpha=0.3)

    ax.set_xscale("log")
    ax.set_xlabel("Allele Frequency (gnomAD)", color="#4B5563", fontsize=8)
    ax.set_ylabel("CADD Phred Score", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")

    from matplotlib.lines import Line2D
    legend_elements = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#FF3B30", markersize=6, label="Pathogenic"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#FF9500", markersize=6, label="Likely Path."),
        Line2D([0], [0], marker="o", color="w", markerfacecolor="#8E8E93", markersize=6, label="VUS"),
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=6,
              facecolor="white", edgecolor="#D0D5DD", labelcolor="#1A1A2E")
    return fig


def _render_resistance_heatmap_chart(
    drug_resistance_data: list[dict],
) -> plt.Figure | None:
    """Drug x Mutation cross-resistance heatmap for PDF."""
    import numpy as np

    if not drug_resistance_data or len(drug_resistance_data) < 2:
        return None

    all_drugs = []
    for mut in drug_resistance_data:
        for d in mut.get("drugs", []):
            name = d.get("name", "")
            if name and name not in all_drugs:
                all_drugs.append(name)
    if len(all_drugs) < 2:
        return None

    mutations = [m.get("name", f"Mut{i}") for i, m in enumerate(drug_resistance_data)]
    matrix = []
    annotations = []

    for mut in drug_resistance_data:
        drug_lookup = {d["name"]: d for d in mut.get("drugs", [])}
        row, row_ann = [], []
        for drug_name in all_drugs:
            d = drug_lookup.get(drug_name)
            if d is None:
                row.append(0)
                row_ann.append("")
            else:
                fc = d.get("fold_change", "")
                status = d.get("status", "")
                combined = f"{fc} {status}".lower()
                if "sensitiz" in combined or ("sensitive" in combined and "designed" not in combined):
                    row.append(-1)
                elif "target" in combined or "designed" in combined or "reactivat" in combined:
                    row.append(-2)
                elif ">100x" in fc or ">50x" in fc:
                    row.append(3)
                elif "resistant" in combined:
                    row.append(2)
                else:
                    row.append(1)
                row_ann.append(fc if fc else status[:15])
        matrix.append(row)
        annotations.append(row_ann)

    from matplotlib.colors import LinearSegmentedColormap
    cmap = LinearSegmentedColormap.from_list("resist", [
        (0.0, "#007AFF"), (0.2, "#34C759"), (0.4, "#AEAEB2"),
        (0.6, "#FF9500"), (0.8, "#FF3B30"), (1.0, "#FFF0F0"),
    ])

    fig, ax = plt.subplots(figsize=(max(4, len(all_drugs) * 1.2), max(2, len(mutations) * 0.6)))
    data = np.array(matrix, dtype=float)
    ax.imshow(data, cmap=cmap, vmin=-2, vmax=3, aspect="auto")

    for i in range(len(mutations)):
        for j in range(len(all_drugs)):
            text = annotations[i][j]
            if text:
                ax.text(j, i, text, ha="center", va="center", fontsize=7,
                        color="white", fontweight="bold")

    ax.set_xticks(range(len(all_drugs)))
    ax.set_xticklabels([d[:20] for d in all_drugs], rotation=30, ha="right", fontsize=7, color="#4B5563")
    ax.set_yticks(range(len(mutations)))
    ax.set_yticklabels(mutations, fontsize=8, color="#1A1A2E")
    ax.tick_params(length=0)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    fig.tight_layout()
    return fig


# ─── Main Generator ──────────────────────────────────────────────

def generate_pdf_report(
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    interpretation: str | None,
    variant_data: dict | None = None,
    drug_resistance_data: list[dict] | None = None,
) -> bytes:
    """Generate a complete PDF report and return raw bytes."""
    pdf = LuminousPDF()
    pdf.alias_nb_pages()

    # Report ID and header context
    report_id = "BV-" + uuid.uuid4().hex[:8].upper()
    pdf._report_id = report_id
    mut_label = query.mutation or "WT"
    pdf._header_label = f"{query.protein_name} {mut_label}"

    # ── PAGE 1: Executive Summary ──
    _render_title_banner(pdf, query, report_id)
    _render_ruo_notice(pdf)
    _render_query_box(pdf, query, report_id)
    if trust_audit:
        _render_key_metrics(pdf, query, prediction, trust_audit, bio_context)
    _render_report_highlights(pdf, query, prediction, trust_audit, bio_context,
                              variant_data, drug_resistance_data)
    if interpretation:
        pdf.subsection_header("AI Interpretation")
        # Truncate on page 1 to keep it self-contained
        max_chars = 500
        if len(interpretation) > max_chars:
            truncated = interpretation[:max_chars].rsplit(" ", 1)[0] + "..."
            pdf.narrative_box(truncated)
            full_interpretation = interpretation
        else:
            pdf.narrative_box(interpretation)
            full_interpretation = None
    else:
        full_interpretation = None

    # Technology partners strip
    _render_partners_strip(pdf)

    # ── PAGE 2: Structure Confidence ──
    if prediction.plddt_per_residue and prediction.residue_ids:
        pdf.add_page()
        pdf.section_header("Structure Confidence Analysis")

        # Full interpretation if truncated on page 1
        if full_interpretation:
            pdf.subsection_header("Full AI Interpretation")
            pdf.narrative_box(full_interpretation)

        # Prediction Statistics table
        _render_prediction_stats(pdf, prediction, trust_audit)

        # Quality gauge bars (wwPDB-style)
        if trust_audit:
            _render_quality_gauges(pdf, trust_audit, prediction)

        # Quality strip (compact residue-level color bar)
        fig_strip = _render_quality_strip(prediction, query)
        if fig_strip:
            pdf.add_chart(fig_strip, "Residue-level confidence strip (AlphaFold color scheme)")

        fig = _render_confidence_chart(prediction, query)
        if fig:
            pdf.add_chart(fig, "Per-residue pLDDT confidence profile")

        # Confidence color legend
        pdf.set_font(pdf._FONT, "", 7)
        legend = [
            ("#0053D6", "Very High (>90)"), ("#65CBF3", "High (70-90)"),
            ("#FFDB13", "Low (50-70)"), ("#FF7D45", "Very Low (<50)"),
        ]
        x = 15
        for color, label in legend:
            rgb = _hex_to_rgb(color)
            pdf.set_fill_color(*rgb)
            pdf.rect(x, pdf.get_y(), 3, 3, "F")
            pdf.set_xy(x + 4, pdf.get_y())
            pdf.set_text_color(*_MUTED)
            pdf.cell(35, 3, label)
            x += 42
        pdf.ln(6)

        # Region chart
        if trust_audit and trust_audit.regions:
            fig_r = _render_region_chart(trust_audit)
            if fig_r:
                pdf.subsection_header("Region Confidence Summary")
                pdf.add_chart(fig_r, "Region-level confidence. Red borders indicate flagged regions.")

    # Flagged regions table
    if trust_audit:
        flagged = [r for r in trust_audit.regions if r.flag]
        if flagged:
            pdf.subsection_header(f"Flagged Regions ({len(flagged)})")
            headers = ["Chain", "Residues", "Avg pLDDT", "Issue"]
            rows = []
            colors = []
            for r in flagged:
                rows.append([
                    r.chain,
                    f"{r.start_residue}-{r.end_residue}",
                    f"{r.avg_plddt:.1f}",
                    r.flag or "",
                ])
                colors.append(_plddt_color(r.avg_plddt))
            pdf.data_table(headers, rows, col_widths=[20, 40, 30, 90],
                           row_colors=colors, color_col=2,
                           table_label="Regions with confidence concerns")

        # Training data note (previously dropped)
        if trust_audit.training_data_note:
            pdf.subsection_header("Training Data Note")
            pdf.narrative_box(trust_audit.training_data_note)

        if trust_audit.known_limitations:
            pdf.subsection_header("Known Limitations")
            pdf.bullet_list(trust_audit.known_limitations)

        all_suggestions = list(trust_audit.suggested_validation)
        if bio_context and bio_context.suggested_experiments:
            all_suggestions.extend(bio_context.suggested_experiments)
        if all_suggestions:
            pdf.subsection_header("Recommended Validation Experiments")
            pdf.bullet_list(all_suggestions)

    # ── PAGE 3: Biological Context ──
    if bio_context and (bio_context.disease_associations or bio_context.drugs
                        or bio_context.literature.key_findings or bio_context.pathways):
        pdf.add_page()
        pdf.section_header("Biological Context")

        if bio_context.narrative:
            pdf.narrative_box(bio_context.narrative)

        if bio_context.disease_associations:
            pdf.subsection_header(f"Disease Associations ({len(bio_context.disease_associations)})")
            headers = ["Disease", "Score", "Evidence"]
            rows, colors = [], []
            for d in bio_context.disease_associations:
                score_str = f"{d.score:.0%}" if d.score is not None else "-"
                rows.append([d.disease, score_str, d.evidence or "-"])
                if d.score and d.score > 0.7:
                    colors.append(_RED)
                elif d.score and d.score > 0.4:
                    colors.append(_AMBER)
                else:
                    colors.append(None)
            pdf.data_table(headers, rows, col_widths=[55, 20, 105],
                           row_colors=colors, color_col=1,
                           table_label="Disease-gene associations from curated databases")

        if bio_context.drugs:
            pdf.subsection_header(f"Drug Candidates ({len(bio_context.drugs)})")
            headers = ["Drug", "Phase", "Evidence", "Mechanism", "Source"]
            rows, row_colors = [], []
            _PHASE_EVIDENCE = {
                "approved": ("FDA-Approved", _GREEN),
                "phase iv": ("FDA-Approved", _GREEN),
                "phase iii": ("Clinical", _BLUE),
                "phase ii": ("Clinical", _BLUE),
                "phase i": ("Early Clinical", _AMBER),
                "preclinical": ("Preclinical", _MUTED),
            }
            for drug in bio_context.drugs:
                phase_lower = (drug.phase or "").lower()
                ev_label, ev_color = _PHASE_EVIDENCE.get(
                    phase_lower, ("Preclinical", _MUTED))
                rows.append([drug.name, drug.phase or "-", ev_label,
                             drug.mechanism or "-", drug.source or "-"])
                row_colors.append(ev_color)
            pdf.data_table(headers, rows, col_widths=[40, 22, 28, 58, 32],
                           row_colors=row_colors, color_col=2,
                           table_label="Therapeutic candidates from ChEMBL / Open Targets")

        if bio_context.pathways:
            pdf.subsection_header("Pathways")
            pdf.bullet_list(bio_context.pathways)

        if bio_context.literature.key_findings:
            pdf.subsection_header(
                f"Literature ({bio_context.literature.total_papers:,} papers, "
                f"{bio_context.literature.recent_papers} recent)"
            )
            pdf.bullet_list(bio_context.literature.key_findings)

    # ── PAGE 4: Variant Analysis ──
    if variant_data and variant_data.get("variants"):
        pdf.add_page()
        pdf.section_header("Variant Analysis")

        v_total = variant_data.get("total", len(variant_data["variants"]))
        v_path = variant_data.get("pathogenic_count", 0)
        v_likely = variant_data.get("likely_pathogenic_count", 0)
        v_hotspots = len(variant_data.get("pathogenic_positions", {}))
        pdf.metric_row([
            ("Total Variants", str(v_total), _BLUE),
            ("Pathogenic", str(v_path), _RED),
            ("Likely Pathogenic", str(v_likely), _ORANGE),
            ("Hotspot Positions", str(v_hotspots), _AMBER),
        ])

        if prediction.plddt_per_residue:
            fig = _render_variant_chart(prediction, variant_data, query)
            if fig:
                pdf.add_chart(fig, "Pathogenic variants mapped onto confidence profile")

        # CADD vs allele frequency scatter
        fig_sev = _render_variant_severity_chart(variant_data, prediction)
        if fig_sev:
            pdf.add_chart(fig_sev,
                "Variant severity landscape: CADD pathogenicity score vs population frequency. "
                "Top-left quadrant (rare + high CADD) indicates strongest pathogenic signal.")

        _SIG_COLORS = {
            "pathogenic": _RED, "likely_pathogenic": _ORANGE,
            "uncertain_significance": _MUTED, "likely_benign": _BLUE, "benign": _GREEN,
        }
        headers = ["Variant", "Pos", "Significance", "CADD", "AF", "Disease", "ID"]
        rows, colors = [], []
        for v in variant_data["variants"][:30]:
            sig = v.get("significance", "unknown")
            cadd = v.get("cadd_score")
            freq = v.get("frequency")
            cadd_str = f"{cadd:.1f}" if cadd is not None else "-"
            if freq is not None:
                freq_str = f"{freq:.2e}" if freq < 0.001 else f"{freq:.4f}"
            else:
                freq_str = "-"
            rows.append([
                v.get("name", "?"), str(v.get("position", "?")),
                sig.replace("_", " ").title(), cadd_str, freq_str,
                v.get("disease", "") or "-", v.get("clinvar_id", "") or "-",
            ])
            colors.append(_SIG_COLORS.get(sig))
        pdf.data_table(headers, rows, col_widths=[25, 18, 35, 18, 22, 40, 22],
                       row_colors=colors, color_col=2,
                       table_label="Known variants from ClinVar / OncoKB (CADD = pathogenicity, AF = allele frequency)")

        if len(variant_data["variants"]) > 30:
            pdf.muted_text(f"Showing 30 of {len(variant_data['variants'])} variants")

    # ── PAGE 5: Structural Insights (SASA, 3D distances) ──
    if prediction.pdb_content:
        _render_structural_insights_page(pdf, query, prediction, variant_data,
                                         drug_resistance_data)

    # ── PAGE 6: Mutation Impact ──
    if query.mutation:
        _render_mutation_impact_page(pdf, query, prediction)

    # ── PAGE 7: Drug Resistance ──
    if drug_resistance_data:
        _render_drug_resistance_page(pdf, drug_resistance_data)

        # Cross-resistance heatmap
        fig_hm = _render_resistance_heatmap_chart(drug_resistance_data)
        if fig_hm:
            pdf.subsection_header("Cross-Resistance Matrix")
            pdf.add_chart(fig_hm,
                "Drug x Mutation resistance matrix. Blue = therapeutic target, "
                "Green = sensitizing, Red = resistant.")

    # ── BioRender Recommendations ──
    _render_biorender_recommendations(pdf, query)

    # ── Methodology ──
    _render_methodology(pdf, query, prediction)

    # ── Glossary ──
    _render_glossary(pdf)

    # ── Final: Disclaimer ──
    _render_disclaimer(pdf, report_id)

    return pdf.output()


# ─── Page Renderers ──────────────────────────────────────────────

def _render_title_banner(pdf: LuminousPDF, query: ProteinQuery, report_id: str):
    y = pdf.get_y()
    pdf.set_fill_color(*_BANNER_BG)
    pdf.rect(15, y, 180, 28, style="F")

    pdf.set_font(pdf._FONT, "B", 24)
    pdf.set_text_color(*_WHITE)
    pdf.set_xy(15, y + 3)
    pdf.cell(180, 10, "Luminous", align="C")

    pdf.set_font(pdf._FONT, "", 10)
    pdf.set_text_color(200, 210, 230)
    pdf.set_xy(15, y + 13)
    pdf.cell(180, 5, "AI Structure Interpretation Report", align="C")

    pdf.set_font(pdf._FONT, "", 8)
    pdf.set_xy(15, y + 19)
    pdf.cell(90, 4, f"Generated {datetime.now().strftime('%B %d, %Y')}")
    pdf.set_xy(105, y + 19)
    pdf.cell(90, 4, f"Report ID: {report_id}", align="R")

    pdf.set_y(y + 30)


def _render_ruo_notice(pdf: LuminousPDF):
    y = pdf.get_y()
    pdf.set_fill_color(*_WHITE)
    pdf.set_draw_color(*_RUO_RED)
    pdf.rect(15, y, 180, 6, style="D")
    pdf.set_font(pdf._FONT, "B", 8)
    pdf.set_text_color(*_RUO_RED)
    pdf.set_xy(15, y + 1)
    pdf.cell(180, 4, "FOR RESEARCH USE ONLY  -  Not for use in clinical diagnostic procedures",
             align="C")
    pdf.set_y(y + 8)

    # About Luminous blurb
    pdf.set_font(pdf._FONT, "I", 7.5)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(180, 3.2,
        "Luminous integrates Boltz-2 structure prediction, ClinVar/OncoKB variant databases, "
        "ChEMBL/Open Targets drug data, and Anthropic Claude AI interpretation to produce "
        "comprehensive protein structure analysis reports with per-residue confidence scoring."
    )
    pdf.ln(2)


def _render_query_box(pdf: LuminousPDF, query: ProteinQuery, report_id: str):
    y = pdf.get_y()
    pdf.set_fill_color(*_BG2)
    pdf.set_draw_color(*_BORDER)
    box_h = 30
    pdf.rect(15, y, 180, box_h, style="DF")

    fields = [
        ("Protein", query.protein_name),
        ("UniProt ID", query.uniprot_id or "N/A"),
        ("Mutation", query.mutation or "Wild-type"),
        ("Analysis Type", query.question_type.replace("_", " ").title()),
        ("Structure Source", "Boltz-2 (Tamarind Bio — 200+ tools)"),
        ("Compute", "Tamarind Bio Cloud / Modal GPU"),
    ]
    if query.interaction_partner:
        fields.append(("Partner", query.interaction_partner))
    if query.sequence:
        seq_hash = hashlib.sha256(query.sequence.encode()).hexdigest()[:12]
        fields.append(("Sequence", f"{len(query.sequence)} aa ({seq_hash})"))

    x_start = 18
    row_y = y + 3
    for i, (label, value) in enumerate(fields):
        col = i % 4
        row = i // 4
        x = x_start + col * 44
        cy = row_y + row * 12

        pdf.set_font(pdf._FONT, "", 6)
        pdf.set_text_color(*_MUTED)
        pdf.set_xy(x, cy)
        pdf.cell(42, 3, label.upper())

        is_protein_name = (col == 0 and row == 0)
        pdf.set_font(pdf._FONT, "B", 10 if is_protein_name else 9)
        pdf.set_text_color(*_TEXT)
        pdf.set_xy(x, cy + 3.5)
        pdf.cell(42, 5, pdf._safe(value))

    pdf.set_y(y + box_h + 4)


def _render_report_highlights(
    pdf: LuminousPDF,
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit | None,
    bio_context: BioContext | None,
    variant_data: dict | None,
    drug_resistance_data: list[dict] | None,
):
    """Key findings callout box on page 1."""
    highlights: list[str] = []

    # Confidence
    if trust_audit:
        highlights.append(
            f"Overall prediction confidence: {trust_audit.overall_confidence.upper()} "
            f"({trust_audit.confidence_score:.0%})"
        )
        flagged = sum(1 for r in trust_audit.regions if r.flag)
        if flagged:
            highlights.append(f"{flagged} structural region(s) flagged for low confidence")
        if trust_audit.complex_plddt is not None:
            highlights.append(f"Complex pLDDT: {trust_audit.complex_plddt:.1f}")

    # Variants
    if variant_data and variant_data.get("variants"):
        p_count = variant_data.get("pathogenic_count", 0)
        total = variant_data.get("total", 0)
        highlights.append(f"{total} known variants identified, {p_count} pathogenic")

    # Drug resistance
    if drug_resistance_data:
        query_drugs = [d for d in drug_resistance_data if d.get("is_query")]
        if query_drugs:
            n_drugs = sum(len(d.get("drugs", [])) for d in query_drugs)
            highlights.append(f"Drug resistance data available ({n_drugs} drug interactions)")

    # Disease associations
    if bio_context and bio_context.disease_associations:
        top = bio_context.disease_associations[0]
        highlights.append(
            f"Top disease association: {top.disease}"
            + (f" ({top.score:.0%})" if top.score else "")
        )

    if not highlights:
        return

    pdf.set_font(pdf._FONT, "B", 9)
    pdf.set_text_color(*_DEEP_BLUE)
    pdf.cell(0, 5, "REPORT HIGHLIGHTS", new_x="LMARGIN", new_y="NEXT")

    pdf.set_font(pdf._FONT, "", 8.5)
    pdf.set_text_color(*_TEXT)
    for h in highlights:
        if pdf.get_y() + 5 > 275:
            pdf.add_page()
        pdf.cell(5, 4, "-", align="R")
        pdf.cell(2)
        pdf.multi_cell(168, 4, pdf._safe(h))
        pdf.ln(0.5)
    pdf.ln(3)


def _render_key_metrics(
    pdf: LuminousPDF,
    query: ProteinQuery,
    prediction: PredictionResult,
    trust_audit: TrustAudit,
    bio_context: BioContext | None,
):
    res_ids, _ = _first_chain_data(prediction)
    residue_count = len(res_ids) if res_ids else len(prediction.residue_ids)
    flagged_count = sum(1 for r in trust_audit.regions if r.flag)

    metrics = [
        ("Confidence", f"{trust_audit.confidence_score:.0%}", _conf_color(trust_audit.confidence_score)),
    ]
    if trust_audit.ptm is not None:
        metrics.append(("pTM Score", f"{trust_audit.ptm:.3f}", _BLUE))
    if trust_audit.iptm is not None:
        metrics.append(("ipTM Score", f"{trust_audit.iptm:.3f}", _BLUE))
    if trust_audit.complex_plddt is not None:
        metrics.append(("Complex pLDDT", f"{trust_audit.complex_plddt:.1f}", _CYAN))
    metrics.append(("Residues", str(residue_count), _CYAN))
    metrics.append(("Flagged", str(flagged_count), _ORANGE if flagged_count > 0 else _GREEN))

    pdf.metric_row(metrics)

    pdf.set_font(pdf._FONT, "", 9)
    pdf.set_text_color(*_MUTED)
    pdf.cell(30, 6, "Trust Level: ")
    pdf.trust_badge(trust_audit.overall_confidence)
    pdf.ln(6)


def _render_structural_insights_page(
    pdf: LuminousPDF,
    query: ProteinQuery,
    prediction: PredictionResult,
    variant_data: dict | None,
    drug_resistance_data: list[dict] | None,
):
    """Render structural insights page: SASA, secondary structure, 3D distances."""
    try:
        from src.structure_analysis import analyze_structure
    except ImportError:
        return

    # Gather variant positions
    pathogenic_positions = {}
    if variant_data and variant_data.get("pathogenic_positions"):
        for pos_key, names in variant_data["pathogenic_positions"].items():
            try:
                pathogenic_positions[int(pos_key)] = names
            except (ValueError, TypeError):
                pass

    # Gather pocket residues
    pocket_residues = []
    try:
        from components.drug_resistance import _RESISTANCE_DB
        data = _RESISTANCE_DB.get(query.protein_name.upper(), {})
        pocket_residues = data.get("binding_pocket_residues", [])
    except ImportError:
        pass

    # Parse mutation position
    mutation_pos = None
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation.upper())
        if m:
            mutation_pos = int(m.group(1))

    try:
        first_chain = prediction.chain_ids[0] if prediction.chain_ids else None
        analysis = analyze_structure(
            prediction.pdb_content,
            mutation_pos=mutation_pos,
            variant_positions=pathogenic_positions or None,
            pocket_residues=pocket_residues,
            first_chain=first_chain,
        )
    except Exception:
        return

    pdf.add_page()
    pdf.section_header("Structural Insights from 3D Coordinates")

    # Key metrics
    sse = analysis.get("sse_counts", {})
    total_res = len(analysis.get("residue_ids", []))
    buried = len(analysis.get("buried_residues", []))
    exposed = len(analysis.get("exposed_residues", []))

    pdf.metric_row([
        ("Total Residues", str(total_res), _BLUE),
        ("Buried (<25 Å²)", str(buried), _RED),
        ("Exposed", str(exposed), _GREEN),
        ("α-Helix", str(sse.get("a", 0)), _CYAN),
        ("β-Sheet", str(sse.get("b", 0)), _DEEP_BLUE),
    ])

    # Mutation-specific structural context
    if mutation_pos:
        sasa = analysis.get("mutation_sasa")
        is_buried = analysis.get("mutation_is_buried")
        sse_code = analysis.get("mutation_sse", "c")
        pocket_dist = analysis.get("mutation_to_pocket_min_distance")
        in_pocket = analysis.get("mutation_in_pocket", False)

        sse_labels = {"a": "α-Helix", "b": "β-Sheet", "c": "Loop/Coil"}

        if sasa is not None:
            status = "BURIED" if is_buried else "SURFACE-EXPOSED"
            mechanism = ("fold destabilization" if is_buried
                         else "drug binding disruption" if in_pocket
                         else "interaction disruption")
            pdf.subsection_header(f"Mutation Site: {query.mutation}")
            pdf.narrative_box(
                f"{query.mutation} is {status} (SASA = {sasa:.1f} Å²) in a "
                f"{sse_labels.get(sse_code, 'loop')} region. "
                f"{'This position is within the drug binding pocket. ' if in_pocket else ''}"
                f"Predicted mechanism of pathogenicity: {mechanism}."
                + (f" Distance to nearest binding pocket residue: {pocket_dist:.1f} Å."
                   if pocket_dist is not None and not in_pocket else "")
            )

        # 3D variant distances
        var_dists = analysis.get("mutation_to_variant_distances", [])
        if var_dists:
            pdf.subsection_header("3D Proximity to Pathogenic Variants")
            headers = ["Variant", "Seq Dist", "3D Dist (Å)", "Proximity"]
            rows, colors = [], []
            for v in var_dists[:10]:
                proximity = ("CONTACT" if v["distance_3d"] < 5
                             else "CLOSE" if v["distance_3d"] < 10
                             else "MODERATE" if v["distance_3d"] < 20
                             else "DISTANT")
                rows.append([
                    v["name"],
                    f"{v['distance_seq']} res",
                    f"{v['distance_3d']:.1f}",
                    proximity,
                ])
                colors.append(_RED if v["distance_3d"] < 5
                              else _ORANGE if v["distance_3d"] < 10
                              else _AMBER if v["distance_3d"] < 20
                              else None)
            pdf.data_table(headers, rows, col_widths=[35, 25, 30, 90],
                           row_colors=colors, color_col=3,
                           table_label="Euclidean Cα-Cα distances from Boltz-2 coordinates")

    # Hidden spatial clusters
    hidden = analysis.get("hidden_spatial_clusters", [])
    if hidden:
        pdf.subsection_header("Hidden Spatial Clusters")
        pdf.narrative_box(
            f"{len(hidden)} variant pair(s) are distant in sequence (>20 residues apart) "
            f"but close in 3D space (<10 Å). These define shared functional surfaces "
            f"invisible from sequence data alone."
        )
        headers = ["Variant 1", "Variant 2", "Seq Dist", "3D Dist (Å)"]
        rows = []
        for h in hidden:
            rows.append([h["name1"], h["name2"],
                         f"{h['distance_seq']} res", f"{h['distance_3d']:.1f}"])
        pdf.data_table(headers, rows, col_widths=[40, 40, 30, 30],
                       table_label="Sequence-distant but spatially proximal pathogenic variants")

    # SASA chart
    fig_sasa = _render_sasa_chart(analysis, query, mutation_pos)
    if fig_sasa:
        pdf.add_chart(fig_sasa,
            "Per-residue solvent accessible surface area (SASA). "
            "Red = buried (<25 Å²), green = exposed (>60 Å²).")

    # ── Multi-Track Protein Map ──
    fig_mt = _render_multi_track_chart(
        analysis, prediction, mutation_pos, pathogenic_positions or None)
    if fig_mt:
        pdf.add_chart(fig_mt,
            "Multi-track protein map: SSE (blue=helix, green=sheet), pLDDT confidence, "
            "SASA, and packing density. Red dotted lines = pathogenic variants.")

    # ── Contact Map ──
    fig_cm = _render_contact_map_chart(analysis, pathogenic_positions or None, mutation_pos)
    if fig_cm:
        pdf.add_chart(fig_cm,
            "Cα–Cα contact map. Blue = close contacts (<8 Å). "
            "Red × = pathogenic variant positions. Gold ★ = query mutation.")

    # ── Packing Density ──
    fig_pd = _render_packing_density_chart(analysis, mutation_pos)
    if fig_pd:
        pdf.add_chart(fig_pd,
            "Local packing density (Cβ neighbours within 12 Å). "
            "Mutations at dense sites cause steric clashes or cavity formation.")

    # ── Ramachandran Plot ──
    fig_rama = _render_ramachandran_chart(analysis, mutation_pos, pathogenic_positions or None)
    if fig_rama:
        pdf.add_chart(fig_rama,
            "Ramachandran plot (φ/ψ backbone dihedrals). "
            "Blue shading = α-helix favored region, green = β-sheet.")

    # Ramachandran stats
    rama_stats = analysis.get("rama_stats")
    if rama_stats:
        pdf.muted_text(
            f"Backbone geometry: {rama_stats['favored_pct']:.1f}% favored "
            f"({rama_stats['favored']}/{rama_stats['total']}), "
            f"{rama_stats['outlier']} outlier(s)."
        )

    # ── Network Centrality ──
    fig_nc = _render_network_centrality_chart(analysis, mutation_pos)
    if fig_nc:
        pdf.add_chart(fig_nc,
            "Residue interaction network betweenness centrality. "
            "Hub residues (amber) are structurally critical communication nodes.")

    # Network hub summary
    hubs = analysis.get("hub_residues", [])
    if hubs:
        hub_strs = [f"Res {h['residue']} ({h['centrality']:.4f})" for h in hubs[:5]]
        pdf.muted_text(f"Top hub residues: {', '.join(hub_strs)}")

    mut_cent = analysis.get("mutation_centrality")
    mut_pct = analysis.get("mutation_centrality_percentile")
    if mut_cent is not None and mut_pct is not None:
        pct_label = f"top {100-mut_pct:.0f}%"
        pdf.muted_text(
            f"Mutation centrality: {mut_cent:.4f} ({pct_label} of residues)"
        )


def _render_sasa_chart(
    analysis: dict, query: ProteinQuery, mutation_pos: int | None,
) -> plt.Figure | None:
    """Render SASA profile as matplotlib chart for PDF."""
    sasa_data = analysis.get("sasa_per_residue", {})
    if not sasa_data:
        return None

    res_ids = sorted(sasa_data.keys())
    sasa_vals = [sasa_data[r] for r in res_ids]

    colors = ["#FF3B30" if s < 25 else "#34C759" if s > 60 else "#FF9500" for s in sasa_vals]

    fig, ax = plt.subplots(figsize=(10, 2.5))
    ax.bar(res_ids, sasa_vals, color=colors, width=1.0, edgecolor="none")

    ax.axhline(y=25, color="#FF3B30", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.text(res_ids[0] + 2, 27, "Buried threshold", fontsize=6, color="#FF3B30")

    if mutation_pos and mutation_pos in sasa_data:
        ax.scatter([mutation_pos], [sasa_data[mutation_pos]], color="#FFCC00",
                   marker="*", s=120, zorder=6, edgecolors="#FF3B30", linewidths=1.0)

    ax.set_xlabel("Residue Number", color="#4B5563", fontsize=8)
    ax.set_ylabel("SASA (Å²)", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_contact_map_chart(
    analysis: dict, pathogenic_positions: dict | None, mutation_pos: int | None,
) -> plt.Figure | None:
    """Cα–Cα contact map heatmap for PDF."""
    dist_matrix = analysis.get("contact_map")
    res_list = analysis.get("contact_map_residues", [])
    if dist_matrix is None or len(res_list) < 3:
        return None

    # Subsample for readability
    step = max(1, len(res_list) // 200)
    if step > 1:
        idx = list(range(0, len(res_list), step))
        sub_res = [res_list[i] for i in idx]
        sub_mat = dist_matrix[np.ix_(idx, idx)]
    else:
        sub_res = res_list
        sub_mat = dist_matrix

    display = np.clip(sub_mat, 0, 40)

    cmap = LinearSegmentedColormap.from_list("contact", [
        "#0053D6", "#65CBF3", "#FFDB13", "#FF7D45", "#E8E8E8",
    ])
    fig, ax = plt.subplots(figsize=(5, 5))
    im = ax.imshow(display, cmap=cmap, vmin=0, vmax=40, origin="upper", aspect="equal")

    # Mark pathogenic variants on diagonal
    if pathogenic_positions:
        sub_set = {r: i for i, r in enumerate(sub_res)}
        for p in pathogenic_positions:
            if p in sub_set:
                idx_p = sub_set[p]
                ax.plot(idx_p, idx_p, "x", color="#FF3B30", markersize=5, markeredgewidth=1.5)

    if mutation_pos and mutation_pos in {r: i for i, r in enumerate(sub_res)}:
        idx_m = {r: i for i, r in enumerate(sub_res)}[mutation_pos]
        ax.plot(idx_m, idx_m, "*", color="#FFCC00", markersize=10,
                markeredgecolor="#FF3B30", markeredgewidth=0.8)

    # Sparse tick labels
    n = len(sub_res)
    tick_step = max(1, n // 8)
    tick_idx = list(range(0, n, tick_step))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([str(sub_res[i]) for i in tick_idx], fontsize=6, rotation=45)
    ax.set_yticks(tick_idx)
    ax.set_yticklabels([str(sub_res[i]) for i in tick_idx], fontsize=6)
    ax.set_xlabel("Residue", fontsize=7, color="#4B5563")
    ax.set_ylabel("Residue", fontsize=7, color="#4B5563")

    cbar = fig.colorbar(im, ax=ax, shrink=0.8, label="Distance (Å)")
    cbar.ax.tick_params(labelsize=6)

    ax.set_facecolor("white")
    fig.subplots_adjust(left=0.12, right=0.92, top=0.95, bottom=0.12)
    return fig


def _render_packing_density_chart(
    analysis: dict, mutation_pos: int | None,
) -> plt.Figure | None:
    """Local packing density bar chart for PDF."""
    packing = analysis.get("packing_density", {})
    if len(packing) < 3:
        return None

    res_ids = sorted(packing.keys())
    vals = [packing[r] for r in res_ids]
    mean_p = sum(vals) / len(vals)

    colors = []
    for r, v in zip(res_ids, vals):
        if mutation_pos and r == mutation_pos:
            colors.append("#FFCC00")
        elif v > mean_p * 1.3:
            colors.append("#FF3B30")
        elif v > mean_p * 0.7:
            colors.append("#007AFF")
        else:
            colors.append("#65CBF3")

    fig, ax = plt.subplots(figsize=(10, 2.2))
    ax.bar(res_ids, vals, color=colors, width=1.0, edgecolor="none")
    ax.axhline(y=mean_p, color="#888", linewidth=0.8, linestyle="--", alpha=0.6)
    ax.text(res_ids[0] + 2, mean_p + 0.5, f"Mean: {mean_p:.0f}", fontsize=6, color="#888")

    if mutation_pos and mutation_pos in packing:
        ax.scatter([mutation_pos], [packing[mutation_pos]], color="#FFCC00",
                   marker="*", s=120, zorder=6, edgecolors="#FF3B30", linewidths=1.0)

    ax.set_xlabel("Residue Number", color="#4B5563", fontsize=8)
    ax.set_ylabel("Cβ Neighbors (12Å)", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_ramachandran_chart(
    analysis: dict, mutation_pos: int | None,
    pathogenic_positions: dict | None,
) -> plt.Figure | None:
    """Ramachandran scatter plot for PDF."""
    rama = analysis.get("ramachandran", [])
    if len(rama) < 3:
        return None

    fig, ax = plt.subplots(figsize=(4.5, 4.5))

    # Favored region shading
    ax.fill_between([-160, -20], [-120, -120], [20, 20], alpha=0.08, color="#007AFF")
    ax.fill_between([-180, -40], [80, 80], [180, 180], alpha=0.08, color="#34C759")
    ax.fill_between([-180, -40], [-180, -180], [-120, -120], alpha=0.08, color="#34C759")
    ax.fill_between([20, 120], [-20, -20], [80, 80], alpha=0.06, color="#FF9500")

    # Region labels
    ax.text(-90, -50, "α", fontsize=18, color="#007AFF", alpha=0.3, ha="center")
    ax.text(-120, 130, "β", fontsize=18, color="#34C759", alpha=0.3, ha="center")
    ax.text(60, 30, "Lα", fontsize=12, color="#FF9500", alpha=0.3, ha="center")

    path_set = set(pathogenic_positions.keys()) if pathogenic_positions else set()

    # Regular residues
    reg = [r for r in rama if r["residue"] != mutation_pos and r["residue"] not in path_set]
    if reg:
        ax.scatter([r["phi"] for r in reg], [r["psi"] for r in reg],
                   c="#007AFF", s=6, alpha=0.4, edgecolors="none")

    # Pathogenic variants
    pv = [r for r in rama if r["residue"] in path_set]
    if pv:
        ax.scatter([r["phi"] for r in pv], [r["psi"] for r in pv],
                   c="#FF3B30", s=25, alpha=0.8, edgecolors="white", linewidths=0.5,
                   label="Pathogenic", zorder=5)

    # Mutation
    if mutation_pos:
        mut_r = [r for r in rama if r["residue"] == mutation_pos]
        if mut_r:
            ax.scatter([mut_r[0]["phi"]], [mut_r[0]["psi"]],
                       c="#FFCC00", s=100, marker="*", edgecolors="#FF3B30",
                       linewidths=1, label="Mutation", zorder=6)

    ax.set_xlim(-180, 180)
    ax.set_ylim(-180, 180)
    ax.set_xlabel("φ (degrees)", fontsize=8, color="#4B5563")
    ax.set_ylabel("ψ (degrees)", fontsize=8, color="#4B5563")
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    ax.axhline(y=0, color="#D0D5DD", linewidth=0.5)
    ax.axvline(x=0, color="#D0D5DD", linewidth=0.5)

    if pv or (mutation_pos and mut_r):
        ax.legend(fontsize=6, loc="upper right", framealpha=0.8)

    fig.subplots_adjust(left=0.14, right=0.95, top=0.95, bottom=0.12)
    return fig


def _render_multi_track_chart(
    analysis: dict, prediction: PredictionResult,
    mutation_pos: int | None, pathogenic_positions: dict | None,
) -> plt.Figure | None:
    """Multi-track protein map for PDF (SSE + pLDDT + SASA + packing)."""
    res_ids = analysis.get("residue_ids", [])
    if len(res_ids) < 3:
        return None

    sse_data = analysis.get("sse_per_residue", {})
    sasa_data = analysis.get("sasa_per_residue", {})
    packing = analysis.get("packing_density", {})

    plddt_map: dict[int, float] = {}
    if prediction.plddt_per_residue and prediction.residue_ids:
        for i, rid in enumerate(prediction.residue_ids):
            if i < len(prediction.plddt_per_residue):
                plddt_map[rid] = prediction.plddt_per_residue[i]

    n_tracks = 3
    if packing:
        n_tracks = 4

    fig, axes = plt.subplots(n_tracks, 1, figsize=(10, 1.2 * n_tracks),
                             sharex=True, gridspec_kw={"hspace": 0.15})
    if n_tracks == 1:
        axes = [axes]

    # Track 1: SSE ribbon
    ax = axes[0]
    sse_color_map = {"a": "#007AFF", "b": "#34C759", "c": "#AEAEB2"}
    for rid in res_ids:
        code = str(sse_data.get(rid, "c")).strip()
        if code not in sse_color_map:
            code = "c"
        ax.barh(0, 1, left=res_ids.index(rid), color=sse_color_map[code],
                height=1.0, edgecolor="none")
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    ax.set_ylabel("SSE", fontsize=7, color="#4B5563", rotation=0, labelpad=20)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Track 2: pLDDT
    ax = axes[1]
    plddt_vals = [plddt_map.get(r, 0) for r in res_ids]
    plddt_colors = [
        "#0053D6" if v >= 90 else "#65CBF3" if v >= 70
        else "#FFDB13" if v >= 50 else "#FF7D45"
        for v in plddt_vals
    ]
    ax.bar(range(len(res_ids)), plddt_vals, color=plddt_colors, width=1.0, edgecolor="none")
    ax.set_ylabel("pLDDT", fontsize=7, color="#4B5563", rotation=0, labelpad=20)
    ax.set_ylim(0, 100)
    ax.tick_params(labelsize=6, colors="#4B5563")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")

    # Track 3: SASA
    ax = axes[2]
    sasa_vals = [sasa_data.get(r, 0) for r in res_ids]
    sasa_colors = ["#FF3B30" if s < 25 else "#34C759" if s > 60 else "#FF9500" for s in sasa_vals]
    ax.bar(range(len(res_ids)), sasa_vals, color=sasa_colors, width=1.0, edgecolor="none")
    ax.set_ylabel("SASA", fontsize=7, color="#4B5563", rotation=0, labelpad=20)
    ax.tick_params(labelsize=6, colors="#4B5563")
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")

    # Track 4: Packing density
    if packing and n_tracks >= 4:
        ax = axes[3]
        pack_vals = [packing.get(r, 0) for r in res_ids]
        ax.bar(range(len(res_ids)), pack_vals, color="#007AFF", width=1.0,
               edgecolor="none", alpha=0.7)
        ax.set_ylabel("Pack", fontsize=7, color="#4B5563", rotation=0, labelpad=20)
        ax.tick_params(labelsize=6, colors="#4B5563")
        ax.set_facecolor("white")
        for spine in ax.spines.values():
            spine.set_color("#D0D5DD")

    # Variant markers on all tracks
    if pathogenic_positions:
        res_set = {r: i for i, r in enumerate(res_ids)}
        for vpos in pathogenic_positions:
            if vpos in res_set:
                idx = res_set[vpos]
                for ax in axes:
                    ax.axvline(x=idx, color="#FF3B30", linewidth=0.6,
                               linestyle=":", alpha=0.6)

    # Mutation marker
    if mutation_pos and mutation_pos in {r: i for i, r in enumerate(res_ids)}:
        m_idx = {r: i for i, r in enumerate(res_ids)}[mutation_pos]
        for ax in axes:
            ax.axvline(x=m_idx, color="#FF9500", linewidth=1.2, alpha=0.8)

    # X-axis on bottom track only
    step = max(len(res_ids) // 10, 1)
    tick_idx = list(range(0, len(res_ids), step))
    axes[-1].set_xticks(tick_idx)
    axes[-1].set_xticklabels([str(res_ids[i]) for i in tick_idx], fontsize=6)
    axes[-1].set_xlabel("Residue Number", fontsize=7, color="#4B5563")

    return fig


def _render_network_centrality_chart(
    analysis: dict, mutation_pos: int | None,
) -> plt.Figure | None:
    """Betweenness centrality profile for PDF."""
    centrality = analysis.get("network_centrality", {})
    if not centrality:
        return None

    res_ids = sorted(centrality.keys())
    vals = [centrality[r] for r in res_ids]
    hubs = {h["residue"] for h in analysis.get("hub_residues", [])}

    colors = []
    for r in res_ids:
        if mutation_pos and r == mutation_pos:
            colors.append("#FFCC00")
        elif r in hubs:
            colors.append("#FF9500")
        else:
            colors.append("#007AFF")

    fig, ax = plt.subplots(figsize=(10, 2.2))
    ax.bar(res_ids, vals, color=colors, width=1.0, edgecolor="none")

    if mutation_pos and mutation_pos in centrality:
        ax.scatter([mutation_pos], [centrality[mutation_pos]], color="#FFCC00",
                   marker="*", s=120, zorder=6, edgecolors="#FF3B30", linewidths=1.0)

    ax.set_xlabel("Residue Number", color="#4B5563", fontsize=8)
    ax.set_ylabel("Betweenness Centrality", color="#4B5563", fontsize=8)
    ax.tick_params(colors="#4B5563", labelsize=7)
    ax.set_facecolor("white")
    for spine in ax.spines.values():
        spine.set_color("#D0D5DD")
    return fig


def _render_mutation_impact_page(
    pdf: LuminousPDF, query: ProteinQuery, prediction: PredictionResult,
):
    m = re.match(r"([A-Z])(\d+)([A-Z])", query.mutation.upper())
    if not m:
        return

    wt_aa, pos, mut_aa = m.group(1), int(m.group(2)), m.group(3)
    wt_props = _AA_PROPS.get(wt_aa)
    mut_props = _AA_PROPS.get(mut_aa)
    if not wt_props or not mut_props:
        return

    pdf.add_page()
    pdf.section_header(f"Mutation Structural Impact: {query.mutation}")

    plddt_val = "N/A"
    plddt_color = _MUTED
    res_ids, scores = _first_chain_data(prediction)
    if pos in res_ids:
        idx = res_ids.index(pos)
        sc = scores[idx]
        plddt_val = f"{sc:.1f}"
        plddt_color = _plddt_color(sc)

    pdf.metric_row([
        ("Wild-Type", f"{wt_aa} ({wt_props['name']})", _BLUE),
        ("Mutant", f"{mut_aa} ({mut_props['name']})", _ORANGE),
        ("Position", str(pos), _CYAN),
        ("pLDDT at Site", plddt_val, plddt_color),
    ])

    pdf.subsection_header("Property Changes")
    headers = ["Property", "Wild-Type", "Mutant", "Impact"]
    rows, row_colors = [], []

    wt_c, mut_c = wt_props["charge"], mut_props["charge"]
    rows.append(["Charge", f"{wt_c:+d}", f"{mut_c:+d}",
                 "Charge change" if wt_c != mut_c else "No change"])
    row_colors.append(_RED if wt_c != mut_c else _GREEN)

    wt_h, mut_h = wt_props["hydro"], mut_props["hydro"]
    delta_h = abs(mut_h - wt_h)
    if delta_h > 3:
        h_impact, h_color = "Major shift", _RED
    elif delta_h > 1.5:
        h_impact, h_color = "Moderate shift", _AMBER
    else:
        h_impact, h_color = "Minor", _GREEN
    rows.append(["Hydrophobicity", f"{wt_h:+.1f}", f"{mut_h:+.1f}", h_impact])
    row_colors.append(h_color)

    sz_changed = wt_props["size"] != mut_props["size"]
    rows.append(["Size", wt_props["size"], mut_props["size"],
                 "Size change" if sz_changed else "Same"])
    row_colors.append(_AMBER if sz_changed else _GREEN)

    wt_mw, mut_mw = wt_props["mw"], mut_props["mw"]
    rows.append(["Molecular Weight", f"{wt_mw} Da", f"{mut_mw} Da",
                 f"{'+'if mut_mw > wt_mw else ''}{mut_mw - wt_mw} Da"])
    row_colors.append(_AMBER if abs(mut_mw - wt_mw) > 30 else _GREEN)

    if wt_aa == "C" or mut_aa == "C":
        if wt_aa == "C":
            rows.append(["Disulfide Bonds", "Cys", "-", "Bond lost"])
            row_colors.append(_RED)
        else:
            rows.append(["Disulfide Bonds", "-", "Cys", "Bond gained"])
            row_colors.append(_AMBER)

    if wt_aa == "P" or mut_aa == "P":
        rows.append(["Backbone", "Pro (rigid)" if wt_aa == "P" else "Flexible",
                     "Pro (rigid)" if mut_aa == "P" else "Flexible",
                     "Rigidified" if mut_aa == "P" else "Flexibility increased"])
        row_colors.append(_AMBER)

    if wt_aa == "G" or mut_aa == "G":
        rows.append(["Flexibility", "Gly (flexible)" if wt_aa == "G" else "Standard",
                     "Gly (flexible)" if mut_aa == "G" else "Standard",
                     "Flexibility lost" if wt_aa == "G" else "Flexibility gained"])
        row_colors.append(_AMBER)

    pdf.data_table(headers, rows, col_widths=[40, 35, 35, 70],
                   row_colors=row_colors, color_col=3,
                   table_label="Physicochemical property comparison")


def _render_drug_resistance_page(pdf: LuminousPDF, drug_resistance_data: list[dict]):
    pdf.add_page()
    pdf.section_header("Drug-Mutation Structural Analysis")

    for mut in drug_resistance_data:
        y = pdf.get_y()
        if y + 40 > 270:
            pdf.add_page()
            y = pdf.get_y()

        border_color = _RED if mut.get("is_query") else _BORDER
        pdf.set_fill_color(*_BG2)
        pdf.set_draw_color(*border_color)
        pdf.rect(15, y, 180, 6, style="DF")

        pdf.set_font(pdf._FONT, "B", 11)
        pdf.set_text_color(*_TEXT)
        pdf.set_xy(18, y + 0.5)
        name = mut.get("name", "Unknown")
        if mut.get("is_query"):
            name += " (Your query)"
        pdf.cell(0, 5, pdf._safe(name))
        pdf.set_y(y + 8)

        if mut.get("mechanism"):
            pdf.set_font(pdf._FONT, "B", 9)
            pdf.set_text_color(*_AMBER)
            pdf.cell(0, 4, pdf._safe(mut["mechanism"]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

        if mut.get("explanation"):
            pdf.body_text(mut["explanation"])

        drugs = mut.get("drugs", [])
        if drugs:
            headers = ["Drug", "Fold Change", "Status"]
            rows, colors = [], []
            for d in drugs:
                status = d.get("status", "")
                if "Resistant" in status:
                    c = _RED
                elif "Sensitiz" in status or "sensitive" in status.lower():
                    c = _GREEN
                else:
                    c = _AMBER
                rows.append([d.get("name", ""), d.get("fold_change", ""), status])
                colors.append(c)
            pdf.data_table(headers, rows, col_widths=[50, 30, 100],
                           row_colors=colors, color_col=2,
                           table_label="Drug interaction profile")

        if mut.get("clinical_note"):
            pdf.muted_text(f"Clinical: {mut['clinical_note']}")

        pdf.ln(3)


def _render_partners_strip(pdf: LuminousPDF):
    """Technology partners visual strip on page 1."""
    y = pdf.get_y()
    if y + 12 > 275:
        return  # Skip if no room on page 1
    pdf.set_draw_color(*_BORDER)
    pdf.line(15, y, 195, y)
    pdf.ln(2)

    partners = ["Tamarind Bio", "Anthropic Claude", "BioRender", "Modal", "MolViewSpec", "BioMCP"]
    total_w = 180
    sep = " | "
    pdf.set_font(pdf._FONT, "", 6.5)
    pdf.set_text_color(*_MUTED)
    pdf.set_x(15)
    pdf.cell(total_w, 3, "TECHNOLOGY PARTNERS", align="C")
    pdf.ln(3.5)
    pdf.set_font(pdf._FONT, "B", 7.5)
    pdf.set_text_color(*_DEEP_BLUE)
    pdf.set_x(15)
    pdf.cell(total_w, 4, sep.join(partners), align="C")
    pdf.ln(5)


def _render_gauge(pdf: LuminousPDF, x: float, y: float, w: float,
                  value: float, max_val: float, label: str, quality: str):
    """Draw a wwPDB-style horizontal gauge bar with marker."""
    h = 4
    # Background track
    pdf.set_fill_color(*_BG2)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(x, y, w, h, style="DF")

    # Gradient fill (green zone, yellow zone, red zone)
    third = w / 3
    pdf.set_fill_color(*_RED)
    pdf.rect(x, y, third, h, "F")
    pdf.set_fill_color(*_AMBER)
    pdf.rect(x + third, y, third, h, "F")
    pdf.set_fill_color(*_GREEN)
    pdf.rect(x + 2 * third, y, third, h, "F")

    # Border on top
    pdf.set_draw_color(*_BORDER)
    pdf.rect(x, y, w, h, "D")

    # Position marker
    ratio = min(max(value / max_val, 0), 1.0)
    mx = x + ratio * w
    pdf.set_fill_color(*_TEXT)
    pdf.rect(mx - 1, y - 1, 2, h + 2, "F")

    # Label (left)
    pdf.set_font(pdf._FONT, "", 6.5)
    pdf.set_text_color(*_MUTED)
    pdf.set_xy(x, y - 4)
    pdf.cell(w * 0.5, 3, label)

    # Value + quality (right)
    pdf.set_font(pdf._FONT, "B", 7)
    color_map = {"high": _GREEN, "medium": _AMBER, "low": _RED, "very high": _GREEN}
    pdf.set_text_color(*color_map.get(quality.lower(), _MUTED))
    pdf.set_xy(x + w * 0.5, y - 4)
    val_str = f"{value:.1f}" if max_val > 1 else f"{value:.3f}"
    pdf.cell(w * 0.5, 3, f"{val_str}  ({quality})", align="R")


def _render_quality_gauges(pdf: LuminousPDF, trust_audit: TrustAudit, prediction: PredictionResult):
    """Render wwPDB-style gauge bars for key quality metrics."""
    res_ids, scores = _first_chain_data(prediction)
    mean_plddt = sum(scores) / len(scores) if scores else 0

    gauges = []
    if scores:
        q = "very high" if mean_plddt >= 90 else "high" if mean_plddt >= 70 else "medium" if mean_plddt >= 50 else "low"
        gauges.append(("Mean pLDDT", mean_plddt, 100, q))
    if trust_audit.ptm is not None:
        q = "high" if trust_audit.ptm >= 0.7 else "medium" if trust_audit.ptm >= 0.5 else "low"
        gauges.append(("pTM Score", trust_audit.ptm, 1.0, q))
    if trust_audit.iptm is not None:
        q = "high" if trust_audit.iptm >= 0.6 else "medium" if trust_audit.iptm >= 0.4 else "low"
        gauges.append(("ipTM Score", trust_audit.iptm, 1.0, q))
    if trust_audit.complex_plddt is not None:
        q = "high" if trust_audit.complex_plddt >= 70 else "medium" if trust_audit.complex_plddt >= 50 else "low"
        gauges.append(("Complex pLDDT", trust_audit.complex_plddt, 100, q))

    if not gauges:
        return

    needed = len(gauges) * 12 + 4
    if pdf.get_y() + needed > 275:
        pdf.add_page()

    y = pdf.get_y() + 2
    for label, val, max_v, quality in gauges:
        _render_gauge(pdf, 15, y + 5, 180, val, max_v, label, quality)
        y += 12

    pdf.set_y(y + 2)


def _render_prediction_stats(
    pdf: LuminousPDF, prediction: PredictionResult, trust_audit: TrustAudit | None,
):
    """Consolidated prediction statistics table (wwPDB-style)."""
    res_ids, scores = _first_chain_data(prediction)
    if not scores:
        return

    mean_s = sum(scores) / len(scores)
    sorted_s = sorted(scores)
    median_s = sorted_s[len(sorted_s) // 2]
    gt90 = sum(1 for s in scores if s >= 90) / len(scores) * 100
    gt70 = sum(1 for s in scores if s >= 70) / len(scores) * 100
    lt50 = sum(1 for s in scores if s < 50) / len(scores) * 100
    n_chains = len(set(prediction.chain_ids)) if prediction.chain_ids else 1

    rows = [
        ["Total residues", str(len(scores))],
        ["Chains", str(n_chains)],
        ["Mean pLDDT", f"{mean_s:.1f}"],
        ["Median pLDDT", f"{median_s:.1f}"],
        ["Residues >= 90 (very high)", f"{gt90:.1f}%"],
        ["Residues >= 70 (confident)", f"{gt70:.1f}%"],
        ["Residues < 50 (disordered)", f"{lt50:.1f}%"],
    ]
    if trust_audit:
        if trust_audit.ptm is not None:
            rows.append(["pTM", f"{trust_audit.ptm:.3f}"])
        if trust_audit.iptm is not None:
            rows.append(["ipTM", f"{trust_audit.iptm:.3f}"])
        if trust_audit.complex_plddt is not None:
            rows.append(["Complex pLDDT", f"{trust_audit.complex_plddt:.1f}"])

    pdf.subsection_header("Prediction Statistics")
    pdf.data_table(
        ["Metric", "Value"], rows,
        col_widths=[100, 80],
        table_label="Consolidated structure prediction quality metrics",
    )


def _render_quality_strip(
    prediction: PredictionResult, query: ProteinQuery,
) -> plt.Figure | None:
    """Compact horizontal color strip showing per-residue confidence."""
    res_ids, scores = _first_chain_data(prediction)
    if not res_ids or len(res_ids) < 2:
        return None

    colors = [trust_to_color(s) for s in scores]
    fig, ax = plt.subplots(figsize=(10, 0.6))
    for i, (rid, c) in enumerate(zip(res_ids, colors)):
        ax.barh(0, 1, left=i, color=c, height=1.0, edgecolor="none")

    # Mutation marker
    if query.mutation:
        m = re.match(r"[A-Z](\d+)[A-Z]", query.mutation.upper())
        if m:
            mut_pos = int(m.group(1))
            if mut_pos in res_ids:
                idx = res_ids.index(mut_pos)
                ax.plot(idx + 0.5, 0, marker="v", color="#B45309", markersize=8, zorder=5)

    ax.set_xlim(0, len(res_ids))
    ax.set_ylim(-0.5, 0.5)
    ax.set_yticks([])
    # Sparse x-ticks
    step = max(len(res_ids) // 8, 1)
    tick_idx = list(range(0, len(res_ids), step))
    ax.set_xticks(tick_idx)
    ax.set_xticklabels([str(res_ids[i]) for i in tick_idx], fontsize=6, color="#4B5563")
    ax.set_xlabel("Residue", fontsize=7, color="#4B5563")
    ax.set_facecolor("white")
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color("#D0D5DD")
    ax.tick_params(left=False, colors="#4B5563", labelsize=6)
    fig.subplots_adjust(left=0.02, right=0.98, top=0.85, bottom=0.35)
    return fig


def _render_biorender_recommendations(pdf: LuminousPDF, query: ProteinQuery):
    """Add a compact BioRender recommendations section to the PDF report."""
    import streamlit as st

    cache_key = f"biorender_results_{query.protein_name}"
    results = st.session_state.get(cache_key)

    if not results:
        # Try to generate results if not cached
        try:
            from src.biorender_search import search_biorender_templates

            results = search_biorender_templates(
                protein_name=query.protein_name,
                mutation=query.mutation,
                question_type=query.question_type,
            )
        except Exception:
            return

    if not results:
        return

    templates = [r for r in results if r.get("type") == "template"]
    if not templates:
        return

    # Don't start a new page -- add to current page if space, else auto-page-break
    if pdf.get_y() + 40 > 275:
        pdf.add_page()

    pdf.subsection_header("Recommended BioRender Templates")
    pdf.muted_text(
        "The following BioRender templates are recommended for creating "
        "publication-quality figures based on this analysis."
    )

    headers = ["Template", "Type", "Description"]
    rows = []
    for tmpl in templates[:6]:
        rows.append([
            tmpl.get("name", "Unknown"),
            tmpl.get("type", "template").title(),
            tmpl.get("description", "")[:80],
        ])

    pdf.data_table(
        headers, rows,
        col_widths=[50, 22, 108],
        table_label="BioRender templates matched to this protein analysis",
    )

    # Add URLs as a footnote list
    url_templates = [t for t in templates[:6] if t.get("url")]
    if url_templates:
        pdf.set_font(pdf._FONT, "", 7)
        pdf.set_text_color(*_MUTED)
        for i, tmpl in enumerate(url_templates, 1):
            url = tmpl["url"]
            if len(url) > 70:
                url = url[:67] + "..."
            pdf.cell(0, 3.5, f"[{i}] {tmpl['name']}: {url}",
                     new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

    pdf.muted_text(
        "Visit app.biorender.com to customize these templates for your publication. "
        "BioRender provides 50,000+ scientific icons and templates."
    )


def _render_methodology(pdf: LuminousPDF, query: ProteinQuery, prediction: PredictionResult):
    pdf.add_page()
    pdf.section_header("Methodology")

    pdf.subsection_header("Structure Prediction & Computational Analysis")
    pdf.body_text(
        "3D structure prediction was performed using Boltz-2 via Tamarind Bio's cloud platform, "
        "which hosts 200+ computational biology tools. Beyond structure prediction, Tamarind Bio "
        "provides molecular docking (AutoDock Vina, GNINA, DiffDock), mutation stability analysis "
        "(ProteinMPNN-ddG, ThermoMPNN), de novo binder design (BoltzGen, RFdiffusion), property "
        "prediction (Aggrescan3D, CamSol, TemStaPro), surface analysis (MaSIF), and small molecule "
        "design (REINVENT 4). The model generates per-residue confidence estimates (pLDDT) and "
        "global quality metrics (pTM, ipTM) using a diffusion-based architecture trained on PDB "
        "structures."
    )

    pdf.subsection_header("Confidence Scoring")
    pdf.body_text(
        "pLDDT (predicted Local Distance Difference Test) scores range from 0 to 100 and estimate "
        "per-residue structural accuracy. Scores above 90 indicate very high confidence, 70-90 high "
        "confidence, 50-70 low confidence, and below 50 very low confidence (likely disordered). "
        "pTM (predicted Template Modeling score) and ipTM (interface pTM) assess global fold and "
        "interface quality respectively."
    )

    pdf.subsection_header("Data Sources")
    sources = [
        "ClinVar - NCBI variant interpretation database (clinical significance)",
        "OncoKB - Memorial Sloan Kettering precision oncology knowledge base",
        "ChEMBL - EMBL-EBI bioactivity database (drug-target interactions)",
        "Open Targets - drug target evidence platform",
        "UniProt - protein sequence and functional annotation",
    ]
    pdf.bullet_list(sources)

    pdf.subsection_header("Structural Analysis")
    pdf.body_text(
        "Structural properties are computed directly from predicted 3D coordinates using "
        "biotite (Kunzmann & Kern, BMC Bioinformatics 2018). Analyses include: "
        "Solvent Accessible Surface Area (Shrake-Rupley algorithm), secondary structure "
        "annotation (DSSP-like), contact map (Cα-Cα pairwise distances), local packing "
        "density (Cβ neighbour count within 12 Å, Cα for Gly), Ramachandran φ/ψ backbone "
        "dihedral angles, and residue interaction network betweenness centrality "
        "(NetworkX, Hagberg et al. 2008)."
    )

    pdf.subsection_header("AI Interpretation")
    pdf.body_text(
        "Natural language interpretation was generated by Anthropic Claude, synthesizing "
        "structural predictions, variant annotations, and biological context. AI-generated "
        "content should be critically evaluated by domain experts."
    )

    pdf.subsection_header("Software")
    sw = [
        f"Luminous v{_APP_VERSION}",
        "Tamarind Bio platform (200+ tools: Boltz-2, ESMFold, AutoDock Vina, GNINA, "
        "DiffDock, ProteinMPNN-ddG, ThermoMPNN, BoltzGen, RFdiffusion, Aggrescan3D, "
        "CamSol, TemStaPro, MaSIF, PRODIGY, REINVENT 4, and more)",
        "BioMCP variant and context retrieval",
        "MolViewSpec 3D visualization",
        "biotite structural analysis (SASA, SSE, contact map, Ramachandran)",
        "NetworkX residue interaction network centrality",
    ]
    pdf.bullet_list(sw)


def _render_glossary(pdf: LuminousPDF):
    pdf.add_page()
    pdf.section_header("Glossary")

    terms = [
        ("pLDDT", "Predicted Local Distance Difference Test. Per-residue confidence score "
         "(0-100) estimating the accuracy of the predicted 3D position. Based on the AlphaFold "
         "confidence metric."),
        ("pTM", "Predicted Template Modeling score. Global metric (0-1) assessing whether the "
         "overall predicted fold is correct. Values above 0.5 suggest a correct topology."),
        ("ipTM", "Interface predicted TM score. Assesses the quality of predicted protein-protein "
         "interfaces in multimeric predictions. Values above 0.6 suggest reliable interface "
         "modeling."),
        ("Complex pLDDT", "Average pLDDT computed across all chains in a complex prediction, "
         "providing a single confidence metric for multi-chain structures."),
        ("Pathogenic", "A variant classified as disease-causing with strong evidence, per ACMG/"
         "AMP 5-tier germline classification guidelines."),
        ("Likely Pathogenic", "A variant with sufficient evidence to support a disease-causing "
         "role, though with less certainty than 'pathogenic.'"),
        ("VUS", "Variant of Uncertain Significance. Insufficient evidence to classify as "
         "pathogenic or benign. Requires further study."),
        ("Hotspot Position", "A residue position harboring one or more known pathogenic variants, "
         "suggesting functional importance."),
        ("Gatekeeper Mutation", "A mutation at a conserved residue that controls access to the "
         "ATP-binding pocket in kinases, often conferring drug resistance."),
        ("Fold Change", "The ratio of drug IC50 (mutant/wild-type). Values >10x typically "
         "indicate clinically significant resistance."),
        ("Contact Map", "2D matrix of pairwise Cα-Cα distances between all residues. "
         "Dark regions indicate structural contacts (<8 Å). Reveals which contacts "
         "a mutation disrupts."),
        ("Packing Density", "Number of Cβ atoms within 12 Å of each residue. Densely "
         "packed sites are structurally critical — mutations there cause voids or "
         "steric clashes."),
        ("Ramachandran Plot", "Scatter plot of backbone φ/ψ dihedral angles. Residues "
         "in favored regions indicate well-modeled geometry; outliers may indicate "
         "structural strain or modelling errors."),
        ("Betweenness Centrality", "Graph theory metric measuring how often a residue "
         "lies on shortest paths between other residues in the contact network. High "
         "centrality = structurally critical hub residue."),
        ("SASA", "Solvent Accessible Surface Area. The surface area of a residue "
         "accessible to solvent. Buried residues (<25 Å²) are in the protein core; "
         "exposed residues (>60 Å²) are on the surface."),
    ]

    for term, definition in terms:
        if pdf.get_y() + 12 > 275:
            pdf.add_page()
        pdf.set_font(pdf._FONT, "B", 9)
        pdf.set_text_color(*_DEEP_BLUE)
        pdf.cell(0, 5, term, new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(pdf._FONT, "", 8)
        pdf.set_text_color(*_TEXT)
        pdf.multi_cell(0, 3.5, pdf._safe(definition))
        pdf.ln(2)


def _render_disclaimer(pdf: LuminousPDF, report_id: str):
    if pdf.get_y() + 45 > 275:
        pdf.add_page()

    y = pdf.get_y() + 5
    pdf.set_fill_color(*_BG2)
    pdf.set_draw_color(*_BORDER)
    pdf.rect(15, y, 180, 40, style="DF")

    pdf.set_xy(18, y + 3)
    pdf.set_font(pdf._FONT, "B", 7)
    pdf.set_text_color(*_RUO_RED)
    pdf.cell(0, 3, "DISCLAIMER - FOR RESEARCH USE ONLY")
    pdf.set_xy(18, y + 7)
    pdf.set_font(pdf._FONT, "", 7)
    pdf.set_text_color(*_MUTED)
    pdf.multi_cell(174, 3,
        "This report is generated by Luminous, an AI-powered structure interpretation tool. "
        "All predictions, confidence scores, and interpretations are computational outputs and "
        "must be validated experimentally before any clinical or research decisions. This report "
        "is not a substitute for professional medical judgment. Structure predictions are from "
        "Boltz-2 (via Tamarind Bio). Variant annotations sourced from ClinVar and OncoKB. "
        "Drug information from ChEMBL and Open Targets. Database content may not reflect the "
        "most recent updates."
    )
    pdf.set_xy(18, y + 27)
    pdf.set_font(pdf._FONT, "", 6.5)
    pdf.cell(0, 3,
        f"Report ID: {report_id}  |  Luminous v{_APP_VERSION}  |  "
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}"
    )
    pdf.set_xy(18, y + 32)
    pdf.set_font(pdf._FONT, "B", 7)
    pdf.cell(0, 3,
        "Powered by: Tamarind Bio | Anthropic Claude | BioRender | Modal | MolViewSpec | BioMCP"
    )
