"""Rule-based diet planner.

Energy:   Mifflin–St Jeor BMR (Mifflin et al., Am J Clin Nutr 1990;51:241–7) × activity factor.
Goal:     lose → −500 kcal/day capped at 20% of TDEE; gain → +300 kcal/day.
Floors:   never below 1200 kcal (women) / 1500 kcal (men) / 1350 kcal (sex not given).
Protein:  ≥ 0.83 g/kg/day (WHO/FAO/UNU 2007 safe level, also used by ICMR-NIN 2020); 1.0 g/kg when losing weight.
Fat:      25% of energy (inside the 20–35% acceptable range, IOM 2005).
Carbs:    remainder.  Fibre: 14 g per 1000 kcal (Dietary Guidelines for Americans 2020–2025).

Not for under-18s, and weight-loss plans are refused when BMI < 18.5. Users who disclosed health
conditions are told to check the plan with a doctor or dietitian.
"""
from __future__ import annotations

import json
import random
import re
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "foods.json"

ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "active": 1.725, "very_active": 1.9}
SLOT_SHARE = {"breakfast": 0.25, "lunch": 0.35, "snack": 0.10, "dinner": 0.30}
DIET_ALLOWED = {
    "vegan": {"vegan"},
    "vegetarian": {"vegan", "dairy"},
    "jain": {"vegan", "dairy"},
    "eggetarian": {"vegan", "dairy", "egg"},
    "non_vegetarian": {"vegan", "dairy", "egg", "fish", "meat"},
    "other": {"vegan", "dairy", "egg", "fish", "meat"},
}
# ---------------------------------------------------------------- allergies & foods to avoid
# Each term maps to ("allergen", key) or ("ingredients", {keys}) or ("dishes", {keys}).
# Terms: English, common romanised Indian names, and native-script names in all 10 Indian languages.
DAL = {"toor_dal", "lentil", "mung", "urad_raw"}
PULSES = DAL | {"chickpea", "rajma", "besan", "mung_sprout"}
_T: dict[str, tuple[str, object]] = {}


def _add(kind: str, target, *terms: str) -> None:
    for t in terms:
        _T[t.lower()] = (kind, target)


# allergen groups
_add("allergen", "dairy", "milk", "dairy", "lactose", "doodh", "दूध", "పాలు", "பால்", "দুধ", "દૂધ", "ಹಾಲು", "പാൽ", "ଦୁଧ", "دودھ")
_add("allergen", "gluten", "gluten", "wheat", "maida", "atta", "gehu", "gehun", "गेहूं", "गेहूँ", "गहू", "గోధుమ", "గోధుమలు", "கோதுமை", "গম", "ઘઉં", "ಗೋಧಿ", "ഗോതമ്പ്", "ଗହମ", "گندم")
_add("allergen", "egg", "egg", "eggs", "anda", "ande", "अंडा", "अंडे", "अंडी", "గుడ్డు", "గుడ్లు", "కోడిగుడ్డు", "முட்டை", "ডিম", "ઈંડા", "ઇંડા", "ಮೊಟ್ಟೆ", "മുട്ട", "ଅଣ୍ଡା", "انڈا", "انڈے")
_add("allergen", "fish", "fish", "seafood", "machli", "machhli", "meen", "मछली", "मासे", "चेप", "చేప", "చేపలు", "மீன்", "মাছ", "માછલી", "ಮೀನು", "മീൻ", "ମାଛ", "مچھلی")
_add("allergen", "peanut", "peanut", "peanuts", "groundnut", "groundnuts", "moongphali", "mungfali", "singdana", "palli", "मूंगफली", "शेंगदाणे", "शेंगदाणा", "వేరుశెనగ", "పల్లీలు", "పల్లి", "வேர்க்கடலை", "கடலை", "চিনাবাদাম", "মগফলি", "મગફળી", "સીંગ", "ಕಡಲೆಕಾಯಿ", "ನೆಲಗಡಲೆ", "നിലക്കടല", "ചിനാബാദാം", "ଚିନାବାଦାମ", "مونگ پھلی")
_add("allergen", "tree_nut", "nut", "nuts", "tree nut", "tree nuts", "almond", "almonds", "cashew", "cashews", "badam", "kaju", "बादाम", "काजू", "బాదం", "జీడిపప్పు", "பாதாம்", "முந்திரி", "বাদাম", "કાજુ", "બદામ", "ಬಾದಾಮಿ", "ഗോഡമ്പ്", "ബദാം", "ବାଦାମ", "بادام", "کاجو")
_add("allergen", "soy", "soy", "soya", "soybean", "tofu", "सोया", "సోయా", "சோயா", "সয়া", "સોયા", "ಸೋಯಾ", "സോയ", "ସୋୟା", "سویا")
_add("allergen", "sesame", "sesame", "til", "gingelly", "तिल", "तीळ", "నువ్వులు", "எள்", "তিল", "તલ", "ಎಳ್ಳು", "എള്ള്", "ରାଶି", "تل")
# ingredient groups
_add("ingredients", DAL, "dal", "daal", "dhal", "lentil", "lentils", "pappu", "paruppu", "parippu", "दाल", "डाळ", "పప్పు", "பருப்பு", "ডাল", "દાળ", "ಬೇಳೆ", "പരിപ്പ്", "ଡାଲି", "دال",
     "దాల్", "டால்", "ದಾಲ್", "ദാൽ", "ଡାଲ୍", "ડાલ")
