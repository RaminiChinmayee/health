"""Build the diet planner's food database.

Nutrient values come from USDA FoodData Central — SR Legacy (April 2018 release), public domain.
Dishes are typical home recipes defined here as ingredient weights per serving; each dish's
nutrition is *computed* from its ingredients. Recipe weights are estimates of common home
portions, so dish values are approximate — the app says so.

Output: backend/app/data/foods.json
"""
import json
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from common import RAW, sha256

SR = RAW / "sr_legacy" / "FoodData_Central_sr_legacy_food_csv_2018-04"
OUT = Path(__file__).resolve().parent.parent / "backend" / "app" / "data" / "foods.json"

NUTRIENTS = {  # FDC nutrient id → key (per 100 g)
    1008: "kcal", 1003: "protein_g", 1004: "fat_g", 1005: "carbs_g", 1079: "fiber_g",
    2000: "sugar_g", 1093: "sodium_mg", 1087: "calcium_mg", 1089: "iron_mg",
}

# key: (fdc_id, diet, allergens, jain_excluded, proxy_note)
# diet: vegan | dairy | egg | meat | fish   (dairy = lacto-vegetarian)
ING = {
    "rice": (168878, "vegan", [], False, None),
    "rice_raw": (168877, "vegan", [], False, None),
    "poha": (168877, "vegan", [], False, "Flattened rice (poha) approximated by raw white rice, same weight"),
    "brown_rice": (169704, "vegan", [], False, None),
    "roti": (174075, "vegan", ["gluten"], False, None),
    "wheat_flour": (168893, "vegan", ["gluten"], False, None),
    "bread": (172688, "vegan", ["gluten"], False, None),
    "semolina": (169715, "vegan", ["gluten"], False, None),
    "oats": (173904, "vegan", [], False, None),
    "millet": (168871, "vegan", [], False, None),
    "lentil": (172421, "vegan", [], False, None),
    "toor_dal": (172437, "vegan", [], False, None),
    "chickpea": (173757, "vegan", [], False, None),
    "rajma": (175194, "vegan", [], False, None),
    "mung_sprout": (169957, "vegan", [], False, None),
    "mung": (174257, "vegan", [], False, None),
    "urad_raw": (174259, "vegan", [], False, None),
    "besan": (174288, "vegan", [], False, None),
    "paneer": (170845, "dairy", ["dairy"], False, "Paneer approximated by whole-milk mozzarella (similar protein/fat); USDA SR has no paneer entry"),
    "yogurt": (171284, "dairy", ["dairy"], False, None),
    "milk": (171267, "dairy", ["dairy"], False, None),
    "ghee": (173412, "dairy", ["dairy"], False, None),
    "egg": (173424, "egg", ["egg"], False, None),
    "chicken": (171477, "meat", [], False, None),
    "fish": (175177, "fish", ["fish"], False, None),
    "tofu": (172475, "vegan", ["soy"], False, None),
    "potato": (170440, "vegan", [], True, None),
    "onion": (170000, "vegan", [], True, None),
    "garlic": (169230, "vegan", [], True, None),
    "ginger": (169231, "vegan", [], True, None),
    "tomato": (170457, "vegan", [], False, None),
    "spinach": (168463, "vegan", [], False, None),
    "cauliflower": (170397, "vegan", [], False, None),
    "cabbage": (169975, "vegan", [], False, None),
    "carrot": (170393, "vegan", [], True, None),
    "peas": (170017, "vegan", [], False, None),
    "okra": (169261, "vegan", [], False, None),
    "eggplant": (169229, "vegan", [], False, None),
    "gourd": (169233, "vegan", [], False, None),
    "cucumber": (168409, "vegan", [], False, None),
    "beans": (169141, "vegan", [], False, None),
    "mushroom": (169252, "vegan", [], False, None),
    "beetroot": (169146, "vegan", [], True, None),
    "sweet_potato": (168484, "vegan", [], True, None),
    "corn": (169999, "vegan", [], False, None),
    "banana": (173944, "vegan", [], False, None),
    "apple": (171688, "vegan", [], False, None),
    "papaya": (169926, "vegan", [], False, None),
    "guava": (173044, "vegan", [], False, None),
    "orange": (169097, "vegan", [], False, None),
    "mango": (169910, "vegan", [], False, None),
    "pomegranate": (169134, "vegan", [], False, None),
    "peanut": (173806, "vegan", ["peanut"], False, None),
    "peanut_butter": (172470, "vegan", ["peanut"], False, None),
    "almond": (170567, "vegan", ["tree_nut"], False, None),
    "sesame": (170150, "vegan", ["sesame"], False, None),
    "coconut": (170169, "vegan", ["tree_nut"], False, None),
    "oil": (171017, "vegan", [], False, None),
    "sugar": (169655, "vegan", [], False, None),
    "honey": (169640, "vegan", [], False, None),
    "lemon": (167747, "vegan", [], False, None),
    "chili": (170497, "vegan", [], False, None),
    "coriander": (169997, "vegan", [], False, None),
    "spices": (170924, "vegan", [], False, None),
}

