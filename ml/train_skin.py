"""Skin-lesion image classifier — EfficientNet-B0 fine-tuned on HAM10000.

Data: HAM10000 (Tschandl P, Rosendahl C, Kittler H. Sci Data 5, 180161 (2018).
doi:10.1038/sdata.2018.161), Harvard Dataverse doi:10.7910/DVN/DBW86T, licence CC BY-NC 4.0
(non-commercial use only). 10,015 dermatoscopic images of 7,470 lesions, 7 diagnostic classes.

Protocol
  * Split by LESION (lesion_id): several images of the same lesion never appear in more than
    one of train / validation / test (HAM10000 has no patient identifier; lesion-level grouping is
    the strongest leakage control the metadata allows). StratifiedGroupKFold keeps class balance.
    ~70% train, ~15% validation (model selection, calibration, OOD threshold), ~15% test (reported).
  * ImageNet-pretrained EfficientNet-B0, all layers fine-tuned on CPU; augmentation (random
    resized crop, flips, rotation, colour jitter); class-weighted loss for the strong imbalance.
  * Best epoch chosen on validation macro-F1. Temperature scaling on validation logits.
  * Test metrics: accuracy, balanced accuracy, per-class precision/recall(sensitivity)/
    specificity/F1, macro-F1, confusion matrix, one-vs-rest ROC-AUC, calibration (ECE).
  * Out-of-distribution gate: images whose features are far (kNN cosine distance) from the
    training images are rejected; threshold = 99th percentile of validation distances.

Usage: python train_skin.py [--epochs 5]
"""
import argparse
import json
import platform
import time
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torchvision
from PIL import Image
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from torch.utils.data import DataLoader, Dataset
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0
from torchvision.transforms import v2 as T

from common import ARTIFACTS, RAW, SEED, sha256

import os

HAM = Path(os.environ.get("HAM_DIR", RAW / "ham10000"))  # override for smoke tests
CACHE = HAM / "cache_256.npy"
VERSION = "1.0.0"
SIZE, CROP = 256, 224
CLASSES = ["akiec", "bcc", "bkl", "df", "mel", "nv", "vasc"]
NAMES = {
    "akiec": "Actinic keratosis / intraepithelial carcinoma (Bowen's disease)",
    "bcc": "Basal cell carcinoma",
    "bkl": "Benign keratosis-like lesion",
    "df": "Dermatofibroma",
    "mel": "Melanoma",
    "nv": "Melanocytic naevus (mole)",
    "vasc": "Vascular lesion",
}
# Classes for which prompt dermatologist review is advised if suggested.
CONCERN = {"mel", "bcc", "akiec"}
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


def extract_and_cache(meta: pd.DataFrame) -> np.ndarray:
    if CACHE.exists():
        return np.load(CACHE, mmap_mode="r")
    wanted = set(meta.image_id + ".jpg")
    arr = np.lib.format.open_memmap(CACHE, mode="w+", dtype=np.uint8, shape=(len(meta), SIZE, SIZE, 3))
    index = {img: i for i, img in enumerate(meta.image_id + ".jpg")}
    done = 0
    for z in sorted(HAM.glob("part_*.zip")):
        with zipfile.ZipFile(z) as zf:
            for name in zf.namelist():
                base = Path(name).name
                if base in wanted:
                    with zf.open(name) as f:
                        im = Image.open(f).convert("RGB").resize((SIZE, SIZE), Image.BICUBIC)
                    arr[index[base]] = np.asarray(im)
                    done += 1
                    if done % 1000 == 0:
                        print(f"  cached {done}/{len(meta)}", flush=True)
    arr.flush()
    assert done == len(meta), f"only {done} of {len(meta)} images found"
    return np.load(CACHE, mmap_mode="r")


