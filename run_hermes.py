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
WINDOW_HEIGHT = 750  # Increased height for progress bar

# --- NEW: User-friendly names for each script in the pipeline ---
SCRIPT_FRIENDLY_NAMES = {
    "report_generator.py": "Generating Knowledge Base",
    "source_generator.py": "Generating News Sources",  # NEW
    "hermes_discoverer.py": "Discovering Articles",
    "filter_and_save.py": "Filtering & Saving Articles",
    "visual_enhancer.py": "Enhancing with Visuals",
    "website_generator.py": "Building Website",
    "deployer.py": "Publishing to GitHub",
}


class HermesApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Project Hermes | AI Content Pipeline")
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)  # Log viewer is on row 2

        self.process_queue = queue.Queue()
        self.is_running = False
        self.create_widgets()
        self.check_process_queue()
        self._on_textbox_change()

    def create_widgets(self):
        # Header Frame
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

        # Theme Input Frame
        theme_frame = ctk.CTkFrame(self)
        theme_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        theme_frame.grid_columnconfigure(0, weight=1)
        theme_label = ctk.CTkLabel(theme_frame, text="Define Your Research Theme",
                                   font=ctk.CTkFont(size=14, weight="bold"))
        theme_label.grid(row=0, column=0, sticky="w", padx=15, pady=(10, 5))
        self.theme_textbox = ctk.CTkTextbox(theme_frame, height=120, font=("sans-serif", 14))
        self.theme_textbox.grid(row=1, column=0, sticky="ew", padx=15, pady=(0, 10))
        self.theme_textbox.insert("1.0",
                                  "I am interested in the emerging geopolitical risks affecting the global semiconductor supply chain, with a specific focus on the dependencies between US chip designers like NVIDIA, Taiwanese manufacturing by companies like TSMC, and Dutch ASML's dominance in EUV lithography equipment.")
        self.theme_textbox.bind("<KeyRelease>", self._on_textbox_change)

        # Log Viewer
        self.log_textbox = ctk.CTkTextbox(self, state="disabled", font=("monospace", 13))
        self.log_textbox.grid(row=2, column=0, sticky="nsew", padx=10, pady=0)

        # --- Progress Bar & Status ---
        progress_frame = ctk.CTkFrame(self)
        progress_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(10, 0))
        progress_frame.grid_columnconfigure(0, weight=1)

        self.progress_bar = ctk.CTkProgressBar(progress_frame, height=10)
        self.progress_bar.grid(row=0, column=0, sticky="ew", padx=5, pady=(5, 0))
        self.progress_bar.set(0)

        self.status_label = ctk.CTkLabel(progress_frame, text="Status: Ready", anchor="w")
        self.status_label.grid(row=1, column=0, sticky="ew", padx=5, pady=(0, 5))

        # Control Panel Frame
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=10)
        control_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.button_gen_pdf = ctk.CTkButton(control_frame, text="Generate Knowledge Base",
                                            command=lambda: self.start_task("pdf"))
        self.button_gen_pdf.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        self.button_run_pipeline = ctk.CTkButton(control_frame, text="Update & Publish Website",
                                                 command=lambda: self.start_task("news"))
        self.button_run_pipeline.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        self.button_full_run = ctk.CTkButton(control_frame, text="Full Run & Publish", fg_color="#1F6AA5",
                                             hover_color="#144E75", command=lambda: self.start_task("full"))
        self.button_full_run.grid(row=0, column=2, padx=10, pady=10, sticky="ew")

    def _on_textbox_change(self, event=None):
        has_text = bool(self.theme_textbox.get("1.0", "end-1c").strip())
        state = "normal" if has_text and not self.is_running else "disabled"
        self.button_gen_pdf.configure(state=state)
        self.button_full_run.configure(state=state)

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

        topic_paragraph = self.theme_textbox.get("1.0", "end-1c").strip()
        if task_type in ["pdf", "full"] and not topic_paragraph:
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
            scripts = ["source_generator.py", "hermes_discoverer.py", "filter_and_save.py", "visual_enhancer.py",
                       "website_generator.py", "deployer.py"]
            self.log_message("Starting Content Update & Deployment", "HEADER")
        elif task_type == "full":
            scripts = ["report_generator.py", "source_generator.py", "hermes_discoverer.py", "filter_and_save.py",
                       "visual_enhancer.py", "website_generator.py", "deployer.py"]
            self.log_message("Starting Full Run & Deployment...", "HEADER")

        threading.Thread(target=self.run_scripts_sequentially, args=(scripts, topic_paragraph), daemon=True).start()

    def update_progress(self, current_step, total_steps, script_name, status="running"):
        progress_value = current_step / total_steps
        friendly_name = SCRIPT_FRIENDLY_NAMES.get(script_name, script_name)
        status_text = f"Status: Step {current_step}/{total_steps}: {friendly_name}..."

        self.progress_bar.set(progress_value)
        self.status_label.configure(text=status_text)

        if status == "success":
            self.progress_bar.configure(progress_color="green")
            self.status_label.configure(text="Status: Completed Successfully", text_color="green")
        elif status == "error":
            self.progress_bar.configure(progress_color="red")
            self.status_label.configure(text=f"Status: Failed during {friendly_name}", text_color="red")

    def run_scripts_sequentially(self, scripts, topic_paragraph=None):
        env = os.environ.copy()
        if topic_paragraph:
            env['HERMES_TOPIC_PARAGRAPH'] = topic_paragraph

        total_steps = len(scripts)
        for i, script in enumerate(scripts):
            current_step = i + 1
            self.after(0, self.update_progress, current_step, total_steps, script)

            self.log_message(f"Executing: {script}", "INFO")
            command = [sys.executable, str(PROJECT_ROOT / script)]
            process = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, cwd=PROJECT_ROOT, bufsize=1, env=env
            )

            for line in iter(process.stdout.readline, ''):
                self.process_queue.put(line)

            process.stdout.close()
            return_code = process.wait()

            if return_code != 0:
                stderr_output = process.stderr.read()
                self.log_message(f"Error in {script}. Halting.", "ERROR")
                self.process_queue.put(stderr_output)
                self.after(0, self.update_progress, current_step, total_steps, script, "error")
                self.task_finished(success=False)
                return

        self.after(0, self.update_progress, total_steps, total_steps, scripts[-1], "success")
        self.task_finished(success=True)

    def task_finished(self, success):
        self.is_running = False
        self.update_ui_state("finished")
        if success:
            self.log_message("All tasks completed successfully!", "SUCCESS")
        else:
            self.log_message("Task failed. See log for details.", "ERROR")

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
            self.status_label.configure(text="Status: Initializing...", text_color="orange")
            self.progress_bar.set(0)
            self.progress_bar.configure(progress_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
            self.button_gen_pdf.configure(state="disabled")
            self.button_run_pipeline.configure(state="disabled")
            self.button_full_run.configure(state="disabled")
            self.theme_textbox.configure(state="disabled")
        else:  # finished
            self.button_gen_pdf.configure(state="normal")
            self.button_run_pipeline.configure(state="normal")
            self.button_full_run.configure(state="normal")
            self.theme_textbox.configure(state="normal")
            self._on_textbox_change()


if __name__ == "__main__":
    app = HermesApp()
    app.mainloop()