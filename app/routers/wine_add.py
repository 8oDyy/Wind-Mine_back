import logging

from fastapi import APIRouter, HTTPException

from app.schemas.wine_add import WineAddRequest, WineAddResponse, WineAddError
from app.services.wine_cellar import create_wine, add_to_user_cellar, get_wine_with_cellar_info

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wine-add"])


@router.post(
    "/wine-label-add",
    response_model=WineAddResponse,
    responses={
        400: {"model": WineAddError},
        422: {"model": WineAddError},
        500: {"model": WineAddError},
    },
)
async def add_wine_to_cellar(request: WineAddRequest):
    """Ajoute un vin à la cave de l'utilisateur.
    
    Soit un vin existant (wine_id), soit un nouveau vin (wine_data).
    """
    # Validation des entrées
    if not request.wine_id and not request.wine_data:
        raise HTTPException(
            status_code=400,
            detail="Fournir soit wine_id (vin existant) soit wine_data (nouveau vin)",
        )
    
    if request.wine_id and request.wine_data:
        raise HTTPException(
            status_code=400,
            detail="Fournir soit wine_id soit wine_data, pas les deux",
        )
    
    try:
        wine_added = False
        wine_id_to_add = None
        
        if request.wine_id:
            # Ajouter un vin existant
            logger.info(f"Ajout vin existant {request.wine_id} à la cave de {request.user_id}")
            wine_id_to_add = request.wine_id
            message = f"Vin existant ajouté à votre cave avec succès !"
        
        else:
            # Créer un nouveau vin puis l'ajouter
            logger.info(f"Création nouveau vin et ajout à la cave de {request.user_id}")
            new_wine = create_wine(request.wine_data)
            wine_id_to_add = new_wine["id"]
            wine_added = True
            message = f"Nouveau vin '{new_wine['name']}' créé et ajouté à votre cave !"
        
        # Ajouter à la cave de l'utilisateur
        cellar_wine_entry = add_to_user_cellar(
            user_id=request.user_id,
            wine_id=wine_id_to_add,
            stock=request.stock,
            notes=request.custom_notes,
            location=request.location,
        )
        
        # Récupérer les infos complètes du vin
        wine_info, _ = get_wine_with_cellar_info(cellar_wine_entry)
        
        return WineAddResponse(
            success=True,
            message=message,
            wine_added=wine_added,
            cellar_wine=cellar_wine_entry,
            wine_info=wine_info,
        )
        
    except Exception as e:
        logger.error("Erreur ajout vin à la cave: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de l'ajout du vin à votre cave",
        )