_add("ingredients", PULSES, "pulses", "legumes", "beans and lentils")
_add("ingredients", {"toor_dal"}, "toor", "tur", "arhar", "toor dal", "अरहर", "तूर", "కందిపప్పు", "துவரம் பருப்பு")
_add("ingredients", {"lentil"}, "masoor", "मसूर", "మసూర్")
_add("ingredients", {"mung", "mung_sprout"}, "moong", "mung", "green gram", "मूंग", "పెసలు", "పెసరపప్పు", "பாசிப்பருப்பு", "মুগ", "મગ")
_add("ingredients", {"urad_raw"}, "urad", "black gram", "उड़द", "उडद", "మినప్పప్పు", "உளுந்து")
_add("ingredients", {"chickpea", "besan"}, "chickpea", "chickpeas", "chana", "chole", "chana dal", "chhole", "चना", "छोले", "శనగలు", "கொண்டைக்கடலை", "ছোলা", "ચણા")
_add("ingredients", {"besan"}, "besan", "gram flour", "बेसन", "శనగపిండి")
_add("ingredients", {"rajma"}, "rajma", "kidney bean", "kidney beans", "राजमा")
_add("ingredients", {"yogurt"}, "curd", "curds", "yogurt", "yoghurt", "dahi", "buttermilk", "chaas", "lassi", "raita", "दही", "छाछ", "ताक", "పెరుగు", "మజ్జిగ", "தயிர்", "மோர்", "দই", "ঘোল", "દહીં", "છાશ", "ಮೊಸರು", "ಮಜ್ಜಿಗೆ", "തൈര്", "മോര്", "ଦହି", "دہی", "لسی")
_add("ingredients", {"paneer"}, "paneer", "cottage cheese", "पनीर", "పనీర్", "பனீர்", "পনির", "પનીર", "ಪನೀರ್", "പനീർ", "ପନିର", "پنیر")
_add("ingredients", {"ghee"}, "ghee", "घी", "తుప్పు", "నెయ్యి", "நெய்", "ঘি", "ઘી", "ತುಪ್ಪ", "നെയ്യ്", "ଘିଅ", "گھی")
_add("ingredients", {"chicken"}, "chicken", "meat", "murgi", "murga", "चिकन", "मुर्गा", "चिकन", "కోడి", "చికెన్", "கோழி", "சிக்கன்", "মুরগি", "ચિકન", "ಕೋಳಿ", "ಚಿಕನ್", "കോഴി", "ചിക്കൻ", "କୁକୁଡ଼ା", "مرغی", "چکن", "گوشت")
_add("ingredients", {"rice", "rice_raw", "poha", "brown_rice"}, "rice", "chawal", "bhaat", "chawal", "चावल", "भात", "तांदूळ", "బియ్యం", "అన్నం", "அரிசி", "சோறு", "চাল", "ভাত", "ચોખા", "ભાત", "ಅಕ್ಕಿ", "ಅನ್ನ", "അരി", "ചോറ്", "ଚାଉଳ", "ଭାତ", "چاول")
_add("ingredients", {"roti", "wheat_flour", "bread"}, "roti", "chapati", "chapathi", "phulka", "paratha", "रोटी", "चपाती", "पोळी", "చపాతీ", "రొట్టె", "சப்பாத்தி", "রুটি", "રોટલી", "ಚಪಾತಿ", "ചപ്പാത്തി", "ରୁଟି", "روٹی")
_add("ingredients", {"bread"}, "bread", "toast", "pav", "ब्रेड", "బ్రెడ్")
_add("ingredients", {"semolina"}, "semolina", "rava", "rawa", "sooji", "suji", "रवा", "सूजी", "రవ్వ", "ரவை", "সুজি", "રવો", "ರವೆ", "റവ", "ସୁଜି", "سوجی")
_add("ingredients", {"oats"}, "oats", "oatmeal", "ओट्स")
_add("ingredients", {"millet"}, "millet", "millets", "ragi", "jowar", "bajra", "बाजरा", "ज्वार", "रागी", "రాగి", "జొన్న", "கேழ்வரகு", "சிறுதானியம்")
_add("ingredients", {"onion"}, "onion", "onions", "pyaz", "pyaaz", "kanda", "प्याज", "प्याज़", "कांदा", "ఉల్లిపాయ", "ఉల్లి", "வெங்காயம்", "পেঁয়াজ", "ડુંગળી", "કાંદા", "ಈರುಳ್ಳಿ", "ഉള്ളി", "സവാള", "ପିଆଜ", "پیاز")
_add("ingredients", {"garlic"}, "garlic", "lahsun", "lehsun", "लहसुन", "लसूण", "వెల్లుల్లి", "பூண்டு", "রসুন", "લસણ", "ಬೆಳ್ಳುಳ್ಳಿ", "വെളുത്തുള്ളി", "ରସୁଣ", "لہسن")
_add("ingredients", {"ginger"}, "ginger", "adrak", "अदरक", "आले", "అల్లం", "இஞ்சி", "আদা", "આદુ", "ಶುಂಠಿ", "ഇഞ്ചി", "ଅଦା", "ادرک")
_add("ingredients", {"tomato"}, "tomato", "tomatoes", "tamatar", "टमाटर", "टोमॅटो", "టమాటా", "టమాట", "தக்காளி", "টমেটো", "ટામેટા", "ಟೊಮೆಟೊ", "ಟೊಮ್ಯಾಟೊ", "തക്കാളി", "ଟମାଟୋ", "ٹماٹر")
_add("ingredients", {"potato"}, "potato", "potatoes", "aloo", "alu", "batata", "आलू", "बटाटा", "బంగాళాదుంప", "ఆలు", "உருளைக்கிழங்கு", "আলু", "બટાકા", "ಆಲೂಗಡ್ಡೆ", "ഉരുളക്കിഴങ്ങ്", "ଆଳୁ", "آلو")
_add("ingredients", {"eggplant"}, "brinjal", "eggplant", "aubergine", "baingan", "vangi", "बैंगन", "वांगी", "వంకాయ", "கத்தரிக்காய்", "বেগুন", "રીંગણ", "ಬದನೆ", "വഴുതന", "ବାଇଗଣ", "بینگن")
_add("ingredients", {"okra"}, "okra", "lady finger", "ladyfinger", "bhindi", "भिंडी", "भेंडी", "బెండకాయ", "வெண்டைக்காய்", "ঢেঁড়স", "ভিন্ডি", "ભીંડા", "ಬೆಂಡೆಕಾಯಿ", "വെണ്ടയ്ക്ക", "ଭେଣ୍ଡି", "بھنڈی")
_add("ingredients", {"mushroom"}, "mushroom", "mushrooms", "मशरूम", "పుట్టగొడుగులు", "காளான்", "মাশরুম", "ಅಣಬೆ", "കൂൺ", "ଛତୁ", "مشروم")
_add("ingredients", {"spinach"}, "spinach", "palak", "पालक", "పాలకూర", "பசலைக்கீரை", "পালং", "પાલક", "ಪಾಲಕ್", "ചീര", "ପାଳଙ୍ଗ", "پالک")
_add("ingredients", {"cauliflower"}, "cauliflower", "gobi", "phool gobi", "फूलगोभी", "गोभी", "కాలీఫ్లవర్", "காலிஃப்ளவர்", "ফুলকপি", "ફ્લાવર", "ಹೂಕೋಸು")
_add("ingredients", {"cabbage"}, "cabbage", "patta gobi", "पत्ता गोभी", "కోసు", "క్యాబేజీ", "முட்டைக்கோஸ்", "বাঁধাকপি", "કોબી", "ಎಲೆಕೋಸು", "കാബേജ്")
_add("ingredients", {"carrot"}, "carrot", "carrots", "gajar", "गाजर", "క్యారెట్", "கேரட்", "গাজর", "ગાજર", "ಗಜ್ಜರಿ", "കാരറ്റ്")
_add("ingredients", {"peas"}, "peas", "green peas", "matar", "mutter", "मटर", "वाटाणा", "బఠానీ", "பட்டாணி", "মটর", "વટાણા", "ಬಟಾಣಿ", "പട്ടാണി")
_add("ingredients", {"beans"}, "green beans", "french beans", "beans", "बीन्स", "బీన్స్")
_add("ingredients", {"cucumber"}, "cucumber", "kheera", "kakdi", "खीरा", "काकडी", "దోసకాయ", "வெள்ளரிக்காய்", "শসা", "કાકડી", "ಸೌತೆಕಾಯಿ", "വെള്ളരിക്ക")
_add("ingredients", {"gourd"}, "gourd", "bottle gourd", "lauki", "dudhi", "ghiya", "लौकी", "दुधी", "సొరకాయ", "சுரைக்காய்", "লাউ", "દૂધી", "ಸೋರೆಕಾಯಿ", "ചുരയ്ക്ക")
_add("ingredients", {"beetroot"}, "beetroot", "beet", "चुकंदर")
_add("ingredients", {"sweet_potato"}, "sweet potato", "shakarkandi", "शकरकंद", "చిలగడదుంప", "சர்க்கரைவள்ளி")
_add("ingredients", {"corn"}, "corn", "maize", "bhutta", "makka", "मक्का", "भुट्टा", "మొక్కజొన్న", "சோளம்")
_add("ingredients", {"coconut"}, "coconut", "nariyal", "नारियल", "కొబ్బరి", "தேங்காய்", "নারকেল", "નાળિયેર", "ತೆಂಗಿನಕಾಯಿ", "തേങ്ങ", "ନଡ଼ିଆ", "ناریل")
_add("ingredients", {"banana"}, "banana", "bananas", "kela", "केला", "केळी", "అరటి", "அரசு", "வாழைப்பழம்", "কলা", "કેળા", "ಬಾಳೆಹಣ್ಣು", "പഴം", "କଦଳୀ", "کیلا")
_add("ingredients", {"mango"}, "mango", "mangoes", "aam", "आम", "आंबा", "మామిడి", "மாம்பழம்", "আম", "કેરી", "ಮಾವು", "മാങ്ങ", "ଆମ୍ବ", "آم")
_add("ingredients", {"apple"}, "apple", "apples", "seb", "सेब", "ఆపిల్")
_add("ingredients", {"papaya"}, "papaya", "papita", "पपीता", "బొప్పాయి", "பப்பாளி")
_add("ingredients", {"guava"}, "guava", "amrood", "अमरूद", "జామ", "கொய்யா")
_add("ingredients", {"orange"}, "orange", "oranges", "santra", "संतरा", "నారింజ", "ஆரஞ்சு")
_add("ingredients", {"pomegranate"}, "pomegranate", "anar", "अनार", "దానిమ్మ", "மாதுளை")
_add("ingredients", {"sugar"}, "sugar", "चीनी", "शक्कर", "చక్కెర", "சர்க்கரை")
_add("ingredients", {"honey"}, "honey", "शहद", "తేనె", "தேன்")
# dish names
for _dish, _terms in {
    "poha": ("poha", "pohe", "avalakki", "aval", "अवल", "पोहा", "पोहे", "అటుకులు", "அவல்"), "upma": ("upma", "uppittu", "उपमा", "ఉప్మా", "உப்புமா"),
    "idli_sambar": ("idli", "idly", "इडली", "ఇడ్లీ", "இட்லி"), "masala_dosa": ("dosa", "dosai", "डोसा", "దోస", "தோசை"),
    "sambar_rice": ("sambar", "sambhar", "सांबर", "సాంబార్", "சாம்பார்"), "aloo_paratha_curd": ("paratha", "पराठा"), "moong_khichdi": ("khichdi", "खिचड़ी"),
    "millet_khichdi": ("khichdi",), "veg_pulao_raita": ("pulao", "pulav", "पुलाव"), "besan_chilla": ("chilla", "cheela"), "moong_chilla": ("chilla", "cheela"),
}.items():
    for _t in _terms:
        k = _t.lower()
        prev = _T.get(k)
        _T[k] = ("dishes", (prev[1] if prev and prev[0] == "dishes" else set()) | {_dish})

