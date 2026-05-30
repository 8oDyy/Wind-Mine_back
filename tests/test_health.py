"""Smoke tests CI — ne nécessitent aucun secret réel.

On injecte des variables d'environnement factices AVANT d'importer l'app
(app.main lève une RuntimeError au démarrage si aucun token n'est présent).
Ces tests vérifient que l'application se charge et que /health répond.
"""
import os

os.environ.setdefault("GITHUB_TOKEN", "dummy-ci-token")
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("SUPABASE_BUCKET_NAME", "dummy-bucket")
os.environ.setdefault("SUPABASE_WINE_LABELS_BUCKET", "wine-labels")
os.environ.setdefault("SUPABASE_JWT_SECRET", "dummy-jwt-secret")
os.environ.setdefault("VISION_MODEL", "gpt-4o")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def test_health_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_routes_present():
    """Garantit que les routers métier sont bien montés."""
    schema = client.get("/openapi.json").json()
    paths = set(schema["paths"])
    expected_routes = (
        "/health",
        "/chat",
        "/api/wine-pairing",
        "/api/cellar",
        "/api/cellar/last",
        "/api/cellar/{cellar_id}",
        "/api/cellar/{cellar_id}/stock",
        "/api/profile",
        "/api/account",
    )
    for expected in expected_routes:
        assert expected in paths, f"route manquante: {expected}"


def test_protected_endpoints_require_jwt():
    """Sans en-tête Authorization, les endpoints cave/profil renvoient 401."""
    assert client.get("/api/cellar").status_code == 401
    assert client.get("/api/cellar/last").status_code == 401
    assert client.post("/api/cellar", json={"stock": 1}).status_code == 401
    assert client.patch("/api/profile", json={}).status_code == 401
    assert client.delete("/api/account").status_code == 401


def test_invalid_jwt_rejected():
    """Un token bidon est rejeté avec 401 (et non 500)."""
    headers = {"Authorization": "Bearer not-a-real-token"}
    assert client.get("/api/cellar", headers=headers).status_code == 401
