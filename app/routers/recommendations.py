"""Endpoint « Découvertes » — recommandations de vins (`GET /api/discovery`).

JWT requis : les recommandations sont personnalisées par le profil et la cave de
l'utilisateur courant. L'`user_id` provient EXCLUSIVEMENT du token
(`get_current_user_id`), jamais du body ni de la query.

Réponse : une liste de catégories (carrousels). Les vins de chaque catégorie sont
les rows `wines` Supabase brutes (iso parser Flutter / fiche détail existante) ;
on ne les enveloppe ni ne les renomme.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.dependencies.auth import get_current_user_id
from app.schemas.recommendations import RecommendationsError, RecommendationsResponse
from app.services.recommendations import get_recommendations

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["discovery"])

_ERROR_RESPONSES = {
    401: {"model": RecommendationsError},
    502: {"model": RecommendationsError},
}


@router.get("/discovery", response_model=RecommendationsResponse, responses=_ERROR_RESPONSES)
async def get_discovery(
    limit_per_category: int = Query(12, ge=1, le=30, description="Nb de vins max par carrousel"),
    categories: str | None = Query(
        None,
        description="Clés de catégories CSV pour ne calculer qu'un sous-ensemble (ex. refresh d'une rangée)",
    ),
    user_id: UUID = Depends(get_current_user_id),
):
    """Retourne les carrousels de recommandations personnalisés de l'utilisateur."""
    only_keys = (
        {k.strip() for k in categories.split(",") if k.strip()} if categories else None
    )
    try:
        result = await get_recommendations(
            user_id,
            limit_per_category=limit_per_category,
            only_keys=only_keys,
        )
    except RuntimeError as e:
        logger.error("Erreur recommandations: %s", e)
        raise HTTPException(status_code=502, detail="Service de recommandations temporairement indisponible")

    return RecommendationsResponse(categories=result)
