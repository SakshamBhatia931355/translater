"""Small Windows UI for image upload, pronunciation, phrase translation and webcam."""
import queue
import json
import socket
import subprocess
import sys
import threading
import urllib.request
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageDraw, ImageTk

from config import KANA, ROOT
from predict import predict_line


if "--webcam" in sys.argv:
    sys.argv = [sys.argv[0], *[arg for arg in sys.argv[1:] if arg != "--webcam"]]
    from webcam_app import main as webcam_main
    webcam_main()
    raise SystemExit(0)


class KanaReaderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Sakura Kana · Japanese practice")
        self.root.geometry("940x760")
        self.root.minsize(760, 560)
        self._apply_sakura_theme()
        self.image = None
        self.preview = None
        self.result = None
        self._recognition_generation = 0
        self._recognizing = False
        self._translating = False
        self._closing = False
        self.phrase = []
        self.current_phrase_range = None
        self.draw_strokes = []
        self.draw_active_stroke = None
        self.draw_ink = "#2f4f9a"
        self.mobile_server_process = None
        self.speech = queue.Queue()
        self.ui_tasks = queue.Queue()

        shell = ttk.Frame(root, style="App.TFrame")
        shell.pack(fill="both", expand=True)
        self.scroll_canvas = tk.Canvas(shell, background=self.colors["bg"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(shell, orient="vertical", command=self.scroll_canvas.yview)
        self.scroll_canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scroll_canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        outer = ttk.Frame(self.scroll_canvas, style="App.TFrame", padding=22)
        self.scroll_window = self.scroll_canvas.create_window((0, 0), window=outer, anchor="nw")
        outer.bind("<Configure>", self._update_scroll_region)
        self.scroll_canvas.bind("<Configure>", self._resize_scroll_content)
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", lambda _event: self._scroll_units(-3))
        self.root.bind_all("<Button-5>", lambda _event: self._scroll_units(3))
        self.root.bind_all("<Prior>", lambda _event: self.scroll_canvas.yview_scroll(-1, "page"))
        self.root.bind_all("<Next>", lambda _event: self.scroll_canvas.yview_scroll(1, "page"))
        header = ttk.Frame(outer, style="App.TFrame")
        header.pack(fill="x", pady=(0, 16))
        ttk.Label(header, text="✿  Sakura Kana", style="Hero.TLabel").pack(anchor="w")
        ttk.Label(header, text="Read Japanese, build a phrase, and hear what it means.", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))

        actions = ttk.Frame(outer, style="Card.TFrame", padding=(14, 11))
        actions.pack(fill="x", pady=(0, 16))
        self.choose_button = ttk.Button(actions, text="Choose a photo", style="Primary.TButton", command=self.choose_image)
        self.choose_button.pack(side="left")
        self.camera_button = ttk.Button(actions, text="Open camera", style="Soft.TButton", command=self.open_webcam)
        self.camera_button.pack(side="left", padx=(9, 16))
        ttk.Label(actions, text="Camo camera", style="CardMuted.TLabel").pack(side="left", padx=(0, 7))
        self.camera_index = tk.StringVar(value="0")
        ttk.Entry(actions, textvariable=self.camera_index, width=4, justify="center").pack(side="left")
        self.phone_button = ttk.Button(actions, text="Start phone server", style="Soft.TButton", command=self.toggle_mobile_server)
        self.phone_button.pack(side="left", padx=(14, 0))

        body = ttk.Frame(outer, style="App.TFrame")
        body.pack(fill="both", expand=True)
        preview_card = ttk.Frame(body, style="Card.TFrame", padding=15)
        preview_card.pack(side="left", fill="both", expand=True, padx=(0, 15))
        ttk.Label(preview_card, text="Your handwriting", style="Section.TLabel").pack(anchor="w", pady=(0, 10))
        self.preview_label = ttk.Label(preview_card, text="Choose a photo to begin\n\nA clear, well-lit line works best.", anchor="center", style="Preview.TLabel")
        self.preview_label.pack(fill="both", expand=True)
        ttk.Label(preview_card, text="Or draw one hiragana", style="Section.TLabel").pack(anchor="w", pady=(12, 5))
        self.draw_canvas = tk.Canvas(preview_card, height=170, background="white", highlightthickness=1,
                                     highlightbackground=self.colors["border"], cursor="crosshair")
        self.draw_canvas.pack(fill="x", expand=False)
        self.draw_canvas.bind("<ButtonPress-1>", self._draw_start)
        self.draw_canvas.bind("<B1-Motion>", self._draw_move)
        self.draw_canvas.bind("<ButtonRelease-1>", self._draw_end)
        draw_actions = ttk.Frame(preview_card, style="Card.TFrame")
        draw_actions.pack(fill="x", pady=(7, 0))
        ttk.Button(draw_actions, text="Clear drawing", style="Soft.TButton", command=self.clear_drawing).pack(side="left")
        self.draw_color_button = ttk.Button(draw_actions, text="Use black ink", style="Soft.TButton", command=self.toggle_draw_color)
        self.draw_color_button.pack(side="left", padx=6)
        self.draw_recognize_button = ttk.Button(draw_actions, text="Read drawing", style="Primary.TButton", command=self.recognize_drawing)
        self.draw_recognize_button.pack(side="left")
        right = ttk.Frame(body, style="App.TFrame")
        right.pack(side="left", fill="both", expand=True)
        read_card = ttk.Frame(right, style="Card.TFrame", padding=15)
        read_card.pack(fill="x", pady=(0, 12))
        ttk.Label(read_card, text="1  ·  Read the kana", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        self.recognition = tk.StringVar(value="No image selected")
        ttk.Label(read_card, textvariable=self.recognition, style="CardBody.TLabel", justify="left", wraplength=380).pack(anchor="w", pady=(0, 12))
        ttk.Label(read_card, text="Japanese · tap to correct", style="CardMuted.TLabel").pack(anchor="w")
        self.kana_line = tk.StringVar()
        ttk.Entry(read_card, textvariable=self.kana_line, width=30, font=("Yu Gothic UI", 18)).pack(fill="x", pady=(4, 9))
        line_actions = ttk.Frame(read_card, style="Card.TFrame")
        line_actions.pack(anchor="w")
        self.translate_line_button = ttk.Button(line_actions, text="Translate this line  →", style="Primary.TButton", command=self.translate_line)
        self.translate_line_button.pack(side="left")
        self.add_button = ttk.Button(line_actions, text="Add to phrase", style="Soft.TButton", command=self.add_current)
        self.add_button.pack(side="left", padx=(8, 0))

        phrase_card = ttk.Frame(right, style="Card.TFrame", padding=15)
        phrase_card.pack(fill="both", expand=True)
        ttk.Label(phrase_card, text="2  ·  Make it a phrase", style="Section.TLabel").pack(anchor="w")
        ttk.Label(phrase_card, text="Translation type", style="CardMuted.TLabel").pack(anchor="w", pady=(7, 0))
        self.translation_type = tk.StringVar(value="Phrase builder")
        ttk.Combobox(phrase_card, textvariable=self.translation_type, values=("Word from reading", "Phrase builder", "Sentence from reading", "Recognized line"), state="readonly").pack(fill="x", pady=(3, 8))
        self.phrase_text = tk.StringVar(value="(empty)")
        ttk.Label(phrase_card, text="Japanese phrase", style="CardMuted.TLabel").pack(anchor="w", pady=(8, 0))
        ttk.Label(phrase_card, textvariable=self.phrase_text, style="Japanese.TLabel", wraplength=380).pack(anchor="w", pady=(1, 8))
        phrase_actions = ttk.Frame(phrase_card, style="Card.TFrame")
        phrase_actions.pack(anchor="w", pady=(0, 10))
        self.translate_button = ttk.Button(phrase_actions, text="Translate selection", style="Primary.TButton", command=self.translate_selected)
        self.translate_button.pack(side="left")
        self.undo_button = ttk.Button(phrase_actions, text="Undo", style="Soft.TButton", command=self.undo)
        self.undo_button.pack(side="left", padx=6)
        self.clear_button = ttk.Button(phrase_actions, text="Clear", style="Soft.TButton", command=self.clear)
        self.clear_button.pack(side="left")
        ttk.Separator(phrase_card).pack(fill="x", pady=(0, 10))
        ttk.Label(phrase_card, text="English meaning", style="CardMuted.TLabel").pack(anchor="w")
        self.english = tk.StringVar(value="English translation will appear here.")
        ttk.Label(phrase_card, textvariable=self.english, style="English.TLabel", wraplength=380).pack(anchor="w", pady=(3, 8))
        self.speak_button = ttk.Button(phrase_card, text="▶  Speak English", style="Soft.TButton", command=self.speak_english)
        self.speak_button.pack(anchor="w")

        vocab_card = ttk.Frame(right, style="Card.TFrame", padding=15)
        vocab_card.pack(fill="x", pady=(12, 0))
        ttk.Label(vocab_card, text="3  ·  Learn vocabulary by level", style="Section.TLabel").pack(anchor="w")
        ttk.Label(vocab_card, text="Starter cards from N5 beginner through N1 advanced · session count", style="CardMuted.TLabel").pack(anchor="w", pady=(3, 8))
        self.vocab_decks = self._load_vocabulary()
        self.vocab_level = tk.StringVar(value="N5")
        ttk.Combobox(vocab_card, textvariable=self.vocab_level, values=("N5", "N4", "N3", "N2", "N1"), state="readonly", width=8).pack(anchor="w")
        self.vocab_level.trace_add("write", lambda *_: self._show_vocabulary())
        self.vocab_word = tk.StringVar()
        self.vocab_reading = tk.StringVar()
        self.vocab_meaning = tk.StringVar(value="Press Show meaning when you are ready.")
        ttk.Label(vocab_card, textvariable=self.vocab_word, style="Japanese.TLabel").pack(anchor="center", pady=(8, 0))
        ttk.Label(vocab_card, textvariable=self.vocab_reading, style="CardMuted.TLabel").pack(anchor="center")
        self.vocab_progress = tk.StringVar()
        ttk.Label(vocab_card, textvariable=self.vocab_progress, style="CardMuted.TLabel").pack(anchor="w", pady=(5, 0))
        ttk.Label(vocab_card, textvariable=self.vocab_meaning, style="English.TLabel", wraplength=380).pack(anchor="w", pady=(4, 6))
        vocab_actions = ttk.Frame(vocab_card, style="Card.TFrame")
        vocab_actions.pack(anchor="w")
        ttk.Button(vocab_actions, text="Show meaning", style="Primary.TButton", command=self._reveal_vocabulary).pack(side="left")
        ttk.Button(vocab_actions, text="I knew it", style="Soft.TButton", command=self._known_vocabulary).pack(side="left", padx=6)
        ttk.Button(vocab_actions, text="Next word", style="Soft.TButton", command=self._next_vocabulary).pack(side="left")
        self.vocab_index = 0
        self.vocab_known = 0
        self._show_vocabulary()

        self.status = tk.StringVar(value="Ready. Images stay on this computer.")
        ttk.Label(outer, textvariable=self.status, style="Status.TLabel", anchor="w", padding=(12, 8)).pack(fill="x", pady=(13, 0))
        self.root.after(40, self._drain_ui_tasks)
        threading.Thread(target=self._speech_worker, daemon=True, name="SakuraKanaSpeech").start()

    def _apply_sakura_theme(self):
        self.colors = {"bg": "#fff7fa", "card": "#ffffff", "ink": "#452a3c", "muted": "#806879",
                       "pink": "#d95f8d", "pink_hover": "#bd4774", "soft": "#ffe7ef", "border": "#f0d5e0",
                       "preview": "#fffafd", "status": "#ffedf3"}
        self.root.configure(background=self.colors["bg"])
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("App.TFrame", background=self.colors["bg"])
        style.configure("Card.TFrame", background=self.colors["card"], bordercolor=self.colors["border"], relief="flat")
        style.configure("TLabel", background=self.colors["bg"], foreground=self.colors["ink"], font=("Segoe UI", 10))
        style.configure("Card.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Segoe UI", 10))
        style.configure("Hero.TLabel", background=self.colors["bg"], foreground=self.colors["ink"], font=("Segoe UI", 25, "bold"))
        style.configure("Subtitle.TLabel", background=self.colors["bg"], foreground=self.colors["muted"], font=("Segoe UI", 11))
        style.configure("Section.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Segoe UI", 13, "bold"))
        style.configure("CardBody.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Segoe UI", 10))
        style.configure("CardMuted.TLabel", background=self.colors["card"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("Preview.TLabel", background=self.colors["preview"], foreground=self.colors["muted"], font=("Segoe UI", 11), padding=12)
        style.configure("Japanese.TLabel", background=self.colors["card"], foreground=self.colors["ink"], font=("Yu Gothic UI", 20))
        style.configure("English.TLabel", background=self.colors["card"], foreground=self.colors["pink_hover"], font=("Segoe UI", 17, "bold"))
        style.configure("Status.TLabel", background=self.colors["status"], foreground=self.colors["muted"], font=("Segoe UI", 9))
        style.configure("TEntry", fieldbackground=self.colors["preview"], foreground=self.colors["ink"], bordercolor=self.colors["border"], padding=7)
        style.configure("Primary.TButton", background=self.colors["pink"], foreground="#ffffff", font=("Segoe UI", 10, "bold"), padding=(13, 8), borderwidth=0)
        style.map("Primary.TButton", background=[("active", self.colors["pink_hover"]), ("pressed", self.colors["pink_hover"])])
        style.configure("Soft.TButton", background=self.colors["soft"], foreground=self.colors["pink_hover"], font=("Segoe UI", 9, "bold"), padding=(11, 7), borderwidth=0)
        style.map("Soft.TButton", background=[("active", self.colors["border"]), ("pressed", self.colors["border"])])

    def choose_image(self):
        filename = filedialog.askopenfilename(
            title="Choose a handwritten kana image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.webp"), ("All files", "*.*")],
        )
        if not filename:
            self.status.set("Photo selection cancelled.")
            return
        try:
            self.current_phrase_range = None
            self.add_button.configure(text="Add to phrase")
            with Image.open(filename) as image:
                self.image = image.convert("RGB")
            preview = self.image.copy()
            preview.thumbnail((350, 430))
            self.preview = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self.preview, text="")
            self._recognition_generation += 1
            generation = self._recognition_generation
            self._recognizing = True
            self.result = None
            self.kana_line.set("")
            self.recognition.set("Reading your handwriting…")
            self.status.set("Reading kana in the background. You can keep using the app.")
            self.choose_button.configure(state="disabled")
            self.draw_recognize_button.configure(state="disabled")
            threading.Thread(target=self._recognize_worker, args=(self.image.copy(), generation), daemon=True).start()
        except Exception as exc:
            messagebox.showerror("Could not read image", str(exc))
            self.status.set("Image recognition failed.")

    def _recognize_worker(self, image, generation):
        try:
            result = predict_line(image)
            error = None
        except Exception as exc:
            result, error = None, str(exc)
        self.ui_tasks.put((self._finish_recognition, (generation, result, error)))

    def _drain_ui_tasks(self):
        if self._closing:
            return
        while True:
            try:
                callback, args = self.ui_tasks.get_nowait()
            except queue.Empty:
                break
            callback(*args)
        self.root.after(40, self._drain_ui_tasks)

    def _finish_recognition(self, generation, result, error):
        if self._closing or generation != self._recognition_generation:
            return
        self._recognizing = False
        self.choose_button.configure(state="normal")
        self.draw_recognize_button.configure(state="normal")
        if error:
            self.recognition.set("Could not read this photo. Try a clearer, closer image.")
            self.status.set(f"Image recognition failed: {error}")
            messagebox.showerror("Could not read image", error)
            return
        self.result = result
        self.kana_line.set("".join(item["kana"] for item in result))
        lines = []
        for i, item in enumerate(result, 1):
            picks = ", ".join(f"{kana} {score:.0%}" for _, kana, score in item["alternatives"])
            mark = "  · check this one" if item["confidence"] < 0.70 else ""
            lines.append(f"{i}. {item['kana']}  {item['label'].lower()}  {item['confidence']:.0%}{mark}\n   Other guesses: {picks}")
        self.recognition.set("\n".join(lines) or "No handwriting found. Try a closer, brighter photo.")
        uncertain = any(item["confidence"] < 0.70 for item in result)
        line = self.kana_line.get().strip()
        if line:
            start = len(self.phrase)
            self._append_phrase_text(line)
            self.current_phrase_range = (start, len(self.phrase))
            self.add_button.configure(text="Update phrase")
        if uncertain:
            self.english.set("Review the reading, then translate the phrase when it looks right.")
            self.status.set(f"Found {len(result)} kana on {self._device_name()}. Added the candidate to your phrase; correct it before translating.")
        else:
            self.status.set(f"Found {len(result)} kana on {self._device_name()}. Added the reading to your phrase; check it before translating.")
        if self.kana_line.get().strip() and not uncertain:
            self._translate_text(self.kana_line.get().strip())

    @staticmethod
    def _device_name():
        import torch
        return torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU"

    def add_current(self):
        if self._recognizing:
            self.status.set("Still reading the photo. Please wait a moment, then add the line.")
            return
        text = self.kana_line.get().strip()
        if not text:
            self.status.set("Choose a photo, or type hiragana in the Japanese box first.")
            return
        if self.current_phrase_range and self.current_phrase_range[1] == len(self.phrase):
            start, end = self.current_phrase_range
            del self.phrase[start:end]
            self._append_phrase_text(text)
            self.current_phrase_range = (start, len(self.phrase))
            self.status.set("Updated the recognized line in your phrase.")
        else:
            self._append_phrase_text(text)
            self.current_phrase_range = None
            self.status.set("Added the line to your phrase.")
        self.add_button.configure(text="Update phrase" if self.current_phrase_range else "Add to phrase")
        self.english.set("Press Translate to English when the word or phrase is complete.")

    def _append_phrase_text(self, text):
        reverse = {character: reading for reading, character in KANA.items()}
        for character in text:
            if not character.isspace():
                self.phrase.append((character, reverse.get(character, character)))
        self.phrase_text.set("".join(character for character, _ in self.phrase) or "(empty)")

    def _draw_start(self, event):
        self.draw_active_stroke = [(event.x, event.y)]
        self.draw_strokes.append((self.draw_ink, self.draw_active_stroke))
        radius = 2
        self.draw_canvas.create_oval(event.x-radius, event.y-radius, event.x+radius, event.y+radius,
                                     fill=self.draw_ink, outline=self.draw_ink, tags="ink")

    def _draw_move(self, event):
        if self.draw_active_stroke is None:
            return
        points = self.draw_active_stroke
        previous = points[-1]
        points.append((event.x, event.y))
        self.draw_canvas.create_line(*previous, event.x, event.y, fill=self.draw_ink, width=4,
                                     capstyle=tk.ROUND, joinstyle=tk.ROUND, tags="ink")

    def _draw_end(self, _event):
        self.draw_active_stroke = None

    def clear_drawing(self):
        self.draw_strokes.clear()
        self.draw_active_stroke = None
        self.draw_canvas.delete("ink")
        self.status.set("Drawing cleared.")

    def toggle_draw_color(self):
        self.draw_ink = "#171717" if self.draw_ink != "#171717" else "#2f4f9a"
        self.draw_color_button.configure(text="Use blue ink" if self.draw_ink == "#171717" else "Use black ink")

    def recognize_drawing(self):
        if not self.draw_strokes:
            self.status.set("Draw one hiragana character in the box first.")
            return
        width = max(1, self.draw_canvas.winfo_width())
        height = max(1, self.draw_canvas.winfo_height())
        image = Image.new("RGB", (width, height), "white")
        painter = ImageDraw.Draw(image)
        for color, points in self.draw_strokes:
            ink = tuple(int(color[i:i+2], 16) for i in (1, 3, 5))
            if len(points) == 1:
                x, y = points[0]
                radius = 5
                painter.ellipse((x-radius, y-radius, x+radius, y+radius), fill=ink)
            else:
                painter.line(points, fill=ink, width=8, joint="curve")
                radius = 4
                for x, y in (points[0], points[-1]):
                    painter.ellipse((x-radius, y-radius, x+radius, y+radius), fill=ink)
        self.current_phrase_range = None
        self.add_button.configure(text="Add to phrase")
        self._recognition_generation += 1
        generation = self._recognition_generation
        self._recognizing = True
        self.result = None
        self.recognition.set("Reading your drawing…")
        self.status.set("Cropping the ink and reading your drawing…")
        self.draw_recognize_button.configure(state="disabled")
        threading.Thread(target=self._recognize_worker, args=(image, generation), daemon=True).start()

    def _update_scroll_region(self, _event=None):
        self.root.after_idle(lambda: self.scroll_canvas.configure(scrollregion=self.scroll_canvas.bbox("all")))

    def _resize_scroll_content(self, event):
        self.scroll_canvas.itemconfigure(self.scroll_window, width=event.width)

    def _on_mousewheel(self, event):
        # Windows reports wheel deltas in multiples of 120; normalize them so
        # high-resolution touchpads and a mouse wheel both move a useful amount.
        delta = -max(1, abs(event.delta) // 120) * (1 if event.delta > 0 else -1)
        self._scroll_units(delta * 3)
        return "break"

    def _scroll_units(self, amount):
        self.scroll_canvas.yview_scroll(amount, "units")
        return "break"

    def translate(self):
        text = "".join(character for character, _ in self.phrase)
        if not text:
            self.status.set("Your phrase is empty. Use Translate this line, or add kana to the phrase first.")
            return
        self._translate_text(text)

    def translate_selected(self):
        if self.translation_type.get() == "Phrase builder":
            self.translate()
        else:
            self.translate_line()

    def _load_vocabulary(self):
        try:
            path = ROOT / "src" / "static" / "vocabulary.json"
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {level: [] for level in ("N5", "N4", "N3", "N2", "N1")}

    def _show_vocabulary(self):
        deck = self.vocab_decks.get(self.vocab_level.get(), [])
        if not deck:
            self.vocab_word.set("Vocabulary unavailable")
            self.vocab_reading.set("")
            self.vocab_progress.set("Check that vocabulary.json is installed.")
            return
        self.vocab_index %= len(deck)
        item = deck[self.vocab_index]
        self.vocab_word.set(item["word"])
        self.vocab_reading.set(item["reading"])
        self.vocab_meaning.set("Press Show meaning when you are ready.")
        self.vocab_progress.set(f"{self.vocab_level.get()} · Card {self.vocab_index + 1} of {len(deck)} · Known: {self.vocab_known}")

    def _reveal_vocabulary(self):
        deck = self.vocab_decks.get(self.vocab_level.get(), [])
        if deck:
            self.vocab_meaning.set(deck[self.vocab_index]["meaning"])

    def _next_vocabulary(self):
        self.vocab_index += 1
        self._show_vocabulary()

    def _known_vocabulary(self):
        self.vocab_known += 1
        self._next_vocabulary()

    def translate_line(self):
        text = self.kana_line.get().strip()
        if not text:
            self.status.set("Choose a photo or type Japanese in the line box first.")
            return
        self._translate_text(text)

    def _translate_text(self, text):
        if self._translating:
            self.status.set("Translation is still running. Please wait a moment.")
            return
        if not text:
            self.status.set("Enter some Japanese before translating.")
            return
        self.status.set("Translating locally on the GPU when available…")
        self._translating = True
        self.translate_button.configure(state="disabled")
        self.translate_line_button.configure(state="disabled")
        self.root.update_idletasks()

        def work():
            try:
                from translation import translate_japanese
                result = translate_japanese(text)
            except Exception as exc:
                result = f"Translation could not run: {exc}"
            self.ui_tasks.put((self._show_translation, (result,)))

        threading.Thread(target=work, daemon=True).start()

    def _show_translation(self, result):
        self._translating = False
        self.translate_button.configure(state="normal")
        self.translate_line_button.configure(state="normal")
        self.english.set(result)
        self.status.set("Translation ready. Use Speak English to hear it." if not result.startswith("Translation could not") else result)

    def speak_english(self):
        text = self.english.get()
        if text and not text.startswith(("English translation", "Press Translate", "Translation could not")):
            self.speech.put(text)
            self.status.set("Speaking the English translation…")
        else:
            self.status.set("Translate a Japanese phrase before using Speak English.")

    def _speech_worker(self):
        pythoncom = None
        engine = None
        try:
            import pythoncom as win32com
            pythoncom = win32com
            # SAPI5 is a COM server. Every worker thread that uses it needs its
            # own COM apartment; pyttsx3 does not initialize this thread.
            pythoncom.CoInitialize()
            import pyttsx3
            engine = pyttsx3.init("sapi5")
            engine.setProperty("rate", 165)
            self._post_status("English voice is ready.")
            while True:
                text = self.speech.get()
                if text is None:
                    break
                engine.say(text)
                engine.runAndWait()
                self._post_status("Speech finished.")
        except Exception as exc:
            message = f"Speech output unavailable: {exc}"
            self._post_status(message)
        finally:
            if engine is not None:
                try:
                    engine.stop()
                except Exception:
                    pass
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _post_status(self, message):
        self.ui_tasks.put((self.status.set, (message,)))

    def undo(self):
        self.current_phrase_range = None
        self.add_button.configure(text="Add to phrase")
        if self.phrase:
            self.phrase.pop()
            self.status.set("Removed the last kana.")
        else:
            self.status.set("There is no kana to undo yet.")
        self.phrase_text.set("".join(character for character, _ in self.phrase) or "(empty)")
        self.english.set("English translation will appear here.")

    def clear(self):
        self.phrase.clear()
        self.current_phrase_range = None
        self.add_button.configure(text="Add to phrase")
        self.phrase_text.set("(empty)")
        self.english.set("English translation will appear here.")
        self.kana_line.set("")
        self.status.set("Phrase cleared. Choose a photo or type a new line.")

    def open_webcam(self):
        try:
            index = int(self.camera_index.get())
            script = Path(__file__).with_name("desktop_app.py")
            if getattr(sys, "frozen", False):
                command = [sys.executable, "--webcam", "--camera", str(index)]
            else:
                command = [sys.executable, str(script), "--webcam", "--camera", str(index)]
            cwd = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
            process = subprocess.Popen(command, cwd=cwd)
            self.status.set(f"Starting camera {index}…")
            self.root.after(1800, lambda: self._check_camera_start(process, index))
        except ValueError:
            messagebox.showerror("Camera index", "Enter a numeric camera index, such as 0 or 1.")
            self.status.set("Camera index must be a number, such as 0 or 1.")
        except Exception as exc:
            messagebox.showerror("Could not open webcam", str(exc))
            self.status.set(f"Could not start the camera: {exc}")

    def _phone_url(self):
        address = "127.0.0.1"
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                probe.connect(("192.0.2.1", 9))
                address = probe.getsockname()[0]
        except OSError:
            pass
        return f"http://{address}:5055"

    def toggle_mobile_server(self):
        process = self.mobile_server_process
        if process is not None and process.poll() is None:
            process.terminate()
            self.mobile_server_process = None
            self.phone_button.configure(text="Start phone server")
            self.status.set("Phone server stopped.")
            return
        url = self._phone_url()
        try:
            # A manually started server may already be available; reuse it.
            with urllib.request.urlopen("http://127.0.0.1:5055/", timeout=1):
                self.status.set(f"Phone server is already running. On your phone open {url}")
                messagebox.showinfo("Sakura Kana on Android", f"Connect the phone to the same Wi-Fi and open:\n\n{url}\n\nKeep this app open while testing.")
                return
        except Exception:
            pass

        try:
            project_root = (Path(sys.executable).resolve().parents[2]
                            if getattr(sys, "frozen", False)
                            else Path(__file__).resolve().parents[1])
            script = project_root / "src" / "mobile_server.py"
            pythonw = project_root / ".venv" / "Scripts" / "pythonw.exe"
            python = project_root / ".venv" / "Scripts" / "python.exe"
            interpreter = pythonw if pythonw.exists() else python
            if not script.exists() or not interpreter.exists():
                raise FileNotFoundError("The app could not find src/mobile_server.py or the project .venv. Run Sakura Kana from its project folder.")
            kwargs = {"cwd": str(project_root), "stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.mobile_server_process = subprocess.Popen([str(interpreter), str(script)], **kwargs)
            self.phone_button.configure(text="Stop phone server")
            self.status.set(f"Starting phone server at {url}…")
            self.root.after(900, lambda: self._show_phone_server(url))
        except Exception as exc:
            messagebox.showerror("Could not start phone server", str(exc))
            self.status.set(f"Could not start phone server: {exc}")

    def _show_phone_server(self, url):
        process = self.mobile_server_process
        if process is None or process.poll() is not None:
            self.phone_button.configure(text="Start phone server")
            self.status.set("Phone server stopped unexpectedly. Check Flask is installed in .venv.")
            return
        self.status.set(f"Phone server running. On Android open {url}")
        messagebox.showinfo("Sakura Kana on Android", f"Connect the phone to the same Wi-Fi and open:\n\n{url}\n\nKeep this app open while testing.")

    def _check_camera_start(self, process, index):
        if self._closing:
            return
        if process.poll() is None:
            self.status.set("Camera window opened. Use Q or Esc in that window to close it.")
        else:
            message = f"Camera {index} did not start. Check the Camo camera index and close other apps using the camera."
            self.status.set(message)
            messagebox.showerror("Camera could not start", message)

    def close(self):
        self._closing = True
        self.speech.put(None)
        self.root.destroy()


def main():
    root = tk.Tk()
    app = KanaReaderApp(root)
    root.protocol("WM_DELETE_WINDOW", app.close)
    root.mainloop()


if __name__ == "__main__":
    main()
