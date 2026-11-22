# Diabetes risk (symptom questionnaire) — model report (v1.0.0)

*Generated 2026-11-21T06:42:02+00:00 by `ml/train_diabetes_symptoms.py`. All numbers are computed from data by the training script.*

## Data
- **Dataset:** UCI Early Stage Diabetes Risk Prediction — https://archive.ics.uci.edu/dataset/529/early+stage+diabetes+risk+prediction+dataset
- **Population:** 520 patients questioned at Sylhet Diabetes Hospital, Bangladesh; 63% male; ages 16–90
- **Licence:** CC BY 4.0
- Rows after removing 269 exact duplicates: 251

## Method
- Evaluation protocol: stratified random 75/25 split (188 development / 63 test rows).
- Model chosen by cross-validated ROC-AUC on development data only: **random_forest**.
- Probabilities: Platt scaling (sigmoid), 5-fold, fit on development data.

| Candidate | CV ROC-AUC (dev) | Best params |
|---|---|---|
| logistic_regression | 0.961 | `{'clf__C': 0.1}` |
| random_forest | 0.975 | `{'clf__max_depth': None, 'clf__min_samples_leaf': 1}` |
| gradient_boosting | 0.965 | `{'clf__learning_rate': 0.1, 'clf__max_depth': 2, 'clf__max_iter': 100}` |

## Held-out test results
| Metric | Value | 95% bootstrap CI |
|---|---|---|
| Accuracy | 92.1% | 84.1% – 98.4% |
| Sensitivity (recall) | 93.0% | 83.8% – 100.0% |
| Specificity | 90.0% | 73.3% – 100.0% |
| Precision | 95.2% |  |
| F1 | 94.1% |  |
| ROC-AUC | 96.3% | 91.0% – 100.0% |
| PR-AUC | 98.6% |  |
| Brier score (lower is better) | 0.079 |  |

Confusion matrix at threshold 0.5: TN=18, FP=2, FN=3, TP=40.

### Calibration (test set, quantile bins)
| Mean predicted probability | Observed rate |
|---|---|
| 8.2% | 15.4% |
| 40.2% | 25.0% |
| 75.7% | 100.0% |
| 94.5% | 100.0% |
| 96.6% | 100.0% |

## Cross-validation on all data (stability check)
| Metric | Mean ± SD |
|---|---|
| accuracy | 91.9% ± 4.7% |
| roc_auc | 97.0% ± 2.9% |
| recall_sensitivity | 95.4% ± 4.0% |
| specificity | 84.3% ± 12.2% |
| f1 | 94.2% ± 3.4% |

## Most influential inputs (permutation importance on test set, drop in ROC-AUC)
- polyuria: 0.124 ± 0.031
- polydipsia: 0.066 ± 0.020
- sex: 0.038 ± 0.013
- irritability: 0.017 ± 0.006
- visual_blurring: 0.012 ± 0.008
- itching: 0.011 ± 0.005
- partial_paresis: 0.011 ± 0.006
- genital_thrush: 0.009 ± 0.006

## Limitations
- Collected from people attending a diabetes hospital, so about 62% had diabetes. Real-world prevalence is far lower, so estimates for the general public will tend to be too high.
- Many rows in the source data are exact duplicates; they were removed before evaluation, leaving a smaller dataset than its nominal 520 rows.
- Symptoms are self-reported yes/no answers; diabetes often has no symptoms in its early stages, so a low estimate does not rule it out.
- Not a diagnosis. Diabetes is diagnosed with laboratory tests such as HbA1c or fasting glucose.
