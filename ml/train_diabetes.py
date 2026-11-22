"""Diabetes model — Pima Indians Diabetes dataset (lab-value based)."""
import numpy as np
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary

FEATURES = [
    Feature("preg", "number", min=0, max=20, step=1, required=False),
    Feature("plas", "number", min=40, max=300, step=1, unit="mg/dL"),  # 2-hour OGTT glucose
    Feature("pres", "number", min=30, max=140, step=1, unit="mm Hg"),  # diastolic BP
    Feature("skin", "number", min=5, max=100, step=1, unit="mm", required=False),
    Feature("insu", "number", min=10, max=900, step=1, unit="µU/mL", required=False),
    Feature("mass", "number", min=12, max=70, step=0.1, unit="kg/m²", profile_source="bmi"),
    Feature("pedi", "number", min=0.05, max=2.5, step=0.001, required=False),
    Feature("age", "number", min=21, max=100, step=1, unit="years", profile_source="age"),
]

if __name__ == "__main__":
    df = pd.read_csv(RAW / "pima.arff")
    for c in ["plas", "pres", "skin", "insu", "mass"]:
        df.loc[df[c] == 0, c] = np.nan  # physiologically impossible zeros = missing
    y = (df["class"] == "tested_positive").astype(int)
    card = train_binary(
        BinaryTask(
            key="diabetes",
            version="1.0.0",
            title="Diabetes risk (lab values)",
            X=df.drop(columns="class"),
            y=y,
            features=FEATURES,
            positive_label="Diabetes within 5 years of examination (WHO criteria)",
            dataset={
                "name": "Pima Indians Diabetes Database (NIDDK), via OpenML #37",
                "source": "https://www.openml.org/d/37",
                "citation": "Smith JW, Everhart JE, Dickson WC, Knowler WC, Johannes RS. Using the ADAP learning algorithm to forecast the onset of diabetes mellitus. Proc Annu Symp Comput Appl Med Care. 1988:261–265.",
                "license": "Public domain (CC0) as distributed by OpenML",
                "population": "768 women aged 21+ of Pima Native American heritage, near Phoenix, Arizona, USA",
                "files": {"pima.arff": sha256(RAW / "pima.arff")},
            },
            limitations=[
                "Trained only on women of Pima heritage aged 21 or older, a population with very high diabetes prevalence. Results for men, younger people, and Indian populations are extrapolations and may be inaccurate.",
                "The glucose input is the 2-hour value from an oral glucose tolerance test, not a fasting or random reading.",
                "Many insulin and skin-fold values are missing in the source data; when you leave optional inputs blank they are filled with typical values.",
                "Not a diagnosis. Diabetes is diagnosed with laboratory tests such as HbA1c or fasting glucose, interpreted by a clinician.",
            ],
        )
    )
    print(render_binary_report(card))
