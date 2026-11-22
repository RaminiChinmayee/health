# HealthAssist AI: demo walkthrough (about 10 minutes)

## Before you start

- **Backend:** `cd backend && .venv/bin/uvicorn app.main:app --port 8000`. Wait about 15 s for the embedding model to load.
- **Frontend:** `source ~/.nvm/nvm.sh && cd frontend && npm run dev`, then open http://localhost:5173.
- **Email:** with `EMAIL_BACKEND=console`, verification and reset links appear in the backend terminal. No email is sent.
- **Quota:** the Gemini free tier has daily limits (only 25 transcriptions a day on the dedicated model; the app then falls back to another model). Use a paid key for a long demo.

## 1. Homepage and languages (1 min)
1. Scroll the homepage: features, how it works, data protection, languages, FAQ.
2. Switch the language selector to **తెలుగు**, then **اردو**. The whole page changes, and Urdu switches to right-to-left.

## 2. Account and profile (1.5 min)
1. **Get Started** → register. Weak passwords and mismatched fields are rejected with clear messages.
2. Open the verification link from the backend terminal, then log in.
3. Use the **profile icon** (top right) to show the 12 menu items. Fill in the **Health Profile**; the BMI updates live.

## 3. Health assessments (2 min)
1. **Symptom Checker:** select *High fever, Headache, Pain behind the eyes, Joint pain, Skin rash*. The results show:
   - match strength rather than a percentage
   - an urgent-care banner with 112
   - an **About this model** panel stating that the data is synthetic.
2. **Health Assessments → Heart disease risk:**
   - Age and sex come pre-filled from the profile.
   - Submit to show the result, its main influences, and the model card's measured sensitivity and specificity with confidence intervals.
3. **Parkinson's voice screening:** explain that it shows "resembles group X", not a risk, and that the original dataset was rejected after splitting by person (see `ml/EVALUATION.md`).
4. **My Prediction History:** compare two results side by side.

## 4. Hospital finder and diet (1.5 min)
1. **Hospitals → Use my location** (or search a city). Shows the list sorted by distance, with Call and Directions buttons.
   - The public map servers can be busy; the Google Maps fallback link appears if they are.
2. **Diet Planner → Generate plan:** a 7-day Indian meal plan within the energy target.
   - Mark a meal as eaten, then open the **Tracker** tab.
   - Mark a dish **Don't show again**; it is excluded from future plans.

## 5. Health chatbot (3 min)
1. Ask in Telugu: *నాకు నిన్నటి నుండి జ్వరం, తలనొప్పి ఉన్నాయి. ఇది డెంగ్యూ కావచ్చా?* The answer streams in Telugu with a **MedlinePlus citation**.
2. Follow up with *since yesterday* to show short-term memory.
3. **Voice:** tap the microphone, speak, stop. The transcript appears for editing before sending. Then tap **Listen** on the answer to hear it read aloud.
4. **Chatbot memory:**
   - Turn memory on, then say *"I'm vegetarian and allergic to peanuts, and I have asthma."*
   - Open **Chatbot memory**: diet and allergy are saved, and asthma waits under **Waiting for your confirmation**.
5. Type *"I have severe chest pain"* to show the emergency banner with 112.

## 6. Privacy controls (30 s)
**Account Settings → Download my data** (one JSON file with everything), and **Delete account**.

## What to say about limitations
- Models are trained on public research datasets. They are not clinically validated and are never presented as a diagnosis.
- Translations are AI-generated and await native-speaker review (`docs/translation-review.md`).
- **Skin-image model:** trained on dermatoscopic images of mostly lighter skin; phone photos and darker skin tones are less reliable. It covers 7 pigmented-lesion types only and never gives a cancer diagnosis. Melanoma sensitivity on the test set is 59.1%, so the app always advises a dermatologist for any changing spot.