class Images(Dataset):
    def __init__(self, arr, idx, labels, train: bool):
        self.arr, self.idx, self.labels = arr, idx, labels
        self.tf = T.Compose(
            ([T.RandomResizedCrop(CROP, scale=(0.6, 1.0), antialias=True), T.RandomHorizontalFlip(), T.RandomVerticalFlip(), T.RandomRotation(20), T.ColorJitter(0.2, 0.2, 0.1, 0.02)] if train else [T.CenterCrop(CROP)])
            + [T.ToDtype(torch.float32, scale=True), T.Normalize(MEAN, STD)]
        )

    def __len__(self):
        return len(self.idx)

    def __getitem__(self, i):
        j = self.idx[i]
        x = torch.from_numpy(np.ascontiguousarray(self.arr[j])).permute(2, 0, 1)
        return self.tf(T.ToImage()(x)), int(self.labels[j])


def build_model() -> nn.Module:
    m = efficientnet_b0(weights=EfficientNet_B0_Weights.IMAGENET1K_V1)
    m.classifier = nn.Sequential(nn.Dropout(0.3), nn.Linear(1280, len(CLASSES)))
    return m


@torch.no_grad()
def predict(model, loader, tta=True):
    model.eval()
    logits, feats, ys = [], [], []
    for x, y in loader:
        f = model.avgpool(model.features(x)).flatten(1)
        lo = model.classifier(f)
        if tta:
            xf = torch.flip(x, dims=[3])
            lo = (lo + model.classifier(model.avgpool(model.features(xf)).flatten(1))) / 2
        logits.append(lo)
        feats.append(f)
        ys.append(y)
    return torch.cat(logits).numpy(), torch.cat(feats).numpy(), torch.cat(ys).numpy()


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    lt, yt = torch.tensor(logits), torch.tensor(y)
    t = torch.ones(1, requires_grad=True)
    opt = torch.optim.LBFGS([t], lr=0.05, max_iter=200)

    def closure():
        opt.zero_grad()
        loss = nn.functional.cross_entropy(lt / t.clamp(min=0.05), yt)
        loss.backward()
        return loss

    opt.step(closure)
    return float(t.clamp(min=0.05).item())


def softmax(z):
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def ece(probs, y, bins=15):
    conf, pred = probs.max(1), probs.argmax(1)
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi)
        if m.any():
            total += m.mean() * abs((pred[m] == y[m]).mean() - conf[m].mean())
    return float(total)


def knn_dist(q: np.ndarray, bank: np.ndarray, k: int = 5) -> np.ndarray:
    qn = q / np.linalg.norm(q, axis=1, keepdims=True)
    bn = bank / np.linalg.norm(bank, axis=1, keepdims=True)
    sims = qn @ bn.T
    return 1 - np.sort(sims, axis=1)[:, -k:].mean(1)


