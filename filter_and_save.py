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
    from llama_cpp import Llama, LlamaGrammar
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

# Model Path
GPT_OSS_MODEL_PATH = Path("/home/benjamincros76/PycharmProjects/Text_Engine/gpt-oss-20b-UD-Q8_K_XL.gguf")

# Input Files
CANDIDATE_URLS_PATH = OUTPUT_DIR / "candidate_urls.txt"
KNOWLEDGE_BASE_PDF_PATH = OUTPUT_DIR / "hermes_knowledge_base.pdf"

# Output File
DATABASE_MD_PATH = PROJECT_ROOT / "database.md"

# LLM Settings
LLM_CONTEXT_SIZE = 8192
RELEVANCE_THRESHOLD = 7  # Score out of 10 for the primary thematic check

# --- GBNF Grammars for Structured Output ---
RELEVANCE_GRAMMAR = r'''
root   ::= "<|channel|>final<|message|>" "Score: " score ". Justification: " justification
score  ::= "10" | [1-9]
justification ::= [^\n]*
'''
# --- INSPIRED BY CERBERUS: A new grammar for the second, yes/no check ---
CONFIRMATION_GRAMMAR = r'''
root   ::= "Yes" | "No"
'''

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


# --- Helper Functions ---
def load_llm():
    """Initializes the LLM and compiles the grammars."""
    if not GPT_OSS_MODEL_PATH.is_file():
        logging.error(f"❌ LLM model file not found at: {GPT_OSS_MODEL_PATH}")
        sys.exit(1)
    try:
        logging.info(f"Initializing model: {GPT_OSS_MODEL_PATH.name}")
        llm = Llama(
            model_path=str(GPT_OSS_MODEL_PATH), n_ctx=LLM_CONTEXT_SIZE,
            verbose=False, n_gpu_layers=-1, chat_format=None
        )
        relevance_grammar = LlamaGrammar.from_string(RELEVANCE_GRAMMAR)
        confirmation_grammar = LlamaGrammar.from_string(CONFIRMATION_GRAMMAR)
        return llm, relevance_grammar, confirmation_grammar
    except Exception as e:
        logging.error(f"❌ Failed to load LLM. Error: {e}")
        sys.exit(1)

def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extracts all text from the knowledge base PDF."""
    if not pdf_path.is_file(): return ""
    try:
        with fitz.open(pdf_path) as doc:
            text = "".join(page.get_text() for page in doc)
        logging.info("✅ Successfully extracted text from knowledge base PDF.")
        return text
    except Exception as e:
        logging.error(f"❌ Failed to extract text from PDF: {e}")
        return ""

# --- LLM Interaction Functions ---
def _check_thematic_relevance(llm: Llama, grammar: LlamaGrammar, article_text: str, knowledge_base: str) -> (bool, str):
    """
    Step A: Broadly checks if the article's theme matches the knowledge base.
    Uses the advanced UD-style prompting for high-quality reasoning.
    """
    user_prompt = f"**Knowledge Base Summary:**\n{knowledge_base[:3000]}\n\n**News Article to Evaluate:**\n{article_text[:4000]}"
    messages = [
        {"role": "system", "content": "You are a meticulous research analyst. Your task is to determine if a news article is relevant to a knowledge base. First, provide your detailed reasoning in the 'analysis' channel. Then, provide your final conclusion in the 'final' channel.\n<|start|>assistant<|message|>Ok, I understand. I will first write my reasoning in the <|channel|>analysis<|message|> block, and then provide the final, formatted score in the <|channel|>final<|message|> block.<|end|>"},
        {"role": "user", "content": user_prompt},
    ]
    try:
        response = llm.create_chat_completion(messages=messages, max_tokens=500, temperature=0.1, grammar=grammar)
        response_text = response['choices'][0]['message']['content'].strip()
        final_match = re.search(r"<\|channel\|>final<\|message\|>(.*)", response_text, re.DOTALL)
        if not final_match: return False, "LLM did not produce a 'final' channel."
        final_content = final_match.group(1).strip()
        match = re.search(r"Score:\s*(\d+).*Justification:\s*(.*)", final_content, re.IGNORECASE)
        if not match: return False, "LLM 'final' channel had unexpected format."
        score, justification = int(match.group(1)), match.group(2).strip()
        if score >= RELEVANCE_THRESHOLD:
            return True, f"High thematic relevance (Score: {score}/10). Justification: {justification}"
        else:
            return False, f"Low thematic relevance (Score: {score}/10)."
    except Exception as e:
        logging.error(f"  - LLM thematic check failed: {e}")
        return False, "LLM analysis error."

def _confirm_keyword_relevance(llm: Llama, grammar: LlamaGrammar, article_text: str, knowledge_base: str) -> bool:
    """
    Step B: A focused check to confirm the article discusses specific concepts from the KB.
    This acts as a high-precision refinement filter.
    """
    prompt = f"""