_NEGATIONS = {"no", "not", "dont", "don't", "avoid", "without", "allergic", "allergy", "to", "i", "am", "and", "or", "eat", "want", "like", "please"}
_SPLIT = re.compile(r"[,;/|\n]+|\s+(?:and|or|और|మరియు|மற்றும்|এবং|आणि|અને|ಮತ್ತು|ഒപ്പം|ଏବଂ|اور)\s+", re.I)


def _match_terms(text: str) -> set[tuple[str, object]]:
    """Whole-word matching (no substrings: 'peanuts' must not match 'pea' or 'nut')."""
    words = [w for w in re.split(r"[\s.()\-–—:+&!?\"']+", text.lower()) if w]
    hits = set()
    # multi-word terms first, then single words (also allowing a simple English plural)
    joined = " " + " ".join(words) + " "
    for term, val in _T.items():
        if " " in term and f" {term} " in joined:
            hits.add((term, val[0]))
    for w in words:
        if w in _NEGATIONS:
            continue
        for cand in (w, w[:-1] if w.endswith("s") else None, w[:-2] if w.endswith("es") else None):
            if cand and cand in _T:
                hits.add((cand, _T[cand][0]))
                break
    return hits


def map_allergies(items: list[str]) -> tuple[set[str], set[str], list[str], set[str], list[str]]:
    """Returns (allergen keys, ingredient keys, unmatched entries, dish keys, matched terms)."""
    allergens: set[str] = set()
    ingredients: set[str] = set()
    dishes: set[str] = set()
    unmapped: list[str] = []
    matched: list[str] = []
    for raw in items:
        for part in [p.strip() for p in _SPLIT.split(raw) if p and p.strip()]:
            hits = _match_terms(part)
            if not hits:
                unmapped.append(part)
                continue
            for term, kind in hits:
                target = _T[term][1]
                if kind == "allergen":
                    allergens.add(target)
                elif kind == "ingredients":
                    ingredients |= set(target)
                else:
                    dishes |= set(target)
            matched.append(part)
    return allergens, ingredients, unmapped, dishes, matched


