"""Shared settings used by training and inference."""
from pathlib import Path
import sys

# PyInstaller's bundled data lives beside the executable in one-folder builds
# and under its extraction directory in one-file builds.
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[1]
IMAGE_DIR = ROOT / "data" / "raw" / "hiragana-dataset" / "hiragana_images"
ETL8G_PREPARED_DIR = ROOT / "datasets" / "ETL8G" / "prepared"
SPLITS_DIR = ROOT / "data" / "splits"
CHECKPOINT_DIR = ROOT / "checkpoints"
OUTPUT_DIR = ROOT / "outputs"
OOD_DIR = ROOT / "data" / "ood_samples"
IMG_SIZE = 64
MEAN = 0.5
STD = 0.5
SEED = 42
FOLDS = 5
EPOCHS = 30
BATCH_SIZE = 64
LEARNING_RATE = 1e-3
MIN_CONFIDENCE = 0.45

# Kana readings in the source filenames; map standard syllables to written hiragana.
KANA = {
    "A":"あ", "I":"い", "U":"う", "E":"え", "O":"お",
    "KA":"か", "KI":"き", "KU":"く", "KE":"け", "KO":"こ",
    "SA":"さ", "SHI":"し", "SU":"す", "SE":"せ", "SO":"そ",
    "TA":"た", "CHI":"ち", "TSU":"つ", "TE":"て", "TO":"と",
    "NA":"な", "NI":"に", "NU":"ぬ", "NE":"ね", "NO":"の",
    "HA":"は", "HI":"ひ", "FU":"ふ", "HE":"へ", "HO":"ほ",
    "MA":"ま", "MI":"み", "MU":"む", "ME":"め", "MO":"も",
    "YA":"や", "YU":"ゆ", "YO":"よ", "RA":"ら", "RI":"り",
    "RU":"る", "RE":"れ", "RO":"ろ", "WA":"わ", "WO":"を", "N":"ん",
    "GA":"が", "GI":"ぎ", "GU":"ぐ", "GE":"げ", "GO":"ご",
    "JI":"じ", "ZU":"ず", "DA":"だ", "DE":"で", "DO":"ど",
    "BA":"ば", "BI":"び", "BU":"ぶ", "BE":"べ", "BO":"ぼ",
    "PA":"ぱ", "PI":"ぴ", "PU":"ぷ", "PE":"ぺ", "PO":"ぽ",
}
