"""Endpoints de gestion de la cave utilisateur.

Tous protégés par JWT Supabase : l'`user_id` provient EXCLUSIVEMENT du token
(`get_current_user_id`), jamais du body ni de la query. Une ressource qui
n'appartient pas à l'utilisateur renvoie 404.

Les réponses de lecture sont les rows `user_cellar` brutes de Supabase (avec
`wines` imbriqué), pour rester iso avec le parser Flutter existant.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies.auth import get_current_user_id
from app.schemas.cellar import CellarAddRequest, CellarError, CellarStockUpdateRequest
from app.services.wine_cellar import (
    add_to_user_cellar,
    delete_cellar_entry,
    get_cellar_entry,
    get_last_cellar_wine,
    list_user_cellar,
    update_cellar_stock,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["cellar"])

_ERROR_RESPONSES = {
    401: {"model": CellarError},
    404: {"model": CellarError},
    502: {"model": CellarError},
}


@router.get("/cellar", responses=_ERROR_RESPONSES)
async def get_cellar(user_id: UUID = Depends(get_current_user_id)):
    """Liste la cave de l'utilisateur (vin catalogue imbriqué), triée par ajout récent."""
    try:
        return list_user_cellar(user_id)
    except RuntimeError as e:
        logger.error("Erreur lecture cave: %s", e)
        raise HTTPException(status_code=502, detail="Service de cave temporairement indisponible")


@router.get("/cellar/last", responses=_ERROR_RESPONSES)
async def get_last_cellar(user_id: UUID = Depends(get_current_user_id)):
    """Retourne le dernier vin ajouté, ou 404 si la cave est vide."""
    try:
        entry = get_last_cellar_wine(user_id)
    except RuntimeError as e:
        logger.error("Erreur lecture dernier vin: %s", e)
        raise HTTPException(status_code=502, detail="Service de cave temporairement indisponible")

    if entry is None:
        raise HTTPException(status_code=404, detail="Aucun vin dans la cave")
    return entry


@router.post("/cellar", status_code=status.HTTP_201_CREATED, responses=_ERROR_RESPONSES)
async def add_cellar(
    request: CellarAddRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Ajoute un vin (catalogue via `wine_id`, ou custom via `custom_*`) à la cave."""
    extra = request.model_dump(
        exclude={"wine_id", "stock", "notes", "location"},
        exclude_none=True,
    )
    try:
        inserted = add_to_user_cellar(
            user_id=user_id,
            wine_id=request.wine_id,
            stock=request.stock,
            notes=request.notes,
            location=request.location,
            extra=extra,
        )
        # Re-SELECT pour renvoyer la forme complète (wines imbriqué).
        entry = get_cellar_entry(user_id, UUID(inserted["id"]))
    except RuntimeError as e:
        logger.error("Erreur ajout cave: %s", e)
        raise HTTPException(status_code=502, detail="Service de cave temporairement indisponible")

    return entry if entry is not None else inserted


@router.delete("/cellar/{cellar_id}", status_code=status.HTTP_204_NO_CONTENT, responses=_ERROR_RESPONSES)
async def delete_cellar(
    cellar_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
):
    """Retire une bouteille de la cave de l'utilisateur."""
    try:
        deleted = delete_cellar_entry(user_id, cellar_id)
    except RuntimeError as e:
        logger.error("Erreur suppression cave: %s", e)
        raise HTTPException(status_code=502, detail="Service de cave temporairement indisponible")

    if not deleted:
        raise HTTPException(status_code=404, detail="Entrée de cave introuvable")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/cellar/{cellar_id}/stock", responses=_ERROR_RESPONSES)
async def patch_cellar_stock(
    cellar_id: UUID,
    request: CellarStockUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Met à jour le stock d'une entrée de cave."""
    try:
        updated = update_cellar_stock(user_id, cellar_id, request.stock)
    except RuntimeError as e:
        logger.error("Erreur mise à jour stock: %s", e)
        raise HTTPException(status_code=502, detail="Service de cave temporairement indisponible")

    if updated is None:
        raise HTTPException(status_code=404, detail="Entrée de cave introuvable")
    return updated
