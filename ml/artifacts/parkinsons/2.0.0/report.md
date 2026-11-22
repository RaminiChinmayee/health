# Parkinson's disease voice screening — model report (v2.0.0)

*Generated 2026-11-21T07:12:02+00:00 by `ml/train_parkinsons.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** UCI Parkinson's Disease Classification (Sakar et al.) — https://archive.ics.uci.edu/dataset/470/parkinson+s+disease+classification
- **Population:** 756 sustained /a/ recordings from 252 people (188 with Parkinson's, 64 without), Istanbul, Turkey; 3 recordings per person
- **Licence:** CC BY 4.0
- Rows after removing 1 exact duplicates: 755

## Method
- Evaluation protocol: subject-level split: 189 subjects for development, 63 different subjects for testing (567 development / 188 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **gradient_boosting**.
- Probabilities: None — class-balanced model; outputs assume equal numbers of positive and negative cases.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.729 | `{'clf__C': 10.0}` |
| random_forest | 0.734 | `{'clf__max_depth': 3, 'clf__min_samples_leaf': 5}` |
| gradient_boosting | 0.743 | `{'clf__learning_rate': 0.03, 'clf__max_depth': 2, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 72.3% | 65.4% – 78.7% |
| Sensitivity (recall) | 75.5% | 68.4% – 82.0% |
| Specificity | 57.6% | 40.6% – 74.2% |
| Precision | 89.3% |  |
| F1 | 81.8% |  |
| ROC-AUC | 69.7% | 57.7% – 80.1% |
| PR-AUC | 89.8% |  |
| Brier score (lower is better) | 0.211 |  |

Confusion matrix at threshold 0.5: TN=19, FP=14, FN=38, TP=117.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 23.0% | 59.5% |
| 49.7% | 84.9% |
| 63.3% | 92.1% |
| 68.1% | 89.2% |
| 79.8% | 89.5% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 73.2% ± 7.0% |
| roc_auc | 74.5% ± 10.3% |
| recall_sensitivity | 77.5% ± 8.3% |
| specificity | 60.8% ± 10.5% |
| f1 | 81.0% ± 5.0% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- period_mean: 0.055 ± 0.018
- shimmer_apq11: 0.040 ± 0.024
- jitter_local_abs: 0.028 ± 0.015
- jitter_ppq5: 0.025 ± 0.013
- jitter_local: 0.009 ± 0.007
- period_sd: 0.007 ± 0.010
- shimmer_local_db: 0.003 ± 0.003
- jitter_rap: 0.001 ± 0.001

## Limitations
- Voice measures are a weak indicator on their own: when tested on people the model had never seen, it missed many people with Parkinson's and wrongly flagged many healthy people (see the measured sensitivity and specificity).
- The result is not a risk percentage. It shows whether the voice measures look more like the Parkinson's group or the healthy group in one study. Parkinson's is uncommon in the general population, so most people whose voice 'resembles the Parkinson's group' do not have it.
- Measures depend on the microphone, room and software. Values from a different setup than the study's may be unreliable.
- Colds, laryngitis, smoking, ageing, and other voice or neurological conditions also change these measures.
- Cannot diagnose Parkinson's disease, which requires examination by a neurologist.

## Notes
- Model v1.0.0 (Oxford dataset, 31 people) was rejected: on a subject-level split it correctly identified 0% of healthy test subjects.
- Class-balanced training without calibration: outputs assume equal numbers of people with and without Parkinson's.
