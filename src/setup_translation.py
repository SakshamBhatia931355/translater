"""Download Helsinki-NLP Japanese-to-English weights for local PyTorch use."""
from pathlib import Path

from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

from config import ROOT

MODEL_ID = "Helsinki-NLP/opus-mt-ja-en"
MODEL_DIR = ROOT / "models" / "opus-mt-ja-en"


def main() -> None:
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {MODEL_ID} to {MODEL_DIR} (one-time setup)...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_ID)
    tokenizer.save_pretrained(MODEL_DIR)
    model.save_pretrained(MODEL_DIR, safe_serialization=True)
    print("Offline Japanese-to-English model is ready.")
    print("It runs on CUDA when PyTorch detects a compatible NVIDIA GPU.")


if __name__ == "__main__":
    main()
