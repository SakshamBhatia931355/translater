from pathlib import Path
import re
import numpy as np
import torch
from PIL import Image, ImageOps
from torch.utils.data import Dataset
from config import IMAGE_DIR, ETL8G_PREPARED_DIR, IMG_SIZE, MEAN, STD

def parse_label(path):
    m = re.match(r"kana([A-Z]+)(?:\d+|_).*\.(?:jpg|jpeg|png)$", Path(path).name, re.I)
    if not m: raise ValueError(f"Unrecognized kana filename: {path}")
    return m.group(1).upper()

def image_to_tensor(image, augment=False):
    image = ImageOps.grayscale(image)
    # The reference set is mostly white ink on a dark background. Convert
    # ordinary dark ink on white paper to that same polarity before scaling.
    if np.asarray(image, dtype=np.float32).mean() > 127.0:
        image = ImageOps.invert(image)
    if augment:
        # Small affine changes and stroke-thickness variation, preserving identity.
        from PIL import ImageEnhance
        angle = float(np.random.uniform(-12, 12))
        image = image.rotate(angle, resample=Image.Resampling.BILINEAR, fillcolor=255)
        image = ImageEnhance.Contrast(image).enhance(float(np.random.uniform(.8, 1.25)))
    image = ImageOps.pad(image, (IMG_SIZE, IMG_SIZE), color=255)
    arr = np.asarray(image, dtype=np.float32) / 255.0
    # Source is black ink on white paper: invert so ink has positive signal.
    arr = (1.0 - arr - MEAN) / STD
    return torch.from_numpy(arr.copy()).unsqueeze(0)

class HiraganaDataset(Dataset):
    def __init__(self, rows=None, training=False, image_dir=IMAGE_DIR, classes=None):
        self.image_dir = Path(image_dir)
        if rows is None:
            rows = ([(p.name, parse_label(p)) for p in sorted(self.image_dir.iterdir())
                     if p.suffix.lower() in {".jpg", ".jpeg", ".png"}]
                    if self.image_dir.is_dir() else [])
            # Add the filtered ETL8G handwriting samples when the user has run
            # prepare_etl8g.py. Absolute paths keep the official archive outside
            # the source dataset folder and avoid copying its large binary files.
            if ETL8G_PREPARED_DIR.is_dir():
                rows.extend((str(p), parse_label(p)) for p in sorted(ETL8G_PREPARED_DIR.glob("kana*"))
                            if p.suffix.lower() == ".png")
        self.rows = [(str(name), str(label)) for name, label in rows]
        self.classes = list(classes or sorted({label for _, label in self.rows}))
        self.class_to_idx = {label:i for i,label in enumerate(self.classes)}
        self.training = training
    def __len__(self): return len(self.rows)
    def __getitem__(self, idx):
        name, label = self.rows[idx]
        image_path = Path(name)
        if not image_path.is_absolute():
            image_path = self.image_dir / image_path
        with Image.open(image_path) as im:
            x = image_to_tensor(im, self.training)
        return x, self.class_to_idx[label]
