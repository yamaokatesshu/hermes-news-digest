# report_generator.py

import sys
import logging
import re
import os  # NEW: To read environment variables
from pathlib import Path
from datetime import datetime

# --- Dependency Imports ---
try:
    from fpdf import FPDF
    from fpdf.enums import XPos, YPos
except ImportError:
    sys.exit("❌ Error: 'fpdf2' library not found. Please run: pip install fpdf2")

# --- Local Module Imports ---
try:
    from research_agent import conduct_gemini_research
except ImportError:
    sys.exit("❌ Error: Could not import from 'research_agent.py'. Ensure it is in the same directory.")

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PDF_OUTPUT_PATH = OUTPUT_DIR / "hermes_knowledge_base.pdf"

# --- NEW: Paths to all styles of the Unicode TTF font ---
# This makes the font registration explicit and robust.
UNICODE_FONT_PATH_REGULAR = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
UNICODE_FONT_PATH_BOLD = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")
UNICODE_FONT_PATH_ITALIC = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf")
UNICODE_FONT_PATH_BOLD_ITALIC = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf")
BASE_FONT_FAMILY = "DejaVu"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)

# --- Text utilities (sanitize + soft break injection) ---
_ZWSP = "\u200B"  # zero-width space for soft wrapping


def sanitize_text(s: str) -> str:
    """Normalize characters and add soft-wrap hints for URLs/paths."""
    if not s:
        return s
    s = (s.replace("\u2013", "-")
         .replace("\u2014", "--")
         .replace("\u2022", "- ")
         .replace("\u00A0", " "))
    s = re.sub(r'([/\-_\.?&=])', r'\1' + _ZWSP, s)
    return s


def break_token_to_fit(token: str, pdf, max_w: float) -> str:
    """Break an over-wide token into lines that each fit max_w."""
    parts = token.split(_ZWSP)
    rebuilt = []
    for piece in parts:
        if not piece:
            rebuilt.append("")
            continue
        if pdf.get_string_width(piece) <= max_w:
            rebuilt.append(piece)
            continue
        start = 0
        curr = []
        while start < len(piece):
            lo, hi = start, len(piece)
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if pdf.get_string_width(piece[start:mid]) <= max_w:
                    lo = mid
                else:
                    hi = mid - 1
            if lo == start:
                lo = start + 1
            segment = piece[start:lo]
            if lo < len(piece) and segment and segment[-1].isalnum() and piece[lo].isalnum():
                segment += "-"
            curr.append(segment)
            start = lo
        rebuilt.append(_ZWSP.join(curr))
    return _ZWSP.join(rebuilt)


def width_aware_wrap(pdf, text: str) -> str:
    """Prepare a string for multi_cell by ensuring no single token exceeds usable width."""
    usable_w = pdf.w - pdf.r_margin - pdf.l_margin - 1.0
    out_lines = []
    for raw_line in text.split("\n"):
        line = sanitize_text(raw_line.strip())
        tokens = line.split(" ")
        fixed_tokens = []
        for tok in tokens:
            if not tok:
                fixed_tokens.append("")
                continue
            t = break_token_to_fit(tok, pdf, usable_w)
            fixed_tokens.append(t)
        out_lines.append(" ".join(fixed_tokens))
    return "\n".join(out_lines)


