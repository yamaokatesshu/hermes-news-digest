# visual_enhancer.py

import sys
import logging
import re
import base64
from pathlib import Path
from urllib.parse import urljoin

# --- Dependency Imports ---
try:
    import requests
    from PIL import Image
    from io import BytesIO
except ImportError as e:
    sys.exit(f"❌ Error: Missing a required library ({e.name}). Please run: pip install Pillow requests")

try:
    from llama_cpp import Llama
    from llama_cpp.llama_chat_format import Llava15ChatHandler
except ImportError:
    sys.exit("❌ Error: 'llama-cpp-python' library not found. Please run: pip install llama-cpp-python")

try:
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("❌ Error: 'beautifulsoup4' library not found. Please run: pip install beautifulsoup4")

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent
DATABASE_MD_PATH = PROJECT_ROOT / "database.md"
IMAGES_DIR = PROJECT_ROOT / "images"
IMAGES_DIR.mkdir(exist_ok=True)

# --- Model Paths (as provided by you) ---
PIXTRAL_MODEL_PATH = Path("/home/benjamincros76/PycharmProjects/Image_Engine/mistral-community_pixtral-12b-Q6_K.gguf")
PIXTRAL_MMPROJ_PATH = Path(
    "/home/benjamincros76/PycharmProjects/Image_Engine/mmproj-mistral-community_pixtral-12b-f16.gguf")

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


