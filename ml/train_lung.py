"""Lung cancer symptom questionnaire — "Lung Cancer" survey dataset (Kaggle, 309 respondents).

Provenance is weakly documented and 87% of respondents had lung cancer, so the model is trained
class-balanced without calibration and the app shows "resembles group" instead of a probability
(as for Parkinson's).
"""
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary

SYMPTOMS = {
    "SMOKING": "smoking",
    "YELLOW_FINGERS": "yellow_fingers",
    "ANXIETY": "anxiety",
    "CHRONIC DISEASE": "chronic_disease",
    "FATIGUE": "fatigue",
    "ALLERGY": "allergy",
    "WHEEZING": "wheezing",
    "ALCOHOL CONSUMING": "alcohol",
    "COUGHING": "coughing",
    "SHORTNESS OF BREATH": "shortness_of_breath",
    "SWALLOWING DIFFICULTY": "swallowing_difficulty",
    "CHEST PAIN": "chest_pain",
}  # PEER_PRESSURE omitted: not a meaningful health question for users

FEATURES = [
    Feature("age", "number", min=18, max=100, step=1, unit="years", profile_source="age"),
    Feature("sex", "choice", options=[0, 1], profile_source="sex"),
    *[Feature(v, "boolean", options=[0, 1]) for v in SYMPTOMS.values()],
]

if __name__ == "__main__":
    df = pd.read_csv(RAW / "lung" / "survey_lung_cancer.csv")
    df.columns = [c.strip() for c in df.columns]
    X = pd.DataFrame({"age": df["AGE"], "sex": (df["GENDER"] == "M").astype(int)})
    for src, dst in SYMPTOMS.items():
        X[dst] = (df[src] == 2).astype(int)  # source encodes 1 = no, 2 = yes
    y = (df["LUNG_CANCER"] == "YES").astype(int)
    card = train_binary(
        BinaryTask(
            key="lung",
            version="1.0.0",
            title="Lung cancer symptom screening",
            X=X,
            y=y,
            features=FEATURES,
            balanced=True,
            calibrate=False,
            display="similarity",
            positive_label="Answers resemble the lung-cancer group",
            dataset={
                "name": "Lung Cancer (survey) dataset",
                "source": "https://www.kaggle.com/datasets/nancyalaswad90/lung-cancer (copy: https://huggingface.co/datasets/nateraw/lung-cancer)",
                "citation": "Alaswad N. Lung Cancer [Dataset]. Kaggle.",
                "license": "CC BY-NC-SA 4.0 (non-commercial use only)",
                "population": "309 survey respondents; country, setting and how diagnoses were confirmed are not documented; 87% had lung cancer",
                "files": {"survey_lung_cancer.csv": sha256(RAW / "lung" / "survey_lung_cancer.csv")},
            },
            notes=[
                "Class-balanced training without calibration: outputs assume equal numbers of people with and without lung cancer, so the app shows how closely the answers resemble each group, not a probability.",
                "The 'peer pressure' question in the source survey was not used.",
            ],
            limitations=[
                "Small, weakly documented survey (309 people, 39 without lung cancer); where and how it was collected and how diagnoses were confirmed is not stated. Treat results as a rough indication only.",
                "Symptoms such as cough, breathlessness, wheezing and chest pain are common in many lung conditions (asthma, COPD, TB, infections), not only cancer; a 'resembles' result does not mean cancer.",
                "Many people with early lung cancer have no symptoms. A low similarity does not rule it out — especially for long-term smokers.",
                "Not a diagnosis. Lung problems are diagnosed with a doctor's examination, chest X-ray or CT scan, and other tests.",
            ],
        )
    )
    print(render_binary_report(card))
