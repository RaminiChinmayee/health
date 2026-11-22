# Translation review checklist

The 10 Indian-language UI files (`frontend/src/i18n/locales/*.json`) were **machine-translated by an AI model** from `en.json`.
Each file passed automated checks: identical keys, and placeholders and markup kept intact. **No native speaker has reviewed them yet.**
Medical and safety text (disclaimers, emergency guidance) should get a native-speaker review before real users see it.

The translators flagged these items as uncertain:

## Applies to several languages
- **"Eggetarian"** (`health.diets.eggetarian`): most languages have no standard single word for it. bn, ta, gu, ur, kn, or and ml use a descriptive phrase ("vegetarian who eats eggs"), hi and mr use अंडाहारी, and te uses a loanword.
- **"Medical Disclaimer"** (`footer.disclaimer`, `legal.disclaimerTitle`): te, ur, kn and or use formal legal terms that some users may not recognize.
- **Gendered verbs** (`auth.register.terms`, `home.faq.q6`): hi, mr and ur use slash forms such as "समझता/समझती". Decide whether to rephrase these neutrally.
- **"FAQ" label** (`home.faq.eyebrow`): te, gu and kn keep "FAQ". hi, ta and ur spell it out, so the label repeats the section title.
- **`profileMenu.signedInAs`** reads naturally only next to the email. It is currently unused in the UI.

## Per language
- **hi:** `legal.disclaimerBody` "इलाज, उपचार" are near-synonyms, so the treat/cure distinction may be lost.
- **te:** `home.cta.title` reads as "take on responsibility for your health". `home.faq.a2` "held-out test data" is a descriptive rendering.
- **bn, mr:** numbers other than 112 are written in native digits (১১, ११). Other languages use Latin digits, so decide on one convention. bn `dashboard.greeting` uses নমস্কার; consider হ্যালো.
- **ta:** "email" uses மின்னஞ்சல் (formal) while other terms are loanwords. `auth.strength.fair` சுமார் may not read as stronger than "weak".
- **gu:** `health.bmiCategories.obese` મેદસ્વી; a clinical review may prefer સ્થૂળ.
- **ur:** `dashboard.greeting` uses the neutral loanword ہیلو. The interface renders right-to-left; this was checked visually.
- **ml:** in `auth.register.terms` the "-ും" suffixes fall inside the link text. `health.bmiCategories.obese` പൊണ്ണത്തടി is informal; അമിതവണ്ണം is more clinical.
- **or, ml:** "confidence levels" was rendered as "trust level", which is not the statistical term.

## Phase 3 feature strings (`locales/features/*.json`, 612 strings per language)

Also AI-translated and unreviewed. Translators flagged:
- **"Paralysis (brain haemorrhage)"** (`diseases.brain_hemorrhage`): the source dataset's own label. In te, ta, hi and gu the word for paralysis also means stroke in general, so it reads broader than the English.
- **Dish names:** mr uses पोळी for roti; kn uses ಅವಲಕ್ಕಿ/ಉಪ್ಪಿಟ್ಟು for poha/upma; gu uses રીંગણનો ઓળો for baingan bharta; ml uses ഉപ്പുമാവ് for upma. Kerala users say പരിപ്പ് rather than ദാൽ for dal. Already applied: te uses పప్పు for dal.
- **Thallium test options** (`fields.heart.thal.options`) and the **Parkinson's voice measures** (jitter, shimmer and others) have no lay equivalents; most languages transliterate them.
- **"Spotting during urination"** is ambiguous in the source; or and ml translated it as blood spots.
- **"Diabetes pedigree function"** has no patient-friendly term in any language.
- Already applied: hi `symptoms.palpitations` no longer includes घबराहट, which also means anxiety.
- **Model limitations** (`limits.*`): safety text. hi renders "extrapolations" in a slightly technical way.

## Phase 4 chat strings (`chat.*`, `voiceTest.*`, 144 strings per language)

AI-translated and unreviewed. Flagged items:
- The **self-harm support message** and **memory-consent text** are safety and privacy text, so they need native review first.
- The **"aaa" vowel** in the voice test is written differently across languages (hi “आआआ”, mr “आऽऽऽ”, ta “ஆ…”, gu “આ…”). Hindi and Telugu also differ slightly from the existing `assess.parkinsonsIntro`.
- **ta `voiceTest.experimental`** "சோதனை நிலை": சோதனை also means "test", so it may be ambiguous next to the voice test.
- **te `chat.suggestions.s2`** uses the everyday "షుగర్ వ్యాధి (డయాబెటిస్)", while the rest of the file uses మధుమేహం.
- **ml `chat.tts.pause`** is long for a button.
- **or `chat.messages_one/_other`** are identical, which is correct for Odia.
