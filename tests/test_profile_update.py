"""Tests de la mise à jour de profil — focus sur la whitelist des champs.

Aucun secret/base réels : on monkeypatch le client Supabase du service profil
pour capturer le payload envoyé à `.update(...)` et simuler le profil relu.
"""
import os

os.environ.setdefault("GITHUB_TOKEN", "dummy-ci-token")
os.environ.setdefault("SUPABASE_URL", "https://dummy.supabase.co")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key")
os.environ.setdefault("SUPABASE_BUCKET_NAME", "dummy-bucket")
os.environ.setdefault("SUPABASE_WINE_LABELS_BUCKET", "wine-labels")
os.environ.setdefault("SUPABASE_JWT_SECRET", "dummy-jwt-secret")
os.environ.setdefault("VISION_MODEL", "gpt-4o")

from uuid import uuid4  # noqa: E402

from app.schemas.profile import ProfileUpdateRequest  # noqa: E402
from app.services import profile as profile_service  # noqa: E402


class _FakeQuery:
    """Capture le payload `.update()` et renvoie une réponse PostgREST factice."""

    def __init__(self, store):
        self._store = store

    def update(self, data):
        self._store["update_payload"] = data
        return self

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def execute(self):
        return type("Resp", (), {"data": [self._store["row"]]})()


class _FakeAdmin:
    """Capture les appels au sync metadata et simule les metadata courantes."""

    def __init__(self, store):
        self._store = store

    def get_user_by_id(self, _uid):
        meta = self._store.get("existing_metadata", {})
        user = type("User", (), {"user_metadata": meta})()
        return type("Resp", (), {"user": user})()

    def update_user_by_id(self, _uid, attributes):
        self._store["metadata_payload"] = attributes


class _FakeAuth:
    def __init__(self, store):
        self.admin = _FakeAdmin(store)


class _FakeClient:
    def __init__(self, store):
        self._store = store
        self.auth = _FakeAuth(store)

    def table(self, _name):
        return _FakeQuery(self._store)


def _patch_client(monkeypatch, store):
    monkeypatch.setattr(profile_service, "_get_client", lambda: _FakeClient(store))


def test_update_profile_accepte_prenom_nom(monkeypatch):
    """prenom et nom traversent désormais la whitelist et sont envoyés à Supabase."""
    row = {
        "id": "u1", "email": "a@b.fr", "prenom": "Hugo", "nom": "Boulicaut",
        "niveau": "Amateur", "preference": "Vin Rouge", "objectif": "Découvrir",
    }
    store = {"row": row}
    _patch_client(monkeypatch, store)

    fields = ProfileUpdateRequest(
        prenom="Hugo", nom="Boulicaut", niveau="Amateur"
    ).model_dump(exclude_none=True)
    result = profile_service.update_profile(uuid4(), fields)

    assert store["update_payload"] == {"prenom": "Hugo", "nom": "Boulicaut", "niveau": "Amateur"}
    assert result == row


def test_update_profile_sync_user_metadata_en_mergeant(monkeypatch):
    """Les champs mis à jour sont répercutés dans user_metadata, sans perdre l'existant."""
    row = {"id": "u1", "email": "a@b.fr", "prenom": "Hugo", "nom": "Boulicaut",
           "niveau": "Amateur", "preference": None, "objectif": None}
    store = {
        "row": row,
        # Metadata déjà présentes côté auth qu'il ne faut PAS écraser.
        "existing_metadata": {"avatar_url": "https://x/y.png", "prenom": "Ancien"},
    }
    _patch_client(monkeypatch, store)

    profile_service.update_profile(uuid4(), {"prenom": "Hugo", "niveau": "Amateur"})

    # update_user_by_id reçoit l'objet user_metadata FUSIONNÉ (existant + nouveaux champs).
    assert store["metadata_payload"] == {
        "user_metadata": {
            "avatar_url": "https://x/y.png",  # préservé
            "prenom": "Hugo",                  # écrasé par la nouvelle valeur
            "niveau": "Amateur",               # ajouté
        }
    }


def test_update_profile_sync_metadata_echoue_sans_casser_le_patch(monkeypatch):
    """Si le sync metadata lève, le PATCH réussit quand même (table = source de vérité)."""
    row = {"id": "u1", "email": "a@b.fr", "prenom": "Hugo", "nom": "B",
           "niveau": None, "preference": None, "objectif": None}
    store = {"row": row}
    _patch_client(monkeypatch, store)

    # Force le sync à échouer.
    def _boom(_self, _uid):
        raise RuntimeError("auth indisponible")

    monkeypatch.setattr(_FakeAdmin, "get_user_by_id", _boom)

    result = profile_service.update_profile(uuid4(), {"prenom": "Hugo"})

    assert store["update_payload"] == {"prenom": "Hugo"}
    assert result == row  # le profil à jour est bien renvoyé malgré l'échec du sync


def test_update_profile_exclut_id_et_email(monkeypatch):
    """Même fournis, id/email ne doivent jamais être écrits via cette API."""
    row = {"id": "u1", "email": "a@b.fr", "prenom": "Hugo", "nom": "B",
           "niveau": None, "preference": None, "objectif": None}
    store = {"row": row}
    _patch_client(monkeypatch, store)

    # On force des champs interdits dans le dict brut (hors schéma).
    result = profile_service.update_profile(
        uuid4(), {"id": "spoof", "email": "evil@x.fr", "prenom": "Hugo"}
    )

    assert store["update_payload"] == {"prenom": "Hugo"}
    assert "id" not in store["update_payload"]
    assert "email" not in store["update_payload"]
    assert result == row


def test_update_profile_sans_champ_exploitable_relit_le_profil(monkeypatch):
    """Aucun champ exploitable → pas d'update, on renvoie le profil courant."""
    row = {"id": "u1", "email": "a@b.fr", "prenom": "Hugo", "nom": "B",
           "niveau": None, "preference": None, "objectif": None}
    store = {"row": row}
    _patch_client(monkeypatch, store)

    result = profile_service.update_profile(uuid4(), {})

    assert "update_payload" not in store  # .update() jamais appelé
    assert result == row


def test_schema_expose_prenom_nom():
    """Le schéma de requête accepte explicitement prenom et nom."""
    champs = ProfileUpdateRequest.model_fields.keys()
    assert "prenom" in champs
    assert "nom" in champs