# key: (slots, ingredients{key: grams per serving})
DISHES = {
    # ------------------------------------------------------------ breakfast
    "poha": (["breakfast"], {"poha": 50, "peanut": 10, "onion": 30, "peas": 20, "oil": 7, "lemon": 5, "coriander": 3, "chili": 3}),
    "upma": (["breakfast"], {"semolina": 50, "onion": 30, "carrot": 20, "peas": 20, "oil": 7, "chili": 3}),
    "idli_sambar": (["breakfast"], {"rice_raw": 45, "urad_raw": 15, "toor_dal": 60, "tomato": 30, "gourd": 30, "onion": 20, "oil": 3, "spices": 2}),
    "masala_dosa": (["breakfast"], {"rice_raw": 50, "urad_raw": 15, "oil": 8, "potato": 80, "onion": 20}),
    "oats_porridge": (["breakfast"], {"oats": 40, "milk": 200, "banana": 60, "almond": 8}),
    "besan_chilla": (["breakfast"], {"besan": 50, "onion": 25, "tomato": 25, "oil": 7, "coriander": 3, "yogurt": 100}),
    "moong_chilla": (["breakfast"], {"mung": 120, "onion": 20, "oil": 6, "coriander": 3, "chili": 2}),
    "aloo_paratha_curd": (["breakfast"], {"wheat_flour": 60, "potato": 60, "oil": 8, "yogurt": 100}),
    "egg_bhurji_toast": (["breakfast"], {"egg": 100, "onion": 20, "tomato": 20, "oil": 5, "bread": 60}),
    "boiled_eggs_fruit": (["breakfast"], {"egg": 100, "apple": 150, "bread": 30}),
    "sprouts_salad": (["breakfast", "snack"], {"mung_sprout": 100, "onion": 20, "tomato": 30, "cucumber": 30, "lemon": 5}),
    "millet_porridge": (["breakfast"], {"millet": 150, "milk": 100, "sugar": 5, "almond": 5}),
    "tofu_scramble_toast": (["breakfast"], {"tofu": 120, "onion": 20, "tomato": 30, "oil": 5, "bread": 60}),
    "peanut_butter_toast": (["breakfast"], {"bread": 60, "peanut_butter": 20, "banana": 100}),
    # ------------------------------------------------------------ lunch / dinner
    "dal_rice": (["lunch", "dinner"], {"toor_dal": 150, "rice": 180, "oil": 5, "tomato": 20, "onion": 20, "spices": 2}),
    "rajma_rice": (["lunch", "dinner"], {"rajma": 150, "rice": 180, "onion": 30, "tomato": 40, "oil": 7}),
    "chole_roti": (["lunch", "dinner"], {"chickpea": 150, "roti": 80, "onion": 30, "tomato": 40, "oil": 7}),
    "palak_paneer_roti": (["lunch", "dinner"], {"spinach": 150, "paneer": 80, "onion": 20, "tomato": 20, "oil": 7, "roti": 80}),
    "veg_pulao_raita": (["lunch", "dinner"], {"rice": 180, "peas": 30, "carrot": 30, "beans": 30, "oil": 7, "yogurt": 100, "cucumber": 30}),
    "mixed_veg_dal_roti": (["lunch", "dinner"], {"lentil": 150, "roti": 80, "cauliflower": 50, "carrot": 30, "peas": 30, "oil": 7}),
    "sambar_rice": (["lunch", "dinner"], {"toor_dal": 100, "rice": 180, "gourd": 50, "okra": 40, "tomato": 30, "oil": 5, "spices": 2}),
    "curd_rice": (["lunch", "dinner"], {"rice": 150, "yogurt": 150, "cucumber": 30, "oil": 2}),
    "moong_khichdi": (["lunch", "dinner"], {"rice": 120, "mung": 100, "ghee": 5, "carrot": 30, "peas": 30}),
    "bhindi_dal_roti": (["lunch", "dinner"], {"okra": 120, "oil": 7, "onion": 20, "lentil": 120, "roti": 80}),
    "aloo_gobi_roti": (["lunch", "dinner"], {"potato": 100, "cauliflower": 100, "oil": 8, "onion": 20, "tomato": 20, "roti": 80, "yogurt": 100}),
    "baingan_bharta_roti": (["lunch", "dinner"], {"eggplant": 150, "onion": 30, "tomato": 40, "oil": 7, "roti": 80, "lentil": 100}),
    "chicken_curry_rice": (["lunch", "dinner"], {"chicken": 120, "onion": 40, "tomato": 40, "oil": 8, "yogurt": 30, "rice": 180}),
    "fish_curry_rice": (["lunch", "dinner"], {"fish": 120, "coconut": 20, "tomato": 30, "onion": 30, "oil": 7, "rice": 180}),
    "egg_curry_roti": (["lunch", "dinner"], {"egg": 100, "onion": 40, "tomato": 40, "oil": 7, "roti": 80}),
    "tofu_peas_curry_rice": (["lunch", "dinner"], {"tofu": 120, "peas": 50, "tomato": 40, "onion": 30, "oil": 7, "rice": 150}),
    "grilled_chicken_salad": (["lunch", "dinner"], {"chicken": 120, "cucumber": 50, "tomato": 50, "cabbage": 50, "lemon": 10, "oil": 5, "bread": 30}),
    "rajma_brown_rice": (["lunch", "dinner"], {"rajma": 120, "brown_rice": 150, "onion": 30, "tomato": 40, "oil": 6}),
    "millet_khichdi": (["lunch", "dinner"], {"millet": 150, "mung": 80, "ghee": 5, "carrot": 30, "beans": 30}),
    "veg_soup_toast": (["dinner"], {"carrot": 50, "cabbage": 50, "beans": 50, "tomato": 50, "mung": 60, "bread": 30, "oil": 3}),
    "paneer_bhurji_roti": (["lunch", "dinner"], {"paneer": 80, "onion": 30, "tomato": 30, "peas": 30, "oil": 5, "roti": 80}),
    "mushroom_matar_roti": (["lunch", "dinner"], {"mushroom": 120, "peas": 60, "onion": 30, "tomato": 30, "oil": 7, "roti": 80}),
    "lauki_chana_dal_rice": (["lunch", "dinner"], {"gourd": 150, "chickpea": 80, "tomato": 30, "oil": 5, "rice": 150}),
    # ------------------------------------------------------------ snacks
    "fruit_bowl": (["snack"], {"papaya": 100, "apple": 75, "pomegranate": 50}),
    "banana": (["snack"], {"banana": 120}),
    "guava": (["snack"], {"guava": 150}),
    "orange": (["snack"], {"orange": 150}),
    "roasted_peanuts": (["snack"], {"peanut": 25}),
    "almonds": (["snack"], {"almond": 20}),
    "buttermilk": (["snack"], {"yogurt": 100}),
    "boiled_corn": (["snack"], {"corn": 100, "lemon": 5}),
    "sweet_potato_chaat": (["snack"], {"sweet_potato": 120, "lemon": 5}),
    "yogurt_fruit": (["snack"], {"yogurt": 150, "banana": 50}),
    "mango": (["snack"], {"mango": 150}),
    "sesame_peanut_mix": (["snack"], {"peanut": 15, "sesame": 10}),
}

