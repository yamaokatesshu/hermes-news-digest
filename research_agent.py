# research_agent.py

import sys
import logging
from pathlib import Path
import os
import json
import time

# --- Dependency Imports ---
try:
    import requests
except ImportError:
    sys.exit("❌ Error: 'requests' library not found. Please run: pip install requests")

# --- Configuration ---
# IMPORTANT: It is recommended to set your Gemini API key as an environment variable
# for security. You can get a key from Google AI Studio.
API_KEY = os.getenv("GEMINI_API_KEY", "")
if not API_KEY:
    # Fallback if the environment variable is not set.
    # WARNING: Do not commit your API key directly into the code.
    API_KEY = "AIzaSyAv2C19Qlm77uPx7ulm2HeRoHDlT0zjsoo"

# --- API Settings ---
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent?key={API_KEY}"
HEADERS = {"Content-Type": "application/json"}

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)


def conduct_gemini_research(topic_paragraph: str) -> str:
    """
    Performs deep research on a topic using the Gemini API with Google Search grounding.
    """
    if API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        logging.error(
            "❌ FATAL: Gemini API key is not configured. Please set the GEMINI_API_KEY environment variable or update the script.")
        sys.exit(1)

    logging.info("Conducting deep research with the Gemini API...")

    # The system prompt instructs the model on its role and desired output format.
    system_prompt = (
        "You are a professional research analyst. Your task is to conduct a deep-dive research effort on the provided topic. "
        "Use your web search capabilities to find the most relevant, authoritative, and up-to-date sources. "
        "Synthesize the information from these sources into a comprehensive, well-structured report. The report must include an "
        "executive summary, identify 3-5 key themes with detailed bullet points, and conclude with a future outlook. "
        "The tone should be professional and analytical. Do not invent any information."
    )

    # The payload for the Gemini API call
    payload = {
        "contents": [{"parts": [{"text": topic_paragraph}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        # This is the crucial part: enabling Google Search grounding
        "tools": [{"google_search": {}}]
    }

    # Exponential backoff for API retries
    max_retries = 5
    backoff_factor = 2
    for attempt in range(max_retries):
        try:
            response = requests.post(API_URL, headers=HEADERS, data=json.dumps(payload), timeout=300)
            response.raise_for_status()  # Raises an exception for bad status codes (4xx or 5xx)

            response_json = response.json()

            # Extract the generated text content
            candidate = response_json.get("candidates", [{}])[0]
            content_part = candidate.get("content", {}).get("parts", [{}])[0]
            research_text = content_part.get("text", "")

            if research_text:
                logging.info("✅ Gemini API research successful.")
                return research_text
            else:
                logging.error(f"❌ Gemini API returned an empty response. Full response: {response_json}")
                return ""

        except requests.exceptions.RequestException as e:
            logging.warning(f"API request failed on attempt {attempt + 1}/{max_retries}. Error: {e}")
            if attempt < max_retries - 1:
                sleep_time = backoff_factor ** attempt
                logging.info(f"Retrying in {sleep_time} seconds...")
                time.sleep(sleep_time)
            else:
                logging.error("❌ All API retries failed.")
                return ""

    return ""


if __name__ == '__main__':
    example_topic = (
        "I am interested in the emerging geopolitical risks affecting the global semiconductor "
        "supply chain, with a specific focus on the dependencies between US chip designers like NVIDIA, "
        "Taiwanese manufacturing by companies like TSMC, and Dutch ASML's dominance in EUV lithography equipment."
    )

    print("--- 🚀 Starting Hermes Research Agent (Gemini API) ---")
    research_content = conduct_gemini_research(example_topic)

    if research_content:
        print("\n--- ✅ Research Conducted Successfully ---")
        print(f"Total characters of research material collected: {len(research_content)}")
        # In the full pipeline, this 'research_content' would be passed to 'report_generator.py'
        # To see the output, you could uncomment the next line:
        # print("\n--- RESEARCH REPORT ---\n", research_content)
    else:
        print("\n--- ❌ Research Failed ---")