# --- PDF Generation Class ---
class PDF(FPDF):
    """Custom PDF class to handle headers, footers, and chapter titles."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.set_auto_page_break(True, margin=15)
        self.set_left_margin(15)
        self.set_right_margin(15)

        # Register all four font styles (Regular, Bold, Italic, Bold-Italic)
        if UNICODE_FONT_PATH_REGULAR.exists():
            try:
                self.add_font(BASE_FONT_FAMILY, "", str(UNICODE_FONT_PATH_REGULAR))
                self.add_font(BASE_FONT_FAMILY, "B", str(UNICODE_FONT_PATH_BOLD))
                self.add_font(BASE_FONT_FAMILY, "I", str(UNICODE_FONT_PATH_ITALIC))
                self.add_font(BASE_FONT_FAMILY, "BI", str(UNICODE_FONT_PATH_BOLD_ITALIC))
                self.set_font(BASE_FONT_FAMILY, "", 12)
            except Exception as e:
                logging.warning(f"Failed to load Unicode fonts ({e}). Falling back to 'helvetica'.")
                self.set_font("helvetica", "", 12)
        else:
            logging.warning("DejaVu fonts not found. Falling back to 'helvetica'.")
            self.set_font("helvetica", "", 12)

    def header(self):
        self.set_font(self.font_family or BASE_FONT_FAMILY, 'B', 12)
        self.cell(0, 10, 'Hermes Knowledge Base Report',
                  new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font(self.font_family or BASE_FONT_FAMILY, 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}',
                  new_x=XPos.RIGHT, new_y=YPos.TOP, align='C')

    def chapter_title(self, title):
        self.set_font(self.font_family or BASE_FONT_FAMILY, 'B', 16)
        self.set_x(self.l_margin)
        safe = width_aware_wrap(self, title)
        self.multi_cell(0, 10, safe)
        self.ln(5)

    def chapter_body(self, body_text):
        self.set_font(self.font_family or BASE_FONT_FAMILY, '', 12)
        self.set_x(self.l_margin)
        safe = width_aware_wrap(self, body_text)
        self.multi_cell(0, 10, safe)
        self.ln()

    def add_report_content(self, report_text: str):
        """Parses the report text and adds it to the PDF with formatting."""
        self.add_page()
        for line in report_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if line.startswith('# '):
                self.chapter_title(line.lstrip('# ').strip())
            elif line.startswith('## '):
                self.set_font(self.font_family or BASE_FONT_FAMILY, 'B', 14)
                self.set_x(self.l_margin)
                safe = width_aware_wrap(self, line.lstrip('## ').strip())
                self.multi_cell(0, 10, safe)
                self.ln(2)
            elif line.startswith('* ') or line.startswith('- '):
                self.set_font(self.font_family or BASE_FONT_FAMILY, '', 12)
                self.set_x(self.l_margin)
                safe = width_aware_wrap(self, "  " + line)
                self.multi_cell(0, 10, safe)
            else:
                self.chapter_body(line)


def generate_pdf_report(report_text: str):
    """Takes the synthesized report text and saves it as a formatted PDF."""
    if not report_text.strip():
        logging.error("❌ The research agent returned no text. Cannot generate PDF.")
        return

    logging.info(f"Generating PDF report at: {PDF_OUTPUT_PATH}")
    pdf = PDF()

    # Create Title Page
    pdf.add_page()
    pdf.set_font(pdf.font_family or BASE_FONT_FAMILY, 'B', 24)
    pdf.cell(0, 20, 'Project Hermes', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.set_font(pdf.font_family or BASE_FONT_FAMILY, 'B', 18)
    pdf.cell(0, 15, 'AI-Generated Knowledge Base', new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
    pdf.ln(20)
    pdf.set_font(pdf.font_family or BASE_FONT_FAMILY, '', 12)
    pdf.cell(0, 10, f"Generated on: {datetime.now().strftime('%B %d, %Y at %H:%M:%S')}",
             new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')

    # Add Report Content
    pdf.add_report_content(report_text)

    try:
        pdf.output(PDF_OUTPUT_PATH)
        logging.info("✅ PDF report generated successfully.")
    except Exception as e:
        logging.error(f"❌ Failed to save PDF file. Error: {e}")


if __name__ == '__main__':
    # --- UPDATED: Read the research topic from the environment variable ---
    # This makes the script dynamic, controlled by the GUI.
    default_topic = (
        "A default topic about the emerging geopolitical risks affecting the global semiconductor "
        "supply chain, with a specific focus on the dependencies between US chip designers like NVIDIA, "
        "Taiwanese manufacturing by companies like TSMC, and Dutch ASML's dominance in EUV lithography equipment."
    )
    topic_paragraph = os.getenv('HERMES_TOPIC_PARAGRAPH', default_topic)

    if topic_paragraph == default_topic:
        logging.info("Running with default topic. To use a custom topic, run from the Hermes GUI.")

    logging.info("--- Starting Phase 1: Research & Synthesis (using Gemini API) ---")
    synthesized_report = conduct_gemini_research(topic_paragraph)

    if synthesized_report:
        generate_pdf_report(synthesized_report)
    else:
        logging.error("❌ Halting process as research phase failed to produce content.")
        sys.exit(1)



