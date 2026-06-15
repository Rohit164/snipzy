import os
import sys
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext

# Add snipzy dir to path so we can import main
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from main import PromptVideoCleaner, check_ffmpeg, RESOLUTION_MAP


class SnipzyApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Snipzy — Video Text Remover")
        self.root.geometry("580x560")
        self.root.resizable(False, False)
        self.root.configure(bg="#1e1e2e")

        self._build_ui()

    def _build_ui(self):
        PAD = {"padx": 16, "pady": 6}
        BG = "#1e1e2e"
        FG = "#cdd6f4"
        ENTRY_BG = "#313244"
        ACCENT = "#cba6f7"
        BTN_BG = "#cba6f7"
        BTN_FG = "#1e1e2e"

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground=ENTRY_BG, background=ENTRY_BG,
                        foreground=FG, arrowcolor=FG)
        style.configure("Horizontal.TProgressbar", troughcolor=ENTRY_BG,
                        background=ACCENT, bordercolor=BG, lightcolor=ACCENT, darkcolor=ACCENT)

        def label(parent, text, **kw):
            return tk.Label(parent, text=text, bg=BG, fg=FG, anchor="w",
                            font=("Segoe UI", 10), **kw)

        def entry(parent, textvariable, **kw):
            return tk.Entry(parent, textvariable=textvariable, bg=ENTRY_BG, fg=FG,
                            insertbackground=FG, relief="flat", font=("Segoe UI", 10),
                            highlightthickness=1, highlightbackground="#45475a",
                            highlightcolor=ACCENT, **kw)

        # Title
        tk.Label(self.root, text="✂  Snipzy", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(pady=(20, 4))
        tk.Label(self.root, text="Remove text & watermarks from video",
                 bg=BG, fg="#6c7086", font=("Segoe UI", 10)).pack(pady=(0, 16))

        frame = tk.Frame(self.root, bg=BG)
        frame.pack(fill="x", padx=20)

        # Input file
        label(frame, "Input Video").grid(row=0, column=0, sticky="w", pady=(0, 2))
        self.input_var = tk.StringVar()
        input_row = tk.Frame(frame, bg=BG)
        input_row.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        frame.columnconfigure(0, weight=1)
        input_row.columnconfigure(0, weight=1)
        entry(input_row, self.input_var).grid(row=0, column=0, sticky="ew", ipady=6, padx=(0, 6))
        tk.Button(input_row, text="Browse", bg=ENTRY_BG, fg=FG, relief="flat",
                  font=("Segoe UI", 9), cursor="hand2", activebackground="#45475a",
                  activeforeground=FG, command=self._browse_input).grid(row=0, column=1)

        # Text to remove
        label(frame, "Text / Watermark to Remove").grid(row=2, column=0, sticky="w", pady=(0, 2))
        self.text_var = tk.StringVar(value="@username")
        entry(frame, self.text_var).grid(row=3, column=0, sticky="ew", ipady=6, pady=(0, 10))

        # Quality + OCR every row
        opts_frame = tk.Frame(frame, bg=BG)
        opts_frame.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        opts_frame.columnconfigure(0, weight=1)
        opts_frame.columnconfigure(1, weight=1)

        label(opts_frame, "Output Quality").grid(row=0, column=0, sticky="w")
        label(opts_frame, "OCR Interval (frames)").grid(row=0, column=1, sticky="w", padx=(12, 0))

        self.quality_var = tk.StringVar(value="720p")
        quality_cb = ttk.Combobox(opts_frame, textvariable=self.quality_var,
                                   values=list(RESOLUTION_MAP.keys()), state="readonly", width=10)
        quality_cb.grid(row=1, column=0, sticky="w", ipady=4, pady=(2, 0))

        self.ocr_every_var = tk.StringVar(value="10")
        entry(opts_frame, self.ocr_every_var, width=8).grid(row=1, column=1, sticky="w",
                                                              padx=(12, 0), ipady=4, pady=(2, 0))

        # Output file
        label(frame, "Output Filename").grid(row=5, column=0, sticky="w", pady=(10, 2))
        self.output_var = tk.StringVar(value="cleaned.mp4")
        entry(frame, self.output_var).grid(row=6, column=0, sticky="ew", ipady=6, pady=(0, 16))

        # Progress bar
        self.progress = ttk.Progressbar(frame, mode="indeterminate",
                                         style="Horizontal.TProgressbar", length=400)
        self.progress.grid(row=7, column=0, sticky="ew", pady=(0, 12))

        # Run button
        self.run_btn = tk.Button(frame, text="Remove Text", bg=BTN_BG, fg=BTN_FG,
                                  font=("Segoe UI", 11, "bold"), relief="flat", cursor="hand2",
                                  activebackground="#b4befe", activeforeground=BTN_FG,
                                  pady=8, command=self._run)
        self.run_btn.grid(row=8, column=0, sticky="ew", pady=(0, 12))

        # Log output
        self.log = scrolledtext.ScrolledText(self.root, height=8, bg="#181825", fg="#a6e3a1",
                                              font=("Consolas", 9), relief="flat",
                                              state="disabled", wrap="word")
        self.log.pack(fill="x", padx=20, pady=(0, 16))

    def _browse_input(self):
        path = filedialog.askopenfilename(
            filetypes=[("Video files", "*.mp4 *.mov *.avi *.mkv *.webm"), ("All files", "*.*")]
        )
        if path:
            self.input_var.set(path)
            # auto-set output name next to input
            base = os.path.splitext(os.path.basename(path))[0]
            self.output_var.set(f"{base}_cleaned.mp4")

    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _run(self):
        input_path = self.input_var.get().strip()
        target_text = self.text_var.get().strip()
        quality = self.quality_var.get()
        output = self.output_var.get().strip()

        try:
            ocr_every = int(self.ocr_every_var.get())
        except ValueError:
            self._log("[ERROR] OCR Interval must be a number.")
            return

        if not input_path or not os.path.exists(input_path):
            self._log("[ERROR] Input file not found.")
            return
        if not target_text:
            self._log("[ERROR] Please enter the text to remove.")
            return

        self.run_btn.configure(state="disabled", text="Processing...")
        self.progress.start(10)
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

        threading.Thread(target=self._process,
                         args=(input_path, target_text, quality, output, ocr_every),
                         daemon=True).start()

    def _process(self, input_path, target_text, quality, output, ocr_every):
        DIR_FRAMES = "temp/frames"
        DIR_MASKS  = "temp/masks"
        DIR_CLEAN  = "temp/clean_frames"

        # Redirect stdout to log box
        original_stdout = sys.stdout
        sys.stdout = _LogRedirect(self._log)

        try:
            check_ffmpeg()
            cleaner = PromptVideoCleaner(ocr_scale=0.75)
            total, fps = cleaner.extract_and_mask(input_path, target_text, DIR_FRAMES, DIR_MASKS, ocr_every=ocr_every)
            cleaner.inpaint_frames(DIR_FRAMES, DIR_MASKS, DIR_CLEAN, total)
            cleaner.compile_and_transcode(DIR_CLEAN, input_path, output, quality, fps)
            shutil.rmtree("temp", ignore_errors=True)
        except Exception as e:
            self._log(f"[ERROR] {e}")
        finally:
            sys.stdout = original_stdout
            self.root.after(0, self._done)

    def _done(self):
        self.progress.stop()
        self.run_btn.configure(state="normal", text="Remove Text")


class _LogRedirect:
    """Redirects print() output into the UI log box."""
    def __init__(self, log_fn):
        self.log_fn = log_fn

    def write(self, msg):
        msg = msg.strip()
        if msg:
            self.log_fn(msg)

    def flush(self):
        pass


if __name__ == "__main__":
    root = tk.Tk()
    app = SnipzyApp(root)
    root.mainloop()
