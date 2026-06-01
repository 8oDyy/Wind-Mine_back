"""Service profil utilisateur + suppression de compte (table `profiles` + auth admin).

Utilise le client Supabase service_role : il bypasse RLS et donne accès à
l'API admin (`auth.admin`) pour supprimer réellement le compte auth — opération
impossible côté client Flutter, c'est la valeur ajoutée du backend.
"""
import logging
import os
from typing import Optional
from uuid import UUID

from supabase import create_client, Client

logger = logging.getLogger(__name__)

# Champs du profil modifiables via l'API (id/email restent exclus, jamais modifiables ici).
_PROFILE_UPDATABLE_FIELDS = ("niveau", "preference", "objectif", "prenom", "nom")


def _get_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant dans .env")
    return create_client(supabase_url, supabase_service_role_key)


def get_profile(user_id: UUID) -> Optional[dict]:
    """Retourne le profil de l'utilisateur, ou None s'il n'existe pas."""
    client = _get_client()
    try:
        response = (
            client.table("profiles")
            .select("id, email, prenom, nom, niveau, preference, objectif")
            .eq("id", str(user_id))
            .limit(1)
            .execute()
        )
        return response.data[0] if response.data else None
    except Exception as e:
        logger.error("Erreur lecture profil: %s", e)
        raise RuntimeError("Erreur lors de la lecture du profil") from e


def update_profile(user_id: UUID, fields: dict) -> Optional[dict]:
    """Met à jour les champs fournis (non-null) du profil de l'utilisateur.

    Si aucun champ exploitable n'est fourni, retourne simplement le profil courant.

    Returns:
        Le profil à jour, ou None si le profil n'existe pas.
    """
    client = _get_client()

    update_data = {
        field: fields[field]
        for field in _PROFILE_UPDATABLE_FIELDS
        if field in fields and fields[field] is not None
    }

    if not update_data:
        return get_profile(user_id)

    try:
        response = (
            client.table("profiles")
            .update(update_data)
            .eq("id", str(user_id))
            .execute()
        )
        if not response.data:
            return None
    except Exception as e:
        logger.error("Erreur mise à jour profil: %s", e)
        raise RuntimeError("Erreur lors de la mise à jour du profil") from e

    # La table `profiles` est la source de vérité, mais le front lit prenom/nom/etc.
    # depuis les `user_metadata` de l'auth (rechargement de session). On y répercute
    # donc les mêmes champs. Best-effort : un échec ne doit pas faire échouer le PATCH.
    _sync_user_metadata(client, user_id, update_data)

    return get_profile(user_id)


def _sync_user_metadata(client: Client, user_id: UUID, fields: dict) -> None:
    """Répercute `fields` dans les `user_metadata` de l'auth (merge, best-effort).

    `update_user_by_id` REMPLACE l'objet `user_metadata` : on lit donc les metadata
    courantes et on les fusionne pour ne perdre aucune clé existante. Toute erreur
    est seulement loggée (la table `profiles` reste la source de vérité).
    """
    try:
        current = client.auth.admin.get_user_by_id(str(user_id))
        existing = dict(getattr(current.user, "user_metadata", None) or {})
        existing.update(fields)
        client.auth.admin.update_user_by_id(str(user_id), {"user_metadata": existing})
    except Exception as e:
        logger.warning("Sync user_metadata échoué (profil déjà à jour en base): %s", e)


def delete_account(user_id: UUID) -> None:
    """Supprime définitivement le compte auth de l'utilisateur.

    Les tables liées (`profiles`, `user_cellar`, `dish_pictures`, `wine_labels`)
    ont des FK `ON DELETE CASCADE` vers `auth.users` : elles sont donc nettoyées
    automatiquement par la suppression du compte auth.
    """
    client = _get_client()
    try:
        client.auth.admin.delete_user(str(user_id))
    except Exception as e:
        logger.error("Erreur suppression compte auth: %s", e)
        raise RuntimeError("Erreur lors de la suppression du compte") from e
