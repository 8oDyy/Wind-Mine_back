"""Tests de l'endpoint « Découvertes » (`GET /api/discovery`) et de son service.

Comme `test_health.py`, on injecte des variables d'environnement factices AVANT
d'importer l'app. On ne touche jamais Supabase : les fonctions d'accès base sont
mockées, et l'auth JWT est court-circuitée via `dependency_overrides`.
"""
import os

os.environ.setdefault("GITHUB_TOKEN", "dummy-ci-token")
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("SUPABASE_BUCKET_NAME", "dummy-bucket")
os.environ.setdefault("SUPABASE_WINE_LABELS_BUCKET", "wine-labels")
os.environ.setdefault("SUPABASE_JWT_SECRET", "dummy-jwt-secret")
os.environ.setdefault("VISION_MODEL", "gpt-4o")

from uuid import UUID  # noqa: E402

import anyio  # noqa: E402
import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.dependencies.auth import get_current_user_id  # noqa: E402
from app.main import app  # noqa: E402
from app.services import recommendations as svc  # noqa: E402

_USER_ID = UUID("11111111-1111-1111-1111-111111111111")

# Contexte cave "vide" complet (toutes les clés attendues par _build_category_specs).
_EMPTY_CELLAR = {
    "owned_wine_ids": [], "owned_regions": [],
    "dominant_region": None, "dominant_type": None, "budget": None,
}


@pytest.fixture
def client_authed():
    """TestClient avec l'auth JWT court-circuitée (user_id fixe)."""
    app.dependency_overrides[get_current_user_id] = lambda: _USER_ID
    yield TestClient(app)
    app.dependency_overrides.pop(get_current_user_id, None)


# ─────────────────────────── Logique pure du service ───────────────────────────

def test_median_odd_even():
    assert svc._median([10.0]) == 10.0
    assert svc._median([30.0, 10.0, 20.0]) == 20.0
    assert svc._median([10.0, 20.0, 30.0, 40.0]) == 25.0


def test_normalize_deaccents():
    assert svc._normalize("  Vin Pétillant ") == "vin petillant"
    assert svc._normalize(None) == ""


def test_slug_ascii():
    assert svc._slug("Côtes du Rhône") == "cotes-du-rhone"
    assert svc._slug("Bordeaux") == "bordeaux"


def test_map_preference_substring():
    """`profiles.preference` libre -> `wines.type` par sous-chaîne désaccentuée.

    Libellés réels d'onboarding (multi-sélection jointe par « , », préfixe « Vin ») :
    Vin Rouge / Vin Rosé / Vin Blanc / Vin Pétillant / Pas de préférence.
    """
    assert svc._map_preference("Vin Pétillant") == "Champagne"   # valeur réelle en base
    assert svc._map_preference("Vin Rouge") == "Rouge"
    assert svc._map_preference("Vin Rosé") == "Rosé"
    assert svc._map_preference("Vin Blanc") == "Blanc"
    # Multi-sélection : on renvoie un type (le premier matché), jamais None ni bancal.
    assert svc._map_preference("Vin Rouge, Vin Blanc") == "Rouge"
    # "Pas de préférence" ne contient aucun mot-clé type => None (=> for_you via cave, ou omis).
    assert svc._map_preference("Pas de préférence") is None
    assert svc._map_preference(None) is None
    assert svc._map_preference("Apprendre") is None  # libellé non mappable => pas de for_you


def test_preferred_type_priority():
    """La préférence mappée prime ; sinon repli sur le type dominant de la cave."""
    assert svc._preferred_type({"preference": "Vin Pétillant"}, {"dominant_type": "Rouge"}) == "Champagne"
    assert svc._preferred_type({"preference": None}, {"dominant_type": "Blanc"}) == "Blanc"
    assert svc._preferred_type({}, {}) is None


def test_build_specs_fallback_profile_vide():
    """Profil + cave vides : pas de for_you/region, mais top_rated + affordable + types + discover + prestige."""
    specs = svc._build_category_specs(profile={}, cellar=_EMPTY_CELLAR, limit=12)
    keys = [s["key"] for s in specs]
    assert "for_you" not in keys
    assert not any(k.startswith("region_") for k in keys)
    assert "top_rated" in keys
    assert "affordable" in keys
    assert "discover" in keys
    assert "prestige" in keys
    assert keys[-1] == "prestige"  # rangée prestige toujours en bas
    # Au plus _MAX_TYPE_CATEGORIES carrousels "par type".
    type_keys = [k for k in keys if k in {"red", "white", "sparkling", "rose"}]
    assert 0 < len(type_keys) <= svc._MAX_TYPE_CATEGORIES