# --- Helper Functions ---
def parse_database():
    """Parses the Markdown database and yields each article as a dictionary."""
    if not DATABASE_MD_PATH.is_file():
        return
    with open(DATABASE_MD_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    articles = re.split(r'--- ARTICLE START ---', content)
    for article_text in articles:
        if not article_text.strip():
            continue

        article_data = {}
        for line in article_text.strip().split('\n'):
            if ': ' in line:
                key, value = line.split(': ', 1)
                article_data[key.strip()] = value.strip()

        summary_match = re.search(r'Summary:\n(.*)', article_text, re.DOTALL)
        if summary_match:
            article_data['Summary'] = summary_match.group(1).strip()

        # Store original text to reconstruct the file
        article_data['original_text'] = article_text
        yield article_data


def update_database(all_articles):
    """Rewrites the database file with updated article information."""
    output_content = []
    for article in all_articles:
        # Reconstruct the entry from the dictionary
        entry = "--- ARTICLE START ---\n"
        # Define a consistent order for keys
        key_order = ["Title", "URL", "Date_Processed", "Image_Path", "Image_Alt_Text", "Image_Caption", "Reason"]
        for key in key_order:
            if key in article and article[key]:
                entry += f"{key}: {article[key]}\n"
        if "Summary" in article and article["Summary"]:
            entry += f"Summary:\n{article['Summary']}\n"
        entry += "--- ARTICLE END ---\n\n"
        output_content.append(entry)

    with open(DATABASE_MD_PATH, 'w', encoding='utf-8') as f:
        f.write("".join(output_content))


def download_hero_image(article_url: str, title: str) -> Path | None:
    """Finds and downloads the best 'hero' image from an article URL."""
    try:
        response = requests.get(article_url, headers={'User-Agent': 'Hermes-Visual-Agent/1.0'}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Strategy 1: Look for the OpenGraph image meta tag (most reliable)
        og_image = soup.find('meta', property='og:image')
        if og_image and og_image.get('content'):
            image_url = og_image['content']
        else:
            # Strategy 2: Find the largest image on the page (heuristic)
            images = soup.find_all('img')
            largest_image_url = None
            max_area = 0
            for img in images:
                src = img.get('src')
                if not src or src.startswith('data:'):
                    continue
                try:
                    width = int(img.get('width', 0))
                    height = int(img.get('height', 0))
                    area = width * height
                    if area > max_area:
                        max_area = area
                        largest_image_url = src
                except (ValueError, TypeError):
                    continue
            if not largest_image_url:
                logging.warning("  - No suitable image found on page.")
                return None
            image_url = largest_image_url

        # Make relative URLs absolute
        image_url = urljoin(article_url, image_url)

        # Download the image
        img_response = requests.get(image_url, timeout=15)
        img_response.raise_for_status()
        image = Image.open(BytesIO(img_response.content))

        # Sanitize title for filename
        safe_filename = re.sub(r'[\\/*?:"<>|]', "", title)[:50] + ".jpg"
        save_path = IMAGES_DIR / safe_filename

        # Convert to RGB if it's not, to ensure it saves as JPG
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")

        image.save(save_path, "JPEG", quality=85)
        logging.info(f"  - ✅ Image downloaded and saved to {save_path}")
        return save_path
    except Exception as e:
        logging.error(f"  - ❌ Failed to download image: {e}")
        return None


def get_image_analysis(llm, image_path: Path, summary: str) -> (str, str):
    """Uses Pixtral to generate alt-text and a caption for an image."""
    try:
        with open(image_path, "rb") as f:
            image_bytes = f.read()

        data_uri = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("utf-8")

        # --- FIX: Truncate the summary to prevent context overflow ---
        # Keep the summary reasonably short to leave room for the image and prompt.
        truncated_summary = summary[:1000]

        prompt = (
            "Analyze this image in the context of the provided news summary. "
            "Respond in a JSON format with two keys: "
            "1) 'alt_text': A concise, SEO-friendly description of the image's contents. "
            "2) 'caption': A compelling one-sentence caption that links the image to the news story.\n"
            f"NEWS SUMMARY: {truncated_summary}" # Use the truncated summary
        )

        response = llm.create_chat_completion(
            messages=[
                {"role": "user", "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt}
                ]}
            ],
            response_format={"type": "json_object"},
            temperature=0.4
        )

        result = response['choices'][0]['message']['content']
        import json
        data = json.loads(result)

        alt_text = data.get("alt_text", "No alt-text generated.")
        caption = data.get("caption", "No caption generated.")

        logging.info("  - ✅ Image analysis successful.")
        return alt_text, caption
    except Exception as e:
        logging.error(f"  - ❌ Pixtral analysis failed: {e}")
        return "A descriptive image.", "An illustrative image related to the article."


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Visual Enhancement ---")

    all_articles = list(parse_database())
    if not all_articles:
        logging.info("database.md is empty or not found. Nothing to enhance.")
        sys.exit(0)

    articles_to_process = [a for a in all_articles if "Image_Path" not in a]

    if not articles_to_process:
        logging.info("All articles in the database already have images. Exiting.")
        sys.exit(0)

    logging.info(f"Found {len(articles_to_process)} new articles to enhance with visuals.")

    # --- Load Pixtral Model ---
    try:
        chat_handler = Llava15ChatHandler(clip_model_path=str(PIXTRAL_MMPROJ_PATH), verbose=False)
        llm = Llama(
            model_path=str(PIXTRAL_MODEL_PATH),
            chat_handler=chat_handler,
            n_ctx=2048,
            n_gpu_layers=-1,
            verbose=False,
        )
        logging.info("✅ Pixtral multimodal model loaded successfully.")
    except Exception as e:
        logging.error(f"❌ Failed to load Pixtral model. Halting. Error: {e}")
        sys.exit(1)

    # --- Main Processing Loop ---
    for article in all_articles:
        if "Image_Path" not in article:
            logging.info(f"\n-> Processing article: {article['Title']}")

            # 1. Download image
            image_path = download_hero_image(article['URL'], article['Title'])
            if image_path:
                article['Image_Path'] = str(image_path.relative_to(PROJECT_ROOT))

                # 2. Analyze with Pixtral
                alt, caption = get_image_analysis(llm, image_path, article['Summary'])
                article['Image_Alt_Text'] = alt
                article['Image_Caption'] = caption
            else:
                # Mark as processed even if image fails so we don't retry every time
                article['Image_Path'] = "download_failed"
                article['Image_Alt_Text'] = ""
                article['Image_Caption'] = ""

    # --- 3. Update the database file with all changes ---
    logging.info("\nUpdating database.md with new visual metadata...")
    update_database(all_articles)

    logging.info("--- Visual Enhancement Complete ---")