DIET_RANK = {"vegan": 0, "dairy": 1, "egg": 2, "fish": 3, "meat": 3}


def main():
    nut = pd.read_csv(SR / "food_nutrient.csv", usecols=["fdc_id", "nutrient_id", "amount"])
    food = pd.read_csv(SR / "food.csv", usecols=["fdc_id", "description"]).set_index("fdc_id")["description"]
    ids = {v[0] for v in ING.values()}
    nut = nut[nut.fdc_id.isin(ids) & nut.nutrient_id.isin(NUTRIENTS)]
    table = nut.pivot_table(index="fdc_id", columns="nutrient_id", values="amount", aggfunc="first").rename(columns=NUTRIENTS)

    ingredients = {}
    for key, (fid, diet, allergens, jain_x, proxy) in ING.items():
        assert fid in table.index, f"{key}: fdc {fid} has no nutrients"
        row = table.loc[fid]
        ingredients[key] = {
            "fdc_id": int(fid),
            "usda_description": food[fid],
            "per_100g": {k: (round(float(row[k]), 2) if k in row and pd.notna(row[k]) else 0.0) for k in NUTRIENTS.values()},
            "diet": diet,
            "allergens": allergens,
            "jain_excluded": jain_x,
            **({"proxy_note": proxy} if proxy else {}),
        }

    dishes = {}
    for key, (slots, recipe) in DISHES.items():
        total = {k: 0.0 for k in NUTRIENTS.values()}
        for ing, g in recipe.items():
            for k, v in ingredients[ing]["per_100g"].items():
                total[k] += v * g / 100
        diets = {ingredients[i]["diet"] for i in recipe}
        grams = sum(recipe.values())
        jain_grams = sum(g for i, g in recipe.items() if ingredients[i]["jain_excluded"])
        dishes[key] = {
            "slots": slots,
            "ingredients": recipe,
            "serving_grams": grams,
            "per_serving": {k: round(v, 1) for k, v in total.items()},
            # Strictest diet that can eat it: vegan < dairy < egg < fish/meat
            "contains": sorted(diets),
            "allergens": sorted({a for i in recipe for a in ingredients[i]["allergens"]}),
            # Jain-friendly if excluded ingredients are minor (≤15% of weight) and can be left out.
            "jain": "ok" if jain_grams == 0 else ("omit_minor" if jain_grams / grams <= 0.15 else "no"),
            "jain_omit": [i for i in recipe if ingredients[i]["jain_excluded"]],
        }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({
        "source": {
            "name": "USDA FoodData Central — SR Legacy (April 2018)",
            "url": "https://fdc.nal.usda.gov/",
            "license": "Public domain (CC0)",
            "file_sha256": sha256(RAW / "sr_legacy.zip"),
            "built_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "note": "Dish nutrition is computed from estimated home-recipe ingredient weights; actual values vary with recipe and portion. Sodium excludes added salt.",
        },
        "ingredients": ingredients,
        "dishes": dishes,
    }, indent=1, ensure_ascii=False))
    print(f"{len(ingredients)} ingredients, {len(dishes)} dishes → {OUT}")
    for k in ("poha", "dal_rice", "chicken_curry_rice", "almonds"):
        print(k, dishes[k]["per_serving"])


if __name__ == "__main__":
    main()
