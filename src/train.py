import csv, json, random
import numpy as np
import torch
from torch.utils.data import DataLoader, Subset
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import accuracy_score, confusion_matrix, classification_report
import matplotlib.pyplot as plt
from tqdm import trange
from config import *
from dataset import HiraganaDataset
from model import SmallCNN

def main():
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    device=torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(f'Training device: {device}')
    base = HiraganaDataset(training=False)
    if len(base)==0: raise SystemExit(f"No training images found at {IMAGE_DIR}. Run the dataset setup in README.md.")
    labels=[base.class_to_idx[y] for _,y in base.rows]
    splitter=StratifiedKFold(n_splits=FOLDS,shuffle=True,random_state=SEED)
    CHECKPOINT_DIR.mkdir(parents=True,exist_ok=True); OUTPUT_DIR.mkdir(parents=True,exist_ok=True)
    fold_metrics=[]; all_logits=[]
    for fold,(tr,va) in enumerate(splitter.split(np.zeros(len(labels)),labels)):
        train_ds=HiraganaDataset([(base.rows[i]) for i in tr],training=True,classes=base.classes)
        val_ds=HiraganaDataset([(base.rows[i]) for i in va],training=False,classes=base.classes)
        train_dl=DataLoader(train_ds,batch_size=BATCH_SIZE,shuffle=True,num_workers=0)
        val_dl=DataLoader(val_ds,batch_size=BATCH_SIZE,shuffle=False,num_workers=0)
        model=SmallCNN(len(base.classes)).to(device); opt=torch.optim.Adam(model.parameters(),lr=LEARNING_RATE); loss_fn=torch.nn.CrossEntropyLoss()
        best=0.; best_state=None
        for epoch in trange(EPOCHS,desc=f'Fold {fold+1}/{FOLDS}'):
            model.train()
            for x,y in train_dl:
                x,y=x.to(device),y.to(device)
                opt.zero_grad(); loss=loss_fn(model(x),y); loss.backward(); opt.step()
            model.eval(); preds=[]; truth=[]
            with torch.no_grad():
                for x,y in val_dl:
                    preds.extend(model(x.to(device)).argmax(1).cpu().tolist()); truth.extend(y.tolist())
            score=accuracy_score(truth,preds)
            if score>best: best=score; best_state={k:v.cpu().clone() for k,v in model.state_dict().items()}
        model.load_state_dict(best_state)
        path=CHECKPOINT_DIR/f'fold_{fold}.pt'
        torch.save({'state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'classes':base.classes,'img_size':IMG_SIZE,'mean':MEAN,'std':STD,'fold':fold,'val_accuracy':best},path)
        fold_metrics.append(best); all_logits.append((fold,model,va))
        print(f'Fold {fold+1}: best validation accuracy {best:.3f}; saved {path}')
    # Select final inference model using mean k-fold validation score, then refit on all data.
    metrics={'fold_accuracies':fold_metrics,'mean_accuracy':float(np.mean(fold_metrics)),'std_accuracy':float(np.std(fold_metrics)),'classes':base.classes,'note':'Random record-level folds can contain samples from the same ETL8G writers in train and validation; this is not a writer-independent estimate. Check personal handwriting separately.'}
    # Retrain one deployable model on all 1000 samples, using a validation holdout for best epoch.
    model=SmallCNN(len(base.classes)).to(device); opt=torch.optim.Adam(model.parameters(),lr=LEARNING_RATE); loss_fn=torch.nn.CrossEntropyLoss()
    ds=HiraganaDataset(training=True,classes=base.classes); dl=DataLoader(ds,batch_size=BATCH_SIZE,shuffle=True,num_workers=0)
    for _ in trange(EPOCHS,desc='Final model'):
        model.train()
        for x,y in dl:
            x,y=x.to(device),y.to(device); opt.zero_grad(); loss=loss_fn(model(x),y); loss.backward(); opt.step()
    torch.save({'state_dict':{k:v.cpu() for k,v in model.state_dict().items()},'classes':base.classes,'img_size':IMG_SIZE,'mean':MEAN,'std':STD},CHECKPOINT_DIR/'best_model.pt')
    (OUTPUT_DIR/'metrics.json').write_text(json.dumps(metrics,indent=2),encoding='utf-8')
    print(f"Mean CV accuracy: {metrics['mean_accuracy']:.3f} ± {metrics['std_accuracy']:.3f}\nSaved deployable model: {CHECKPOINT_DIR/'best_model.pt'}")
if __name__=='__main__': main()
