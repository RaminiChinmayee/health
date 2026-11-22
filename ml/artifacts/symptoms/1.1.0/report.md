# Symptom checker — model report (v1.1.0)

*Generated 2026-11-21T16:28:53+00:00 by `ml/train_symptoms.py`.*

## Data
- Disease Prediction Using Machine Learning (41 diseases, 132 symptoms) — https://www.kaggle.com/datasets/kaushil268/disease-prediction-using-machine-learning (copy from https://github.com/anujdutt9/Disease-Prediction-from-Symptoms)
- **Synthetic data.** 4962 rows contain only **305 unique symptom patterns** (at least 5 per disease). Duplicates were removed before evaluation; the original test file's rows nearly all appear in its training file.
- Licence: Not clearly stated by the original publisher — verify before commercial use

## Results (cross-validation over unique patterns)
| Model | Full symptoms top-1 | Full top-3 | 50% symptoms top-1 | 50% top-3 | 50% macro-F1 |
|---|---|---|---|---|---|
| bernoulli_nb | 98.0% | 100.0% | 82.4% ± 4.5% | 96.6% | 0.782 |
| bernoulli_nb+augment **(selected)** | 100.0% | 100.0% | 98.3% ± 1.6% | 99.8% | 0.979 |
| logistic_regression | 100.0% | 100.0% | 93.6% ± 3.3% | 99.7% | 0.934 |
| logistic_regression+augment | 99.8% | 99.9% | 96.8% ± 2.1% | 99.8% | 0.966 |
| random_forest | 99.9% | 100.0% | 91.6% ± 3.2% | 98.7% | 0.911 |
| random_forest+augment | 99.3% | 99.7% | 95.4% ± 2.0% | 99.5% | 0.951 |

Selection criterion: top-3 accuracy with 50% of symptoms (the realistic case).

## Ranking used in the app (v1.1.0)
- Unticked symptoms are treated as 'not mentioned': their penalty is scaled by min(1, (n − 1)/6), so one symptom alone no longer favours diseases with few symptoms. A symptom typical for a disease (probability ≥ 0.5) counts equally for every such disease.
- Conditions common in India get 3× prior weight: acne, allergy, arthritis, asthma, cervical_spondylosis, chicken_pox, common_cold, dengue, diabetes, fungal_infection, gastroenteritis, gerd, hemorrhoids, hepatitis_a, hepatitis_e, hypertension, hypothyroidism, jaundice, malaria, migraine, osteoarthritis, peptic_ulcer, pneumonia, tuberculosis, typhoid, uti. **This is a clinical-knowledge heuristic, not measured prevalence**; the dataset has none.
- Accuracy (correct disease ranked 1st / in top 3 / in top 5). The test folds have every disease equally often, so they cannot reward the prior, and it costs a little accuracy for rare conditions here:

| Input | Plain NB | Not-mentioned ramp | Ramp + India prior (app) |
|---|---|---|---|
| 1 symptom | 35% / 54% / 63% | 43% / 70% / 82% | 42% / 66% / 79% |
| 2 symptoms | 65% / 83% / 88% | 80% / 95% / 99% | 76% / 92% / 98% |
| 3 symptoms | 85% / 95% / 97% | 92% / 99% / 100% | 91% / 98% / 100% |
| 50% of symptoms | 98% / 100% / 100% | 98% / 100% / 100% | 95% / 100% / 100% |
| all symptoms | 100% / 100% / 100% | 100% / 100% / 100% | 100% / 100% / 100% |

## Safety rules (not learned — applied at inference)
- Red-flag symptoms always trigger an urgent-care message: acute_liver_failure, altered_sensorium, blood_in_sputum, bloody_stool, breathlessness, chest_pain, coma, fast_heart_rate, loss_of_balance, palpitations, slurred_speech, spinning_movements, stomach_bleeding, unsteadiness, weakness_of_one_body_side.
- Urgent conditions are flagged whenever they appear in the top results: alcoholic_hepatitis, brain_hemorrhage, dengue, heart_attack, hepatitis_b, hepatitis_c, hepatitis_d, hepatitis_e, hypoglycemia, malaria, pneumonia, tuberculosis, typhoid.

## Limitations
- The training data is synthetic, generated from a fixed table of diseases and symptoms. Scores show how well the model reproduces that table, not how accurately it identifies illness in real people.
- Only 41 conditions are covered. Your illness may be something not on the list, and the closest match will still be shown.
- With only one or two symptoms many conditions fit equally well; the order among them partly reflects a 'common in India' heuristic, not your individual risk. Add more symptoms for a more specific result.
- Match scores are relative to these 41 conditions and are not the probability that you have a disease.
- Not a diagnosis. Many conditions share symptoms; a doctor's examination and tests are needed.
