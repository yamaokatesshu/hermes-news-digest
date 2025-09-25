# source_generator.py

import sys
import logging
import os
import yaml
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

# Gemini API settings
API_KEY = "AIzaSyAv2C19Qlm77uPx7ulm2HeRoHDlT0zjsoo"  # Handled by the execution environment
# --- FIX: Corrected the typo in the Gemini API URL ---
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"

# Validation settings
VALIDATION_TIMEOUT = 10  # Seconds to wait for a response from a potential source

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


def generate_sources_with_gemini(topic_paragraph: str) -> list[dict]:
    """
    Uses the Gemini API to generate a list of potential news sources.
    """
    logging.info("-> Asking Gemini API to discover relevant news sources...")

    if not topic_paragraph:
        logging.error("  - ❌ Topic paragraph is empty. Cannot generate sources.")
        return []

    # This prompt is engineered to get a diverse, structured list.
    system_prompt = (
        "You are an expert research librarian. Your task is to identify a diverse range of high-quality "
        "news and information sources for a given topic. The list should include major news organizations, "
        "specialized industry blogs, any lesser known but relevant sources, relevant academic journals or official publications especially if they are quoted often. "
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
                    "properties": {
                        "name": {"type": "STRING"},
                        "url": {"type": "STRING"}
                    },
                    "required": ["name", "url"]
                }
            }
        }
    }

    try:
        response = requests.post(API_URL, json=payload, headers={'Content-Type': 'application/json'}, timeout=60)
        response.raise_for_status()
        result = response.json()

        candidate = result.get('candidates', [{}])[0]
        if 'content' in candidate and 'parts' in candidate['content']:
            generated_list_str = candidate['content']['parts'][0]['text']
            import json
            source_list = json.loads(generated_list_str)
            logging.info(f"  - ✅ Gemini generated {len(source_list)} potential sources.")
            return source_list
        else:
            logging.error(f"  - ❌ Gemini API returned an unexpected response format: {result}")
            return []
    except Exception as e:
        logging.error(f"  - ❌ An error occurred during Gemini API call: {e}")
        return []


def validate_sources(sources: list[dict]) -> list[dict]:
    """
    Validates a list of sources by making a HEAD request to each URL.
    Returns a new list containing only the valid sources.
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
            # Use a HEAD request for efficiency - we only need the status code.
            response = requests.head(url, timeout=VALIDATION_TIMEOUT, allow_redirects=True,
                                     headers={'User-Agent': 'Hermes-Source-Validator/1.0'})
            if response.status_code == 200:
                logging.info("    -> ✅ Valid (200 OK)")
                validated_sources.append(source)
            else:
                logging.warning(f"    -> ❌ Invalid (Status: {response.status_code})")
        except requests.RequestException as e:
            logging.warning(f"    -> ❌ Failed to connect: {e.__class__.__name__}")

    logging.info(f"  - ✅ Validation complete. {len(validated_sources)} of {len(sources)} sources are live.")
    return validated_sources


def save_sources_to_yaml(sources: list[dict]):
    """Saves the final list of validated sources to a YAML file."""
    # --- FIX: Ensure the output file is always a dictionary, even if empty ---
    # This prevents the next script from crashing if no sources are found.
    output_data = {"sources": sources or []}

    with open(DYNAMIC_SOURCES_PATH, "w", encoding="utf-8") as f:
        yaml.dump(output_data, f, default_flow_style=False, sort_keys=False)

    if sources:
        logging.info(f"✅ Saved {len(sources)} validated sources to: {DYNAMIC_SOURCES_PATH}")
    else:
        logging.warning("No valid sources were found to save, an empty sources file was created.")


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Dynamic Source Generation ---")

    # Read the topic from the environment variable set by the GUI controller
    topic = os.getenv('HERMES_TOPIC_PARAGRAPH')
    if not topic:
        logging.error("❌ The HERMES_TOPIC_PARAGRAPH environment variable was not set.")
        logging.error("   This script should be run from the main Hermes GUI.")
        sys.exit(1)

    # 1. Generate a list of potential sources with the Gemini API
    potential_sources = generate_sources_with_gemini(topic)

    # 2. Validate each source to ensure it's a working URL
    validated_sources = validate_sources(potential_sources)

    # 3. Save the final, validated list to a YAML file for the next script
    save_sources_to_yaml(validated_sources)

    logging.info("--- Dynamic Source Generation Complete ---")

