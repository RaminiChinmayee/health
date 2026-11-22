# Heart disease risk — model report (v1.0.0)

*Generated 2026-11-21T06:35:55+00:00 by `ml/train_heart.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** UCI Heart Disease — Cleveland Clinic Foundation (processed) — https://archive.ics.uci.edu/dataset/45/heart+disease
- **Population:** 303 patients referred for coronary angiography, Cleveland Clinic, USA, 1981–1984; 68% male; mean age 54
- **Licence:** CC BY 4.0
- Rows after removing 0 exact duplicates: 303

## Method
- Evaluation protocol: stratified random 75/25 split (227 development / 76 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **gradient_boosting**.
- Probabilities: Platt scaling (sigmoid), 5-fold, fit on development data.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.893 | `{'clf__C': 0.01}` |
| random_forest | 0.902 | `{'clf__max_depth': 3, 'clf__min_samples_leaf': 1}` |
| gradient_boosting | 0.902 | `{'clf__learning_rate': 0.03, 'clf__max_depth': 3, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 81.6% | 72.4% – 89.5% |
| Sensitivity (recall) | 82.9% | 69.4% – 93.9% |
| Specificity | 80.5% | 67.5% – 92.1% |
| Precision | 78.4% |  |
| F1 | 80.6% |  |
| ROC-AUC | 92.7% | 86.4% – 97.4% |
| PR-AUC | 93.0% |  |
| Brier score (lower is better) | 0.115 |  |

Confusion matrix at threshold 0.5: TN=33, FP=8, FN=6, TP=29.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 7.9% | 6.2% |
| 21.7% | 6.7% |
| 45.6% | 46.7% |
| 74.9% | 73.3% |
| 91.0% | 100.0% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 83.5% ± 4.8% |
| roc_auc | 91.3% ± 3.7% |
| recall_sensitivity | 77.4% ± 9.7% |
| specificity | 88.6% ± 3.7% |
| f1 | 80.9% ± 6.4% |

## External validation (different hospital / population)
| Dataset | n | Accuracy | Sensitivity | Specificity | ROC-AUC |
|---|---|---|---|---|---|
| Hungarian Institute of Cardiology, Budapest (n≈294) | 294 | 75.8% | 85.9% | 70.2% | 88.0% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- cp: 0.083 ± 0.025
- ca: 0.038 ± 0.020
- thal: 0.036 ± 0.019
- sex: 0.020 ± 0.008
- oldpeak: 0.014 ± 0.005
- slope: 0.010 ± 0.003
- age: 0.009 ± 0.012
- thalach: 0.009 ± 0.005

## Limitations
- Trained on 303 patients from one US hospital in the 1980s who had already been referred for angiography — a population with a much higher rate of heart disease than the general public. Estimates for people without symptoms will tend to be too high.
- Several inputs (maximum heart rate on exercise test, ST depression, fluoroscopy vessel count, thallium scan) come from clinical tests. Missing optional inputs are filled with typical values, which lowers reliability.
- Sex was recorded as binary in the source data.
- Not validated on Indian populations. Not a diagnosis.

## Notes
- External-validation rows are missing most 'ca' and 'thal' values; they are imputed, so those results reflect performance with incomplete test data.
