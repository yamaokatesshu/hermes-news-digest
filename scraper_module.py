# scraper_module.py

import requests
import logging
import sys
from requests.exceptions import RequestException
from bs4 import BeautifulSoup
from typing import Optional

# --- Dependency Imports ---
# Selenium is used as a fallback for complex, JavaScript-heavy websites.
SELENIUM_AVAILABLE = False
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from webdriver_manager.chrome import ChromeDriverManager

    SELENIUM_AVAILABLE = True
except ImportError:
    # This is not a fatal error; the script can run without Selenium, but it will be less effective.
    print("⚠️ Warning: Selenium libraries not found. Scraping will rely only on the basic method.")
    print("   For best results, install with: pip install selenium webdriver-manager")

# --- Configuration & Constants ---
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}
REQUEST_TIMEOUT = 30
SELENIUM_WAIT_TIMEOUT = 20

# --- Content Extraction Settings ---
MIN_CONTENT_LENGTH = 200  # Ignore pages with less than this many characters of meaningful text
MIN_PARAGRAPH_LENGTH = 50  # Ignore short paragraphs, which are often boilerplate or captions

# --- Selenium Options (if available) ---
if SELENIUM_AVAILABLE:
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")  # Run browser in the background
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--log-level=3")  # Suppress console noise from Chrome
    chrome_options.add_argument(f"user-agent={HEADERS['User-Agent']}")
    chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])


def extract_text_from_soup(soup: BeautifulSoup) -> Optional[str]:
    """
    Extracts meaningful text content from a BeautifulSoup object.
    It joins all paragraph ('p') tags that meet a minimum length requirement.
    """
    # Remove irrelevant tags like scripts, styles, and navigation to clean up the content
    for element in soup(["script", "style", "nav", "header", "footer", "aside"]):
        element.decompose()

    paragraphs = soup.find_all('p', recursive=True)
    article_text = "\n".join(
        p.get_text(strip=True) for p in paragraphs
        if len(p.get_text(strip=True)) >= MIN_PARAGRAPH_LENGTH
    )

    if len(article_text) >= MIN_CONTENT_LENGTH:
        return article_text.strip()
    return None


def _attempt_requests_extraction(url: str) -> Optional[str]:
    """Primary, fast scraping method using the Requests library."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        return extract_text_from_soup(soup)
    except RequestException as e:
        logging.warning(f"    - Requests method failed: {e}")
        return None


def _attempt_selenium_extraction(url: str) -> Optional[str]:
    """Fallback method using a real browser via Selenium for dynamic sites."""
    if not SELENIUM_AVAILABLE:
        logging.warning("    - Skipping Selenium fallback: libraries not installed.")
        return None

    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)

        # Wait for the main body of the page to be present
        WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )

        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        return extract_text_from_soup(soup)
    except Exception as e:
        logging.error(f"    - Selenium method failed: {e}")
        return None
    finally:
        if driver:
            driver.quit()


def get_article_content(url: str) -> Optional[dict]:
    """
    Main function to scrape an article. Tries the fast Requests method first,
    then automatically triggers the Selenium fallback if it fails.

    Returns a dictionary with title and content, or None if scraping fails.
    """
    logging.info("    - Trying fast method (Requests)...")
    try:
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        title = soup.title.string.strip() if soup.title and soup.title.string else "No Title Found"
        content = extract_text_from_soup(soup)

        if content:
            logging.info(f"    ✅ Success (Requests): Extracted ~{len(content)} chars.")
            return {"title": title, "content": content}

    except RequestException as e:
        logging.warning(f"    - Requests method failed: {e}")

    # If the fast method failed or didn't find enough content, try Selenium
    logging.info("    - Fast method failed. Trying robust method (Selenium)...")

    if not SELENIUM_AVAILABLE:
        logging.warning("    - Skipping Selenium fallback: libraries not installed.")
        return None

    driver = None
    try:
        service = ChromeService(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.get(url)

        WebDriverWait(driver, SELENIUM_WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
        )

        title = driver.title if driver.title else "No Title Found"
        page_source = driver.page_source
        soup = BeautifulSoup(page_source, 'html.parser')
        content = extract_text_from_soup(soup)

        if content:
            logging.info(f"    ✅ Success (Selenium): Extracted ~{len(content)} chars.")
            return {"title": title, "content": content}

    except Exception as e:
        logging.error(f"    - Selenium method failed: {e}")
        return None
    finally:
        if driver:
            driver.quit()

    return None  # Return None if all methods fail
