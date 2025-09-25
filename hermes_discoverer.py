# hermes_discoverer.py

import yaml
import requests
import feedparser
import logging
import time
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from bs4 import BeautifulSoup
from requests.exceptions import RequestException
import sys
from typing import Optional, Dict, Set, List

# --- Dependency Imports ---
try:
    from dateutil.parser import parse as date_parser
except ImportError:
    sys.exit("❌ Error: 'python-dateutil' library not found. Please install it using: pip install python-dateutil")

# --- Configuration & Constants ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
# --- UPDATED: Define paths for both static and dynamic configs ---
STATIC_CONFIG_PATH = PROJECT_ROOT / "config_hermes.yaml"
DYNAMIC_CONFIG_PATH = OUTPUT_DIR / "dynamic_sources.yaml"

# File Paths
CANDIDATE_URLS_PATH = OUTPUT_DIR / "candidate_urls.txt"
PROCESSED_URLS_LOG_PATH = OUTPUT_DIR / "processed_urls.log"
GENERAL_LOG_PATH = OUTPUT_DIR / "discovery_general.log"

# Settings
SUMMARY_HOURS = 72
REQUEST_TIMEOUT = 25
POLITENESS_DELAY = 1
HEADERS = {'User-Agent': 'Hermes-News-Discoverer/1.0'}

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s',
    handlers=[
        logging.FileHandler(GENERAL_LOG_PATH, mode='w', encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)


# --- Helper Functions ---
def load_sources() -> List[Dict]:
    """Loads sources from both the static and the dynamic YAML files."""
    all_sources = []

    # 1. Load static, curated sources
    if not STATIC_CONFIG_PATH.is_file():
        logging.error(f"Static configuration file not found at {STATIC_CONFIG_PATH}")
        sys.exit(1)
    with open(STATIC_CONFIG_PATH, "r", encoding='utf-8') as f:
        static_config = yaml.safe_load(f)
        static_sources = static_config.get("sources", [])
        if static_sources:
            logging.info(f"Loaded {len(static_sources)} static sources from config_hermes.yaml.")
            all_sources.extend(static_sources)

    # 2. Load dynamic, AI-generated sources if they exist
    if DYNAMIC_CONFIG_PATH.is_file():
        with open(DYNAMIC_CONFIG_PATH, "r", encoding='utf-8') as f:
            dynamic_config = yaml.safe_load(f)
            # Add a check to handle empty or malformed dynamic source files
            if isinstance(dynamic_config, dict):
                dynamic_sources = dynamic_config.get("sources", [])
                if dynamic_sources:
                    logging.info(f"Loaded {len(dynamic_sources)} AI-generated sources for this topic.")
                    all_sources.extend(dynamic_sources)
            else:
                logging.warning("Dynamic sources file was not in the expected format (skipping).")
    else:
        logging.info("No dynamic sources file found. Proceeding with static sources only.")

    return all_sources


def load_processed_urls() -> Set[str]:
    """Loads the log of already processed URLs to avoid duplicates across runs."""
    if not PROCESSED_URLS_LOG_PATH.is_file():
        return set()
    with open(PROCESSED_URLS_LOG_PATH, "r", encoding='utf-8') as f:
        return {line.strip() for line in f if line.strip()}


def normalize_url(url: str) -> str:
    """Strips common tracking parameters and 'www.' from a URL."""
    try:
        from urllib.parse import urljoin, urlparse, urlunparse, parse_qs, urlencode
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        filtered_params = {k: v for k, v in params.items() if not k.startswith(('utm_', 'fbclid', 'gclid'))}
        netloc = parsed.netloc.replace('www.', '')
        new_query = urlencode(filtered_params, doseq=True)
        return urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception:
        return url


def find_article_date(soup: BeautifulSoup) -> Optional[datetime]:
    """Finds the publication date of an article from its HTML soup."""
    date_selectors = [
        ('meta', {'property': 'article:published_time'}),
        ('meta', {'name': 'publication_date'}),
        ('time', {'datetime': True})
    ]
    for tag, attrs in date_selectors:
        element = soup.find(tag, attrs)
        if element:
            date_str = element.get('content') or element.get('datetime')
            if date_str:
                try:
                    return date_parser(date_str).astimezone(timezone.utc)
                except (ValueError, TypeError):
                    continue
    return None


def process_rss_source(source_config: Dict, found_urls: Set, cutoff_time: datetime):
    url = source_config.get('url')
    logging.info(f"-> Processing RSS feed: {source_config.get('name')}")
    feed = feedparser.parse(url, agent=HEADERS['User-Agent'])
    if not feed.entries:
        logging.warning(f"  - Source '{source_config.get('name')}' is not a valid RSS or is empty. Trying as HTML.")
        return False

    count = 0
    for entry in feed.entries:
        link = entry.get("link")
        if not link: continue
        pub_date = None
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                pub_date = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
        if pub_date and pub_date >= cutoff_time:
            if normalize_url(link) not in found_urls:
                found_urls.add(normalize_url(link))
                count += 1
    logging.info(f"  - Found {count} new articles from RSS.")
    return True


def crawl_html_source(source_config: Dict, found_urls: Set, cutoff_time: datetime):
    from urllib.parse import urljoin, urlparse
    url, source_name = source_config.get('url'), source_config.get('name')
    logging.info(f"-> Crawling HTML page: '{source_name}'")
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        base_netloc = urlparse(url).netloc
        links_to_check = {normalize_url(urljoin(url, link['href'])) for link in soup.find_all('a', href=True)
                          if urlparse(urljoin(url, link['href'])).netloc == base_netloc and
                          urljoin(url, link['href']).startswith('http')}

        found_count = 0
        logging.info(f"  - Found {len(links_to_check)} potential links. Checking each for recency...")
        for i, article_url in enumerate(links_to_check):
            if i > 0 and i % 10 == 0:
                logging.info(f"    ({i}/{len(links_to_check)}) links checked...")
            if article_url in found_urls: continue

            logging.info(f"    - Checking: {article_url[:90]}")

            try:
                time.sleep(POLITENESS_DELAY)
                article_res = requests.get(article_url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
                article_res.raise_for_status()
                article_soup = BeautifulSoup(article_res.content, 'html.parser')
                pub_date = find_article_date(article_soup)
                if pub_date and pub_date >= cutoff_time:
                    logging.info(f"      -> Found recent article!")
                    found_urls.add(article_url)
                    found_count += 1
            except RequestException:
                continue
        logging.info(f"  - Found {found_count} new articles from crawling.")
    except RequestException as e:
        logging.error(f"Could not fetch HTML for '{source_name}': {e}")


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Article Discovery ---")

    # --- UPDATED: Load combined sources ---
    sources_to_process = load_sources()
    if not sources_to_process:
        logging.warning("No news sources found in static or dynamic configs. Exiting.")
        # Create an empty candidate file to allow the pipeline to continue gracefully
        with open(CANDIDATE_URLS_PATH, "w", encoding='utf-8') as f:
            pass
        sys.exit(0)

    processed_urls = load_processed_urls()
    logging.info(f"Loaded {len(processed_urls)} previously processed URLs from log.")

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=SUMMARY_HOURS)
    logging.info(f"Time Window: Fetching articles newer than {cutoff_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logging.info(f"Scanning a total of {len(sources_to_process)} sources...")

    all_candidate_urls = set()
    for source_config in sources_to_process:
        is_rss = process_rss_source(source_config, all_candidate_urls, cutoff_time)
        if not is_rss:
            crawl_html_source(source_config, all_candidate_urls, cutoff_time)

    # Filter out URLs that have already been processed in previous runs
    new_urls = sorted([url for url in all_candidate_urls if url not in processed_urls])

    logging.info("\n--- Discovery Phase Complete ---")
    with open(CANDIDATE_URLS_PATH, "w", encoding='utf-8') as f:
        for url in new_urls:
            f.write(url + "\n")

    logging.info(f"Found {len(new_urls)} new, unique article URLs to be processed.")
    logging.info(f"Saved candidate list to: {CANDIDATE_URLS_PATH}")
    logging.info("--- End of Discovery ---")

