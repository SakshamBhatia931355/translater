"""Local Japanese-to-English translation using Helsinki-NLP OPUS-MT."""
from functools import lru_cache
from pathlib import Path

import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from config import ROOT

MODEL_ID = "Helsinki-NLP/opus-mt-ja-en"
MODEL_DIR = ROOT / "models" / "opus-mt-ja-en"
DEVICE = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


@lru_cache(maxsize=1)
def _load():
    if not (MODEL_DIR / "config.json").exists():
        raise FileNotFoundError(
            f"Translation model is missing at {MODEL_DIR}. Run python src/setup_translation.py first."
        )
    tokenizer = AutoTokenizer.from_pretrained(MODEL_DIR, local_files_only=True)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_DIR, local_files_only=True)
    model.to(DEVICE).eval()
    return tokenizer, model


def translate_japanese(text: str) -> str:
    text = " ".join(text.split())
    if not text:
        return ""
    tokenizer, model = _load()
    inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=256)
    inputs = {name: tensor.to(DEVICE) for name, tensor in inputs.items()}
    with torch.inference_mode():
        generated = model.generate(**inputs, num_beams=4, max_new_tokens=128)
    return tokenizer.decode(generated[0], skip_special_tokens=True).strip()
