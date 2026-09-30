"""Personalize a trained model with labeled samples in data/personal_samples."""
from pathlib import Path
import random
import numpy as np
import torch
from PIL import Image
from torch.utils.data import Dataset, DataLoader, ConcatDataset
from config import CHECKPOINT_DIR, IMAGE_DIR, ROOT, BATCH_SIZE, SEED
from dataset import HiraganaDataset, image_to_tensor, parse_label
from model import SmallCNN

PERSONAL_DIR=ROOT/'data'/'personal_samples'
# A small user-labeled set needs meaningful weight beside thousands of ETL8G
# examples. Augmentation creates varied views while this cap keeps the base
# handwriting distribution in every epoch.
PERSONAL_REPEATS=1800
EPOCHS=16

class PersonalDataset(Dataset):
    def __init__(self, paths, classes):
        self.paths=paths; self.to_idx={name:i for i,name in enumerate(classes)}
    def __len__(self): return max(1,PERSONAL_REPEATS//len(self.paths))
    def __getitem__(self,index):
        path=self.paths[index%len(self.paths)]
        with Image.open(path) as image: x=image_to_tensor(image,augment=True)
        return x,self.to_idx[parse_label(path)]

def main():
    paths=sorted(p for p in PERSONAL_DIR.glob('*') if p.suffix.lower() in {'.jpg','.jpeg','.png'})
    if not paths: raise SystemExit(f'Add labeled files such as kanaO1.jpg to {PERSONAL_DIR}')
    random.seed(SEED); np.random.seed(SEED); torch.manual_seed(SEED)
    device=torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    print(f'Fine-tuning device: {device}')
    checkpoint=CHECKPOINT_DIR/'best_model.pt'
    data=torch.load(checkpoint,map_location='cpu',weights_only=False)
    for path in paths:
        label=parse_label(path)
        if label not in data['classes']: raise SystemExit(f'{path.name}: unknown label {label}')
    base=HiraganaDataset(training=True,image_dir=IMAGE_DIR,classes=data['classes'])
    personal=PersonalDataset(paths,data['classes'])
    loader=DataLoader(ConcatDataset([base,personal]),batch_size=BATCH_SIZE,shuffle=True,num_workers=0)
    model=SmallCNN(len(data['classes'])); model.load_state_dict(data['state_dict']); model.to(device); model.train()
    optimizer=torch.optim.Adam(model.parameters(),lr=1.5e-4); loss_fn=torch.nn.CrossEntropyLoss()
    for epoch in range(EPOCHS):
        total=0.
        for x,y in loader:
            x,y=x.to(device),y.to(device); optimizer.zero_grad(); loss=loss_fn(model(x),y); loss.backward(); optimizer.step(); total+=float(loss.detach())
        print(f'Epoch {epoch+1}/{EPOCHS} loss={total/len(loader):.4f}')
    data['state_dict']={k:v.cpu() for k,v in model.state_dict().items()}; data['personal_samples']=[p.name for p in paths]
    torch.save(data,checkpoint)
    print(f'Updated {checkpoint} with {len(paths)} personal example(s).')

if __name__=='__main__': main()
