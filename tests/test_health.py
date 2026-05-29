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
    for expected in ("/health", "/chat", "/api/wine-pairing"):
        assert expected in paths, f"route manquante: {expected}"
