"""Chronic kidney disease model — UCI Chronic Kidney Disease (Apollo Hospitals, Tamil Nadu, India)."""
import numpy as np
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary

# Only inputs a user can be asked for directly. Optional lab fields were dropped: blanks were filled
# with the dataset's typical (mostly CKD-patient) values, which pushed healthy users' estimates up.
FEATURES = [
    Feature("age", "number", min=18, max=100, step=1, unit="years", profile_source="age"),
    Feature("bp", "number", min=40, max=140, step=1, unit="mm Hg"),  # diastolic (lower number)
    Feature("sc", "number", min=0.3, max=20, step=0.1, unit="mg/dL"),  # serum creatinine
    Feature("hemo", "number", min=3, max=20, step=0.1, unit="g/dL"),  # haemoglobin
    Feature("al", "choice", options=[0, 1, 2, 3, 4, 5]),  # urine albumin (dipstick)
    Feature("htn", "boolean", options=[0, 1]),
    Feature("dm", "boolean", options=[0, 1]),
    Feature("appet", "choice", options=[0, 1]),  # 0 good, 1 poor
    Feature("pe", "boolean", options=[0, 1]),  # swelling of feet/ankles
    Feature("ane", "boolean", options=[0, 1]),  # anaemia
]


def load() -> tuple[pd.DataFrame, pd.Series]:
    df = pd.read_csv(RAW / "kidney" / "ckd.csv")
    df = df.apply(lambda c: c.str.strip() if c.dtype == object else c)  # source has stray tabs
    df = df[(df["age"].isna()) | (df["age"] >= 18)]  # the app is for adults
    yn = lambda c: df[c].map({"yes": 1, "no": 0})  # noqa: E731
    X = pd.DataFrame({
        "age": df["age"], "bp": df["bp"], "sc": df["sc"], "hemo": df["hemo"], "al": df["al"],
        "htn": yn("htn"), "dm": yn("dm"), "su": df["su"], "sg": df["sg"], "bgr": df["bgr"], "bu": df["bu"],
        "appet": df["appet"].map({"good": 0, "poor": 1}), "pe": yn("pe"), "ane": yn("ane"),
    }).astype(float)
    y = (df["class"] == "ckd").astype(int)
    return X, y


if __name__ == "__main__":
    X, y = load()
    card = train_binary(
        BinaryTask(
            key="kidney",
            version="1.0.0",
            title="Chronic kidney disease risk",
            X=X,
            y=y,
            features=FEATURES,
            positive_label="Chronic kidney disease (diagnosed at the hospital)",
            dataset={
                "name": "UCI Chronic Kidney Disease",
                "source": "https://archive.ics.uci.edu/dataset/336/chronic+kidney+disease",
                "citation": "Rubini L, Soundarapandian P, Eswaran P. Chronic Kidney Disease [Dataset]. UCI Machine Learning Repository, 2015. doi:10.24432/C5G020",
                "license": "CC BY 4.0",
                "population": f"Patients at Apollo Hospitals, Karaikudi, Tamil Nadu, India (2015); adults only here (n={len(X)}), {y.mean():.0%} with CKD",
                "files": {"ckd.csv": sha256(RAW / "kidney" / "ckd.csv")},
            },
            limitations=[
                "A small dataset (about 390 adults) from one hospital in Tamil Nadu, where about 62% had chronic kidney disease. Real-world prevalence is far lower, so estimates for the general public will tend to be too high.",
                "People without kidney disease in this dataset were largely healthy, so the two groups are easy to tell apart. The very high test scores are therefore optimistic; performance on people with borderline values is likely lower.",
                "Uses blood and urine test values (creatinine, haemoglobin, urine albumin) that need a recent lab report; the model does not use eGFR or repeated measurements.",
                "Not a diagnosis. Kidney disease is diagnosed by a doctor using eGFR (from creatinine) and urine albumin tests repeated over 3 months.",
            ],
        )
    )
    print(render_binary_report(card))
