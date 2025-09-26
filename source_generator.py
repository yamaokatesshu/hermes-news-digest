# source_generator.py

import sys
import logging
import os
import yaml
import json
from pathlib import Path

# --- Dependency Imports ---
try:
    import requests
except ImportError:
    sys.exit("❌ Error: 'requests' library not found. Please run: pip install requests")

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DYNAMIC_SOURCES_PATH = OUTPUT_DIR / "dynamic_sources.yaml"

# --- UPDATED: Securely load API key using the exact logic from research_agent.py ---
# This reads from an environment variable first, providing a secure default.
API_KEY = os.getenv("GEMINI_API_KEY", "")
if not API_KEY:
    # Fallback if the environment variable is not set.
    # WARNING: Do not commit your API key directly into the code.
    API_KEY = "AIzaSyAv2C19Qlm77uPx7ulm2HeRoHDlT0zjsoo"

API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"

# Validation settings
VALIDATION_TIMEOUT = 10

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


def generate_sources_with_gemini(topic_paragraph: str) -> list[dict]:
    """
    Uses the Gemini API to generate a list of potential news sources.
    """
    logging.info("-> Asking Gemini API to discover relevant news sources...")

    if not API_KEY:
        logging.error("  - ❌ Gemini API key is not configured. Cannot proceed.")
        return []

    if not topic_paragraph:
        logging.error("  - ❌ Topic paragraph is empty. Cannot generate sources.")
        return []

    system_prompt = (
        "You are an expert research librarian. Your task is to identify a diverse range of high-quality "
        "news and information sources for a given topic. The list should include major news organizations, "
        "specialized industry blogs, any lesser known but relevant sources, and relevant academic journals or official publications. "
        "Respond ONLY with a JSON-formatted list of 20 objects, where each object has two keys: 'name' and 'url'."
    )

    payload = {
        "contents": [{"parts": [{"text": f"Topic: {topic_paragraph}"}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {"name": {"type": "STRING"}, "url": {"type": "STRING"}},
                    "required": ["name", "url"]
                }
            }
        }
    }

    try:
        response = requests.post(API_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=60)
        if response.status_code != 200:
            logging.error(f"  - ❌ Gemini API returned a non-200 status code: {response.status_code}")
            logging.error(f"     Response body: {response.text}")
            return []

        result = response.json()
        candidate = result.get('candidates', [{}])[0]

        if 'content' in candidate and 'parts' in candidate['content']:
            generated_list_str = candidate['content']['parts'][0]['text']
            source_list = json.loads(generated_list_str)
            logging.info(f"  - ✅ Gemini generated {len(source_list)} potential sources.")
            return source_list
        else:
            # Handle cases where the API call succeeds but the response is empty or unexpected (e.g., safety settings)
            logging.error(f"  - ❌ Gemini API returned an unexpected or empty response format.")
            logging.error(f"     Full response: {result}")
            return []

    except requests.exceptions.RequestException as e:
        logging.error(f"  - ❌ An error occurred during the Gemini API call: {e}")
        return []
    except json.JSONDecodeError as e:
        logging.error(f"  - ❌ Failed to parse the JSON response from Gemini: {e}")
        return []


def validate_sources(sources: list[dict]) -> list[dict]:
    """
    Validates a list of sources by making a HEAD request to each URL.
    """
    if not sources:
        return []

    logging.info("-> Validating generated sources...")
    validated_sources = []
    for source in sources:
        url = source.get("url")
        name = source.get("name", "Unnamed Source")
        if not url:
            continue

        logging.info(f"  - Checking: {name} ({url})")
        try:
            response = requests.head(url, timeout=VALIDATION_TIMEOUT, allow_redirects=True,
                                     headers={'User-Agent': 'Hermes-Source-Validator/1.0'})
            if response.status_code == 200:
                logging.info("    -> ✅ Valid (200 OK)")
                validated_sources.append(source)
            else:
                logging.warning(f"    -> ❌ Invalid (Status: {response.status_code})")
        except requests.RequestException:
            logging.warning(f"    -> ❌ Failed to connect or timed out.")

    logging.info(f"  - ✅ Validation complete. {len(validated_sources)} of {len(sources)} sources are live.")
    return validated_sources


def save_sources_to_yaml(sources: list[dict]):
    """Saves the final list of validated sources to a YAML file."""
    output_data = {"sources": sources or []}
    with open(DYNAMIC_SOURCES_PATH, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    if sources:
        logging.info(f"✅ Saved {len(sources)} validated sources to: {DYNAMIC_SOURCES_PATH}")
    else:
        logging.warning("No valid sources were found to save; an empty sources file was created.")


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Dynamic Source Generation ---")

    topic = os.getenv('HERMES_TOPIC_PARAGRAPH')
    if not topic:
        logging.error("❌ The HERMES_TOPIC_PARAGRAPH environment variable was not set.")
        sys.exit(1)

    potential_sources = generate_sources_with_gemini(topic)
    validated_sources = validate_sources(potential_sources)
    save_sources_to_yaml(validated_sources)

    logging.info("--- Dynamic Source Generation Complete ---")