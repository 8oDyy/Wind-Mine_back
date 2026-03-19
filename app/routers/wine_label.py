import logging

from fastapi import APIRouter, HTTPException

from app.schemas.wine_label import (
    WineLabelRequest,
    WineLabelResponse,
    WineLabelError,
    WineAnalysis,
    WineInfo,
    CellarWine,
    WineProposal,
)
from app.services.supabase_storage import create_signed_url
from app.services.wine_analysis import analyze_wine_label
from app.services.wine_cellar import (
    find_similar_wine,
    create_wine,
    add_to_user_cellar,
    get_wine_with_cellar_info,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["wine-label"])


def _get_match_confidence(match_type: str) -> float:
    """Retourne un score de confiance selon le type de correspondance."""
    confidence_map = {
        "exact": 1.0,
        "same_wine_different_year": 0.9,
        "similar_name_same_winery": 0.8,
        "same_winery_region": 0.7,
        "same_region_similar_name": 0.6,
        "no_match": 0.0
    }
    return confidence_map.get(match_type, 0.0)


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

    # 4. Chercher un vin similaire et préparer les propositions
    try:
        similar_wine, match_type = find_similar_wine(wine_data)
        
        # Préparer la proposition de vin existant
        existing_proposal = None
        if similar_wine:
            existing_proposal = {
                "id": similar_wine["id"],
                "name": similar_wine["name"],
                "winery": similar_wine.get("winery"),
                "year": similar_wine.get("year"),
                "region": similar_wine.get("region"),
                "country": similar_wine.get("country"),
                "variety": similar_wine.get("variety"),
                "type": similar_wine.get("type"),
                "match_type": match_type,
                "match_confidence": _get_match_confidence(match_type)
            }
            
            # Adapter le message selon le type de correspondance
            if match_type == "exact":
                match_message = f"🎉 **Vin identifié !**\n\n{similar_wine['name']} ({similar_wine.get('year', 'N/A')}) existe déjà dans notre catalogue."
            elif match_type in ["same_wine_different_year", "similar_name_same_winery"]:
                match_message = f"🔍 **Vin très similaire trouvé !**\n\nJ'ai trouvé : {similar_wine['name']} ({similar_wine.get('year', 'N/A')}) - probablement le même vin avec une légère variation."
            else:
                match_message = f"🍷 **Correspondance détectée !**\n\nJ'ai identifié : {similar_wine['name']} ({similar_wine.get('year', 'N/A')}) qui correspond à votre étiquette."
        else:
            match_message = "🔍 **Aucune correspondance trouvée** dans notre catalogue actuel."
        
        # Préparer la proposition de nouveau vin
        new_proposal = {
            "name": wine_data.get("name"),
            "winery": wine_data.get("winery"),
            "year": wine_data.get("year"),
            "region": wine_data.get("region"),
            "country": wine_data.get("country"),
            "variety": wine_data.get("variety"),
            "type": wine_data.get("type"),
            "alcohol_percentage": wine_data.get("alcohol_percentage"),
            "description": wine_data.get("description"),
            "designation": wine_data.get("designation"),
            "sub_region": wine_data.get("sub_region"),
            "confidence": wine_data.get("confidence", 0.0)
        }
        
        # Construire le message conversationnel
        chat_response = f"""{match_message}

J'ai analysé votre étiquette et voici mes propositions :

**Option 1 - Vin existant** : {existing_proposal['name'] if existing_proposal else 'Non disponible'}
{'- ' + existing_proposal.get('winery', '') + ' - ' + str(existing_proposal.get('year', 'N/A')) if existing_proposal else ''}

**Option 2 - Nouveau vin** : {new_proposal['name']}
{'- ' + new_proposal.get('winery', '') + ' - ' + str(new_proposal.get('year', 'N/A'))}

Choisissez l'option qui vous convient le mieux. Vous pourrez ensuite ajouter le vin sélectionné à votre cave.

{chat_response}"""

        # 5. Construire la réponse avec les propositions
        wine_analysis = WineAnalysis(**wine_data)
        
        # Créer les objets WineProposal
        existing_proposal_obj = WineProposal(**existing_proposal) if existing_proposal else None
        new_proposal_obj = WineProposal(**new_proposal)

        return WineLabelResponse(
            chat_response=chat_response,
            existing_proposal=existing_proposal_obj,
            new_proposal=new_proposal_obj,
            wine_analysis=wine_analysis,
        )

    except Exception as e:
        logger.error("Erreur traitement cave: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Erreur lors de l'ajout du vin à votre cave",
        )
