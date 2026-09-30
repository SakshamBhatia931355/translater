import re, csv, json
from pathlib import Path
from collections import defaultdict
from PIL import Image
from predict import load_model, predict
from config import OOD_DIR, OUTPUT_DIR, KANA

def main():
    model,classes=load_model(); rows=[]
    for path in sorted(OOD_DIR.iterdir()):
        if path.suffix.lower() not in {'.jpg','.jpeg','.png'}: continue
        m=re.match(r'ood([A-Z]+)\d+\.(?:jpg|jpeg|png)$',path.name,re.I)
        if not m: print(f'Skipping {path.name}: expected oodKA1.jpg'); continue
        truth=m.group(1).upper()
        if truth not in classes: print(f'Skipping {path.name}: class {truth} not in model'); continue
        result=predict(path,model,classes); rows.append({'filename':path.name,'truth':truth,'predicted':result['label'],'confidence':result['confidence'],'correct':truth==result['label']})
    if not rows: raise SystemExit(f'No labeled OOD samples found in {OOD_DIR}. Add files such as oodKA1.jpg.')
    OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    (OUTPUT_DIR/'ood_metrics.json').write_text(json.dumps({'count':len(rows),'accuracy':sum(r['correct'] for r in rows)/len(rows),'results':rows},indent=2),encoding='utf-8')
    print(f"OOD accuracy on {len(rows)} personal samples: {sum(r['correct'] for r in rows)/len(rows):.1%}; see outputs/ood_metrics.json")
if __name__=='__main__': main()
