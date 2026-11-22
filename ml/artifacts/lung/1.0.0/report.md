# Lung cancer symptom screening — model report (v1.0.0)

*Generated 2026-11-21T17:23:25+00:00 by `ml/train_lung.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** Lung Cancer (survey) dataset — https://www.kaggle.com/datasets/nancyalaswad90/lung-cancer (copy: https://huggingface.co/datasets/nateraw/lung-cancer)
- **Population:** 309 survey respondents; country, setting and how diagnoses were confirmed are not documented; 87% had lung cancer
- **Licence:** CC BY-NC-SA 4.0 (non-commercial use only)
- Rows after removing 33 exact duplicates: 276

## Method
- Evaluation protocol: stratified random 75/25 split (207 development / 69 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **logistic_regression**.
- Probabilities: None — class-balanced model; outputs assume equal numbers of positive and negative cases.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.923 | `{'clf__C': 0.1}` |
| random_forest | 0.883 | `{'clf__max_depth': 5, 'clf__min_samples_leaf': 5}` |
| gradient_boosting | 0.860 | `{'clf__learning_rate': 0.03, 'clf__max_depth': 2, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 91.3% | 84.1% – 97.1% |
| Sensitivity (recall) | 89.8% | 81.7% – 96.7% |
| Specificity | 100.0% | 100.0% – 100.0% |
| Precision | 100.0% |  |
| F1 | 94.6% |  |
| ROC-AUC | 97.0% | 92.4% – 100.0% |
| PR-AUC | 99.5% |  |
| Brier score (lower is better) | 0.089 |  |

Confusion matrix at threshold 0.5: TN=10, FP=0, FN=6, TP=53.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 16.3% | 28.6% |
| 60.2% | 100.0% |
| 81.2% | 100.0% |
| 89.3% | 100.0% |
| 96.7% | 100.0% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 86.6% ± 4.4% |
| roc_auc | 93.3% ± 4.5% |
| recall_sensitivity | 86.7% ± 4.3% |
| specificity | 86.1% ± 15.0% |
| f1 | 91.7% ± 2.8% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- alcohol: 0.030 ± 0.012
- swallowing_difficulty: 0.024 ± 0.011
- coughing: 0.022 ± 0.008
- yellow_fingers: 0.021 ± 0.013
- allergy: 0.020 ± 0.017
- fatigue: 0.015 ± 0.019
- wheezing: 0.008 ± 0.005
- anxiety: 0.005 ± 0.011

## Limitations
- Small, weakly documented survey (309 people, 39 without lung cancer); where and how it was collected and how diagnoses were confirmed is not stated. Treat results as a rough indication only.
- Symptoms such as cough, breathlessness, wheezing and chest pain are common in many lung conditions (asthma, COPD, TB, infections), not only cancer; a 'resembles' result does not mean cancer.
- Many people with early lung cancer have no symptoms. A low similarity does not rule it out — especially for long-term smokers.
- Not a diagnosis. Lung problems are diagnosed with a doctor's examination, chest X-ray or CT scan, and other tests.

## Notes
- Class-balanced training without calibration: outputs assume equal numbers of people with and without lung cancer, so the app shows how closely the answers resemble each group, not a probability.
- The 'peer pressure' question in the source survey was not used.
