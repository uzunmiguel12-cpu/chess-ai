"""
S3 — Rete neurale posizionale (PyTorch): ResNet su tensori 24x8x8 + eval scalare.

Predice la probabilita' che la mossa sia un ERRORE posizionale (cp_loss >= 100,
mosse non tattiche) — stesso target del classificatore GBM, cosi' l'AUC e'
confrontabile [DATO vs DATO].

PRINCIPIO NON NEGOZIABILE (deciso da Miguel): la rete fa solo RILEVAZIONE;
le spiegazioni nel pannello Sparring restano deterministiche (feature peggiorate).

Dimensioni (canali x blocchi -> parametri circa):
     64 x  6  ->   ~0.5M   (prova rapida, anche CPU)
    128 x 10  ->   ~3.0M   (default)
    192 x 12  ->   ~8.0M   (se c'e' GPU e i dati sono milioni)
"""

import torch
import torch.nn as nn

from tensori import N_PIANI


class BloccoResiduo(nn.Module):
    def __init__(self, canali):
        super().__init__()
        self.conv1 = nn.Conv2d(canali, canali, 3, padding=1, bias=False)
        self.bn1 = nn.BatchNorm2d(canali)
        self.conv2 = nn.Conv2d(canali, canali, 3, padding=1, bias=False)
        self.bn2 = nn.BatchNorm2d(canali)
        self.relu = nn.ReLU(inplace=True)

    def forward(self, x):
        y = self.relu(self.bn1(self.conv1(x)))
        y = self.bn2(self.conv2(y))
        return self.relu(x + y)


class RetePosizionale(nn.Module):
    def __init__(self, canali=128, blocchi=10):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv2d(N_PIANI, canali, 3, padding=1, bias=False),
            nn.BatchNorm2d(canali), nn.ReLU(inplace=True))
        self.tronco = nn.Sequential(*[BloccoResiduo(canali) for _ in range(blocchi)])
        self.testa = nn.Sequential(
            nn.Linear(canali + 1, 128), nn.ReLU(inplace=True),
            nn.Dropout(0.1), nn.Linear(128, 1))

    def forward(self, piani, eval_prima):
        """piani: (B,24,8,8) — eval_prima: (B,1) normalizzato. Ritorna logit (B,1)."""
        x = self.tronco(self.stem(piani))
        x = x.mean(dim=(2, 3))                       # global average pooling
        return self.testa(torch.cat([x, eval_prima], dim=1))


def conta_parametri(m):
    return sum(p.numel() for p in m.parameters() if p.requires_grad)


if __name__ == "__main__":
    for c, b in ((64, 6), (128, 10), (192, 12)):
        m = RetePosizionale(c, b)
        print(f"canali={c:3d} blocchi={b:2d} -> {conta_parametri(m)/1e6:.2f}M parametri")
