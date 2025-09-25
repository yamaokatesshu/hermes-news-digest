# deployer.py
# Note GitHub key = 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

import sys
import logging
import subprocess
from pathlib import Path
from datetime import datetime

# --- Configuration ---
PROJECT_ROOT = Path(__file__).parent

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stdout)


def run_command(command: list):
    """Runs a command and streams its output, checking for errors."""
    logging.info(f"-> Running command: {' '.join(command)}")
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        cwd=PROJECT_ROOT,
        bufsize=1
    )

    # Stream stdout
    for line in iter(process.stdout.readline, ''):
        logging.info(f"   {line.strip()}")

    process.stdout.close()
    return_code = process.wait()

    if return_code != 0:
        stderr_output = process.stderr.read()
        logging.error(f"❌ Command failed with return code {return_code}")
        logging.error(stderr_output.strip())
        return False
    return True


if __name__ == "__main__":
    logging.info("--- Hermes: Starting Automated Deployment ---")

    # --- Step 1: Check for Git repository ---
    if not (PROJECT_ROOT / ".git").is_dir():
        logging.error("❌ This is not a Git repository. Cannot deploy.")
        logging.error("   Please run 'git init' and set up a remote repository.")
        sys.exit(1)

    # --- Step 2: Stage all changes ---
    # This will add the new index.html, new images, and the updated database.md
    if not run_command(["git", "add", "."]):
        sys.exit(1)

    # --- Step 3: Commit the changes ---
    commit_message = f"Automated content update: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    if not run_command(["git", "commit", "-m", commit_message]):
        # This might fail if there's nothing new to commit, which is not a critical error.
        logging.warning("Commit failed. This may be because there were no new changes to the website.")

    # --- Step 4: Push to the remote repository ---
    logging.info("Pushing changes to the live website...")
    if not run_command(["git", "push"]):
        sys.exit(1)

    logging.info("\n✅ Deployment successful!")
    logging.info("   Your website should be updated in a few moments.")
    logging.info("--- Deployment Complete ---")

