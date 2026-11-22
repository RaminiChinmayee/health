# Speech-to-text and language identification evaluation

*Generated 2026-11-21T10:56:10+00:00 by `ml/eval_speech_language.py`. Dataset: Google FLEURS (test split) (CC BY 4.0).*

## Input-language identification (app's offline detector)
Every FLEURS test transcript per language, classified by `detect_language()`.

| Language | Sentences | Accuracy | Most common confusions |
|---|---|---|---|
| English | 647 | 100.0% | — |
| Hindi | 418 | 100.0% | — |
| Bengali | 920 | 100.0% | — |
| Marathi | 1015 | 97.1% | hi: 29 |
| Telugu | 472 | 100.0% | — |
| Tamil | 591 | 100.0% | — |
| Gujarati | 1000 | 100.0% | — |
| Urdu | 299 | 100.0% | — |
| Kannada | 838 | 100.0% | — |
| Odia | 883 | 100.0% | — |
| Malayalam | 958 | 100.0% | — |

## Speech-to-text (gemini-3.5-flash-lite)
First 5 FLEURS test recordings per language, transcribed with the app's language hint. Noisy = white noise added at 10 dB SNR. Lower is better. **Small samples: indicative only.**

| Language | WER (clean) | CER (clean) | WER (noisy) | CER (noisy) |
|---|---|---|---|---|
| English | 9.6% | 3.2% | 6.7% | 1.9% |
| Hindi | 5.7% | 1.4% | 17.1% | 8.0% |
| Bengali | 17.9% | 3.0% | 26.3% | 13.4% |
| Marathi | 35.0% | 12.3% | 30.0% | 11.4% |
| Telugu | 15.9% | 2.5% | 27.5% | 9.3% |
| Tamil | 56.5% | 37.7% | 66.1% | 39.9% |
| Gujarati | 15.7% | 5.2% | 25.9% | 11.3% |
| Urdu | 16.2% | 4.8% | 33.8% | 29.5% |
| Kannada | 13.1% | 3.5% | 27.9% | 14.3% |
| Odia | 40.2% | 15.1% | 40.2% | 21.2% |
| Malayalam | 21.1% | 5.5% | 25.4% | 5.8% |

WER is harsh for agglutinative languages (Telugu, Tamil, Kannada, Malayalam) where one spelling or suffix difference makes a whole long word wrong; CER is more informative there.

## Notes from inspecting individual transcripts
- **Tamil:** 4 of 5 clean clips have 2–9% CER. One recording (`10072241588933076862.wav`, 25.4 s for a 145-character sentence) was transcribed with the sentence read twice. The speaker most likely re-read it, so the transcript may be correct and the reference contains one reading. Excluding that clip, Tamil clean CER is **5.3%** (4 clips). The table above includes it.
- **Odia:** most errors are numbers written out as words ("11ଶ" → "ଏକାଦଶ") and spacing differences, not mis-heard words.
- **Urdu (fixed):** before the transcription prompt named the target script, Urdu speech was often written in Devanagari or romanised (CER 76%). With the script named, clean CER is about 5%. The fix is in `backend/app/services/gemini.py`.
- **Model:** these results are for `gemini-3.5-flash-lite`, the app's fallback, which handles most requests because the dedicated `gemini-3.5-transcribe` model allows only 25 requests a day on the free tier.
