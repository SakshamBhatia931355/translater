from pathlib import Path
from functools import lru_cache
import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
from config import CHECKPOINT_DIR, KANA
from dataset import image_to_tensor
from model import SmallCNN

DEVICE = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')

@lru_cache(maxsize=1)
def load_model(checkpoint=None):
    checkpoint=Path(checkpoint or CHECKPOINT_DIR/'best_model.pt')
    if not checkpoint.exists(): raise FileNotFoundError(f"Model checkpoint not found: {checkpoint}. Run `python src/train.py` first.")
    data=torch.load(checkpoint,map_location='cpu',weights_only=False)
    model=SmallCNN(len(data['classes'])); model.load_state_dict(data['state_dict']); model.to(DEVICE); model.eval()
    return model,data['classes']

def predict(image, model=None, classes=None):
    if model is None: model,classes=load_model()
    if isinstance(image,(str,Path)):
        with Image.open(image) as im: tensor=image_to_tensor(im)
    elif isinstance(image,Image.Image): tensor=image_to_tensor(image)
    else: raise TypeError('image must be a path or PIL image')
    with torch.inference_mode(): probs=model(tensor.unsqueeze(0).to(next(model.parameters()).device)).softmax(1)[0].cpu()
    idx=int(probs.argmax()); roman=classes[idx]
    return {'label':roman,'kana':KANA.get(roman,roman),'confidence':float(probs[idx]),'alternatives':[(classes[i],KANA.get(classes[i],classes[i]),float(probs[i])) for i in probs.argsort(descending=True)[:3]]}


def _ink_mask(image):
    """Find pen strokes in a photo, preferring colored ink over paper shadows."""
    rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    colored = cv2.inRange(hsv, np.array([0, 45, 35]), np.array([179, 255, 245]))
    if cv2.countNonZero(colored) >= 20:
        mask = colored
    else:
        gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
        block = max(15, (min(gray.shape[:2]) // 2) | 1)
        block = min(block, 61)
        mask = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                     cv2.THRESH_BINARY_INV, block, 9)
    return cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))


def segment_kana_line(image):
    """Return left-to-right ink crops for a single handwritten line of kana."""
    if not isinstance(image, Image.Image):
        image = Image.open(image)
    image = ImageOps.exif_transpose(image).convert("RGB")
    mask = _ink_mask(image)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    height, width = mask.shape
    boxes = []
    for i in range(1, count):
        x, y, w, h, area = map(int, stats[i])
        # Ignore paper texture, isolated dust, and large background regions.
        if area >= 7 and h >= 5 and w >= 2 and area < height * width * .12:
            boxes.append((x, y, x + w, y + h, h))
    if not boxes:
        return []
    # Keep the main handwritten row. Photos often contain paper edges,
    # shadows, table texture, and isolated specks well below the text; without
    # this row filter, those components can join into a fake extra character.
    row_center = float(np.median([(box[1] + box[3]) / 2 for box in boxes]))
    preliminary_h = float(np.median([box[4] for box in boxes]))
    row_tolerance = max(2.2 * preliminary_h, height * 0.08)
    boxes = [box for box in boxes if abs((box[1] + box[3]) / 2 - row_center) <= row_tolerance]
    if not boxes:
        return []
    median_h = float(np.median([box[4] for box in boxes]))
    join_gap = max(7, int(median_h * .38))
    boxes.sort(key=lambda box: (box[0], box[1]))
    groups = []
    for x0, y0, x1, y1, _ in boxes:
        # Merge nearby disconnected strokes into one kana. The scale-aware gap
        # keeps normally spaced neighboring characters separate.
        match = next((g for g in reversed(groups) if x0 - g[2] <= join_gap), None)
        if match is None:
            groups.append([x0, y0, x1, y1])
        else:
            match[0] = min(match[0], x0); match[1] = min(match[1], y0)
            match[2] = max(match[2], x1); match[3] = max(match[3], y1)
    # Very wide groups usually mean touching strokes; split by clear empty
    # columns as a conservative fallback rather than feeding the whole word.
    crops = []
    for x0, y0, x1, y1 in groups:
        if x1 - x0 > max(100, median_h * 2.4) or y1 - y0 > max(120, median_h * 2.8):
            continue
        margin = max(3, int(max(x1 - x0, y1 - y0) * .12))
        x0, y0 = max(0, x0 - margin), max(0, y0 - margin)
        x1, y1 = min(width, x1 + margin), min(height, y1 + margin)
        # Remove lighting, paper grain, and pen color while preserving the
        # stroke silhouette expected by the character classifier.
        crops.append(Image.fromarray(255 - mask[y0:y1, x0:x1]))
    return crops


def predict_line(image):
    """Recognize a photo containing one or more separated handwritten kana."""
    segments = segment_kana_line(image)
    if not segments:
        # Preserve single-character support when segmentation finds no ink.
        segments = [image]
    model, classes = load_model()
    return [predict(segment, model, classes) for segment in segments]

if __name__=='__main__':
    import argparse, json
    p=argparse.ArgumentParser(); p.add_argument('image'); a=p.parse_args()
    # ASCII escaping keeps the CLI usable in Windows terminals with legacy code pages.
    print(json.dumps(predict(a.image), ensure_ascii=True, indent=2))
