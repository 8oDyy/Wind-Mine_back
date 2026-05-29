"""Endpoints profil + suppression de compte (JWT requis).

L'`user_id` provient exclusivement du JWT. La suppression de compte effectue
une vraie suppression du compte auth (impossible côté client Flutter) ; les
tables liées sont nettoyées par cascade FK.
"""
import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.dependencies.auth import get_current_user_id
from app.schemas.profile import ProfileError, ProfileUpdateRequest
from app.services.profile import delete_account, get_profile, update_profile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["profile"])

_ERROR_RESPONSES = {
    401: {"model": ProfileError},
    404: {"model": ProfileError},
    502: {"model": ProfileError},
}


@router.patch("/profile", responses=_ERROR_RESPONSES)
async def patch_profile(
    request: ProfileUpdateRequest,
    user_id: UUID = Depends(get_current_user_id),
):
    """Met à jour les champs fournis du profil (niveau, preference, objectif)."""
    try:
        profile = update_profile(user_id, request.model_dump(exclude_none=True))
    except RuntimeError as e:
        logger.error("Erreur mise à jour profil: %s", e)
        raise HTTPException(status_code=502, detail="Service de profil temporairement indisponible")

    if profile is None:
        raise HTTPException(status_code=404, detail="Profil introuvable")
    return profile


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT, responses=_ERROR_RESPONSES, tags=["account"])
async def delete_my_account(user_id: UUID = Depends(get_current_user_id)):
    """Supprime définitivement le compte de l'utilisateur (auth + données liées par cascade)."""
    try:
        delete_account(user_id)
    except RuntimeError as e:
        logger.error("Erreur suppression compte: %s", e)
        raise HTTPException(status_code=502, detail="Service de compte temporairement indisponible")

    return Response(status_code=status.HTTP_204_NO_CONTENT)
