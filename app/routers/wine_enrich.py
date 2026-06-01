"""Endpoint d'enrichissement d'un vin du catalogue.

Génère via LLM (variante texte-only) le profil gustatif, les accords mets-vin et
la fenêtre de garde d'un vin à partir de ses seules métadonnées, puis les persiste
dans la row `wines`.

JWT requis : `wines` est un catalogue global (pas une ressource possédée), donc
l'`user_id` ne filtre pas l'accès — le token sert uniquement à protéger un appel
LLM coûteux, comme pour `wine-label-analysis`.

Idempotent : si le vin a déjà des données d'enrichissement (profil gustatif hors
défaut 0.5, accords renseignés, ou fenêtre de garde), il est renvoyé tel quel sans
appel LLM.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth import get_current_user_id
from app.schemas.wine_enrich import WineEnrichResponse, WineEnrichError
from app.services.wine_analysis import enrich_wine_from_metadata
from app.services.wine_cellar import get_wine_by_id, update_wine_enrichment

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wine-enrich"])

_DEFAULT_LEVEL = 0.5


def _already_enriched(wine: dict) -> bool:
    """Vrai si le vin ne doit pas être (ré)enrichi.

    Critère primaire : marqueur `enriched_at` posé (génération déjà effectuée).
    Filet secondaire : des données réelles existent déjà (gustatif hors défaut,
    accords, ou fenêtre de garde) — couvre un vin legacy enrichi sans flag.
    Ce test ne déclenche JAMAIS un appel LLM superflu (lecture seule).
    """
    if wine.get("enriched_at") is not None:
        return True
    levels_set = any(
        wine.get(field) is not None and wine.get(field) != _DEFAULT_LEVEL
        for field in ("body_level", "tannin_level", "fruit_level")
    )
    pairings_set = bool(wine.get("food_pairings"))
    window_set = any(
        wine.get(field) is not None
        for field in ("drink_from", "peak_year", "drink_to")
    )
    return levels_set or pairings_set or window_set


def _clean_enrichment(data: dict) -> dict:
    """Normalise la sortie LLM : niveaux 0.0-1.0, années int, accords liste de str."""
    cleaned: dict = {}

    for field in ("body_level", "tannin_level", "fruit_level"):
        if field in data:
            try:
                value = float(data[field])
                cleaned[field] = value if 0.0 <= value <= 1.0 else _DEFAULT_LEVEL
            except (ValueError, TypeError):
                cleaned[field] = _DEFAULT_LEVEL

    for field in ("drink_from", "peak_year", "drink_to"):
        if field in data:
            try:
                cleaned[field] = int(data[field])
            except (ValueError, TypeError):
                cleaned[field] = None

    if "food_pairings" in data:
        food = data["food_pairings"]
        if isinstance(food, list):
            cleaned["food_pairings"] = [str(item).strip() for item in food if str(item).strip()]

    return cleaned


@router.post(
    "/wine/{wine_id}/enrich",
    response_model=WineEnrichResponse,
    responses={
        401: {"model": WineEnrichError},
        404: {"model": WineEnrichError},
        502: {"model": WineEnrichError},
    },
)
async def enrich_wine(
    wine_id: UUID,
    _user_id: UUID = Depends(get_current_user_id),
):
    """Enrichit un vin du catalogue (profil gustatif + accords + fenêtre de garde)."""
    try:
        wine = get_wine_by_id(wine_id)
    except RuntimeError as e:
        logger.error("Erreur lecture vin %s: %s", wine_id, e)
        raise HTTPException(status_code=502, detail="Service vin temporairement indisponible")

    if wine is None:
        raise HTTPException(status_code=404, detail="Vin introuvable")

    # Idempotence : enriched_at posé (primaire) ou données déjà présentes (filet) → pas de LLM.
    if _already_enriched(wine):
        return WineEnrichResponse(enriched=False, wine=wine)

    # Générer l'enrichissement via le LLM (texte-only).
    try:
        result = enrich_wine_from_metadata(wine)
    except RuntimeError as e:
        logger.error("Erreur modèle enrichissement vin %s: %s", wine_id, e)
        raise HTTPException(status_code=502, detail="Le service d'enrichissement est temporairement indisponible")
    except ValueError as e:
        logger.error("Réponse invalide du modèle (enrichissement %s): %s", wine_id, e)
        raise HTTPException(status_code=502, detail="Le modèle a retourné une réponse invalide")

    # Le modèle signale des métadonnées insuffisantes : on renvoie le vin inchangé.
    if "error" in result:
        return WineEnrichResponse(enriched=False, wine=wine)

    enrichment = _clean_enrichment(result)

    try:
        updated = update_wine_enrichment(wine_id, enrichment)
    except RuntimeError as e:
        logger.error("Erreur persistance enrichissement vin %s: %s", wine_id, e)
        raise HTTPException(status_code=502, detail="Service vin temporairement indisponible")

    if updated is None:
        raise HTTPException(status_code=404, detail="Vin introuvable")

    return WineEnrichResponse(enriched=True, wine=updated)
