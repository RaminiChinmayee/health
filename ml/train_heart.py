"""Heart disease model — UCI Heart Disease (Cleveland), externally validated on Hungarian data."""
import numpy as np
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary  # noqa: F401

COLS = ["age", "sex", "cp", "trestbps", "chol", "fbs", "restecg", "thalach", "exang", "oldpeak", "slope", "ca", "thal", "num"]


def load(name: str) -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(RAW / "heart" / name, header=None, names=COLS, na_values="?")
    df.loc[df["chol"] == 0, "chol"] = np.nan  # 0 cholesterol = not recorded
    df.loc[df["trestbps"] == 0, "trestbps"] = np.nan
    y = (df["num"] > 0).astype(int)  # 0 = <50% vessel narrowing; 1-4 = disease present
    return df.drop(columns="num"), y


FEATURES = [
    Feature("age", "number", min=18, max=100, step=1, unit="years", profile_source="age"),
    Feature("sex", "choice", options=[0, 1], profile_source="sex"),  # 0 female, 1 male
    Feature("cp", "choice", options=[1, 2, 3, 4]),  # chest pain type
    Feature("trestbps", "number", min=70, max=220, step=1, unit="mm Hg"),
    Feature("chol", "number", min=90, max=650, step=1, unit="mg/dL"),
    Feature("fbs", "choice", options=[0, 1]),  # fasting blood sugar > 120 mg/dL
    Feature("restecg", "choice", options=[0, 1, 2], required=False),
    Feature("thalach", "number", min=60, max=220, step=1, unit="bpm"),
    Feature("exang", "choice", options=[0, 1]),
    Feature("oldpeak", "number", min=0, max=7, step=0.1, unit="mm"),
    Feature("slope", "choice", options=[1, 2, 3], required=False),
    Feature("ca", "choice", options=[0, 1, 2, 3], required=False),
    Feature("thal", "choice", options=[3, 6, 7], required=False),
]

if __name__ == "__main__":
    X, y = load("processed.cleveland.data")
    Xh, yh = load("processed.hungarian.data")
    card = train_binary(
        BinaryTask(
            key="heart",
            version="1.0.0",
            title="Heart disease risk",
            X=X,
            y=y,
            features=FEATURES,
            positive_label="Angiographic coronary artery disease (>50% narrowing of a major vessel)",
            dataset={
                "name": "UCI Heart Disease — Cleveland Clinic Foundation (processed)",
                "source": "https://archive.ics.uci.edu/dataset/45/heart+disease",
                "citation": "Janosi A, Steinbrunn W, Pfisterer M, Detrano R. Heart Disease [Dataset]. UCI Machine Learning Repository, 1988. doi:10.24432/C52P4X",
                "license": "CC BY 4.0",
                "population": "303 patients referred for coronary angiography, Cleveland Clinic, USA, 1981–1984; 68% male; mean age 54",
                "files": {"heart.zip": sha256(RAW / "heart.zip")},
            },
            external={"Hungarian Institute of Cardiology, Budapest (n≈294)": (Xh, yh)},
            limitations=[
                "Trained on 303 patients from one US hospital in the 1980s who had already been referred for angiography — a population with a much higher rate of heart disease than the general public. Estimates for people without symptoms will tend to be too high.",
                "Several inputs (maximum heart rate on exercise test, ST depression, fluoroscopy vessel count, thallium scan) come from clinical tests. Missing optional inputs are filled with typical values, which lowers reliability.",
                "Sex was recorded as binary in the source data.",
                "Not validated on Indian populations. Not a diagnosis.",
            ],
            notes=["External-validation rows are missing most 'ca' and 'thal' values; they are imputed, so those results reflect performance with incomplete test data."],
        )
    )
    print(render_binary_report(card))
