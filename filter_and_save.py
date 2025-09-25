# filter_and_save.py

import sys
import logging
import re
import time
from pathlib import Path
from datetime import datetime

# --- Dependency Imports ---
try:
    import fitz  # PyMuPDF
except ImportError:
    sys.exit("❌ Error: 'PyMuPDF' library not found. Please run: pip install PyMuPDF")

try:
    from llama_cpp import Llama
except ImportError:
    sys.exit("❌ Error: 'llama-cpp-python' library not found. Please run: pip install llama-cpp-python")

# --- Local Module Imports ---
try:
    from scraper_module import get_article_content
except ImportError:
    sys.exit("❌ Error: Could not import from 'scraper_module.py'. Ensure it is in the same directory.")

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"

# Model Path (using the corrected path you provided)
GPT_OSS_MODEL_PATH = Path("/home/benjamincros76/PycharmProjects/Text_Engine/gpt-oss-20b-UD-Q8_K_XL.gguf")

# Input Files
CANDIDATE_URLS_PATH = OUTPUT_DIR / "candidate_urls.txt"
KNOWLEDGE_BASE_PDF_PATH = OUTPUT_DIR / "hermes_knowledge_base.pdf"

# Output File
DATABASE_MD_PATH = PROJECT_ROOT / "database.md"

# LLM Settings
LLM_CONTEXT_SIZE = 4096
RELEVANCE_THRESHOLD = 7  # Score out of 10

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


# --- Helper Functions ---
def load_llm():
    """Initializes and returns the local LLM instance."""
    if not GPT_OSS_MODEL_PATH.is_file():
        logging.error(f"❌ LLM model file not found at: {GPT_OSS_MODEL_PATH}")
        sys.exit(1)
    try:
        logging.info(f"Initializing model: {GPT_OSS_MODEL_PATH.name}")
        llm = Llama(model_path=str(GPT_OSS_MODEL_PATH), n_ctx=LLM_CONTEXT_SIZE, verbose=False, n_gpu_layers=-1)
        return llm
    except Exception as e:
        logging.error(f"❌ Failed to load LLM. Error: {e}")
        sys.exit(1)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extracts all text from a given PDF file to be used as the knowledge base."""
    if not pdf_path.is_file():
        logging.error(f"Knowledge base PDF not found: {pdf_path}")
        return ""
    try:
        with fitz.open(pdf_path) as doc:
            text = "".join(page.get_text() for page in doc)
        logging.info("✅ Successfully extracted text from knowledge base PDF.")
        return text
    except Exception as e:
        logging.error(f"❌ Failed to extract text from PDF: {e}")
        return ""


def check_relevance_with_llm(llm: Llama, article_text: str, knowledge_base: str) -> (bool, str):
    """Uses the LLM to score the relevance of an article against the knowledge base."""
    prompt = f"""
    As a research analyst, evaluate the following news article against our established knowledge base.
    Determine if the article is highly relevant. High relevance means it directly supports, updates, or introduces a significant new perspective on the known themes.

    Respond ONLY with a single line in this exact format:
    Score: [score from 1-10]. Justification: [a brief, one-sentence explanation].

    --- KNOWLEDGE BASE (SUMMARY) ---
    {knowledge_base[:3000]}
    --- NEWS ARTICLE ---
    {article_text[:4000]}
    """
    try:
        response = llm(prompt, max_tokens=100, stop=["\n"], echo=False)
        response_text = response['choices'][0]['text'].strip()

        match = re.search(r"Score:\s*(\d+).*Justification:\s*(.*)", response_text, re.IGNORECASE)
        if not match:
            logging.warning(f"  - LLM relevance check returned an unexpected format: {response_text}")
            return False, "LLM response format error."

        score = int(match.group(1))
        justification = match.group(2).strip()

        if score >= RELEVANCE_THRESHOLD:
            reason = f"High thematic relevance (Score: {score}/10). Justification: {justification}"
            return True, reason
        else:
            return False, f"Low thematic relevance (Score: {score}/10)."
    except Exception as e:
        logging.error(f"  - LLM relevance check failed: {e}")
        return False, "LLM analysis error."


def summarize_with_llm(llm: Llama, title: str, article_text: str) -> str:
    """Uses the LLM to generate a bulleted summary of the article."""
    prompt = f"""
    You are a strategic analyst. Create a concise, insightful summary of the following news article.
    Present the key findings as 3-5 bullet points.

    **Article Title:** {title}
    **Content:**
    {article_text[:6000]}
    """
    try:
        response = llm(prompt, max_tokens=300, temperature=0.3, echo=False)
        summary = response['choices'][0]['text'].strip()
        # Clean up potential conversational filler from the model
        summary = re.sub(r"^\s*Here is a summary.*?:", "", summary, flags=re.IGNORECASE).strip()
        return summary
    except Exception as e:
        logging.error(f"  - LLM summarization failed: {e}")
        return "Summarization failed due to an error."


def append_to_database(article_data: dict):
    """Formats and appends a new article entry to the Markdown database."""
    entry = f"""--- ARTICLE START ---
Title: {article_data['title']}
URL: {article_data['url']}
Date_Processed: {datetime.now().strftime('%Y-%m-%d')}
Reason: {article_data['reason']}
Summary:
{article_data['summary']}
--- ARTICLE END ---

"""
    with open(DATABASE_MD_PATH, "a", encoding="utf-8") as f:
        f.write(entry)


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Filtering & Saving ---")

    if not CANDIDATE_URLS_PATH.is_file():
        logging.info("No candidate URLs found to process. Exiting.")
        sys.exit(0)

    with open(CANDIDATE_URLS_PATH, "r", encoding='utf-8') as f:
        urls_to_process = [line.strip() for line in f if line.strip()]

    if not urls_to_process:
        logging.info("Candidate URL file is empty. Exiting.")
        sys.exit(0)

    # --- Perform one-time setups ---
    llm = load_llm()
    knowledge_base = extract_text_from_pdf(KNOWLEDGE_BASE_PDF_PATH)
    if not knowledge_base:
        logging.error("❌ Cannot proceed without a knowledge base. Halting.")
        sys.exit(1)

    logging.info(f"Processing {len(urls_to_process)} candidate URLs...")
    saved_count = 0

    for url in urls_to_process:
        logging.info(f"\n-> Processing URL: {url}")

        # 1. Scrape content
        article_data = get_article_content(url)
        if not (article_data and article_data.get("content")):
            logging.error(f"  - ❌ FAILED to scrape content.")
            continue

        full_text = f"{article_data['title']}\n\n{article_data['content']}"

        # 2. Filter for relevance
        logging.info("  - Checking relevance against knowledge base...")
        is_relevant, reason = check_relevance_with_llm(llm, full_text, knowledge_base)

        if is_relevant:
            logging.info(f"  - ✅ PASSED: {reason}")

            # 3. Summarize the relevant article
            logging.info("  - Generating summary...")
            summary = summarize_with_llm(llm, article_data['title'], article_data['content'])

            # 4. Append to database
            db_entry = {
                "title": article_data['title'],
                "url": url,
                "reason": reason,
                "summary": summary
            }
            append_to_database(db_entry)
            logging.info(f"  - ✅ Saved to database.md")
            saved_count += 1
        else:
            logging.info(f"  - ❌ SKIPPED: {reason}")

        time.sleep(1)  # Small delay to be polite

    logging.info(f"\n--- Filtering & Saving Complete ---")
    logging.info(f"Saved {saved_count} new articles to database.md.")