class DietError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@lru_cache
def foods() -> dict:
    return json.loads(DATA.read_text())


def compute_targets(*, age: int, sex: str | None, height_cm: float, weight_kg: float, activity: str, goal: str) -> dict:
    s = 5 if sex == "male" else -161 if sex == "female" else -78
    bmr = 10 * weight_kg + 6.25 * height_cm - 5 * age + s
    tdee = bmr * ACTIVITY[activity]
    if goal == "lose":
        kcal = tdee - min(500, 0.2 * tdee)
    elif goal == "gain":
        kcal = tdee + 300
    else:
        kcal = tdee
    floor = 1500 if sex == "male" else 1200 if sex == "female" else 1350
    floored = kcal < floor
    kcal = max(kcal, floor)
    protein = max((1.0 if goal == "lose" else 0.83) * weight_kg, 0.10 * kcal / 4)
    fat = 0.25 * kcal / 9
    carbs = max(0.0, (kcal - protein * 4 - fat * 9) / 4)
    return {
        "bmr": round(bmr),
        "tdee": round(tdee),
        "kcal": round(kcal),
        "protein_g": round(protein),
        "fat_g": round(fat),
        "carbs_g": round(carbs),
        "fiber_g": round(14 * kcal / 1000),
        "floor_applied": floored,
        "sex_assumed_average": sex not in ("male", "female"),
    }


