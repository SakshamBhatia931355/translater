"""Live one-character kana recognizer with read-aloud and phrase translation.

Aim one handwritten hiragana at a time inside the guide box. Press Space to add
the steady prediction to the text line. Press T to translate that line to
English (requires the optional offline Japanese-English Argos model).
"""
import argparse
import queue
import threading
import time
from collections import Counter, deque

import cv2
import torch
from PIL import Image

from config import IMG_SIZE, KANA, MIN_CONFIDENCE
from dataset import image_to_tensor
from predict import load_model


def start_speaker():
    requests = queue.Queue()

    def worker():
        try:
            import pyttsx3
            engine = pyttsx3.init("sapi5")
            engine.setProperty("rate", 155)
            while True:
                phrase = requests.get()
                if phrase is None:
                    break
                engine.say(phrase)
                engine.runAndWait()
        except Exception as exc:
            print(f"Speech output unavailable: {exc}")

    threading.Thread(target=worker, daemon=True).start()
    return requests.put


def crop_character(roi):
    """Crop the ink inside the guide box while resisting colored Camo shadows."""
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY) if roi.ndim == 3 else roi
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV) if roi.ndim == 3 else None
    if hsv is not None:
        sat, val = hsv[:, :, 1], hsv[:, :, 2]
        mask = cv2.inRange(sat, 55, 255) & cv2.inRange(val, 0, 250)
    else:
        mask = None
    if mask is None or cv2.countNonZero(mask) < 12:
        _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    )
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    height, width = gray.shape
    parts = []
    for index in range(1, count):
        x, y, box_width, box_height, area = stats[index]
        if 3 <= area < height * width * 0.10:
            parts.append((int(x), int(y), int(x + box_width), int(y + box_height)))
    if not parts:
        return gray
    x0 = min(part[0] for part in parts)
    y0 = min(part[1] for part in parts)
    x1 = max(part[2] for part in parts)
    y1 = max(part[3] for part in parts)
    margin = max(6, int(max(x1 - x0, y1 - y0) * 0.12))
    x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
    x1, y1 = min(width, x1 + margin), min(height, y1 + margin)
    if (x1 - x0) * (y1 - y0) > height * width * 0.35:
        return gray
    return gray[y0:y1, x0:x1]


def translate_line(text):
    """Translate Japanese text with the installed local PyTorch ja→en model."""
    if not text:
        return "Add characters with Space before translating."
    try:
        from translation import translate_japanese
    except ImportError:
        return "Translation setup missing. Run: python src/setup_translation.py"
    try:
        result = translate_japanese(text)
    except Exception as exc:
        return f"Offline Japanese-to-English model is not ready: {exc}"
    return result or "No English translation returned."