def test_build_specs_price_caps():
    """Plafond grand public sur toutes les rangées sauf `affordable` (budget propre) et `prestige` (sans plafond).

    On inspecte les params PostgREST réellement générés par chaque `build`.
    """
    from postgrest import SyncPostgrestClient

    pg = SyncPostgrestClient("http://localhost/rest/v1", schema="public", headers={"apikey": "x"})

    class _C:
        def table(self, n):
            return pg.table(n)

    profile = {"preference": "Vin Rouge"}
    cellar = {
        "owned_wine_ids": ["a"], "owned_regions": ["Bordeaux"],
        "dominant_region": "Bordeaux", "dominant_type": "Rouge", "budget": None,
    }
    for spec in svc._build_category_specs(profile, cellar, limit=12):
        params = dict(spec["build"](_C()).params)
        price = params.get("price")
        if spec["key"] == "prestige":
            assert price is None  # prestige assumé : aucun plafond
            assert params.get("points") == f"gte.{svc._PRESTIGE_MIN_POINTS}"
        elif spec["key"] == "affordable":
            assert price == "lte.20.0"  # budget par défaut (cave sans prix)
        else:
            # Toutes les autres rangées sont plafonnées au prix grand public.
            assert price == f"lte.{svc._MAX_EVERYDAY_PRICE}", f"{spec['key']} non plafonné: {price}"


def test_build_specs_personalized():
    """Profil + cave renseignés : for_you en tête, region_<slug>, type préféré non dupliqué."""
    profile = {"preference": "J'aime le rouge"}
    cellar = {
        "owned_wine_ids": ["a"], "owned_regions": ["Bordeaux"],
        "dominant_region": "Bordeaux", "dominant_type": "Rouge", "budget": 15.0,
    }
    specs = svc._build_category_specs(profile, cellar, limit=12)
    keys = [s["key"] for s in specs]
    assert keys[0] == "for_you"
    assert "region_bordeaux" in keys
    # "Rouge" est couvert par for_you => pas de carrousel "red" redondant.
    assert "red" not in keys
    # Une autre catégorie de type reste présente.
    assert "white" in keys


# ─────────────────────────── Orchestration (mockée) ───────────────────────────

def test_get_recommendations_omits_empty(monkeypatch):
    """Catégories sans vin omises ; ordre des specs préservé. Coroutine via `anyio.run`."""
    monkeypatch.setattr(svc, "_get_client", lambda: object())
    monkeypatch.setattr(svc, "_fetch_profile", lambda c, u: {})
    monkeypatch.setattr(svc, "_fetch_cellar_context", lambda c, u: dict(_EMPTY_CELLAR))
    monkeypatch.setattr(svc, "_build_category_specs", lambda p, c, l: [
        {"key": "for_you", "title": "Pour vous", "subtitle": None, "build": lambda c: "HAS"},
        {"key": "empty", "title": "Vide", "subtitle": None, "build": lambda c: "NONE"},
        {"key": "top_rated", "title": "Top", "subtitle": None, "build": lambda c: "HAS"},
    ])
    monkeypatch.setattr(svc, "_run", lambda q: [{"id": "w1"}] if q == "HAS" else [])

    svc._cache.clear()
    result = anyio.run(svc.get_recommendations, _USER_ID, 5)
    assert [c["key"] for c in result] == ["for_you", "top_rated"]