def main(epochs: int):
    torch.manual_seed(SEED)
    torch.set_num_threads(10)
    meta = pd.read_csv(HAM / "HAM10000_metadata.tab").sort_values("image_id").reset_index(drop=True)
    y_all = meta.dx.map({c: i for i, c in enumerate(CLASSES)}).values
    arr = extract_and_cache(meta)

    # Lesion-grouped, class-stratified split: fold 0 → test, fold 1 → validation, rest → train.
    sgkf = StratifiedGroupKFold(n_splits=7, shuffle=True, random_state=SEED)
    folds = [te for _, te in sgkf.split(meta, y_all, groups=meta.lesion_id)]
    test_idx, val_idx = folds[0], folds[1]
    train_idx = np.setdiff1d(np.arange(len(meta)), np.concatenate([test_idx, val_idx]))
    for a, b in [(train_idx, val_idx), (train_idx, test_idx), (val_idx, test_idx)]:
        assert not set(meta.lesion_id[a]) & set(meta.lesion_id[b]), "lesion leakage between splits"
    print(f"train {len(train_idx)} / val {len(val_idx)} / test {len(test_idx)} images", flush=True)

    counts = np.bincount(y_all[train_idx], minlength=len(CLASSES))
    weights = torch.tensor((counts.sum() / counts) ** 0.5, dtype=torch.float32)
    weights = weights / weights.mean()

    dl = lambda idx, train: DataLoader(Images(arr, idx, y_all, train), batch_size=32, shuffle=train, num_workers=4, persistent_workers=True)  # noqa: E731
    train_dl, val_dl, test_dl = dl(train_idx, True), dl(val_idx, False), dl(test_idx, False)

    model = build_model()
    opt = torch.optim.AdamW([
        {"params": model.features.parameters(), "lr": 2e-4},
        {"params": model.classifier.parameters(), "lr": 1e-3},
    ], weight_decay=1e-4)
    steps = epochs * len(train_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(opt, max_lr=[2e-4, 1e-3], total_steps=steps, pct_start=0.15)
    loss_fn = nn.CrossEntropyLoss(weight=weights, label_smoothing=0.05)
    ckpt = HAM / "train_ckpt.pt"
    history, best_f1, best_state, start_epoch = [], -1.0, None, 0
    if ckpt.exists():
        c = torch.load(ckpt, weights_only=False)
        model.load_state_dict(c["model"]); opt.load_state_dict(c["opt"]); sched.load_state_dict(c["sched"])
        history, best_f1, best_state, start_epoch = c["history"], c["best_f1"], c["best_state"], c["epoch"] + 1
        print(f"resuming after epoch {start_epoch}", flush=True)

    for ep in range(start_epoch, epochs):
        model.train()
        t0, run = time.time(), 0.0
        for i, (x, y) in enumerate(train_dl):
            opt.zero_grad()
            loss = loss_fn(model(x), y)
            loss.backward()
            opt.step()
            sched.step()
            run += loss.item()
            if i % 50 == 0:
                print(f"  epoch {ep + 1} batch {i}/{len(train_dl)} loss {run / (i + 1):.3f} ({time.time() - t0:.0f}s)", flush=True)
        vl, _, vy = predict(model, val_dl, tta=False)
        vf1 = f1_score(vy, vl.argmax(1), average="macro")
        vbacc = balanced_accuracy_score(vy, vl.argmax(1))
        history.append({"epoch": ep + 1, "train_loss": run / len(train_dl), "val_macro_f1": vf1, "val_balanced_acc": vbacc, "minutes": (time.time() - t0) / 60})
        print(f"epoch {ep + 1}: val macro-F1 {vf1:.3f}, balanced acc {vbacc:.3f} ({(time.time() - t0) / 60:.1f} min)", flush=True)
        if vf1 > best_f1:
            best_f1, best_state = vf1, {k: v.clone() for k, v in model.state_dict().items()}
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(), "history": history, "best_f1": best_f1, "best_state": best_state, "epoch": ep}, ckpt)

    model.load_state_dict(best_state)
    vl, vfeat, vy = predict(model, val_dl)
    temp = fit_temperature(vl, vy)
    tl, tfeat, ty = predict(model, test_dl)
    p_raw, p_cal = softmax(tl), softmax(tl / temp)
    pred = p_cal.argmax(1)

    # OOD gate: feature bank from training images (no augmentation).
    rng = np.random.default_rng(SEED)
    bank_idx = rng.choice(train_idx, size=min(2500, len(train_idx)), replace=False)
    _, bank, _ = predict(model, dl(bank_idx, False), tta=False)
    vdist = knn_dist(vfeat, bank)
    ood_thr = float(np.percentile(vdist, 99))
    tdist = knn_dist(tfeat, bank)
    # Sanity check on clearly non-skin synthetic inputs (noise, flat colour, stripes).
    synth = []
    for kind in range(30):
        g = np.random.default_rng(kind)
        img = g.integers(0, 255, (SIZE, SIZE, 3), dtype=np.uint8) if kind % 3 == 0 else np.full((SIZE, SIZE, 3), g.integers(0, 255, 3), dtype=np.uint8) if kind % 3 == 1 else np.tile((np.arange(SIZE) // 16 % 2 * 255).astype(np.uint8)[None, :, None], (SIZE, 1, 3))
        synth.append(img)
    s_arr = np.stack(synth)
    _, sfeat, _ = predict(model, DataLoader(Images(s_arr, np.arange(len(s_arr)), np.zeros(len(s_arr), int), False), batch_size=32), tta=False)
    sdist = knn_dist(sfeat, bank)

    cm = confusion_matrix(ty, pred, labels=range(len(CLASSES)))
    rep = classification_report(ty, pred, labels=range(len(CLASSES)), target_names=CLASSES, output_dict=True, zero_division=0)
    per_class = {}
    for i, c in enumerate(CLASSES):
        tp = cm[i, i]; fn = cm[i].sum() - tp; fp = cm[:, i].sum() - tp; tn = cm.sum() - tp - fn - fp
        per_class[c] = {
            "n_test": int(cm[i].sum()), "precision": rep[c]["precision"], "recall_sensitivity": rep[c]["recall"],
            "specificity": float(tn / (tn + fp)) if tn + fp else None, "f1": rep[c]["f1-score"],
            "roc_auc": float(roc_auc_score((ty == i).astype(int), p_cal[:, i])) if 0 < (ty == i).sum() < len(ty) else None,
        }
    metrics = {
        "n_test": int(len(ty)), "accuracy": float(accuracy_score(ty, pred)), "balanced_accuracy": float(balanced_accuracy_score(ty, pred)),
        "macro_f1": float(f1_score(ty, pred, average="macro")), "macro_roc_auc_ovr": float(roc_auc_score(ty, p_cal, multi_class="ovr", average="macro")),
        "ece_before_calibration": ece(p_raw, ty), "ece_after_calibration": ece(p_cal, ty), "temperature": temp,
        "per_class": per_class, "confusion_matrix": {"labels": CLASSES, "matrix": cm.tolist()},
        "majority_class_baseline_accuracy": float((ty == CLASSES.index("nv")).mean()),
    }

    out = Path(os.environ["SKIN_OUT"]) if os.environ.get("SKIN_OUT") else ARTIFACTS / "skin" / VERSION
    out.mkdir(parents=True, exist_ok=True)
    torch.save(best_state, out / "model.pt")
    np.save(out / "feature_bank.npy", bank.astype(np.float16))
    card = {
        "key": "skin", "version": VERSION, "title": "Skin lesion image classifier", "task": "image_classification",
        "trained_at": datetime.now(UTC).isoformat(timespec="seconds"), "architecture": "EfficientNet-B0 (ImageNet-pretrained, fully fine-tuned)",
        "input": {"size": CROP, "resize": SIZE, "mean": MEAN, "std": STD}, "classes": CLASSES, "class_names": NAMES, "concern_classes": sorted(CONCERN),
        "temperature": temp, "ood": {"method": "mean cosine distance to 5 nearest training-image features", "threshold": ood_thr, "bank_size": int(len(bank)),
            "val_rejected": float((vdist > ood_thr).mean()), "test_rejected": float((tdist > ood_thr).mean()), "synthetic_non_skin_rejected": float((sdist > ood_thr).mean())},
        "dataset": {
            "name": "HAM10000 (Human Against Machine with 10000 training images)", "source": "https://doi.org/10.7910/DVN/DBW86T",
            "citation": "Tschandl P, Rosendahl C, Kittler H. The HAM10000 dataset, a large collection of multi-source dermatoscopic images of common pigmented skin lesions. Sci Data 5, 180161 (2018). doi:10.1038/sdata.2018.161",
            "license": "CC BY-NC 4.0 (non-commercial use only)",
            "population": "10,015 dermatoscopic images of 7,470 pigmented skin lesions from patients in Austria and Australia; mostly lighter skin types",
            "rows_after_dedup": int(len(meta)), "class_counts": {c: int((y_all == i).sum()) for i, c in enumerate(CLASSES)},
            "files": {f.name: sha256(f) for f in sorted(HAM.glob("part_*.zip"))},
        },
        "evaluation": {
            "protocol": f"Lesion-grouped stratified split (no lesion in more than one split): {len(train_idx)} train / {len(val_idx)} validation / {len(test_idx)} test images. Best of {epochs} epochs by validation macro-F1; temperature scaling on validation; horizontal-flip test-time augmentation.",
            "history": history, "test": metrics,
        },
        "limitations": [
            "Trained on dermatoscopic images (taken with a skin-surface microscope), mostly of lighter skin types from Europe and Australia. Ordinary phone photos and darker skin tones are different from the training data, so results on them are much less reliable.",
            "Covers only 7 kinds of pigmented skin lesions. Rashes, infections, wounds and other skin conditions are outside what the model knows; it will still pick one of the 7 categories.",
            "It is not a cancer diagnosis. Only a doctor's examination, often with a biopsy, can diagnose skin cancer. Any changing, bleeding or unusual spot should be checked by a dermatologist regardless of this result.",
            "The dataset contains far more ordinary moles than other lesion types; the rarer categories are recognised less reliably (see per-category results).",
            "Licence is non-commercial (CC BY-NC 4.0).",
        ],
        "environment": {"python": platform.python_version(), "torch": torch.__version__, "torchvision": torchvision.__version__},
    }
    (out / "card.json").write_text(json.dumps(card, indent=2, ensure_ascii=False))
    pc = metrics["per_class"]
    lines = [
        f"# Skin lesion image classifier — model report (v{VERSION})", "",
        f"*Generated {card['trained_at']} by `ml/train_skin.py`. All numbers computed by the script.*", "",
        "## Data", f"- {card['dataset']['name']} — {card['dataset']['source']} — {card['dataset']['license']}",
        f"- {card['dataset']['population']}", f"- Class counts: {card['dataset']['class_counts']}", "",
        "## Method", f"- {card['architecture']}.", f"- {card['evaluation']['protocol']}", "",
        "| Epoch | Train loss | Val macro-F1 | Val balanced acc | Minutes |", "|---|---|---|---|---|",
        *[f"| {h['epoch']} | {h['train_loss']:.3f} | {h['val_macro_f1']:.3f} | {h['val_balanced_acc']:.3f} | {h['minutes']:.1f} |" for h in history], "",
        f"## Test results ({metrics['n_test']} images)",
        f"- Accuracy {metrics['accuracy']*100:.1f}% (majority-class baseline: {metrics['majority_class_baseline_accuracy']*100:.1f}%)",
        f"- Balanced accuracy {metrics['balanced_accuracy']*100:.1f}% · macro-F1 {metrics['macro_f1']:.3f} · macro ROC-AUC (one-vs-rest) {metrics['macro_roc_auc_ovr']:.3f}",
        f"- Calibration: ECE {metrics['ece_before_calibration']:.3f} before → {metrics['ece_after_calibration']:.3f} after temperature scaling (T = {temp:.2f})", "",
        "| Class | Test images | Precision | Sensitivity | Specificity | F1 | ROC-AUC |", "|---|---|---|---|---|---|---|",
        *[f"| {NAMES[c]} | {pc[c]['n_test']} | {pc[c]['precision']*100:.1f}% | {pc[c]['recall_sensitivity']*100:.1f}% | {pc[c]['specificity']*100:.1f}% | {pc[c]['f1']:.3f} | {pc[c]['roc_auc']:.3f} |" for c in CLASSES], "",
        "### Confusion matrix (rows = true, columns = predicted)", "| | " + " | ".join(CLASSES) + " |", "|---" * (len(CLASSES) + 1) + "|",
        *[f"| {CLASSES[i]} | " + " | ".join(str(v) for v in row) + " |" for i, row in enumerate(cm.tolist())], "",
        "## Out-of-distribution gate",
        f"- Threshold {ood_thr:.3f} (99th percentile of validation distances). Rejects {card['ood']['test_rejected']*100:.1f}% of real test images and {card['ood']['synthetic_non_skin_rejected']*100:.0f}% of 30 synthetic non-skin images (noise, flat colours, stripes).",
        "- Not evaluated on realistic non-skin photographs; the app additionally asks a vision model whether the photo shows a skin lesion.", "",
        "## Limitations", *[f"- {x}" for x in card["limitations"]],
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--epochs", type=int, default=5)
    main(ap.parse_args().epochs)
