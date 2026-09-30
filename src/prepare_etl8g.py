"""Prepare the local AIST ETL8G archive as extra training images for this kana model.

The conversion keeps only ETL8G records whose JIS character and typical reading
both match one of the 50 kana labels supported by this project. The raw archive
is not copied or redistributed by this script.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import re
import zipfile
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from config import KANA, ROOT

ARCHIVE = ROOT / "datasets" / "ETL8G" / "ETL8G.zip"
OUTPUT = ROOT / "datasets" / "ETL8G" / "prepared"
RECORD_SIZE = 8199
IMAGE_START = 64
IMAGE_BYTES = 8128


def decode_jis(code: bytes) -> str:
    """Decode a two-byte JIS X 0208 code as used in a G-type ETL record."""
    if len(code) != 2:
        return ""
    try:
        return (b"\x1b$B" + code + b"\x1b(B").decode("iso2022_jp")
    except UnicodeDecodeError:
        return ""


def unpack_image(record: bytes) -> Image.Image:
    packed = np.frombuffer(record[IMAGE_START:IMAGE_START + IMAGE_BYTES], dtype=np.uint8)
    pixels = np.empty(packed.size * 2, dtype=np.uint8)
    pixels[0::2] = packed >> 4
    pixels[1::2] = packed & 0x0F
    return Image.fromarray((pixels.reshape(127, 128) * 17), mode="L")


def iter_records(payload: bytes):
    usable = len(payload) - len(payload) % RECORD_SIZE
    if usable != len(payload):
        raise ValueError(f"ETL8G file size {len(payload)} is not divisible by {RECORD_SIZE}")
    for offset in range(0, usable, RECORD_SIZE):
        yield payload[offset:offset + RECORD_SIZE]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=ARCHIVE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--limit-per-class", type=int, default=0,
                        help="optional cap for quick experiments; 0 uses every matching record")
    args = parser.parse_args()
    if not args.archive.is_file():
        raise SystemExit(f"ETL8G archive not found: {args.archive}\nDownload it from the official ETL Character Database site first.")
    digest = hashlib.md5()
    with args.archive.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != "360a5ea345de6eefe4296b958b4db256":
        raise SystemExit(f"ETL8G archive MD5 mismatch: {digest.hexdigest()}")

    args.output.mkdir(parents=True, exist_ok=True)
    seen: Counter[str] = Counter()
    rows = []
    with zipfile.ZipFile(args.archive) as archive:
        entries = [name for name in archive.namelist()
                   if not name.endswith("/") and re.search(r"etl8g_\d{2}$", name, re.I)]
        if not entries:
            raise SystemExit("No ETL8G record files were found inside the archive.")
        for name in entries:
            payload = archive.read(name)
            for record_index, record in enumerate(iter_records(payload)):
                char = decode_jis(record[2:4])
                # ETL8G's typical-reading field uses forms such as A.HIRA.
                # Keep the syllable and verify it against the JIS character so
                # kanji with the same pronunciation are not mislabeled as kana.
                reading = record[4:12].decode("ascii", errors="ignore").strip().upper().split(".", 1)[0]
                if reading not in KANA or char != KANA[reading]:
                    continue
                if args.limit_per_class and seen[reading] >= args.limit_per_class:
                    continue
                seen[reading] += 1
                image_name = f"kana{reading}_etl8g_{seen[reading]:05d}.png"
                output_path = args.output / image_name
                unpack_image(record).save(output_path, optimize=True)
                rows.append((image_name, reading, char, name, record_index))
    with (args.output / "labels.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(("filename", "reading", "character", "source_file", "record_index"))
        writer.writerows(rows)
    summary = ", ".join(f"{label}: {seen[label]}" for label in sorted(seen))
    print(f"Prepared {len(rows):,} hiragana images in {args.output}")
    print(summary)
    if not rows:
        raise SystemExit("No kana records matched. Check that this archive contains the official ETL8G files.")


if __name__ == "__main__":
    main()
