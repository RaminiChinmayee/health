# Diabetes risk (lab values) — model report (v1.0.0)

*Generated 2026-11-21T06:36:26+00:00 by `ml/train_diabetes.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** Pima Indians Diabetes Database (NIDDK), via OpenML #37 — https://www.openml.org/d/37
- **Population:** 768 women aged 21+ of Pima Native American heritage, near Phoenix, Arizona, USA
- **Licence:** Public domain (CC0) as distributed by OpenML
- Rows after removing 0 exact duplicates: 768

## Method
- Evaluation protocol: stratified random 75/25 split (576 development / 192 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **logistic_regression**.
- Probabilities: Platt scaling (sigmoid), 5-fold, fit on development data.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.836 | `{'clf__C': 0.1}` |
| random_forest | 0.831 | `{'clf__max_depth': 5, 'clf__min_samples_leaf': 5}` |
| gradient_boosting | 0.824 | `{'clf__learning_rate': 0.03, 'clf__max_depth': 2, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 71.9% | 65.1% – 78.1% |
| Sensitivity (recall) | 52.2% | 40.7% – 64.6% |
| Specificity | 82.4% | 75.4% – 89.3% |
| Precision | 61.4% |  |
| F1 | 56.5% |  |
| ROC-AUC | 82.2% | 76.1% – 87.6% |
| PR-AUC | 68.5% |  |
| Brier score (lower is better) | 0.168 |  |

Confusion matrix at threshold 0.5: TN=103, FP=22, FN=32, TP=35.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 5.8% | 2.6% |
| 14.0% | 7.9% |
| 27.5% | 44.7% |
| 47.6% | 50.0% |
| 78.5% | 69.2% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 76.6% ± 2.9% |
| roc_auc | 83.6% ± 3.0% |
| recall_sensitivity | 55.6% ± 7.0% |
| specificity | 87.8% ± 4.0% |
| f1 | 62.2% ± 5.2% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- plas: 0.162 ± 0.037
- mass: 0.040 ± 0.017
- preg: 0.025 ± 0.011
- pedi: 0.009 ± 0.005
- age: 0.004 ± 0.005
- pres: 0.000 ± 0.000
- skin: -0.000 ± 0.000
- insu: -0.001 ± 0.002

## Limitations
- Trained only on women of Pima heritage aged 21 or older, a population with very high diabetes prevalence. Results for men, younger people, and Indian populations are extrapolations and may be inaccurate.
- The glucose input is the 2-hour value from an oral glucose tolerance test, not a fasting or random reading.
- Many insulin and skin-fold values are missing in the source data; when you leave optional inputs blank they are filled with typical values.
- Not a diagnosis. Diabetes is diagnosed with laboratory tests such as HbA1c or fasting glucose, interpreted by a clinician.