def main():
    parser = argparse.ArgumentParser(description="Live handwritten hiragana reader")
    parser.add_argument("--camera", type=int, default=0, help="camera device index (Camo may be 1 or 2)")
    parser.add_argument("--checkpoint", default=None)
    parser.add_argument("--mirror", action="store_true")
    parser.add_argument("--no-speech", action="store_true")
    args = parser.parse_args()

    model, classes = load_model(args.checkpoint)
    device = next(model.parameters()).device
    print(f"Inference device: {device}")
    print("Space: add the stable kana | T: English translation | Backspace: undo | C: clear | Q: quit")
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        raise SystemExit(f"Could not open camera {args.camera}. Try --camera 1 or close apps using the camera.")

    speak = start_speaker() if not args.no_speech else (lambda _text: None)
    frame_votes = deque(maxlen=7)
    phrase = []
    result = "Center one handwritten hiragana in the guide box"
    translation = ""
    stable_candidate = None
    candidate_since = 0.0
    spoken_label = None
    current = None
    current_top = []
    frozen_frame = None
    title = "Kana Reader — q: quit | space: add | t: translate"
    try:
        while True:
            if frozen_frame is None:
                ok, frame = cap.read()
                if not ok:
                    break
                if args.mirror:
                    frame = cv2.flip(frame, 1)
            else:
                frame = frozen_frame.copy()
            height, width = frame.shape[:2]
            side = min(height, width, 360)
            x0, y0 = (width - side) // 2, (height - side) // 2
            x1, y1 = x0 + side, y0 + side
            cv2.rectangle(frame, (x0, y0), (x1, y1), (30, 220, 80), 2)

            if frozen_frame is None:
                gray = crop_character(frame[y0:y1, x0:x1])
                crop = cv2.resize(gray, (IMG_SIZE, IMG_SIZE), interpolation=cv2.INTER_AREA)
                tensor = image_to_tensor(Image.fromarray(crop))
                with torch.inference_mode():
                    probs = model(tensor.unsqueeze(0).to(device)).softmax(1)[0].cpu()
                idx = int(probs.argmax())
                top_ids = probs.topk(min(3, len(classes))).indices.tolist()
                current_top = [(classes[i], float(probs[i])) for i in top_ids]
                frame_votes.append((classes[idx], float(probs[idx])))
                votes = Counter(label for label, _ in frame_votes)
                top_label, count = votes.most_common(1)[0]
                top_conf = sum(conf for label, conf in frame_votes if label == top_label) / count
                if count >= 4 and top_conf >= MIN_CONFIDENCE:
                    current = (top_label, top_conf)
                    result = f"Kana reading: {top_label.lower()}    Confidence: {top_conf:.0%}"
                    if top_label != stable_candidate:
                        stable_candidate = top_label
                        candidate_since = time.monotonic()
                    elif (not args.no_speech and time.monotonic() - candidate_since >= 1.0
                          and top_label != spoken_label and top_conf >= 0.70):
                        speak(top_label.lower())
                        spoken_label = top_label
                else:
                    current = None
                    result = f"Hold still — best guess {classes[idx].lower()} ({float(probs[idx]):.0%})"
                    stable_candidate = None
                    spoken_label = None

            cv2.putText(frame, result[:100], (18, 32), cv2.FONT_HERSHEY_SIMPLEX,
                        0.62, (20, 20, 230), 2, cv2.LINE_AA)
            choices = "  ".join(f"{i + 1}:{label.lower()} {conf:.0%}"
                                 for i, (label, conf) in enumerate(current_top))
            if choices:
                cv2.putText(frame, choices, (18, 90), cv2.FONT_HERSHEY_SIMPLEX,
                            0.53, (80, 255, 180), 1, cv2.LINE_AA)
            romaji = " ".join(label.lower() for _, label in phrase)
            cv2.putText(frame, f"Text: {romaji[-80:] or '(press Space to add a kana)'}",
                        (18, 62), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA)
            if translation:
                cv2.putText(frame, f"English: {translation[:86]}", (18, 118),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.52, (50, 240, 240), 1, cv2.LINE_AA)
            cv2.putText(frame, "Dark ink on light paper | T translates the captured kana line",
                        (18, height - 18), cv2.FONT_HERSHEY_SIMPLEX, 0.48,
                        (255, 255, 255), 1, cv2.LINE_AA)
            cv2.imshow(title, frame)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key in (ord(" "), ord("1"), ord("2"), ord("3")) and current_top:
                choice = 0 if key == ord(" ") else int(chr(key)) - 1
                if choice >= len(current_top):
                    continue
                label, confidence = current_top[choice]
                character = KANA.get(label)
                if character:
                    phrase.append((character, label))
                    translation = ""
                    print(f"Added {character.encode('unicode_escape').decode('ascii')} ({label.lower()}, {confidence:.0%})")
            elif key in (8, 127):
                if phrase:
                    phrase.pop()
                    translation = ""
            elif key in (ord("c"), ord("C")):
                phrase.clear()
                translation = ""
            elif key in (ord("t"), ord("T")):
                translation = translate_line("".join(character for character, _ in phrase))
                print(f"English translation: {translation}")
                if not args.no_speech and translation and not translation.startswith(("Translation setup", "Offline", "Add ")):
                    speak(translation)
            elif key == ord("r"):
                frozen_frame = None if frozen_frame is not None else frame.copy()
    finally:
        if not args.no_speech:
            speak(None)
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
