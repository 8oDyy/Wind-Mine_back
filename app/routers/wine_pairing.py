import logging

from fastapi import APIRouter, HTTPException

from app.schemas.wine_pairing import (
    WinePairingRequest,
    WinePairingResponse,
    WinePairingError,
)
from app.services.supabase_storage import create_signed_url
from app.services.vision import analyze_dish_image

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wine-pairing"])


@router.post(
    "/wine-pairing",
    response_model=WinePairingResponse,
    responses={
        400: {"model": WinePairingError},
        422: {"model": WinePairingError},
        502: {"model": WinePairingError},
    },
)
async def wine_pairing(request: WinePairingRequest):
    file_path = request.file_path.strip()
    if not file_path:
        raise HTTPException(
            status_code=400,
            detail="file_path ne peut pas être vide ou composé uniquement d'espaces",
        )

    # 1. Générer la signed URL Supabase
    try:
        signed_url = create_signed_url(file_path)
    except ValueError as e:
        logger.error("Configuration Supabase manquante: %s", e)
        raise HTTPException(status_code=500, detail="Configuration serveur incomplète")
    except RuntimeError as e:
        logger.error("Erreur Supabase signed URL: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de récupérer l'image depuis le stockage: {e}",
        )

    # 2. Appeler le modèle vision
    try:
        result = analyze_dish_image(signed_url, request.user_note)
    except RuntimeError as e:
        logger.error("Erreur modèle vision: %s", e)
        raise HTTPException(
            status_code=502,
            detail="Le service d'analyse d'image est temporairement indisponible",
        )
    except ValueError as e:
        logger.error("Réponse invalide du modèle: %s", e)
        raise HTTPException(
            status_code=502,
            detail="Le modèle a retourné une réponse invalide",
        )

    # 3. Vérifier si le modèle signale une image inexploitable
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result.get("detail", "Image inexploitable par le modèle"),
        )

    # 4. Valider et retourner la réponse structurée
    try:
        return WinePairingResponse(**result)
    except Exception as e:
        logger.error("Réponse du modèle non conforme au schéma: %s", e)
        raise HTTPException(
            status_code=502,
            detail="La réponse du modèle ne correspond pas au format attendu",
        )