def eligible_dishes(diet: str | None, allergies: list[str], disliked: set[str]) -> tuple[dict, list[str]]:
    f = foods()
    allowed = DIET_ALLOWED.get(diet or "other", DIET_ALLOWED["other"])
    bad_allergens, bad_ingredients, unmapped, bad_dishes, _ = map_allergies(allergies)
    out = {}
    for key, d in f["dishes"].items():
        if key in disliked:
            continue
        if not set(d["contains"]) <= allowed:
            continue
        if diet == "jain" and d["jain"] == "no":
            continue
        if set(d["allergens"]) & bad_allergens or set(d["ingredients"]) & bad_ingredients or key in bad_dishes:
            continue
        out[key] = d
    return out, unmapped


def _dish_nutrients(key: str, jain: bool) -> tuple[dict, list[str]]:
    f = foods()
    d = f["dishes"][key]
    if not (jain and d["jain"] == "omit_minor"):
        return d["per_serving"], []
    total = {k: 0.0 for k in d["per_serving"]}
    for ing, g in d["ingredients"].items():
        if ing in d["jain_omit"]:
            continue
        for k, v in f["ingredients"][ing]["per_100g"].items():
            total[k] += v * g / 100
    return {k: round(v, 1) for k, v in total.items()}, d["jain_omit"]


