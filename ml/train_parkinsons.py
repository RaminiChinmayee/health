"""Parkinson's voice screening — UCI "Parkinson's Disease Classification" (Sakar et al., 2019).

Why this dataset (v2): the earlier Oxford dataset (v1.0.0) has only 31 people, 8 of them
healthy. Evaluated with a subject-level split it identified 0% of healthy test subjects
correctly — see `artifacts/parkinsons/1.0.0/report.md`. It is not deployed.

This dataset has 252 people (64 healthy). We use only the 15 standard Praat voice measures
(jitter, shimmer, harmonicity, pitch period), which appear in clinical voice-analysis reports
and can be computed from a recording. Rows are split by *person* (3 recordings each).

The training data is 75% Parkinson's — far above real-world prevalence — so the model is
class-balanced and *not* calibrated to that prevalence, and the app shows "resembles group
A / group B" rather than a risk percentage.
"""
import pandas as pd

from common import RAW, BinaryTask, Feature, render_binary_report, sha256, train_binary

# source column → (feature name, min, max, step, unit). Values are fractions, as in Praat.
PRAAT = {
    "locPctJitter": ("jitter_local", 0, 0.06, 0.00001, None),
    "locAbsJitter": ("jitter_local_abs", 0, 0.0006, 0.0000001, "s"),
    "rapJitter": ("jitter_rap", 0, 0.03, 0.00001, None),
    "ppq5Jitter": ("jitter_ppq5", 0, 0.04, 0.00001, None),
    "ddpJitter": ("jitter_ddp", 0, 0.09, 0.00001, None),
    "locShimmer": ("shimmer_local", 0, 0.5, 0.00001, None),
    "locDbShimmer": ("shimmer_local_db", 0, 4, 0.001, "dB"),
    "apq3Shimmer": ("shimmer_apq3", 0, 0.3, 0.00001, None),
    "apq5Shimmer": ("shimmer_apq5", 0, 0.4, 0.00001, None),
    "apq11Shimmer": ("shimmer_apq11", 0, 0.5, 0.00001, None),
    "ddaShimmer": ("shimmer_dda", 0, 0.8, 0.00001, None),
    "meanNoiseToHarmHarmonicity": ("nhr", 0, 1.5, 0.00001, None),
    "meanHarmToNoiseHarmonicity": ("hnr", -5, 45, 0.001, "dB"),
    "meanPeriodPulses": ("period_mean", 0.0015, 0.02, 0.000001, "s"),
    "stdDevPeriodPulses": ("period_sd", 0, 0.006, 0.0000001, "s"),
}

FEATURES = [Feature(n, "number", min=lo, max=hi, step=st, unit=u) for (n, lo, hi, st, u) in PRAAT.values()]

if __name__ == "__main__":
    f = RAW / "pd_speech" / "pd_speech_features.csv"
    df = pd.read_csv(f, header=1)
    X = df[list(PRAAT)].rename(columns={k: v[0] for k, v in PRAAT.items()})
    y = df["class"].astype(int)
    groups = df["id"].astype(str)
    healthy = groups[y == 0].nunique()
    card = train_binary(
        BinaryTask(
            key="parkinsons",
            version="2.0.0",
            title="Parkinson's disease voice screening",
            X=X,
            y=y,
            groups=groups,
            features=FEATURES,
            balanced=True,
            calibrate=False,
            display="similarity",
            positive_label="Voice pattern resembles the Parkinson's group",
            dataset={
                "name": "UCI Parkinson's Disease Classification (Sakar et al.)",
                "source": "https://archive.ics.uci.edu/dataset/470/parkinson+s+disease+classification",
                "citation": "Sakar CO, Serbes G, Gunduz A, et al. A comparative analysis of speech signal processing algorithms for Parkinson's disease classification and the use of the tunable Q-factor wavelet transform. Applied Soft Computing 2019;74:255–263. doi:10.24432/C5MS4X",
                "license": "CC BY 4.0",
                "population": f"{len(df)} sustained /a/ recordings from {groups.nunique()} people ({groups.nunique() - healthy} with Parkinson's, {healthy} without), Istanbul, Turkey; 3 recordings per person",
                "files": {"pd_speech.zip": sha256(RAW / "pd_speech.zip")},
            },
            limitations=[
                "Voice measures are a weak indicator on their own: when tested on people the model had never seen, it missed many people with Parkinson's and wrongly flagged many healthy people (see the measured sensitivity and specificity).",
                "The result is not a risk percentage. It shows whether the voice measures look more like the Parkinson's group or the healthy group in one study. Parkinson's is uncommon in the general population, so most people whose voice 'resembles the Parkinson's group' do not have it.",
                "Measures depend on the microphone, room and software. Values from a different setup than the study's may be unreliable.",
                "Colds, laryngitis, smoking, ageing, and other voice or neurological conditions also change these measures.",
                "Cannot diagnose Parkinson's disease, which requires examination by a neurologist.",
            ],
            notes=[
                "Model v1.0.0 (Oxford dataset, 31 people) was rejected: on a subject-level split it correctly identified 0% of healthy test subjects.",
                "Class-balanced training without calibration: outputs assume equal numbers of people with and without Parkinson's.",
            ],
        )
    )
    print(render_binary_report(card))
