import logging

from fastapi import APIRouter, HTTPException

from app.schemas.wine_label import (
    WineLabelRequest,
    WineLabelResponse,
    WineLabelError,
    WineAnalysis,
    WineInfo,
    CellarWine,
)
from app.services.supabase_storage import create_signed_url
from app.services.wine_analysis import analyze_wine_label
from app.services.wine_cellar import (
    find_existing_wine,
    create_wine,
    add_to_user_cellar,
    get_wine_with_cellar_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wine-label"])


@router.post(
    "/wine-label-analysis",
    response_model=WineLabelResponse,
    responses={
        400: {"model": WineLabelError},
        422: {"model": WineLabelError},
        502: {"model": WineLabelError},
    },
)
async def wine_label_analysis(request: WineLabelRequest):
    file_path = request.file_path.strip()
    if not file_path:
        raise HTTPException(
            status_code=400,
            detail="file_path ne peut pas être vide",
        )

    # 1. Générer la signed URL Supabase (bucket wine-labels dédié)
    try:
        signed_url = create_signed_url(file_path, bucket_name="wine-labels")
    except ValueError as e:
        logger.error("Configuration Supabase manquante: %s", e)
        raise HTTPException(status_code=500, detail="Configuration serveur incomplète")
    except RuntimeError as e:
        logger.error("Erreur Supabase signed URL: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Impossible de récupérer l'image depuis le stockage: {e}",
        )

    # 2. Analyser l'étiquette avec le modèle vision
    try:
        result = analyze_wine_label(signed_url)
    except RuntimeError as e:
        logger.error("Erreur modèle vision: %s", e)
        raise HTTPException(
            status_code=502,
            detail="Le service d'analyse d'étiquette est temporairement indisponible",
        )
    except ValueError as e:
        logger.error("Réponse invalide du modèle: %s", e)
        raise HTTPException(
            status_code=502,
            detail="Le modèle a retourné une réponse invalide",
        )

    # 3. Vérifier si le modèle signale une étiquette inexploitable
    if "error" in result:
        raise HTTPException(
            status_code=400,
            detail=result.get("detail", "Étiquette inexploitable par le modèle"),
        )

    wine_data = result.get("wine_data", {})
    chat_response = result.get("chat_response", "Vin analysé avec succès")

    # 4. Chercher si le vin existe déjà
    try:
        existing_wine = find_existing_wine(wine_data)
        wine_added = False
        cellar_wine_entry = None

        if existing_wine:
            # Le vin existe, l'ajouter directement à la cave
            logger.info(f"Vin existant trouvé: {existing_wine['name']}")
            cellar_wine_entry = add_to_user_cellar(
                user_id=request.user_id,
                wine_id=existing_wine["id"],
                stock=request.stock,
                notes=request.custom_notes,
                location=request.location,
            )
        else:
            # Créer le vin puis l'ajouter à la cave
            logger.info(f"Création nouveau vin: {wine_data.get('name', 'Inconnu')}")
            new_wine = create_wine(wine_data)
            cellar_wine_entry = add_to_user_cellar(
                user_id=request.user_id,
                wine_id=new_wine["id"],
                stock=request.stock,
                notes=request.custom_notes,
                location=request.location,
            )
            wine_added = True

        # 5. Récupérer les infos complètes pour la réponse
        wine_info, _ = get_wine_with_cellar_info(cellar_wine_entry)

        # Construire la réponse
        wine_analysis = WineAnalysis(**wine_data)
        wine_info_model = WineInfo(**wine_info)
        
        cellar_wine_model = CellarWine(
            id=cellar_wine_entry["id"],
            wine_id=cellar_wine_entry["wine_id"],
            user_id=cellar_wine_entry["user_id"],
            stock=cellar_wine_entry["stock"],
            rating=cellar_wine_entry.get("rating"),
            notes=cellar_wine_entry.get("notes"),
            location=cellar_wine_entry.get("location"),
            created_at=str(cellar_wine_entry["created_at"]),
            wine_info=wine_info_model,
        )

        return WineLabelResponse(
            chat_response=chat_response,
            wine_added=wine_added,
            cellar_wine=cellar_wine_model,
            wine_analysis=wine_analysis,
        )

    except Exception as e:
        logger.error("Erreur traitement cave: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de l'ajout du vin à votre cave",
        )
