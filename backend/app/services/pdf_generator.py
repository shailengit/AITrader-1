"""
Professional PDF report generator for TradeCraft AI Stock Screener.
Uses fpdf2 to create branded, structured reports.
"""

import io
from datetime import datetime
from typing import List, Dict, Any, Optional
from fpdf import FPDF


class ScreenerPDF(FPDF):
    """Custom PDF class for TradeCraft screener reports."""

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)
        # Use standard fonts (no external TTF files needed)
        self.set_font("Helvetica", "", 12)

    def header(self):
        """Add header on each page after the cover."""
        if self.page_no() == 1:
            return  # Skip header on cover page
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(16, 185, 129)
        self.cell(0, 10, "TradeCraft AI Stock Screener", ln=0, align="L")  # type: ignore[arg-type]
        self.set_text_color(100, 100, 100)
        self.cell(0, 10, f"Page {self.page_no()}", ln=1, align="R")  # type: ignore[arg-type]
        self.set_draw_color(230, 230, 230)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(5)

    def footer(self):
        """Add footer on each page."""
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | TradeCraft", ln=1, align="C")  # type: ignore[arg-type]

    def add_cover_page(self, mode: str, date: str, total_stocks: int, use_ai: bool):
        """Generate the branded cover page."""
        self.add_page()
        # Top accent bar
        self.set_fill_color(16, 185, 129)
        self.rect(0, 0, 210, 60, style="F")

        # Title
        self.set_y(80)
        self.set_font("Helvetica", "B", 32)
        self.set_text_color(16, 185, 129)
        self.cell(0, 15, "TradeCraft", ln=1, align="C")  # type: ignore[arg-type]

        self.set_font("Helvetica", "", 20)
        self.set_text_color(50, 50, 50)
        self.cell(0, 12, "AI Stock Screener Report", ln=1, align="C")  # type: ignore[arg-type]

        # Mode badge
        self.ln(15)
        mode_label = "Dormant Giant Screener" if mode == "dormant_giant" else "Quant Strategy Screener"
        self.set_font("Helvetica", "B", 14)
        self.set_fill_color(16, 185, 129)
        self.set_text_color(255, 255, 255)
        self.cell(0, 12, f"  {mode_label}  ", ln=1, align="C", fill=True)  # type: ignore[arg-type]

        # AI badge
        if use_ai:
            self.ln(5)
            self.set_font("Helvetica", "B", 11)
            self.set_fill_color(59, 130, 246)
            self.set_text_color(255, 255, 255)
            self.cell(0, 10, "  AI Multi-Agent Analysis Enabled  ", ln=1, align="C", fill=True)  # type: ignore[arg-type]

        # Meta info
        self.ln(20)
        self.set_font("Helvetica", "", 13)
        self.set_text_color(80, 80, 80)
        self.cell(0, 10, f"Scan Date: {date}", ln=1, align="C")  # type: ignore[arg-type]
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(16, 185, 129)
        self.cell(0, 10, f"{total_stocks} Stocks Identified", ln=1, align="C")  # type: ignore[arg-type]

        # Bottom accent
        self.set_y(-30)
        self.set_fill_color(16, 185, 129)
        self.rect(0, self.get_y(), 210, 5, style="F")

    def add_executive_summary(self, summary: str, stats: Dict[str, Any]):
        """Add the executive summary section."""
        self.add_page()
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(30, 30, 30)
        self.cell(0, 12, "Executive Summary", ln=1)  # type: ignore[arg-type]
        self.ln(2)

        # Summary paragraph
        self.set_font("Helvetica", "", 11)
        self.set_text_color(60, 60, 60)
        self.multi_cell(0, 7, summary)
        self.ln(10)

        # Stats boxes
        self.set_font("Helvetica", "B", 11)
        self.set_fill_color(245, 245, 245)
        self.set_draw_color(200, 200, 200)

        items = [
            ("Technical Candidates", str(stats.get("technical_candidates", "N/A"))),
            ("Verified Candidates", str(stats.get("verified_candidates", "N/A"))),
            ("Final Results", str(stats.get("results_count", "N/A"))),
        ]
        for label, value in items:
            self.cell(60, 12, f"  {label}", ln=0, border=1, fill=True)  # type: ignore[arg-type]
            self.cell(30, 12, f"{value}  ", ln=1, align="R", border=1)  # type: ignore[arg-type]
            self.ln(2)

    def add_results_table(self, results: List[Dict[str, Any]]):
        """Add the results table section."""
        self.add_page()
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(30, 30, 30)
        self.cell(0, 12, "Screening Results", ln=1)  # type: ignore[arg-type]
        self.ln(5)

        if not results:
            self.set_font("Helvetica", "", 11)
            self.set_text_color(120, 120, 120)
            self.cell(0, 10, "No stocks matched the screening criteria.", ln=1)  # type: ignore[arg-type]
            return

        # Table headers
        headers = ["Ticker", "Signal", "Price", "Catalyst", "SMA(20)", "RSI", "MACD", "Volume"]
        col_widths = [25, 45, 20, 45, 20, 15, 20, 35]

        self.set_font("Helvetica", "B", 9)
        self.set_fill_color(16, 185, 129)
        self.set_text_color(255, 255, 255)
        for h, w in zip(headers, col_widths):
            self.cell(w, 10, f"  {h}", border=1, fill=True)
        self.ln()

        # Rows
        self.set_font("Helvetica", "", 9)
        self.set_text_color(40, 40, 40)
        for i, row in enumerate(results):
            bg = (240, 248, 245) if i % 2 == 0 else (255, 255, 255)
            self.set_fill_color(*bg)

            ticker = row.get("ticker", "")
            signal = row.get("signal", "") or ""
            close = row.get("close")
            catalyst = row.get("fundamental_catalyst", "") or ""
            sma20 = row.get("sma_20")
            rsi = row.get("rsi")
            macd = row.get("macd")
            vol = row.get("volume")

            price_str = f"${close:.2f}" if close is not None else "N/A"
            sma_str = f"{sma20:.2f}" if sma20 is not None else "N/A"
            rsi_str = f"{rsi:.1f}" if rsi is not None else "N/A"
            macd_str = f"{macd:.4f}" if macd is not None else "N/A"
            vol_str = f"{vol:,}" if vol is not None else "N/A"

            self.cell(col_widths[0], 8, f"  {ticker}", border=1, fill=True)
            self.cell(col_widths[1], 8, f"  {signal[:20]}", border=1, fill=True)
            self.cell(col_widths[2], 8, f"  {price_str}", border=1, fill=True)
            self.cell(col_widths[3], 8, f"  {catalyst[:22]}", border=1, fill=True)
            self.cell(col_widths[4], 8, f"  {sma_str}", border=1, fill=True)
            self.cell(col_widths[5], 8, f"  {rsi_str}", border=1, fill=True)
            self.cell(col_widths[6], 8, f"  {macd_str}", border=1, fill=True)
            self.cell(col_widths[7], 8, f"  {vol_str}", border=1, fill=True)
            self.ln()

    def add_ai_report(self, report: str):
        """Add the AI analysis report section."""
        self.add_page()
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(30, 30, 30)
        self.cell(0, 12, "AI Multi-Agent Analysis Report", ln=1)  # type: ignore[arg-type]
        self.ln(3)

        self.set_font("Helvetica", "", 10)
        self.set_text_color(60, 60, 60)

        # Clean up markdown for PDF
        cleaned = report.replace("**", "").replace("*", "")
        cleaned = cleaned.replace("#", "").replace("##", "").replace("###", "")
        cleaned = cleaned.replace("`", "")
        for line in cleaned.split("\n"):
            line = line.strip()
            if not line:
                self.ln(3)
                continue
            if line.startswith("-") or line.startswith("*"):
                self.set_x(self.get_x() + 5)
                self.multi_cell(0, 6, line[1:].strip())
            else:
                self.multi_cell(0, 6, line)

    def add_methodology(self, mode: str):
        """Add methodology appendix."""
        self.add_page()
        self.set_font("Helvetica", "B", 18)
        self.set_text_color(30, 30, 30)
        self.cell(0, 12, "Methodology", ln=1)  # type: ignore[arg-type]
        self.ln(3)

        self.set_font("Helvetica", "", 10)
        self.set_text_color(60, 60, 60)

        if mode == "dormant_giant":
            text = (
                "The Dormant Giant Screener identifies stocks building energy before a potential explosive move. "
                "It screens for three technical signatures:\n\n"
                "1. Bollinger Bandwidth Squeeze: volatility contracts to a tight range, indicating a coiling pattern.\n"
                "2. OBV Hidden Accumulation: On-Balance Volume rises while price remains flat, signaling quiet institutional buying.\n"
                "3. Resistance Breakout: price punches through a 120-day resistance level on a volume spike.\n\n"
                "After technical candidates are identified, fundamental verification checks for EPS acceleration "
                "over the last three quarterly reports. Only stocks with both a technical setup and an earnings "
                "catalyst are included in the final results."
            )
        else:
            text = (
                "The Quant Strategy Screener performs a broad technical indicator sweep across the S&P 1500 universe. "
                "For each stock, it calculates SMA(20), SMA(50), RSI(14), MACD, and volume metrics.\n\n"
                "Candidates are then vetted by the Fundamental Specialist for revenue growth and income trends, "
                "and by the Risk Manager for market cap, beta, and sector concentration.\n\n"
                "When a cutoff date is provided, the Performance Analyst calculates forward returns from that date "
                "to the present, simulating how the screening criteria would have performed historically."
            )

        for paragraph in text.split("\n\n"):
            self.multi_cell(0, 6, paragraph)
            self.ln(4)


def generate_screener_report(
    mode: str,
    use_ai: bool,
    results: List[Dict[str, Any]],
    summary: str,
    ai_report: Optional[str],
    stats: Dict[str, Any]
) -> bytes:
    """
    Generate a professional PDF report for a screener scan.

    Returns:
        bytes: The PDF file content ready for streaming/download.
    """
    pdf = ScreenerPDF()
    date_str = datetime.now().strftime("%B %d, %Y")

    # Cover
    pdf.add_cover_page(mode, date_str, len(results), use_ai)

    # Executive Summary
    pdf.add_executive_summary(summary, stats)

    # Results Table
    pdf.add_results_table(results)

    # AI Report
    if use_ai and ai_report:
        pdf.add_ai_report(ai_report)

    # Methodology
    pdf.add_methodology(mode)

    return bytes(pdf.output(dest="S"))  # type: ignore[call-overload]
