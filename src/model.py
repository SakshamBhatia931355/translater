import torch.nn as nn

class SmallCNN(nn.Module):
    def __init__(self, num_classes):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(1,16,3,padding=1), nn.BatchNorm2d(16), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.Conv2d(16,32,3,padding=1), nn.BatchNorm2d(32), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.Conv2d(32,64,3,padding=1), nn.BatchNorm2d(64), nn.ReLU(inplace=True), nn.MaxPool2d(2),
            nn.AdaptiveAvgPool2d((4,4)))
        self.classifier = nn.Sequential(nn.Flatten(), nn.Linear(64*16,128), nn.ReLU(inplace=True), nn.Dropout(.4), nn.Linear(128,num_classes))
    def forward(self, x): return self.classifier(self.features(x))
