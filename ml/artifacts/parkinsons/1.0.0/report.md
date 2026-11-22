# Parkinson's disease voice screening — model report (v1.0.0)

*Generated 2026-11-21T06:42:26+00:00 by `ml/train_parkinsons.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** UCI Parkinsons (Oxford Parkinson's Disease Detection Dataset) — https://archive.ics.uci.edu/dataset/174/parkinsons
- **Population:** 195 sustained-vowel recordings from 32 people (23 with Parkinson's, 8 without), UK
- **Licence:** CC BY 4.0
- Rows after removing 0 exact duplicates: 195

## Method
- Evaluation protocol: subject-level split: 24 subjects for development, 8 different subjects for testing (146 development / 49 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **logistic_regression**.
- Probabilities: Platt scaling (sigmoid), 5-fold, fit on development data.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.902 | `{'clf__C': 0.01}` |
| random_forest | 0.755 | `{'clf__max_depth': 3, 'clf__min_samples_leaf': 5}` |
| gradient_boosting | 0.820 | `{'clf__learning_rate': 0.03, 'clf__max_depth': 3, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 69.4% | 55.1% – 81.6% |
| Sensitivity (recall) | 91.9% | 82.9% – 100.0% |
| Specificity | 0.0% | 0.0% – 0.0% |
| Precision | 73.9% |  |
| F1 | 81.9% |  |
| ROC-AUC | 69.4% | 54.3% – 84.2% |
| PR-AUC | 91.1% |  |
| Brier score (lower is better) | 0.189 |  |

Confusion matrix at threshold 0.5: TN=0, FP=12, FN=3, TP=34.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 54.5% | 90.0% |
| 74.1% | 30.0% |
| 84.4% | 55.6% |
| 93.2% | 100.0% |
| 97.6% | 100.0% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 71.4% ± 20.7% |
| roc_auc | 78.8% ± 26.4% |
| recall_sensitivity | 90.2% ± 14.1% |
| specificity | 23.3% ± 38.9% |
| f1 | 81.5% ± 14.5% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- shimmer_apq11: 0.019 ± 0.034
- fo_max: 0.016 ± 0.010
- shimmer_apq5: 0.013 ± 0.014
- shimmer: 0.012 ± 0.015
- shimmer_db: 0.010 ± 0.018
- shimmer_apq3: 0.009 ± 0.011
- shimmer_dda: 0.009 ± 0.011
- hnr: 0.005 ± 0.011

## Limitations
- Very small study: 31 people in total, only 8 without Parkinson's. Test results come from a handful of people and have wide uncertainty.
- Voice measures depend strongly on the microphone, room, and recording software. Values measured differently from the original study (high-quality microphone in a sound-treated booth) may give unreliable results.
- Other conditions (colds, laryngitis, other neurological or voice disorders, smoking) also change these measures; the model was not trained to tell them apart.
- This is a research-grade screening model and cannot diagnose Parkinson's disease, which requires clinical examination by a neurologist.

## Notes
- Only the 16 Praat-derived measures were used; the nonlinear measures in the original dataset (RPDE, DFA, PPE, spread1/2, D2) were excluded because users can't obtain them from standard voice reports.
