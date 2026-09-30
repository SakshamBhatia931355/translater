import csv
from sklearn.model_selection import StratifiedKFold
from dataset import parse_label
from config import IMAGE_DIR, SPLITS_DIR, FOLDS, SEED

def main():
    files = sorted(p for p in IMAGE_DIR.iterdir() if p.suffix.lower() in {'.jpg','.jpeg','.png'})
    if not files: raise SystemExit(f"No images found in {IMAGE_DIR}. See README dataset setup.")
    labels = [parse_label(p) for p in files]
    splitter = StratifiedKFold(n_splits=FOLDS, shuffle=True, random_state=SEED)
    SPLITS_DIR.mkdir(parents=True, exist_ok=True)
    with (SPLITS_DIR/'folds.csv').open('w', newline='', encoding='utf-8') as f:
        w=csv.writer(f); w.writerow(['filename','label','fold'])
        for fold, (_, valid) in enumerate(splitter.split(files, labels)):
            for i in valid: w.writerow([files[i].name, labels[i], fold])
    print(f"Wrote stratified {FOLDS}-fold assignments for {len(files)} images to {SPLITS_DIR/'folds.csv'}")
if __name__=='__main__': main()
