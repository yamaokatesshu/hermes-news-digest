# run_hermes.py

import sys
import subprocess
import threading
import queue
import os
from pathlib import Path

# --- Dependency Import ---
try:
    import customtkinter as ctk
except ImportError:
    print("❌ Error: 'customtkinter' library not found.")
    print("   Please install it by running: pip install customtkinter")
    sys.exit(1)

# --- Constants ---
PROJECT_ROOT = Path(__file__).parent
WINDOW_WIDTH = 900
WINDOW_HEIGHT = 720  # Increased height for the new input box

# --- App Styling ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class HermesApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Project Hermes | AI Content Pipeline")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Log viewer is now on row 2

        self.process_queue = queue.Queue()
        self.is_running = False
        self.create_widgets()
        self.check_process_queue()
        self._on_textbox_change()  # Initial check to set button state

    def create_widgets(self):
        # --- Header Frame ---
        header_frame = ctk.CTkFrame(self, corner_radius=0)
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        header_frame.grid_columnconfigure(1, weight=1)

        logo_canvas = ctk.CTkCanvas(header_frame, width=50, height=50, bg="#2b2b2b", highlightthickness=0)
        logo_canvas.grid(row=0, column=0, rowspan=2, padx=20, pady=10)
        self.draw_logo(logo_canvas)

        title_label = ctk.CTkLabel(header_frame, text="Project Hermes", font=ctk.CTkFont(size=24, weight="bold"))
        title_label.grid(row=0, column=1, sticky="w")
        subtitle_label = ctk.CTkLabel(header_frame, text="Your Automated AI Research & Publishing Assistant",
                                      font=ctk.CTkFont(size=12))
        subtitle_label.grid(row=1, column=1, sticky="w")

        # --- NEW: Theme Input Frame ---
        theme_frame = ctk.CTkFrame(self)
        theme_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        theme_frame.grid_columnconfigure(0, weight=1)

        theme_label = ctk.CTkLabel(theme_frame, text="Step 1: Define Your Research Theme",
                                   font=ctk.CTkFont(size=14, weight="bold"))
        theme_label.grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))

        self.theme_textbox = ctk.CTkTextbox(self, height=120, font=("sans-serif", 14))
        self.theme_textbox.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.theme_textbox.insert("1.0",
                                  "I am interested in the emerging geopolitical risks affecting the global semiconductor supply chain, with a specific focus on the dependencies between US chip designers like NVIDIA, Taiwanese manufacturing by companies like TSMC, and Dutch ASML's dominance in EUV lithography equipment.")
        self.theme_textbox.bind("<KeyRelease>", self._on_textbox_change)

        # --- Log Viewer (now on row 3) ---
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("monospace", 13))
        self.log_textbox.grid(row=3, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.grid_rowconfigure(3, weight=1)  # Make log viewer expand

        # --- Control Panel Frame ---
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=10)
        control_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.button_gen_pdf = ctk.CTkButton(control_frame, text="Generate Knowledge Base",
                                            command=lambda: self.start_task("pdf"))
        self.button_gen_pdf.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.button_run_pipeline = ctk.CTkButton(control_frame, text="Run News Pipeline",
                                                 command=lambda: self.start_task("news"))
        self.button_run_pipeline.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.button_full_run = ctk.CTkButton(control_frame, text="Full Run", fg_color="#1F6AA5", hover_color="#144E75",
                                             command=lambda: self.start_task("full"))
        self.button_full_run.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

        # --- Status Bar ---
        self.status_label = ctk.CTkLabel(self, text="Status: Ready", anchor="w")
        self.status_label.grid(row=5, column=0, sticky="ew", padx=10, pady=(5, 10))

    def _on_textbox_change(self, event=None):
        """Enable/disable buttons based on whether the textbox has content."""
        has_text = bool(self.theme_textbox.get("1.0", "end-1c").strip())
        if has_text:
            self.button_gen_pdf.configure(state="normal")
            self.button_full_run.configure(state="normal")
        else:
            self.button_gen_pdf.configure(state="disabled")
            self.button_full_run.configure(state="disabled")

    def draw_logo(self, canvas):
        canvas.create_line(10, 10, 10, 40, fill="#007BFF", width=4)
        canvas.create_line(40, 10, 40, 40, fill="#007BFF", width=4)
        canvas.create_line(10, 25, 40, 25, fill="#FFFFFF", width=4)
        canvas.create_line(25, 10, 40, 10, fill="#FFFFFF", width=3)
        canvas.create_line(25, 18, 40, 18, fill="#FFFFFF", width=3)

    def start_task(self, task_type):
        if self.is_running:
            self.log_message("A task is already running. Please wait.", "ERROR")
            return

        topic_paragraph = None
        if task_type in ["pdf", "full"]:
            topic_paragraph = self.theme_textbox.get("1.0", "end-1c").strip()
            if not topic_paragraph:
                self.log_message("Theme input cannot be empty to generate a knowledge base.", "ERROR")
                return

        self.is_running = True
        self.update_ui_state("running")
        self.log_textbox.configure(state="normal")
        self.log_textbox.delete("1.0", "end")
        self.log_textbox.configure(state="disabled")

        scripts = []
        if task_type == "pdf":
            scripts = ["report_generator.py"]
            self.log_message("Starting Phase 1: Research & PDF Generation", "HEADER")
        elif task_type == "news":
            scripts = ["hermes_discoverer.py"]
            self.log_message("Starting Phase 2: News Pipeline", "HEADER")
        elif task_type == "full":
            scripts = ["report_generator.py", "hermes_discoverer.py"]
            self.log_message("Starting Full Run...", "HEADER")

        threading.Thread(target=self.run_scripts_sequentially, args=(scripts, topic_paragraph), daemon=True).start()

    def run_scripts_sequentially(self, scripts, topic_paragraph=None):
        # --- NEW: Prepare environment for subprocess ---
        env = os.environ.copy()
        if topic_paragraph:
            env['HERMES_TOPIC_PARAGRAPH'] = topic_paragraph

        for script in scripts:
            self.log_message(f"Executing: {script}", "INFO")

            command = [sys.executable, str(PROJECT_ROOT / script)]
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=PROJECT_ROOT,
                bufsize=1,
                env=env  # Pass the environment to the child process
            )

            for line in iter(process.stdout.readline, ''):
                self.process_queue.put(line)

            process.stdout.close()
            return_code = process.wait()

            if return_code != 0:
                stderr_output = process.stderr.read()
                self.log_message(f"Error in {script}. Halting.", "ERROR")
                self.process_queue.put(stderr_output)
                self.task_finished(success=False)
                return

        self.task_finished(success=True)

    def task_finished(self, success):
        self.is_running = False
        if success:
            self.log_message("All tasks completed successfully!", "SUCCESS")
            self.update_ui_state("success")
        else:
            self.log_message("Task failed. See log for details.", "ERROR")
            self.update_ui_state("error")

    def check_process_queue(self):
        try:
            while True:
                line = self.process_queue.get_nowait()
                self.log_message(line.strip())
        except queue.Empty:
            pass
        self.after(100, self.check_process_queue)

    def log_message(self, message, level="NORMAL"):
        self.log_textbox.configure(state="normal")
        tag = f"tag-{level.lower()}"
        self.log_textbox.tag_config(tag, foreground=self.get_color_for_level(level))
        if level in ["HEADER", "INFO", "SUCCESS", "ERROR"]:
            self.log_textbox.insert("end", f"[{level}] {message}\n", tag)
        else:
            self.log_textbox.insert("end", f"{message}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def get_color_for_level(self, level):
        if level == "HEADER": return "#00AFFF"
        if level == "INFO": return "#007BFF"
        if level == "SUCCESS": return "#28a745"
        if level == "ERROR": return "#dc3545"
        return "white"

    def update_ui_state(self, state):
        if state == "running":
            self.status_label.configure(text="Status: Running...", text_color="orange")
            self.button_gen_pdf.configure(state="disabled")
            self.button_run_pipeline.configure(state="disabled")
            self.button_full_run.configure(state="disabled")
            self.theme_textbox.configure(state="disabled")
        else:
            self.button_gen_pdf.configure(state="normal")
            self.button_run_pipeline.configure(state="normal")
            self.button_full_run.configure(state="normal")
            self.theme_textbox.configure(state="normal")
            self._on_textbox_change()  # Re-check button state
            if state == "success":
                self.status_label.configure(text="Status: Completed Successfully", text_color="green")
            elif state == "error":
                self.status_label.configure(text="Status: Failed", text_color="red")


if __name__ == "__main__":
    app = HermesApp()
    app.mainloop()