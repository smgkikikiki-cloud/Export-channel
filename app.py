"""Paste text, review, generate. Local desktop UI; no web server."""
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk

from narration import DEFAULT_MODEL, DEFAULT_VOICE, PipelineError, make_plan, run


class App:
    def __init__(self, window):
        self.window = window
        self.root = Path(__file__).resolve().parent / "work"
        self.events = queue.Queue()
        self.busy = False
        self.output = None
        self.approved = None
        window.title("Narration Desk — English to CapCut")
        window.geometry("940x730")
        window.minsize(720, 570)
        window.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(window, padding=18)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Narration Desk", font=("Arial", 20, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Paste final English text → Speechify → 5-minute WAV files. Edit footage in CapCut.").pack(anchor="w", pady=(4, 12))
        settings = ttk.Frame(frame)
        settings.pack(fill="x")
        self.key = tk.StringVar(value=os.environ.get("SPEECHIFY_API_KEY", ""))
        self.voice = tk.StringVar(value=DEFAULT_VOICE)
        self.model = tk.StringVar(value=DEFAULT_MODEL)
        for row, (label, variable, hidden) in enumerate([
            ("Speechify API key (stays in memory)", self.key, True),
            ("Voice ID", self.voice, False), ("Model", self.model, False)]):
            ttk.Label(settings, text=label).grid(row=row, column=0, sticky="w", padx=(0, 12), pady=3)
            ttk.Entry(settings, textvariable=variable, show="*" if hidden else "", width=55).grid(row=row, column=1, sticky="ew", pady=3)
        settings.columnconfigure(1, weight=1)
        self.text = scrolledtext.ScrolledText(frame, wrap="word", font=("Arial", 11), undo=True, height=16)
        self.text.pack(fill="both", expand=True, pady=12)
        controls = ttk.Frame(frame)
        controls.pack(fill="x")
        self.load_button = ttk.Button(controls, text="Load .txt", command=self.load)
        self.load_button.pack(side="left")
        self.plan_button = ttk.Button(controls, text="1. Review (free)", command=self.review)
        self.plan_button.pack(side="left", padx=8)
        self.generate_button = ttk.Button(controls, text="2. Generate audio", command=self.generate, state="disabled")
        self.generate_button.pack(side="left")
        self.open_button = ttk.Button(controls, text="Open output folder", command=self.open_output, state="disabled")
        self.open_button.pack(side="right")
        self.status = tk.StringVar(value="No API request is made until you click Generate audio.")
        ttk.Label(frame, textvariable=self.status, wraplength=870).pack(anchor="w", pady=10)
        self.logs = scrolledtext.ScrolledText(frame, height=7, wrap="word", state="disabled")
        self.logs.pack(fill="x")
        window.after(100, self.poll)

    def snapshot(self):
        return self.text.get("1.0", "end-1c"), self.voice.get().strip(), self.model.get().strip()

    def load(self):
        filename = filedialog.askopenfilename(filetypes=[("Text", "*.txt"), ("All files", "*.*")])
        if filename:
            try:
                value = Path(filename).read_text(encoding="utf-8-sig")
                self.text.delete("1.0", "end")
                self.text.insert("1.0", value)
                self.generate_button.configure(state="disabled")
            except (OSError, UnicodeError):
                messagebox.showerror("Cannot load", "Use a UTF-8 .txt file.")

    def review(self):
        try:
            text, voice, model = self.snapshot()
            plan = make_plan(text, self.root, voice, model)
            blocked = any(r["status"] == "blocked" for r in plan["rows"])
            new = sum(r["status"] == "new" for r in plan["rows"])
            cached = sum(r["status"] == "cached" for r in plan["rows"])
            self.approved = (text, voice, model)
            self.status.set(f"{len(text):,} input characters | {new} new API request(s), {cached} cached | "
                            f"~{plan['estimated_minutes_at_150_wpm']:.1f} min at an assumed 150 words/min. "
                            f"Up to {plan['new_characters_upper_bound']:,} characters submitted anew. "
                            + ("BLOCKED: review earlier incomplete work; see README." if blocked else "Generate will use your API allowance; actual billable count comes from Speechify."))
            self.generate_button.configure(state="disabled" if blocked else "normal")
        except PipelineError as exc:
            self.generate_button.configure(state="disabled")
            messagebox.showerror("Review", str(exc))

    def generate(self):
        current = self.snapshot()
        if current != self.approved:
            self.review()
            messagebox.showinfo("Text or voice changed", "Review the updated plan, then click Generate again.")
            return
        self.busy = True
        for button in (self.load_button, self.plan_button, self.generate_button):
            button.configure(state="disabled")
        text, voice, model = current
        api_key = self.key.get()
        self.status.set("Working. Existing completed requests will be reused. No automatic retries.")

        def worker():
            try:
                output = run(text, self.root, api_key, voice, model, log=lambda value: self.events.put(("log", value)))
                self.events.put(("done", output))
            except Exception as exc:
                self.events.put(("error", str(exc) if isinstance(exc, PipelineError) else "Local operation failed. Existing cache retained; no automatic regeneration."))

        threading.Thread(target=worker, daemon=False).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == "log":
                    self.logs.configure(state="normal")
                    self.logs.insert("end", value + "\n")
                    self.logs.see("end")
                    self.logs.configure(state="disabled")
                else:
                    self.busy = False
                    self.load_button.configure(state="normal")
                    self.plan_button.configure(state="normal")
                    if kind == "done":
                        self.output = value
                        self.open_button.configure(state="normal")
                        self.status.set("Done. Import narration_001.wav, narration_002.wav, ... into CapCut in order, with no gaps.")
                    else:
                        self.status.set(value)
                        messagebox.showerror("Stopped without retry", value)
        except queue.Empty:
            pass
        self.window.after(100, self.poll)

    def open_output(self):
        try:
            if sys.platform == "win32":
                os.startfile(self.output)
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(self.output)])
        except OSError:
            messagebox.showinfo("Output folder", str(self.output))

    def close(self):
        if self.busy:
            messagebox.showinfo("Generation is running", "Let the current request finish before closing, so paid audio is not interrupted.")
            return
        self.window.destroy()


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
