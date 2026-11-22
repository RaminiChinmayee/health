"""Diabetes model — UCI Early Stage Diabetes Risk Prediction (symptom questionnaire, Bangladesh)."""
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary

SYMPTOMS = {
    "Polyuria": "polyuria",
    "Polydipsia": "polydipsia",
    "sudden weight loss": "sudden_weight_loss",
    "weakness": "weakness",
    "Polyphagia": "polyphagia",
    "Genital thrush": "genital_thrush",
    "visual blurring": "visual_blurring",
    "Itching": "itching",
    "Irritability": "irritability",
    "delayed healing": "delayed_healing",
    "partial paresis": "partial_paresis",
    "muscle stiffness": "muscle_stiffness",
    "Alopecia": "alopecia",
    "Obesity": "obesity",
}

FEATURES = [
    Feature("age", "number", min=16, max=100, step=1, unit="years", profile_source="age"),
    Feature("sex", "choice", options=[0, 1], profile_source="sex"),
    *[Feature(v, "boolean", options=[0, 1]) for v in SYMPTOMS.values()],
]

if __name__ == "__main__":
    df = pd.read_csv(RAW / "early_diabetes" / "diabetes_data_upload.csv")
    X = pd.DataFrame({"age": df["Age"], "sex": (df["Gender"] == "Male").astype(int)})
    for src, dst in SYMPTOMS.items():
        X[dst] = (df[src] == "Yes").astype(int)
    y = (df["class"] == "Positive").astype(int)
    card = train_binary(
        BinaryTask(
            key="diabetes_symptoms",
            version="1.0.0",
            title="Diabetes risk (symptom questionnaire)",
            X=X,
            y=y,
            features=FEATURES,
            positive_label="Diabetes diagnosed by a physician",
            dataset={
                "name": "UCI Early Stage Diabetes Risk Prediction",
                "source": "https://archive.ics.uci.edu/dataset/529/early+stage+diabetes+risk+prediction+dataset",
                "citation": "Islam MMF, Ferdousi R, Rahman S, Bushra HY. Likelihood prediction of diabetes at early stage using data mining techniques. In: Computer Vision and Machine Intelligence in Medical Image Analysis. Springer; 2020. doi:10.24432/C5VG8H",
                "license": "CC BY 4.0",
                "population": "520 patients questioned at Sylhet Diabetes Hospital, Bangladesh; 63% male; ages 16–90",
                "files": {"early_diabetes.zip": sha256(RAW / "early_diabetes.zip")},
            },
            limitations=[
                "Collected from people attending a diabetes hospital, so about 62% had diabetes. Real-world prevalence is far lower, so estimates for the general public will tend to be too high.",
                "Many rows in the source data are exact duplicates; they were removed before evaluation, leaving a smaller dataset than its nominal 520 rows.",
                "Symptoms are self-reported yes/no answers; diabetes often has no symptoms in its early stages, so a low estimate does not rule it out.",
                "Not a diagnosis. Diabetes is diagnosed with laboratory tests such as HbA1c or fasting glucose.",
            ],
        )
    )
    print(render_binary_report(card))
