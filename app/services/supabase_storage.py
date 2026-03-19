import logging
import os

from supabase import create_client, Client

logger = logging.getLogger(__name__)


def _get_client() -> Client:
    supabase_url = os.getenv("SUPABASE_URL")
    supabase_service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    
    if not supabase_url or not supabase_service_role_key:
        raise RuntimeError("SUPABASE_URL ou SUPABASE_SERVICE_ROLE_KEY manquant dans .env")
    return create_client(supabase_url, supabase_service_role_key)


def create_signed_url(file_path: str, expires_in: int = 300) -> str:
    """Génère une signed URL temporaire pour un fichier dans le bucket Supabase.

    Args:
        file_path: Chemin du fichier dans le bucket.
        expires_in: Durée de validité en secondes (défaut 5 min).

    Returns:
        URL signée temporaire.

    Raises:
        ValueError: Si le bucket n'est pas configuré.
        RuntimeError: Si la génération échoue côté Supabase.
    """
    supabase_bucket_name = os.getenv("SUPABASE_BUCKET_NAME")
    if not supabase_bucket_name:
        raise ValueError("SUPABASE_BUCKET_NAME manquant dans .env")

    try:
        client = _get_client()
        response = client.storage.from_(supabase_bucket_name).create_signed_url(
            file_path, expires_in
        )
    except (ValueError, RuntimeError):
        raise
    except Exception as e:
        logger.error("Erreur Supabase lors de la génération de la signed URL: %s", e)
        raise RuntimeError(f"Impossible de générer la signed URL pour '{file_path}'") from e

    signed_url = None
    if isinstance(response, dict):
        signed_url = response.get("signedURL") or response.get("signedUrl")

    if not signed_url:
        logger.error("Réponse Supabase inattendue: %s", response)
        raise RuntimeError(f"Réponse Supabase inattendue pour '{file_path}'")

    return signed_url
