# website_generator.py

import sys
import logging
import re
import shutil
from pathlib import Path
from datetime import datetime

# --- Dependency Imports ---
try:
    from jinja2 import Environment, FileSystemLoader
except ImportError:
    sys.exit("❌ Error: 'Jinja2' library not found. Please run: pip install Jinja2")

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent
DATABASE_MD_PATH = PROJECT_ROOT / "database.md"
ADS_MD_PATH = PROJECT_ROOT / "ads.md"
IMAGES_DIR = PROJECT_ROOT / "images"

# The final website will be generated in a clean 'build' directory
BUILD_DIR = PROJECT_ROOT / "build"
BUILD_IMAGES_DIR = BUILD_DIR / "images"

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


# --- Helper Functions ---
def parse_database():
    """Parses the Markdown database and returns a list of article dictionaries."""
    if not DATABASE_MD_PATH.is_file():
        logging.warning("database.md not found. Cannot build website.")
        return []

    with open(DATABASE_MD_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    articles = []
    article_chunks = re.split(r'--- ARTICLE START ---', content)
    for article_text in article_chunks:
        if not article_text.strip():
            continue

        article_data = {}
        # Use regex to robustly capture key-value pairs
        for match in re.finditer(r"^(.*?):\s*(.*)", article_text, re.MULTILINE):
            key, value = match.groups()
            article_data[key.strip()] = value.strip()

        summary_match = re.search(r'Summary:\n(.*)', article_text, re.DOTALL)
        if summary_match:
            article_data['Summary'] = summary_match.group(1).strip()

        if 'Title' in article_data:
            articles.append(article_data)

    # Sort articles by date processed, newest first
    articles.sort(key=lambda x: x.get('Date_Processed', '0000-00-00'), reverse=True)
    return articles


def load_ads():
    """Loads ad snippets from the ads.md file."""
    if not ADS_MD_PATH.is_file():
        return []
    with open(ADS_MD_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split ads by a clear delimiter
    return [ad.strip() for ad in re.split(r'<!--.*?-->', content) if ad.strip()]


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Website Generation ---")

    # --- 1. Prepare Build Directory ---
    if BUILD_DIR.exists():
        logging.info("Clearing previous build directory...")
        shutil.rmtree(BUILD_DIR)
    BUILD_DIR.mkdir()

    # Copy images to the build directory
    if IMAGES_DIR.exists():
        logging.info("Copying images to build directory...")
        shutil.copytree(IMAGES_DIR, BUILD_IMAGES_DIR)

    # --- 2. Load Content ---
    articles = parse_database()
    ads = load_ads()

    if not articles:
        logging.info("No articles found in database.md. Website will be empty.")

    # --- 3. Weave Ads into Content ---
    # Intersperse an ad every 5 articles, for example.
    items_for_template = []
    ad_index = 0
    for i, article in enumerate(articles):
        items_for_template.append({'type': 'article', 'data': article})
        if (i + 1) % 5 == 0 and ad_index < len(ads):
            items_for_template.append({'type': 'ad', 'data': ads[ad_index]})
            ad_index += 1

    # --- 4. Render HTML using Jinja2 Template ---
    logging.info("Rendering HTML from template...")
    env = Environment(loader=FileSystemLoader(PROJECT_ROOT))
    template = env.get_template('template.html')

    html_content = template.render(
        page_title="Hermes News Digest",
        generation_date=datetime.now().strftime('%B %d, %Y'),
        items=items_for_template
    )

    # --- 5. Save Final Website ---
    output_path = BUILD_DIR / "index.html"
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    logging.info(f"✅ Website successfully generated at: {output_path}")
    logging.info("--- Website Generation Complete ---")
