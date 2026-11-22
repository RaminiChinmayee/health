# Chronic kidney disease risk — model report (v1.0.0)

*Generated 2026-11-21T17:26:48+00:00 by `ml/train_kidney.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** UCI Chronic Kidney Disease — https://archive.ics.uci.edu/dataset/336/chronic+kidney+disease
- **Population:** Patients at Apollo Hospitals, Karaikudi, Tamil Nadu, India (2015); adults only here (n=381), 61% with CKD
- **Licence:** CC BY 4.0
- Rows after removing 0 exact duplicates: 381

## Method
- Evaluation protocol: stratified random 75/25 split (285 development / 96 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **gradient_boosting**.
- Probabilities: Platt scaling (sigmoid), 5-fold, fit on development data.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.991 | `{'clf__C': 0.1}` |
| random_forest | 0.992 | `{'clf__max_depth': 5, 'clf__min_samples_leaf': 1}` |
| gradient_boosting | 0.993 | `{'clf__learning_rate': 0.1, 'clf__max_depth': 3, 'clf__max_iter': 300}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 97.9% | 94.8% – 100.0% |
| Sensitivity (recall) | 98.3% | 93.5% – 100.0% |
| Specificity | 97.4% | 90.7% – 100.0% |
| Precision | 98.3% |  |
| F1 | 98.3% |  |
| ROC-AUC | 97.5% | 91.1% – 100.0% |
| PR-AUC | 95.9% |  |
| Brier score (lower is better) | 0.028 |  |

Confusion matrix at threshold 0.5: TN=37, FP=1, FN=1, TP=57.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 5.9% | 0.0% |
| 16.9% | 10.5% |
| 82.8% | 100.0% |
| 97.1% | 100.0% |
| 98.9% | 94.7% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 97.7% ± 1.3% |
| roc_auc | 99.1% ± 1.2% |
| recall_sensitivity | 97.9% ± 2.1% |
| specificity | 97.5% ± 2.3% |
| f1 | 98.1% ± 1.1% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- hemo: 0.063 ± 0.021
- al: 0.011 ± 0.008
- dm: 0.010 ± 0.007
- bp: 0.005 ± 0.004
- sc: 0.002 ± 0.004
- pe: 0.001 ± 0.001
- htn: 0.000 ± 0.000
- appet: -0.000 ± 0.000

## Limitations
- A small dataset (about 390 adults) from one hospital in Tamil Nadu, where about 62% had chronic kidney disease. Real-world prevalence is far lower, so estimates for the general public will tend to be too high.
- People without kidney disease in this dataset were largely healthy, so the two groups are easy to tell apart. The very high test scores are therefore optimistic; performance on people with borderline values is likely lower.
- Uses blood and urine test values (creatinine, haemoglobin, urine albumin) that need a recent lab report; the model does not use eGFR or repeated measurements.
- Not a diagnosis. Kidney disease is diagnosed by a doctor using eGFR (from creatinine) and urine albumin tests repeated over 3 months.
