# Skin lesion image classifier — model report (v1.0.0)

*Generated 2026-11-21T14:49:33+00:00 by `ml/train_skin.py`. All numbers computed by the script.*

## Data
- HAM10000 (Human Against Machine with 10000 training images) — https://doi.org/10.7910/DVN/DBW86T — CC BY-NC 4.0 (non-commercial use only)
- 10,015 dermatoscopic images of 7,470 pigmented skin lesions from patients in Austria and Australia; mostly lighter skin types
- Class counts: {'akiec': 327, 'bcc': 514, 'bkl': 1099, 'df': 115, 'mel': 1113, 'nv': 6705, 'vasc': 142}

## Method
- EfficientNet-B0 (ImageNet-pretrained, fully fine-tuned).
- Lesion-grouped stratified split (no lesion in more than one split): 7153 train / 1431 validation / 1431 test images. Best of 5 epochs by validation macro-F1; temperature scaling on validation; horizontal-flip test-time augmentation.

| Epoch | Train loss | Val macro-F1 | Val balanced acc | Minutes |
|---|---|---|---|---|
| 1 | 1.593 | 0.510 | 0.563 | 7.5 |
| 2 | 1.182 | 0.646 | 0.681 | 9.4 |
| 3 | 1.043 | 0.708 | 0.747 | 10.3 |
| 4 | 0.952 | 0.712 | 0.743 | 10.9 |
| 5 | 0.925 | 0.719 | 0.754 | 9.8 |

## Test results (1431 images)
- Accuracy 81.6% (majority-class baseline: 66.9%)
- Balanced accuracy 64.7% · macro-F1 0.659 · macro ROC-AUC (one-vs-rest) 0.940
- Calibration: ECE 0.088 before → 0.043 after temperature scaling (T = 0.73)

| Class | Test images | Precision | Sensitivity | Specificity | F1 | ROC-AUC |
|---|---|---|---|---|---|---|
| Actinic keratosis / intraepithelial carcinoma (Bowen's disease) | 46 | 57.7% | 32.6% | 99.2% | 0.417 | 0.903 |
| Basal cell carcinoma | 74 | 67.0% | 79.7% | 97.9% | 0.728 | 0.988 |
| Benign keratosis-like lesion | 157 | 58.1% | 68.8% | 93.9% | 0.630 | 0.926 |
| Dermatofibroma | 17 | 72.7% | 47.1% | 99.8% | 0.571 | 0.916 |
| Melanoma | 159 | 57.0% | 59.1% | 94.4% | 0.580 | 0.915 |
| Melanocytic naevus (mole) | 958 | 92.8% | 90.7% | 85.8% | 0.918 | 0.956 |
| Vascular lesion | 20 | 78.9% | 75.0% | 99.7% | 0.769 | 0.980 |

### Confusion matrix (rows = true, columns = predicted)
| | akiec | bcc | bkl | df | mel | nv | vasc |
|---|---|---|---|---|---|---|---|
| akiec | 15 | 8 | 12 | 1 | 8 | 2 | 0 |
| bcc | 2 | 59 | 6 | 0 | 1 | 5 | 1 |
| bkl | 5 | 6 | 108 | 1 | 21 | 16 | 0 |
| df | 1 | 6 | 0 | 8 | 0 | 2 | 0 |
| mel | 2 | 4 | 18 | 0 | 94 | 40 | 1 |
| nv | 1 | 2 | 42 | 1 | 41 | 869 | 2 |
| vasc | 0 | 3 | 0 | 0 | 0 | 2 | 15 |

## Out-of-distribution gate
- Threshold 0.610 (99th percentile of validation distances). Rejects 0.6% of real test images and 100% of 30 synthetic non-skin images (noise, flat colours, stripes).
- Not evaluated on realistic non-skin photographs; the app additionally asks a vision model whether the photo shows a skin lesion.

## Limitations
- Trained on dermatoscopic images (taken with a skin-surface microscope), mostly of lighter skin types from Europe and Australia. Ordinary phone photos and darker skin tones are different from the training data, so results on them are much less reliable.
- Covers only 7 kinds of pigmented skin lesions. Rashes, infections, wounds and other skin conditions are outside what the model knows; it will still pick one of the 7 categories.
- It is not a cancer diagnosis. Only a doctor's examination, often with a biopsy, can diagnose skin cancer. Any changing, bleeding or unusual spot should be checked by a dermatologist regardless of this result.
- The dataset contains far more ordinary moles than other lesion types; the rarer categories are recognised less reliably (see per-category results).
- Licence is non-commercial (CC BY-NC 4.0).
