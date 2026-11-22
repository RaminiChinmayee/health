from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.services import diet as diet_svc
from app.services import places
from tests.conftest import auth, register, verified_login

PROFILE = {"height_cm": 160, "weight_kg": 60, "activity_level": "moderate", "dietary_preference": "vegetarian", "food_allergies": ["Peanuts"], "health_conditions": []}


def _setup(client, mailbox, **hp):
    t = verified_login(client, mailbox)
    client.put("/api/profile/health", headers=auth(t), json={**PROFILE, **hp})
    return t


def test_targets_formula():
    # Mifflin–St Jeor: woman, 30y, 160cm, 60kg → BMR = 600 + 1000 − 150 − 161 = 1289
    t = diet_svc.compute_targets(age=30, sex="female", height_cm=160, weight_kg=60, activity="moderate", goal="maintain")
    assert t["bmr"] == 1289 and t["tdee"] == round(1289 * 1.55)
    lose = diet_svc.compute_targets(age=30, sex="female", height_cm=160, weight_kg=60, activity="sedentary", goal="lose")
    assert lose["kcal"] >= 1200 and lose["protein_g"] >= 60


def test_plan_requires_complete_profile(client, mailbox):
    t = verified_login(client, mailbox)
    meta = client.get("/api/diet/meta", headers=auth(t)).json()
    assert set(meta["missing"]) == {"height_cm", "weight_kg", "activity_level"} and meta["targets"] is None
    r = client.post("/api/diet/plans", headers=auth(t), json={"goal": "maintain"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "health_profile_incomplete"


def test_plan_respects_diet_allergies_and_targets(client, mailbox):
    t = _setup(client, mailbox)
    r = client.post("/api/diet/plans", headers=auth(t), json={"goal": "maintain", "days": 7})
    assert r.status_code == 201, r.text
    plan = r.json()
    dishes = diet_svc.foods()["dishes"]
    kcal = plan["targets"]["kcal"]
    assert len(plan["plan"]["days"]) == 7
    for day in plan["plan"]["days"]:
        assert [m["slot"] for m in day["meals"]] == ["breakfast", "lunch", "snack", "dinner"]
        for m in day["meals"]:
            d = dishes[m["dish"]]
            assert set(d["contains"]) <= {"vegan", "dairy"}, m["dish"]
            assert "peanut" not in d["allergens"], m["dish"]
        assert 0.75 * kcal <= day["totals"]["kcal"] <= 1.25 * kcal
    assert client.get("/api/history/diets", headers=auth(t)).json()["total"] == 1


def test_jain_plan_omits_root_vegetables(client, mailbox):
    t = _setup(client, mailbox, dietary_preference="jain", food_allergies=[])
    plan = client.post("/api/diet/plans", headers=auth(t), json={"days": 7}).json()
    dishes = diet_svc.foods()["dishes"]
    for day in plan["plan"]["days"]:
        for m in day["meals"]:
            assert dishes[m["dish"]]["jain"] != "no"
            assert set(m["omit"]) == set(dishes[m["dish"]]["jain_omit"] if dishes[m["dish"]]["jain"] == "omit_minor" else [])


def test_safety_refusals(client, mailbox):
    t = _setup(client, mailbox, weight_kg=44)  # BMI 17.2
    r = client.post("/api/diet/plans", headers=auth(t), json={"goal": "lose"})
    assert r.json()["detail"]["code"] == "weight_loss_not_advised"
    assert client.post("/api/diet/plans", headers=auth(t), json={"goal": "gain"}).status_code == 201

    minor = TestClient(app)
    register(minor, email="teen@example.com", date_of_birth="2012-01-01")
    tok = mailbox.last_link("teen@example.com", "/verify-email")
    minor.post("/api/auth/verify-email", json={"token": tok})
    tt = minor.post("/api/auth/login", json={"email": "teen@example.com", "password": "Correct-Horse-42-battery"}).json()["access_token"]
    minor.put("/api/profile/health", headers=auth(tt), json=PROFILE)
    assert minor.post("/api/diet/plans", headers=auth(tt), json={}).json()["detail"]["code"] == "diet_minor_not_supported"


def test_disliked_dishes_are_avoided(client, mailbox):
    t = _setup(client, mailbox, dietary_preference="vegetarian", food_allergies=[])
    eligible, _ = diet_svc.eligible_dishes("vegetarian", [], set())
    breakfasts = [k for k, d in eligible.items() if "breakfast" in d["slots"]]
    for k in breakfasts[:-1]:  # dislike all but one breakfast
        assert client.put(f"/api/diet/feedback/{k}", headers=auth(t), json={"rating": -1}).status_code == 200
    plan = client.post("/api/diet/plans", headers=auth(t), json={"days": 7}).json()
    assert {d["meals"][0]["dish"] for d in plan["plan"]["days"]} == {breakfasts[-1]}
    assert client.get("/api/diet/feedback", headers=auth(t)).json()[breakfasts[0]]["rating"] == -1


def test_meal_logs_summary_and_isolation(client, mailbox):
    t = _setup(client, mailbox)
    plan = client.post("/api/diet/plans", headers=auth(t), json={"days": 1}).json()
    today = date.today().isoformat()
    log = client.post("/api/diet/logs", headers=auth(t), json={"log_date": today, "slot": "lunch", "dish_key": "dal_rice", "servings": 1.5, "plan_id": plan["id"]})
    assert log.status_code == 201 and log.json()["nutrients"]["kcal"] > 600
    s = client.get(f"/api/diet/summary?week_start={today}", headers=auth(t)).json()
    assert s["days"][today]["meals"] == 1 and s["days_logged"] == 1 and s["targets"]["kcal"]

    other = TestClient(app)
    tb = verified_login(other, mailbox, email="b@example.com")
    # Can't attach logs to, read, favourite, or delete someone else's plan/log.
    assert other.post("/api/diet/logs", headers=auth(tb), json={"log_date": today, "slot": "lunch", "dish_key": "dal_rice", "servings": 1, "plan_id": plan["id"]}).status_code == 404
    assert other.get(f"/api/diet/plans/{plan['id']}", headers=auth(tb)).status_code == 404
    assert other.patch(f"/api/diet/plans/{plan['id']}", headers=auth(tb), json={"is_favorite": True}).status_code == 404
    assert other.delete(f"/api/history/{log.json()['id']}", headers=auth(tb)).status_code == 404
    assert client.delete(f"/api/history/{log.json()['id']}", headers=auth(t)).status_code == 204


# ------------------------------------------------------------------ hospitals
FAKE = [
    {"type": "node", "id": 1, "lat": 19.045, "lon": 72.862, "tags": {"amenity": "hospital", "name": "Far Hospital", "emergency": "yes", "phone": "+91 22 0000 0000"}},
    {"type": "way", "id": 2, "center": {"lat": 19.0410, "lon": 72.8620}, "tags": {"amenity": "clinic", "name": "Near Clinic", "addr:street": "MG Road", "addr:city": "Mumbai"}},
    {"type": "node", "id": 3, "lat": 19.5, "lon": 73.5, "tags": {"amenity": "hospital", "name": "Way Outside Radius"}},
    {"type": "node", "id": 4, "tags": {"amenity": "hospital"}},  # no coordinates → skipped
]


def test_hospitals_sorted_and_coordinates_rounded(client, mailbox, monkeypatch):
    sent = []
    monkeypatch.setattr(places, "local_index", lambda: None)
    monkeypatch.setattr(places, "_fetch_overpass", lambda q: (sent.append(q), FAKE)[1])
    places._cache.clear()
    t = verified_login(client, mailbox)
    r = client.get("/api/hospitals?lat=19.040212&lon=72.861634&radius_km=5", headers=auth(t)).json()
    assert [x["name"] for x in r["results"]] == ["Near Clinic", "Far Hospital"]
    assert r["results"][0]["address"] == "MG Road, Mumbai" and r["results"][1]["emergency"] is True
    assert "OpenStreetMap" in r["attribution"]
    # Only ~110 m precision leaves our server.
    assert "19.04," in sent[0] and "72.862" in sent[0] and "19.040212" not in sent[0]
    assert client.get("/api/hospitals?lat=19&lon=72", ).status_code == 401


def test_hospitals_unavailable(client, mailbox, monkeypatch):
    def boom(q):
        raise places.PlacesUnavailable("down")

    monkeypatch.setattr(places, "local_index", lambda: None)
    monkeypatch.setattr(places, "_fetch_overpass", boom)
    places._cache.clear()
    t = verified_login(client, mailbox)
    r = client.get("/api/hospitals?lat=12.97&lon=77.59", headers=auth(t))
    assert r.status_code == 503 and r.json()["detail"]["code"] == "places_unavailable"


def test_foods_to_avoid_matching():
    from app.services.diet import DAL, map_allergies

    a, i, u, d, _ = map_allergies(["curd", "dal"])
    assert DAL | {"yogurt"} <= i and not u
    # Whole-word matching: no accidental matches inside other words.
    a, i, u, d, _ = map_allergies(["Peanuts"])
    assert a == {"peanut"} and "peas" not in i
    a, i, u, d, _ = map_allergies(["lentils"])
    assert "sesame" not in a and "lentil" in i
    # Indian languages and scripts, several foods in one entry, dish names.
    for text in (["దాల్, పెరుగు"], ["मुझे दही और दाल नहीं चाहिए"], ["பருப்பு", "தயிர்"]):
        _, i, u, _, _ = map_allergies(text)
        assert DAL | {"yogurt"} <= i and not u, text
    _, _, _, d, _ = map_allergies(["poha"])
    assert d == {"poha"}
    _, _, u, _, _ = map_allergies(["unicorn meat?"])
    assert u == [] or u == ["unicorn meat?"]


def test_plan_excludes_avoided_foods_and_reports_them(client, mailbox):
    t = _setup(client, mailbox, dietary_preference="vegetarian", food_allergies=["curd", "dal", "xyzfood"])
    plan = client.post("/api/diet/plans", headers=auth(t), json={"days": 7}).json()
    dishes = diet_svc.foods()["dishes"]
    avoid = diet_svc.DAL | {"yogurt"}
    for day in plan["plan"]["days"]:
        for m in day["meals"]:
            assert not set(dishes[m["dish"]]["ingredients"]) & avoid, m["dish"]
    codes = {n["code"]: n for n in plan["plan"]["notes"]}
    assert codes["excluded_foods"]["items"] == ["curd", "dal"]
    assert codes["allergies_unmapped"]["items"] == ["xyzfood"]


def test_local_extract_answers_without_overpass(client, mailbox, monkeypatch):
    import numpy as np

    els = [e for e in FAKE if "lat" in e or "center" in e]
    els = [{**e, "lat": e.get("lat") or e["center"]["lat"], "lon": e.get("lon") or e["center"]["lon"]} for e in els]
    idx = {
        "elements": els, "bbox": [6.0, 68.0, 36.0, 98.0],
        "lat": np.radians([e["lat"] for e in els]), "lon": np.radians([e["lon"] for e in els]),
        "kind": np.array([places._kind(e["tags"]) for e in els]),
    }
    monkeypatch.setattr(places, "local_index", lambda: idx)

    def never(q):
        raise AssertionError("Overpass must not be called inside local coverage")

    monkeypatch.setattr(places, "_fetch_overpass", never)
    t = verified_login(client, mailbox)
    r = client.get("/api/hospitals?lat=19.040212&lon=72.861634&radius_km=5", headers=auth(t)).json()
    assert [x["name"] for x in r["results"]] == ["Near Clinic", "Far Hospital"]
    # Outside coverage (e.g. London) falls back to live Overpass.
    monkeypatch.setattr(places, "_fetch_overpass", lambda q: [])
    places._cache.clear()
    assert client.get("/api/hospitals?lat=51.5&lon=-0.12&radius_km=5", headers=auth(t)).json()["results"] == []