You are a factual verification agent. Analyze the news article below.
Based *only* on the text of the article, does it explicitly discuss any of the core concepts or entities mentioned in the Knowledge Base Summary?
Your answer must be a single word: either "Yes" or "No".

--- KNOWLEDGE BASE SUMMARY ---
{knowledge_base[:3000]}

--- NEWS ARTICLE ---
{article_text[:4000]}
"""
    try:
        response = llm(prompt, max_tokens=3, temperature=0.0, grammar=grammar)
        answer = response['choices'][0]['text'].strip()
        return 'yes' in answer.lower()
    except Exception as e:
        logging.error(f"  - LLM keyword confirmation failed: {e}")
        return False

def summarize_with_llm(llm: Llama, title: str, article_text: str) -> str:
    """Generates a bulleted summary of the article."""
    prompt = f"You are a strategic analyst. Create a concise, insightful summary of the following news article as 3-5 bullet points.\n\n**Article Title:** {title}\n**Content:**\n{article_text[:6000]}"
    try:
        response = llm(prompt, max_tokens=300, temperature=0.3, echo=False)
        summary = response['choices'][0]['text'].strip()
        return re.sub(r"^\s*Here is a summary.*?:", "", summary, flags=re.IGNORECASE).strip()
    except Exception as e:
        logging.error(f"  - LLM summarization failed: {e}")
        return "Summarization failed due to an error."

# --- Main File I/O ---
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

# --- Main Execution ---
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

    llm, relevance_grammar, confirmation_grammar = load_llm()
    knowledge_base = extract_text_from_pdf(KNOWLEDGE_BASE_PDF_PATH)
    if not knowledge_base:
        logging.error("❌ Cannot proceed without a knowledge base. Halting.")
        sys.exit(1)

    logging.info(f"Processing {len(urls_to_process)} candidate URLs...")
    saved_count = 0

    for url in urls_to_process:
        logging.info(f"\n-> Processing URL: {url}")
        article_data = get_article_content(url)
        if not (article_data and article_data.get("content")):
            logging.error(f"  - ❌ FAILED to scrape content.")
            continue

        full_text = f"{article_data['title']}\n\n{article_data['content']}"

        # --- INSPIRED BY CERBERUS: Two-Step Filtering Logic ---
        # Step A: Check for broad thematic relevance.
        logging.info("  - Step A: Checking for broad thematic relevance...")
        passed_thematic, reason_thematic = _check_thematic_relevance(llm, relevance_grammar, full_text, knowledge_base)

        if not passed_thematic:
            logging.info(f"  - ❌ SKIPPED (Thematic): {reason_thematic}")
            continue

        # Step B: If Step A passed, perform a stricter keyword confirmation.
        logging.info("  - Step B: Thematic check passed. Confirming specific keyword relevance...")
        passed_confirmation = _confirm_keyword_relevance(llm, confirmation_grammar, full_text, knowledge_base)

        if passed_confirmation:
            logging.info(f"  - ✅ PASSED (Confirmation): Article explicitly discusses core concepts.")
            logging.info("  - Generating summary...")
            summary = summarize_with_llm(llm, article_data['title'], article_data['content'])
            db_entry = {
                "title": article_data['title'], "url": url,
                "reason": reason_thematic, "summary": summary
            }
            append_to_database(db_entry)
            logging.info(f"  - ✅ Saved to database.md")
            saved_count += 1
        else:
            logging.info(f"  - ❌ SKIPPED (Confirmation): Article does not explicitly discuss core concepts.")

        time.sleep(1)

    logging.info(f"\n--- Filtering & Saving Complete ---")
    logging.info(f"Saved {saved_count} new articles to database.md.")