def test_get_recommendations_excludes_cellar(monkeypatch):
    """Les vins déjà en cave sont exclus : `_exclude_owned` retire l'id possédé du résultat.

    On simule `_run` en filtrant sur les ids passés à `not_.in_` capturés via un faux query.
    """
    owned = ["11111111-1111-1111-1111-111111111111"]
    catalog = [{"id": "w-free"}, {"id": owned[0]}]

    class FakeQuery:
        """Faux query builder qui ne retient que l'exclusion not.in_ pour le test."""
        def __init__(self):
            self.excluded = set()
            self._negate = False
        def select(self, *a, **k): return self
        def order(self, *a, **k): return self
        def limit(self, *a, **k): return self
        def eq(self, *a, **k): return self
        def gte(self, *a, **k): return self
        def lte(self, *a, **k): return self
        def neq(self, *a, **k): return self
        @property
        def not_(self):
            self._negate = True
            return self
        def in_(self, col, vals):
            if self._negate:
                self.excluded.update(vals)
                self._negate = False
            return self

    fq = FakeQuery()

    class FakeClient:
        def table(self, name): return fq

    monkeypatch.setattr(svc, "_get_client", lambda: FakeClient())
    monkeypatch.setattr(svc, "_fetch_profile", lambda c, u: {"preference": "rouge"})
    monkeypatch.setattr(svc, "_fetch_cellar_context", lambda c, u: {
        "owned_wine_ids": owned, "owned_regions": [],
        "dominant_region": None, "dominant_type": "Rouge", "budget": None,
    })
    # _run renvoie le catalogue moins les ids exclus collectés par le faux query.
    monkeypatch.setattr(svc, "_run", lambda q: [w for w in catalog if w["id"] not in q.excluded])

    svc._cache.clear()
    result = anyio.run(svc.get_recommendations, _USER_ID, 12)
    for_you = next(c for c in result if c["key"] == "for_you")
    ids = {w["id"] for w in for_you["wines"]}
    assert owned[0] not in ids  # vin de la cave exclu
    assert "w-free" in ids


def test_get_recommendations_cache(monkeypatch):
    """Deux appels successifs (sans only_keys) : le 2e est servi par le cache."""
    calls = {"profile": 0}

    def counting_profile(c, u):
        calls["profile"] += 1
        return {}

    monkeypatch.setattr(svc, "_get_client", lambda: object())
    monkeypatch.setattr(svc, "_fetch_profile", counting_profile)
    monkeypatch.setattr(svc, "_fetch_cellar_context", lambda c, u: dict(_EMPTY_CELLAR))
    monkeypatch.setattr(svc, "_build_category_specs", lambda p, c, l: [
        {"key": "top_rated", "title": "Top", "subtitle": None, "build": lambda c: "HAS"},
    ])
    monkeypatch.setattr(svc, "_run", lambda q: [{"id": "w1"}])

    svc._cache.clear()
    anyio.run(svc.get_recommendations, _USER_ID, 5)
    anyio.run(svc.get_recommendations, _USER_ID, 5)
    assert calls["profile"] == 1
    svc._cache.clear()


# ─────────────────────────── Endpoint (HTTP) ───────────────────────────

def test_discovery_endpoint_ok(client_authed, monkeypatch):
    """L'endpoint renvoie la forme {categories:[{key,title,subtitle,wines:[row brute]}]}."""
    async def fake_get(user_id, limit_per_category=12, only_keys=None):
        assert user_id == _USER_ID
        assert limit_per_category == 8
        return [
            {"key": "top_rated", "title": "Les mieux notés", "subtitle": None,
             "wines": [{"id": "w1", "name": "Château Test", "type": "Rouge", "points": 95}]},
        ]

    monkeypatch.setattr("app.routers.recommendations.get_recommendations", fake_get)
    resp = client_authed.get("/api/discovery?limit_per_category=8")
    assert resp.status_code == 200
    body = resp.json()
    assert body["categories"][0]["key"] == "top_rated"
    wine = body["categories"][0]["wines"][0]
    assert wine["name"] == "Château Test"  # row brute, clés catalogue inchangées
    assert wine["points"] == 95


def test_discovery_endpoint_categories_filter(client_authed, monkeypatch):
    """Le param `categories` (CSV) est transmis comme set de clés au service."""
    captured = {}

    async def fake_get(user_id, limit_per_category=12, only_keys=None):
        captured["only_keys"] = only_keys
        return []

    monkeypatch.setattr("app.routers.recommendations.get_recommendations", fake_get)
    resp = client_authed.get("/api/discovery?categories=for_you, top_rated")
    assert resp.status_code == 200
    assert captured["only_keys"] == {"for_you", "top_rated"}


def test_discovery_endpoint_limit_validation(client_authed):
    """limit_per_category hors bornes => 422."""
    assert client_authed.get("/api/discovery?limit_per_category=0").status_code == 422
    assert client_authed.get("/api/discovery?limit_per_category=99").status_code == 422