def _quarter(x: float, lo: float, hi: float) -> float:
    return min(hi, max(lo, round(x * 4) / 4))


def generate_plan(*, targets: dict, diet: str | None, allergies: list[str], disliked: set[str], favorites: set[str], days: int, seed: int) -> dict:
    dishes, unmapped = eligible_dishes(diet, allergies, disliked)
    matched = map_allergies(allergies)[4]
    by_slot = {s: [k for k, d in dishes.items() if s in d["slots"]] for s in SLOT_SHARE}
    empty = [s for s, ks in by_slot.items() if not ks]
    if empty:
        raise DietError("not_enough_dishes")
    rng = random.Random(seed)
    jain = diet == "jain"
    recent: dict[str, list[str]] = {s: [] for s in SLOT_SHARE}
    out_days = []
    for day in range(1, days + 1):
        meals, totals = [], {k: 0.0 for k in ("kcal", "protein_g", "fat_g", "carbs_g", "fiber_g", "sugar_g", "sodium_mg", "calcium_mg", "iron_mg")}
        for slot, share in SLOT_SHARE.items():
            want = targets["kcal"] * share
            # Only dishes whose portion can reach this meal's energy share within 0.5–2 servings.
            feasible = [k for k in by_slot[slot] if 0.5 * _dish_nutrients(k, jain)[0]["kcal"] <= 1.25 * want <= 2.5 * _dish_nutrients(k, jain)[0]["kcal"]] or by_slot[slot]
            pool = [k for k in feasible if k not in recent[slot][-2:]] or feasible
            weights = [3.0 if k in favorites else 1.0 for k in pool]
            key = rng.choices(pool, weights=weights, k=1)[0]
            recent[slot].append(key)
            per, omit = _dish_nutrients(key, jain)
            servings = _quarter(want / per["kcal"], 0.5, 2.0) if per["kcal"] else 1.0
            meals.append({"slot": slot, "dish": key, "servings": servings, "per": per, "omit": omit})
        # Day-level balancing: scale the main meals so the day lands near the energy target.
        total_kcal = sum(m["per"]["kcal"] * m["servings"] for m in meals)
        gap = targets["kcal"] - total_kcal
        mains = [m for m in meals if m["slot"] in ("lunch", "dinner")]
        main_kcal = sum(m["per"]["kcal"] * m["servings"] for m in mains)
        if main_kcal and abs(gap) > 0.08 * targets["kcal"]:
            factor = (main_kcal + gap) / main_kcal
            for m in mains:
                m["servings"] = _quarter(m["servings"] * factor, 0.5, 2.5)
        # High energy targets: add extra snack items until within 8% (at most 3).
        for _ in range(3):
            gap = targets["kcal"] - sum(m["per"]["kcal"] * m["servings"] for m in meals)
            if gap <= 0.08 * targets["kcal"]:
                break
            used = {m["dish"] for m in meals}
            options = [k for k in by_slot["snack"] if k not in used] or by_slot["snack"]
            key = min(options, key=lambda k: abs(_dish_nutrients(k, jain)[0]["kcal"] * 2 - gap) if _dish_nutrients(k, jain)[0]["kcal"] * 2 > gap else abs(_dish_nutrients(k, jain)[0]["kcal"] * 2 - gap) * 1.5)
            per, omit = _dish_nutrients(key, jain)
            meals.append({"slot": "snack", "dish": key, "servings": _quarter(gap / per["kcal"], 0.5, 2.0), "per": per, "omit": omit, "extra": True})
        for m in meals:
            per = m.pop("per")
            m["nutrients"] = {k: round(v * m["servings"], 1) for k, v in per.items()}
            for k in totals:
                totals[k] += m["nutrients"].get(k, 0)
        out_days.append({"day": day, "meals": meals, "totals": {k: round(v, 1) for k, v in totals.items()}})
    notes = []
    off = [d["day"] for d in out_days if abs(d["totals"]["kcal"] / targets["kcal"] - 1) > 0.10]
    if off:
        notes.append({"code": "days_off_target", "days": off})
    if matched:
        notes.append({"code": "excluded_foods", "items": matched})
    if unmapped:
        notes.append({"code": "allergies_unmapped", "items": unmapped})
    if targets.get("floor_applied"):
        notes.append({"code": "kcal_floor_applied"})
    if targets.get("sex_assumed_average"):
        notes.append({"code": "sex_assumed_average"})
    return {"days": out_days, "notes": notes, "source": foods()["source"]}


def catalogue() -> dict:
    f = foods()
    return {
        "source": f["source"],
        "dishes": {k: {kk: d[kk] for kk in ("slots", "per_serving", "allergens", "contains", "serving_grams", "ingredients")} for k, d in f["dishes"].items()},
        "ingredients": {k: {"fdc_id": v["fdc_id"], "usda_description": v["usda_description"], **({"proxy_note": v["proxy_note"]} if "proxy_note" in v else {})} for k, v in f["ingredients"].items()},
    }
